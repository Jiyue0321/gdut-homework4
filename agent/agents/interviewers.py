"""三类面试官智能体：一次调用完成「给上一题打分 + 出下一题」。"""

from __future__ import annotations

import json
from typing import Any

from agent.agents.resume import ChatClient
from agent.prompts import INTERVIEWER
from agent.state import AGENT_LABELS, AnswerScore, ResumeProfile, Slot, TurnDecision

RECENT_TURNS = 2


def build_messages(
    slot: Slot,
    profile: ResumeProfile,
    role_title: str,
    *,
    last_question: str | None = None,
    last_answer: str | None = None,
    is_last_slot: bool = False,
) -> list[dict[str, Any]]:
    """面试官提示：只带最近一轮问答与当前考察点，避免长篇简历反复计费。"""
    system = INTERVIEWER.format(
        label=AGENT_LABELS[slot.agent],
        focus=slot.focus,
        competency=slot.competency,
        role_title=role_title,
        summary=profile.summary,
        highlights="；".join(profile.highlights) or "（无）",
        concerns="；".join(profile.concerns) or "（无）",
    )
    tasks = [
        "本次输出包含两部分：",
        "1. score：给上一题打分。若这是第一题，score 填 null。",
        "2. question：下一题。若这是最后一题，question 填 null。",
    ]
    if is_last_slot:
        tasks.append("这是最后一题，因此 question 必须为 null，并且要给上一个回答打分。")
    else:
        tasks.append("如果不是最后一题，必须给出 question。")

    history: list[str] = []
    if last_question and last_answer:
        history.append(f"上一题：{last_question}")
        history.append(f"候选人回答：{last_answer}")
    else:
        history.append("这是面试第一题，还没有候选人回答。")

    content = "\n".join([system, "", *tasks, "", *history])
    return [
        {"role": "system", "content": content},
        {"role": "user", "content": json.dumps(_output_skeleton(), ensure_ascii=False)},
    ]


def _output_skeleton() -> dict[str, Any]:
    return {
        "score": {"dimensions": {"能力名": 0}, "overall": 0, "evidence": "原文摘抄", "comment": "评语"},
        "question": {
            "text": "问题",
            "competency": "能力名",
            "rubric": {"criteria": ["要点1"], "good_looks_like": "优秀回答特征"},
            "followup_hint": "",
        },
        "is_followup": False,
    }


def ask(
    client: ChatClient,
    slot: Slot,
    profile: ResumeProfile,
    role_title: str,
    *,
    last_question: str | None = None,
    last_answer: str | None = None,
    is_last_slot: bool = False,
) -> TurnDecision:
    decision = client.chat_json(
        build_messages(
            slot,
            profile,
            role_title,
            last_question=last_question,
            last_answer=last_answer,
            is_last_slot=is_last_slot,
        ),
        TurnDecision,
        temperature=0.7,
        max_tokens=900,
    )
    return _sanitize(decision, has_previous=bool(last_answer), is_last_slot=is_last_slot)


def _sanitize(decision: TurnDecision, *, has_previous: bool, is_last_slot: bool) -> TurnDecision:
    """兜住模型的自相矛盾：第一题不该有分，最后一题不该再来一题。"""
    score: AnswerScore | None = decision.score
    question = decision.question
    if not has_previous:
        score = None
    if is_last_slot:
        question = None
    return TurnDecision(score=score, question=question, is_followup=decision.is_followup if question else False)
