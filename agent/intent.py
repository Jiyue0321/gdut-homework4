"""作答意图判定：把「系统反馈 / 测试吐槽 / 误触」从真实面试回答里挑出来。

不调用大模型，纯规则判断，零延迟、可测试。命中时面试流程不推进、不打分，
而是把输入退回给用户重填，避免把「这个报错是大模型格式异常」当成跑题作答打 0 分。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 明显在描述系统/工具异常，而不是回答面试问题。
_FEEDBACK_KEYWORDS = (
    "报错", "错误信息", "堆栈", "异常", "崩溃", "卡住", "卡死", "转圈", "打不开",
    "bug", "debug", "测试一下", "测试模式", "系统坏了", "系统问题", "页面崩溃",
    "jsondecodeerror", "invalid json", "eof while parsing", "traceback", "api key",
    "接口报错", "模型输出", "大模型", "解析失败", "格式异常", "超时了",
)

# 整句在说自己/系统状态，而不是在作答。
_FEEDBACK_PATTERNS = (
    re.compile(r"^\s*(测试|test)\s*[0-9一二三四五六七八九十]*\s*$", re.I),
    re.compile(r"(这是|这个|刚才|上面).{0,6}(报错|异常|错误|bug)", re.I),
    re.compile(r"(系统|页面|界面|程序).{0,6}(报错|崩|卡|异常|问题)", re.I),
)

MIN_ANSWER_CHARS = 8


@dataclass(frozen=True)
class IntentVerdict:
    """``valid=False`` 时 ``message`` 是给用户看的中文提示。"""

    valid: bool
    message: str = ""


def check_answer(text: str, *, min_chars: int = 0) -> IntentVerdict:
    """判定一段输入是否是可评分的面试回答。

    ``min_chars`` 只在界面层传非零值，用于最短字数校验；
    编排层调用时不限制长度，避免把简短的合理回答误拒。
    """
    answer = (text or "").strip()
    if not answer:
        return IntentVerdict(False, "回答不能为空。")
    if min_chars and len(answer) < min_chars:
        return IntentVerdict(False, f"回答太短（少于 {min_chars} 个字），请展开说明后再提交。")

    lowered = answer.lower()
    hits = [kw for kw in _FEEDBACK_KEYWORDS if kw.lower() in lowered]
    if len(hits) >= 2:
        return IntentVerdict(
            False,
            "这段内容像是在反馈系统问题而不是回答问题。本系统只会给你的面试回答打分；"
            "如果遇到报错，请截图反馈，并重新作答。",
        )
    if any(pattern.search(answer) for pattern in _FEEDBACK_PATTERNS):
        return IntentVerdict(
            False, "这段内容看起来不是面试回答，请针对当前问题给出你的回答。"
        )
    return IntentVerdict(True)
