"""面试界面：5 步向导中的录入、进行与雷达展示。"""

from __future__ import annotations

from typing import Any

import streamlit as st

from agent.state import AGENT_LABELS, Phase

SAMPLE_RESUME = """\
教育背景：广东工业大学 软件工程 本科 2022-2026，GPA 3.6/4.0
实习经历：某电商公司 后端开发实习 2025.07-2025.09
- 负责订单模块的重构，把下单接口 P99 从 800ms 降到 120ms
- 用 Redis 缓存热点商品，缓存命中率 92%
项目经历：校园二手交易平台（个人项目）
- 技术栈 Python + FastAPI + MySQL + Redis，日活 3000 人
- 自己设计了幂等下单方案，解决重复下单问题
技能：Python、FastAPI、MySQL、Redis、Docker
"""

SAMPLE_JD = """\
后端开发实习生
岗位职责：
1. 参与交易系统后端开发，负责接口设计与性能优化
2. 定位并解决线上问题，编写技术文档
任职要求：
1. 熟悉 Python 及常见 Web 框架
2. 理解关系型数据库与缓存的使用场景
3. 有较强的排查问题能力，能独立推进任务
4. 沟通顺畅，能与产品、前端协作
"""


def hero() -> None:
    st.title("面面俱到 · 模拟面试多智能体")
    st.caption("粘贴简历与岗位 JD，让 HR、技术、压力三位 AI 面试官轮流发难。")


def setup_form() -> tuple[str, str, str] | None:
    """第 1-2 步：录入简历、JD 与岗位名。返回 (简历, JD, 岗位) 或 None。"""
    st.subheader("第一步 · 让面试官认识你")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("填入示例简历", width='stretch'):
            st.session_state.resume_text = SAMPLE_RESUME
        resume_text = st.text_area(
            "简历正文",
            key="resume_text",
            height=260,
            placeholder="把简历复制粘贴到这里，建议保留项目经历里的数字。",
        )
    with col2:
        if st.button("填入示例 JD", width='stretch'):
            st.session_state.jd_text = SAMPLE_JD
        jd_text = st.text_area(
            "岗位 JD",
            key="jd_text",
            height=260,
            placeholder="把目标岗位的 JD 粘贴到这里。",
        )

    role_title = st.text_input(
        "岗位名称", key="role_title", placeholder="例如：后端开发实习生"
    )

    ready = bool(resume_text.strip() and jd_text.strip())
    if not ready:
        st.info("填写简历和 JD 后即可开始面试。")
        return None
    if st.button("开始面试", type="primary", width='stretch'):
        return resume_text, jd_text, role_title.strip() or "目标岗位"
    return None


def radar_chart(radar: list[dict[str, Any]], measured: dict[str, float] | None = None):
    """能力雷达：JD 要求 vs 简历自评 vs 面试实测三条线。"""
    import plotly.graph_objects as go

    if not radar:
        return None
    names = [row["competency"] for row in radar]
    required = [row["required"] for row in radar]
    resume = [row["resume"] for row in radar]

    figure = go.Figure()
    figure.add_trace(
        go.Scatterpolar(r=required, theta=names, fill="toself", name="岗位要求", opacity=0.35)
    )
    figure.add_trace(
        go.Scatterpolar(r=resume, theta=names, fill="toself", name="简历自评", opacity=0.35)
    )
    if measured:
        figure.add_trace(
            go.Scatterpolar(
                r=[measured.get(name, 0) for name in names],
                theta=names,
                fill="toself",
                name="面试实测",
                opacity=0.5,
            )
        )
    figure.update_layout(
        polar={"radialaxis": {"visible": True, "range": [0, 5]}},
        showlegend=True,
        margin={"l": 40, "r": 40, "t": 30, "b": 30},
        height=420,
    )
    return figure


def scorecard(score: dict[str, Any]) -> None:
    """单题评分卡：总分与失分维度。"""
    overall = score.get("overall", 0)
    dims = score.get("dimensions") or {}
    st.markdown(f"**本题得分：{overall} / 5**")
    cols = st.columns(max(1, len(dims)))
    for col, (name, value) in zip(cols, dims.items()):
        col.metric(name, f"{value} / 5")


def agent_badge(agent: str) -> str:
    return AGENT_LABELS.get(agent, agent)


def progress(session) -> None:
    total = len(session.plan.slots) if session.plan else 0
    done = min(session.slot_index, total)
    st.progress(done / total if total else 0.0, text=f"进度 {done}/{total} 题")


def render_transcript(session) -> None:
    """已答题目以对话形式回放，最近一题带评分卡。"""
    for pair in session.qa_pairs:
        label = AGENT_LABELS.get(pair["agent"], pair["agent"])
        suffix = "（追问）" if pair["is_followup"] else ""
        with st.chat_message("assistant"):
            st.markdown(f"**{label}{suffix}**：{pair['question']}")
        with st.chat_message("user"):
            st.write(pair["answer"])
            with st.expander(f"评分：{pair['overall']} / 5 · {pair['competency']}"):
                st.markdown(f"- 依据：{pair['evidence'] or '（未摘录）'}")
                st.markdown(f"- 评语：{pair['comment']}")


def interview_body(session) -> str | None:
    """面试进行中的主体界面。返回本轮提交的回答（若有）。"""
    progress(session)
    render_transcript(session)

    if session.phase in {Phase.REPORT, Phase.DONE}:
        return None

    question = session.current_question
    if question is None:
        st.warning("面试官正在整理问题，请稍候。")
        return None

    label = agent_badge(session.current_agent)
    suffix = "（追问）" if session.followup_used else ""
    with st.chat_message("assistant"):
        st.markdown(f"**{label}{suffix}**：{question.text}")
        with st.expander("本题考察什么"):
            st.markdown(f"- 考察能力：{question.competency}")
            st.markdown("- 评分要点：" + "；".join(question.rubric.criteria))
            st.markdown(f"- 优秀回答：{question.rubric.good_looks_like}")

    if session.error:
        st.error(session.error)

    with st.form(key=f"answer_{len(session.turns)}", clear_on_submit=True):
        answer = st.text_area(
            "你的回答",
            key=f"answer_input_{len(session.turns)}",
            height=140,
            placeholder="建议用 STAR 结构：背景 → 任务 → 行动 → 结果",
        )
        submitted = st.form_submit_button("提交回答", type="primary", width='stretch')
    if submitted:
        if not answer.strip():
            st.warning("回答不能为空。")
            return None
        return answer.strip()
    return None
