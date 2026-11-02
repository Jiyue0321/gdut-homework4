"""把面试报告数据渲染成 PDF（中文，A4，可直接交给面试者留存）。

PDF 只做版面，不重新计算任何评分：所有数字都来自 ``report`` 字典，
与 Markdown 导出、页面展示共用同一份数据，避免三处结论不一致。
"""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

FONT = "ReportCJK"
MUTED = colors.HexColor("#5A6472")
BRAND = colors.HexColor("#2E5EAA")
LIGHT = colors.HexColor("#E8EEF7")

# 优先嵌入本机中文字体，PDF 换台机器也能正常显示；都没有时退回 reportlab 的 CID 字体。
FONT_CANDIDATES = (
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
)


def _register_cjk_font() -> str:
    candidates = list(FONT_CANDIDATES)
    extra = os.getenv("REPORT_FONT_PATH", "").strip()
    if extra:
        candidates.insert(0, extra)
    for path in candidates:
        if not Path(path).exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont(FONT, path, subfontIndex=0))
            return FONT
        except Exception:
            continue
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"


FONT_NAME = _register_cjk_font()

STYLES = {
    "title": ParagraphStyle("title", fontName=FONT_NAME, fontSize=20, leading=28, textColor=BRAND),
    "subtitle": ParagraphStyle("subtitle", fontName=FONT_NAME, fontSize=10, leading=16, textColor=MUTED),
    "h2": ParagraphStyle("h2", fontName=FONT_NAME, fontSize=14, leading=22, textColor=BRAND, spaceBefore=12),
    "body": ParagraphStyle("body", fontName=FONT_NAME, fontSize=10.5, leading=17, alignment=TA_LEFT),
    "small": ParagraphStyle("small", fontName=FONT_NAME, fontSize=9, leading=14, textColor=MUTED),
    "cell": ParagraphStyle("cell", fontName=FONT_NAME, fontSize=9.5, leading=14),
}

PAGE_MARGIN = 18 * mm
CONTENT_WIDTH = A4[0] - 2 * PAGE_MARGIN
LEVEL_LABELS = ((4, "优秀"), (3, "达标"), (2, "偏弱"), (0, "不足"))


def _esc(value: Any) -> str:
    """Paragraph 按迷你 HTML 解析，用户文本必须先转义。"""
    text = "" if value is None else str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _para(value: Any, style: str = "body") -> Paragraph:
    return Paragraph(_esc(value).replace("\n", "<br/>"), STYLES[style])


def _level_label(score: float) -> str:
    for threshold, label in LEVEL_LABELS:
        if score >= threshold:
            return label
    return "不足"


