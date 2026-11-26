"""会话级运行观测：模型调用、工具调用与耗时记录，供后台页展示。

数据只活在当前浏览器会话的 ``st.session_state`` 里，**不落盘**。
跨会话统计需要持久化，Beta 方案见 ``docs/prototype-api.md`` 的持久化章节。

记录项的措辞刻意与设计原型后台的日志页对齐（``llm chat_json schema=... ok (1.7s)``），
将来接 SQLite 时字段可以原样映射成表列。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from time import perf_counter
from typing import Any

LEVELS = ("INFO", "WARN", "ERROR")

# 事件条数上限：一次面试约 20–30 次调用，留足空间又不至于把内存撑大。
MAX_EVENTS = 500


@dataclass
class Recorder:
    """一次浏览器会话的观测记录器。"""

    session_id: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    llm_calls: int = 0
    tool_calls: int = 0
    llm_errors: int = 0
    started_at: float = field(default_factory=perf_counter)

    def __post_init__(self) -> None:
        if not self.session_id:
            self.session_id = f"S-{datetime.now():%Y%m%d-%H%M%S}"

    # ---------- 写入 ----------

    def note(self, message: str, *, level: str = "INFO", kind: str = "event") -> None:
        self._append({"level": level if level in LEVELS else "INFO", "kind": kind, "message": message})

    def note_llm(self, schema: str, seconds: float, *, ok: bool = True) -> None:
        self.llm_calls += 1
        if not ok:
            self.llm_errors += 1
        status = "ok" if ok else "failed"
        self._append(
            {
                "level": "INFO" if ok else "ERROR",
                "kind": "llm",
                "message": f"llm chat_json schema={schema} {status} ({seconds:.1f}s)",
                "duration_ms": round(seconds * 1000),
            }
        )

    def note_tool(self, name: str, seconds: float, *, ok: bool = True, detail: str = "") -> None:
        self.tool_calls += 1
        suffix = f" -> {detail}" if detail else ""
        self._append(
            {
                "level": "INFO" if ok else "ERROR",
                "kind": "tool",
                "message": f"tool {name}{suffix}",
                "duration_ms": round(seconds * 1000),
            }
        )

    def _append(self, item: dict[str, Any]) -> None:
        item.setdefault("time", f"{datetime.now():%H:%M:%S}")
        item.setdefault("duration_ms", None)
        self.events.append(item)
        if len(self.events) > MAX_EVENTS:
            del self.events[: len(self.events) - MAX_EVENTS]

    # ---------- 读取 ----------

    @property
    def elapsed_seconds(self) -> float:
        return perf_counter() - self.started_at

    def summary(self) -> dict[str, Any]:
        tool_events = [e for e in self.events if e["kind"] == "tool"]
        times = [e["duration_ms"] for e in tool_events if e["duration_ms"] is not None]
        return {
            "session_id": self.session_id,
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
            "llm_errors": self.llm_errors,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "tool_avg_ms": round(sum(times) / len(times)) if times else 0,
            "unique_tools": len({e["message"].split(" -> ")[0] for e in tool_events}),
        }

    def rows(self) -> list[dict[str, Any]]:
        """日志页表格：时间、级别、类型、内容、耗时。"""
        return [
            {
                "时间": e["time"],
                "级别": e["level"],
                "类型": {"llm": "模型", "tool": "工具", "event": "事件"}.get(e["kind"], e["kind"]),
                "内容": e["message"],
                "耗时(ms)": e["duration_ms"],
            }
            for e in self.events
        ]

    def clear(self) -> None:
        self.events.clear()
        self.llm_calls = self.tool_calls = self.llm_errors = 0
        self.started_at = perf_counter()


class CountingChat:
    """给 ``LLMClient`` 套一层：统计调用次数与耗时，行为完全透传。"""

    def __init__(self, inner: Any, recorder: Recorder) -> None:
        self._inner = inner
        self._recorder = recorder

    def chat_json(self, messages: Any, schema: Any, **kwargs: Any) -> Any:
        name = getattr(schema, "__name__", str(schema))
        start = perf_counter()
        try:
            result = self._inner.chat_json(messages, schema, **kwargs)
        except Exception:
            self._recorder.note_llm(name, perf_counter() - start, ok=False)
            raise
        self._recorder.note_llm(name, perf_counter() - start)
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class InstrumentedTools:
    """给工具层套一层：逐次记录调用与耗时，行为完全透传。

    用 ``__getattr__`` 统一包装，新增工具时无需改这里。
    """

    def __init__(self, inner: Any, recorder: Recorder) -> None:
        self._inner = inner
        self._recorder = recorder

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if not callable(attr):
            return attr

        def call(*args: Any, **kwargs: Any) -> Any:
            start = perf_counter()
            try:
                result = attr(*args, **kwargs)
            except Exception as exc:
                self._recorder.note_tool(
                    name, perf_counter() - start, ok=False, detail=str(exc)[:120]
                )
                raise
            self._recorder.note_tool(name, perf_counter() - start, detail=_detail(result))
            return result

        return call


def _detail(result: Any) -> str:
    """从工具返回值里挑一个短摘要，让日志像原型里那样带结果。"""
    if isinstance(result, dict):
        for key in ("path", "bytes", "merged", "overall_score", "total"):
            if key in result:
                return f"{key}={result[key]}"
        for key in ("count", "questions"):
            if key in result:
                value = result[key]
                return f"count={len(value) if isinstance(value, list) else value}"
        return f"keys={len(result)}"
    if isinstance(result, (list, tuple)):
        return f"count={len(result)}"
    if isinstance(result, (bytes, bytearray)):
        return f"bytes={len(result)}"
    if isinstance(result, str):
        return result.strip()[:40]
    return ""


def get_recorder(st_module: Any = None) -> Recorder:
    """取当前会话的记录器；没有就新建并放进 session_state。"""
    if st_module is None:
        import streamlit as st_module  # type: ignore[no-redef]
    existing = st_module.session_state.get("telemetry")
    if isinstance(existing, Recorder):
        return existing
    recorder = Recorder()
    st_module.session_state["telemetry"] = recorder
    return recorder
