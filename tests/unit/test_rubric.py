"""确定性评分函数的单元测试。"""

from mcp_server import rubric


def test_clamp_bounds():
    assert rubric.clamp(-1) == 0
    assert rubric.clamp(9) == 5
    assert rubric.clamp(3.4) == 3.4


def test_normalize_weights_sums_to_one():
    weights = rubric.normalize_weights({"a": 1, "b": 3})
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert weights["b"] > weights["a"]


def test_normalize_weights_all_zero_falls_back_to_even():
    weights = rubric.normalize_weights({"a": 0, "b": 0})
    assert weights == {"a": 0.5, "b": 0.5}


def test_normalize_weights_empty():
    assert rubric.normalize_weights({}) == {}


def test_weighted_total_uses_weights():
    scores = {"技术深度": 5, "沟通表达": 1}
    weights = {"技术深度": 0.9, "沟通表达": 0.1}
    assert rubric.weighted_total(scores, weights) == 4.6


def test_weighted_total_clamps_out_of_range_scores():
    assert rubric.weighted_total({"a": 99}, {"a": 1}) == 5.0


def test_weighted_total_missing_weight_contributes_zero():
    total = rubric.weighted_total({"a": 5, "b": 5}, {"a": 1})
    assert total == 5.0


def test_competency_averages_groups_same_competency():
    turns = [
        {"competency": "技术深度", "score": 4},
        {"competency": "技术深度", "score": 3},
        {"competency": "沟通表达", "score": 2},
    ]
    assert rubric.competency_averages(turns) == {"技术深度": 3.5, "沟通表达": 2.0}


def test_competency_averages_skips_blank_competency():
    turns = [{"competency": "", "score": 5}, {"competency": "x", "score": 1}]
    assert rubric.competency_averages(turns) == {"x": 1.0}


def test_merge_cross_exam_uses_median():
    assert rubric.merge_cross_exam([1, 5, 3]) == 3.0
    assert rubric.merge_cross_exam([2, 4]) == 3.0


def test_merge_cross_exam_empty():
    assert rubric.merge_cross_exam([]) == 0.0


def test_consistency_warnings_flags_low_scores():
    warnings = rubric.consistency_warnings({"系统设计": 1.5, "沟通表达": 4.0})
    assert len(warnings) == 1
    assert "系统设计" in warnings[0]


def test_overall_verdict_thresholds():
    assert "出色" in rubric.overall_verdict(4.2)
    assert "基本达标" in rubric.overall_verdict(3.1)
    assert "明显缺口" in rubric.overall_verdict(2.4)
    assert "差距较大" in rubric.overall_verdict(1.0)
