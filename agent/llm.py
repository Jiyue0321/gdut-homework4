"""大模型调用封装：结构化 JSON 输出 + 容错解析 + 校验重试。"""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from agent.config import LLMConfig

ModelT = TypeVar("ModelT", bound=BaseModel)

JSON_ONLY_RULE = "\n\n只输出一个 JSON 对象，不要 markdown 代码块，不要任何解释文字。"

# 模型偶尔会带着"好的，以下是评分……"这类前缀，或把 JSON 包在代码块里。
_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)(?:```|$)", re.S)


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
        max_tokens: int = 2048,
        frequency_penalty: float = 0.2,
        presence_penalty: float = 0.1,
    ) -> ModelT:
        """要求模型返回 JSON，并用 pydantic 模型校验。

        失败时分两步重试：第一次把校验错误回喂给模型，第二次用原始提示重试。
        每次解析前先做容错（剥离代码块/前缀、补全被截断的括号），
        避免一次输出不完美就让整个面试中断。
        """
        convo = _with_schema_rules(messages, schema)
        last_error: Exception | None = None

        for attempt in range(2):
            try:
                content = self._complete(
                    convo,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    frequency_penalty=frequency_penalty,
                    presence_penalty=presence_penalty,
                )
            except Exception as exc:
                last_error = exc
                continue

            try:
                return _parse_structured(content, schema)
            except (ValidationError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt == 0:
                    convo = convo + [
                        {"role": "assistant", "content": content},
                        {
                            "role": "user",
                            "content": f"上一次输出不合法：{_brief_error(exc)}。请严格按要求只输出一个完整 JSON 对象。",
                        },
                    ]

        raise LLMError(f"大模型调用失败：{last_error}")

    def _complete(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float,
        max_tokens: int,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
    ) -> str:
        response = self._client.chat.completions.create(
            model=self._config.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            response_format={"type": "json_object"},
            stream=False,
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


def _parse_structured(content: str, schema: type[ModelT]) -> ModelT:
    """从模型输出里稳妥地取出 JSON 并校验。

    依次尝试：直接解析 → 剥离代码块 → 截取首尾括号 → 补全被截断的结构。
    """
    for candidate in _json_candidates(content):
        try:
            return schema.model_validate_json(candidate)
        except (ValidationError, json.JSONDecodeError):
            continue
    # 全部失败时抛出最后一次的解析错误，交给上层重试。
    return schema.model_validate_json(_json_candidates(content)[-1])


def _json_candidates(text: str) -> list[str]:
    cleaned = (text or "").strip()
    candidates: list[str] = [cleaned]

    fenced = _FENCE_RE.search(cleaned)
    if fenced:
        inner = fenced.group(1).strip()
        candidates.append(inner)
        cleaned = inner

    start = cleaned.find("{")
    if start >= 0:
        body = cleaned[start:]
        candidates.append(body)
        end = body.rfind("}")
        if end >= 0:
            candidates.append(body[: end + 1])
        candidates.extend(_repair_variants(body))

    # 去重且保持顺序
    seen: set[str] = set()
    unique = [c for c in candidates if c and not (c in seen or seen.add(c))]
    return unique or [cleaned]


def _repair_variants(text: str) -> list[str]:
    """生成由宽到严的截断修复候选：先尝试保留字符串内容，再尝试丢弃残缺尾巴。"""
    return [_repair_json(text), _repair_json(text, keep_partial_string=False)]


def _repair_json(text: str, *, keep_partial_string: bool = True) -> str:
    """补全被 max_tokens 截断的 JSON。

    截断可能发生在字符串中间、键名之后、值之后任意位置。做法是记录最后一个
    「完整值结束」的位置，从那里截断、去掉尾随逗号，再补齐未闭合的括号。
    """
    stack: list[str] = []
    in_string = False
    escaped = False
    safe_cut = 0

    def skip_space(pos: int) -> int:
        while pos < len(text) and text[pos] in " \t\r\n":
            pos += 1
        return pos

    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
                # 字符串后面紧跟冒号说明它是键名，不是完整值。
                if skip_space(index + 1) >= len(text) or text[skip_space(index + 1)] != ":":
                    safe_cut = index + 1
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append(char)
        elif char in "}]" and stack:
            stack.pop()
            safe_cut = index + 1

    if in_string and keep_partial_string:
        # 截在字符串中间：直接补引号即可保留已输出的内容。
        repaired = text.rstrip() + '"'
        for opener in reversed(stack):
            repaired += "}" if opener == "{" else "]"
        return repaired

    # 结构性截断：退回到最后一个完整值，丢掉残缺的键/值片段。
    head = text[: safe_cut or len(text)].rstrip()
    while head and head[-1] == ",":
        head = head[:-1].rstrip()
    if not head:
        return text.strip()

    depth: list[str] = []
    in_string = False
    escaped = False
    for char in head:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            depth.append(char)
        elif char in "}]" and depth:
            depth.pop()
    for opener in reversed(depth):
        head += "}" if opener == "{" else "]"
    return head


def _schema_hint(schema: type[BaseModel]) -> str:
    props = schema.model_json_schema()
    return json.dumps(props, ensure_ascii=False)[:1500]


def _brief_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:3])
    return str(exc)[:200]
