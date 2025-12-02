"""
Market Data Fetcher - Real-time market data from Binance USDS-M futures SDK
"""
import time
import logging
import threading
import config as app_config
from datetime import datetime, timezone
from typing import Dict, List, Optional
import pandas as pd
import pandas_ta as ta

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
        实时计算指定交易对的技术指标（使用pandas-ta库优化）
        
        技术指标说明：
        1. MA（移动平均线）：反映价格趋势方向和强度
           - MA5：5周期均线（短期趋势）
           - MA20：20周期均线（中期趋势）
           - MA60：60周期均线（中长期趋势）
           - MA99：99周期均线（长期趋势，币圈中部分交易者视为牛熊分界线）
           
        2. MACD（指数平滑异同移动平均线）：判断买卖时机和趋势强度
           - DIF（差离值）：快线与慢线的差值
           - DEA（信号线）：DIF的移动平均线
           - BAR（柱状线）：DIF与DEA的差值（简化版，不乘以2）
           
        3. RSI（相对强弱指数）：衡量超买超卖状态
           - RSI6：6周期RSI（短期敏感度）
           - RSI9：9周期RSI（中期平衡点）
           
        4. VOL（成交量）和均量线（MAVOL）：辅助判断资金流向和趋势可靠性
           - VOL：当前K线的成交量（该周期内的成交总量）
           - MAVOL5：5周期成交量均线（短期资金热度）
           - MAVOL10：10周期成交量均线（中期资金趋势）
           
        币圈特点说明：
        - 7×24小时连续交易，无休市时间
        - 波动剧烈，需要多时间框架结合分析
        - 技术指标滞后性明显，需结合基本面分析
        
        Args:
            symbol: 交易对符号（如 BTCUSDT）
            
        Returns:
            包含各时间框架技术指标的嵌套字典，结构如下：
            {
                'BTCUSDT': {
                    '1w': {
                        'kline': {...},
                        'ma': {'ma5': ..., 'ma20': ..., 'ma60': ..., 'ma99': ...},
                        'macd': {'dif': ..., 'dea': ..., 'bar': ...},
                        'rsi': {'rsi6': ..., 'rsi9': ...},
                        'vol': {'vol': ..., 'mavol5': ..., 'mavol10': ...}
                    },
                    '1d': {...},
                    '4h': {...},
                    '1h': {...},
                    '15m': {...},
                    '5m': {...},
                    '1m': {...}
                }
            }
        """
        logger.debug(f'[Indicators] 开始计算技术指标: {symbol}')
        
        # 定义时间框架映射关系（标签: Binance API周期标识符）
        timeframe_mapping = {
            '1w': '1w',   # 周线：观察长期趋势和牛熊转换
            '1d': '1d',   # 日线：观察中期趋势和重要支撑阻力
            '4h': '4h',   # 4小时线：日内短线交易的重要参考
            '1h': '1h',   # 1小时线：短线交易的主要依据
            '15m': '15m', # 15分钟线：捕捉短期波动和入场点
            '5m': '5m',   # 5分钟线：超短线交易的精确参考
            '1m': '1m'    # 1分钟线：极短线交易的微观信号
        }
        
        # 定义各指标的计算周期参数
        ma_lengths = [5, 20, 60, 99]         # MA均线周期
        mavol_lengths = [5, 10, 60]          # 成交量均线周期
        
        # 存储各时间框架的数据
        timeframe_data = {}
        
        # 为每个时间框架计算技术指标
        for label, interval in timeframe_mapping.items():
            try:
                logger.debug(f'[Indicators] Processing {symbol} {label} ({interval})')
                
                # 根据不同时间框架设置不同的K线数量限制
                # 短周期需要更多数据以保证指标准确性
                limit_map = {
                    '1w': 120,   # 周线：获取120周数据（约2.3年）
                    '1d': 120,   # 日线：获取120天数据（约4个月）
                    '4h': 120,   # 4小时线：获取120根4小时K线（约20天）
                    '1h': 120,   # 1小时线：获取120根1小时K线（约5天）
                    '15m': 120,  # 15分钟线：获取120根15分钟K线（约1.25天）
                    '5m': 120,   # 5分钟线：获取120根5分钟K线（约10小时）
                    '1m': 120    # 1分钟线：获取120根1分钟K线（约2小时）
                }
                limit = limit_map.get(label, 120)  # 默认获取120根K线
                
                # 构造币安API需要的交易对符号（统一转为大写）
                symbol_key = symbol.upper()
                
                # 从币安期货API获取K线数据
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
                timestamps = []
                for item in klines:
                    # 兼容旧的列表格式和新的字典格式
                    try:
                        # 如果是字典格式（新的实现）
                        if isinstance(item, dict):
                            closes.append(float(item['close']))
                            volumes.append(float(item['volume']))
                            timestamps.append(int(item['open_time']) if item.get('open_time') else 0)
                        # 如果是列表格式（旧的实现）
                        elif isinstance(item, (list, tuple)) and len(item) > 4:
                            closes.append(float(item[4]))
                            if len(item) > 5:
                                volumes.append(float(item[5]))
                            if len(item) > 0:
                                timestamps.append(int(item[0]))
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
                
                # 创建pandas DataFrame用于技术指标计算
                df = pd.DataFrame({
                    'close': closes,
                    'volume': volumes
                })
                
                # 实时计算MA值（简单移动平均）使用pandas-ta
                ma_values = {}
                for length in ma_lengths:
                    if len(closes) >= length:
                        ma_series = ta.sma(df['close'], length=length)
                        if ma_series is not None and not ma_series.empty:
                            ma_values[f'ma{length}'] = float(ma_series.iloc[-1])
                        else:
                            ma_values[f'ma{length}'] = 0.0
                    else:
                        ma_values[f'ma{length}'] = 0.0
                        logger.warning(
                            f'[MA] 数据不足: MA{length}需要至少{length}根K线数据，实际只有{len(closes)}根，无法计算'
                        )
                
                # 实时计算MACD指标使用pandas-ta
                macd = {'dif': 0.0, 'dea': 0.0, 'bar': 0.0}
                if len(closes) >= 26:  # MACD需要至少26个数据点
                    macd_df = ta.macd(df['close'], fast=12, slow=26, signal=9)
                    if macd_df is not None and not macd_df.empty:
                        # pandas-ta返回的列名可能因版本而异，尝试几种常见的命名
                        dif_col = None
                        dea_col = None
                        bar_col = None
                        
                        # 查找对应的列
                        for col in macd_df.columns:
                            if 'MACDh' in col or 'histogram' in col or 'bar' in col.lower():
                                bar_col = col
                            elif 'MACDs' in col or 'signal' in col:
                                dea_col = col
                            elif 'MACD_' in col or 'macd' in col.lower():
                                dif_col = col
                        
                        # 如果找不到标准列名，使用索引
                        if dif_col is None and len(macd_df.columns) >= 1:
                            dif_col = macd_df.columns[0]
                        if dea_col is None and len(macd_df.columns) >= 2:
                            dea_col = macd_df.columns[1]
                        if bar_col is None and len(macd_df.columns) >= 3:
                            bar_col = macd_df.columns[2]
                        
                        # 获取最新值
                        if dif_col and dif_col in macd_df.columns:
                            macd['dif'] = float(macd_df[dif_col].iloc[-1])
                        if dea_col and dea_col in macd_df.columns:
                            macd['dea'] = float(macd_df[dea_col].iloc[-1])
                        if bar_col and bar_col in macd_df.columns:
                            macd['bar'] = float(macd_df[bar_col].iloc[-1])
                else:
                    logger.warning(f'[MACD] 数据不足: 需要至少26个数据点，实际只有{len(closes)}个')
                
                # 实时计算RSI指标使用pandas-ta
                rsi = {'rsi6': 50.0, 'rsi9': 50.0}
                # 计算RSI(6)
                if len(closes) >= 7:  # RSI(6)需要至少7个数据点
                    rsi6_series = ta.rsi(df['close'], length=6)
                    if rsi6_series is not None and not rsi6_series.empty:
                        rsi['rsi6'] = float(rsi6_series.iloc[-1])
                
                # 计算RSI(9)
                if len(closes) >= 10:  # RSI(9)需要至少10个数据点
                    rsi9_series = ta.rsi(df['close'], length=9)
                    if rsi9_series is not None and not rsi9_series.empty:
                        rsi['rsi9'] = float(rsi9_series.iloc[-1])
                
                # 计算VOL指标（成交量）和均量线（MAVOL）使用pandas-ta
                vol_data = {}
                # VOL：最新一根K线的成交量
                vol_data['vol'] = volumes[-1] if volumes else 0.0
                
                # 计算均量线（MAVOL）
                for length in mavol_lengths:
                    if len(volumes) >= length:
                        mavol_series = ta.sma(df['volume'], length=length)
                        if mavol_series is not None and not mavol_series.empty:
                            vol_data[f'mavol{length}'] = float(mavol_series.iloc[-1])
                        else:
                            vol_data[f'mavol{length}'] = 0.0
                            logger.warning(
                                f'[VOL] 无法计算MAVOL{length}: pandas-ta返回空结果'
                            )
                    else:
                        # 数据不足：使用所有可用数据的平均值
                        if len(volumes) > 0:
                            vol_data[f'mavol{length}'] = sum(volumes) / len(volumes)
                            logger.warning(
                                f'[VOL] 数据不足: MAVOL{length}需要{length}个数据点，实际只有{len(volumes)}个，使用所有可用数据计算'
                            )
                        else:
                            vol_data[f'mavol{length}'] = 0.0
                            logger.warning(f'[VOL] 无数据: 无法计算MAVOL{length}')
                
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
                
                # 创建pandas DataFrame用于技术指标计算
                df = pd.DataFrame({
                    'close': closes,
                    'volume': volumes
                })
                
                # 实时计算MA值（简单移动平均）使用pandas-ta
                ma_values = {}
                for length in ma_lengths:
                    if len(closes) >= length:
                        ma_series = ta.sma(df['close'], length=length)
                        if ma_series is not None and not ma_series.empty:
                            ma_values[f'ma{length}'] = float(ma_series.iloc[-1])
                        else:
                            ma_values[f'ma{length}'] = 0.0
                    else:
                        ma_values[f'ma{length}'] = 0.0
                        logger.warning(
                            f'[MA] 数据不足: MA{length}需要至少{length}根K线数据，实际只有{len(closes)}根，无法计算'
                        )
                
                # 实时计算MACD指标使用pandas-ta
                macd = {'dif': 0.0, 'dea': 0.0, 'bar': 0.0}
                if len(closes) >= 26:  # MACD需要至少26个数据点
                    macd_df = ta.macd(df['close'], fast=12, slow=26, signal=9)
                    if macd_df is not None and not macd_df.empty:
                        # pandas-ta返回的列名可能因版本而异，尝试几种常见的命名
                        dif_col = None
                        dea_col = None
                        bar_col = None
                        
                        # 查找对应的列
                        for col in macd_df.columns:
                            if 'MACDh' in col or 'histogram' in col or 'bar' in col.lower():
                                bar_col = col
                            elif 'MACDs' in col or 'signal' in col:
                                dea_col = col
                            elif 'MACD_' in col or 'macd' in col.lower():
                                dif_col = col
                        
                        # 如果找不到标准列名，使用索引
                        if dif_col is None and len(macd_df.columns) >= 1:
                            dif_col = macd_df.columns[0]
                        if dea_col is None and len(macd_df.columns) >= 2:
                            dea_col = macd_df.columns[1]
                        if bar_col is None and len(macd_df.columns) >= 3:
                            bar_col = macd_df.columns[2]
                        
                        # 获取最新值
                        if dif_col and dif_col in macd_df.columns:
                            macd['dif'] = float(macd_df[dif_col].iloc[-1])
                        if dea_col and dea_col in macd_df.columns:
                            macd['dea'] = float(macd_df[dea_col].iloc[-1])
                        if bar_col and bar_col in macd_df.columns:
                            macd['bar'] = float(macd_df[bar_col].iloc[-1])
                else:
                    logger.warning(f'[MACD] 数据不足: 需要至少26个数据点，实际只有{len(closes)}个')
                
                # 实时计算RSI指标使用pandas-ta
                rsi = {'rsi6': 50.0, 'rsi9': 50.0}
                # 计算RSI(6)
                if len(closes) >= 7:  # RSI(6)需要至少7个数据点
                    rsi6_series = ta.rsi(df['close'], length=6)
                    if rsi6_series is not None and not rsi6_series.empty:
                        rsi['rsi6'] = float(rsi6_series.iloc[-1])
                
                # 计算RSI(9)
                if len(closes) >= 10:  # RSI(9)需要至少10个数据点
                    rsi9_series = ta.rsi(df['close'], length=9)
                    if rsi9_series is not None and not rsi9_series.empty:
                        rsi['rsi9'] = float(rsi9_series.iloc[-1])
                
                # 计算VOL指标（成交量）和均量线（MAVOL）使用pandas-ta
                vol_data = {}
                # VOL：最新一根K线的成交量
                vol_data['vol'] = volumes[-1] if volumes else 0.0
                
                # 计算均量线（MAVOL）
                for length in mavol_lengths:
                    if len(volumes) >= length:
                        mavol_series = ta.sma(df['volume'], length=length)
                        if mavol_series is not None and not mavol_series.empty:
                            vol_data[f'mavol{length}'] = float(mavol_series.iloc[-1])
                        else:
                            vol_data[f'mavol{length}'] = 0.0
                            logger.warning(
                                f'[VOL] 无法计算MAVOL{length}: pandas-ta返回空结果'
                            )
                    else:
                        # 数据不足：使用所有可用数据的平均值
                        if len(volumes) > 0:
                            vol_data[f'mavol{length}'] = sum(volumes) / len(volumes)
                            logger.warning(
                                f'[VOL] 数据不足: MAVOL{length}需要{length}个数据点，实际只有{len(volumes)}个，使用所有可用数据计算'
                            )
                        else:
                            vol_data[f'mavol{length}'] = 0.0
                            logger.warning(f'[VOL] 无数据: 无法计算MAVOL{length}')
                
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
