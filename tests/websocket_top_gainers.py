import asyncio
import json
import logging
import os
from typing import Any, Callable, Optional

from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import (
    DerivativesTradingUsdsFutures,
    DERIVATIVES_TRADING_USDS_FUTURES_WS_STREAMS_PROD_URL,
    ConfigurationWebSocketStreams,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("tests.websocket_top_gainers")


def _default_stream_url() -> str:
    return os.getenv(
        "STREAM_URL",
        DERIVATIVES_TRADING_USDS_FUTURES_WS_STREAMS_PROD_URL,
    )


class WebsocketTopGainers:
    """Simple helper for subscribing/logging the Binance !ticker@arr feed."""

    def __init__(self, *, reconnect_delay: int = 5) -> None:
        configuration_ws_streams = ConfigurationWebSocketStreams(
            stream_url=_default_stream_url()
        )
        self._client = DerivativesTradingUsdsFutures(
            config_ws_streams=configuration_ws_streams
        )
        self._connection = None
        self._stream = None
        self._reconnect_delay = reconnect_delay

    async def _connect(self) -> None:
        logger.info("[WS] Connecting to %s", _default_stream_url())
        self._connection = await self._client.websocket_streams.create_connection()
        self._stream = await self._connection.all_market_tickers_streams()
        self._stream.on("message", self._log_message)
        self._stream.on("error", lambda err: logger.error("[WS] error: %s", err))
        self._stream.on("close", lambda _: logger.warning("[WS] closed"))
        logger.info("[WS] Subscribed to !ticker@arr feed")

    async def _disconnect(self) -> None:
        if self._stream:
            try:
                await self._stream.unsubscribe()
            except Exception:
                logger.debug("[WS] Stream already unsubscribed")
            finally:
                self._stream = None
        if self._connection:
            try:
                await self._connection.close_connection(close_session=True)
            except Exception:
                logger.debug("[WS] Connection already closed")
            finally:
                self._connection = None

    async def run(self) -> None:
        while True:
            try:
                await self._connect()
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("[WS] Streaming error: %s", exc)
                await self._disconnect()
                logger.info("[WS] Reconnecting in %ss...", self._reconnect_delay)
                await asyncio.sleep(self._reconnect_delay)

    @staticmethod
    def _log_message(data: Any) -> None:
        try:
            text = data if isinstance(data, str) else json.dumps(data)
        except (TypeError, ValueError):
            text = str(data)
        logger.info("[WS] message: %s", text[:512])


async def main() -> None:
    streamer = WebsocketTopGainers()
    try:
        await streamer.run()
    finally:
        await streamer._disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[WS] Stopped by user")
