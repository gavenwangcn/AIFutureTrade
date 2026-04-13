from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from trade_mcp_client import TradeMcpClient, load_trade_mcp_config


@dataclass(frozen=True)
class StrategyConfig:
    symbol: str
    interval: str
    poll_interval_seconds: int
    max_seconds: int
    rsi_period: int
    rsi_threshold: float


def _parse_args() -> StrategyConfig:
    p = argparse.ArgumentParser(description="Trade-buy watcher (trade-mcp via Python MCP client).")
    p.add_argument("--symbol", default="ETHUSDT")
    p.add_argument("--interval", default="5m")
    p.add_argument("--poll-interval-seconds", type=int, default=10)
    p.add_argument("--max-seconds", type=int, default=86400)
    p.add_argument("--rsi-period", type=int, default=14)
    p.add_argument("--rsi-threshold", type=float, default=70.0)
    args = p.parse_args()

    poll = max(1, int(args.poll_interval_seconds))
    max_s = max(1, int(args.max_seconds))
    return StrategyConfig(
        symbol=str(args.symbol).strip().upper(),
        interval=str(args.interval).strip(),
        poll_interval_seconds=poll,
        max_seconds=max_s,
        rsi_period=int(args.rsi_period),
        rsi_threshold=float(args.rsi_threshold),
    )


def _extract_latest_rsi14(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Best-effort extractor for trade_market_klines_with_indicators responses.
    We intentionally keep parsing forgiving since backend fields can evolve.
    """
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return None
    latest = data[-1]
    if not isinstance(latest, dict):
        return None
    indicators = latest.get("indicators")
    if not isinstance(indicators, dict):
        return None
    rsi = indicators.get("rsi")
    if not isinstance(rsi, dict):
        return None
    # Prefer rsi14, fall back to any key that matches.
    v = rsi.get("rsi14")
    if v is None:
        for k in ("rsi_14", "rsi14_value", "rsi"):
            if k in rsi:
                v = rsi.get(k)
                break
    try:
        rsi14 = float(v)
    except Exception:
        return None
    close = latest.get("close")
    try:
        close_f = float(close) if close is not None else None
    except Exception:
        close_f = None
    ts = latest.get("close_time") or latest.get("closeTime") or latest.get("t")
    try:
        ts_ms = int(ts) if ts is not None else None
    except Exception:
        ts_ms = None
    return {"rsi14": rsi14, "close": close_f, "timestamp_ms": ts_ms}


async def main() -> int:
    cfg = _parse_args()
    started = time.time()

    trade_cfg = load_trade_mcp_config()
    async with TradeMcpClient(trade_cfg) as client:
        while True:
            elapsed = int(time.time() - started)
            if elapsed >= cfg.max_seconds:
                out = {
                    "status": "timeout",
                    "symbol": cfg.symbol,
                    "interval": cfg.interval,
                    "strategy": f"rsi{cfg.rsi_period}_gt_{cfg.rsi_threshold:g}",
                    "timestamp_ms": int(time.time() * 1000),
                    "details": {"elapsed_seconds": elapsed},
                }
                print(json.dumps(out, ensure_ascii=False))
                return 0

            try:
                raw = await client.klines_with_indicators(
                    symbol=cfg.symbol, interval=cfg.interval, limit=200
                )
                snapshot = _extract_latest_rsi14(raw)
                if snapshot and snapshot["rsi14"] > cfg.rsi_threshold:
                    out = {
                        "status": "signal",
                        "symbol": cfg.symbol,
                        "interval": cfg.interval,
                        "strategy": f"rsi{cfg.rsi_period}_gt_{cfg.rsi_threshold:g}",
                        "timestamp_ms": snapshot.get("timestamp_ms") or int(time.time() * 1000),
                        "details": {"rsi14": snapshot["rsi14"], "close": snapshot.get("close")},
                    }
                    print(json.dumps(out, ensure_ascii=False))
                    return 0
            except Exception as exc:
                # Keep running; transient errors should not stop a watcher.
                # Use stderr for diagnostics so stdout stays easy to parse.
                print(f"[warn] trade-buy watcher error: {exc}", file=sys.stderr)

            await asyncio.sleep(cfg.poll_interval_seconds)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

