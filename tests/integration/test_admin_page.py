"""只读后台页与运行观测的测试。

后台页是独立脚本，用 AppTest 直接跑；观测层是纯 Python，单独测。
页面用 HTML 渲染表格与统计卡，断言直接对渲染出的 HTML 文本做匹配。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from agent.telemetry import CountingChat, InstrumentedTools, Recorder

ADMIN_PATH = Path(__file__).resolve().parents[2] / "pages" / "1_后台管理.py"
TIMEOUT = 90


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
    assert recorder.summary()["tool_calls"] == 1


def test_instrumented_tools_pass_through_non_callables():
    recorder = Recorder()
    inner = _FakeTools()
    inner.threshold = 3
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


def _page_html(page: AppTest) -> str:
    return " ".join(str(m.value) for m in page.markdown)


def _open(page: AppTest, tab: str) -> AppTest:
    page.button(key=f"nav_{tab}").click()
    page.run()
    return page


@pytest.fixture
def admin() -> AppTest:
    page = AppTest.from_file(str(ADMIN_PATH), default_timeout=TIMEOUT)
    page.run()
    return page


def test_admin_page_runs_without_session(admin: AppTest):
    assert not admin.exception, [e.value for e in admin.exception]
    labels = [b.label for b in admin.button]
    assert labels[:4] == ["数据概览", "题库管理", "系统配置", "运行日志"]


def test_overview_shows_real_bank_stats(admin: AppTest):
    html = _page_html(admin)
    assert ">98<" in html
    assert "题库参考题" in html
    assert ">9<" in html
    assert ">14<" in html  # MCP 工具数由源码实时统计


def test_overview_marks_persistence_as_placeholder(admin: AppTest):
    html = _page_html(admin)
    assert "占位 · 待 V2.2" in html
    assert "数据占位版" in html
    # 占位数字必须被明确标注，不能伪装成真实数据
    assert "不是系统产出" in html


def test_bank_tab_lists_real_questions(admin: AppTest):
    page = _open(admin, "bank")
    assert not page.exception
    html = _page_html(page)
    assert "hr-01" in html
    assert "当前显示" in html


def test_bank_filter_narrows_rows(admin: AppTest):
    page = _open(admin, "bank")
    page.selectbox(key="f_industry").select("互联网后端")
    page.selectbox(key="f_agent").select("tech")
    page.run()
    assert not page.exception
    html = _page_html(page)
    match = re.search(r"当前显示 <b>(\d+)</b> / 98 题", html)
    assert match, "找不到计数"
    shown = int(match.group(1))
    assert 0 < shown < 98
    # 过滤后不应再出现其它行业的题号行
    assert "tech-08" not in html  # 前端题，被行业过滤排除


def test_bank_keyword_filter_matches_competency(admin: AppTest):
    page = _open(admin, "bank")
    page.text_input(key="f_keyword").set_value("岗位动机")
    page.run()
    html = _page_html(page)
    match = re.search(r"当前显示 <b>(\d+)</b> / 98 题", html)
    assert match and int(match.group(1)) > 0


def test_bank_export_button_enabled_only_with_rows(admin: AppTest):
    page = _open(admin, "bank")
    page.text_input(key="f_keyword").set_value("绝对不存在的关键词xyz")
    page.run()
    assert page.download_button[0].disabled


def test_config_tab_masks_api_key(admin: AppTest):
    page = _open(admin, "config")
    assert not page.exception
    key_input = page.text_input(key="cfg_key")
    assert key_input.disabled
    assert "****" in key_input.value or key_input.value == "未配置"

    from agent.config import load_config

    key = load_config().api_key
    if key and key.isascii() and len(key) > 8:
        assert key not in _page_html(page)


def test_config_toggles_are_readonly(admin: AppTest):
    page = _open(admin, "config")
    assert page.toggle, "配置页应展示只读开关"
    assert all(t.disabled for t in page.toggle)


def test_logs_tab_starts_empty(admin: AppTest):
    page = _open(admin, "logs")
    html = _page_html(page)
    assert "暂无记录" in html
    assert "ms-log" in html


def test_logs_tab_renders_recorded_events(admin: AppTest):
    page = _open(admin, "logs")
    recorder = page.session_state["telemetry"]
    recorder.note_llm("ResumeProfile", 1.7)
    recorder.note_tool("pick_questions", 0.02, detail="count=2")
    page.run()
    html = _page_html(page)
    assert "llm chat_json schema=ResumeProfile ok" in html
    assert "tool pick_questions" in html


def test_nav_uses_session_state(admin: AppTest):
    page = _open(admin, "logs")
    assert page.session_state["admin_tab"] == "logs"
    page = _open(page, "overview")
    assert page.session_state["admin_tab"] == "overview"
