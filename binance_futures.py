import logging
import threading
from typing import Callable, Dict, List, Optional

from binance_common.configuration import ConfigurationRestAPI
from binance_common.constants import (
    DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL,
    DERIVATIVES_TRADING_USDS_FUTURES_REST_API_TESTNET_URL,
)
from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import (
    DerivativesTradingUsdsFutures,
)
from binance_sdk_derivatives_trading_usds_futures.rest_api.models import (
    KlineCandlestickDataIntervalEnum,
    SymbolPriceTickerResponse,
    Ticker24hrPriceChangeStatisticsResponse,
)


logger = logging.getLogger(__name__)


class BinanceFuturesClient:
    """High level helper over Binance official derivatives SDK"""

    _KEEPALIVE_INTERVAL = 15 * 60  # seconds

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        quote_asset: str = "USDT",
        base_path: Optional[str] = None,
        testnet: bool = False,
    ):
        rest_base = base_path
        if not rest_base:
            rest_base = (
                DERIVATIVES_TRADING_USDS_FUTURES_REST_API_TESTNET_URL
                if testnet
                else DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL
            )

        configuration = ConfigurationRestAPI(
            api_key=api_key,
            api_secret=api_secret,
            base_path=rest_base,
        )

        self.quote_asset = quote_asset.upper()
        self._client = DerivativesTradingUsdsFutures(config_rest_api=configuration)
        self._rest = self._client.rest_api
        self._callback: Optional[Callable[[Dict], None]] = None
        self._listen_key: Optional[str] = None
        self._listen_stop = threading.Event()
        self._keepalive_thread: Optional[threading.Thread] = None

    def format_symbol(self, base_symbol: str) -> str:
        return f"{base_symbol.upper()}{self.quote_asset}"

    def _call(self, func_name: str, *args, **kwargs):
        func = getattr(self._rest, func_name)
        response = func(*args, **kwargs)
        data = response.data()
        return data

    def get_24h_ticker(self, symbols: List[str]) -> Dict[str, Dict]:
        result: Dict[str, Dict] = {}
        if not symbols:
            return result
        all_stats: List[Ticker24hrPriceChangeStatisticsResponse] = self._call(
            "ticker24hr_price_change_statistics"
        )
        for stat in all_stats:
            if stat.symbol in symbols:
                result[stat.symbol] = stat.model_dump()
        return result

    def get_top_gainers(self, limit: int = 10) -> List[Dict]:
        data = self.get_all_tickers()
        filtered = [
            item for item in data if item.get("symbol", "").endswith(self.quote_asset)
        ]
        filtered.sort(key=lambda x: float(x.get("priceChangePercent", 0)), reverse=True)
        return filtered[:limit]

    def get_all_tickers(self) -> List[Dict]:
        """Return 24h ticker stats for all symbols."""
        return self._call("ticker24hr_price_change_statistics")

    def get_symbol_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        payload: Dict[str, Dict] = {}
        if not symbols:
            return payload
        data = self._call("symbol_price_ticker")
        for item in data:
            if item.symbol in symbols:
                payload[item.symbol] = item.model_dump()
        return payload

    def get_klines(self, symbol: str, interval: str, limit: int = 120) -> List[List]:
        interval_enum = KlineCandlestickDataIntervalEnum(interval)
        data = self._call(
            "kline_candlestick_data",
            symbol=symbol,
            interval=interval_enum,
            limit=limit,
        )
        # each data item is a dict with fields mapping to kline columns
        klines = [
            [
                item.open_time,
                item.open,
                item.high,
                item.low,
                item.close,
                item.volume,
            ]
            for item in data
        ]
        return klines

    # Placeholder user stream (REST create listen key via user data stream API)
    def start_user_stream(self, callback: Optional[Callable[[Dict], None]] = None):
        self._callback = callback
        try:
            resp = self._rest.start_user_data_stream()
            key = resp.data().get("listenKey")
        except Exception as exc:
            logger.error(f"[Binance Futures] start_user_stream failed: {exc}")
            return

        self._listen_key = key
        self._listen_stop.clear()
        self._keepalive_thread = threading.Thread(
            target=self._keep_listen_key_alive, daemon=True
        )
        self._keepalive_thread.start()
        logger.info("[Binance Futures] Listen key created")

    def _keep_listen_key_alive(self):
        while not self._listen_stop.wait(self._KEEPALIVE_INTERVAL):
            if not self._listen_key:
                continue
            try:
                self._rest.keepalive_user_data_stream(listen_key=self._listen_key)
            except Exception as exc:
                logger.warning(f"[Binance Futures] keepalive failed: {exc}")

    def stop_user_stream(self):
        self._listen_stop.set()
        self._listen_key = None

    def close(self):
        self.stop_user_stream()
