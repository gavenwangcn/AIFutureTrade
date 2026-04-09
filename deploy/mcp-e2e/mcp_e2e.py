#!/usr/bin/env python3
"""
MCP 相关下游端到端探活：backend（MCP market-tickers）+ binance-service（K 线）。
与 trade-mcp 运行时依赖一致；Binance 地址应与 trade/common/config.py 中 BINANCE_SERVICE_LIST 对齐。

环境变量：
  BACKEND_BASE_URL       Java backend 根地址，默认 http://154.89.148.172:5002
  BINANCE_SERVICE_LIST   JSON 数组，与 config.py / Docker 中格式相同（含 base_url）
  TRADE_MCP_BASE_URL     可选；若设置则对 trade-mcp 做简单 HTTP 可达性检查
  E2E_HTTP_TIMEOUT_SEC   单次请求超时秒数，默认 30
  E2E_SKIP_BINANCE       若为 1/true 则跳过 binance-service 检查
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from typing import Any

# 与 trade/common/config.py 中默认 BINANCE_SERVICE_LIST 保持一致（环境变量未设置时使用）
_DEFAULT_BINANCE_SERVICE_LIST = (
    '[{"base_url":"http://185.242.232.23:5004","timeout":30},'
    '{"base_url":"http://185.242.232.42:5004","timeout":30}]'
)


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name, "").strip().lower()
    if not v:
        return default
    return v in {"1", "true", "yes", "y", "on"}


def _http_get_json(url: str, timeout: float) -> tuple[int, Any]:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            code = resp.getcode()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        code = e.code
    try:
        parsed = json.loads(body) if body.strip() else None
    except json.JSONDecodeError:
        parsed = body
    return code, parsed


def _http_get_code_only(url: str, timeout: float) -> int:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.getcode()
    except urllib.error.HTTPError as e:
        return e.code
    except OSError:
        return 0


def _trim_base(url: str) -> str:
    u = url.strip().rstrip("/")
    return u


def main() -> int:
    timeout = float(os.environ.get("E2E_HTTP_TIMEOUT_SEC", "30"))
    backend = _trim_base(os.environ.get("BACKEND_BASE_URL", "http://154.89.148.172:5002"))
    raw_list = os.environ.get("BINANCE_SERVICE_LIST", "").strip() or _DEFAULT_BINANCE_SERVICE_LIST
    skip_binance = _env_bool("E2E_SKIP_BINANCE", False)
    mcp_url = os.environ.get("TRADE_MCP_BASE_URL", "").strip()

    errors: list[str] = []

    # --- Backend: MCP market-tickers（与 trade-mcp BackendClient 一致）---
    for path, name in (
        ("/api/mcp/market-tickers/symbols", "market-tickers symbols"),
        ("/api/mcp/market-tickers/snapshot?page=1&size=2", "market-tickers snapshot"),
    ):
        url = backend + path
        print(f"[check] backend {name}: GET {url}")
        code, data = _http_get_json(url, timeout)
        if code != 200:
            errors.append(f"backend {name}: HTTP {code}")
            continue
        if isinstance(data, dict) and data.get("success") is True:
            print(f"  OK success=true")
        else:
            snippet = repr(data)[:500]
            errors.append(f"backend {name}: unexpected body or success!=true: {snippet}")

    if skip_binance:
        print("[skip] E2E_SKIP_BINANCE: binance-service checks skipped")
    else:
        if not raw_list:
            errors.append("BINANCE_SERVICE_LIST 未设置或为空（应对齐 trade/common/config.py）")
        else:
            try:
                services = json.loads(raw_list)
            except json.JSONDecodeError as e:
                errors.append(f"BINANCE_SERVICE_LIST JSON 无效: {e}")
                services = []
            if isinstance(services, list):
                for i, item in enumerate(services):
                    if not isinstance(item, dict):
                        errors.append(f"BINANCE_SERVICE_LIST[{i}] 不是对象")
                        continue
                    base = item.get("base_url") or item.get("baseUrl")
                    if not base or not str(base).strip():
                        errors.append(f"BINANCE_SERVICE_LIST[{i}] 缺少 base_url")
                        continue
                    b = _trim_base(str(base))
                    kline_url = (
                        f"{b}/api/market-data/klines?"
                        "symbol=BTCUSDT&interval=1m&limit=1"
                    )
                    print(f"[check] binance-service[{i}] klines: GET {kline_url}")
                    code, data = _http_get_json(kline_url, timeout)
                    if code != 200:
                        errors.append(f"binance-service[{i}] klines: HTTP {code}")
                        continue
                    if isinstance(data, dict) and data.get("success") is True:
                        print(f"  OK success=true")
                    else:
                        snippet = repr(data)[:500]
                        errors.append(f"binance-service[{i}] klines: unexpected body: {snippet}")

    if mcp_url:
        u = _trim_base(mcp_url)
        print(f"[check] trade-mcp reachability: GET {u}/")
        code = _http_get_code_only(f"{u}/", timeout)
        if code == 0:
            errors.append(f"trade-mcp {u}: 无法连接")
        else:
            print(f"  HTTP {code} (任意响应即视为进程可达)")

    if errors:
        print("\n--- FAILED ---", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("\n--- ALL CHECKS PASSED ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
