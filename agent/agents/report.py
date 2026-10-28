"""报告智能体：把确定性统计数据写成复盘结论。"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from agent.agents.resume import ChatClient
from agent.prompts import REPORT_WRITER
from agent.state import FinalReport


def build_messages(report_data: Mapping[str, Any], turns: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    weak = [
        name
        for name, score in (report_data.get("dimensions") or {}).items()
        if float(score) < 3.0
    ]
    transcript = [
        {
            "面试官": t.get("agent_label"),
            "考察能力": t.get("competency"),
            "问题": t.get("question"),
            "回答": t.get("answer"),
            "得分": t.get("overall"),
            "评语": t.get("comment"),
        }
        for t in turns
    ]
    content = REPORT_WRITER.format(
        role_title=report_data.get("role_title", ""),
        overall_score=report_data.get("overall_score", 0),
        verdict=report_data.get("verdict", ""),
        dimensions=json.dumps(report_data.get("dimensions") or {}, ensure_ascii=False),
        weak_points="、".join(weak) or "无",
        transcript=json.dumps(transcript, ensure_ascii=False)[:3000],
    )
    return [{"role": "user", "content": content}]


def write_report(
    client: ChatClient, report_data: Mapping[str, Any], turns: Sequence[Mapping[str, Any]]
) -> FinalReport:
    narrative = client.chat_json(
        build_messages(report_data, turns), FinalReport, temperature=0.5, max_tokens=1200
    )
    return narrative
