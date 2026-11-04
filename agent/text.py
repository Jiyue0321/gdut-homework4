"""文本清洗：过滤模型幻觉产生的重复句与不可见字符，保证报告可读。"""

from __future__ import annotations

import re

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
