"""Tool executor: runs a tool with a timeout and returns a safe ToolResult.

Never raises: any tool failure or timeout becomes ``ToolResult(ok=False, ...)``
so it can be handed back to the agent as a normal (error) observation. Every
invocation is logged with the current execution/task/agent context.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Optional

from ..config import get_settings
from ..logging_config import get_logger
from .base import Tool, ToolResult

logger = get_logger(__name__)


def _short(value: object, limit: int = 120) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def execute_tool(tool: Tool, arguments: dict, *, timeout: Optional[float] = None) -> ToolResult:
    settings = get_settings()
    timeout = timeout or settings.tool_timeout_seconds
    args = arguments if isinstance(arguments, dict) else {}
    start = time.perf_counter()
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(lambda: tool.run(**args))
        output = future.result(timeout=timeout)
        pool.shutdown(wait=False)
        duration = (time.perf_counter() - start) * 1000
        logger.info(
            "tool=%s ok duration_ms=%.1f args=%s", tool.name, duration, _short(args)
        )
        return ToolResult(ok=True, output=str(output), duration_ms=duration)
    except FuturesTimeout:
        pool.shutdown(wait=False)
        duration = (time.perf_counter() - start) * 1000
        logger.warning("tool=%s timed out after %.1fs", tool.name, timeout)
        return ToolResult(
            ok=False, error=f"tool '{tool.name}' timed out after {timeout}s", duration_ms=duration
        )
    except Exception as exc:  # noqa: BLE001 - normalize to a safe result
        pool.shutdown(wait=False)
        duration = (time.perf_counter() - start) * 1000
        logger.warning("tool=%s error: %s", tool.name, exc)
        return ToolResult(ok=False, error=f"{type(exc).__name__}: {exc}", duration_ms=duration)
