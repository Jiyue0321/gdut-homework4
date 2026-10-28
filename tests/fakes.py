"""脚本化假模型：按 schema 类型返回预置数据，避免测试依赖真实 API。"""

from __future__ import annotations

from typing import Any

from agent.state import (
    AnswerScore,
    Competency,
    CompetencyModel,
    Question,
    ResumeProfile,
    Rubric,
    TurnDecision,
)


class FakeLLM:
    """实现了 ``chat_json`` 的假客户端。

    ``responses`` 是 schema 类型到数据（模型或 dict）的映射；
    调用计数便于断言「每轮只调用一次模型」。
    """

    def __init__(self, responses: dict[type, Any] | None = None) -> None:
        self.responses = responses or default_responses()
        self.calls: list[tuple[type, list[dict[str, Any]], dict[str, Any]]] = []

    def chat_json(self, messages, schema, **kwargs):
        self.calls.append((schema, messages, kwargs))
        payload = self.responses[schema]
        if isinstance(payload, list):
            payload = payload.pop(0) if len(payload) > 1 else payload[0]
        if isinstance(payload, BaseException):
            raise payload
        if isinstance(payload, schema):
            return payload
        return schema.model_validate(payload)


def default_responses() -> dict[type, Any]:
    score = {
        "dimensions": {"系统设计": 3},
        "overall": 3,
        "evidence": "用了唯一索引",
        "comment": "讲到关键点",
    }
    question = {
        "text": "讲讲你订单模块里怎么防止重复下单？",
        "competency": "系统设计",
        "rubric": {"criteria": ["讲到幂等键", "讲到并发场景"], "good_looks_like": "有具体方案与取舍"},
        "followup_hint": "如果只提数据库唯一索引，追问高并发下的性能",
    }
    return {
        ResumeProfile: {
            "summary": "软件工程本科生，做过订单模块",
            "skills": ["Python", "FastAPI"],
            "projects": ["校园二手交易平台"],
            "highlights": ["接口耗时从 800ms 降到 120ms"],
            "concerns": ["项目团队规模未提及"],
        },
        CompetencyModel: {
            "role_title": "后端开发实习生",
            "competencies": [
                {"name": "系统设计", "weight": 2, "required_level": 4, "resume_level": 2},
                {"name": "技术深度", "weight": 1, "required_level": 4, "resume_level": 3},
                {"name": "沟通表达", "weight": 1, "required_level": 3, "resume_level": 3},
            ],
        },
        TurnDecision: [{"score": None, "question": question, "is_followup": False}]
        + [{"score": score, "question": question, "is_followup": False}],
        AnswerScore: score,
    }


def make_score(overall: int, competency: str = "系统设计") -> AnswerScore:
    return AnswerScore(
        dimensions={competency: overall}, overall=overall, evidence="原文", comment="评语"
    )


def make_question(text: str = "问题", competency: str = "系统设计") -> Question:
    return Question(
        text=text,
        competency=competency,
        rubric=Rubric(criteria=["要点"], good_looks_like="优秀"),
    )


def make_competency(name: str, weight: float = 1.0, req: int = 4, res: int = 2) -> Competency:
    return Competency(name=name, weight=weight, required_level=req, resume_level=res)
