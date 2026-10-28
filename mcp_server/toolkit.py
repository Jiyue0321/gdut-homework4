"""确定性工具的实现：简历体检、能力匹配、评分聚合、报告渲染。

MCP 服务与本地直调共用这里的函数，两套调用路径结果完全一致。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from mcp_server import rubric
from mcp_server.question_bank import competencies_in_bank, pick_questions
from mcp_server.sandbox import SandboxError, display_path, resolve_safe

SECTION_HINTS = {
    "教育": ("教育", "学校", "学历", "本科", "硕士", "大学"),
    "经历": ("经历", "实习", "工作", "任职"),
    "项目": ("项目", "作品", "实践"),
    "技能": ("技能", "技术栈", "掌握", "熟悉", "精通"),
}

QUANT_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|％|倍|万|k|K|ms|s|秒|qps|QPS|人|个|项)")


def check_resume_quality(text: str) -> dict[str, Any]:
    """体检简历文本：篇幅、缺失的板块、量化成果数量。"""
    clean = (text or "").strip()
    found = {name: any(h in clean for h in hints) for name, hints in SECTION_HINTS.items()}
    missing = [name for name, ok in found.items() if not ok]
    quantified = len(QUANT_RE.findall(clean))

    tips: list[str] = []
    if len(clean) < 120:
        tips.append("简历内容偏短，建议补充项目背景、你的职责与结果")
    if missing:
        tips.append("未识别到这些板块：" + "、".join(missing))
    if quantified == 0:
        tips.append("没有发现量化成果，面试官无法判断你的贡献大小")
    elif quantified < 3:
        tips.append("量化成果偏少，建议每段经历至少给一个数字")

    return {
        "length": len(clean),
        "sections": found,
        "missing_sections": missing,
        "quantified_results": quantified,
        "tips": tips,
    }


def match_competencies(competencies_json: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """比对 JD 要求与简历自评，输出雷达图数据与缺口表。"""
    radar: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for item in competencies_json:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        required = rubric.clamp(float(item.get("required_level", 0)))
        resume = rubric.clamp(float(item.get("resume_level", 0)))
        weight = max(0.0, float(item.get("weight", 0)))
        radar.append(
            {
                "competency": name,
                "required": round(required, 1),
                "resume": round(resume, 1),
                "weight": round(weight, 3),
            }
        )
        delta = required - resume
        if delta > 0:
            gaps.append(
                {
                    "competency": name,
                    "gap": round(delta, 1),
                    "priority": "高" if delta >= 2 else "中",
                }
            )

    gaps.sort(key=lambda g: g["gap"], reverse=True)
    return {"radar": radar, "gaps": gaps}


def aggregate_scores(
    turns_json: Sequence[Mapping[str, Any]], weights_json: Mapping[str, float]
) -> dict[str, Any]:
    """按能力聚合逐题得分并给出加权总分、判定与预警。"""
    averages = rubric.competency_averages(turns_json)
    total = rubric.weighted_total(averages, weights_json)
    return {
        "overall_score": total,
        "dimensions": averages,
        "verdict": rubric.overall_verdict(total),
        "warnings": rubric.consistency_warnings(averages),
    }


def merge_cross_exam(scores_json: Sequence[float]) -> dict[str, Any]:
    """交叉拷问合并：取三位面试官的中位数。"""
    return {
        "merged": rubric.merge_cross_exam(scores_json),
        "scores": [rubric.clamp(float(s)) for s in scores_json],
    }


def render_report_md(report: Mapping[str, Any]) -> str:
    """把报告数据渲染成 Markdown，供页面展示与下载。"""
    lines: list[str] = []
    title = report.get("role_title") or "模拟面试"
    lines.append(f"# {title} · 面试复盘报告")
    lines.append("")
    lines.append(f"**加权总分：{report.get('overall_score', 0)} / 5**  ")
    lines.append(f"**结论：{report.get('verdict', '')}**")
    lines.append("")

    dims = report.get("dimensions") or {}
    if dims:
        lines.append("## 能力得分")
        lines.append("")
        lines.append("| 能力 | 得分 | 等级 |")
        lines.append("| --- | --- | --- |")
        for name, score in dims.items():
            lines.append(f"| {name} | {score} | {_level_label(float(score))} |")
        lines.append("")

    turns = report.get("turns") or []
    if turns:
        lines.append("## 逐题回顾")
        lines.append("")
        for index, turn in enumerate(turns, start=1):
            lines.append(f"### 第 {index} 题 · {turn.get('agent_label', '')}")
            lines.append("")
            lines.append(f"> **问：** {turn.get('question', '')}")
            lines.append(">")
            lines.append(f"> **答：** {turn.get('answer', '')}")
            lines.append("")
            lines.append(
                f"- 得分：{turn.get('overall', '-')} / 5　考察能力：{turn.get('competency', '-')}"
            )
            if turn.get("evidence"):
                lines.append(f"- 依据：{turn['evidence']}")
            if turn.get("comment"):
                lines.append(f"- 评语：{turn['comment']}")
            lines.append("")

    for key, heading in (
        ("strengths", "## 优势"),
        ("improvements", "## 待改进"),
        ("action_plan", "## 行动清单"),
    ):
        values = report.get(key) or []
        if values:
            lines.append(heading)
            lines.append("")
            for item in values:
                lines.append(f"- {item}")
            lines.append("")

    sample = report.get("sample_answer")
    if sample:
        lines.append("## 参考答案示范")
        lines.append("")
        lines.append(sample)
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("由「面面俱到」模拟面试多智能体生成，评分为启发式参考，不构成招聘结论。")
    return "\n".join(lines)


def _level_label(score: float) -> str:
    if score >= 4:
        return "优秀"
    if score >= 3:
        return "达标"
    if score >= 2:
        return "偏弱"
    return "不足"


def export_report(filename: str, content: str) -> dict[str, Any]:
    """把报告写入 workspace 沙箱。"""
    try:
        target = resolve_safe(filename)
    except SandboxError as exc:
        raise ValueError(str(exc)) from exc
    if target.suffix.lower() not in {".md", ".markdown", ".txt"}:
        raise ValueError("仅支持导出 .md / .markdown / .txt 报告")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"path": display_path(target), "bytes": len(content.encode("utf-8"))}


def get_current_time() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def list_question_competencies() -> list[str]:
    return competencies_in_bank()


def select_questions(
    competencies: Sequence[str], agent: str, count: int, seed: int | None = None
) -> list[dict[str, Any]]:
    return pick_questions(competencies, agent, count, seed)
