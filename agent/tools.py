"""工具层抽象：进程内直调（LocalTools）与 MCP 子进程（MCPTools）两套实现。

编排器与界面只依赖 ``ToolProvider`` 协议，切换实现只需改配置项 ``USE_MCP``。
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any, Mapping, Protocol, Sequence

from agent.config import LLMConfig
from agent.mcp_client import MCPToolClient, _server_for
from mcp_server import toolkit


class ToolProvider(Protocol):
    def check_resume_quality(self, text: str) -> dict[str, Any]: ...
    def match_competencies(self, competencies: Sequence[Mapping[str, Any]]) -> dict[str, Any]: ...
    def pick_questions(
        self,
        competencies: Sequence[str],
        agent: str,
        count: int,
        seed: int | None = None,
        industry: str | None = None,
    ) -> list[dict[str, Any]]: ...
    def list_industries(self) -> list[str]: ...
    def detect_industry(self, jd_text: str) -> str: ...
    def extract_document(self, filename: str, data: bytes) -> dict[str, Any]: ...
    def aggregate_scores(
        self, turns: Sequence[Mapping[str, Any]], weights: Mapping[str, float]
    ) -> dict[str, Any]: ...
    def merge_cross_exam(self, scores: Sequence[float]) -> dict[str, Any]: ...
    def render_report_md(self, report: Mapping[str, Any]) -> str: ...
    def render_report_pdf(self, report: Mapping[str, Any]) -> bytes: ...
    def export_report(self, filename: str, content: str) -> dict[str, Any]: ...
    def export_report_pdf(self, filename: str, report: Mapping[str, Any]) -> dict[str, Any]: ...


class LocalTools:
    """进程内直调：与 MCP 工具共用 mcp_server.toolkit 的实现。"""

    def check_resume_quality(self, text: str) -> dict[str, Any]:
        return toolkit.check_resume_quality(text)

    def match_competencies(self, competencies: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        return toolkit.match_competencies(competencies)

    def pick_questions(
        self,
        competencies: Sequence[str],
        agent: str,
        count: int,
        seed: int | None = None,
        industry: str | None = None,
    ) -> list[dict[str, Any]]:
        return toolkit.select_questions(competencies, agent, count, seed, industry)

    def list_industries(self) -> list[str]:
        return toolkit.list_industries()

    def detect_industry(self, jd_text: str) -> str:
        return toolkit.detect_job_industry(jd_text)

    def extract_document(self, filename: str, data: bytes) -> dict[str, Any]:
        return toolkit.extract_document_text(filename, data)

    def aggregate_scores(
        self, turns: Sequence[Mapping[str, Any]], weights: Mapping[str, float]
    ) -> dict[str, Any]:
        return toolkit.aggregate_scores(turns, weights)

    def merge_cross_exam(self, scores: Sequence[float]) -> dict[str, Any]:
        return toolkit.merge_cross_exam(scores)

    def render_report_md(self, report: Mapping[str, Any]) -> str:
        return toolkit.render_report_md(report)

    def render_report_pdf(self, report: Mapping[str, Any]) -> bytes:
        return toolkit.render_report_pdf_bytes(report)

    def export_report(self, filename: str, content: str) -> dict[str, Any]:
        return toolkit.export_report(filename, content)

    def export_report_pdf(self, filename: str, report: Mapping[str, Any]) -> dict[str, Any]:
        return toolkit.export_report_pdf(filename, report)


class MCPTools:
    """通过 stdio 子进程调用 MCP 工具服务。

    子进程常驻复用：早期实现每次调用都重新拉起进程，单次约 1 秒，
    一次面试累计二十余次，会把容器 CPU 占满并拖垮静态资源。
    """

    def _server(self):
        return _server_for("mcp_server.interview_server")

    def _run(self, factory) -> Any:
        server = self._server()
        try:
            return server.run(factory)
        except Exception:
            # 子进程可能已崩溃或管道断开，重置后重试一次。
            try:
                asyncio.run_coroutine_threadsafe(server.reset(), server._ensure_loop()).result(5)
            except Exception:
                pass
            return server.run(factory)

    def _call(self, name: str, arguments: dict[str, Any]) -> Any:
        return self._run(lambda client: self._call_async(client, name, arguments))

    @staticmethod
    async def _call_async(client: MCPToolClient, name: str, arguments: dict[str, Any]) -> Any:
        return await client.call_tool_json(name, arguments)

    def _call_text(self, name: str, arguments: dict[str, Any]) -> str:
        """工具返回的是纯文本（如 Markdown 报告），不做 JSON 解析。"""
        return self._run(lambda client: self._call_text_async(client, name, arguments))

    @staticmethod
    async def _call_text_async(client: MCPToolClient, name: str, arguments: dict[str, Any]) -> str:
        text = await client.call_tool(name, arguments)
        if text.startswith(("错误", "工具执行出错")):
            raise ToolError(text)
        return text

    def check_resume_quality(self, text: str) -> dict[str, Any]:
        return self._call("check_resume_quality", {"text": text})

    def match_competencies(self, competencies: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        return self._call(
            "match_competencies", {"competencies_json": json.dumps(competencies, ensure_ascii=False)}
        )

    def pick_questions(
        self,
        competencies: Sequence[str],
        agent: str,
        count: int,
        seed: int | None = None,
        industry: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._call(
            "pick_questions",
            {
                "competencies_json": json.dumps(list(competencies), ensure_ascii=False),
                "agent": agent,
                "count": count,
                "seed": seed,
                "industry": industry,
            },
        )

    def list_industries(self) -> list[str]:
        return self._call("list_industries", {})

    def detect_industry(self, jd_text: str) -> str:
        return self._call("detect_industry", {"jd_text": jd_text})

    def extract_document(self, filename: str, data: bytes) -> dict[str, Any]:
        return self._call(
            "extract_document",
            {"filename": filename, "content_base64": base64.b64encode(data).decode("ascii")},
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
        return self._call_text(
            "render_report_md", {"report_json": json.dumps(report, ensure_ascii=False)}
        )

    def render_report_pdf(self, report: Mapping[str, Any]) -> bytes:
        result = self._call(
            "render_report_pdf", {"report_json": json.dumps(report, ensure_ascii=False)}
        )
        return base64.b64decode(result["pdf_base64"])

    def export_report(self, filename: str, content: str) -> dict[str, Any]:
        return self._call("export_report", {"filename": filename, "content": content})

    def export_report_pdf(self, filename: str, report: Mapping[str, Any]) -> dict[str, Any]:
        return self._call(
            "export_report_pdf",
            {"filename": filename, "report_json": json.dumps(report, ensure_ascii=False)},
        )


def open_tools(config: LLMConfig) -> ToolProvider:
    return MCPTools() if config.use_mcp else LocalTools()
