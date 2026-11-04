"""文本清洗、重复抑制与问题查重的单元测试（BUG-06 / BUG-07）。"""

from __future__ import annotations

from agent.text import (
    DUPLICATE_THRESHOLD,
    clean_lines,
    clean_text,
    collapse_repetition,
    is_duplicate_question,
    question_similarity,
)

BOTTLENECK_Q = "你说下单接口 P99 从 800ms 降到 120ms，当时是怎么定位瓶颈在哪的？先讲讲你的排查过程。"


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


def test_rephrased_same_question_is_duplicate():
    rewritten = "下单接口从 800ms 优化到 120ms，你是怎么定位性能瓶颈的？"
    assert question_similarity(BOTTLENECK_Q, rewritten) >= DUPLICATE_THRESHOLD
    assert is_duplicate_question(rewritten, [BOTTLENECK_Q])


def test_same_highlight_from_new_angle_is_not_duplicate():
    """同样挖 P99 这个亮点，换成验证/回滚视角就不该被拦掉。"""
    new_angle = "那这次优化上线后，你怎么验证 P99 确实稳定，回滚预案是什么？"
    assert question_similarity(BOTTLENECK_Q, new_angle) < DUPLICATE_THRESHOLD
    assert not is_duplicate_question(new_angle, [BOTTLENECK_Q])


def test_question_similarity_is_bounded_and_handles_empty():
    assert question_similarity("", BOTTLENECK_Q) == 0.0
    assert question_similarity(BOTTLENECK_Q, BOTTLENECK_Q) == 1.0
