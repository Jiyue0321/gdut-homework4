"""PDF 中文字体的单元测试：确保仓库自带字体存在且被真正内嵌。

线上曾出现「中文看着正常但文件只有 15 KB」的情况——那是 CID 回退，
换台设备或换阅读器就可能变方块。这里用文件结构断言，不靠肉眼判断。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_server import pdf_report

REPO_FONT = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "SimHei.ttf"

SAMPLE_REPORT = {
    "role_title": "后端开发实习生",
    "industry": "互联网后端",
    "overall_score": 3.4,
    "verdict": "基本达标",
    "dimensions": {"系统设计": 3.5, "沟通表达": 3.0},
    "turns": [
        {
            "agent_label": "技术面试官",
            "question": "订单模块怎么防止重复下单？",
            "answer": "用唯一索引保证幂等。",
            "overall": 3,
            "competency": "系统设计",
            "evidence": "唯一索引",
            "comment": "方法正确，缺少并发场景说明。",
        }
    ],
    "strengths": ["给出量化结果"],
    "improvements": ["补充回滚预案"],
    "action_plan": ["练习 STAR 结构"],
}


def test_repo_font_is_committed():
    """字体必须随仓库走：云端容器的系统字体目录通常为空。"""
    assert REPO_FONT.exists(), "assets/fonts/SimHei.ttf 缺失，云端 PDF 会退回 CID 字体"
    assert REPO_FONT.stat().st_size > 1_000_000


def test_pdf_embeds_truetype_font():
    """生成的 PDF 里必须有 FontFile2 流，否则中文字体没被内嵌。"""
    payload = pdf_report.render_report_pdf(SAMPLE_REPORT)
    assert b"/FontFile2" in payload


def test_pdf_size_implies_embedded_font():
    """内嵌字体的 PDF 不可能只有十几 KB——这个门槛能拦住静默回退。"""
    payload = pdf_report.render_report_pdf(SAMPLE_REPORT)
    assert len(payload) > 16 * 1024


def test_embedded_font_flag_matches_reality():
    """诊断开关要和实际注册的字体一致。"""
    assert pdf_report.embedded_font_in_use() is (pdf_report.FONT_NAME != "STSong-Light")


@pytest.mark.parametrize("text", ["面试复盘报告", "面面俱到 · 模拟面试", "P99 从 800ms 降到 120ms"])
def test_pdf_renders_chinese_without_error(text):
    report = dict(SAMPLE_REPORT, strengths=[text])
    payload = pdf_report.render_report_pdf(report)
    assert payload.startswith(b"%PDF")
