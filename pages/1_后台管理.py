"""只读后台页面，按设计原型 `prototype/index.html` 的视觉重做。

- 左侧导航 + 右侧内容，统计卡、表格、开关、深色日志控制台都用原型配色
- **真实数据优先**：题库、配置、本次会话的调用记录全部来自系统
- **持久化相关一律占位**：会话数、趋势、使用次数等标「占位 · 待 V2.2」，
  不编造接口，也不假装能写
"""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
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
from agent.orchestrator import InterviewConfig
from agent.state import AGENT_LABELS, Phase
from agent.telemetry import get_recorder
from mcp_server import rubric
from mcp_server.question_bank import (
    INDUSTRY_KEYWORDS,
    competencies_in_bank,
    industries_in_bank,
    load_bank,
)

st.set_page_config(page_title="后台 · 面面俱到", page_icon="🗂️", layout="wide")

AGENT_SHORT = {"hr": "HR", "tech": "技术", "pressure": "压力"}

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

TABS = (
    ("overview", "数据概览"),
    ("bank", "题库管理"),
    ("config", "系统配置"),
    ("logs", "运行日志"),
)

CSS = """
<style>
/* 与原型 prototype/index.html 同一套色板 */
.block-container { padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1180px; }
.ms-topbar {
  background: linear-gradient(100deg,#22467F,#2E5EAA 55%,#4A7BC8);
  color:#fff; border-radius:12px; padding:14px 22px; display:flex;
  align-items:center; gap:14px; box-shadow:0 6px 20px rgba(31,59,110,.18);
}
.ms-topbar .mark {
  width:34px;height:34px;border-radius:9px;background:#fff;color:#2E5EAA;
  display:grid;place-items:center;font-weight:800;font-size:15px;
}
.ms-topbar .t { font-weight:700; font-size:17px; letter-spacing:.4px; }
.ms-topbar .s { font-size:11px; opacity:.85; letter-spacing:1px; }
.ms-topbar .sp { flex:1; }
.ms-pill {
  display:inline-block;border-radius:20px;padding:2px 10px;font-size:11px;font-weight:700;
}
.ms-pill.warn { background:#FFF4E5;color:#96641A;border:1px solid #D9A441; }
.ms-pill.ok { background:#EAF5EF;color:#2B7A5C; }
.ms-pill.info { background:#E8F0FF;color:#2E5EAA; }
.ms-pill.gray { background:#EEF1F5;color:#5A6472; }
.ms-banner {
  background:linear-gradient(90deg,#FFF9EC,#FFFDF7); border:1px solid #F0D9A6;
  border-left:4px solid #D9A441; border-radius:10px; padding:10px 16px;
  font-size:13px; color:#7A5514; margin:14px 0 18px;
}
.ms-h1 { margin:6px 0 2px; font-size:22px; color:#22467F; font-weight:700; }
.ms-sub { margin:0 0 4px; color:#5A6472; font-size:13px; }
.ms-section {
  font-size:15px; color:#22467F; font-weight:700; border-left:4px solid #2E5EAA;
  padding-left:10px; margin:20px 0 10px;
}
.ms-grid4 { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; }
@media (max-width:900px){ .ms-grid4{grid-template-columns:repeat(2,1fr);} }
.ms-stat {
  background:#fff;border:1px solid #D5DDE8;border-radius:12px;padding:16px;text-align:center;
  box-shadow:0 6px 20px rgba(31,59,110,.08);
}
.ms-stat .v { font-size:26px;font-weight:800;color:#2E5EAA;line-height:1.2; }
.ms-stat .v.sm { font-size:19px; }
.ms-stat .k { font-size:12px;color:#5A6472;margin-top:4px; }
.ms-stat .d { font-size:11px;color:#3B8C6E;margin-top:4px; }
.ms-stat .d.warn { color:#96641A; }
.ms-card {
  background:#fff;border:1px solid #D5DDE8;border-radius:14px;padding:18px 20px;
  box-shadow:0 6px 20px rgba(31,59,110,.08); margin:14px 0;
}
.ms-table-wrap { overflow-x:auto; border-radius:10px; border:1px solid #D5DDE8; background:#fff; }
.ms-table { width:100%; border-collapse:collapse; font-size:13px; }
.ms-table th {
  background:#E8EEF7;color:#22467F;text-align:left;padding:9px 10px;
  border-bottom:1px solid #CBD9EE;font-size:12px;white-space:nowrap;
}
.ms-table td { padding:8px 10px;border-bottom:1px solid #EDF1F6;vertical-align:top; }
.ms-table tbody tr:nth-child(even){ background:#FAFCFF; }
.ms-table tbody tr:last-child td { border-bottom:none; }
.ms-log {
  font-family:Consolas,"Courier New",monospace; font-size:12px; background:#0F2038;
  color:#B9D4F5; border-radius:10px; padding:14px 16px; line-height:1.9;
  overflow-x:auto; white-space:pre-wrap;
}
.ms-log .t { color:#7FB3F0; }
.ms-log .ok { color:#7BD3A6; }
.ms-log .wn { color:#F2C879; }
.ms-log .er { color:#F08B87; }
.ms-note {
  background:#EAF5EF;border-left:4px solid #3B8C6E;padding:10px 14px;border-radius:8px;
  font-size:12.5px;color:#2B6B53;margin:12px 0;
}
.ms-side-note { font-size:12px;color:#5A6472;line-height:1.7; }
/* 左侧导航按钮：仿原型的 .side button */
div[class*="st-key-admin_nav"] { display:flex; flex-direction:column; gap:8px; }
div[class*="st-key-admin_nav"] button {
  width:100%; border-radius:9px; border:1px solid #D5DDE8; background:#fff;
  color:#22467F; font-weight:600; justify-content:center;
}
div[class*="st-key-admin_nav"] button[kind="primary"] {
  background:#2E5EAA; color:#fff; border-color:#2E5EAA;
}
</style>
"""


