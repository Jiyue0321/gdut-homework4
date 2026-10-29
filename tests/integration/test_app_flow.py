"""Streamlit 界面的端到端测试：用假模型跑完整个面试向导。

通过替换 ``load_config`` / ``LLMClient`` / ``open_tools`` 三个入口，
让真实的 app.py 脚本在 AppTest 里完整执行，不触碰真实 API。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from agent.config import LLMConfig
from agent.tools import LocalTools
from tests.conftest import JD_TEXT, RESUME_TEXT, build_fake_llm

TIMEOUT = 90
APP_PATH = Path(__file__).resolve().parents[2] / "app.py"


class FakeClient:
    """冒充 LLMClient：忽略传入的配置，复用脚本化回答。"""

    def __init__(self, _config=None) -> None:
        self._inner = build_fake_llm()

    def chat_json(self, messages, schema, **kwargs):
        return self._inner.chat_json(messages, schema, **kwargs)


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(
        "agent.config.load_config",
        lambda: LLMConfig(base_url="https://example.invalid", api_key="test-key", model="fake"),
    )
    monkeypatch.setattr("agent.llm.LLMClient", FakeClient)
    monkeypatch.setattr("agent.tools.open_tools", lambda _config: LocalTools())
    test_app = AppTest.from_file(str(APP_PATH), default_timeout=TIMEOUT)
    test_app.run()
    return test_app


def _button(at: AppTest, label: str):
    matches = [b for b in at.button if label in b.label]
    assert matches, f"找不到按钮：{label}，现有：{[b.label for b in at.button]}"
    return matches[0]


def test_setup_page_shows_prompt_to_fill_inputs(app: AppTest):
    assert not app.exception
    assert any("填写简历和 JD" in info.value for info in app.info)


def test_empty_resume_keeps_start_button_hidden(app: AppTest):
    app.text_area(key="resume_text").set_value("只有简历")
    app.run()
    assert not [b for b in app.button if "开始面试" in b.label]


def test_fill_sample_buttons_populate_text_areas(app: AppTest):
    _button(app, "填入示例简历").click()
    _button(app, "填入示例 JD").click()
    app.run()
    assert "广东工业大学" in app.text_area(key="resume_text").value
    assert "后端开发实习生" in app.text_area(key="jd_text").value


def test_full_interview_reaches_report(app: AppTest):
    app.text_area(key="resume_text").set_value(RESUME_TEXT)
    app.text_area(key="jd_text").set_value(JD_TEXT)
    app.text_input(key="role_title").set_value("后端开发实习生")
    app.run()
    _button(app, "开始面试").click()
    app.run()
    assert not app.exception, [e.value for e in app.exception]
    assert app.session_state["session"].phase.value == "interview"

    for step in range(12):
        session = app.session_state["session"]
        if session.phase.value in {"done", "report"}:
            break
        # 表单内外控件要在同一次 run 中一并生效：设值 → 点提交 → run
        app.text_area(key=f"answer_input_{len(session.turns)}").set_value(
            "我用唯一索引保证幂等，压测 QPS 从 200 提到 900。"
        )
        _button(app, "提交回答").click()
        app.run()
        assert not app.exception, [e.value for e in app.exception]

    session = app.session_state["session"]
    assert session.phase.value == "done", session.error
    assert len(session.turns) >= 3
    assert session.report_data["overall_score"] >= 0
    assert session.narrative["action_plan"]


def test_report_page_renders_scores_and_export(app: AppTest):
    app.text_area(key="resume_text").set_value(RESUME_TEXT)
    app.text_area(key="jd_text").set_value(JD_TEXT)
    app.run()
    _button(app, "开始面试").click()
    app.run()

    for _ in range(12):
        session = app.session_state["session"]
        if session.phase.value in {"done", "report"}:
            break
        app.text_area(key=f"answer_input_{len(session.turns)}").set_value("回答")
        _button(app, "提交回答").click()
        app.run()

    labels = [m.label for m in app.metric]
    assert "加权总分" in labels
    assert any("下载复盘报告" in b.label for b in app.download_button)
    assert any("复盘报告" in h.value for h in app.subheader)


def test_report_page_shows_cross_exam_and_improvements(app: AppTest):
    app.text_area(key="resume_text").set_value(RESUME_TEXT)
    app.text_area(key="jd_text").set_value(JD_TEXT)
    app.run()
    _button(app, "开始面试").click()
    app.run()

    for _ in range(12):
        session = app.session_state["session"]
        if session.phase.value in {"done", "report"}:
            break
        app.text_area(key=f"answer_input_{len(session.turns)}").set_value("回答")
        _button(app, "提交回答").click()
        app.run()

    session = app.session_state["session"]
    assert session.cross_exam is not None
    marks = [m.value for m in app.markdown]
    headings = " ".join(marks)
    assert "交叉拷问" in headings
    assert "你的优势" in headings
    assert "待改进" in headings
    assert "行动清单" in headings

    # 报告导出内容要覆盖交叉拷问与行动清单
    markdown = LocalTools().render_report_md(session.report_data)
    assert "## 交叉拷问" in markdown
    assert "## 行动清单" in markdown


def test_restart_button_returns_to_setup(app: AppTest):
    app.text_area(key="resume_text").set_value(RESUME_TEXT)
    app.text_area(key="jd_text").set_value(JD_TEXT)
    app.run()
    _button(app, "开始面试").click()
    app.run()

    for _ in range(12):
        session = app.session_state["session"]
        if session.phase.value in {"done", "report"}:
            break
        app.text_area(key=f"answer_input_{len(session.turns)}").set_value("回答")
        _button(app, "提交回答").click()
        app.run()

    _button(app, "再面一次").click()
    app.run()
    assert "session" not in app.session_state
    assert any("填写简历和 JD" in info.value for info in app.info)
