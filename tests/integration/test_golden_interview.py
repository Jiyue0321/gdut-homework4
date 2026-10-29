"""Golden 集成测试：用脚本化假模型跑完整面试，比对报告快照。

快照文件在 tests/fixtures/golden/report.md。
若确需更新：pytest --update-golden
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.orchestrator import InterviewConfig, Orchestrator
from agent.state import Phase
from agent.tools import LocalTools
from tests.conftest import JD_TEXT, RESUME_TEXT, build_fake_llm

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "golden" / "report.md"


def run_interview(config: InterviewConfig | None = None):
    orchestrator = Orchestrator(build_fake_llm(), LocalTools(), config or InterviewConfig())
    session = orchestrator.start(RESUME_TEXT, JD_TEXT, "后端开发实习生")
    steps = 0
    while not session.finished and session.error == "" and steps < 20:
        session = orchestrator.answer(session, "我用唯一索引保证幂等，压测 QPS 从 200 提到 900。")
        steps += 1
    return session


def test_golden_interview_produces_stable_report():
    session = run_interview()
    assert session.phase == Phase.DONE, session.error
    markdown = LocalTools().render_report_md(session.report_data)

    if not GOLDEN.exists() or "--update-golden" in _argv():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(markdown, encoding="utf-8")
        pytest.skip("已生成 golden 快照")

    assert markdown == GOLDEN.read_text(encoding="utf-8")


def test_report_covers_every_question():
    session = run_interview()
    markdown = LocalTools().render_report_md(session.report_data)
    for pair in session.qa_pairs:
        assert pair["question"] in markdown
    assert "## 交叉拷问" in markdown


def test_report_score_matches_aggregation():
    session = run_interview()
    expected = LocalTools().aggregate_scores(session.turn_records(), session.weights())
    assert session.report_data["overall_score"] == expected["overall_score"]
    assert session.report_data["dimensions"] == expected["dimensions"]
    assert session.report_data["verdict"] == expected["verdict"]


def _argv() -> list[str]:
    import sys

    return sys.argv
