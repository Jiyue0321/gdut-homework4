"""只读后台页面。

对应设计原型 `prototype/index.html` 的后台四页，Alpha 期只做**能真实读到数据**的部分：

- 数据概览：本次会话的实时指标（跨会话统计需要持久化，见 docs/prototype-api.md）
- 题库管理：98 道题的真实筛选与统计，可导出当前筛选结果
- 系统配置：模型、Endpoint、Key 掩码、生成参数、Prompt 模板、行业关键词，全部只读
- 运行日志：本次会话的模型与工具调用记录

所有页面**不写任何数据**：不改题库、不改配置、不改会话。
"""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from agent import prompts
from agent.config import PROVIDERS, load_config
from agent.llm import (
    DEFAULT_FREQUENCY_PENALTY,
    DEFAULT_MAX_TOKENS,
    DEFAULT_PRESENCE_PENALTY,
    DEFAULT_TEMPERATURE,
)
from agent.state import AGENT_LABELS, Phase
from agent.telemetry import get_recorder
from mcp_server import rubric
from mcp_server.question_bank import (
    GENERAL_INDUSTRY,
    INDUSTRY_KEYWORDS,
    competencies_in_bank,
    industries_in_bank,
    load_bank,
)

st.set_page_config(page_title="后台 · 面面俱到", page_icon="🗂️", layout="wide")

AGENT_SHORT = {"hr": "HR", "tech": "技术", "pressure": "压力"}

# 原型里那份 8 个 Prompt 常量；名字到常量的映射写死，避免反射带来的不确定性。
PROMPT_NAMES = (
    "RESUME_ANALYST",
    "JD_ANALYST",
    "INTERVIEWER_CONTEXT",
    "INTERVIEWER_SCORE_RULES",
    "INTERVIEWER_QUESTION_RULES",
    "CROSS_EXAM",
    "EVALUATOR",
    "REPORT_WRITER",
)


def main() -> None:
    st.title("🗂️ 后台管理 · 只读")
    st.caption(
        "Alpha 期只读版：所有数字都来自当前系统真实数据，"
        "不写题库、不改配置、不落库。跨会话统计与写入能力留给 V2.2。"
    )
    st.info(
        "数据范围说明：概览与日志反映**当前浏览器会话**的真实调用；"
        "题库与配置是**全站静态数据**。系统无持久化，会话关闭后概览与日志会清零。",
        icon="ℹ️",
    )

    overview, bank, config, logs = st.tabs(["数据概览", "题库管理", "系统配置", "运行日志"])
    with overview:
        render_overview()
    with bank:
        render_bank()
    with config:
        render_config()
    with logs:
        render_logs()


# ---------------------------------------------------------------- 概览


def render_overview() -> None:
    session = st.session_state.get("session")
    recorder = get_recorder(st)
    summary = recorder.summary()

    st.subheader("本次会话")
    cols = st.columns(4)
    cols[0].metric("已答轮次", f"{len(session.turns) if session else 0} 题")
    cols[1].metric("当前阶段", _phase_label(session.phase) if session else "未开始")
    cols[2].metric("模型调用", f"{summary['llm_calls']} 次")
    cols[3].metric("工具调用", f"{summary['tool_calls']} 次")

    if not session:
        st.caption("还没有进行中的面试。回到主站开始一次面试，这里的指标会变成真实数据。")
        _render_unavailable_table()
        return

    left, right = st.columns(2)
    with left:
        st.markdown("#### 得分与结论")
        data = session.report_data or {}
        if session.turns:
            partial = partial_score(session)
            st.metric("当前加权总分", f"{partial['overall_score']} / 5")
            st.caption(f"按已答 {len(session.turns)} 题实时聚合，与报告页算法一致。")
        else:
            st.caption("尚无作答记录。")
        if data:
            st.metric("最终总分", f"{data.get('overall_score', '-')} / 5", data.get("verdict", ""))

        st.markdown("#### 会话信息")
        st.table(
            [
                {"项": "会话编号", "值": summary["session_id"]},
                {"项": "目标岗位", "值": session.role_title or "（未填）"},
                {"项": "目标行业", "值": session.industry or "通用"},
                {"项": "计划题数", "值": len(session.plan.slots) if session.plan else 0},
                {"项": "追问已用", "值": "是" if session.followup_used else "否"},
                {"项": "耗时", "值": f"{summary['elapsed_seconds']} 秒"},
            ]
        )

    with right:
        st.markdown("#### 能力维度实测")
        dims = (session.report_data or {}).get("dimensions") or {}
        if dims:
            st.dataframe(
                [{"能力": k, "得分": v, "等级": _level(float(v))} for k, v in dims.items()],
                width="stretch",
                hide_index=True,
            )
        else:
            st.caption("面试结束后这里显示各能力维度的实测得分。")

        st.markdown("#### 逐题得分")
        if session.turns:
            st.dataframe(
                [
                    {
                        "题号": i + 1,
                        "面试官": AGENT_LABELS.get(t.agent, t.agent),
                        "考察能力": session._competency_of(t),
                        "得分": t.score.overall,
                        "追问": "是" if t.is_followup else "",
                    }
                    for i, t in enumerate(session.turns)
                ],
                width="stretch",
                hide_index=True,
            )
        else:
            st.caption("尚无作答记录。")


