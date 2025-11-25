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
        self._cache_duration = getattr(app_config, 'MARKET_API_CACHE', 2)

        self._last_live_prices: Dict[str, Dict] = {}
        self._last_live_date: Optional[datetime.date] = None

        self._futures_client: Optional[BinanceFuturesClient] = None
        self._last_gainers_update: float = 0
        self._gainers_refresh = getattr(app_config, 'FUTURES_TOP_GAINERS_REFRESH', 3600)
        self._indicator_cache: Dict[str, Dict] = {}
        self._indicator_refresh = getattr(app_config, 'FUTURES_INDICATOR_REFRESH', 2)
        self._futures_kline_limit = getattr(app_config, 'FUTURES_KLINE_LIMIT', 120)
        self._futures_quote_asset = getattr(app_config, 'FUTURES_QUOTE_ASSET', 'USDT')
        self._leaderboard_refresh = getattr(app_config, 'FUTURES_LEADERBOARD_REFRESH', 10)
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

    # ============ Price Fetching Methods ============

    def get_prices(self, symbols: Optional[List[str]] = None) -> Dict[str, Dict]:
        """
        获取最新价格数据（仅使用实时数据）
        
        优先返回实时价格，如果无法获取实时数据，则返回最近一次缓存的实时价格快照。
        
        Args:
            symbols: 可选的交易对符号列表，如果为None则返回所有已配置的交易对
            
        Returns:
            价格数据字典，key为交易对符号，value为价格信息
        """
        now = datetime.now()
        
        # 尝试获取实时价格
        live_prices = self.get_current_prices(symbols)
        if live_prices:
            # 标记为实时数据并更新缓存
            for payload in live_prices.values():
                payload['source'] = 'live'
                payload['price_date'] = now.strftime('%Y-%m-%d')
            self._last_live_prices = live_prices
            self._last_live_date = now.date()
            return live_prices

        # 如果无法获取实时数据，返回最近一次缓存的实时价格快照
        if self._last_live_prices:
            fallback: Dict[str, Dict] = {}
            for symbol, payload in self._last_live_prices.items():
                if symbols and symbol not in symbols:
                    continue
                fallback[symbol] = {
                    **payload,
                    'source': payload.get('source', 'previous_live'),
                    'price_date': payload.get('price_date') or (
                        self._last_live_date.strftime('%Y-%m-%d') if self._last_live_date else None
                    )
                }
            return fallback

        # 如果没有任何数据，返回空字典
        return {}

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
                'timeframes': self._indicator_cache.get(symbol, {}).get('data', {}).get(symbol, {})
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
            # 新格式：{symbol: {1w: {...}, 1d: {...}}}
            # 提取 symbol 对应的数据
            timeframes = timeframe_data.get(symbol, {}) if timeframe_data else {}
            
            future_meta = next((f for f in futures if f['symbol'] == symbol), {})
            prices[symbol] = {
                'price': last_price,
                'name': future_meta.get('name', symbol),
                'exchange': future_meta.get('exchange', 'BINANCE_FUTURES'),
                'change_24h': change_percent,
                'daily_volume': quote_volume,
                'timeframes': timeframes
            }

        return prices

    # ============ Technical Indicator Methods ============

    def calculate_technical_indicators(self, symbol: str) -> Dict:
        """
        计算技术指标
        
        Args:
            symbol: 交易对符号
            
        Returns:
            格式：{'timeframes': {1w: {kline: {}, ma: {}, macd: {}, rsi: {}, vol: {}}, 1d: {...}}}
        """
        try:
            timeframe_data = self._get_timeframe_indicators(symbol)
            # 新格式：{symbol: {1w: {...}, 1d: {...}}}
            # 提取 symbol 对应的数据
            if timeframe_data and symbol in timeframe_data:
                return {'timeframes': timeframe_data[symbol]}
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
        """
        获取指定交易对的所有时间框架技术指标
        
        计算每个时间框架的：
        - K线数据（最新一根K线）
        - MA值（5、20、60、99周期）
        - MACD指标（DIF、DEA、BAR）
        - RSI指标（RSI6、RSI9）
        - 成交量（VOL）
        
        Args:
            symbol: 交易对符号（如 'BTC'）
            
        Returns:
            格式：{symbol: {1w: {kline: {}, ma: {}, macd: {}, rsi: {}, vol: {}}, 1d: {...}}}
        """
        if not self._futures_client:
            return {}

        # 检查缓存
        cache = self._indicator_cache.get(symbol)
        now_ts = time.time()
        if cache and now_ts - cache['timestamp'] < self._indicator_refresh:
            return cache['data']

        # 时间框架映射
        timeframe_map = {
            '1w': '1w',
            '1d': '1d',
            '4h': '4h',
            '1h': '1h',
            '15m': '15m',
            '5m': '5m',
            '1m': '1m'
        }
        
        # MA周期列表
        ma_lengths = [5, 20, 60, 99]
        
        # 格式化交易对符号（添加计价资产后缀）
        symbol_key = self._futures_client.format_symbol(symbol)
        
        # 存储所有时间框架的数据
        timeframe_data: Dict[str, Dict] = {}

        # 遍历每个时间框架
        for label, interval in timeframe_map.items():
            try:
                # 获取K线数据
                klines = self._futures_client.get_klines(symbol_key, interval, limit=self._futures_kline_limit)
                
                if not klines or len(klines) == 0:
                    continue
                
                # 提取收盘价和成交量
                closes = [float(item[4]) for item in klines if len(item) > 4]
                volumes = [float(item[5]) for item in klines if len(item) > 5]
                
                if not closes:
                    continue
                
                # 获取最新一根K线数据
                latest_kline = klines[-1]
                kline_data = {
                    'open_time': latest_kline[0] if len(latest_kline) > 0 else None,
                    'open': float(latest_kline[1]) if len(latest_kline) > 1 else 0.0,
                    'high': float(latest_kline[2]) if len(latest_kline) > 2 else 0.0,
                    'low': float(latest_kline[3]) if len(latest_kline) > 3 else 0.0,
                    'close': float(latest_kline[4]) if len(latest_kline) > 4 else 0.0,
                    'volume': float(latest_kline[5]) if len(latest_kline) > 5 else 0.0
                }
                
                # 计算MA值（简单移动平均）
                ma_values = self._calculate_ma_values(closes, ma_lengths)
                
                # 计算MACD指标
                macd = self._calculate_macd(closes)
                
                # 计算RSI指标
                rsi = self._calculate_rsi(closes)
                
                # 获取最新成交量
                vol = volumes[-1] if volumes else 0.0
                
                # 组装该时间框架的数据
                timeframe_data[label] = {
                    'kline': kline_data,
                    'ma': ma_values,
                    'macd': macd,
                    'rsi': rsi,
                    'vol': vol
                }
                
            except Exception as e:
                logger.warning(
                    f"[技术指标] 计算 {symbol} {label} 时间框架指标失败: {e}",
                    exc_info=True
                )
                continue

        # 缓存结果
        result = {symbol: timeframe_data}
        self._indicator_cache[symbol] = {
            'timestamp': now_ts,
            'data': result
        }
        
        return result

    def _calculate_ma_values(self, closes: List[float], ma_lengths: List[int]) -> Dict[str, float]:
        """
        计算简单移动平均（MA）值
        
        MA(N) = 近N个交易日的收盘价之和 ÷ N
        
        如果数据不足N个，则使用所有可用数据的平均值。
        
        Args:
            closes: 收盘价列表（按时间顺序，最新的在最后）
            ma_lengths: MA周期列表，如 [5, 20, 60, 99]
            
        Returns:
            包含各周期MA值的字典，如 {'ma5': 100.5, 'ma20': 98.3, ...}
        """
        ma_values = {}
        
        for length in ma_lengths:
            if len(closes) >= length:
                # 数据充足：使用最近N个收盘价的平均值
                # 取最后N个收盘价（最新的在最后）
                recent_closes = closes[-length:]
                ma_value = sum(recent_closes) / length
                ma_values[f'ma{length}'] = ma_value
            else:
                # 数据不足：使用所有可用数据的平均值
                if len(closes) > 0:
                    ma_value = sum(closes) / len(closes)
                    ma_values[f'ma{length}'] = ma_value
                else:
                    ma_values[f'ma{length}'] = 0.0
        
        return ma_values


    def _calculate_macd(self, closes: List[float]) -> Dict[str, float]:
        """
        计算MACD指标（指数平滑异同移动平均线）
        
        MACD计算过程：
        1. 计算EMA(12)和EMA(26)
        2. 计算DIF = EMA(12) - EMA(26)
        3. 计算DEA = DIF的9日EMA（信号线）
        4. 计算BAR = (DIF - DEA) × 2（柱状线）
        
        Args:
            closes: 收盘价列表
            
        Returns:
            包含DIF、DEA、BAR的字典，如果数据不足则返回默认值
        """
        # 需要至少26个数据点才能计算EMA(26)
        if len(closes) < 26:
            return {'dif': 0.0, 'dea': 0.0, 'bar': 0.0}
        
        # 步骤1：计算EMA(12)和EMA(26)的历史序列
        ema12_series = self._calculate_ema_series(closes, 12)
        ema26_series = self._calculate_ema_series(closes, 26)
        
        # 步骤2：计算DIF序列 = EMA(12) - EMA(26)
        dif_series = [ema12_series[i] - ema26_series[i] for i in range(len(closes))]
        
        # 获取最新的DIF值
        dif = dif_series[-1]
        
        # 步骤3：计算DEA（DIF的9日EMA）
        # 需要至少9个DIF值才能计算DEA
        if len(dif_series) < 9:
            return {'dif': dif, 'dea': 0.0, 'bar': 0.0}
        
        dea = self._calculate_ema(dif_series, 9)
        
        # 步骤4：计算BAR = (DIF - DEA) × 2
        bar = (dif - dea) * 2
        
        return {
            'dif': dif,
            'dea': dea,
            'bar': bar
        }

    def _calculate_ema_series(self, closes: List[float], period: int) -> List[float]:
        """
        计算EMA序列（返回所有历史EMA值）
        
        为了保持序列长度一致，前period-1个数据点使用简单移动平均作为初始值。
        
        Args:
            closes: 收盘价列表
            period: EMA周期
            
        Returns:
            EMA值序列，长度与closes相同
        """
        if len(closes) < period:
            # 数据不足时，返回简单移动平均
            avg = sum(closes) / len(closes) if closes else 0.0
            return [avg] * len(closes)
        
        multiplier = 2.0 / (period + 1)
        ema_series = []
        
        # 前period-1个数据点使用简单移动平均（逐步增加窗口）
        for i in range(period - 1):
            if i == 0:
                ema_series.append(closes[0])
            else:
                avg = sum(closes[:i+1]) / (i + 1)
                ema_series.append(avg)
        
        # 从第period个数据点开始，使用标准EMA计算
        # 初始化：第一个有效EMA值使用前period个数据的简单平均
        ema = sum(closes[:period]) / period
        ema_series.append(ema)
        
        # 递推计算后续EMA值
        # EMA(n) = 今日收盘价 × (2/(n+1)) + 昨日EMA × ((n-1)/(n+1))
        for price in closes[period:]:
            ema = (price - ema) * multiplier + ema
            ema_series.append(ema)
        
        return ema_series

    def _calculate_ema(self, values: List[float], period: int) -> float:
        """
        计算指数移动平均线（EMA）的最终值
        
        公式：EMA(n) = 今日值 × (2/(n+1)) + 昨日EMA × ((n-1)/(n+1))
        
        Args:
            values: 数值列表（可以是收盘价或DIF序列）
            period: EMA周期
            
        Returns:
            EMA的最终值
        """
        if len(values) < period:
            return sum(values) / len(values) if values else 0.0
        
        multiplier = 2.0 / (period + 1)
        # 初始化：使用前period个数据的简单平均
        ema = sum(values[:period]) / period
        
        # 递推计算：EMA = 今日值 × multiplier + 昨日EMA × (1 - multiplier)
        for value in values[period:]:
            ema = (value - ema) * multiplier + ema
        
        return ema

    def _calculate_rsi(self, closes: List[float]) -> Dict[str, float]:
        """
        计算RSI（相对强弱指数）指标
        
        RSI计算过程：
        1. 计算每日涨跌幅度（涨幅和跌幅分开统计）
        2. 使用平滑平均计算平均涨幅和平均跌幅
        3. 计算RS = 平均涨幅 ÷ 平均跌幅
        4. 计算RSI = 100 - (100 ÷ (1 + RS))
        
        返回RSI(6)和RSI(9)两个值。
        
        Args:
            closes: 收盘价列表
            
        Returns:
            包含rsi6和rsi9的字典，如果数据不足则返回默认值
        """
        result = {'rsi6': 50.0, 'rsi9': 50.0}
        
        # 计算RSI(6)
        if len(closes) >= 7:  # 需要至少7个数据点（6个周期+1个用于计算变化）
            rsi6 = self._calculate_rsi_single(closes, 6)
            result['rsi6'] = rsi6
        
        # 计算RSI(9)
        if len(closes) >= 10:  # 需要至少10个数据点（9个周期+1个用于计算变化）
            rsi9 = self._calculate_rsi_single(closes, 9)
            result['rsi9'] = rsi9
        
        return result

    def _calculate_rsi_single(self, closes: List[float], period: int) -> float:
        """
        计算单个周期的RSI值
        
        使用平滑平均（类似EMA）：
        - 首次计算：使用简单平均
        - 后续计算：平滑平均 = (前n-1天平均值 × (n-1) + 今日值) ÷ n
        
        Args:
            closes: 收盘价列表
            period: RSI周期（如6、9、14）
            
        Returns:
            RSI值（0-100之间）
        """
        if len(closes) < period + 1:
            return 50.0
        
        # 步骤1：计算每日涨跌幅度
        changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [change if change > 0 else 0.0 for change in changes]
        losses = [-change if change < 0 else 0.0 for change in changes]
        
        # 步骤2：计算平滑平均涨幅和平均跌幅
        # 首次计算（第period天）：使用简单平均
        initial_gains = gains[:period]
        initial_losses = losses[:period]
        avg_gain = sum(initial_gains) / period
        avg_loss = sum(initial_losses) / period
        
        # 后续计算（第period+1天及以后）：使用平滑平均
        # 平滑平均 = (前n-1天平均值 × (n-1) + 今日值) ÷ n
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
        # 步骤3：计算RS = 平均涨幅 ÷ 平均跌幅
        if avg_loss == 0:
            # 如果平均跌幅为0，说明没有下跌，RSI应该接近100
            return 100.0
        
        rs = avg_gain / avg_loss
        
        # 步骤4：计算RSI = 100 - (100 ÷ (1 + RS))
        rsi = 100 - (100 / (1 + rs))
        
        return rsi

    # ============ Leaderboard Methods ============

    def sync_leaderboard(self, force: bool = False, limit: Optional[int] = None) -> Dict[str, List[Dict]]:
        """
        同步涨幅榜数据
        
        优化逻辑：
        1. 如果数据库中没有数据，立即通过SDK获取并更新
        2. 如果数据库有数据且未到刷新时间，返回缓存数据
        3. 如果数据库有数据但已到刷新时间，更新数据
        
        Args:
            force: 是否强制刷新，忽略刷新节流
            limit: 返回的数据条数限制
            
        Returns:
            涨幅榜数据字典，包含 gainers 和 losers
        """
        if limit is None:
            limit = getattr(app_config, 'FUTURES_TOP_GAINERS_LIMIT', 10)

        logger.info(
            '[Leaderboard] sync_leaderboard called | force=%s limit=%s refresh=%ss',
            force,
            limit,
            self._leaderboard_refresh
        )

        # 如果没有可用的币安客户端，直接返回数据库缓存
        if not self._futures_client:
            logger.warning('[Leaderboard] Binance client unavailable, returning cached DB data')
            return self.db.get_futures_leaderboard(limit=limit)

        # 先检查数据库中是否有数据
        cached_data = self.db.get_futures_leaderboard(limit=limit)
        has_cached_data = (
            len(cached_data.get('gainers', [])) > 0 or 
            len(cached_data.get('losers', [])) > 0
        )

        # 如果数据库中没有数据，立即强制从SDK获取
        if not has_cached_data:
            logger.info('[Leaderboard] 数据库中没有涨幅榜数据，立即从SDK获取并更新')
            force = True  # 强制刷新

        now = time.time()
        # 刷新节流：除非 force 或数据库为空，否则在刷新周期内直接返回数据库缓存
        if not force and now - self._last_leaderboard_sync < self._leaderboard_refresh:
            logger.debug('[Leaderboard] Skip refresh, last_sync=%.2fs ago (< %s)',
                         now - self._last_leaderboard_sync, self._leaderboard_refresh)
            return cached_data

        with self._leaderboard_lock:
            # 进入临界区后再次检查，避免并发线程重复刷新
            now = time.time()
            if not force and now - self._last_leaderboard_sync < self._leaderboard_refresh:
                logger.debug('[Leaderboard] Skip refresh (post-lock), another thread just updated')
                return self.db.get_futures_leaderboard(limit=limit)

            logger.info('[Leaderboard] Refreshing leaderboard from Binance...')
            sync_start = time.time()
            try:
                entries = self._build_leaderboard_entries(limit)
                logger.info('[Leaderboard] Raw entries fetched: %s', len(entries))
                if entries:
                    self.db.upsert_leaderboard_entries(entries)
                    self._last_leaderboard_sync = now
                    logger.info('[Leaderboard] DB updated successfully (elapsed %.2fs)',
                                time.time() - sync_start)
                else:
                    logger.warning('[Leaderboard] No entries returned from Binance, keep cached data')
            except Exception as exc:
                self._log_api_error(
                    api_name='Binance Futures',
                    scenario='涨跌幅榜同步',
                    error_type='数据处理错误',
                    error_msg=str(exc),
                    level='ERROR'
                )
                logger.exception('[Leaderboard] Failed to refresh leaderboard from Binance')

        # 返回更新后的数据
        data = self.db.get_futures_leaderboard(limit=limit)
        logger.info('[Leaderboard] Returning leaderboard payload: gainers=%s losers=%s',
                    len(data.get('gainers', [])), len(data.get('losers', [])))
        return data

    def get_leaderboard(self, limit: Optional[int] = None) -> Dict[str, List[Dict]]:
        """Get leaderboard data (wrapper for sync_leaderboard)"""
        return self.sync_leaderboard(force=False, limit=limit)

    def _build_leaderboard_entries(self, limit: int) -> List[Dict]:
        """
        构建涨跌幅榜条目
        
        从币安获取所有涨跌幅数据（已包含 side 标记），然后分离出涨幅前N名和跌幅前N名。
        
        利用 get_top_gainers() 返回的 'side' 标记来分离涨跌榜：
        - side='gainer': 涨幅榜（priceChangePercent >= 0）
        - side='loser': 跌幅榜（priceChangePercent < 0）
        
        Args:
            limit: 每个榜单返回的条数（涨幅榜和跌幅榜各返回limit条）
            
        Returns:
            涨跌幅榜条目列表，每个条目包含 'side' 字段（'gainer' 或 'loser'）
        """
        # 获取所有涨跌幅数据（不限制数量，以便正确分离涨跌榜）
        # get_top_gainers 已经为每条数据设置了 'side' 标记
        tickers = self._futures_client.get_top_gainers(limit=None)
        if not tickers:
            return []

        # 数据已经在 get_top_gainers 中过滤过，这里不需要再次过滤
        # 但为了安全，再次确认计价资产匹配
        filtered = [
            item for item in tickers
            if item.get('symbol', '').endswith(self._futures_client.quote_asset)
        ]

        if not filtered:
            return []

        # 按涨跌幅百分比排序
        def sort_key(item):
            try:
                return float(item.get('priceChangePercent', 0))
            except (TypeError, ValueError):
                return 0.0

        # 利用 get_top_gainers 返回的 side 标记分离涨跌榜
        # 涨幅榜：筛选 side='gainer' 的数据，按涨跌幅降序，取前limit个
        gainers = sorted(
            [item for item in filtered if item.get('side') == 'gainer'],
            key=sort_key,
            reverse=True
        )[:limit]
        # 跌幅榜：筛选 side='loser' 的数据，按涨跌幅升序，取前limit个
        losers = sorted(
            [item for item in filtered if item.get('side') == 'loser'],
            key=sort_key
        )[:limit]

        entries: List[Dict] = []
        for side, collection in (('gainer', gainers), ('loser', losers)):
            for idx, item in enumerate(collection):
                # 确保使用数据中的 side 标记（如果存在）
                item_side = item.get('side', side)
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
                # 新格式：{symbol: {1w: {...}, 1d: {...}}}
                # 提取 symbol 对应的数据
                timeframes = timeframe_data.get(base_symbol, {}) if timeframe_data else {}

                entries.append({
                    'symbol': base_symbol,
                    'contract_symbol': contract_symbol,
                    'name': base_symbol,
                    'exchange': 'BINANCE_FUTURES',
                    'side': item_side,  # 使用数据中的 side 标记
                    'rank': idx + 1,
                    'price': price,
                    'change_percent': change_percent,
                    'quote_volume': quote_volume,
                    'timeframes': timeframes
                })

        return entries
