"""题库抽题的单元测试。"""

from mcp_server.question_bank import competencies_in_bank, load_bank, pick_questions


def test_bank_loads_and_has_all_roles():
    bank = load_bank()
    agents = {q["agent"] for q in bank}
    assert agents == {"hr", "tech", "pressure"}
    ids = [q["id"] for q in bank]
    assert len(ids) == len(set(ids))


def test_pick_questions_respects_count_and_role():
    picks = pick_questions(["系统设计"], "tech", 3, seed=7)
    assert len(picks) == 3
    assert all(q["agent"] == "tech" for q in picks)


def test_pick_questions_is_deterministic_with_seed():
    first = pick_questions(["技术深度"], "tech", 2, seed=42)
    second = pick_questions(["技术深度"], "tech", 2, seed=42)
    assert [q["id"] for q in first] == [q["id"] for q in second]


def test_pick_questions_falls_back_when_no_tag_matches():
    picks = pick_questions(["不存在的标签"], "hr", 2, seed=1)
    assert len(picks) == 2
    assert all(q["agent"] == "hr" for q in picks)


def test_pick_questions_zero_count():
    assert pick_questions(["技术深度"], "tech", 0) == []


def test_competencies_in_bank_sorted_and_non_empty():
    names = competencies_in_bank()
    assert names == sorted(names)
    assert "技术深度" in names
