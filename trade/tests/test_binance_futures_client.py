"""Manual connectivity test harness for common.binance_futures.BinanceFuturesClient.

Usage:
    export BINANCE_API_KEY=...
    export BINANCE_API_SECRET=...
    python trade/tests/test_binance_futures_client.py
    或
    python -m trade.tests.test_binance_futures_client

This script first runs the official SDK sample (exchange_information) to verify
that credentials, network access, and SDK wiring are correct. It then invokes
key helper methods defined in common.binance_futures.BinanceFuturesClient and prints a
few sample rows from each response so you can confirm live data is accessible.
"""

import logging
import os
import sys
from pathlib import Path
from typing import List
from datetime import datetime, timedelta

# 添加项目根目录到Python路径，以便导入项目模块（tests现在在trade/tests下）
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from binance_common.configuration import ConfigurationRestAPI
from binance_common.constants import (
    DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL,
)
from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import (
    DerivativesTradingUsdsFutures,
)
from binance_sdk_derivatives_trading_usds_futures.rest_api.models import (
    ExchangeInformationResponse,
    Ticker24hrPriceChangeStatisticsResponse,
)

from trade.common.binance_futures import BinanceFuturesClient
import trade.common.config as config
BINANCE_API_KEY = getattr(config, 'BINANCE_API_KEY', None)
BINANCE_API_SECRET = getattr(config, 'BINANCE_API_SECRET', None)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


def _load_credentials() -> tuple[str, str]:
    api_key = BINANCE_API_KEY or os.getenv("BINANCE_API_KEY")
    api_secret = BINANCE_API_SECRET or os.getenv("BINANCE_API_SECRET")
    if not api_key or not api_secret:
        raise RuntimeError(
            "Please configure BINANCE_API_KEY and BINANCE_API_SECRET in config.py or env vars before running this test."
        )
    return api_key, api_secret


def sdk_exchange_information_health_check(api_key: str, api_secret: str) -> None:
    """Run the official SDK sample to confirm connectivity and signing."""
    logging.info("Running exchange_information() health check via official SDK...")
    configuration = ConfigurationRestAPI(
        api_key=api_key,
        api_secret=api_secret,
        base_path=DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL,
    )

    client = DerivativesTradingUsdsFutures(config_rest_api=configuration)

    try:
        response = client.rest_api.ticker24hr_price_change_statistics()

        rate_limits = response.rate_limits
        raw_data = response.data()
        logging.info("ticker24hr_price_change_statistics() rate limits: %s", rate_limits)

        if raw_data is None:
            entries = []
        elif isinstance(raw_data, list):
            entries = raw_data
        else:
            entries = [raw_data]

        logging.info("ticker24hr_price_change_statistics() raw entries: %s", len(entries))

        def _convert_entry(model) -> dict | list | None:
            if model is None:
                return None
            if isinstance(model, dict):
                return model
            try:
                # 官方响应模型提供 to_dict，可直接展开 Union 结构
                return Ticker24hrPriceChangeStatisticsResponse.to_dict(model)
            except Exception:
                pass
            if hasattr(model, "to_dict"):
                try:
                    return model.to_dict()
                except Exception:
                    return None
            return None

        def _extract_dicts(node) -> List[dict]:
            if node is None:
                return []
            if isinstance(node, list):
                flattened: List[dict] = []
                for item in node:
                    flattened.extend(_extract_dicts(item))
                return flattened
            parsed = _convert_entry(node)
            if parsed is None:
                return []
            if isinstance(parsed, list):
                flattened: List[dict] = []
                for item in parsed:
                    flattened.extend(_extract_dicts(item))
                return flattened

            #logging.info(f"ticker24hr_price_change_statistics() response: {parsed}")
            return [parsed]

        detailed_samples = []
        for entry in entries:
            for parsed in _extract_dicts(entry):
                symbol = parsed.get("symbol") or parsed.get("s")
                detail = {
                    "symbol": symbol,
                    "last_price": parsed.get("lastPrice") or parsed.get("c"),
                    "price_change_percent": parsed.get("priceChangePercent") or parsed.get("P"),
                    "high_price": parsed.get("highPrice") or parsed.get("h"),
                    "low_price": parsed.get("lowPrice") or parsed.get("l"),
                    "quote_volume": parsed.get("quoteVolume") or parsed.get("q"),
                }
                detailed_samples.append(detail)
                if len(detailed_samples) >= 5:
                    break
            if len(detailed_samples) >= 5:
                break

        if detailed_samples:
            logging.info("Sample ticker24hr stats:")
            logging.info("ticker24hr_price_change_statistics() detailed_samples: %s", len(detailed_samples))
            for idx, item in enumerate(detailed_samples, start=1):
                logging.info(
                    "  #%d %s | last=%s | change=%s%% | high=%s | low=%s | quote_volume=%s",
                    idx,
                    item.get("symbol") or "N/A",
                    item.get("last_price"),
                    item.get("price_change_percent"),
                    item.get("high_price"),
                    item.get("low_price"),
                    item.get("quote_volume"),
                )
        else:
            logging.warning("ticker24hr_price_change_statistics() returned no parsable entries")

    except Exception as e:
        logging.error(f"ticker24hr_price_change_statistics() error: {e}")


