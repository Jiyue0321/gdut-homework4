"""确定性评分：维度分子在模型，聚合与合并在这里。

这些函数被 MCP 工具、本地工具与单元测试共同调用，
保证「同一批分数怎么算总分」永远可复现。
"""

from __future__ import annotations

from statistics import median
from typing import Any, Iterable, Mapping

SCORE_MIN = 0
SCORE_MAX = 5


def clamp(value: float, low: float = SCORE_MIN, high: float = SCORE_MAX) -> float:
    return max(low, min(high, value))


def normalize_weights(weights: Mapping[str, float]) -> dict[str, float]:
    """把权重归一化到总和为 1；全为 0 时退化为均分。"""
    positive = {k: max(0.0, float(v)) for k, v in weights.items()}
    total = sum(positive.values())
    if total <= 0:
        if not positive:
            return {}
        even = 1.0 / len(positive)
        return {k: even for k in positive}
    return {k: v / total for k, v in positive.items()}


def weighted_total(scores: Mapping[str, float], weights: Mapping[str, float]) -> float:
    """按能力权重计算加权总分（0-5，保留一位小数）。"""
    normalized = normalize_weights({k: weights.get(k, 0.0) for k in scores})
    if not normalized:
        return 0.0
    total = sum(clamp(float(scores[k])) * w for k, w in normalized.items())
    return round(total, 1)


def aggregate_competency_scores(
    turns: Iterable[Mapping[str, Any]],
) -> dict[str, list[float]]:
    """按能力聚合每一题的得分，用于雷达图的「面试实测」一列。

    ``turns`` 中每项需包含 ``competency`` 与 ``score``（0-5 的数字）。
    """
    buckets: dict[str, list[float]] = {}
    for turn in turns:
        competency = str(turn.get("competency", "")).strip()
        if not competency:
            continue
        buckets.setdefault(competency, []).append(clamp(float(turn["score"])))
    return buckets


def competency_averages(turns: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    buckets = aggregate_competency_scores(turns)
    return {name: round(sum(vals) / len(vals), 1) for name, vals in buckets.items()}


def merge_cross_exam(scores: Iterable[float]) -> float:
    """交叉拷问：三位面试官各自打分，取中位数，避免单个严格/宽松面试官带偏。"""
    values = [clamp(float(s)) for s in scores]
    if not values:
        return 0.0
    return round(float(median(values)), 1)


def consistency_warnings(
    scores: Mapping[str, float], *, threshold: float = 2.5
) -> list[str]:
    """面试实测与 JD 要求差距过大的能力项，作为报告的改进重点。"""
    warnings: list[str] = []
    for name, score in scores.items():
        if clamp(score) < threshold:
            warnings.append(f"{name} 实测 {score:.1f}/5，低于岗位要求的常见门槛")
    return warnings


def overall_verdict(total: float) -> str:
    if total >= 4.0:
        return "表现出色，可以投递该岗位"
    if total >= 3.0:
        return "基本达标，补齐短板后竞争力明显"
    if total >= 2.0:
        return "存在明显缺口，建议针对性训练后再面"
    return "差距较大，建议先系统补基础"
