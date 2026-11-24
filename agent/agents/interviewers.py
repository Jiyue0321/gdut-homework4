"""三类面试官智能体。

打分与出题拆成两次独立调用，编排器并行发起：合并成一次调用时模型要同时产出
评分和题目（约 1400 token），单题 5–9 秒；拆开后各约 130 / 250 token，
并行后单题耗时约等于其中较慢的一次，且两部分提示互不干扰、各自可单独调优。
"""

from __future__ import annotations

import json
from typing import Any, Sequence

from agent.agents.resume import ChatClient
from agent.prompts import INTERVIEWER_CONTEXT, INTERVIEWER_QUESTION_RULES, INTERVIEWER_SCORE_RULES
from agent.state import AGENT_LABELS, Question, ResumeProfile, Slot, TurnDecision

RECENT_TURNS = 2

# 打分只输出一个分数对象，给足几百 token 即可；出题要带 rubric，留出余量。
SCORE_MAX_TOKENS = 600
QUESTION_MAX_TOKENS = 900


def _context(
    slot: Slot,
    profile: ResumeProfile,
    role_title: str,
    *,
    industry: str,
    bank_questions: Sequence[str],
    asked_questions: Sequence[str],
) -> str:
    """两位调用共用的事实上下文：简历摘要、考察点、已问题目、参考题。"""
    return INTERVIEWER_CONTEXT.format(
        label=AGENT_LABELS[slot.agent],
        focus=slot.focus,
        competency=slot.competency,
        role_title=role_title,
        industry=industry or "通用",
        summary=profile.summary,
        highlights="；".join(profile.highlights) or "（无）",
        concerns="；".join(profile.concerns) or "（无）",
        asked="\n".join(f"- {text}" for text in asked_questions) or "- （暂无）",
        bank_hints="\n".join(f"- {text}" for text in bank_questions) or "- （无，自行设计问题）",
    )


def _score_context(
    slot: Slot, profile: ResumeProfile, role_title: str, *, industry: str
) -> str:
    """打分只需要考察点与岗位，参考题与已问题目对判分没有帮助，不进提示省 token。"""
    return INTERVIEWER_CONTEXT.format(
        label=AGENT_LABELS[slot.agent],
        focus=slot.focus,
        competency=slot.competency,
        role_title=role_title,
        industry=industry or "通用",
        summary=profile.summary,
        highlights="；".join(profile.highlights) or "（无）",
        concerns="；".join(profile.concerns) or "（无）",
        asked="- （打分无需参考）",
        bank_hints="- （打分无需参考）",
    )


def build_score_messages(
    slot: Slot,
    profile: ResumeProfile,
    role_title: str,
    *,
    last_question: str,
    last_answer: str,
    rubric: list[str] | None = None,
    industry: str = "通用",
    bank_questions: Sequence[str] = (),
    asked_questions: Sequence[str] = (),
) -> list[dict[str, Any]]:
    system = "\n".join(
        [
            _score_context(slot, profile, role_title, industry=industry),
            INTERVIEWER_SCORE_RULES,
        ]
    )
    criteria = "；".join(rubric or []) or "（未提供评分要点，按问题本身判断答到与否）"
    user = (
        f"上一题：{last_question}\n"
        f"本题评分要点：{criteria}\n"
        f"候选人回答：{last_answer}\n\n"
        "请输出评分结果。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_question_messages(
    slot: Slot,
    profile: ResumeProfile,
    role_title: str,
    *,
    industry: str = "通用",
    bank_questions: Sequence[str] = (),
    asked_questions: Sequence[str] = (),
    avoid_questions: Sequence[str] = (),
) -> list[dict[str, Any]]:
    parts = [
        _context(
            slot,
            profile,
            role_title,
            industry=industry,
            bank_questions=bank_questions,
            asked_questions=asked_questions,
        ),
        INTERVIEWER_QUESTION_RULES,
    ]
    if avoid_questions:
        parts.append(
            "刚才的题目重复了，不要输出这类问题："
            + "；".join(f"「{text}」" for text in avoid_questions)
        )
    return [
        {"role": "system", "content": "\n".join(parts)},
        {"role": "user", "content": "请出下一道题。"},
    ]


