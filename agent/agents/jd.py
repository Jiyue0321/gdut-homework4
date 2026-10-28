"""岗位分析智能体：JD + 简历 → 能力模型。"""

from __future__ import annotations

import json
from typing import Any

from agent.agents.resume import ChatClient
from agent.prompts import JD_ANALYST
from agent.state import CompetencyModel, ResumeProfile


def build_messages(
    jd_text: str, role_title: str, profile: ResumeProfile | None = None
) -> list[dict[str, Any]]:
    parts = [JD_ANALYST, f"\n目标岗位：{role_title}", "\n岗位 JD：\n\"\"\"", jd_text.strip(), "\"\"\""]
    if profile:
        parts.append("\n候选人简历事实：\n" + json.dumps(profile.model_dump(), ensure_ascii=False))
    return [{"role": "user", "content": "\n".join(parts)}]


def analyze_jd(
    client: ChatClient,
    jd_text: str,
    role_title: str,
    profile: ResumeProfile | None = None,
) -> CompetencyModel:
    model = client.chat_json(
        build_messages(jd_text, role_title, profile),
        CompetencyModel,
        temperature=0.2,
        max_tokens=800,
    )
    return _ensure_weights(model)


def _ensure_weights(model: CompetencyModel) -> CompetencyModel:
    """模型给的权重可能不归一，这里统一处理；同时限制能力数量。"""
    comps = model.competencies[:7]
    total = sum(c.weight for c in comps)
    if total > 0:
        for c in comps:
            c.weight = round(c.weight / total, 3)
    return CompetencyModel(role_title=model.role_title or "目标岗位", competencies=comps)
