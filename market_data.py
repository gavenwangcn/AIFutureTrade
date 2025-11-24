"""
Market Data Fetcher - Real-time market data from Binance USDS-M futures SDK
"""
import time
import logging
import threading
import config as app_config
from datetime import datetime
from typing import Dict, List, Optional

from binance_futures import BinanceFuturesClient

logger = logging.getLogger(__name__)


class MarketDataFetcher:
    """Fetch real-time market data from Binance USDS-M futures with caching and fallback"""

    def __init__(self, db):
        """Initialize market data fetcher"""
        self.db = db
        self._cache = {}
        self._cache_time = {}
        self._cache_duration = getattr(app_config, 'MARKET_API_CACHE', 5)

        self._last_live_prices: Dict[str, Dict] = {}
        self._last_live_date: Optional[datetime.date] = None

        self._futures_client: Optional[BinanceFuturesClient] = None
        self._last_gainers_update: float = 0
        self._gainers_refresh = getattr(app_config, 'FUTURES_TOP_GAINERS_REFRESH', 3600)
        self._indicator_cache: Dict[str, Dict] = {}
        self._indicator_refresh = getattr(app_config, 'FUTURES_INDICATOR_REFRESH', 2)
        self._futures_kline_limit = getattr(app_config, 'FUTURES_KLINE_LIMIT', 120)
        self._futures_quote_asset = getattr(app_config, 'FUTURES_QUOTE_ASSET', 'USDT')
        self._leaderboard_refresh = getattr(app_config, 'FUTURES_LEADERBOARD_REFRESH', 180)
        self._last_leaderboard_sync: float = 0
        self._leaderboard_lock = threading.Lock()
        self._init_futures_client()

    # ============ Initialization Methods ============

    def _init_futures_client(self):
        """Initialize Binance futures client"""
        api_key = getattr(app_config, 'BINANCE_API_KEY', '')
        api_secret = getattr(app_config, 'BINANCE_API_SECRET', '')
        if not api_key or not api_secret:
            logger.warning('[Futures] Binance API key/secret not configured; live data unavailable')
            self._futures_client = None
            return

        try:
            self._futures_client = BinanceFuturesClient(
                api_key=api_key,
                api_secret=api_secret,
                quote_asset=self._futures_quote_asset,
                testnet=getattr(app_config, 'BINANCE_TESTNET', False)
            )
            logger.info('[Futures] Binance futures client initialized')
        except Exception as exc:
            logger.warning(f'[Futures] Unable to initialize Binance futures client: {exc}')
            self._futures_client = None

    # ============ Helper/Utility Methods ============

    def _log_api_error(self, api_name: str, scenario: str, error_type: str,
                       symbol: str = None, error_msg: str = "", level: str = "WARN"):
        """Unified API error logging format"""
        symbol_str = f"[币种:{symbol}]" if symbol else ""
        log_msg = f"[API:{api_name.upper()}][场景:{scenario}]{symbol_str}[错误类型:{error_type}] {error_msg}"

        if level == "ERROR":
            logger.error(log_msg)
        elif level == "INFO":
            logger.info(log_msg)
        else:
            logger.warning(log_msg)

    def _get_configured_futures(self) -> List[Dict]:
        """Get configured futures from database"""
        futures = self.db.get_future_configs()
        if not futures:
            logger.warning('[配置] 未检测到任何已持仓的USDS-M合约，等待交易产生持仓后自动记录')
        return futures

    def _format_stored_prices(self, stored_prices: Dict[str, Dict], symbols: Optional[List[str]] = None) -> Dict[str, Dict]:
        """Format stored prices for display"""
        future_map = {future['symbol']: future for future in self._get_configured_futures()}
        target_symbols = symbols or list(future_map.keys()) or list(stored_prices.keys())
        formatted: Dict[str, Dict] = {}

        for symbol in target_symbols:
            stored = stored_prices.get(symbol)
            future = future_map.get(symbol, {})
            if not stored:
                continue

            formatted[symbol] = {
                'price': stored.get('price', 0),
                'name': future.get('name', symbol),
                'exchange': future.get('exchange', ''),
                'change_24h': 0,
                'price_date': stored.get('price_date'),
                'source': 'closing'
            }

        return formatted

    # ============ Price Fetching Methods ============

    def get_prices(self, symbols: Optional[List[str]] = None) -> Dict[str, Dict]:
        """Return latest prices with 24/7 trading support"""
        now = datetime.now()
        live_prices = self.get_current_prices(symbols)
        if live_prices:
            for payload in live_prices.values():
                payload['source'] = 'live'
                payload['price_date'] = now.strftime('%Y-%m-%d')
            self._last_live_prices = live_prices
            self._last_live_date = now.date()
            return live_prices

        stored_prices = self.db.get_latest_daily_prices(symbols)
        formatted = self._format_stored_prices(stored_prices, symbols)

        target_symbols = symbols or [future['symbol'] for future in self._get_configured_futures()]
        missing_symbols = [sym for sym in target_symbols if sym not in formatted]

        if missing_symbols:
            live_prices = self.get_current_prices(missing_symbols)
            if live_prices:
                price_date = now.strftime('%Y-%m-%d')
                if not self._last_live_prices:
                    self._last_live_prices = {}
                for symbol, payload in live_prices.items():
                    payload['source'] = 'live_fallback'
                    payload['price_date'] = price_date
                    formatted[symbol] = payload
                    self._last_live_prices[symbol] = payload.copy()
                    try:
                        self.db.upsert_daily_price(symbol, float(payload.get('price', 0)), price_date)
                    except Exception as err:
                        self._log_api_error(
                            api_name="数据库",
                            scenario="数据持久化",
                            error_type="持久化错误",
                            symbol=symbol,
                            error_msg=f"保存回退价格失败: {str(err)}"
                        )
                self._last_live_date = now.date()

        # Fallback to most recent live snapshot if still no data
        if not formatted and self._last_live_prices:
            fallback: Dict[str, Dict] = {}
            for symbol, payload in self._last_live_prices.items():
                if symbols and symbol not in symbols:
                    continue
                fallback[symbol] = {
                    **payload,
                    'source': payload.get('source', 'previous_live'),
                    'price_date': payload.get('price_date') or (self._last_live_date.strftime('%Y-%m-%d') if self._last_live_date else None)
                }
            return fallback

        return formatted

    def get_current_prices(self, symbols: List[str] = None) -> Dict[str, Dict]:
        """Get current futures prices using Binance SDK with caching/fallback"""
        futures = self._get_configured_futures()
        if not futures:
            return {}

        if symbols:
            futures = [f for f in futures if f['symbol'] in symbols]

        if not futures:
            return {}

        cache_key = 'prices_' + '_'.join(sorted([f['symbol'] for f in futures]))
        if cache_key in self._cache:
            if time.time() - self._cache_time[cache_key] < self._cache_duration:
                return self._cache[cache_key]

        prices = self._fetch_from_binance_futures(futures)

        # Fallback to last known prices when futures client unavailable or missing data
        missing_symbols = [f['symbol'] for f in futures if f['symbol'] not in prices]
        for symbol in missing_symbols:
            last_price = self._last_live_prices.get(symbol, {}).get('price', 0)
            prices[symbol] = {
                'price': last_price if last_price > 0 else 0,
                'name': symbol,
                'exchange': 'BINANCE_FUTURES',
                'change_24h': 0,
                'daily_volume': 0,
                'timeframes': self._indicator_cache.get(symbol, {}).get('data', {})
            }

        self._cache[cache_key] = prices
        self._cache_time[cache_key] = time.time()
        return prices

    def _fetch_from_binance_futures(self, futures: List[Dict]) -> Dict[str, Dict]:
        """Fetch prices from Binance futures API"""
        prices: Dict[str, Dict] = {}
        if not futures or not self._futures_client:
            return prices

        symbol_map = {}
        for future in futures:
            base_symbol = future['symbol']
            contract_symbol = future.get('contract_symbol') or self._futures_client.format_symbol(base_symbol)
            symbol_map[base_symbol] = contract_symbol.upper()
        tickers = self._futures_client.get_24h_ticker(list(symbol_map.values()))
        spot_prices = self._futures_client.get_symbol_prices(list(symbol_map.values()))

        for symbol, futures_symbol in symbol_map.items():
            payload = tickers.get(futures_symbol)
            if not payload:
                continue
            try:
                last_price = float(
                    payload.get('lastPrice')
                    or spot_prices.get(futures_symbol, {}).get('price', 0)
                )
                change_percent = float(payload.get('priceChangePercent', 0))
                quote_volume = float(payload.get('quoteVolume', payload.get('volume', 0)))
            except (ValueError, TypeError):
                continue

            timeframe_data = self._get_timeframe_indicators(symbol)
            future_meta = next((f for f in futures if f['symbol'] == symbol), {})
            prices[symbol] = {
                'price': last_price,
                'name': future_meta.get('name', symbol),
                'exchange': future_meta.get('exchange', 'BINANCE_FUTURES'),
                'change_24h': change_percent,
                'daily_volume': quote_volume,
                'timeframes': timeframe_data
            }

        return prices

    # ============ Technical Indicator Methods ============

    def calculate_technical_indicators(self, symbol: str) -> Dict:
        """Calculate futures-oriented technical indicators"""
        try:
            timeframe_data = self._get_timeframe_indicators(symbol)
            if timeframe_data:
                return {'timeframes': timeframe_data}
            return {}
        except Exception as e:
            self._log_api_error(
                api_name="技术指标",
                scenario="技术指标计算",
                error_type="计算错误",
                symbol=symbol,
                error_msg=f"计算技术指标时发生错误: {str(e)[:200]}",
                level="ERROR"
            )
            return {}

    def _get_timeframe_indicators(self, symbol: str) -> Dict:
        """Get timeframe indicators with caching"""
        if not self._futures_client:
            return {}

        cache = self._indicator_cache.get(symbol)
        now_ts = time.time()
        if cache and now_ts - cache['timestamp'] < self._indicator_refresh:
            return cache['data']

        timeframe_map = {
            '1w': '1w',
            '1d': '1d',
            '4h': '4h',
            '1h': '1h',
            '15m': '15m',
            '5m': '5m',
            '1m': '1m'
        }
        ma_lengths = [5, 20, 60, 99]
        symbol_key = self._futures_client.format_symbol(symbol)
        data: Dict[str, Dict] = {}

        for label, interval in timeframe_map.items():
            klines = self._futures_client.get_klines(symbol_key, interval, limit=self._futures_kline_limit)
            closes = [float(item[4]) for item in klines if len(item) > 4]
            volumes = [float(item[5]) for item in klines if len(item) > 5]
            if not closes:
                continue
            ma_values = {}
            for length in ma_lengths:
                if len(closes) >= length:
                    ma_values[f'ma{length}'] = sum(closes[-length:]) / length
                else:
                    ma_values[f'ma{length}'] = sum(closes) / len(closes)
            macd = self._calculate_macd(closes)
            rsi = self._calculate_rsi(closes)
            vol = volumes[-1] if volumes else 0
            data[label] = {
                'close': closes[-1],
                'ma': ma_values,
                'macd': macd,
                'rsi': rsi,
                'vol': vol
            }

        self._indicator_cache[symbol] = {
            'timestamp': now_ts,
            'data': data
        }
        return data


    def _calculate_macd(self, closes: List[float]) -> float:
        """Calculate MACD indicator"""
        if len(closes) < 26:
            return 0.0
        ema12 = self._calculate_ema(closes, 12)
        ema26 = self._calculate_ema(closes, 26)
        return ema12 - ema26

    def _calculate_ema(self, closes: List[float], period: int) -> float:
        """Calculate Exponential Moving Average"""
        if len(closes) < period:
            return sum(closes) / len(closes) if closes else 0.0
        multiplier = 2.0 / (period + 1)
        ema = sum(closes[:period]) / period
        for price in closes[period:]:
            ema = (price - ema) * multiplier + ema
        return ema

    def _calculate_rsi(self, closes: List[float], period: int = 14) -> float:
        """Calculate Relative Strength Index"""
        if len(closes) < period + 1:
            return 50.0
        changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [change if change > 0 else 0 for change in changes[-period:]]
        losses = [-change if change < 0 else 0 for change in changes[-period:]]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    # ============ Leaderboard Methods ============

    def sync_leaderboard(self, force: bool = False, limit: Optional[int] = None) -> Dict[str, List[Dict]]:
        """Sync leaderboard data from Binance and update database"""
        if limit is None:
            limit = getattr(app_config, 'FUTURES_TOP_GAINERS_LIMIT', 10)

        if not self._futures_client:
            return self.db.get_futures_leaderboard(limit=limit)

        now = time.time()
        if not force and now - self._last_leaderboard_sync < self._leaderboard_refresh:
            return self.db.get_futures_leaderboard(limit=limit)

        with self._leaderboard_lock:
            now = time.time()
            if not force and now - self._last_leaderboard_sync < self._leaderboard_refresh:
                return self.db.get_futures_leaderboard(limit=limit)

            try:
                entries = self._build_leaderboard_entries(limit)
                if entries:
                    self.db.upsert_leaderboard_entries(entries)
                    self._last_leaderboard_sync = now
            except Exception as exc:
                self._log_api_error(
                    api_name='Binance Futures',
                    scenario='涨跌幅榜同步',
                    error_type='数据处理错误',
                    error_msg=str(exc),
                    level='ERROR'
                )

        return self.db.get_futures_leaderboard(limit=limit)

    def get_leaderboard(self, limit: Optional[int] = None) -> Dict[str, List[Dict]]:
        """Get leaderboard data (wrapper for sync_leaderboard)"""
        return self.sync_leaderboard(force=False, limit=limit)

    def _build_leaderboard_entries(self, limit: int) -> List[Dict]:
        """Build leaderboard entries from Binance ticker data"""
        tickers = self._futures_client.get_all_tickers()
        if not tickers:
            return []

        filtered = [
            item for item in tickers
            if item.get('symbol', '').endswith(self._futures_client.quote_asset)
        ]

        def sort_key(item):
            try:
                return float(item.get('priceChangePercent', 0))
            except (TypeError, ValueError):
                return 0.0

        gainers = sorted(filtered, key=sort_key, reverse=True)[:limit]
        losers = sorted(filtered, key=sort_key)[:limit]

        entries: List[Dict] = []
        for side, collection in (('gainer', gainers), ('loser', losers)):
            for idx, item in enumerate(collection):
                contract_symbol = item.get('symbol', '')
                if not contract_symbol or not contract_symbol.endswith(self._futures_client.quote_asset):
                    continue
                base_symbol = contract_symbol[:-len(self._futures_client.quote_asset)]
                if not base_symbol:
                    continue
                try:
                    price = float(item.get('lastPrice') or item.get('close') or 0)
                except (TypeError, ValueError):
                    price = 0
                try:
                    change_percent = float(item.get('priceChangePercent', 0))
                except (TypeError, ValueError):
                    change_percent = 0
                try:
                    quote_volume = float(item.get('quoteVolume', item.get('volume', 0)))
                except (TypeError, ValueError):
                    quote_volume = 0

                timeframe_data = self._get_timeframe_indicators(base_symbol)

                entries.append({
                    'symbol': base_symbol,
                    'contract_symbol': contract_symbol,
                    'name': base_symbol,
                    'exchange': 'BINANCE_FUTURES',
                    'side': side,
                    'rank': idx + 1,
                    'price': price,
                    'change_percent': change_percent,
                    'quote_volume': quote_volume,
                    'timeframes': timeframe_data
                })

        return entries