def score(
    client: ChatClient,
    slot: Slot,
    profile: ResumeProfile,
    role_title: str,
    *,
    last_question: str,
    last_answer: str,
    rubric: list[str] | None = None,
    industry: str = "通用",
    bank_questions: Sequence[str] = (),
    asked_questions: Sequence[str] = (),
) -> TurnDecision:
    """给上一题打分；作答含糊时同时返回一道追问。"""
    decision = client.chat_json(
        build_score_messages(
            slot,
            profile,
            role_title,
            last_question=last_question,
            last_answer=last_answer,
            rubric=rubric,
            industry=industry,
            bank_questions=bank_questions,
            asked_questions=asked_questions,
        ),
        TurnDecision,
        temperature=0.2,
        max_tokens=SCORE_MAX_TOKENS,
    )
    return _sanitize_score(decision)


def next_question(
    client: ChatClient,
    slot: Slot,
    profile: ResumeProfile,
    role_title: str,
    *,
    industry: str = "通用",
    bank_questions: Sequence[str] = (),
    asked_questions: Sequence[str] = (),
    avoid_questions: Sequence[str] = (),
) -> Question:
    """单独生成一道新题。"""
    return client.chat_json(
        build_question_messages(
            slot,
            profile,
            role_title,
            industry=industry,
            bank_questions=bank_questions,
            asked_questions=asked_questions,
            avoid_questions=avoid_questions,
        ),
        Question,
        temperature=0.7,
        max_tokens=QUESTION_MAX_TOKENS,
    )


def _sanitize_score(decision: TurnDecision) -> TurnDecision:
    """模型可能在不需要追问时仍塞一道题：没有 is_followup 就丢弃，避免污染下一槽位。"""
    if not decision.is_followup:
        return TurnDecision(score=decision.score, question=None, is_followup=False)
    return decision


def build_messages(
    slot: Slot,
    profile: ResumeProfile,
    role_title: str,
    *,
    last_question: str | None = None,
    last_answer: str | None = None,
    is_last_slot: bool = False,
    industry: str = "通用",
    bank_questions: Sequence[str] = (),
    asked_questions: Sequence[str] = (),
    avoid_questions: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """兼容入口：有上一轮回答时构造打分提示，否则构造出题提示。"""
    if last_question and last_answer:
        return build_score_messages(
            slot,
            profile,
            role_title,
            last_question=last_question,
            last_answer=last_answer,
            industry=industry,
            bank_questions=bank_questions,
            asked_questions=asked_questions,
        )
    return build_question_messages(
        slot,
        profile,
        role_title,
        industry=industry,
        bank_questions=bank_questions,
        asked_questions=asked_questions,
        avoid_questions=avoid_questions,
    )


def ask(
    client: ChatClient,
    slot: Slot,
    profile: ResumeProfile,
    role_title: str,
    *,
    last_question: str | None = None,
    last_answer: str | None = None,
    is_last_slot: bool = False,
    industry: str = "通用",
    bank_questions: Sequence[str] = (),
    asked_questions: Sequence[str] = (),
    avoid_questions: Sequence[str] = (),
) -> TurnDecision:
    """出题或打分的统一入口，保留给一次性调用（首题、追问、测试）。"""
    if last_question and last_answer:
        decision = score(
            client,
            slot,
            profile,
            role_title,
            last_question=last_question,
            last_answer=last_answer,
            industry=industry,
            bank_questions=bank_questions,
            asked_questions=asked_questions,
        )
        if is_last_slot:
            decision = TurnDecision(score=decision.score, question=None, is_followup=False)
        return decision
    question = next_question(
        client,
        slot,
        profile,
        role_title,
        industry=industry,
        bank_questions=bank_questions,
        asked_questions=asked_questions,
        avoid_questions=avoid_questions,
    )
    return TurnDecision(question=question, is_followup=False)


__all__ = [
    "ask",
    "build_messages",
    "build_question_messages",
    "build_score_messages",
    "next_question",
    "score",
]
