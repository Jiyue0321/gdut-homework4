"""面试编排器：确定性状态机，掌握阶段、题量、追问与评分聚合。

智能体的自主性限于「问什么、怎么追问」，流程边界由代码保证可复现、可测试。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from agent.agents import evaluator, interviewers, jd, report, resume
from agent.mcp_client import ToolError
from agent.state import (
    AGENT_LABELS,
    AgentName,
    AnswerScore,
    CompetencyModel,
    CrossExam,
    InterviewPlan,
    Phase,
    Question,
    ResumeProfile,
    Slot,
    Turn,
    TurnDecision,
)


@dataclass(frozen=True)
class InterviewConfig:
    max_questions: int = 6
    allow_followups: bool = True
    run_cross_exam: bool = True

    @property
    def agent_cycle(self) -> tuple[AgentName, ...]:
        return ("hr", "tech", "pressure")


@dataclass
class InterviewSession:
    """一次面试的全部状态，可序列化后放进 Streamlit session_state。"""

    phase: Phase = Phase.IDLE
    resume_text: str = ""
    jd_text: str = ""
    role_title: str = ""
    profile: ResumeProfile | None = None
    competency_model: CompetencyModel | None = None
    radar: list[dict[str, Any]] = field(default_factory=list)
    gaps: list[dict[str, Any]] = field(default_factory=list)
    plan: InterviewPlan | None = None
    slot_index: int = 0
    current_question: Question | None = None
    current_agent: AgentName = "hr"
    turns: list[Turn] = field(default_factory=list)
    cross_exam: CrossExam | None = None
    report_data: dict[str, Any] = field(default_factory=dict)
    narrative: dict[str, Any] = field(default_factory=dict)
    followup_used: bool = False
    error: str = ""

    @property
    def finished(self) -> bool:
        return self.phase in {Phase.REPORT, Phase.DONE}

    @property
    def qa_pairs(self) -> list[dict[str, Any]]:
        return [
            {
                "index": i,
                "agent": t.agent,
                "agent_label": AGENT_LABELS[t.agent],
                "question": t.question,
                "answer": t.answer,
                "overall": t.score.overall,
                "competency": self._competency_of(t),
                "comment": t.score.comment,
                "evidence": t.score.evidence,
                "is_followup": t.is_followup,
            }
            for i, t in enumerate(self.turns)
        ]

    def _competency_of(self, turn: Turn) -> str:
        if self.plan and 0 <= turn.slot_index < len(self.plan.slots):
            return self.plan.slots[turn.slot_index].competency
        return ""

    def turn_records(self) -> list[dict[str, Any]]:
        return [
            {
                "competency": self._competency_of(t),
                "score": t.score.overall,
                "dimensions": t.score.dimensions,
            }
            for t in self.turns
        ]

    def weights(self) -> dict[str, float]:
        if not self.competency_model:
            return {}
        return {c.name: c.weight for c in self.competency_model.competencies}


class ChatProvider(Protocol):
    def chat_json(self, messages: Any, schema: Any, **kwargs: Any) -> Any: ...


class Tools(Protocol):
    def check_resume_quality(self, text: str) -> dict[str, Any]: ...
    def match_competencies(self, competencies: Sequence[Mapping[str, Any]]) -> dict[str, Any]: ...
    def aggregate_scores(self, turns: Any, weights: Any) -> dict[str, Any]: ...
    def merge_cross_exam(self, scores: Sequence[float]) -> dict[str, Any]: ...


class Orchestrator:
    """驱动一次面试的状态机。模式::

        session = Orchestrator(client, tools).start(resume, jd, role, config)
        question = session.current_question
        session = Orchestrator(client, tools).answer(session, "候选人回答")
    """

    def __init__(self, llm: ChatProvider, tools: Tools, config: InterviewConfig | None = None) -> None:
        self._llm = llm
        self._tools = tools
        self._config = config or InterviewConfig()

    # ---------- 入口 ----------

    def start(self, resume_text: str, jd_text: str, role_title: str) -> InterviewSession:
        session = InterviewSession(
            resume_text=resume_text.strip(),
            jd_text=jd_text.strip(),
            role_title=role_title.strip() or "目标岗位",
        )
        try:
            session.phase = Phase.PARSE_RESUME
            quality = self._tools.check_resume_quality(session.resume_text)
            session.profile = resume.analyze_resume(self._llm, session.resume_text, quality)

            session.phase = Phase.ANALYZE_JD
            session.competency_model = jd.analyze_jd(
                self._llm, session.jd_text, session.role_title, session.profile
            )

            session.phase = Phase.PLAN
            match = self._tools.match_competencies(
                [c.model_dump() for c in session.competency_model.competencies]
            )
            session.radar = match.get("radar", [])
            session.gaps = match.get("gaps", [])
            session.plan = self._build_plan(session)

            session.phase = Phase.INTERVIEW
            self._ask_next_question(session)
        except Exception as exc:  # 面向用户的中文错误
            session.error = _friendly_error(exc)
            session.phase = Phase.IDLE
        return session

    def answer(self, session: InterviewSession, answer_text: str) -> InterviewSession:
        """提交一次回答，推进到下一题或进入下一阶段。"""
        if session.current_question is None:
            session.error = "当前没有待回答的问题"
            return session

        session.error = ""
        try:
            slot = self._current_slot(session)
            last_slot = self._is_last_slot(session)
            decision = interviewers.ask(
                self._llm,
                slot,
                session.profile,  # type: ignore[arg-type]
                session.role_title,
                last_question=session.current_question.text,
                last_answer=answer_text.strip(),
                is_last_slot=last_slot,
            )
            score = decision.score or evaluator.evaluate(
                self._llm, session.current_question, answer_text.strip()
            )

            session.turns.append(
                Turn(
                    slot_index=session.slot_index,
                    agent=session.current_agent,
                    question=session.current_question.text,
                    answer=answer_text.strip(),
                    score=score,
                    is_followup=session.followup_used,
                )
            )

            if self._should_followup(session, decision):
                session.followup_used = True
                session.current_question = _followup_question(session.current_question, decision)
                return session

            session.followup_used = False
            session.slot_index += 1
            if session.slot_index >= len(session.plan.slots):  # type: ignore[union-attr]
                self._finish(session)
            else:
                self._ask_next_question(session)
        except Exception as exc:
            session.error = _friendly_error(exc)
        return session

    # ---------- 内部 ----------

    def _build_plan(self, session: InterviewSession) -> InterviewPlan:
        assert session.competency_model is not None
        ranked = sorted(
            session.competency_model.competencies,
            key=lambda c: (c.required_level - c.resume_level, c.weight),
            reverse=True,
        )
        count = max(3, min(self._config.max_questions, len(ranked) * 2))
        slots: list[Slot] = []
        cycle = self._config.agent_cycle
        for position in range(count):
            competency = ranked[position % len(ranked)]
            agent = cycle[position % len(cycle)]
            slots.append(
                Slot(
                    agent=agent,
                    competency=competency.name,
                    focus=_focus_for(agent, competency.name, position),
                )
            )
        return InterviewPlan(slots=slots)

    def _current_slot(self, session: InterviewSession) -> Slot:
        assert session.plan is not None
        return session.plan.slots[session.slot_index]

    def _is_last_slot(self, session: InterviewSession) -> bool:
        assert session.plan is not None
        return session.slot_index >= len(session.plan.slots) - 1

    def _ask_next_question(self, session: InterviewSession) -> None:
        slot = self._current_slot(session)
        session.current_agent = slot.agent
        decision = interviewers.ask(
            self._llm,
            slot,
            session.profile,  # type: ignore[arg-type]
            session.role_title,
        )
        if decision.question is None:
            session.error = "面试官没有给出问题，请重试"
            return
        session.current_question = decision.question

    def _should_followup(self, session: InterviewSession, decision: TurnDecision) -> bool:
        if not self._config.allow_followups or session.followup_used:
            return False
        if not decision.is_followup or decision.question is None:
            return False
        return True

    def _finish(self, session: InterviewSession) -> None:
        session.current_question = None
        if self._config.run_cross_exam and session.turns:
            session.phase = Phase.CROSS_EXAM
            self._run_cross_exam(session)
        self._evaluate_and_report(session)

    def _run_cross_exam(self, session: InterviewSession) -> None:
        """挑得分最低的一题，让三位面试官分别从各自视角打分，取中位数。"""
        worst_index = min(range(len(session.turns)), key=lambda i: session.turns[i].score.overall)
        worst = session.turns[worst_index]
        scores: dict[str, AnswerScore] = {}
        for agent in ("hr", "tech", "pressure"):
            scores[agent] = evaluator.cross_exam(self._llm, agent, worst.question, worst.answer)
        merged_value = self._tools.merge_cross_exam(
            [scores[a].overall for a in ("hr", "tech", "pressure")]
        )["merged"]
        merged = AnswerScore(
            dimensions={"交叉拷问": int(round(merged_value))},
            overall=int(round(merged_value)),
            evidence=worst.score.evidence,
            comment="；".join(
                f"{AGENT_LABELS[a]}：{scores[a].comment}" for a in ("hr", "tech", "pressure")
            ),
        )
        session.cross_exam = CrossExam(
            turn_index=worst_index, question=worst.question, scores=scores, merged=merged
        )
        session.turns[worst_index] = worst.model_copy(
            update={"score": worst.score.model_copy(update={"overall": merged.overall})}
        )

    def _evaluate_and_report(self, session: InterviewSession) -> None:
        session.phase = Phase.EVALUATE
        aggregate = self._tools.aggregate_scores(session.turn_records(), session.weights())
        session.report_data = {
            "role_title": session.role_title,
            **aggregate,
            "turns": session.qa_pairs,
            "cross_exam": session.cross_exam.model_dump() if session.cross_exam else None,
        }

        session.phase = Phase.REPORT
        narrative = report.write_report(self._llm, session.report_data, session.qa_pairs)
        session.narrative = {
            "strengths": narrative.strengths,
            "improvements": narrative.improvements,
            "action_plan": narrative.action_plan,
            "sample_answer": narrative.sample_answer,
        }
        session.report_data.update(session.narrative)
        session.phase = Phase.DONE


def _focus_for(agent: AgentName, competency: str, position: int) -> str:
    if agent == "hr":
        return f"从候选人的真实动机与稳定性出发，考察「{competency}」"
    if agent == "tech":
        return f"结合简历中的项目细节深挖「{competency}」，要求给出取舍与依据"
    return f"用质疑与情境压力检验「{competency}」是否站得住"


def _followup_question(current: Question, decision: TurnDecision) -> Question:
    """把面试官给的追问包装成题目；没有新题就沿用追问线索。"""
    if decision.question is not None:
        return decision.question
    return current.model_copy(
        update={"text": current.followup_hint or f"请针对刚才的回答再补充细节：{current.text}"}
    )


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, ToolError):
        return f"工具服务出错：{exc}"
    text = str(exc)
    if "API key" in text or "Unauthorized" in text or "401" in text:
        return "大模型鉴权失败：请检查 API Key 是否正确、是否还有额度"
    if "timed out" in text.lower() or "timeout" in text.lower():
        return "大模型响应超时，请稍后重试"
    return f"出错了：{text[:200]}"
