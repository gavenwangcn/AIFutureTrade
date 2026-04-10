#!/usr/bin/env python3
"""
使用官方 MCP Python SDK（SSE）探测 trade-mcp 是否可用。

默认流程：
  1) 连接 {TRADE_MCP_BASE_URL}{MCP_SSE_PATH}（与 spring.ai.mcp.server 一致，默认 /sse）
  2) ClientSession.initialize → list_tools
  3) call_tool：每次调用前打印 tool 名称与入参；返回后先打印「工具返回数据」（structuredContent / content 文本 JSON），再打印协议层详情

仅校验协议与工具注册（不调用下游）：设置环境变量 SCRIPT_LIST_ONLY=1 或传入 --list-only

依赖：
  pip install -r requirements.txt

环境变量（与 deploy/mcp-e2e/mcp_e2e.py 对齐）：
  TRADE_MCP_BASE_URL   默认 http://127.0.0.1:8099
  MCP_SSE_PATH         默认 /sse
  E2E_MCP_TIMEOUT      秒，默认 120
  SCRIPT_LIST_ONLY     若为 1：只做 initialize + list_tools
  E2E_SKIP_MARKET      若为 1：与 mcp_e2e 语义一致时可用于跳过行情类（本脚本在 --full 下可选用另一组工具）
  SCRIPT_PRINT_MAX_CHARS  打印返回 JSON/文本时的最大字符数，默认 6000；设为 0 表示不截断

自定义工具调用：
  python test_trade_mcp_client.py --tool trade.market.klines --args "{\"symbol\":\"BTCUSDT\",\"interval\":\"1m\",\"limit\":5}"
  python test_trade_mcp_client.py --tool trade.market.symbol_prices --args-file payload.json
  # PowerShell 可用单引号包一层 JSON，避免转义引号：
  # python test_trade_mcp_client.py --tool trade.market.klines --args '{"symbol":"BTCUSDT","interval":"1m","limit":5}'
  # 环境变量：SCRIPT_MCP_TOOL、SCRIPT_MCP_ARGS（未传命令行 --args 时生效）
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

TOOL_KLINES = "trade.market.klines"
TOOL_SYMBOL_PRICES = "trade.market.symbol_prices"
TOOL_TICKERS_ALL = "trade.market_tickers.all_symbols"


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name, "").strip().lower()
    if not v:
        return default
    return v in {"1", "true", "yes", "y", "on"}


def _print_max_chars() -> int:
    raw = os.environ.get("SCRIPT_PRINT_MAX_CHARS", "6000").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 6000
    return n if n >= 0 else 6000


def _truncate(s: str, max_chars: int) -> str:
    if max_chars == 0 or len(s) <= max_chars:
        return s
    return s[: max_chars - 20] + "\n... [truncated] ..."


def _json_structure_hint(obj: Any, depth: int = 0, max_depth: int = 4) -> str:
    """简要描述 dict/list 的键与类型，便于扫一眼数据结构。"""
    indent = "  " * depth
    if depth > max_depth:
        return f"{indent}..."
    if obj is None:
        return f"{indent}null"
    if isinstance(obj, bool):
        return f"{indent}bool"
    if isinstance(obj, (int, float, str)):
        t = type(obj).__name__
        return f"{indent}{t}"
    if isinstance(obj, list):
        if not obj:
            return f"{indent}list (len=0)"
        inner = _json_structure_hint(obj[0], depth + 1, max_depth)
        return f"{indent}list (len={len(obj)}), item0:\n{inner}"
    if isinstance(obj, dict):
        lines = [f"{indent}object (keys={len(obj)}):"]
        for k in sorted(obj.keys())[:40]:
            v = obj[k]
            vt = type(v).__name__
            lines.append(f"{indent}  {k!r}: {vt}")
        if len(obj) > 40:
            lines.append(f"{indent}  ... ({len(obj) - 40} more keys)")
        return "\n".join(lines)
    return f"{indent}{type(obj).__name__}"


def _tool_input_schema_as_dict(tool) -> dict:
    schema = getattr(tool, "inputSchema", None)
    if schema is None:
        return {}
    if isinstance(schema, dict):
        return schema
    md = getattr(schema, "model_dump", None)
    if callable(md):
        try:
            return md()
        except Exception:
            pass
    return {}


def _print_tool_invocation(tool_name: str, arguments: dict[str, Any]) -> None:
    """调用前打印：正在执行的 tool 与入参。"""
    print("[trade-mcp-test] ---------- 执行 tools/call ----------")
    print(f"  tool : {tool_name}")
    print(f"  args : {json.dumps(arguments, ensure_ascii=False)}")
    print("[trade-mcp-test] ---------- 请求已发出，等待返回 ----------\n")


def _print_tool_return_data(tool_name: str, result) -> None:
    """优先打印工具业务返回数据（structuredContent + content 文本，可读 JSON）。"""
    from mcp.types import CallToolResult

    mc = _print_max_chars()
    print("[trade-mcp-test] ========== 工具返回数据（业务载荷）==========")
    print(f"  tool: {tool_name}")
    if not isinstance(result, CallToolResult):
        print(f"  异常: 返回不是 CallToolResult，而是 {type(result).__name__}")
        print(f"  raw: {repr(result)[:2000]}")
        print("[trade-mcp-test] ========== 返回数据结束 ==========\n")
        return

    if result.isError:
        print("  [警告] isError=true，以下为仍打印的原始内容便于排查")

    sc = result.structuredContent
    if sc is not None:
        print("  --- structuredContent（业务数据，优先阅读）---")
        try:
            dumped = json.dumps(sc, ensure_ascii=False, indent=2, default=str)
            print(_truncate(dumped, mc))
        except Exception as e:
            print(f"  JSON 序列化失败: {e}")
            print(f"  raw: {sc!r}")

    blocks = result.content or []
    text_blocks = [b for b in blocks if getattr(b, "text", None)]
    if text_blocks:
        for i, block in enumerate(blocks):
            text = getattr(block, "text", None)
            if not text:
                continue
            bt = getattr(block, "type", None) or ""
            print(f"  --- content 文本块 [{i}] type={bt!r}（len={len(text)}）---")
            try:
                j = json.loads(text)
                out = json.dumps(j, ensure_ascii=False, indent=2, default=str)
                print(_truncate(out, mc))
            except json.JSONDecodeError:
                print(_truncate(text, mc))

    if sc is None and not text_blocks:
        print("  (本次返回无 structuredContent 且无带 text 的 content 块)")

    print("[trade-mcp-test] ========== 返回数据结束 ==========\n")


def _print_mcp_call_result(tool_name: str, result) -> None:
    """先打印业务返回数据，再打印 MCP 协议层详情（元数据、结构概要）。"""
    from mcp.types import CallToolResult

    _print_tool_return_data(tool_name, result)

    mc = _print_max_chars()
    print(f"[trade-mcp-test] ---------- MCP 协议层详情: {tool_name} ----------")
    print(f"  Python 类型: {type(result).__name__}")
    if not isinstance(result, CallToolResult):
        print(f"  repr: {repr(result)[:2000]}")
        print(f"[trade-mcp-test] ---------- 协议层详情结束 ----------\n")
        return

    print(f"  isError: {result.isError}")
    if getattr(result, "meta", None) is not None:
        try:
            meta_s = json.dumps(result.meta, ensure_ascii=False, default=str)
            print(f"  meta: {_truncate(meta_s, mc)}")
        except Exception:
            print(f"  meta: {result.meta!r}")

    sc = result.structuredContent
    print(f"  structuredContent 类型: {type(sc).__name__}")
    if sc is not None:
        try:
            if isinstance(sc, (dict, list)):
                print("  structuredContent 键/类型概要:")
                print(_json_structure_hint(sc))
            else:
                print(f"  structuredContent 标量: {sc!r}")
        except Exception as e:
            print(f"  structuredContent 概要失败: {e}")

    blocks = result.content or []
    print(f"  content 块数量: {len(blocks)}")
    for i, block in enumerate(blocks):
        bt = getattr(block, "type", None) or type(block).__name__
        print(f"    [{i}] type={bt}")
        text = getattr(block, "text", None)
        if text:
            try:
                j = json.loads(text)
                print("        JSON 结构概要:")
                print(_json_structure_hint(j))
            except json.JSONDecodeError:
                print("        (非 JSON 文本，略)")
        else:
            extra = {k: v for k, v in getattr(block, "__dict__", {}).items() if k != "type"}
            if extra:
                print(f"        fields: {extra!r}")

    print(f"[trade-mcp-test] ---------- 协议层详情结束 ----------\n")


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


def _parse_tool_arguments_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    if not raw:
        return {}
    try:
        v = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[trade-mcp-test] ERROR: --args 不是合法 JSON: {e}", file=sys.stderr)
        raise SystemExit(2) from e
    if not isinstance(v, dict):
        print("[trade-mcp-test] ERROR: --args 必须是 JSON object（例如 {{\"k\":1}}）", file=sys.stderr)
        raise SystemExit(2)
    return v


def _load_tool_arguments_file(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as f:
            v = json.load(f)
    except OSError as e:
        print(f"[trade-mcp-test] ERROR: 无法读取 --args-file {path!r}: {e}", file=sys.stderr)
        raise SystemExit(2) from e
    except json.JSONDecodeError as e:
        print(f"[trade-mcp-test] ERROR: --args-file 内容不是合法 JSON: {e}", file=sys.stderr)
        raise SystemExit(2) from e
    if not isinstance(v, dict):
        print("[trade-mcp-test] ERROR: --args-file 根对象必须是 JSON object", file=sys.stderr)
        raise SystemExit(2)
    return v


async def _run(
    *,
    list_only: bool,
    full_e2e: bool,
    custom_tool: str | None,
    custom_arguments: dict[str, Any],
) -> None:
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
    print(
        f"[trade-mcp-test] timeout={timeout}s list_only={list_only} full_e2e={full_e2e} "
        f"custom_tool={custom_tool!r}"
    )

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
            # list_tools 响应结构（名称 + 参数 schema 键，便于对照 MCP 协议）
            print("[trade-mcp-test] ---------- list_tools 响应结构摘要 ----------")
            print(f"  ListToolsResult.tools: list 长度={len(listed.tools)}")
            for idx, t in enumerate(listed.tools[:5]):
                schema = _tool_input_schema_as_dict(t)
                keys = list(schema.keys()) if isinstance(schema, dict) else []
                props = (schema.get("properties") or {}) if isinstance(schema, dict) else {}
                prop_keys = list(props.keys())[:20] if isinstance(props, dict) else []
                desc = (getattr(t, "description", None) or "")[:120]
                print(f"  [{idx}] name={t.name!r}")
                if desc:
                    print(f"      description: {desc!r}")
                print(f"      inputSchema 顶层键: {keys}")
                if prop_keys:
                    print(f"      inputSchema properties 参数名(前20个): {prop_keys}")
            if len(listed.tools) > 5:
                print(f"  ... 另有 {len(listed.tools) - 5} 个工具未展开")
            print("[trade-mcp-test] ---------- list_tools 摘要结束 ----------\n")

            if list_only:
                print("[trade-mcp-test] --- PASSED (list-only) ---")
                return

            if custom_tool:
                if custom_tool not in names:
                    print(
                        f"[trade-mcp-test] ERROR: 服务端未注册工具 {custom_tool!r}",
                        file=sys.stderr,
                    )
                    raise SystemExit(1)
                _print_tool_invocation(custom_tool, custom_arguments)
                rc = await session.call_tool(custom_tool, arguments=custom_arguments)
                _assert_tool_success(rc, custom_tool)
                print(f"[trade-mcp-test] call_tool {custom_tool}: OK")
                _print_mcp_call_result(custom_tool, rc)
                print("[trade-mcp-test] --- PASSED (custom tool) ---")
                return

            if full_e2e:
                # 与 deploy/mcp-e2e 行为对齐：库表 + 行情价
                skip_market = _env_bool("E2E_SKIP_MARKET", False)
                for need in (TOOL_TICKERS_ALL, TOOL_SYMBOL_PRICES):
                    if need not in names and not (need == TOOL_SYMBOL_PRICES and skip_market):
                        print(f"[trade-mcp-test] ERROR: 缺少工具 {need}", file=sys.stderr)
                        raise SystemExit(1)
                _print_tool_invocation(TOOL_TICKERS_ALL, {})
                r1 = await session.call_tool(TOOL_TICKERS_ALL, arguments={})
                _assert_tool_success(r1, TOOL_TICKERS_ALL)
                print(f"[trade-mcp-test] call_tool {TOOL_TICKERS_ALL}: OK")
                _print_mcp_call_result(TOOL_TICKERS_ALL, r1)
                if not skip_market:
                    _print_tool_invocation(TOOL_SYMBOL_PRICES, {"symbols": ["BTCUSDT"]})
                    r2 = await session.call_tool(
                        TOOL_SYMBOL_PRICES,
                        arguments={"symbols": ["BTCUSDT"]},
                    )
                    _assert_tool_success(r2, TOOL_SYMBOL_PRICES)
                    print(f"[trade-mcp-test] call_tool {TOOL_SYMBOL_PRICES}: OK")
                    _print_mcp_call_result(TOOL_SYMBOL_PRICES, r2)
                print("[trade-mcp-test] --- PASSED (full e2e, same as deploy/mcp-e2e) ---")
                return

            # 默认：仅调用 K 线（依赖 binance-service）
            if TOOL_KLINES not in names:
                print(f"[trade-mcp-test] ERROR: 缺少工具 {TOOL_KLINES}", file=sys.stderr)
                raise SystemExit(1)
            klines_args = {
                "symbol": "BTCUSDT",
                "interval": "1m",
                "limit": 3,
            }
            _print_tool_invocation(TOOL_KLINES, klines_args)
            rk = await session.call_tool(TOOL_KLINES, arguments=klines_args)
            _assert_tool_success(rk, TOOL_KLINES)
            print(f"[trade-mcp-test] call_tool {TOOL_KLINES}: OK")
            _print_mcp_call_result(TOOL_KLINES, rk)

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
    p.add_argument(
        "--tool",
        metavar="NAME",
        default=None,
        help="指定要调用的 MCP tool 名称；与 --args / --args-file 配合。指定后不再执行默认 klines 或 --full",
    )
    p.add_argument(
        "--args",
        default="{}",
        metavar="JSON",
        help='tools/call 的 arguments，JSON 对象字符串，默认 {}。例: {"symbol":"BTCUSDT","interval":"1m","limit":3}',
    )
    p.add_argument(
        "--args-file",
        metavar="PATH",
        default=None,
        help="从 UTF-8 文件读取 JSON 对象作为 arguments（优先于 --args）",
    )
    args = p.parse_args()
    list_only = args.list_only or _env_bool("SCRIPT_LIST_ONLY", False)

    custom_tool = (args.tool or os.environ.get("SCRIPT_MCP_TOOL", "") or "").strip() or None
    if args.args_file:
        custom_arguments = _load_tool_arguments_file(args.args_file)
    else:
        # 未在命令行写 --args 时，可用环境变量 SCRIPT_MCP_ARGS 传入 JSON（与显式 --args 互斥）
        if "--args" not in sys.argv and os.environ.get("SCRIPT_MCP_ARGS"):
            raw_json = os.environ["SCRIPT_MCP_ARGS"]
        else:
            raw_json = args.args
        custom_arguments = _parse_tool_arguments_json(raw_json)

    if custom_tool and list_only:
        print(
            "[trade-mcp-test] ERROR: 不能同时使用 --list-only 与 --tool",
            file=sys.stderr,
        )
        raise SystemExit(2)

    if args.full and custom_tool:
        print(
            "[trade-mcp-test] WARN: 已指定 --tool，将忽略 --full，仅调用自定义工具",
            file=sys.stderr,
        )

    try:
        asyncio.run(
            _run(
                list_only=list_only,
                full_e2e=args.full,
                custom_tool=custom_tool,
                custom_arguments=custom_arguments,
            )
        )
    except SystemExit:
        raise
    except Exception as e:
        print(f"[trade-mcp-test] FAILED: {e}", file=sys.stderr)
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
