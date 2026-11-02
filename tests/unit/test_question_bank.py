"""题库抽题的单元测试。"""

from mcp_server.question_bank import (
    competencies_in_bank,
    detect_industry,
    industries_in_bank,
    load_bank,
    pick_questions,
)


def test_bank_loads_and_has_all_roles():
    bank = load_bank()
    agents = {q["agent"] for q in bank}
    assert agents == {"hr", "tech", "pressure"}
    ids = [q["id"] for q in bank]
    assert len(ids) == len(set(ids))


def test_bank_is_large_enough_for_v3():
    bank = load_bank()
    assert len(bank) >= 90
    roles = {role: sum(1 for q in bank if q["agent"] == role) for role in ("hr", "tech", "pressure")}
    assert all(count >= 20 for count in roles.values())


def test_every_question_declares_known_industry_and_competency():
    bank = load_bank()
    industries = set(industries_in_bank())
    competencies = set(competencies_in_bank())
    for question in bank:
        assert question["industry"] in industries, question["id"]
        assert set(question["competencies"]) <= competencies, question["id"]
        assert question["text"].strip()


def test_every_industry_has_questions_for_all_roles():
    bank = load_bank()
    for industry in industries_in_bank():
        if industry == "通用":
            continue
        roles = {q["agent"] for q in bank if q["industry"] == industry}
        assert roles == {"hr", "tech", "pressure"}, industry


def test_detect_industry_recognizes_common_jds():
    assert detect_industry("负责 React 前端页面开发，熟悉 TypeScript 与 Web 性能优化") == "互联网前端"
    assert detect_industry("参与后端服务开发，使用 Java、Spring 与 MySQL") == "互联网后端"
    assert detect_industry("负责大模型算法与推荐系统，熟悉 PyTorch") == "人工智能"
    assert detect_industry("搭建指标体系、做用户增长与 AB 实验分析") == "数据分析"
    assert detect_industry("负责智能手表固件、RTOS 驱动开发") == "嵌入式"


def test_detect_industry_falls_back_to_general():
    assert detect_industry("负责日常行政事务与会议安排") == "通用"
    assert detect_industry("") == "通用"


def test_pick_questions_respects_count_and_role():
    picks = pick_questions(["系统设计"], "tech", 3, seed=7)
    assert len(picks) == 3
    assert all(q["agent"] == "tech" for q in picks)


def test_pick_questions_filters_by_industry():
    picks = pick_questions(["抗压能力"], "pressure", 3, seed=3, industry="嵌入式")
    assert all(q["industry"] in {"通用", "嵌入式"} for q in picks)


def test_pick_questions_prefers_industry_specific_bank():
    picks = pick_questions([], "tech", 40, seed=5, industry="金融科技")
    assert {q["industry"] for q in picks} >= {"通用", "金融科技"}


def test_pick_questions_tops_up_when_industry_is_thin():
    picks = pick_questions(["系统设计"], "tech", 10, seed=0, industry="产品运营")
    assert len(picks) == 10


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
