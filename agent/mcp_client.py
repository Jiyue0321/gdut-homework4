"""MCP 客户端封装：连接 stdio 工具服务器。

MCP 2.x 只提供原生 snake_case 字段（如 ``tool.input_schema``），
本项目只做工具调用与管理，转换逻辑留在需要时再加。
"""

from __future__ import annotations

import asyncio
import atexit
import json
import sys
import threading
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Callable, Coroutine, TypeVar

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

PROJECT_ROOT = Path(__file__).resolve().parent.parent

T = TypeVar("T")


class MCPToolClient:
    """一个 MCP 工具服务器的会话（异步上下文管理器）。

    用法::

        async with MCPToolClient() as client:
            names = await client.list_tool_names()
            result = await client.call_tool_json("get_current_time", {})

    传入 ``server`` 时复用该常驻进程的会话，``__aexit__`` 不会断开连接。
    """

    def __init__(
        self, module: str = "mcp_server.interview_server", *, server: _ServerProcess | None = None
    ) -> None:
        self._module = module
        self._server = server
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tool_names: list[str] = []

    async def __aenter__(self) -> "MCPToolClient":
        if self._server is not None:
            self._session = await self._server.connect()
            self._tool_names = self._server.tool_names
            return self
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", self._module],
            cwd=str(PROJECT_ROOT),
            encoding="utf-8",
        )
        self._stack = AsyncExitStack()
        read, write = await self._stack.enter_async_context(
            stdio_client(params, errlog=sys.stderr)
        )
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        await self.refresh()
        return self

    async def __aexit__(self, *exc_info) -> None:
        if self._server is not None:
            # 常驻会话由 _ServerProcess 管理，这里只解绑引用。
            self._session = None
            return
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self._session = None

    async def refresh(self) -> list[str]:
        assert self._session is not None
        result = await self._session.list_tools()
        self._tool_names = [tool.name for tool in result.tools]
        return list(self._tool_names)

    async def list_tool_names(self) -> list[str]:
        return await self.refresh()

    async def call_tool(self, name: str, arguments: dict) -> str:
        """调用一个 MCP 工具，返回纯文本结果。"""
        assert self._session is not None
        if name not in self._tool_names:
            return f"错误：不存在名为 {name} 的工具"

        result = await self._session.call_tool(name, arguments)
        texts = [
            block.text
            for block in result.content
            if getattr(block, "type", None) == "text"
        ]
        output = "\n".join(texts) if texts else "(工具无文本输出)"
        if result.is_error:
            return f"工具执行出错：{output}"
        return output

    async def call_tool_json(self, name: str, arguments: dict) -> Any:
        """调用工具并把返回的 JSON 文本解析成对象。"""
        text = await self.call_tool(name, arguments)
        if text.startswith(("错误", "工具执行出错")):
            raise ToolError(text)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ToolError(f"工具 {name} 返回的不是 JSON：{text[:120]}") from exc


class ToolError(RuntimeError):
    """工具调用失败。"""


class _ServerProcess:
    """常驻的后台事件循环 + MCP 子进程会话。

    早期实现每次工具调用都 ``asyncio.run`` 起一个新进程，单次约 1 秒；
    一次面试要调二十来次，容器 CPU 被子进程反复冷启动占满，
    连静态资源请求都会超时，前端因此报「Failed to fetch module」。
    这里改成后台线程持有唯一的事件循环，子进程只拉起一次。
    """

    def __init__(self, module: str) -> None:
        self._module = module
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tool_names: list[str] = []

    def run(self, factory: Callable[["MCPToolClient"], Coroutine[Any, Any, T]]) -> T:
        """在后台循环里执行一次协程，阻塞等待结果。"""
        loop = self._ensure_loop()

        async def runner() -> T:
            async with MCPToolClient(module=self._module, server=self) as client:
                return await factory(client)

        return asyncio.run_coroutine_threadsafe(runner(), loop).result()

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is not None and self._loop.is_running():
                return self._loop
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._loop.run_forever, name="mcp-tools", daemon=True
            )
            self._thread.start()
            atexit.register(self.shutdown)
            return self._loop

    # 下面三个方法只在后台循环里被调用

    async def connect(self) -> "ClientSession":
        if self._session is not None:
            return self._session
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", self._module],
            cwd=str(PROJECT_ROOT),
            encoding="utf-8",
        )
        self._stack = AsyncExitStack()
        read, write = await self._stack.enter_async_context(
            stdio_client(params, errlog=sys.stderr)
        )
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        self._tool_names = [
            tool.name for tool in (await self._session.list_tools()).tools
        ]
        return self._session

    async def reset(self) -> None:
        """子进程异常退出后清掉会话，下次调用会重新拉起。"""
        if self._stack is not None:
            try:
                await self._stack.aclose()
            except Exception:
                pass
        self._stack = None
        self._session = None
        self._tool_names = []

    @property
    def tool_names(self) -> list[str]:
        return list(self._tool_names)

    def shutdown(self) -> None:
        """进程退出时关掉子进程，避免遗留孤儿进程。"""
        loop, self._loop = self._loop, None
        if loop is None or not loop.is_running():
            return
        try:
            asyncio.run_coroutine_threadsafe(self.reset(), loop).result(timeout=5)
        except Exception:
            pass
        loop.call_soon_threadsafe(loop.stop)


_SERVERS: dict[str, _ServerProcess] = {}
_SERVERS_LOCK = threading.Lock()


def _server_for(module: str) -> _ServerProcess:
    with _SERVERS_LOCK:
        server = _SERVERS.get(module)
        if server is None:
            server = _ServerProcess(module)
            _SERVERS[module] = server
        return server
