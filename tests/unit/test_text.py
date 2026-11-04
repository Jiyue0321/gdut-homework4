"""文本清洗与重复抑制的单元测试（BUG-06）。"""

from __future__ import annotations

from agent.text import clean_lines, clean_text, collapse_repetition


def test_clean_text_removes_invisible_characters():
    dirty = "教育背景​：广东工业大学﻿ 软件工程\x00"
    cleaned = clean_text(dirty)
    assert "​" not in cleaned
    assert "﻿" not in cleaned
    assert "\x00" not in cleaned
    assert "广东工业大学" in cleaned


def test_clean_text_keeps_paragraph_breaks():
    cleaned = clean_text("第一段\n\n\n\n第二段")
    assert cleaned == "第一段\n\n第二段"


def test_collapse_repetition_stops_hallucination_loop():
    loop = "被访问点列表 100ms 的数据量有 30ms 的。" * 6
    result = collapse_repetition(loop)
    assert result.count("被访问点列表") == 3


def test_collapse_repetition_leaves_normal_text_untouched():
    text = "我做的是订单模块。用了幂等键。压测 QPS 提到 900。"
    assert collapse_repetition(text) == text


def test_clean_lines_deduplicates_and_drops_blank():
    items = ["表达清晰", "表达清晰", "  ", "缺少量化"]
    assert clean_lines(items) == ["表达清晰", "缺少量化"]
