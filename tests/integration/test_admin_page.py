"""只读后台页与运行观测的测试。

后台页是独立脚本，用 AppTest 直接跑；观测层是纯 Python，单独测。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from agent.telemetry import CountingChat, InstrumentedTools, Recorder

ADMIN_PATH = Path(__file__).resolve().parents[2] / "pages" / "1_后台管理.py"
TIMEOUT = 60


# ---------------------------------------------------------------- 观测层


class _FakeLLM:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def chat_json(self, messages, schema, **kwargs):
        if self.fail:
            raise RuntimeError("模型挂了")
        return {"ok": True}


class _FakeTools:
    def pick_questions(self, *args, **kwargs):
        return [{"id": "hr-01"}, {"id": "hr-02"}]

    def export_report(self, filename: str, content: str):
        return {"path": filename, "bytes": len(content.encode())}

    def boom(self):
        raise ValueError("工具出错")


def test_recorder_counts_llm_and_tool_calls():
    recorder = Recorder()
    chat = CountingChat(_FakeLLM(), recorder)
    tools = InstrumentedTools(_FakeTools(), recorder)

    chat.chat_json([], type("ResumeProfile", (), {}))
    tools.pick_questions()
    tools.export_report("a.md", "内容")

    summary = recorder.summary()
    assert summary["llm_calls"] == 1
    assert summary["tool_calls"] == 2
    assert summary["llm_errors"] == 0
    assert summary["unique_tools"] == 2


def test_recorder_marks_failures_without_changing_behaviour():
    recorder = Recorder()
    chat = CountingChat(_FakeLLM(fail=True), recorder)
    tools = InstrumentedTools(_FakeTools(), recorder)

    with pytest.raises(RuntimeError):
        chat.chat_json([], type("X", (), {}))
    with pytest.raises(ValueError):
        tools.boom()

    assert recorder.summary()["llm_errors"] == 1
    assert any(row["级别"] == "ERROR" for row in recorder.rows())
    # 失败的工具调用同样计数
    assert recorder.summary()["tool_calls"] == 1


def test_instrumented_tools_pass_through_non_callables():
    recorder = Recorder()
    inner = _FakeTools()
    inner.threshold = 3  # 普通属性
    assert InstrumentedTools(inner, recorder).threshold == 3


def test_recorder_event_limit_keeps_latest():
    from agent.telemetry import MAX_EVENTS

    recorder = Recorder()
    for i in range(MAX_EVENTS + 20):
        recorder.note(f"事件 {i}")
    assert len(recorder.events) == MAX_EVENTS
    assert recorder.events[-1]["message"] == f"事件 {MAX_EVENTS + 19}"


def test_rows_are_localized_for_display():
    recorder = Recorder()
    recorder.note_tool("pick_questions", 0.012, detail="count=2")
    row = recorder.rows()[0]
    assert row["类型"] == "工具"
    assert row["耗时(ms)"] == 12
    assert "count=2" in row["内容"]


# ---------------------------------------------------------------- 后台页


@pytest.fixture
def admin():
    page = AppTest.from_file(str(ADMIN_PATH), default_timeout=TIMEOUT)
    page.run()
    return page


def test_admin_page_runs_without_session(admin: AppTest):
    assert not admin.exception, [e.value for e in admin.exception]
    assert len(admin.tabs) == 4
    labels = [m.label for m in admin.metric]
    assert "题库总量" in labels
    assert "覆盖行业" in labels


def test_bank_stats_match_real_data(admin: AppTest):
    metrics = {m.label: m.value for m in admin.metric}
    assert metrics["题库总量"] == "98 题"
    assert metrics["覆盖行业"] == "9 个"
    assert metrics["能力标签"] == "10 个"
    assert metrics["角色分布"] == "27 / 45 / 26"


def test_bank_filter_narrows_rows():
    page = AppTest.from_file(str(ADMIN_PATH), default_timeout=TIMEOUT)
    page.run()
    page.selectbox(key="f_industry").select("互联网后端")
    page.selectbox(key="f_agent").select("tech")
    page.run()
    assert not page.exception
    frame = page.dataframe[0].value
    assert len(frame) > 0
    assert set(frame["行业"]) == {"互联网后端"}
    assert set(frame["角色"]) == {"技术"}


def test_bank_keyword_filter_matches_competency():
    page = AppTest.from_file(str(ADMIN_PATH), default_timeout=TIMEOUT)
    page.run()
    page.text_input(key="f_keyword").set_value("岗位动机")
    page.run()
    frame = page.dataframe[0].value
    assert len(frame) > 0
    assert all("岗位动机" in row for row in frame["能力标签"])


def test_config_page_masks_api_key(admin: AppTest):
    tables = " ".join(str(t.value) for t in admin.table)
    assert "未配置" in tables or "****" in tables
    # 真实 Key 的任何长片段都不应出现在页面上
    from agent.config import load_config

    key = load_config().api_key
    if key and key.isascii() and len(key) > 8:
        assert key not in tables


def test_logs_tab_starts_empty(admin: AppTest):
    assert any("暂无记录" in c.value for c in admin.caption)


def test_overview_reports_missing_persistence_honestly(admin: AppTest):
    text = " ".join(str(t.value) for t in admin.table)
    assert "待 V2.2" in text
