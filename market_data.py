"""
Market Data Fetcher - Real-time market data from Binance USDS-M futures SDK
"""
import time
import logging
import threading
import config as app_config
from datetime import datetime, timezone
from typing import Dict, List, Optional

from binance_futures import BinanceFuturesClient
from database_clickhouse import ClickHouseDatabase

logger = logging.getLogger(__name__)


class MarketDataFetcher:
    """Fetch real-time market data from Binance USDS-M futures with caching and fallback"""

    def __init__(self, db):
        """Initialize market data fetcher"""
        self.db = db
        # 移除价格缓存，实时获取以保证最高实时性
        self._last_live_prices: Dict[str, Dict] = {}
        self._last_live_date: Optional[datetime.date] = None

        self._futures_client: Optional[BinanceFuturesClient] = None
        self._last_gainers_update: float = 0
        self._gainers_refresh = getattr(app_config, 'FUTURES_TOP_GAINERS_REFRESH', 300)
        self._futures_kline_limit = getattr(app_config, 'FUTURES_KLINE_LIMIT', 120)
        self._futures_quote_asset = getattr(app_config, 'FUTURES_QUOTE_ASSET', 'USDT')
        self._leaderboard_refresh = getattr(app_config, 'FUTURES_LEADERBOARD_REFRESH', 60)
        self._last_leaderboard_sync: float = 0
        self._leaderboard_lock = threading.Lock()
        self._clickhouse_db: Optional[ClickHouseDatabase] = None
        self._init_futures_client()
        self._init_clickhouse_db()

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

    def _init_clickhouse_db(self):
        """Initialize ClickHouse database connection"""
        try:
            self._clickhouse_db = ClickHouseDatabase(auto_init_tables=True)
            logger.info('[ClickHouse] ClickHouse database connection initialized')
        except Exception as exc:
            logger.warning('[ClickHouse] Failed to initialize ClickHouse connection: %s', exc)
            self._clickhouse_db = None

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
        获取最新价格数据（实时获取，无缓存）
        
        实时从交易所获取最新价格数据，不使用任何缓存机制。
        如果无法获取实时数据，则返回最近一次的价格作为降级方案（仅在API完全不可用时使用）。
        
        Args:
            symbols: 可选的交易对符号列表，如果为None则返回所有已配置的交易对
            
        Returns:
            价格数据字典，key为交易对符号，value为价格信息
        """
        now = datetime.now()
        
        # 实时获取价格数据（不使用缓存）
        live_prices = self.get_current_prices(symbols)
        if live_prices:
            # 标记为实时数据
            for payload in live_prices.values():
                payload['source'] = 'live'
                payload['price_date'] = now.strftime('%Y-%m-%d')
            return live_prices

        # 如果无法获取实时数据，返回最近一次的价格作为降级方案
        # 这仅在交易所API完全不可用时使用，不用于缓存目的
        if self._last_live_prices:
            fallback: Dict[str, Dict] = {}
            for symbol, payload in self._last_live_prices.items():
                if symbols and symbol not in symbols:
                    continue
                fallback[symbol] = {
                    **payload,
                    'source': 'fallback',  # 明确标记为降级数据
                    'price_date': payload.get('price_date') or (
                        self._last_live_date.strftime('%Y-%m-%d') if self._last_live_date else None
                    )
                }
            logger.warning(f'[Prices] Using fallback prices for {len(fallback)} symbols (API unavailable)')
            return fallback

        # 如果没有任何数据，返回空字典
        logger.warning('[Prices] No price data available')
        return {}

    def get_current_prices(self, symbols: List[str] = None) -> Dict[str, Dict]:
        """
        获取当前期货价格（实时获取，无缓存）
        
        此方法实时从交易所获取最新价格数据，不使用任何缓存机制，
        以保证最高实时性。每次调用都直接请求交易所API获取最新数据。
        
        Args:
            symbols: 可选的交易对符号列表，如果为None则返回所有已配置的交易对
            
        Returns:
            价格数据字典，key为交易对符号，value为价格信息
        """
        futures = self._get_configured_futures()
        if not futures:
            return {}

        if symbols:
            futures = [f for f in futures if f['symbol'] in symbols]

        if not futures:
            return {}

        # 实时获取价格数据（不使用缓存）
        prices = self._fetch_from_binance_futures(futures)

        # 如果某些交易对获取失败，使用最近一次的价格作为降级方案
        # 但仅在交易所API完全不可用时使用，不用于缓存
        missing_symbols = [f['symbol'] for f in futures if f['symbol'] not in prices]
        if missing_symbols and self._last_live_prices:
            for symbol in missing_symbols:
                last_price_info = self._last_live_prices.get(symbol, {})
                last_price = last_price_info.get('price', 0)
                # 只有在有有效历史价格时才使用降级方案
                if last_price > 0:
                    prices[symbol] = {
                        'price': last_price,
                        'name': symbol,
                        'exchange': 'BINANCE_FUTURES',
                        'change_24h': last_price_info.get('change_24h', 0),
                        'daily_volume': last_price_info.get('daily_volume', 0),
                        'timeframes': {}  # 不再实时生成，只在 AI 交易时计算
                    }
                    logger.debug(f'[Prices] Using fallback price for {symbol}: ${last_price}')

        # 更新最近一次的价格记录（仅用于降级方案，不用于缓存）
        if prices:
            for symbol, price_data in prices.items():
                self._last_live_prices[symbol] = price_data.copy()
            self._last_live_date = datetime.now().date()

        return prices

    def _fetch_from_binance_futures(self, futures: List[Dict]) -> Dict[str, Dict]:
        """
        从币安期货API实时获取价格数据
        
        此方法每次调用都直接请求币安API获取最新价格数据，不使用任何缓存。
        保证数据的最高实时性。
        
        Args:
            futures: 期货配置列表
            
        Returns:
            价格数据字典，key为交易对符号，value为价格信息
        """
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

            # 不再实时生成 timeframes 数据，只在 AI 交易时通过 calculate_technical_indicators 计算
            future_meta = next((f for f in futures if f['symbol'] == symbol), {})
            prices[symbol] = {
                'price': last_price,
                'name': future_meta.get('name', symbol),
                'exchange': future_meta.get('exchange', 'BINANCE_FUTURES'),
                'change_24h': change_percent,
                'daily_volume': quote_volume,
                'timeframes': {}  # 不再实时生成，只在 AI 交易时计算
            }

        return prices

    # ============ Technical Indicator Methods ============

    def calculate_technical_indicators(self, symbol: str) -> Dict:
        """
        计算技术指标（实时计算，无缓存）
        
        此方法用于 AI 交易决策，需要最高实时性，每次调用都实时计算所有指标。
        不再使用任何缓存机制，确保数据的最新性。
        
        Args:
            symbol: 交易对符号（如 'BTC'）
            
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
        获取指定交易对的所有时间框架技术指标（实时计算，无缓存）
        
        计算每个时间框架的：
        - K线数据（最新一根K线）
        - MA值（5、20、60、99周期）
        - MACD指标（DIF、DEA、BAR）
        - RSI指标（RSI6、RSI9）
        - 成交量（VOL）
        
        注意：此方法不再使用缓存，每次调用都实时从交易所获取最新数据并计算，
        以保证 AI 交易决策所需的高实时性。
        
        Args:
            symbol: 交易对符号（如 'BTC'）
            
        Returns:
            格式：{symbol: {1w: {kline: {}, ma: {}, macd: {}, rsi: {}, VoL: {}}, 1d: {...}}}
        """
        if not self._futures_client:
            logger.warning(f'[Indicators] Futures client unavailable for {symbol}')
            return {}

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
        
        # VOL均量线（MAVOL）周期列表
        # 根据文档：5周期（短期）、10周期（中期）
        mavol_lengths = [5, 10]
        
        # 不同时间框架的K线limit值优化配置
        # 注意：Binance API的limit最大值为120，所有时间框架统一使用120
        # 120根K线足够计算所有指标：
        # - MA99需要99根（满足）
        # - MACD需要26根（满足）
        # - RSI需要14根（满足）
        timeframe_limits = {
            '1w': 120,   # 周线：120根 = 约2.3年历史数据
            '1d': 120,   # 日线：120根 = 约4个月历史数据
            '4h': 120,   # 4小时：120根 = 约20天历史数据
            '1h': 120,   # 1小时：120根 = 约5天历史数据
            '15m': 120,  # 15分钟：120根 = 约1.25天历史数据
            '5m': 120,   # 5分钟：120根 = 约10小时历史数据
            '1m': 120    # 1分钟：120根 = 约2小时历史数据
        }
        
        # 格式化交易对符号（添加计价资产后缀）
        symbol_key = self._futures_client.format_symbol(symbol)
        
        # 存储所有时间框架的数据
        timeframe_data: Dict[str, Dict] = {}

        # 遍历每个时间框架（实时计算，无缓存）
        for label, interval in timeframe_map.items():
            try:
                # 根据时间框架获取优化的limit值
                limit = timeframe_limits.get(label, self._futures_kline_limit)
                
                # 实时获取K线数据（每次调用都获取最新数据）
                # 注意：Binance API的kline_candlestick_data()方法不支持endTime参数
                # 不指定startTime和endTime时，API默认返回最新的limit根K线数据
                # 这正好符合我们的需求：获取最新的K线数据用于指标计算
                klines = self._futures_client.get_klines(
                    symbol_key, 
                    interval, 
                    limit=limit
                )
                
                logger.debug(
                    f'[Indicators] 获取K线数据: symbol={symbol}, interval={interval}, limit={limit}, '
                    f'返回{len(klines) if klines else 0}根K线'
                )
                
                if not klines or len(klines) == 0:
                    logger.debug(f'[Indicators] No klines data for {symbol} {label}')
                    continue
                
                # 提取收盘价和成交量（使用列表推导式提高效率）
                closes = []
                volumes = []
                for item in klines:
                    # 兼容旧的列表格式和新的字典格式
                    try:
                        # 如果是字典格式（新的实现）
                        if isinstance(item, dict):
                            closes.append(float(item['close']))
                            volumes.append(float(item['volume']))
                        # 如果是列表格式（旧的实现）
                        elif isinstance(item, (list, tuple)) and len(item) > 4:
                            closes.append(float(item[4]))
                            if len(item) > 5:
                                volumes.append(float(item[5]))
                    except (ValueError, TypeError, KeyError):
                        continue
                
                if not closes or len(closes) < 2:
                    logger.debug(f'[Indicators] Insufficient data for {symbol} {label}: {len(closes)} closes')
                    continue
                
                # 获取最新一根K线数据
                latest_kline = klines[-1]
                try:
                    # 兼容旧的列表格式和新的字典格式
                    if isinstance(latest_kline, dict):
                        # 新的字典格式
                        kline_data = {
                            'open_time': int(latest_kline['open_time']) if latest_kline.get('open_time') else None,
                            'open': float(latest_kline['open']) if latest_kline.get('open') else 0.0,
                            'high': float(latest_kline['high']) if latest_kline.get('high') else 0.0,
                            'low': float(latest_kline['low']) if latest_kline.get('low') else 0.0,
                            'close': float(latest_kline['close']) if latest_kline.get('close') else 0.0,
                            'volume': float(latest_kline['volume']) if latest_kline.get('volume') else 0.0
                        }
                    else:
                        # 旧的列表格式
                        kline_data = {
                            'open_time': int(latest_kline[0]) if len(latest_kline) > 0 and latest_kline[0] else None,
                            'open': float(latest_kline[1]) if len(latest_kline) > 1 else 0.0,
                            'high': float(latest_kline[2]) if len(latest_kline) > 2 else 0.0,
                            'low': float(latest_kline[3]) if len(latest_kline) > 3 else 0.0,
                            'close': float(latest_kline[4]) if len(latest_kline) > 4 else 0.0,
                            'volume': float(latest_kline[5]) if len(latest_kline) > 5 else 0.0
                        }
                except (ValueError, TypeError, IndexError) as e:
                    logger.warning(f'[Indicators] Failed to parse kline data for {symbol} {label}: {e}')
                    continue
                
                # 实时计算MA值（简单移动平均）
                ma_values = self._calculate_ma_values(closes, ma_lengths)
                
                # 实时计算MACD指标
                macd = self._calculate_macd(closes)
                
                # 实时计算RSI指标
                rsi = self._calculate_rsi(closes)
                
                # 计算VOL指标（成交量）和均量线（MAVOL）
                # VOL：当前K线的成交量（该周期内的成交总量）
                # MAVOL：成交量移动平均线，用于过滤短期波动
                vol_data = self._calculate_vol_indicators(volumes, mavol_lengths)
                
                # 组装该时间框架的数据
                timeframe_data[label] = {
                    'kline': kline_data,
                    'ma': ma_values,
                    'macd': macd,
                    'rsi': rsi,
                    'vol': vol_data
                }
                
                # 记录计算成功的日志（仅在DEBUG级别）
                logger.debug(
                    f'[Indicators] {symbol} {label} 指标计算完成: '
                    f'MA5={ma_values.get("ma5", 0):.2f}, '
                    f'MACD_DIF={macd.get("dif", 0):.4f}, '
                    f'RSI6={rsi.get("rsi6", 0):.2f}, '
                    f'VOL={vol_data.get("vol", 0):.2f}, '
                    f'MAVOL5={vol_data.get("mavol5", 0):.2f}'
                )
                
            except Exception as e:
                logger.warning(
                    f"[技术指标] 计算 {symbol} {label} 时间框架指标失败: {e}",
                    exc_info=True
                )
                continue

        # 直接返回结果，不使用缓存（保证实时性）
        result = {symbol: timeframe_data}
        logger.debug(f'[Indicators] Calculated indicators for {symbol}: {len(timeframe_data)} timeframes')
        
        return result

    def _calculate_ma_values(self, closes: List[float], ma_lengths: List[int]) -> Dict[str, float]:
        """
        计算简单移动平均（MA）值（币圈标准计算方式）
        
        MA（Moving Average，移动平均线）是某一时间段内标的资产收盘价的算术平均值。
        这是简单移动平均（SMA），核心作用是过滤短期价格波动、反映中长期趋势方向。
        
        MA标准计算公式（币圈与股票市场完全一致）：
        MA(n) = （第1期收盘价 + 第2期收盘价 + ... + 第n期收盘价）÷ n
        
        计算逻辑：
        1. 收盘价列表按时间顺序从旧到新排列（最新的在最后）
        2. 取最近n期的收盘价（即最后n个收盘价）
        3. 求和后除以n得到MA值
        
        示例（MA5计算）：
        假设收盘价列表：[42000, 43500, 42800, 44200, 43900, 45000, 44500, 46000, 45800, 47000]
        取最后5个：45000, 44500, 46000, 45800, 47000
        MA5 = (45000 + 44500 + 46000 + 45800 + 47000) ÷ 5 = 45660
        
        周期说明：
        - MA5：5周期均线（短期趋势）
        - MA20：20周期均线（中期趋势）
        - MA60：60周期均线（中长期趋势）
        - MA99：99周期均线（长期趋势，币圈中部分交易者视为牛熊分界线）
        
        注意：
        - 币圈7×24小时交易，周期划分以自然时间单位为准（日/小时/分钟）
        - 计算MA99需至少99根对应周期的K线数据
        - 数据不足时返回0.0，并记录警告日志
        
        Args:
            closes: 收盘价列表（按时间顺序从旧到新排列，最新的在最后）
            ma_lengths: MA周期列表，如 [5, 20, 60, 99]
            
        Returns:
            包含各周期MA值的字典，如 {'ma5': 100.5, 'ma20': 98.3, 'ma60': 99.2, 'ma99': 98.8}
            如果数据不足，对应周期的MA值为0.0
        """
        ma_values = {}
        
        for length in ma_lengths:
            if len(closes) >= length:
                # 数据充足：使用最近N个收盘价的算术平均值
                # 取最后N个收盘价（最新的在最后，符合文档要求）
                recent_closes = closes[-length:]
                # MA(n) = 最近n期收盘价之和 ÷ n
                ma_value = sum(recent_closes) / length
                ma_values[f'ma{length}'] = ma_value
            else:
                # 数据不足：根据文档，应返回None或0，不计算MA值
                # 这里返回0.0，表示无法计算（数据不足）
                ma_values[f'ma{length}'] = 0.0
                logger.warning(
                    f'[MA] 数据不足: MA{length}需要至少{length}根K线数据，实际只有{len(closes)}根，无法计算'
                )
        
        return ma_values


    def _calculate_macd(self, closes: List[float]) -> Dict[str, float]:
        """
        计算MACD指标（指数平滑异同移动平均线）- 简化版
        
        MACD标准计算公式：
        1. 计算快速EMA(12)和慢速EMA(26)
        2. 计算DIF（差离值）= EMA(12) - EMA(26)
        3. 计算DEA（信号线）= DIF的9日EMA
        4. 计算BAR（柱状线）= DIF - DEA（简化版，不乘以2）
        
        注意：MACD的BAR有两种计算方式：
        - 方式1：BAR = (DIF - DEA) × 2（常用版，放大视觉效果）
        - 方式2：BAR = DIF - DEA（简化版，直接差值）
        这里使用简化版方式2
        
        Args:
            closes: 收盘价列表（按时间顺序，最新的在最后）
            
        Returns:
            包含DIF、DEA、BAR的字典，如果数据不足则返回默认值
        """
        # 需要至少26个数据点才能计算EMA(26)
        if len(closes) < 26:
            logger.warning(f'[MACD] 数据不足: 需要至少26个数据点，实际只有{len(closes)}个')
            return {'dif': 0.0, 'dea': 0.0, 'bar': 0.0}
        
        # 步骤1：计算EMA(12)和EMA(26)的历史序列
        ema12_series = self._calculate_ema_series(closes, 12)
        ema26_series = self._calculate_ema_series(closes, 26)
        
        # 步骤2：计算DIF序列 = EMA(12) - EMA(26)
        dif_series = [ema12_series[i] - ema26_series[i] for i in range(len(closes))]
        
        # 获取最新的DIF值
        dif = dif_series[-1]
        
        # 步骤3：计算DEA（DIF的9日EMA，也称为信号线）
        # 需要至少9个DIF值才能计算DEA
        if len(dif_series) < 9:
            logger.warning(f'[MACD] DIF序列不足: 需要至少9个DIF值，实际只有{len(dif_series)}个')
            return {'dif': dif, 'dea': 0.0, 'bar': 0.0}
        
        dea = self._calculate_ema(dif_series, 9)
        
        # 步骤4：计算BAR = DIF - DEA（简化版，不乘以2）
        bar = dif - dea
        
        return {
            'dif': dif,
            'dea': dea,
            'bar': bar
        }

    def _calculate_ema_series(self, closes: List[float], period: int) -> List[float]:
        """
        计算EMA序列（返回所有历史EMA值）
        
        EMA标准计算公式：
        - 平滑系数（multiplier）= 2 / (period + 1)
        - 第一个EMA值 = 前period个数据的简单移动平均（SMA）
        - 后续EMA值 = 今日价格 × multiplier + 昨日EMA × (1 - multiplier)
        即：EMA(today) = Price(today) × (2/(N+1)) + EMA(yesterday) × ((N-1)/(N+1))
        
        为了保持序列长度一致，前period-1个数据点使用简单移动平均作为初始值。
        
        Args:
            closes: 收盘价列表（按时间顺序，最新的在最后）
            period: EMA周期（如12、26）
            
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
        # 这样可以保持序列长度一致，但前几个值不是真正的EMA
        for i in range(period - 1):
            if i == 0:
                ema_series.append(closes[0])
            else:
                avg = sum(closes[:i+1]) / (i + 1)
                ema_series.append(avg)
        
        # 从第period个数据点开始，使用标准EMA计算
        # 初始化：第一个有效EMA值使用前period个数据的简单平均（SMA）
        ema = sum(closes[:period]) / period
        ema_series.append(ema)
        
        # 递推计算后续EMA值
        # EMA公式：EMA(today) = Price(today) × multiplier + EMA(yesterday) × (1 - multiplier)
        # 等价于：EMA(today) = EMA(yesterday) + (Price(today) - EMA(yesterday)) × multiplier
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
        计算单个周期的RSI值（使用Wilder's Smoothing Method）
        
        RSI标准计算公式（Wilder's Method）：
        1. 计算价格变化：change = close[i] - close[i-1]
        2. 分离涨幅和跌幅：
           - gain = change if change > 0 else 0
           - loss = -change if change < 0 else 0
        3. 计算初始平均涨幅和跌幅（前period个周期）：
           - avg_gain = sum(gains[:period]) / period
           - avg_loss = sum(losses[:period]) / period
        4. 使用Wilder's平滑方法计算后续平均值：
           - avg_gain = (avg_gain * (period - 1) + current_gain) / period
           - avg_loss = (avg_loss * (period - 1) + current_loss) / period
        5. 计算RS = avg_gain / avg_loss
        6. 计算RSI = 100 - (100 / (1 + RS))
        
        Args:
            closes: 收盘价列表（按时间顺序，最新的在最后）
            period: RSI周期（如6、9、14）
            
        Returns:
            RSI值（0-100之间）
        """
        if len(closes) < period + 1:
            logger.warning(f'[RSI] 数据不足: 需要至少{period + 1}个数据点，实际只有{len(closes)}个')
            return 50.0
        
        # 步骤1：计算每日涨跌幅度
        changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [change if change > 0 else 0.0 for change in changes]
        losses = [-change if change < 0 else 0.0 for change in changes]
        
        # 步骤2：计算初始平均涨幅和平均跌幅（前period个周期）
        initial_gains = gains[:period]
        initial_losses = losses[:period]
        avg_gain = sum(initial_gains) / period
        avg_loss = sum(initial_losses) / period
        
        # 步骤3：使用Wilder's平滑方法计算后续平均值
        # Wilder's平滑公式：新平均值 = (旧平均值 × (周期-1) + 当前值) / 周期
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
        # 步骤4：计算RS = 平均涨幅 ÷ 平均跌幅
        if avg_loss == 0:
            # 如果平均跌幅为0，说明没有下跌，RSI应该为100
            return 100.0
        
        rs = avg_gain / avg_loss
        
        # 步骤5：计算RSI = 100 - (100 / (1 + RS))
        rsi = 100 - (100 / (1 + rs))
        
        # 确保RSI值在0-100范围内
        rsi = max(0.0, min(100.0, rsi))
        
        return rsi

    def _calculate_vol_indicators(self, volumes: List[float], mavol_lengths: List[int]) -> Dict[str, float]:
        """
        计算VOL指标（成交量）和均量线（MAVOL）
        
        VOL指标定义：
        - VOL（Volume，成交量）：某一时间段内标的资产的成交总量
        - 每根K线对应一个VOL值，表示该周期内的成交总量
        
        均量线（MAVOL）定义：
        - MAVOL-n = 过去n个周期的VOL总和 ÷ n
        - 用于过滤短期波动，识别成交量趋势
        - 常用参数：5周期（短期）、10周期（中期）
        
        计算逻辑：
        1. VOL = 最新一根K线的成交量（当前周期的成交总量）
        2. MAVOL-n = 过去n个周期成交量的简单移动平均
        
        注意：
        - 币圈VOL以基础货币数量为单位（如BTC/USDT交易对，VOL单位为BTC）
        - 数据来源于Binance API的K线数据，已包含对应周期的成交量
        
        Args:
            volumes: 成交量列表（按时间顺序，最新的在最后）
            mavol_lengths: 均量线周期列表，如 [5, 10, 60]
            
        Returns:
            包含VOL和MAVOL值的字典，格式：
            {
                'vol': 当前周期成交量,
                'mavol5': 5周期均量线,
                'mavol10': 10周期均量线
            }
        """
        result = {}
        
        # 1. 计算VOL：最新一根K线的成交量
        vol = volumes[-1] if volumes else 0.0
        result['vol'] = vol
        
        # 2. 计算均量线（MAVOL）
        for length in mavol_lengths:
            if len(volumes) >= length:
                # 数据充足：使用最近N个周期的成交量平均值
                recent_volumes = volumes[-length:]
                mavol_value = sum(recent_volumes) / length
                result[f'mavol{length}'] = mavol_value
            else:
                # 数据不足：使用所有可用数据的平均值
                if len(volumes) > 0:
                    mavol_value = sum(volumes) / len(volumes)
                    result[f'mavol{length}'] = mavol_value
                    logger.warning(
                        f'[VOL] 数据不足: MAVOL{length}需要{length}个数据点，实际只有{len(volumes)}个，使用所有可用数据计算'
                    )
                else:
                    result[f'mavol{length}'] = 0.0
                    logger.warning(f'[VOL] 无数据: 无法计算MAVOL{length}')
        
        return result

    # ============ Leaderboard Methods ============

    def sync_leaderboard(self, force: bool = False, limit: Optional[int] = None) -> Dict[str, List[Dict]]:
        """
        同步涨幅榜数据（从 ClickHouse 查询）
        
        优化逻辑：
        1. 从 ClickHouse futures_leaderboard 表查询涨幅榜数据
        2. 不再查询 SQLite 数据库
        3. 不再实时计算 K线指标和 timeframes 数据
        4. 使用 ClickHouse 表中的 last_price 字段作为最新价格
        
        Args:
            force: 是否强制刷新（保留参数以兼容现有调用，但实际不使用）
            limit: 返回的数据条数限制
            
        Returns:
            涨幅榜数据字典，包含 gainers 和 losers
        """
        if limit is None:
            limit = getattr(app_config, 'FUTURES_TOP_GAINERS_LIMIT', 10)

        logger.info(
            '[Leaderboard] sync_leaderboard called | limit=%s (from ClickHouse)',
            limit
        )

        # 如果没有可用的 ClickHouse 连接，返回空数据
        if not self._clickhouse_db:
            logger.warning('[Leaderboard] ClickHouse unavailable, returning empty data')
            return {'gainers': [], 'losers': []}

        try:
            # 从 ClickHouse 查询涨幅榜数据
            data = self._clickhouse_db.get_leaderboard(limit=limit)
            
            # 转换数据格式以兼容现有接口
            # ClickHouse 返回的数据格式：{'gainers': [...], 'losers': [...]}
            # 需要转换为与原来 SQLite 返回格式一致的结构
            formatted_data = {
                'gainers': [],
                'losers': []
            }
            
            # 格式化涨幅榜数据
            for item in data.get('gainers', []):
                symbol = item.get('symbol', '')
                # 提取基础符号（去掉 USDT 后缀）
                base_symbol = symbol.replace(self._futures_quote_asset, '') if symbol.endswith(self._futures_quote_asset) else symbol
                
                formatted_data['gainers'].append({
                    'symbol': base_symbol,
                    'contract_symbol': symbol,
                    'name': base_symbol,
                    'exchange': 'BINANCE_FUTURES',
                    'side': 'gainer',
                    'rank': item.get('rank', 0),
                    'price': item.get('price', 0.0),  # 使用 ClickHouse 的 last_price
                    'change_percent': item.get('change_percent', 0.0),
                    'quote_volume': item.get('quote_volume', 0.0),
                    'timeframes': {}  # 不再生成 timeframes 数据
                })
            
            # 格式化跌幅榜数据
            for item in data.get('losers', []):
                symbol = item.get('symbol', '')
                # 提取基础符号（去掉 USDT 后缀）
                base_symbol = symbol.replace(self._futures_quote_asset, '') if symbol.endswith(self._futures_quote_asset) else symbol
                
                formatted_data['losers'].append({
                    'symbol': base_symbol,
                    'contract_symbol': symbol,
                    'name': base_symbol,
                    'exchange': 'BINANCE_FUTURES',
                    'side': 'loser',
                    'rank': item.get('rank', 0),
                    'price': item.get('price', 0.0),  # 使用 ClickHouse 的 last_price
                    'change_percent': item.get('change_percent', 0.0),
                    'quote_volume': item.get('quote_volume', 0.0),
                    'timeframes': {}  # 不再生成 timeframes 数据
                })
            
            logger.info('[Leaderboard] Returning leaderboard payload from ClickHouse: gainers=%s losers=%s',
                        len(formatted_data.get('gainers', [])), len(formatted_data.get('losers', [])))
            return formatted_data
            
        except Exception as exc:
            logger.error('[Leaderboard] Failed to get leaderboard from ClickHouse: %s', exc, exc_info=True)
            return {'gainers': [], 'losers': []}

    def get_leaderboard(self, limit: Optional[int] = None) -> Dict[str, List[Dict]]:
        """Get leaderboard data (wrapper for sync_leaderboard)"""
        return self.sync_leaderboard(force=False, limit=limit)

    def _build_leaderboard_entries(self, limit: int) -> List[Dict]:
        """
        构建涨跌幅榜条目（已废弃，不再使用）
        
        此方法已被废弃，涨幅榜数据现在直接从 ClickHouse 查询。
        保留此方法仅为了向后兼容，实际不会被调用。
        
        Args:
            limit: 每个榜单返回的条数
            
        Returns:
            空列表（已废弃）
        """
        logger.warning('[Leaderboard] _build_leaderboard_entries is deprecated, data now comes from ClickHouse')
        return []
