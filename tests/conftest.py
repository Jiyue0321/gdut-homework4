"""共享 fixture。"""

from __future__ import annotations

import pytest

from agent.state import FinalReport
from tests.fakes import FakeLLM, default_responses

RESUME_TEXT = """\
教育背景：广东工业大学 软件工程 本科 2022-2026
实习经历：某互联网公司 后端开发实习 2025.07-2025.09
项目经历：校园二手交易平台，负责订单模块
技术栈：Python、FastAPI、MySQL、Redis
项目成果：接口平均响应从 800ms 降到 120ms，日活 3000 人
"""

JD_TEXT = """\
后端开发实习生
职责：参与交易系统后端开发，负责接口设计与性能优化。
要求：熟悉 Python 与常见 Web 框架；理解数据库与缓存；能独立定位线上问题。
"""


def build_fake_llm(questions: int = 20) -> FakeLLM:
    """每个 slot 至少一次调用；追问与交叉拷问都复用同一份问答模板。"""
    from agent.state import TurnDecision

    responses = default_responses()
    responses[TurnDecision] = [{"score": None, "question": _question(0), "is_followup": False}] + [
        {
            "score": {"dimensions": {"系统设计": 3}, "overall": 3, "evidence": "原文", "comment": "尚可"},
            "question": _question(i + 1),
            "is_followup": False,
        }
        for i in range(questions)
    ]
    responses[FinalReport] = {
        "overall_score": 3.0,
        "dimensions": {"系统设计": 3.0},
        "verdict": "基本达标",
        "strengths": ["表达有结构"],
        "improvements": ["缺少量化"],
        "action_plan": ["准备三个项目故事", "补齐性能指标", "练习追问场景"],
        "sample_answer": "按 STAR 结构回答，先讲背景再讲结果。",
    }
    return FakeLLM(responses)


def _question(index: int) -> dict:
    return {
        "text": f"第 {index} 个问题：讲讲你的项目",
        "competency": "系统设计",
        "rubric": {"criteria": ["讲到背景", "讲到结果"], "good_looks_like": "有量化结果"},
        "followup_hint": "追问一下数据来源",
    }


@pytest.fixture
def fake_llm() -> FakeLLM:
    return build_fake_llm()


@pytest.fixture
def resume_text() -> str:
    return RESUME_TEXT


@pytest.fixture
def jd_text() -> str:
    return JD_TEXT
