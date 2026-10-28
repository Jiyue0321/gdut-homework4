"""评估智能体：交叉拷问时从各自视角给同一答案打分。"""

from __future__ import annotations

from typing import Any

from agent.agents.resume import ChatClient
from agent.prompts import CROSS_EXAM, EVALUATOR
from agent.state import AGENT_LABELS, AnswerScore, Question

LENSES = {
    "hr": "动机是否真实、表达是否清楚、是否在绕开问题",
    "tech": "技术细节是否站得住、有没有量化依据、方案是否有取舍",
    "pressure": "面对压力是否回避、是否推诿责任、论据能否自洽",
}


def build_cross_exam_messages(agent: str, question: str, answer: str) -> list[dict[str, Any]]:
    return [
        {
            "role": "user",
            "content": CROSS_EXAM.format(
                label=AGENT_LABELS[agent],
                question=question,
                answer=answer,
                lens=LENSES[agent],
            ),
        }
    ]


def cross_exam(client: ChatClient, agent: str, question: str, answer: str) -> AnswerScore:
    return client.chat_json(
        build_cross_exam_messages(agent, question, answer),
        AnswerScore,
        temperature=0.2,
        max_tokens=500,
    )


def build_messages(question: Question, answer: str) -> list[dict[str, Any]]:
    return [
        {
            "role": "user",
            "content": EVALUATOR.format(
                question=question.text,
                criteria="；".join(question.rubric.criteria),
                good_looks_like=question.rubric.good_looks_like,
                answer=answer,
            ),
        }
    ]


def evaluate(client: ChatClient, question: Question, answer: str) -> AnswerScore:
    return client.chat_json(
        build_messages(question, answer), AnswerScore, temperature=0.2, max_tokens=500
    )
