"""简历、岗位与面试官智能体的单元测试（使用假模型）。"""

import pytest

from agent.agents import interviewers, jd, resume
from agent.state import AnswerScore, Question, Rubric, Slot, TurnDecision
from tests.fakes import FakeLLM, default_responses


@pytest.fixture
def fake():
    return FakeLLM()


def test_resume_analysis_returns_profile(fake):
    profile = resume.analyze_resume(fake, "我的简历文本", {"tips": ["缺少量化成果"]})
    assert profile.skills == ["Python", "FastAPI"]
    assert "缺少量化成果" in fake.calls[0][1][0]["content"]


def test_resume_messages_include_original_text():
    messages = resume.build_messages("技能：Python")
    assert "技能：Python" in messages[0]["content"]


def test_jd_analysis_normalizes_weights(fake):
    model = jd.analyze_jd(fake, "岗位 JD 文本", "后端开发实习生")
    assert abs(sum(c.weight for c in model.competencies) - 1.0) < 0.01


def test_jd_analysis_falls_back_to_default_role_title(fake):
    model = jd.analyze_jd(fake, "JD", "")
    assert model.role_title


def test_ensure_weights_caps_competency_count():
    from agent.state import CompetencyModel

    model = CompetencyModel(
        role_title="岗位",
        competencies=[
            {"name": f"能力{i}", "weight": 1, "required_level": 3, "resume_level": 2}
            for i in range(9)
        ],
    )
    result = jd._ensure_weights(model)
    assert len(result.competencies) == 7


def test_interviewer_messages_carry_slot_focus(fake):
    messages = interviewers.build_messages(
        Slot(agent="tech", competency="系统设计", focus="订单幂等"),
        profile=default_resume(),
        role_title="后端开发",
    )
    assert "订单幂等" in messages[0]["content"]


def test_interviewer_first_question_drops_hallucinated_score():
    fake = FakeLLM()
    slot = Slot(agent="tech", competency="系统设计", focus="订单")
    decision = interviewers.ask(fake, slot, default_resume(), "后端开发")
    assert decision.score is None
    assert decision.question.text.startswith("讲讲你订单模块")


def test_interviewer_last_slot_drops_extra_question():
    responses = default_responses()
    responses[TurnDecision] = {
        "score": {"dimensions": {"系统设计": 4}, "overall": 4, "evidence": "e", "comment": "c"},
        "question": {
            "text": "不该出现的问题",
            "competency": "系统设计",
            "rubric": {"criteria": ["a"], "good_looks_like": "b"},
        },
    }
    fake = FakeLLM(responses)
    slot = Slot(agent="hr", competency="沟通表达", focus="收尾")
    decision = interviewers.ask(
        fake, slot, default_resume(), "后端开发", last_question="问", last_answer="答", is_last_slot=True
    )
    assert decision.question is None
    assert decision.score.overall == 4


def test_interviewer_uses_generation_temperature():
    fake = FakeLLM()
    slot = Slot(agent="tech", competency="系统设计", focus="订单")
    interviewers.ask(fake, slot, default_resume(), "后端开发")
    assert fake.calls[0][2]["temperature"] == 0.7


def default_resume():
    from agent.state import ResumeProfile

    return ResumeProfile(
        summary="后端实习",
        skills=["Python"],
        projects=["订单"],
        highlights=["接口提速"],
        concerns=["缺数字"],
    )
