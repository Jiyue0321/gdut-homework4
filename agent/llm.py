"""大模型调用封装：结构化 JSON 输出 + 校验重试。"""

from __future__ import annotations

import json
from typing import Any, TypeVar

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from agent.config import LLMConfig

ModelT = TypeVar("ModelT", bound=BaseModel)

JSON_ONLY_RULE = "\n\n只输出一个 JSON 对象，不要 markdown 代码块，不要任何解释文字。"


class LLMError(RuntimeError):
    """大模型调用或输出解析失败。"""


class LLMClient:
    """OpenAI 兼容接口的薄封装。

    用法::

        client = LLMClient(config)
        profile = client.chat_json(messages, ResumeProfile, temperature=0.2)
    """

    def __init__(self, config: LLMConfig, *, timeout: float = 60.0) -> None:
        if not config.configured:
            raise LLMError("未配置大模型：请复制 .env.example 为 .env 并填写 API Key")
        self._config = config
        self._client = OpenAI(
            base_url=config.base_url, api_key=config.api_key, timeout=timeout
        )

    def chat_json(
        self,
        messages: list[dict[str, Any]],
        schema: type[ModelT],
        *,
        temperature: float = 0.2,
        max_tokens: int = 900,
    ) -> ModelT:
        """要求模型返回 JSON，并用 pydantic 模型校验。

        失败时分两步重试：第一次把校验错误回喂给模型，第二次用原始提示重试。
        """
        convo = _with_schema_rules(messages, schema)
        last_error: Exception | None = None

        for attempt in range(2):
            try:
                content = self._complete(convo, temperature=temperature, max_tokens=max_tokens)
            except Exception as exc:
                last_error = exc
                continue

            try:
                return schema.model_validate_json(_strip_fence(content))
            except (ValidationError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt == 0:
                    convo = convo + [
                        {"role": "assistant", "content": content},
                        {
                            "role": "user",
                            "content": f"上一次输出不合法：{_brief_error(exc)}。请严格按要求重新输出 JSON。",
                        },
                    ]

        raise LLMError(f"大模型调用失败：{last_error}")

    def _complete(
        self, messages: list[dict[str, Any]], *, temperature: float, max_tokens: int
    ) -> str:
        response = self._client.chat.completions.create(
            model=self._config.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or ""


def _with_schema_rules(
    messages: list[dict[str, Any]], schema: type[BaseModel]
) -> list[dict[str, Any]]:
    """把输出结构要求追加到 system 消息末尾（没有 system 就补一条）。"""
    rule = JSON_ONLY_RULE + "\n字段结构：" + _schema_hint(schema)
    convo = [dict(m) for m in messages]
    if convo and convo[0].get("role") == "system":
        convo[0]["content"] = str(convo[0].get("content", "")) + rule
    else:
        convo.insert(0, {"role": "system", "content": rule.strip()})
    return convo


def _strip_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    return cleaned.strip()


def _schema_hint(schema: type[BaseModel]) -> str:
    props = schema.model_json_schema()
    return json.dumps(props, ensure_ascii=False)[:1500]


def _brief_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:3])
    return str(exc)[:200]