def partial_score(session) -> dict[str, Any]:
    """复用确定性聚合，算法与报告页完全一致。"""
    return rubric_aggregate(session.turn_records(), session.weights())


def rubric_aggregate(turns: list[dict[str, Any]], weights: dict[str, float]) -> dict[str, Any]:
    averages = rubric.competency_averages(turns)
    total = rubric.weighted_total(averages, weights)
    return {"overall_score": total, "dimensions": averages, "verdict": rubric.overall_verdict(total)}


def _render_unavailable_table() -> None:
    st.markdown("#### 需要持久化才能提供的指标")
    st.table(
        [
            {"指标": "会话总数", "状态": "待 V2.2", "依赖": "interview_sessions 表"},
            {"指标": "完成率", "状态": "待 V2.2", "依赖": "会话表 + phase 字段"},
            {"指标": "平均总分", "状态": "待 V2.2", "依赖": "会话表 + overall_score"},
            {"指标": "近 7 天趋势", "状态": "待 V2.2", "依赖": "会话表 + created_at"},
            {"指标": "近期会话列表", "状态": "待 V2.2", "依赖": "会话表"},
        ]
    )
    st.caption(
        "这些指标不是没做，是系统当前无状态：会话只活在浏览器会话里，"
        "关闭即丢。Beta 的持久化方案见 docs/prototype-api.md。"
    )


# ---------------------------------------------------------------- 题库


def render_bank() -> None:
    bank = list(load_bank())
    st.subheader("题库概览")
    cols = st.columns(4)
    cols[0].metric("题库总量", f"{len(bank)} 题")
    cols[1].metric("覆盖行业", f"{len(industries_in_bank())} 个")
    cols[2].metric("能力标签", f"{len(competencies_in_bank())} 个")
    by_agent = {a: sum(1 for q in bank if q["agent"] == a) for a in AGENT_SHORT}
    cols[3].metric(
        "角色分布",
        " / ".join(str(by_agent[a]) for a in AGENT_SHORT),
        help="HR / 技术 / 压力 各自的题量",
    )

    st.markdown("#### 筛选")
    f1, f2, f3 = st.columns([2, 2, 3])
    industry = f1.selectbox("行业", ["全部", *industries_in_bank()], key="f_industry")
    agent = f2.selectbox(
        "面试官角色", ["全部", *AGENT_SHORT], key="f_agent", format_func=lambda v: AGENT_SHORT.get(v, v)
    )
    keyword = f3.text_input("关键词（题面或能力标签）", key="f_keyword")

    rows = filter_bank(bank, industry, agent, keyword)
    st.caption(f"当前显示 {len(rows)} / {len(bank)} 题")
    st.dataframe(
        [
            {
                "题号": q["id"],
                "行业": q["industry"],
                "角色": AGENT_SHORT.get(q["agent"], q["agent"]),
                "题面": q["text"],
                "能力标签": " / ".join(q["competencies"]),
            }
            for q in rows
        ],
        width="stretch",
        hide_index=True,
    )

    st.download_button(
        "导出当前筛选结果（JSON）",
        data=json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name="题库筛选结果.json",
        mime="application/json",
        disabled=not rows,
    )

    st.markdown("#### 题库暂缺的字段")
    st.table(
        [
            {"字段": "difficulty（难度）", "状态": "需人工标注 98 题", "计划": "Beta 前不排期"},
            {"字段": "usage_count（使用次数）", "状态": "无埋点", "计划": "随 V2.2 持久化"},
            {"字段": "status（启用状态）", "状态": "题库是只读 JSON", "计划": "随 V2.2 持久化"},
        ]
    )
    st.caption("题库当前只有 5 个字段：id / agent / industry / competencies / text。")


def filter_bank(bank: list[dict[str, Any]], industry: str, agent: str, keyword: str) -> list[dict[str, Any]]:
    text = (keyword or "").strip()
    return [
        q
        for q in bank
        if (industry == "全部" or q["industry"] == industry)
        and (agent == "全部" or q["agent"] == agent)
        and (not text or text in q["text"] or any(text in c for c in q["competencies"]))
    ]


# ---------------------------------------------------------------- 配置


