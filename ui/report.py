"""面试报告页：总分、雷达、交叉拷问、改进建议与 Markdown 导出。"""

from __future__ import annotations

from typing import Any

import streamlit as st

from agent.state import AGENT_LABELS
from ui.interview import radar_chart


def render_report(session, tools, *, export_name: str = "面试复盘报告.md") -> None:
    data = session.report_data
    st.subheader("面试复盘报告")

    col1, col2, col3 = st.columns(3)
    col1.metric("加权总分", f"{data.get('overall_score', 0)} / 5")
    col2.metric("面试用时题数", f"{len(session.turns)} 题")
    col3.metric("结论", data.get("verdict", ""))

    measured = {name: float(v) for name, v in (data.get("dimensions") or {}).items()}
    figure = radar_chart(session.radar, measured)
    if figure is not None:
        st.plotly_chart(figure, width='stretch')
        st.caption("三条线分别为岗位要求、简历自评与面试实测；实测线明显低于要求的能力就是下一步要补的。")

    if session.cross_exam:
        render_cross_exam(session.cross_exam)

    left, right = st.columns(2)
    with left:
        st.markdown("### 你的优势")
        for item in session.narrative.get("strengths", []):
            st.markdown(f"- {item}")
        st.markdown("### 待改进")
        for item in session.narrative.get("improvements", []):
            st.markdown(f"- {item}")
    with right:
        st.markdown("### 行动清单")
        for index, item in enumerate(session.narrative.get("action_plan", []), start=1):
            st.markdown(f"{index}. {item}")

    sample = session.narrative.get("sample_answer")
    if sample:
        st.markdown("### 参考答案示范")
        st.info(sample)

    warnings = data.get("warnings") or []
    if warnings:
        st.markdown("### 需要优先补强的能力")
        for warning in warnings:
            st.warning(warning)

    _render_export(session, tools, export_name)


def render_cross_exam(cross_exam) -> None:
    st.markdown("### 交叉拷问")
    st.caption(f"三位面试官针对这道题独立打分："+cross_exam.question)
    cols = st.columns(3)
    for col, (agent, score) in zip(cols, cross_exam.scores.items()):
        col.metric(AGENT_LABELS.get(agent, agent), f"{score.overall} / 5", help=score.comment)
    st.success(f"综合中位数：{cross_exam.merged.overall} / 5 —— {cross_exam.merged.comment}")


def _render_export(session, tools, default_name: str) -> None:
    markdown = tools.render_report_md(session.report_data)
    st.download_button(
        "下载复盘报告（Markdown）",
        data=markdown.encode("utf-8"),
        file_name=default_name,
        mime="text/markdown",
        width='stretch',
    )
    with st.expander("在页面上查看完整报告"):
        st.markdown(markdown)


def render_error(message: str) -> None:
    st.error(message)
    if st.button("返回重新开始", width='stretch'):
        st.session_state.pop("session", None)
        st.rerun()
