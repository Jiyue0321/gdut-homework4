"""MCP 服务冒烟测试：确认子进程能启动并注册全部工具。"""

import asyncio

import pytest

from agent.mcp_client import MCPToolClient

EXPECTED = {
    "check_resume_quality",
    "match_competencies",
    "pick_questions",
    "list_competencies",
    "list_industries",
    "detect_industry",
    "extract_document",
    "aggregate_scores",
    "merge_cross_exam",
    "render_report_md",
    "render_report_pdf",
    "export_report",
    "export_report_pdf",
    "get_current_time",
}


def test_server_registers_expected_tools():
    async def run() -> list[str]:
        async with MCPToolClient() as client:
            return await client.list_tool_names()

    assert EXPECTED <= set(asyncio.run(run()))


def test_server_answer_roundtrip():
    async def run():
        async with MCPToolClient() as client:
            return await client.call_tool_json("match_competencies", {
                "competencies_json": '[{"name":"系统设计","required_level":4,"resume_level":2}]'
            })

    result = asyncio.run(run())
    assert result["gaps"][0]["competency"] == "系统设计"


@pytest.mark.slow
def test_mcp_roundtrip_is_consistent_with_local_tools():
    from agent.tools import LocalTools, MCPTools

    payload = [{"name": "技术深度", "weight": 0.6, "required_level": 4, "resume_level": 3}]
    assert MCPTools().match_competencies(payload) == LocalTools().match_competencies(payload)


def test_mcp_renders_markdown_report():
    """render_report_md 返回纯 Markdown，不能按 JSON 解析。"""
    from agent.tools import LocalTools, MCPTools

    report = {"role_title": "后端开发实习生", "overall_score": 3.2, "verdict": "基本达标"}
    markdown = MCPTools().render_report_md(report)
    assert markdown.startswith("# ")
    assert markdown == LocalTools().render_report_md(report)


def test_mcp_renders_pdf_ipc_payload():
    from agent.tools import MCPTools

    report = {"role_title": "后端开发实习生", "overall_score": 3.2, "verdict": "基本达标"}
    payload = MCPTools().render_report_pdf(report)
    assert payload.startswith(b"%PDF-")


def test_mcp_extracts_text_document():
    from agent.tools import LocalTools, MCPTools

    payload = "教育背景：广东工业大学".encode("utf-8")
    assert MCPTools().extract_document("resume.txt", payload) == LocalTools().extract_document(
        "resume.txt", payload
    )