def main() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(
        '<div class="ms-topbar">'
        '<span class="mark">面</span>'
        '<span><span class="t">面面俱到 · 后台管理</span><br>'
        '<span class="s">MOCKSTAR · ADMIN CONSOLE</span></span>'
        '<span class="sp"></span>'
        '<span class="ms-pill warn">数据占位版</span>'
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="ms-banner">'
        "<b>真实数据与占位数据的边界</b>：题库统计、系统配置、本次会话的调用记录均来自系统真实数据，"
        "只读不可改；<b>跨会话统计</b>（会话数、趋势、使用次数）需要持久化，本页以占位形式展示并标注"
        "「占位 · 待 V2.2」，不编造接口。"
        "</div>",
        unsafe_allow_html=True,
    )

    left, right = st.columns([1, 3.6], gap="large")
    with left:
        tab = _nav()
        st.markdown(
            '<div class="ms-side-note">只读后台：不写题库、不改配置、不落库。'
            "运行日志仅记录当前浏览器会话。</div>",
            unsafe_allow_html=True,
        )
    with right:
        {
            "overview": render_overview,
            "bank": render_bank,
            "config": render_config,
            "logs": render_logs,
        }[tab]()


def _nav() -> str:
    if "admin_tab" not in st.session_state:
        st.session_state.admin_tab = "overview"
    with st.container(key="admin_nav"):
        for key, label in TABS:
            active = st.session_state.admin_tab == key
            if st.button(
                label,
                key=f"nav_{key}",
                type="primary" if active else "secondary",
                width="stretch",
            ):
                st.session_state.admin_tab = key
                st.rerun()
    return st.session_state.admin_tab


# ---------------------------------------------------------------- 数据概览


