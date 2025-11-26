"""Market data streaming via Binance websocket into ClickHouse.

Creates the 24_market_tickers table (if missing) and streams quotes from the
all-market tickers websocket into ClickHouse for persistence.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, Iterable, List, Optional

from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import (
    DERIVATIVES_TRADING_USDS_FUTURES_WS_STREAMS_PROD_URL,
    ConfigurationWebSocketStreams,
    DerivativesTradingUsdsFutures,
)

import config as app_config
from database_clickhouse import ClickHouseDatabase

logger = logging.getLogger(__name__)


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize_ticker(raw: Dict[str, Any]) -> Dict[str, Any]:
    percent = raw.get("P")
    return {
        "event_time": _to_int(raw.get("E")),
        "symbol": raw.get("s", ""),
        "price_change": _to_float(raw.get("p")),
        "price_change_percent": _to_float(percent),
        "side": "loser" if _to_float(percent) < 0 else "gainer",
        "change_percent_text": f"{_to_float(percent):.2f}%",
        "average_price": _to_float(raw.get("w")),
        "last_price": _to_float(raw.get("c")),
        "last_trade_volume": _to_float(raw.get("Q")),
        "open_price": _to_float(raw.get("o")),
        "high_price": _to_float(raw.get("h")),
        "low_price": _to_float(raw.get("l")),
        "base_volume": _to_float(raw.get("v")),
        "quote_volume": _to_float(raw.get("q")),
        "stats_open_time": _to_int(raw.get("O")),
        "stats_close_time": _to_int(raw.get("C")),
        "first_trade_id": _to_int(raw.get("F")),
        "last_trade_id": _to_int(raw.get("L")),
        "trade_count": _to_int(raw.get("n")),
    }


def _extract_tickers(message: Any) -> List[Dict[str, Any]]:
    if isinstance(message, (bytes, bytearray)):
        message = message.decode()

    if isinstance(message, str):
        try:
            message = json.loads(message)
        except json.JSONDecodeError:
            logger.warning("[MarketStreams] Unable to decode message: %s", message)
            return []

    # SDK response objects (e.g., AllMarketTickersStreamsResponse)
    if hasattr(message, "model_dump"):
        try:
            message = message.model_dump()
        except Exception:
            message = message.__dict__

    if isinstance(message, dict):
        data = message.get("data") or message.get("tickers") or message.get("payload")
        if data is None:
            data = message
    else:
        data = message

    result: List[Dict[str, Any]] = []
    if isinstance(data, list):
        for item in data:
            if hasattr(item, "model_dump"):
                try:
                    result.append(item.model_dump())
                    continue
                except Exception:
                    pass
            if isinstance(item, dict):
                result.append(item)
            else:
                result.append(vars(item))
        return result
    if isinstance(data, dict):
        return [data]
    return []


class MarketTickerStream:
    """Stream Binance all-market tickers into ClickHouse."""

    def __init__(self, db: ClickHouseDatabase) -> None:
        self._db = db
        configuration_ws_streams = ConfigurationWebSocketStreams(
            stream_url=os.getenv(
                "STREAM_URL",
                DERIVATIVES_TRADING_USDS_FUTURES_WS_STREAMS_PROD_URL,
            )
        )
        self._client = DerivativesTradingUsdsFutures(
            config_ws_streams=configuration_ws_streams
        )

    async def _handle_message(self, message: Any) -> None:
        tickers = _extract_tickers(message)
        if not tickers:
            return
        normalized = [_normalize_ticker(ticker) for ticker in tickers]
        await asyncio.to_thread(self._db.insert_market_tickers, normalized)

    async def stream(self, run_seconds: Optional[int] = None) -> None:
        connection = None
        stream = None
        try:
            connection = await self._client.websocket_streams.create_connection()
            stream = await connection.all_market_tickers_streams()
            stream.on(
                "message",
                lambda data: asyncio.create_task(self._handle_message(data)),
            )

            if run_seconds is not None:
                await asyncio.sleep(run_seconds)
                await stream.unsubscribe()
            else:
                while True:
                    await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("[MarketStreams] Streaming error: %s", exc)
        finally:
            if stream:
                try:
                    await stream.unsubscribe()
                except Exception:
                    logger.debug("[MarketStreams] Stream already unsubscribed")
            if connection:
                await connection.close_connection(close_session=True)


async def run_market_ticker_stream(run_seconds: Optional[int] = None) -> None:
    db = ClickHouseDatabase()
    streamer = MarketTickerStream(db)
    await streamer.stream(run_seconds=run_seconds)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=getattr(logging, app_config.LOG_LEVEL, logging.INFO),
        format=app_config.LOG_FORMAT,
        datefmt=app_config.LOG_DATE_FORMAT,
    )

    parser = argparse.ArgumentParser(
        description="Stream Binance 24h market tickers into ClickHouse"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Optional runtime in seconds before shutting down (runs forever when omitted)",
    )

    args = parser.parse_args()

    try:
        asyncio.run(run_market_ticker_stream(run_seconds=args.duration))
    except KeyboardInterrupt:
        logger.info("[MarketStreams] Interrupted by user")