def _table(header: list[str], rows: list[list[Any]], widths: list[float] | None = None) -> Table:
    data = [[Paragraph(_esc(h), STYLES["cell"]) for h in header]]
    data += [[Paragraph(_esc(cell), STYLES["cell"]) for cell in row] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
                ("TEXTCOLOR", (0, 0), (-1, 0), BRAND),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B9C6DA")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _headline(report: Mapping[str, Any], story: list[Any]) -> None:
    title = report.get("role_title") or "模拟面试"
    story.append(_para(f"{title} · 面试复盘报告", "title"))
    subtitle = "由「面面俱到」模拟面试多智能体生成"
    industry = report.get("industry")
    if industry and industry != "通用":
        subtitle += f"　|　目标行业：{industry}"
    story.append(_para(subtitle, "subtitle"))
    story.append(Spacer(1, 8))

    score = report.get("overall_score", 0)
    verdict = report.get("verdict", "")
    summary = _table(
        ["加权总分", "结论"],
        [[f"{score} / 5", verdict or "—"]],
        widths=[CONTENT_WIDTH * 0.25, CONTENT_WIDTH * 0.75],
    )
    summary.setStyle(TableStyle([("FONTSIZE", (0, 1), (-1, 1), 11)]))
    story.append(summary)


def _dimensions(report: Mapping[str, Any], story: list[Any]) -> None:
    dims = report.get("dimensions") or {}
    if not dims:
        return
    story.append(_para("能力得分", "h2"))
    rows = [[name, f"{float(score):.1f}", _level_label(float(score))] for name, score in dims.items()]
    story.append(
        _table(["能力", "得分", "等级"], rows, widths=[CONTENT_WIDTH * 0.56, CONTENT_WIDTH * 0.22, CONTENT_WIDTH * 0.22])
    )


def _turns(report: Mapping[str, Any], story: list[Any]) -> None:
    turns = report.get("turns") or []
    if not turns:
        return
    story.append(_para("逐题回顾", "h2"))
    for index, turn in enumerate(turns, start=1):
        block: list[Any] = [
            _para(f"第 {index} 题 · {turn.get('agent_label', '')}", "body"),
            _para(f"问：{turn.get('question', '')}", "small"),
            _para(f"答：{turn.get('answer', '')}", "small"),
            _para(
                f"得分：{turn.get('overall', '-')} / 5　考察能力：{turn.get('competency', '-')}",
                "small",
            ),
        ]
        if turn.get("evidence"):
            block.append(_para(f"依据：{turn['evidence']}", "small"))
        if turn.get("comment"):
            block.append(_para(f"评语：{turn['comment']}", "small"))
        block.append(Spacer(1, 6))
        story.append(KeepTogether(block))


def _cross_exam(report: Mapping[str, Any], story: list[Any]) -> None:
    cross_exam = report.get("cross_exam")
    if not cross_exam:
        return
    story.append(_para("交叉拷问", "h2"))
    story.append(_para(f"针对最弱的一题：{cross_exam.get('question', '')}", "small"))
    scores = cross_exam.get("scores") or {}
    labels = (("hr", "HR 面试官"), ("tech", "技术面试官"), ("pressure", "压力面试官"))
    rows = [
        [label, f"{scores[agent].get('overall', '-')} / 5", scores[agent].get("comment", "")]
        for agent, label in labels
        if isinstance(scores.get(agent), Mapping)
    ]
    if rows:
        story.append(_table(["面试官", "得分", "评语"], rows, widths=[CONTENT_WIDTH * 0.24, CONTENT_WIDTH * 0.16, CONTENT_WIDTH * 0.6]))
    merged = cross_exam.get("merged") or {}
    story.append(Spacer(1, 4))
    story.append(_para(f"综合中位数：{merged.get('overall', '-')} / 5", "body"))


def _narrative(report: Mapping[str, Any], story: list[Any]) -> None:
    for key, heading in (
        ("strengths", "优势"),
        ("improvements", "待改进"),
        ("action_plan", "行动清单"),
    ):
        values = report.get(key) or []
        if not values:
            continue
        story.append(_para(heading, "h2"))
        for index, item in enumerate(values, start=1):
            prefix = f"{index}. " if key == "action_plan" else "· "
            story.append(_para(prefix + str(item), "body"))

    warnings = report.get("warnings") or []
    if warnings:
        story.append(_para("需要优先补强的能力", "h2"))
        for warning in warnings:
            story.append(_para("· " + str(warning), "body"))

    sample = report.get("sample_answer")
    if sample:
        story.append(_para("参考答案示范", "h2"))
        story.append(_para(sample, "body"))


def _footer(story: list[Any], generated_at: str) -> None:
    story.append(Spacer(1, 16))
    story.append(_para("——", "small"))
    story.append(
        _para(
            f"生成时间：{generated_at}。评分为启发式参考，不构成招聘结论。",
            "small",
        )
    )


def render_report_pdf(report: Mapping[str, Any], *, generated_at: str = "") -> bytes:
    """报告字典 → PDF 字节流。空字段会被跳过，不产生空表格。"""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN,
        bottomMargin=PAGE_MARGIN,
        title="面试复盘报告",
        author="面面俱到",
    )
    story: list[Any] = []
    _headline(report, story)
    _dimensions(report, story)
    _turns(report, story)
    _cross_exam(report, story)
    _narrative(report, story)
    _footer(story, generated_at or "—")
    document.build(story)
    return buffer.getvalue()


__all__ = ["render_report_pdf"]
