"""简历分析智能体：简历文本 → 结构化事实。"""

from __future__ import annotations

from typing import Any, Protocol

from agent.prompts import RESUME_ANALYST
from agent.state import ResumeProfile


class ChatClient(Protocol):
    def chat_json(
        self, messages: list[dict[str, Any]], schema: Any, **kwargs: Any
    ) -> Any: ...


def build_messages(resume_text: str, quality: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """构造简历分析的提示。``quality`` 是确定性体检结果，作为额外线索提供给模型。"""
    parts = [RESUME_ANALYST, "\n简历原文：\n\"\"\"", resume_text.strip(), "\"\"\""]
    if quality:
        hints = quality.get("tips") or []
        if hints:
            parts.append("\n系统体检发现的格式问题（参考，不必全部写进 concerns）：\n- " + "\n- ".join(hints))
    return [{"role": "user", "content": "\n".join(parts)}]


def analyze_resume(
    client: ChatClient, resume_text: str, quality: dict[str, Any] | None = None
) -> ResumeProfile:
    return client.chat_json(
        build_messages(resume_text, quality), ResumeProfile, temperature=0.2, max_tokens=800
    )
