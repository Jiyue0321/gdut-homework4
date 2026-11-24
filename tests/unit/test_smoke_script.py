"""冒烟脚本自身的测试：确保 dry-run 不会发请求、判定逻辑可复现。

真跑一次要消耗 API 额度，所以这里只测「不发请求的部分」：参数解析、Key 检查、
断言汇总与记录落盘。真跑由 ``scripts/smoke_real_llm.py --run`` 手动触发。
"""

from __future__ import annotations

import json

import pytest

from agent.config import LLMConfig
from scripts import smoke_real_llm as smoke


class StubTools:
    """替代 MCP / LocalTools：返回固定结构，不启动子进程、不读文件。"""

    def check_resume_quality(self, text: str) -> dict:
        return {"length": len(text), "missing": [], "tips": []}

    def match_competencies(self, competencies) -> dict:
        return {
            "radar": [],
            "gaps": [{"competency": "系统设计", "gap": 2, "priority": "高"}],
        }

    def detect_industry(self, jd_text: str) -> str:
        return "互联网后端"


@pytest.fixture(autouse=True)
def stub_tools(monkeypatch):
    monkeypatch.setattr(smoke, "open_tool_provider", lambda config: StubTools())


def _config(key: str = "sk-" + "a" * 32, use_mcp: bool = False) -> LLMConfig:
    return LLMConfig(
        base_url="https://api.deepseek.com/v1",
        api_key=key,
        model="deepseek-chat",
        use_mcp=use_mcp,
    )


def test_dry_run_reports_config_without_calling_model(capsys):
    record = smoke.SmokeRecord(dry_run=True)
    code = smoke.dry_run(_config(), smoke.parse_args([]), record)

    assert code == 0
    assert record.passed
    assert record.industry == "互联网后端"
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "未发送任何请求" in out


def test_dry_run_rejects_missing_key():
    record = smoke.SmokeRecord(dry_run=True)
    code = smoke.dry_run(_config(key=""), smoke.parse_args([]), record)

    assert code == 2
    assert not record.passed
    assert record.checks[0].name == "API Key 已配置"


def test_dry_run_rejects_placeholder_key():
    """`.env.example` 里的中文占位符不是 Key，必须在发请求前就拦下。"""
    record = smoke.SmokeRecord(dry_run=True)
    code = smoke.dry_run(_config(key="请填入你的 Key"), smoke.parse_args([]), record)

    assert code == 2


def test_key_is_masked():
    masked = smoke.mask_key("sk-1234567890abcdef")

    assert masked.startswith("sk-123")
    assert "…cdef" in masked
    assert "567890" not in masked


def test_write_record_is_skipped_for_dry_run(tmp_path):
    record = smoke.SmokeRecord(dry_run=True)

    assert smoke.write_record(record, str(tmp_path)) is None
    assert list(tmp_path.iterdir()) == []


def test_write_record_serialises_checks(tmp_path):
    record = smoke.SmokeRecord(dry_run=False, model="deepseek-chat", overall_score=3.2)
    record.checks.append(smoke.Check("流程走到 DONE", True, "phase=done"))

    path = smoke.write_record(record, str(tmp_path))
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["passed"] is True
    assert payload["checks"][0]["name"] == "流程走到 DONE"
    assert payload["overall_score"] == 3.2


def test_collect_checks_flags_missing_cross_exam():
    session = smoke.InterviewSession()
    session.phase = smoke.Phase.DONE
    record = smoke.SmokeRecord(dry_run=False, first_round_seconds=9.0, overall_score=3.0,
                               verdict="基本达标")
    session.narrative = {"action_plan": ["一", "二", "三"]}
    args = smoke.parse_args(["--questions", "6"])

    from agent.state import AnswerScore, Turn

    session.turns = [
        Turn(slot_index=0, agent="hr", question="q", answer="a",
             score=AnswerScore(dimensions={}, overall=3, evidence="", comment=""))
        for _ in range(6)
    ]
    checks = smoke._collect_checks(session, record, args)
    by_name = {c.name: c for c in checks}

    assert by_name["流程走到 DONE"].passed
    assert by_name["交叉拷问已执行"].passed is False


def test_median_handles_even_and_odd():
    assert smoke._median([3.0]) == 3.0
    assert smoke._median([1.0, 2.0, 6.0]) == 2.0
    assert smoke._median([1.0, 2.0, 3.0, 4.0]) == 2.5
