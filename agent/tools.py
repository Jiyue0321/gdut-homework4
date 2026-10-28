"""工具层抽象：进程内直调（LocalTools）与 MCP 子进程（MCPTools）两套实现。

编排器与界面只依赖 ``ToolProvider`` 协议，切换实现只需改配置项 ``USE_MCP``。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Mapping, Protocol, Sequence

from agent.config import LLMConfig
from agent.mcp_client import MCPToolClient
from mcp_server import toolkit


class ToolProvider(Protocol):
    def check_resume_quality(self, text: str) -> dict[str, Any]: ...
    def match_competencies(self, competencies: Sequence[Mapping[str, Any]]) -> dict[str, Any]: ...
    def pick_questions(
        self, competencies: Sequence[str], agent: str, count: int, seed: int | None = None
    ) -> list[dict[str, Any]]: ...
    def aggregate_scores(
        self, turns: Sequence[Mapping[str, Any]], weights: Mapping[str, float]
    ) -> dict[str, Any]: ...
    def merge_cross_exam(self, scores: Sequence[float]) -> dict[str, Any]: ...
    def render_report_md(self, report: Mapping[str, Any]) -> str: ...
    def export_report(self, filename: str, content: str) -> dict[str, Any]: ...


class LocalTools:
    """进程内直调：与 MCP 工具共用 mcp_server.toolkit 的实现。"""

    def check_resume_quality(self, text: str) -> dict[str, Any]:
        return toolkit.check_resume_quality(text)

    def match_competencies(self, competencies: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        return toolkit.match_competencies(competencies)

    def pick_questions(
        self, competencies: Sequence[str], agent: str, count: int, seed: int | None = None
    ) -> list[dict[str, Any]]:
        return toolkit.select_questions(competencies, agent, count, seed)

    def aggregate_scores(
        self, turns: Sequence[Mapping[str, Any]], weights: Mapping[str, float]
    ) -> dict[str, Any]:
        return toolkit.aggregate_scores(turns, weights)

    def merge_cross_exam(self, scores: Sequence[float]) -> dict[str, Any]:
        return toolkit.merge_cross_exam(scores)

    def render_report_md(self, report: Mapping[str, Any]) -> str:
        return toolkit.render_report_md(report)

    def export_report(self, filename: str, content: str) -> dict[str, Any]:
        return toolkit.export_report(filename, content)


class MCPTools:
    """通过 stdio 子进程调用 MCP 工具服务，每次调用复用同一套 JSON 契约。"""

    def _call(self, name: str, arguments: dict[str, Any]) -> Any:
        return asyncio.run(self._call_async(name, arguments))

    async def _call_async(self, name: str, arguments: dict[str, Any]) -> Any:
        async with MCPToolClient() as client:
            return await client.call_tool_json(name, arguments)

    def check_resume_quality(self, text: str) -> dict[str, Any]:
        return self._call("check_resume_quality", {"text": text})

    def match_competencies(self, competencies: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        return self._call(
            "match_competencies", {"competencies_json": json.dumps(competencies, ensure_ascii=False)}
        )

    def pick_questions(
        self, competencies: Sequence[str], agent: str, count: int, seed: int | None = None
    ) -> list[dict[str, Any]]:
        return self._call(
            "pick_questions",
            {
                "competencies_json": json.dumps(list(competencies), ensure_ascii=False),
                "agent": agent,
                "count": count,
                "seed": seed,
            },
        )

    def aggregate_scores(
        self, turns: Sequence[Mapping[str, Any]], weights: Mapping[str, float]
    ) -> dict[str, Any]:
        return self._call(
            "aggregate_scores",
            {
                "turns_json": json.dumps(turns, ensure_ascii=False),
                "weights_json": json.dumps(weights, ensure_ascii=False),
            },
        )

    def merge_cross_exam(self, scores: Sequence[float]) -> dict[str, Any]:
        return self._call(
            "merge_cross_exam", {"scores_json": json.dumps(list(scores), ensure_ascii=False)}
        )

    def render_report_md(self, report: Mapping[str, Any]) -> str:
        return self._call(
            "render_report_md", {"report_json": json.dumps(report, ensure_ascii=False)}
        )

    def export_report(self, filename: str, content: str) -> dict[str, Any]:
        return self._call("export_report", {"filename": filename, "content": content})


def open_tools(config: LLMConfig) -> ToolProvider:
    return MCPTools() if config.use_mcp else LocalTools()
