"""面试工具服务的 MCP 服务器。

以 stdio 传输运行，把确定性工具（简历体检、能力匹配、抽题、评分聚合、
报告渲染、报告导出）暴露给编排器与界面。所有文件写入都被限制在 workspace/。

启动方式（一般由客户端作为子进程拉起，无需手动运行）：
    python -m mcp_server.interview_server
"""

from __future__ import annotations

import json
from typing import Any, Sequence

from mcp.server.mcpserver import MCPServer

from mcp_server import toolkit

mcp = MCPServer("mock-interview-tools")


def _loads(value: Any, default: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default if value is None else value


@mcp.tool()
def check_resume_quality(text: str) -> str:
    """体检简历文本：识别板块完整性、篇幅和量化成果数量，返回 JSON。"""
    return json.dumps(toolkit.check_resume_quality(text), ensure_ascii=False)


@mcp.tool()
def match_competencies(competencies_json: str) -> str:
    """比对岗位要求与简历自评，返回雷达图数据与能力缺口 JSON。

    参数 competencies_json 是 JSON 数组，元素形如
    {"name": "系统设计", "weight": 0.3, "required_level": 4, "resume_level": 2}。
    """
    items = _loads(competencies_json, [])
    return json.dumps(toolkit.match_competencies(items), ensure_ascii=False)


@mcp.tool()
def pick_questions(competencies_json: str, agent: str, count: int, seed: int | None = None) -> str:
    """按能力标签和面试官角色（hr/tech/pressure）从题库抽题，返回 JSON 数组。"""
    competencies = _loads(competencies_json, [])
    return json.dumps(
        toolkit.select_questions(competencies, agent, count, seed), ensure_ascii=False
    )


@mcp.tool()
def list_competencies() -> str:
    """列出题库覆盖的全部能力标签。"""
    return json.dumps(toolkit.list_question_competencies(), ensure_ascii=False)


@mcp.tool()
def aggregate_scores(turns_json: str, weights_json: str) -> str:
    """按能力聚合逐题得分并计算加权总分，返回 JSON。

    turns_json 是 JSON 数组，元素需含 competency 与 score 字段；
    weights_json 是能力名到权重的 JSON 对象。
    """
    turns = _loads(turns_json, [])
    weights = _loads(weights_json, {})
    return json.dumps(toolkit.aggregate_scores(turns, weights), ensure_ascii=False)


@mcp.tool()
def merge_cross_exam(scores_json: str) -> str:
    """合并交叉拷问中多位面试官的分数（取中位数），返回 JSON。"""
    scores: Sequence[float] = _loads(scores_json, [])
    return json.dumps(toolkit.merge_cross_exam(scores), ensure_ascii=False)


@mcp.tool()
def render_report_md(report_json: str) -> str:
    """把面试报告数据渲染为 Markdown 文本。"""
    report = _loads(report_json, {})
    return toolkit.render_report_md(report)


@mcp.tool()
def export_report(filename: str, content: str) -> str:
    """把报告写入 workspace/ 目录（仅支持 .md/.markdown/.txt），返回 JSON。"""
    try:
        result = toolkit.export_report(filename, content)
    except ValueError as exc:
        return f"错误：{exc}"
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def get_current_time() -> str:
    """返回当前本地时间，用于报告落款与面试用时计算。"""
    return toolkit.get_current_time()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
