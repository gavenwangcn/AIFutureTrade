"""Market data streaming via Binance websocket into ClickHouse.

Creates the 24_market_tickers table (if missing) and streams quotes from the
all-market tickers websocket into ClickHouse for persistence.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from datetime import datetime, timezone

from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import (
    DERIVATIVES_TRADING_USDS_FUTURES_WS_STREAMS_PROD_URL,
    ConfigurationWebSocketStreams,
    DerivativesTradingUsdsFutures,
)

import common.config as app_config
from common.database_clickhouse import ClickHouseDatabase

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
    """标准化ticker数据，不再从报文中解析 price_change, price_change_percent, side, change_percent_text, open_price
    这些字段将在 upsert_market_tickers 中根据业务逻辑计算
    """
    return {
        "event_time": _to_int(raw.get("E")),
        "symbol": raw.get("s", ""),
        # 不再从报文中解析这些字段，将在 upsert_market_tickers 中计算
        # "price_change": _to_float(raw.get("p")),
        # "price_change_percent": _to_float(percent),
        # "side": "loser" if _to_float(percent) < 0 else "gainer",
        # "change_percent_text": f"{_to_float(percent):.2f}%",
        "average_price": _to_float(raw.get("w")),
        "last_price": _to_float(raw.get("c")),
        "last_trade_volume": _to_float(raw.get("Q")),
        # "open_price": _to_float(raw.get("o")),  # 不再从报文中解析
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
        # 使用优化后的增量插入逻辑
        await asyncio.to_thread(self._db.upsert_market_tickers, normalized)

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


def _normalize_kline(message_data: Any) -> Optional[Dict[str, Any]]:
    """
    Normalize kline data from SDK response.
    
    Expected format:
    e='kline' E=1764148546845 s='BTCUSDT' k=KlineCandlestickStreamsResponseK(...)
    """
    try:
        # Extract data from message
        if hasattr(message_data, "model_dump"):
            data = message_data.model_dump()
        elif hasattr(message_data, "__dict__"):
            data = message_data.__dict__
        elif isinstance(message_data, dict):
            data = message_data
        else:
            logger.warning("[MarketStreams] Unknown kline message format: %s", type(message_data))
            return None
        
        # Extract event time, symbol, and kline data
        event_time = data.get("E") or data.get("event_time", 0)
        symbol = data.get("s") or data.get("symbol", "")
        kline_obj = data.get("k")
        
        # Extract kline data
        if hasattr(kline_obj, "model_dump"):
            k = kline_obj.model_dump()
        elif hasattr(kline_obj, "__dict__"):
            k = kline_obj.__dict__
        elif isinstance(kline_obj, dict):
            k = kline_obj
        else:
            logger.warning("[MarketStreams] Unknown kline object format: %s", type(kline_obj))
            return None
        
        # Check if kline is closed (only process closed klines)
        is_closed = k.get("x") or k.get("is_closed", False)
        if not is_closed:
            return None  # Skip incomplete klines
        
        # Extract contract type (may be in parent data)
        contract_type = data.get("ps") or data.get("contract_type", "PERPETUAL")
        
        # Convert timestamps from milliseconds to datetime
        def ms_to_datetime(ms: Any) -> datetime:
            try:
                if isinstance(ms, datetime):
                    return ms
                return datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc)
            except (TypeError, ValueError):
                return datetime.now(timezone.utc)
        
        return {
            "event_time": ms_to_datetime(event_time),
            "symbol": symbol.upper(),
            "contract_type": contract_type or "PERPETUAL",
            "kline_start_time": ms_to_datetime(k.get("t") or k.get("kline_start_time", 0)),
            "kline_end_time": ms_to_datetime(k.get("T") or k.get("kline_end_time", 0)),
            "interval": k.get("i") or k.get("interval", ""),
            "first_trade_id": _to_int(k.get("f") or k.get("first_trade_id", 0)),
            "last_trade_id": _to_int(k.get("L") or k.get("last_trade_id", 0)),
            "open_price": _to_float(k.get("o") or k.get("open_price", 0)),
            "close_price": _to_float(k.get("c") or k.get("close_price", 0)),
            "high_price": _to_float(k.get("h") or k.get("high_price", 0)),
            "low_price": _to_float(k.get("l") or k.get("low_price", 0)),
            "base_volume": _to_float(k.get("v") or k.get("base_volume", 0)),
            "trade_count": _to_int(k.get("n") or k.get("trade_count", 0)),
            "is_closed": 1 if is_closed else 0,
            "quote_volume": _to_float(k.get("q") or k.get("quote_volume", 0)),
            "taker_buy_base_volume": _to_float(k.get("V") or k.get("taker_buy_base_volume", 0)),
            "taker_buy_quote_volume": _to_float(k.get("Q") or k.get("taker_buy_quote_volume", 0)),
        }
    except Exception as e:
        logger.warning("[MarketStreams] Failed to normalize kline: %s", e, exc_info=True)
        return None


class KlineStreamManager:
    """Manage kline websocket streams for leaderboard symbols."""
    
    # Supported intervals
    INTERVALS = ['1w', '1d', '4h', '1h', '15m', '5m', '1m']
    
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
        # Track active streams: {(symbol, interval): (connection, stream)}
        self._active_streams: Dict[Tuple[str, str], Tuple[Any, Any]] = {}
        self._lock = asyncio.Lock()
    
    async def _handle_kline_message(self, symbol: str, interval: str, message: Any) -> None:
        """Handle kline message and insert into database."""
        try:
            # Normalize kline data
            normalized = _normalize_kline(message)
            
            if normalized:
                # Insert into database
                await asyncio.to_thread(self._db.insert_market_klines, [normalized])
                logger.debug("[KlineStream] Inserted kline: %s %s", symbol, interval)
        except Exception as e:
            logger.error("[KlineStream] Error handling kline message: %s", e, exc_info=True)
    
    async def add_stream(self, symbol: str, interval: str) -> bool:
        """Add a kline stream for symbol and interval."""
        key = (symbol.upper(), interval)
        
        async with self._lock:
            if key in self._active_streams:
                logger.debug("[KlineStream] Stream already exists: %s %s", symbol, interval)
                return True
            
            try:
                connection = await self._client.websocket_streams.create_connection()
                stream = await connection.kline_candlestick_streams(
                    symbol=symbol.lower(),
                    interval=interval
                )
                
                # Set up message handler
                def handler(data: Any) -> None:
                    asyncio.create_task(self._handle_kline_message(symbol, interval, data))
                
                stream.on("message", handler)
                
                self._active_streams[key] = (connection, stream)
                logger.info("[KlineStream] Added stream: %s %s", symbol, interval)
                return True
            except Exception as e:
                logger.error("[KlineStream] Failed to add stream %s %s: %s", symbol, interval, e)
                return False
    
    async def remove_stream(self, symbol: str, interval: str) -> bool:
        """Remove a kline stream."""
        key = (symbol.upper(), interval)
        
        async with self._lock:
            if key not in self._active_streams:
                return True
            
            try:
                connection, stream = self._active_streams[key]
                await stream.unsubscribe()
                await connection.close_connection(close_session=True)
                del self._active_streams[key]
                logger.info("[KlineStream] Removed stream: %s %s", symbol, interval)
                return True
            except Exception as e:
                logger.error("[KlineStream] Failed to remove stream %s %s: %s", symbol, interval, e)
                # Remove from dict even if unsubscribe fails
                if key in self._active_streams:
                    del self._active_streams[key]
                return False
    
    async def sync_with_leaderboard(self) -> None:
        """Sync streams with current leaderboard symbols."""
        try:
            # Get current leaderboard symbols
            symbols = await asyncio.to_thread(self._db.get_leaderboard_symbols)
            symbol_set = {s.upper() for s in symbols}
            
            # Expected streams: all combinations of symbols and intervals
            expected_streams = {
                (symbol, interval)
                for symbol in symbol_set
                for interval in self.INTERVALS
            }
            
            # Current active streams
            current_streams = set(self._active_streams.keys())
            
            # Add missing streams
            to_add = expected_streams - current_streams
            for symbol, interval in to_add:
                await self.add_stream(symbol, interval)
            
            # Remove extra streams
            to_remove = current_streams - expected_streams
            for symbol, interval in to_remove:
                await self.remove_stream(symbol, interval)
            
            logger.info(
                "[KlineStream] Sync complete: %s symbols, %s streams (added: %s, removed: %s)",
                len(symbol_set),
                len(expected_streams),
                len(to_add),
                len(to_remove)
            )
        except Exception as e:
            logger.error("[KlineStream] Sync error: %s", e, exc_info=True)
    
    async def cleanup(self) -> None:
        """Cleanup all streams."""
        async with self._lock:
            keys = list(self._active_streams.keys())
            for symbol, interval in keys:
                await self.remove_stream(symbol, interval)


async def run_kline_sync_agent(check_interval: int = 10) -> None:
    """Run kline websocket sync agent."""
    db = ClickHouseDatabase()
    manager = KlineStreamManager(db)
    
    try:
        # Initial sync
        await manager.sync_with_leaderboard()
        
        # Periodic sync
        while True:
            await asyncio.sleep(check_interval)
            await manager.sync_with_leaderboard()
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.exception("[KlineSyncAgent] Error: %s", e)
    finally:
        await manager.cleanup()


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=getattr(logging, app_config.LOG_LEVEL, logging.INFO),
        format=app_config.LOG_FORMAT,
        datefmt=app_config.LOG_DATE_FORMAT,
    )

    parser = argparse.ArgumentParser(
        description="Stream Binance market data into ClickHouse"
    )
    parser.add_argument(
        "--mode",
        choices=["ticker", "kline-sync"],
        default="ticker",
        help="Stream mode: ticker or kline-sync"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Optional runtime in seconds before shutting down (runs forever when omitted)",
    )
    parser.add_argument(
        "--check-interval",
        type=int,
        default=10,
        help="Kline sync check interval in seconds (default: 10)"
    )

    args = parser.parse_args()

    try:
        if args.mode == "kline-sync":
            asyncio.run(run_kline_sync_agent(check_interval=args.check_interval))
        else:
            asyncio.run(run_market_ticker_stream(run_seconds=args.duration))
    except KeyboardInterrupt:
        logger.info("[MarketStreams] Interrupted by user")
