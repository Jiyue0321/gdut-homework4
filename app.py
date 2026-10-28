"""面面俱到 · 模拟面试多智能体 —— Streamlit 入口。

流程：录入简历与 JD → 三位面试官轮流提问 → 自适应追问 → 交叉拷问 → 复盘报告。
"""

from __future__ import annotations

import streamlit as st

from agent.config import load_config
from agent.llm import LLMClient, LLMError
from agent.orchestrator import InterviewConfig, Orchestrator
from agent.state import Phase
from agent.tools import open_tools
from ui import interview, report

st.set_page_config(page_title="面面俱到 · 模拟面试", page_icon="🎤", layout="wide")


def _get_context():
    """配置与依赖只在需要时构造，避免首屏就因缺 Key 报错。"""
    config = load_config()
    if not config.configured:
        st.error("未配置大模型 API Key。请在 `.env` 或 Streamlit Secrets 中设置 `OPENAI_API_KEY`。")
        st.stop()
    try:
        client = LLMClient(config)
        tools = open_tools(config)
    except LLMError as exc:
        st.error(str(exc))
        st.stop()
    return client, tools, config


def _new_interview(client, tools, resume_text: str, jd_text: str, role_title: str):
    orchestrator = Orchestrator(client, tools, InterviewConfig())
    with st.spinner("面试官正在阅读你的简历与岗位要求…"):
        session = orchestrator.start(resume_text, jd_text, role_title)
    if session.error:
        st.error(session.error)
        return None
    st.session_state.session = session
    st.session_state.orchestrator = orchestrator
    return session


def main() -> None:
    interview.hero()

    session = st.session_state.get("session")
    if session is None:
        inputs = interview.setup_form()
        if inputs:
            client, tools, _ = _get_context()
            _new_interview(client, tools, *inputs)
            st.rerun()
        return

    orchestrator: Orchestrator = st.session_state.orchestrator
    _, tools, _ = _get_context()

    if session.phase in {Phase.REPORT, Phase.DONE}:
        report.render_report(session, tools)
        if st.button("再面一次", use_container_width=True):
            st.session_state.pop("session", None)
            st.session_state.pop("orchestrator", None)
            st.rerun()
        return

    answer = interview.interview_body(session)
    if answer:
        with st.spinner("面试官正在看你的回答…"):
            session = orchestrator.answer(session, answer)
        st.session_state.session = session
        if session.error:
            st.error(session.error)
        st.rerun()


if __name__ == "__main__":
    main()
