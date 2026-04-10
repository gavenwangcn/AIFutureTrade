#!/usr/bin/env python3
"""
使用官方 MCP Python SDK（SSE）探测 trade-mcp 是否可用。

默认流程：
  1) 连接 {TRADE_MCP_BASE_URL}{MCP_SSE_PATH}（与 spring.ai.mcp.server 一致，默认 /sse）
  2) ClientSession.initialize → list_tools
  3) call_tool：默认调用 trade.market.klines（只依赖 binance-service，不需 modelId）

仅校验协议与工具注册（不调用下游）：设置环境变量 SCRIPT_LIST_ONLY=1 或传入 --list-only

依赖：
  pip install -r requirements.txt

环境变量（与 deploy/mcp-e2e/mcp_e2e.py 对齐）：
  TRADE_MCP_BASE_URL   默认 http://127.0.0.1:8099
  MCP_SSE_PATH         默认 /sse
  E2E_MCP_TIMEOUT      秒，默认 120
  SCRIPT_LIST_ONLY     若为 1：只做 initialize + list_tools
  E2E_SKIP_MARKET      若为 1：与 mcp_e2e 语义一致时可用于跳过行情类（本脚本在 --full 下可选用另一组工具）
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

TOOL_KLINES = "trade.market.klines"
TOOL_SYMBOL_PRICES = "trade.market.symbol_prices"
TOOL_TICKERS_ALL = "trade.market_tickers.all_symbols"


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name, "").strip().lower()
    if not v:
        return default
    return v in {"1", "true", "yes", "y", "on"}


def _result_summary(result) -> str:
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


async def _run(*, list_only: bool, full_e2e: bool) -> None:
    try:
        from mcp import ClientSession
        from mcp.client.sse import sse_client
    except ImportError as e:
        print(
            "缺少依赖：请在 trade-mcp/script 下执行  pip install -r requirements.txt",
            file=sys.stderr,
        )
        raise SystemExit(2) from e

    base = os.environ.get("TRADE_MCP_BASE_URL", "http://127.0.0.1:8099").rstrip("/")
    sse_path = os.environ.get("MCP_SSE_PATH", "/sse")
    if not sse_path.startswith("/"):
        sse_path = "/" + sse_path
    sse_url = base + sse_path
    timeout = float(os.environ.get("E2E_MCP_TIMEOUT", "120"))

    print(f"[trade-mcp-test] SSE URL: {sse_url}")
    print(f"[trade-mcp-test] timeout={timeout}s list_only={list_only} full_e2e={full_e2e}")

    async with sse_client(sse_url, timeout=timeout, sse_read_timeout=timeout) as (
        read_stream,
        write_stream,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("[trade-mcp-test] initialize: OK")

            listed = await session.list_tools()
            names = {t.name for t in listed.tools}
            print(f"[trade-mcp-test] list_tools: {len(names)} tools")
            if len(names) == 0:
                print("[trade-mcp-test] ERROR: 未注册任何工具", file=sys.stderr)
                raise SystemExit(1)

            sample = sorted(names)[:12]
            print(f"[trade-mcp-test] sample tool names: {sample}")

            if list_only:
                print("[trade-mcp-test] --- PASSED (list-only) ---")
                return

            if full_e2e:
                # 与 deploy/mcp-e2e 行为对齐：库表 + 行情价
                skip_market = _env_bool("E2E_SKIP_MARKET", False)
                for need in (TOOL_TICKERS_ALL, TOOL_SYMBOL_PRICES):
                    if need not in names and not (need == TOOL_SYMBOL_PRICES and skip_market):
                        print(f"[trade-mcp-test] ERROR: 缺少工具 {need}", file=sys.stderr)
                        raise SystemExit(1)
                r1 = await session.call_tool(TOOL_TICKERS_ALL, arguments={})
                _assert_tool_success(r1, TOOL_TICKERS_ALL)
                print(f"[trade-mcp-test] call_tool {TOOL_TICKERS_ALL}: OK")
                if not skip_market:
                    r2 = await session.call_tool(
                        TOOL_SYMBOL_PRICES,
                        arguments={"symbols": ["BTCUSDT"]},
                    )
                    _assert_tool_success(r2, TOOL_SYMBOL_PRICES)
                    print(f"[trade-mcp-test] call_tool {TOOL_SYMBOL_PRICES}: OK")
                print("[trade-mcp-test] --- PASSED (full e2e, same as deploy/mcp-e2e) ---")
                return

            # 默认：仅调用 K 线（依赖 binance-service）
            if TOOL_KLINES not in names:
                print(f"[trade-mcp-test] ERROR: 缺少工具 {TOOL_KLINES}", file=sys.stderr)
                raise SystemExit(1)
            rk = await session.call_tool(
                TOOL_KLINES,
                arguments={
                    "symbol": "BTCUSDT",
                    "interval": "1m",
                    "limit": 3,
                },
            )
            _assert_tool_success(rk, TOOL_KLINES)
            print(f"[trade-mcp-test] call_tool {TOOL_KLINES}: OK")

    print("[trade-mcp-test] --- PASSED ---")


def main() -> None:
    p = argparse.ArgumentParser(description="Test trade-mcp via MCP Python SDK (SSE)")
    p.add_argument(
        "--list-only",
        action="store_true",
        help="仅 initialize + list_tools，不 call_tool",
    )
    p.add_argument(
        "--full",
        action="store_true",
        help="与 deploy/mcp-e2e/mcp_e2e.py 相同：all_symbols + symbol_prices（需 backend DB 与 binance）",
    )
    args = p.parse_args()
    list_only = args.list_only or _env_bool("SCRIPT_LIST_ONLY", False)

    try:
        asyncio.run(_run(list_only=list_only, full_e2e=args.full))
    except SystemExit:
        raise
    except Exception as e:
        print(f"[trade-mcp-test] FAILED: {e}", file=sys.stderr)
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
