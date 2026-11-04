"""作答意图与输入校验的单元测试（BUG-03）。"""

from __future__ import annotations

import pytest

from agent.intent import check_answer


@pytest.mark.parametrize(
    "text",
    [
        "这个报错是典型的大模型输出格式异常，Invalid JSON: EOF while parsing",
        "测试一下，系统页面崩了，一直在转圈",
        "刚才那个 JSONDecodeError 堆栈是不是模型输出的问题",
    ],
)
def test_system_feedback_is_rejected(text):
    verdict = check_answer(text)
    assert not verdict.valid
    assert verdict.message


@pytest.mark.parametrize(
    "text",
    [
        "我用唯一索引保证幂等，压测 QPS 从 200 提到 900。",
        "团队里我负责订单模块，遇到重复下单问题，用幂等键解决。",
        "这个项目从需求到上线都参与，接口耗时降到了 120 毫秒。",
        "含 bug 这个词但只有一个关键词的回答仍然算有效回答",
    ],
)
def test_real_answer_is_accepted(text):
    assert check_answer(text).valid


def test_empty_and_too_short_answers_are_rejected():
    assert not check_answer("").valid
    assert not check_answer("   ").valid
    # 最短字数仅在显式要求时生效
    assert check_answer("回答", min_chars=8).valid is False
    assert check_answer("回答", min_chars=0).valid is True


def test_bare_test_keyword_is_rejected():
    assert not check_answer("测试").valid
    assert not check_answer("test 2").valid
