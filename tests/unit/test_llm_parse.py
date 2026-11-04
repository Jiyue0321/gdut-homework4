"""大模型 JSON 容错解析的单元测试（BUG-02 / BUG-04）。"""

from __future__ import annotations

import json

import pytest

from agent.llm import _json_candidates, _parse_structured, _repair_json
from agent.state import AnswerScore

VALID = {
    "dimensions": {"系统设计": 3},
    "overall": 3,
    "evidence": "用了唯一索引",
    "comment": "讲到关键点",
}


def test_parse_plain_json():
    score = _parse_structured(json.dumps(VALID, ensure_ascii=False), AnswerScore)
    assert score.overall == 3


def test_parse_json_wrapped_in_markdown_fence():
    text = "```json\n" + json.dumps(VALID, ensure_ascii=False) + "\n```"
    score = _parse_structured(text, AnswerScore)
    assert score.comment == "讲到关键点"


def test_parse_json_with_chatty_prefix():
    text = "好的，这是我的评分：\n" + json.dumps(VALID, ensure_ascii=False)
    score = _parse_structured(text, AnswerScore)
    assert score.evidence == "用了唯一索引"


def test_parse_truncated_json_is_repaired():
    """模拟 max_tokens 截断：末尾闭合符号丢失（BUG-02 的真实场景）。"""
    full = json.dumps(VALID, ensure_ascii=False)
    truncated = full.rstrip()[:-1]
    assert not truncated.endswith("}")
    score = _parse_structured(truncated, AnswerScore)
    assert score.overall == 3


def test_parse_truncated_mid_string_keeps_partial_value():
    full = json.dumps(VALID, ensure_ascii=False)
    truncated = full[: full.index("讲到") + 2]
    score = _parse_structured(truncated, AnswerScore)
    assert score.comment == "讲到"


def test_repair_truncated_nested_structure():
    text = '{"dimensions": {"系统设计": 3}, "overall": 3, "evidence": "用了唯一索引", "comment": "讲'
    repaired = _repair_json(text)
    payload = json.loads(repaired)
    assert payload["comment"] == "讲"
    assert payload["dimensions"]["系统设计"] == 3


def test_repair_drops_trailing_comma():
    assert json.loads(_repair_json('{"a": 1, "b": [1, 2,')) == {"a": 1, "b": [1, 2]}


def test_candidates_are_unique_and_non_empty():
    candidates = _json_candidates("```json\n{\"a\": 1}\n```")
    assert candidates[0] != ""
    assert len(candidates) == len(set(candidates))


def test_unrecoverable_output_raises():
    with pytest.raises(Exception):
        _parse_structured("完全不是 JSON 的一段话", AnswerScore)
