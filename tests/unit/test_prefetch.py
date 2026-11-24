"""预取出题的单元测试：提前生成、命中复用、过期作废、失败降级。"""

from __future__ import annotations

import threading
import time

from agent.orchestrator import InterviewConfig, Orchestrator
from agent.state import Question, TurnDecision
from agent.tools import LocalTools
from tests.conftest import JD_TEXT, RESUME_TEXT, build_fake_llm

ANSWER = "我用唯一索引保证幂等，压测 QPS 从 200 提到 900。"


def make_orchestrator(llm, config: InterviewConfig | None = None) -> Orchestrator:
    return Orchestrator(llm, LocalTools(), config or InterviewConfig())


def _question_calls(llm) -> int:
    return sum(1 for call in llm.calls if call[0] is Question)


def test_start_prefetches_next_question():
    """开场出第一题后，应立即在后台预取第二题。"""
    orchestrator = make_orchestrator(build_fake_llm())
    session = orchestrator.start(RESUME_TEXT, JD_TEXT, "后端开发实习生")
    assert session.prefetched is not None
    index, future = session.prefetched
    assert index == session.slot_index
    slot, question = future.result(timeout=5)  # 预取必须能正常完成
    assert slot is not None and question is not None


def test_prefetched_question_belongs_to_next_slot():
    """预取的是下一槽位的题，不能把当前题又发一遍。"""
    orchestrator = make_orchestrator(build_fake_llm())
    session = orchestrator.start(RESUME_TEXT, JD_TEXT, "后端开发实习生")
    first = session.current_question.text
    _, future = session.prefetched
    slot, question = future.result(timeout=5)
    assert slot is session.plan.slots[1]
    assert question.text != first


def test_answer_consumes_prefetched_question():
    """预取命中时直接采用预取结果，不再为同一槽位重复出题。"""
    llm = build_fake_llm()
    orchestrator = make_orchestrator(llm)
    session = orchestrator.start(RESUME_TEXT, JD_TEXT, "后端开发实习生")
    _, future = session.prefetched
    slot, expected = future.result(timeout=5)  # 模拟用户读完题再作答

    session = orchestrator.answer(session, ANSWER)
    assert session.error == ""
    assert session.current_agent == slot.agent
    assert session.current_question.text == expected.text
    assert session.prefetched is None or session.prefetched[0] == session.slot_index


def test_prefetch_snapshot_survives_slot_advance():
    """预取参数在提交时固定：即便槽位随后推进，也算不出错题。"""
    orchestrator = make_orchestrator(build_fake_llm())
    session = orchestrator.start(RESUME_TEXT, JD_TEXT, "岗位")
    _, future = session.prefetched
    expected_slot = session.plan.slots[1]

    # 模拟预取线程还没跑起来，槽位就被推进了
    session.slot_index = 3
    slot, _ = future.result(timeout=5)
    assert slot is expected_slot, "预取应针对提交那一刻的下一个槽位，而不是运行时的 slot_index"


def test_last_question_does_not_prefetch():
    """最后一题没有下一题可预取。"""
    orchestrator = make_orchestrator(build_fake_llm(), InterviewConfig(max_questions=3))
    session = orchestrator.start(RESUME_TEXT, JD_TEXT, "岗位")
    for _ in range(2):
        session = orchestrator.answer(session, ANSWER)
    assert session.slot_index == len(session.plan.slots) - 1
    assert session.prefetched is None


def test_stale_prefetch_discarded_after_followup():
    """追问时槽位不动，但预取针对的是旧槽位的后一题，必须重新发起。"""
    llm = build_fake_llm()
    llm.responses[Question] = [
        {"text": "第一题：讲讲订单模块", "competency": "系统设计",
         "rubric": {"criteria": ["a"], "good_looks_like": "b"}},
        {"text": "预取的第二题：压测怎么做的", "competency": "系统设计",
         "rubric": {"criteria": ["a"], "good_looks_like": "b"}},
        {"text": "追随后重新出的题", "competency": "系统设计",
         "rubric": {"criteria": ["a"], "good_looks_like": "b"}},
    ]
    llm.responses[TurnDecision] = {
        "score": {"dimensions": {"系统设计": 2}, "overall": 2, "evidence": "e", "comment": "含糊"},
        "question": {
            "text": "追问：基线是多少", "competency": "系统设计",
            "rubric": {"criteria": ["a"], "good_looks_like": "b"},
        },
        "is_followup": True,
    }
    orchestrator = make_orchestrator(llm)
    session = orchestrator.start(RESUME_TEXT, JD_TEXT, "岗位")
    session.prefetched[1].result(timeout=5)

    session = orchestrator.answer(session, "含糊回答")
    assert session.followup_used
    assert "追问" in session.current_question.text
    # 槽位没动，预取应针对同一槽位重新发起，而不是继续沿用旧结果。
    assert session.prefetched is None or session.prefetched[0] == session.slot_index


def test_prefetch_failure_falls_back_to_sync_generation():
    """预取抛异常时不能让面试卡住，应回退为同步出题。"""

    class FailsOnceOnPrefetch:
        """预取线程里第一次出题抛错，其余调用正常。"""

        def __init__(self) -> None:
            self._inner = build_fake_llm()
            self._failed = False
            self._lock = threading.Lock()

        def chat_json(self, messages, schema, **kwargs):
            if schema is Question and threading.current_thread().name.startswith("prefetch"):
                with self._lock:
                    if not self._failed:
                        self._failed = True
                        raise RuntimeError("预取失败")
            return self._inner.chat_json(messages, schema, **kwargs)

    orchestrator = make_orchestrator(FailsOnceOnPrefetch())
    session = orchestrator.start(RESUME_TEXT, JD_TEXT, "岗位")
    time.sleep(0.05)  # 让预取线程把异常抛出
    session = orchestrator.answer(session, ANSWER)
    assert session.error == ""
    assert session.current_question is not None
