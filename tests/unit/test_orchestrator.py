"""编排器单元测试：计划生成、阶段流转、追问与交叉拷问。"""

from __future__ import annotations

import pytest

from agent.orchestrator import InterviewConfig, InterviewSession, Orchestrator, _friendly_error
from agent.state import Phase
from agent.tools import LocalTools
from tests.conftest import JD_TEXT, RESUME_TEXT, build_fake_llm


def make_orchestrator(llm, config: InterviewConfig | None = None) -> Orchestrator:
    return Orchestrator(llm, LocalTools(), config)


def test_start_reaches_interview_with_question():
    session = make_orchestrator(build_fake_llm()).start(RESUME_TEXT, JD_TEXT, "后端开发实习生")
    assert session.error == ""
    assert session.phase == Phase.INTERVIEW
    assert session.current_question is not None
    assert session.profile is not None
    assert session.competency_model is not None
    assert session.radar and session.gaps


def test_start_reports_error_on_bad_config():
    from agent.llm import LLMError

    class BrokenLLM:
        def chat_json(self, *args, **kwargs):
            raise LLMError("API key 无效")

    session = make_orchestrator(BrokenLLM()).start(RESUME_TEXT, JD_TEXT, "岗位")
    assert session.phase == Phase.IDLE
    assert "鉴权" in session.error


def test_plan_prioritizes_largest_gap():
    llm = build_fake_llm()
    session = make_orchestrator(llm, InterviewConfig(max_questions=6)).start(
        RESUME_TEXT, JD_TEXT, "后端开发实习生"
    )
    assert session.plan is not None
    assert session.plan.slots[0].competency == "系统设计"  # 缺口 4-2 最大


def test_plan_alternates_agents():
    session = make_orchestrator(build_fake_llm()).start(RESUME_TEXT, JD_TEXT, "岗位")
    agents = [slot.agent for slot in session.plan.slots]
    assert agents[:3] == ["hr", "tech", "pressure"]


def test_plan_respects_max_questions():
    session = make_orchestrator(
        build_fake_llm(), InterviewConfig(max_questions=3)
    ).start(RESUME_TEXT, JD_TEXT, "岗位")
    assert len(session.plan.slots) == 3


def test_full_interview_reaches_done_with_report():
    session = make_orchestrator(build_fake_llm()).start(RESUME_TEXT, JD_TEXT, "后端开发实习生")
    orchestrator = make_orchestrator(build_fake_llm())
    steps = 0
    while not session.finished and session.error == "" and steps < 20:
        session = orchestrator.answer(session, "我用唯一索引保证幂等，压测 QPS 从 200 提到 900。")
        steps += 1
    assert session.phase == Phase.DONE
    assert session.error == ""
    assert len(session.turns) == len(session.plan.slots)
    assert 0 <= session.report_data["overall_score"] <= 5
    assert session.narrative["action_plan"]


def test_answer_without_question_is_rejected():
    session = make_orchestrator(build_fake_llm()).start(RESUME_TEXT, JD_TEXT, "岗位")
    empty = InterviewSession()
    result = make_orchestrator(build_fake_llm()).answer(empty, "回答")
    assert "没有待回答的问题" in result.error


def test_followup_keeps_same_slot_when_model_requests():
    llm = build_fake_llm()
    orchestrator = make_orchestrator(llm)
    session = orchestrator.start(RESUME_TEXT, JD_TEXT, "岗位")
    slot_before = session.slot_index
    # 第二次面试官调用带 is_followup=True
    from agent.state import TurnDecision

    llm.responses[TurnDecision] = {
        "score": {"dimensions": {"系统设计": 2}, "overall": 2, "evidence": "原文", "comment": "含糊"},
        "question": {
            "text": "你说的提升 30% 基线是多少？",
            "competency": "系统设计",
            "rubric": {"criteria": ["给出基线"], "good_looks_like": "有数据"},
        },
        "is_followup": True,
    }
    session = orchestrator.answer(session, "提升很多。")
    assert session.slot_index == slot_before
    assert session.current_question.text.startswith("你说的提升")
    assert session.followup_used


def test_followup_happens_at_most_once_per_slot():
    from agent.state import TurnDecision

    llm = build_fake_llm()
    llm.responses[TurnDecision] = {
        "score": {"dimensions": {"系统设计": 2}, "overall": 2, "evidence": "原文", "comment": "含糊"},
        "question": {
            "text": "追问",
            "competency": "系统设计",
            "rubric": {"criteria": ["a"], "good_looks_like": "b"},
        },
        "is_followup": True,
    }
    orchestrator = make_orchestrator(llm)
    session = orchestrator.start(RESUME_TEXT, JD_TEXT, "岗位")
    session = orchestrator.answer(session, "含糊回答")
    slot_after_first = session.slot_index
    session = orchestrator.answer(session, "还是含糊")
    assert session.slot_index == slot_after_first + 1


def test_cross_exam_runs_and_merges_three_lenses():
    session = make_orchestrator(build_fake_llm()).start(RESUME_TEXT, JD_TEXT, "岗位")
    orchestrator = make_orchestrator(build_fake_llm())
    steps = 0
    while not session.finished and session.error == "" and steps < 20:
        session = orchestrator.answer(session, "回答")
        steps += 1
    assert session.cross_exam is not None
    assert set(session.cross_exam.scores) == {"hr", "tech", "pressure"}
    assert 0 <= session.cross_exam.merged.overall <= 5


def test_cross_exam_can_be_disabled():
    session = make_orchestrator(
        build_fake_llm(), InterviewConfig(run_cross_exam=False)
    ).start(RESUME_TEXT, JD_TEXT, "岗位")
    orchestrator = make_orchestrator(build_fake_llm(), InterviewConfig(run_cross_exam=False))
    steps = 0
    while not session.finished and session.error == "" and steps < 20:
        session = orchestrator.answer(session, "回答")
        steps += 1
    assert session.cross_exam is None
    assert session.phase == Phase.DONE


def test_qa_pairs_expose_competency_and_labels():
    session = make_orchestrator(build_fake_llm()).start(RESUME_TEXT, JD_TEXT, "岗位")
    orchestrator = make_orchestrator(build_fake_llm())
    session = orchestrator.answer(session, "回答")
    pair = session.qa_pairs[0]
    assert pair["agent_label"] == "HR 面试官"
    assert pair["competency"]
    assert pair["overall"] == 3


@pytest.mark.parametrize(
    "message,expected",
    [
        ("Error code 401 Unauthorized", "鉴权失败"),
        ("Request timed out", "超时"),
        ("something odd", "出错了"),
    ],
)
def test_friendly_error_mapping(message, expected):
    assert expected in _friendly_error(RuntimeError(message))
