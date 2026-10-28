"""面试会话的数据结构：智能体输出、轮次记录、报告。"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

AgentName = Literal["hr", "tech", "pressure"]
AGENT_LABELS: dict[str, str] = {
    "hr": "HR 面试官",
    "tech": "技术面试官",
    "pressure": "压力面试官",
}


class Phase(str, Enum):
    IDLE = "idle"
    PARSE_RESUME = "parse_resume"
    ANALYZE_JD = "analyze_jd"
    PLAN = "plan"
    INTERVIEW = "interview"
    CROSS_EXAM = "cross_exam"
    EVALUATE = "evaluate"
    REPORT = "report"
    DONE = "done"


class ResumeProfile(BaseModel):
    summary: str = Field(description="两三句话概括候选人背景")
    skills: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list, description="有量化成果或被验证的亮点")
    concerns: list[str] = Field(default_factory=list, description="简历里含糊、缺失或可疑的点")


class Competency(BaseModel):
    name: str
    weight: float = Field(ge=0, description="相对重要度；不要求模型归一化，由代码统一归一")
    required_level: int = Field(ge=0, le=5, description="岗位要求的熟练度 0-5")
    resume_level: int = Field(ge=0, le=5, description="简历体现出的熟练度 0-5")


class CompetencyModel(BaseModel):
    role_title: str
    competencies: list[Competency] = Field(
        min_length=1, description="提示词要求 3-7 项；过多由代码截断，避免校验失败空转"
    )


class Rubric(BaseModel):
    criteria: list[str] = Field(description="这道题的评分要点，2-4 条")
    good_looks_like: str = Field(description="优秀回答具备什么特征")


class AnswerScore(BaseModel):
    dimensions: dict[str, int] = Field(description="维度名到 0-5 分")
    overall: int = Field(ge=0, le=5)
    evidence: str = Field(description="从回答中摘出的支撑原文（简短）")
    comment: str


class Question(BaseModel):
    text: str
    competency: str
    rubric: Rubric
    followup_hint: str = ""


class Slot(BaseModel):
    agent: AgentName
    competency: str
    focus: str = Field(description="这一题想考察的具体点")


class InterviewPlan(BaseModel):
    slots: list[Slot]


class TurnDecision(BaseModel):
    """面试官一次调用的双重产出：给上一题打分 + 出下一题。"""

    score: AnswerScore | None = Field(
        default=None, description="上一题的打分；若是第一题则为 null"
    )
    question: Question | None = Field(default=None, description="下一题；本次为最后一题则为 null")
    is_followup: bool = Field(default=False, description="下一题是否是对上一题的追问")


class Turn(BaseModel):
    slot_index: int
    agent: AgentName
    question: str
    answer: str
    score: AnswerScore
    is_followup: bool = False


class CrossExam(BaseModel):
    """交叉拷问轮：同一道题由三位面试官分别打分。"""

    turn_index: int
    question: str
    scores: dict[str, AnswerScore]
    merged: AnswerScore


class FinalReport(BaseModel):
    overall_score: float
    dimensions: dict[str, float]
    verdict: str
    strengths: list[str]
    improvements: list[str]
    action_plan: list[str]
    sample_answer: str