def render_overview() -> None:
    bank = list(load_bank())
    session = st.session_state.get("session")
    recorder = get_recorder(st)
    summary = recorder.summary()

    st.markdown('<div class="ms-h1">数据概览</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="ms-sub">上方为全站静态数据的真实统计；跨会话指标为占位，'
        "本次会话指标实时计算。</p>",
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="ms-grid4">'
        + _stat(str(len(bank)), "题库参考题", f"覆盖 {len(industries_in_bank())} 个行业")
        + _stat(str(len(industries_in_bank())), "行业标签", "通用 + 8 个行业")
        + _stat(str(InterviewConfig().max_questions), "默认题量", "可配置 3–N")
        + _stat(str(_tool_count()), "确定性工具", "MCP 服务注册")
        + "</div>",
        unsafe_allow_html=True,
    )

    st.markdown('<div class="ms-section">本次会话（真实数据）</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="ms-grid4">'
        + _stat(str(len(session.turns)) if session else "0", "已答轮次", "来自当前面试")
        + _stat(_phase_label(session.phase) if session else "未开始", "当前阶段", _kind="sm")
        + _stat(str(summary["llm_calls"]), "模型调用", "当前浏览器会话")
        + _stat(str(summary["tool_calls"]), "工具调用", f"平均 {summary['tool_avg_ms']} ms")
        + "</div>",
        unsafe_allow_html=True,
    )

    if session:
        data = session.report_data or {}
        left, right = st.columns(2)
        with left:
            st.markdown('<div class="ms-section">得分</div>', unsafe_allow_html=True)
            rows = []
            if session.turns:
                partial = _aggregate(session.turn_records(), session.weights())
                rows.append(("当前加权总分（按已答题实时聚合）", f"{partial['overall_score']} / 5"))
            if data:
                rows.append(("最终总分", f"{data.get('overall_score', '-')} / 5"))
                rows.append(("结论", str(data.get("verdict", "-"))))
            rows += [
                ("目标岗位", session.role_title or "（未填）"),
                ("目标行业", session.industry or "通用"),
                ("计划题数", str(len(session.plan.slots) if session.plan else 0)),
                ("追问已用", "是" if session.followup_used else "否"),
            ]
            st.markdown(_table(["项", "值"], rows), unsafe_allow_html=True)
        with right:
            st.markdown('<div class="ms-section">能力维度实测</div>', unsafe_allow_html=True)
            dims = data.get("dimensions") or {}
            if dims:
                st.markdown(
                    _table(
                        ["能力", "得分", "等级"],
                        [(k, str(v), _level(float(v))) for k, v in dims.items()],
                    ),
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div class="ms-note">面试结束后这里显示各能力维度的实测得分。</div>',
                    unsafe_allow_html=True,
                )
            st.markdown('<div class="ms-section">逐题得分</div>', unsafe_allow_html=True)
            if session.turns:
                st.markdown(
                    _table(
                        ["题号", "面试官", "考察能力", "得分", "追问"],
                        [
                            (
                                str(i + 1),
                                AGENT_LABELS.get(t.agent, t.agent),
                                session._competency_of(t),
                                str(t.score.overall),
                                "是" if t.is_followup else "",
                            )
                            for i, t in enumerate(session.turns)
                        ],
                    ),
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div class="ms-note">尚无作答记录。</div>', unsafe_allow_html=True
                )
    else:
        st.markdown(
            '<div class="ms-note">还没有进行中的面试。回到主站开始一次面试，'
            "「本次会话」的指标就会变成真实数据。</div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div class="ms-section">最近面试记录 <span class="ms-pill warn">占位</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        _table(
            ["会话", "岗位", "行业", "总分", "结论", "导出"],
            [
                ("S-20261111-01", "后端开发实习生", "互联网后端", "3.6", "基本达标", "MD / PDF"),
                ("S-20261111-02", "算法工程师", "人工智能", "4.2", "表现出色", "MD"),
                ("S-20261110-07", "数据分析师", "数据分析", "2.8", "存在明显缺口", "PDF"),
                ("S-20261110-06", "前端开发", "互联网前端", "3.1", "基本达标", "MD / PDF"),
            ],
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="ms-banner">上表为设计原型中的<b>占位数据</b>，不是系统产出。'
        "系统当前无持久化：会话只活在浏览器会话里，关闭即丢，因此「最近面试记录」要等 V2.2 的"
        "会话表才能真实呈现。</div>",
        unsafe_allow_html=True,
    )
    _render_pending_table()


