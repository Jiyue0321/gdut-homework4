"""题库装载、行业识别与抽题。"""

from __future__ import annotations

import json
import random
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "question_bank.json"

GENERAL_INDUSTRY = "通用"
AUTO_INDUSTRY = "自动"

# 关键词按命中次数计分；都命中时按顺序取第一个。故意写小写，匹配前统一转小写。
INDUSTRY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "互联网后端": (
        "后端", "服务端", "java", "spring", "mysql", "redis", "微服务",
        "分布式", "高并发", "mq", "kafka", "go", "api",
    ),
    "互联网前端": (
        "前端", "react", "vue", "javascript", "typescript", "css", "html",
        "小程序", "web前端", "web 前端", "浏览器", "移动端",
    ),
    "人工智能": (
        "算法", "机器学习", "深度学习", "大模型", "llm", "nlp", "推荐系统",
        "计算机视觉", "pytorch", "tensorflow", "模型训练", "特征工程",
    ),
    "数据分析": (
        "数据分析", "bi", "指标", "用户增长", "ab 实验", "ab实验", "hive",
        "指标体系", "漏斗", "留存分析", "数据看板",
    ),
    "软件测试": ("软件测试", "测试工程师", "qa", "自动化测试", "selenium", "jmeter", "缺陷管理", "测试用例"),
    "嵌入式": ("嵌入式", "单片机", "rtos", "stm32", "驱动程序", "固件", "arm", "物联网", "传感器"),
    "产品运营": ("产品经理", "运营", "用户研究", "活动策划", "拉新", "留存", "需求文档", "原型"),
    "金融科技": ("金融", "支付", "风控", "清结算", "银行", "证券", "保险", "交易系统", "账务"),
}


@lru_cache(maxsize=1)
def _load_raw(path: Path = DATA_FILE) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_bank(path: Path = DATA_FILE) -> tuple[dict[str, Any], ...]:
    return tuple(_load_raw(path)["questions"])


def industries_in_bank() -> list[str]:
    """题库支持的行业，通用排第一，其余按配置顺序。"""
    names = list(_load_raw().get("industries") or [])
    if GENERAL_INDUSTRY in names:
        names.remove(GENERAL_INDUSTRY)
    return [GENERAL_INDUSTRY, *names]


def industry_of(question: Mapping[str, Any]) -> str:
    return str(question.get("industry") or GENERAL_INDUSTRY)


# 「与前端协作」「Web 框架」说的是配合关系或通用技术，不能说明岗位本身是前端。
_COLLAB_RE = re.compile(r"(与|和|同|跟|配合|协同|联调)[^。；\n]{0,4}前端|前端[^。；\n]{0,3}(协作|对接|联调|沟通|配合)")


def detect_industry(text: str) -> str:
    """按关键词给 JD 归类；没有命中就返回「通用」。"""
    lowered = _COLLAB_RE.sub("", (text or "").lower())
    best_name, best_score = GENERAL_INDUSTRY, 0
    for name, keywords in INDUSTRY_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in lowered)
        if score > best_score:
            best_name, best_score = name, score
    return best_name


def pick_questions(
    competencies: Sequence[str],
    agent: str,
    count: int,
    seed: int | None = None,
    industry: str | None = None,
) -> list[dict[str, Any]]:
    """按能力标签、面试官角色与行业抽题。

    行业题永远与通用题混在一起；指定行业没有足够题目时依次退化为
    「该行业任意题」→「同角色任意题」，保证任何 JD 都能凑够题量。
    """
    bank = list(load_bank())
    wanted = {c.strip() for c in competencies if c and c.strip()}
    industries = {GENERAL_INDUSTRY}
    if industry and industry not in {GENERAL_INDUSTRY, AUTO_INDUSTRY}:
        industries.add(industry)

    def in_role(q: Mapping[str, Any]) -> bool:
        return q.get("agent") == agent

    def in_industry(q: Mapping[str, Any]) -> bool:
        return industry_of(q) in industries

    pool = [q for q in bank if in_role(q) and in_industry(q) and wanted & set(q.get("competencies", []))]
    if len(pool) < count:
        seen = {q["id"] for q in pool}
        pool += [q for q in bank if in_role(q) and in_industry(q) and q["id"] not in seen]
    if len(pool) < count:
        seen = {q["id"] for q in pool}
        pool += [q for q in bank if in_role(q) and q["id"] not in seen]

    rng = random.Random(seed)
    rng.shuffle(pool)
    return pool[: max(0, count)]


def competencies_in_bank() -> list[str]:
    names: set[str] = set()
    for question in load_bank():
        names.update(question.get("competencies", []))
    return sorted(names)


def questions_for(agent: str) -> Iterable[dict[str, Any]]:
    return (q for q in load_bank() if q.get("agent") == agent)
