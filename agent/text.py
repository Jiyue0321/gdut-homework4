"""文本清洗：过滤模型幻觉产生的重复句与不可见字符，保证报告可读。"""

from __future__ import annotations

import re
from typing import Sequence

# 不可见字符：零宽空格、零宽连接符、BOM、方向控制符、软连字符等。
_INVISIBLE_RE = re.compile(r"[​-‏‪-‮⁠-⁤﻿­]")
# 连续空白（不含换行）压成单个空格，连续换行最多保留一个空行。
_INLINE_WS_RE = re.compile(r"[ \t　]{2,}")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_CLAUSE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;，,])")

# 同一分句重复出现超过 3 次视为幻觉循环，保留首次出现。
_REPEAT_LIMIT = 3


def clean_text(text: str) -> str:
    """去掉不可见字符，统一空白。保留换行，供 Markdown 渲染。"""
    if not text:
        return ""
    cleaned = _INVISIBLE_RE.sub("", str(text))
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    cleaned = _INLINE_WS_RE.sub(" ", cleaned)
    return _MULTI_NEWLINE_RE.sub("\n\n", cleaned).strip()


def collapse_repetition(text: str, *, limit: int = _REPEAT_LIMIT) -> str:
    """压制幻觉式重复：同一分句循环出现时只保留前 ``limit`` 次，并截断后续。"""
    if not text:
        return ""
    clauses = _CLAUSE_SPLIT_RE.split(text)
    counts: dict[str, int] = {}
    kept: list[str] = []
    for clause in clauses:
        key = clause.strip()
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
        if counts[key] <= limit:
            kept.append(clause)
    return "".join(kept).strip()


_ASCII_WORD_RE = re.compile(r"[a-z0-9]+")
# 二元组重叠度达到该值即视为「换个说法问同一件事」。
DUPLICATE_THRESHOLD = 0.6


def _question_tokens(text: str) -> set[str]:
    lowered = str(text or "").lower()
    chars = re.sub(r"[\s\W_]+", "", lowered)
    grams = {chars[i : i + 2] for i in range(len(chars) - 1)}
    return grams | set(_ASCII_WORD_RE.findall(lowered))


def question_similarity(left: str, right: str) -> float:
    """按字二元组 + 英文词（P99、800ms）计算重叠度，取值 0-1。

    用重叠度而非 Jaccard：改写过的问题与原文长度不同，但共同片段足以说明
    在问同一件事；分母取较短一方，避免长问题把分数稀释。
    """
    a, b = _question_tokens(left), _question_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def is_duplicate_question(text: str, asked: list[str] | Sequence[str]) -> bool:
    return any(
        question_similarity(text, previous) >= DUPLICATE_THRESHOLD for previous in asked
    )


def clean_lines(items: list[str]) -> list[str]:
    """清洗列表型文本并去重（保留顺序），丢弃清洗后为空的项。"""
    result: list[str] = []
    seen: set[str] = set()
    for item in items or []:
        cleaned = collapse_repetition(clean_text(str(item)))
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result