def _render_pending_table() -> None:
    st.markdown(
        '<div class="ms-section">需要持久化才能提供的指标 <span class="ms-pill warn">占位</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        _table(
            ["指标", "状态", "依赖"],
            [
                ("会话总数", "占位 · 待 V2.2", "interview_sessions 表"),
                ("完成率", "占位 · 待 V2.2", "会话表 + phase 字段"),
                ("平均总分", "占位 · 待 V2.2", "会话表 + overall_score"),
                ("近 7 天趋势", "占位 · 待 V2.2", "会话表 + created_at"),
                ("AI 调用次数（跨会话）", "占位 · 待 V2.2", "会话表 + 调用计数落库"),
            ],
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="ms-note">这些指标不是没做，是数据根本没留下。Beta 方案：留在 Streamlit Cloud，'
        "接外部托管数据库，见 <code>docs/prototype-api.md</code> §5.2。</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------- 题库管理


def render_bank() -> None:
    bank = list(load_bank())
    by_agent = {a: sum(1 for q in bank if q["agent"] == a) for a in AGENT_SHORT}

    st.markdown('<div class="ms-h1">题库管理</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="ms-sub">全部为真实题库数据；筛选与导出可用，写入不开放。</p>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="ms-grid4">'
        + _stat(str(len(bank)), "题库参考题", f"覆盖 {len(industries_in_bank())} 个行业")
        + _stat(str(len(industries_in_bank())), "行业标签", "通用 + 8 个行业")
        + _stat(str(len(competencies_in_bank())), "能力标签", "competencies 字段")
        + _stat(
            " / ".join(str(by_agent[a]) for a in AGENT_SHORT), "角色分布", "HR / 技术 / 压力", _kind="sm"
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    f1, f2, f3, f4 = st.columns([1.3, 1.1, 2, 1])
    industry = f1.selectbox("行业", ["全部", *industries_in_bank()], key="f_industry")
    agent = f2.selectbox(
        "角色", ["全部", *AGENT_SHORT], key="f_agent", format_func=lambda v: AGENT_SHORT.get(v, v)
    )
    keyword = f3.text_input("搜索题目关键词 / 能力标签", key="f_keyword")
    with f4:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        st.button("新增题目", disabled=True, help="只读版不开放写入，改题库需提交仓库", width="stretch")

    rows = filter_bank(bank, industry, agent, keyword)
    st.markdown(
        f'<p class="ms-sub">当前显示 <b>{len(rows)}</b> / {len(bank)} 题'
        f'　<span class="ms-pill gray">只读</span></p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        _table(
            ["题号", "行业", "角色", "题面", "能力标签"],
            [
                (
                    escape(q["id"]),
                    escape(q["industry"]),
                    escape(AGENT_SHORT.get(q["agent"], q["agent"])),
                    escape(q["text"]),
                    escape(" / ".join(q["competencies"])),
                )
                for q in rows
            ],
        )
        if rows
        else '<div class="ms-note">没有匹配的题目，请调整筛选条件。</div>',
        unsafe_allow_html=True,
    )

    st.download_button(
        "导出当前筛选结果（JSON）",
        data=json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name="题库筛选结果.json",
        mime="application/json",
        disabled=not rows,
    )

    st.markdown('<div class="ms-section">题库暂缺的字段</div>', unsafe_allow_html=True)
    st.markdown(
        _table(
            ["字段", "状态", "计划"],
            [
                ("difficulty（难度）", "占位 · 需人工标注 98 题", "Beta 前不排期"),
                ("usage_count（使用次数）", "占位 · 待 V2.2", "需出题埋点 + 持久化"),
                ("status（启用 / 停用）", "占位 · 待 V2.2", "需落库后才能改"),
            ],
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="ms-note">题库当前只有 5 个字段：id / agent / industry / competencies / text。'
        "上表三项在三份原型截图里都有，但现有 JSON 里并不存在——这是设计与实现的已知差距。</div>",
        unsafe_allow_html=True,
    )


def filter_bank(
    bank: list[dict[str, Any]], industry: str, agent: str, keyword: str
) -> list[dict[str, Any]]:
    text = (keyword or "").strip()
    return [
        q
        for q in bank
        if (industry == "全部" or q["industry"] == industry)
        and (agent == "全部" or q["agent"] == agent)
        and (not text or text in q["text"] or any(text in c for c in q["competencies"]))
    ]


# ---------------------------------------------------------------- 系统配置


def render_config() -> None:
    config = load_config()
    defaults = InterviewConfig()

    st.markdown('<div class="ms-h1">系统配置</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="ms-sub">全部为只读：显示当前生效值，不提供写入入口。'
        "改配置需修改 <code>.env</code> / Streamlit Secrets 后重启。</p>",
        unsafe_allow_html=True,
    )

    left, right = st.columns(2)
    with left:
        st.markdown('<div class="ms-section">大模型设置</div>', unsafe_allow_html=True)
        provider = _provider_of(config.base_url)
        st.selectbox(
            "大模型供应商",
            [*PROVIDERS, "自定义"],
            index=[*PROVIDERS, "自定义"].index(provider),
            disabled=True,
            key="cfg_provider",
        )
        st.text_input("模型", value=config.model, disabled=True, key="cfg_model")
        st.text_input("Endpoint", value=config.base_url, disabled=True, key="cfg_base")
        st.text_input(
            "API Key",
            value=mask_key(config.api_key) if config.configured else "未配置",
            disabled=True,
            key="cfg_key",
            help="永不回显真实 Key，只显示掩码与是否可用",
        )
        st.text_input("温度 temperature", value=str(DEFAULT_TEMPERATURE), disabled=True, key="cfg_temp")
        st.text_input("最大 Token", value=str(DEFAULT_MAX_TOKENS), disabled=True, key="cfg_tokens")

        st.markdown('<div class="ms-section">面试参数</div>', unsafe_allow_html=True)
        st.text_input("默认题量上限", value=str(defaults.max_questions), disabled=True, key="cfg_maxq")
        st.text_input(
            "每轮参考题数", value=str(defaults.bank_questions_per_slot), disabled=True, key="cfg_bankq"
        )
        st.selectbox("行业选择默认值", ["自动", "通用"], disabled=True, key="cfg_ind")

    with right:
        st.markdown('<div class="ms-section">功能开关（当前生效值）</div>', unsafe_allow_html=True)
        st.toggle(
            "允许自适应追问", value=defaults.allow_followups, disabled=True, key="tg_follow",
            help="每个考察点最多 1 次",
        )
        st.toggle(
            "开启交叉拷问", value=defaults.run_cross_exam, disabled=True, key="tg_cross",
            help="最弱一题三视角评分",
        )
        st.toggle(
            "使用 MCP 子进程", value=config.use_mcp, disabled=True, key="tg_mcp",
            help="关闭则进程内直调，等价实现",
        )
        st.toggle(
            "作答意图过滤", value=True, disabled=True, key="tg_intent",
            help="纯规则判定，零大模型调用",
        )

        st.markdown('<div class="ms-section">其他生成参数</div>', unsafe_allow_html=True)
        st.markdown(
            _table(
                ["参数", "值", "说明"],
                [
                    ("frequency_penalty", str(DEFAULT_FREQUENCY_PENALTY), "抑制重复措辞"),
                    ("presence_penalty", str(DEFAULT_PRESENCE_PENALTY), "鼓励引入新要点"),
                ],
            ),
            unsafe_allow_html=True,
        )

        st.markdown('<div class="ms-section">Prompt 模板</div>', unsafe_allow_html=True)
        choice = st.selectbox("选择模板", PROMPT_NAMES, key="prompt_pick")
        st.code(getattr(prompts, choice, ""), language="text")

    st.button("保存配置", disabled=True, width="stretch", help="只读版不提供写入")
    st.markdown(
        '<div class="ms-note">API Key 不入库、不写日志、不回显。'
        "原型的「修改密码」入口已在实现中取消——系统没有用户体系。</div>",
        unsafe_allow_html=True,
    )

    st.markdown('<div class="ms-section">行业关键词</div>', unsafe_allow_html=True)
    st.markdown(
        _table(
            ["行业", "关键词数", "关键词"],
            [
                (escape(name), str(len(words)), escape("、".join(words)))
                for name, words in INDUSTRY_KEYWORDS.items()
            ],
        ),
        unsafe_allow_html=True,
    )
    st.caption("JD 自动识别行业的依据：命中关键词多者胜出，全不命中则为「通用」。")


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


# ---------------------------------------------------------------- 运行日志


def render_logs() -> None:
    recorder = get_recorder(st)
    summary = recorder.summary()

    st.markdown('<div class="ms-h1">运行日志</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="ms-sub">记录当前浏览器会话中的模型调用与工具调用；会话关闭即清空，不落盘。</p>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="ms-grid4">'
        + _stat(str(len(recorder.events)), "记录条数", "本次会话")
        + _stat(str(summary["llm_calls"]), "模型调用", f"失败 {summary['llm_errors']} 次")
        + _stat(str(summary["tool_calls"]), "工具调用", f"{summary['unique_tools']} 种工具")
        + _stat(f"{summary['tool_avg_ms']} ms", "平均工具耗时", "仅统计工具", _kind="sm")
        + "</div>",
        unsafe_allow_html=True,
    )

    level = st.selectbox("按级别过滤", ["全部", "INFO", "ERROR"], key="log_level")
    st.markdown(_log_console(recorder, level), unsafe_allow_html=True)

    st.markdown(
        '<div class="ms-note">日志只包含工具名、模型结构与耗时，'
        "<b>不含 API Key、简历原文或任何用户身份信息</b>。</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="ms-section">落盘计划 <span class="ms-pill warn">占位</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        _table(
            ["项", "状态", "依赖"],
            [
                ("日志持久化", "占位 · 待 V2.2", "会话表 + 错误表"),
                ("跨会话检索", "占位 · 待 V2.2", "同上"),
                ("模型调用次数统计", "占位 · 待 V2.2", "调用计数需随会话落库"),
            ],
        ),
        unsafe_allow_html=True,
    )


def _log_console(recorder, level: str) -> str:
    events = [e for e in recorder.events if level == "全部" or e["level"] == level]
    if not events:
        return (
            '<div class="ms-log"><span class="wn">WARN</span>  暂无记录。'
            "回到主站开始一次面试，模型与工具调用会实时出现在这里。</div>"
        )
    lines = []
    for event in events:
        cls = {"INFO": "ok", "WARN": "wn", "ERROR": "er"}.get(event["level"], "ok")
        cost = f" ({event['duration_ms']}ms)" if event.get("duration_ms") else ""
        lines.append(
            f'<span class="t">[{event["time"]}]</span> '
            f'<span class="{cls}">{event["level"]}</span>  '
            f'{escape(event["message"])}{cost}'
        )
    return '<div class="ms-log">' + "<br>".join(lines) + "</div>"


# ---------------------------------------------------------------- 组件


def _stat(value: str, label: str, detail: str = "", *, _kind: str = "") -> str:
    cls = " sm" if _kind == "sm" else ""
    warn = " warn" if "占位" in detail else ""
    tail = f'<div class="d{warn}">{escape(detail)}</div>' if detail else ""
    return (
        f'<div class="ms-stat"><div class="v{cls}">{escape(value)}</div>'
        f'<div class="k">{escape(label)}</div>{tail}</div>'
    )


def _table(headers: list[str], rows: list[tuple[Any, ...]]) -> str:
    head = "".join(f"<th>{escape(str(h))}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows
    )
    return (
        f'<div class="ms-table-wrap"><table class="ms-table">'
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def _tool_count() -> int:
    """数一下 MCP 服务实际注册了多少工具，避免文档与代码再次漂移。"""
    source = Path(__file__).resolve().parents[1] / "mcp_server" / "interview_server.py"
    try:
        return len(re.findall(r"^@mcp\.tool\(\)", source.read_text(encoding="utf-8"), re.M))
    except OSError:
        return 0


def _aggregate(turns: list[dict[str, Any]], weights: dict[str, float]) -> dict[str, Any]:
    averages = rubric.competency_averages(turns)
    total = rubric.weighted_total(averages, weights)
    return {"overall_score": total, "dimensions": averages, "verdict": rubric.overall_verdict(total)}


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


def _level(score: float) -> str:
    if score >= 4:
        return "优秀"
    if score >= 3:
        return "达标"
    if score >= 2:
        return "偏弱"
    return "不足"


main()
