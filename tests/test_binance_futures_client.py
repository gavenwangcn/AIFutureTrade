"""Manual connectivity test harness for binance_futures.BinanceFuturesClient.

Usage:
    export BINANCE_API_KEY=...
    export BINANCE_API_SECRET=...
    python tests/test_binance_futures_client.py

This script first runs the official SDK sample (exchange_information) to verify
that credentials, network access, and SDK wiring are correct. It then invokes
key helper methods defined in binance_futures.BinanceFuturesClient and prints a
few sample rows from each response so you can confirm live data is accessible.
"""

import logging
import os
from typing import List

from binance_common.configuration import ConfigurationRestAPI
from binance_common.constants import (
    DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL,
)
from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import (
    DerivativesTradingUsdsFutures,
)
from binance_sdk_derivatives_trading_usds_futures.rest_api.models import (
    ExchangeInformationResponse,
)

from binance_futures import BinanceFuturesClient
from config import BINANCE_API_KEY, BINANCE_API_SECRET

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
        data = response.data()
        logging.info(f"ticker24hr_price_change_statistics() response: {data}")
        logging.info(f"ticker24hr_price_change_statistics() rate limits: {rate_limits}")
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

    logging.info("Testing get_top_gainers()...")
    top_gainers = client.get_top_gainers(limit=5)
    _log_sample("top_gainers", top_gainers)

  ##  logging.info("Testing get_all_tickers()...")
  #  all_tickers = client.get_all_tickers()
  #  _log_sample("all_tickers", all_tickers)

   # symbols: List[str] = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

  #  logging.info("Testing get_24h_ticker()...")
   # ticker_24h = client.get_24h_ticker(symbols)
   # _log_sample("ticker_24h", ticker_24h)

  #  logging.info("Testing get_symbol_prices()...")
  #  symbol_prices = client.get_symbol_prices(symbols)
  #  _log_sample("symbol_prices", symbol_prices)

   # logging.info("Testing get_klines()...")
   # klines = client.get_klines(symbol="BTCUSDT", interval="1m", limit=5)
   # _log_sample("klines", klines)

    logging.info("All BinanceFuturesClient method calls completed.")


if __name__ == "__main__":
    api_key_value, api_secret_value = _load_credentials()
    #sdk_exchange_information_health_check(api_key_value, api_secret_value)
    exercise_binance_futures_client(api_key_value, api_secret_value)