def _log_sample(name: str, payload) -> None:
    if isinstance(payload, list):
        sample = payload[:3]
    elif isinstance(payload, dict):
        sample = list(payload.items())[:3]
    else:
        sample = payload
    logging.info("%s sample: %s", name, sample)


def exercise_binance_futures_client(api_key: str, api_secret: str) -> None:
    client = BinanceFuturesClient(api_key=api_key, api_secret=api_secret)
    logging.info("Created BinanceFuturesClient: quote_asset=%s", client.quote_asset)

    #logging.info("Testing get_top_gainers()...")
    #top_gainers = client.get_top_gainers(limit=10)
    #_log_sample("top_gainers", top_gainers)


    symbols: List[str] = ["MYXUSDT", "ESPORTSUSDT", "CROSSUSDT"]

    #logging.info("Testing get_24h_ticker()...")
    #ticker_24h = client.get_24h_ticker(symbols)
    #_log_sample("ticker_24h", ticker_24h)

    #logging.info("Testing get_symbol_prices()...")
    #symbol_prices = client.get_symbol_prices(symbols)
    #_log_sample("symbol_prices", symbol_prices)

    logging.info("Testing get_klines()...")
    klines = client.get_klines(symbol="MYXUSDT", interval="1m", limit=5)
    _log_sample("klines", klines)

    # 获取今天和昨天的日K线数据，使用limit=2验证是否能获取两条K线
    logging.info("Testing get_klines() for today and yesterday daily data with limit=2...")
    
    # 获取最近两天的日K线数据
    klines_daily = client.get_klines(symbol="MYXUSDT", interval="1d", limit=2)
    
    # 打印结果
    logging.info(f"Daily klines count: {len(klines_daily)}")
    for i, kline in enumerate(klines_daily):
        logging.info(f"Daily kline #{i+1}:")
        logging.info(f"  开盘时间: {kline.get('open_time')} ({kline.get('open_time_dt')})")
        logging.info(f"  开盘价: {kline.get('open')}")
        logging.info(f"  最高价: {kline.get('high')}")
        logging.info(f"  最低价: {kline.get('low')}")
        logging.info(f"  收盘价: {kline.get('close')}")
        logging.info(f"  成交量: {kline.get('volume')}")
        logging.info(f"  收盘时间: {kline.get('close_time')} ({kline.get('close_time_dt')})")
        logging.info(f"  成交额: {kline.get('quote_asset_volume')}")
        logging.info(f"  成交笔数: {kline.get('number_of_trades')}")
        logging.info(f"  主动买入成交量: {kline.get('taker_buy_base_volume')}")
        logging.info(f"  主动买入成交额: {kline.get('taker_buy_quote_volume')}")
    
    # 验证是否获取到了两条K线数据
    if len(klines_daily) == 2:
        logging.info("Successfully retrieved 2 daily klines as expected")
    else:
        logging.warning(f"Expected 2 daily klines, but got {len(klines_daily)}")
        
    logging.info("All BinanceFuturesClient method calls completed.")


if __name__ == "__main__":
    api_key_value, api_secret_value = _load_credentials()
    #sdk_exchange_information_health_check(api_key_value, api_secret_value)
    exercise_binance_futures_client(api_key_value, api_secret_value)

