"""Realtime 24h gainers/losers tracker using Binance Futures websocket streams.

This script subscribes to the official USDS-M futures `all_market_tickers` stream
(`!ticker@arr`) and logs the top-N gainers & losers among contracts that end with
FUTURES_QUOTE_ASSET (default: USDT).

Usage::

    export FUTURES_QUOTE_ASSET=USDT  # optional, defaults to USDT
    export FUTURES_WS_TOP_N=10       # optional, defaults to 10
    python tests/websocket_top_gainers.py

Stop the script with Ctrl+C.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import (
    DERIVATIVES_TRADING_USDS_FUTURES_WS_STREAMS_PROD_URL,
    ConfigurationWebSocketStreams,
    DerivativesTradingUsdsFutures,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("futures.ws.top_gainers")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class FuturesTopGainersStream:
    """Subscribe to `!ticker@arr` stream and compute top gainers/losers."""

    def __init__(
        self,
        quote_asset: str = "USDT",
        top_n: int = 10,
        stream_url: Optional[str] = None,
    ) -> None:
        configuration = ConfigurationWebSocketStreams(
            stream_url=stream_url or DERIVATIVES_TRADING_USDS_FUTURES_WS_STREAMS_PROD_URL
        )
        self._client = DerivativesTradingUsdsFutures(config_ws_streams=configuration)
        self.quote_asset = quote_asset.upper()
        self.top_n = max(1, top_n)
        self._connection = None
        self._stream = None

    async def run_forever(self) -> None:
        """Keep the websocket stream alive until interrupted."""
        while True:
            try:
                await self._start_stream()
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # pragma: no cover - interactive script
                logger.exception("[Stream] Unexpected error, reconnecting in 3s: %s", exc)
                await asyncio.sleep(3)
            finally:
                await self._stop_stream()

    async def _start_stream(self) -> None:
        if self._connection and not self._connection.closed:
            return

        logger.info(
            "[Stream] Connecting... quote_asset=%s top_n=%s", self.quote_asset, self.top_n
        )
        self._connection = await self._client.websocket_streams.create_connection()
        self._stream = await self._connection.all_market_tickers_streams()
        self._stream.on("message", self._handle_message)
        self._stream.on("error", lambda err: logger.error("[Stream] error: %s", err))
        self._stream.on("close", lambda _: logger.warning("[Stream] closed"))
        logger.info("[Stream] Subscribed to !ticker@arr feed")

    async def _stop_stream(self) -> None:
        if self._stream:
            try:
                await self._stream.unsubscribe()
            except Exception:
                pass
            self._stream = None

        if self._connection:
            try:
                await self._connection.close_connection(close_session=True)
            except Exception:
                pass
            self._connection = None

    # ------------------------------------------------------------------
    # Stream handlers
    # ------------------------------------------------------------------
    def _handle_message(self, payload: Any) -> None:
        self._log_raw_payload(payload)
        entries = self._extract_entries(payload)
        if not entries:
            logger.warning("[Stream] Payload parsed but contains no entries")
            return

        filtered = [item for item in map(self._normalize_entry, entries) if item]
        filtered = [item for item in filtered if item["symbol"].endswith(self.quote_asset)]
        if not filtered:
            logger.warning(
                "[Stream] Entries received (%s) but none matched quote_asset=%s",
                len(entries),
                self.quote_asset,
            )
            return

        logger.info(
            "[Stream] Parsed entries=%s | normalized=%s | filtered=%s",
            len(entries),
            len(filtered),
            len([item for item in entries if isinstance(item, dict)]),
        )

        gainers = sorted(filtered, key=lambda x: x["change_percent"], reverse=True)[: self.top_n]
        losers = sorted(filtered, key=lambda x: x["change_percent"])[: self.top_n]

        self._log_leaderboard(gainers, losers)

    @staticmethod
    def _log_raw_payload(payload: Any) -> None:
        if isinstance(payload, (bytes, bytearray)):
            display = payload[:512]
            logger.debug("[Stream] Raw payload bytes (%s): %s", len(payload), display)
        else:
            text = payload
            try:
                text = json.dumps(payload) if not isinstance(payload, str) else payload
            except TypeError:
                text = str(payload)

            if isinstance(text, str) and len(text) > 1024:
                logger.debug(
                    "[Stream] Raw payload str length=%s truncated=%s...",
                    len(text),
                    text[:1024],
                )
            else:
                logger.debug("[Stream] Raw payload: %s", text)

    @staticmethod
    def _extract_entries(payload: Any) -> List[Dict[str, Any]]:
        if payload is None:
            return []

        if isinstance(payload, (bytes, str)):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                logger.debug("[Stream] Unable to decode payload: %s", payload)
                return []

        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, list):
                return data
            if isinstance(payload.get("result"), list):
                return payload["result"]
            return []

        if isinstance(payload, list):
            return payload

        return []

    @staticmethod
    def _normalize_entry(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(item, dict):
            return None

        symbol = item.get("symbol") or item.get("s")
        if not symbol:
            return None

        price = item.get("lastPrice") or item.get("c")
        change = item.get("priceChangePercent") or item.get("P")
        volume = item.get("quoteVolume") or item.get("q")

        return {
            "symbol": symbol,
            "price": _safe_float(price),
            "change_percent": _safe_float(change),
            "quote_volume": _safe_float(volume),
        }

    def _log_leaderboard(
        self, gainers: List[Dict[str, Any]], losers: List[Dict[str, Any]]
    ) -> None:
        logger.info("========== WebSocket 24h Leaderboard ==========")

        if gainers:
            logger.info("Top %s Gainers:", len(gainers))
            for idx, item in enumerate(gainers, start=1):
                logger.info(
                    "#%02d %-12s Δ=%7.2f%% Price=%10.4f Volume=%12.2f",
                    idx,
                    item["symbol"],
                    item["change_percent"],
                    item["price"],
                    item["quote_volume"],
                )
        else:
            logger.info("No gainers detected for quote_asset=%s", self.quote_asset)

        if losers:
            logger.info("Top %s Losers:", len(losers))
            for idx, item in enumerate(losers, start=1):
                logger.info(
                    "#%02d %-12s Δ=%7.2f%% Price=%10.4f Volume=%12.2f",
                    idx,
                    item["symbol"],
                    item["change_percent"],
                    item["price"],
                    item["quote_volume"],
                )
        else:
            logger.info("No losers detected for quote_asset=%s", self.quote_asset)

        logger.info("==============================================")


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


async def main() -> None:
    quote_asset = os.getenv("FUTURES_QUOTE_ASSET", "USDT")
    top_n = _env_int("FUTURES_WS_TOP_N", 10)
    stream = FuturesTopGainersStream(quote_asset=quote_asset, top_n=top_n)
    await stream.run_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[Stream] Stopped by user")
