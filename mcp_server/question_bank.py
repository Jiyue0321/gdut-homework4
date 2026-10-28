"""题库装载与抽题。"""

from __future__ import annotations

import json
import random
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Sequence

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "question_bank.json"


@lru_cache(maxsize=1)
def load_bank(path: Path = DATA_FILE) -> tuple[dict[str, Any], ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return tuple(raw["questions"])


def pick_questions(
    competencies: Sequence[str],
    agent: str,
    count: int,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """按能力标签与面试官角色抽题；标签无匹配时退化为同角色任意题。"""
    bank = list(load_bank())
    wanted = {c.strip() for c in competencies if c and c.strip()}

    def matches(q: dict[str, Any]) -> bool:
        return q.get("agent") == agent and bool(wanted & set(q.get("competencies", [])))

    pool = [q for q in bank if matches(q)]
    if len(pool) < count:
        fallback = [q for q in bank if q.get("agent") == agent and q not in pool]
        pool.extend(fallback)

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
