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
        st.error(
            "未配置大模型 API Key。请在 `.env` 中把 `OPENAI_API_KEY` 换成真实 Key"
            "（示例文件里的 `sk-你的deepseek密钥` 是占位符），保存后刷新页面。"
        )
        st.stop()
    try:
        client = LLMClient(config)
        tools = open_tools(config)
    except LLMError as exc:
        st.error(str(exc))
        st.stop()
    return client, tools, config


def _new_interview(
    client, tools, resume_text: str, jd_text: str, role_title: str, industry: str
):
    orchestrator = Orchestrator(client, tools, InterviewConfig(industry=industry))
    with st.spinner("面试官正在阅读你的简历与岗位要求…"):
        session = orchestrator.start(resume_text, jd_text, role_title)
    if session.error:
        st.error(session.error)
        return None
    st.session_state.session = session
    st.session_state.orchestrator = orchestrator
    return session


def _industries() -> list[str]:
    """录入页需要行业下拉项；取不到时退化为「自动/通用」，不阻塞填表。"""
    cached = st.session_state.get("industries")
    if cached is not None:
        return cached
    try:
        config = load_config()
        names = open_tools(config).list_industries() if config.configured else []
    except Exception:
        names = []
    st.session_state.industries = names
    return names


def _extractor():
    """上传文件解析器；工具不可用时返回 None，页面不显示上传入口。"""
    try:
        config = load_config()
        if not config.configured:
            return None
        tools = open_tools(config)
        return tools.extract_document
    except Exception:
        return None


def main() -> None:
    interview.hero()

    session = st.session_state.get("session")
    if session is None:
        inputs = interview.setup_form(_industries(), extract=_extractor())
        if inputs:
            client, tools, _ = _get_context()
            _new_interview(client, tools, *inputs)
            st.rerun()
        return

    orchestrator: Orchestrator = st.session_state.orchestrator
    _, tools, _ = _get_context()

    if session.phase in {Phase.REPORT, Phase.DONE}:
        report.render_report(session, tools)
        if not session.narrative and st.button("重新生成复盘结论", width="stretch"):
            with st.spinner("正在重新生成复盘结论…"):
                session = orchestrator.retry(session)
            st.session_state.session = session
            st.rerun()
        if st.button("再面一次", width="stretch"):
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

    if session.current_question is None and session.error:
        if st.button("重试当前步骤", width="stretch"):
            with st.spinner("正在重试…"):
                session = orchestrator.retry(session)
            st.session_state.session = session
            st.rerun()


if __name__ == "__main__":
    main()
