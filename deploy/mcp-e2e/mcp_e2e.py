#!/usr/bin/env python3
"""
trade-mcp 端到端测试：仅通过 MCP 协议访问本服务（不直接请求 backend / binance-service）。

流程：
  1) SSE 连接 {TRADE_MCP_BASE_URL}{MCP_SSE_PATH}（与 Spring AI 默认 /sse 一致）
  2) ClientSession.initialize → list_tools（校验工具已注册）
  3) tools/call：至少调用 2 个工具，覆盖「经 backend」与「经 binance-service」两条链路

依赖：pip install -r requirements-e2e.txt（需要 mcp 官方 Python SDK）

环境变量：
  TRADE_MCP_BASE_URL   trade-mcp 根 URL，默认 http://127.0.0.1:8099
  MCP_SSE_PATH         SSE 路径，默认 /sse（与 spring.ai.mcp.server.sse-endpoint 一致）
  E2E_MCP_TIMEOUT      HTTP/SSE 超时（秒），默认 120
  E2E_SKIP_MARKET      若为 1：跳过 trade.market.symbol_prices（仅测库表类 tool）
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

# --- 与 trade-mcp 中 @McpTool name 一致 ---
TOOL_TICKERS_ALL_SYMBOLS = "trade.market_tickers.all_symbols"
TOOL_MARKET_SYMBOL_PRICES = "trade.market.symbol_prices"


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name, "").strip().lower()
    if not v:
        return default
    return v in {"1", "true", "yes", "y", "on"}


def _result_summary(result) -> str:
    """便于失败时打印。"""
    try:
        if result.structuredContent is not None:
            return json.dumps(result.structuredContent, ensure_ascii=False)[:800]
    except Exception:
        pass
    parts = []
    for block in result.content or []:
        if getattr(block, "text", None):
            parts.append(block.text[:400])
    return " | ".join(parts) if parts else repr(result)


def _assert_tool_success(result, tool_name: str) -> None:
    from mcp.types import CallToolResult

    if not isinstance(result, CallToolResult):
        raise AssertionError(f"{tool_name}: 返回类型异常: {type(result)}")
    if result.isError:
        raise AssertionError(f"{tool_name}: isError=true，{_result_summary(result)}")
    # Java Map 常出现在 structuredContent；部分实现为 JSON 文本
    sc = result.structuredContent
    if isinstance(sc, dict) and "success" in sc and sc["success"] is not True:
        raise AssertionError(f"{tool_name}: success!=true，{_result_summary(result)}")
    for block in result.content or []:
        if getattr(block, "type", "") == "text" and getattr(block, "text", ""):
            try:
                j = json.loads(block.text)
                if isinstance(j, dict) and j.get("success") is False:
                    raise AssertionError(f"{tool_name}: {block.text[:500]}")
            except json.JSONDecodeError:
                pass


async def _run() -> None:
    try:
        from mcp import ClientSession
        from mcp.client.sse import sse_client
    except ImportError as e:
        print(
            "缺少依赖：请执行  pip install -r requirements-e2e.txt  （需要 mcp 包）",
            file=sys.stderr,
        )
        raise SystemExit(2) from e

    base = os.environ.get("TRADE_MCP_BASE_URL", "http://127.0.0.1:8099").rstrip("/")
    sse_path = os.environ.get("MCP_SSE_PATH", "/sse")
    if not sse_path.startswith("/"):
        sse_path = "/" + sse_path
    sse_url = base + sse_path
    timeout = float(os.environ.get("E2E_MCP_TIMEOUT", "120"))
    skip_market = _env_bool("E2E_SKIP_MARKET", False)

    print(f"[e2e] MCP SSE URL: {sse_url}")
    print(f"[e2e] timeout={timeout}s skip_market_prices={skip_market}")

    async with sse_client(sse_url, timeout=timeout, sse_read_timeout=timeout) as (
        read_stream,
        write_stream,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            listed = await session.list_tools()
            names = {t.name for t in listed.tools}
            print(f"[e2e] list_tools: {len(names)} tools")

            for need in (TOOL_TICKERS_ALL_SYMBOLS, TOOL_MARKET_SYMBOL_PRICES):
                if need not in names and not (need == TOOL_MARKET_SYMBOL_PRICES and skip_market):
                    print(f"[e2e] ERROR: 缺少工具 {need}", file=sys.stderr)
                    raise SystemExit(1)

            r1 = await session.call_tool(TOOL_TICKERS_ALL_SYMBOLS, arguments={})
            _assert_tool_success(r1, TOOL_TICKERS_ALL_SYMBOLS)
            print(f"[e2e] call_tool {TOOL_TICKERS_ALL_SYMBOLS}: OK")

            if not skip_market:
                r2 = await session.call_tool(
                    TOOL_MARKET_SYMBOL_PRICES,
                    arguments={"symbols": ["BTCUSDT"]},
                )
                _assert_tool_success(r2, TOOL_MARKET_SYMBOL_PRICES)
                print(f"[e2e] call_tool {TOOL_MARKET_SYMBOL_PRICES}: OK")

    print("[e2e] --- MCP END-TO-END PASSED ---")


def main() -> None:
    try:
        asyncio.run(_run())
    except SystemExit:
        raise
    except Exception as e:
        print(f"[e2e] FAILED: {e}", file=sys.stderr)
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