def render_config() -> None:
    config = load_config()

    st.subheader("当前生效配置（只读）")
    st.table(
        [
            {"项": "模型", "值": config.model},
            {"项": "Endpoint", "值": config.base_url},
            {"项": "Provider", "值": _provider_of(config.base_url)},
            {"项": "API Key", "值": mask_key(config.api_key) if config.configured else "未配置"},
            {"项": "工具层", "值": "MCP 子进程" if config.use_mcp else "进程内直调"},
        ]
    )
    st.caption(
        "API Key 永不回显，只显示掩码与是否可用。修改配置需改 `.env` / Streamlit Secrets 后重启，"
        "页面不提供写入入口。"
    )
    if not config.configured:
        st.warning("当前 Key 未通过校验（缺失、含占位符或非 ASCII），主站会拒绝启动面试。")

    st.markdown("#### 生成参数")
    st.table(
        [
            {"参数": "temperature", "值": DEFAULT_TEMPERATURE, "说明": "低温度保证评分稳定"},
            {"参数": "max_tokens", "值": DEFAULT_MAX_TOKENS, "说明": "超长时自动补全截断的 JSON"},
            {"参数": "frequency_penalty", "值": DEFAULT_FREQUENCY_PENALTY, "说明": "抑制重复措辞"},
            {"参数": "presence_penalty", "值": DEFAULT_PRESENCE_PENALTY, "说明": "鼓励引入新要点"},
        ]
    )

    st.markdown("#### 面试参数")
    from agent.orchestrator import InterviewConfig

    defaults = InterviewConfig()
    st.table(
        [
            {"参数": "max_questions", "值": str(defaults.max_questions), "说明": "默认题量上限"},
            {"参数": "bank_questions_per_slot", "值": str(defaults.bank_questions_per_slot), "说明": "每轮参考题数"},
            {"参数": "allow_followups", "值": _on_off(defaults.allow_followups), "说明": "是否允许自适应追问"},
            {"参数": "run_cross_exam", "值": _on_off(defaults.run_cross_exam), "说明": "是否开启交叉拷问"},
        ]
    )

    st.markdown("#### Prompt 模板")
    st.caption("8 份中文提示词，集中管理便于调参。此处只读展示，编辑需改代码后发版。")
    choice = st.selectbox("选择模板", PROMPT_NAMES, key="prompt_pick")
    st.code(getattr(prompts, choice, ""), language="text")

    st.markdown("#### 行业关键词")
    st.caption("JD 自动识别行业的依据：命中关键词多者胜出，全不命中则为「通用」。")
    st.dataframe(
        [
            {"行业": name, "关键词数": len(words), "关键词": "、".join(words)}
            for name, words in INDUSTRY_KEYWORDS.items()
        ],
        width="stretch",
        hide_index=True,
    )


def mask_key(key: str) -> str:
    if not key:
        return "未配置"
    if len(key) <= 8:
        return "sk-****"
    return f"{key[:3]}****{key[-4:]}"


def _provider_of(base_url: str) -> str:
    for name, preset in PROVIDERS.items():
        if preset["base_url"] == base_url:
            return name
    return "自定义"


# ---------------------------------------------------------------- 日志


def render_logs() -> None:
    recorder = get_recorder(st)
    summary = recorder.summary()

    st.subheader("本次会话运行日志")
    cols = st.columns(4)
    cols[0].metric("记录条数", len(recorder.events))
    cols[1].metric("模型调用", summary["llm_calls"])
    cols[2].metric("工具调用", summary["tool_calls"])
    cols[3].metric("平均工具耗时", f"{summary['tool_avg_ms']} ms")

    if not recorder.events:
        st.caption("暂无记录。回到主站开始一次面试，模型与工具调用会实时出现在这里。")
    else:
        level = st.selectbox("按级别过滤", ["全部", "INFO", "ERROR"], key="log_level")
        rows = [r for r in recorder.rows() if level == "全部" or r["级别"] == level]
        st.dataframe(rows, width="stretch", hide_index=True)

    st.info(
        "日志只包含工具名、模型结构与耗时，**不含 API Key、简历原文或任何用户身份信息**。"
        "会话关闭即清空，Alpha 期不落盘。",
        icon="🔒",
    )

    st.markdown("#### 落盘计划")
    st.table(
        [
            {"项": "日志持久化", "状态": "待 V2.2", "依赖": "会话表 + 错误表"},
            {"项": "跨会话检索", "状态": "待 V2.2", "依赖": "同上"},
        ]
    )


# ---------------------------------------------------------------- 工具


def _phase_label(phase: Phase | None) -> str:
    if phase is None:
        return "未开始"
    return {
        Phase.IDLE: "待录入",
        Phase.PARSE_RESUME: "解析简历",
        Phase.ANALYZE_JD: "分析岗位",
        Phase.PLAN: "生成计划",
        Phase.INTERVIEW: "面试进行中",
        Phase.CROSS_EXAM: "交叉拷问",
        Phase.EVALUATE: "评分汇总",
        Phase.REPORT: "已出报告",
        Phase.DONE: "已完成",
    }.get(phase, str(phase.value))


def _on_off(flag: bool) -> str:
    return "开启" if flag else "关闭"


def _level(score: float) -> str:
    if score >= 4:
        return "优秀"
    if score >= 3:
        return "达标"
    if score >= 2:
        return "偏弱"
    return "不足"


main()
