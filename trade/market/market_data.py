"""
市场数据获取模块 - 从币安 USDS-M 期货与 binance-service 获取实时市场数据。

K 线技术指标由 binance-service（get_klines_with_indicators）计算；本模块不在 Python 内实现指标公式。
"""
import time
import logging
import threading
import trade.common.config as app_config
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from trade.common.binance_futures import BinanceFuturesClient
from trade.common.database.database_market_tickers import MarketTickersDatabase
from trade.common.database.database_futures import FuturesDatabase

logger = logging.getLogger(__name__)


def _ensure_usdt_suffix(symbol: str, quote_asset: str = 'USDT') -> str:
    """
    确保symbol以USDT结尾，如果没有则添加，防止重复添加
    
    Args:
        symbol: 交易对符号（如 'BTC' 或 'BTCUSDT'）
        quote_asset: 计价资产，默认为 'USDT'
        
    Returns:
        格式化后的symbol，确保以USDT结尾（如 'BTCUSDT'）
    """
    if not symbol:
        return symbol
    
    symbol_upper = symbol.upper()
    quote_asset_upper = quote_asset.upper()
    
    # 检查是否已经以quote_asset结尾，避免重复添加
    if not symbol_upper.endswith(quote_asset_upper):
        return f"{symbol_upper}{quote_asset_upper}"
    return symbol_upper


class MarketDataFetcher:
    """
    市场数据获取器：价格、多周期带指标 K 线（binance-service）、涨跌榜等。
    K 线内嵌指标由服务端计算，本类不包含 TA-Lib 等指标公式实现。
    """

    def __init__(self, db):
        """
        初始化市场数据获取器
        
        Args:
            db: 数据库实例（用于获取配置信息和涨跌榜数据）
        
        Note:
            - 自动初始化币安期货客户端和MySQL数据库连接
            - 如果API密钥未配置，期货客户端将为None（部分功能不可用）
            - 所有数据均为实时获取，不使用缓存
        """
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
        self._mysql_db: Optional[MarketTickersDatabase] = None
        self._futures_db: Optional[FuturesDatabase] = None
        self._init_futures_client()
        self._init_mysql_db()
        self._init_futures_db()

    # ============ Initialization Methods ============

    # ============ 初始化方法 ============
    
    def _init_futures_client(self):
        """
        初始化币安期货客户端
        
        从配置文件读取API密钥和密钥，创建BinanceFuturesClient实例。
        如果API密钥未配置，客户端将为None，部分功能将不可用。
        
        Note:
            - API密钥从app_config读取
            - 支持测试网络（通过BINANCE_TESTNET配置）
            - 初始化失败时记录警告日志，但不抛出异常
        """
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

    def _init_mysql_db(self):
        """
        初始化MySQL数据库连接
        
        创建MarketTickersDatabase实例，用于查询涨跌榜数据。
        如果连接失败，_mysql_db将为None，涨跌榜功能将不可用。
        
        Note:
            - 自动初始化数据库表（auto_init_tables=True）
            - 连接失败时记录警告日志，但不抛出异常
        """
        try:
            self._mysql_db = MarketTickersDatabase()
            logger.info('[MySQL] MySQL database connection initialized')
        except Exception as exc:
            logger.warning('[MySQL] Failed to initialize MySQL connection: %s', exc)
            self._mysql_db = None
    
    def _init_futures_db(self):
        """
        初始化期货合约配置数据库连接
        
        创建FuturesDatabase实例，用于查询期货合约配置数据。
        如果连接失败，_futures_db将为None，期货配置功能将不可用。
        
        Note:
            - 使用db的连接池（如果可用）
            - 连接失败时记录警告日志，但不抛出异常
        """
        try:
            pool = self.db._pool if hasattr(self.db, '_pool') else None
            self._futures_db = FuturesDatabase(pool=pool)
            logger.info('[Futures] Futures database connection initialized')
        except Exception as exc:
            logger.warning('[Futures] Failed to initialize Futures database connection: %s', exc)
            self._futures_db = None

    # ============ 工具方法 ============
    
    def _log_api_error(self, api_name: str, scenario: str, error_type: str,
                       symbol: str = None, error_msg: str = "", level: str = "WARN"):
        """
        统一的API错误日志记录格式
        
        Args:
            api_name: API名称（如'BINANCE', 'MYSQL'）
            scenario: 场景描述（如'获取价格', '查询涨跌榜'）
            error_type: 错误类型（如'连接失败', '数据解析错误'）
            symbol: 可选的交易对符号
            error_msg: 错误消息详情
            level: 日志级别（'ERROR', 'WARN', 'INFO'），默认为'WARN'
        """
        symbol_str = f"[币种:{symbol}]" if symbol else ""
        log_msg = f"[API:{api_name.upper()}][场景:{scenario}]{symbol_str}[错误类型:{error_type}] {error_msg}"

        if level == "ERROR":
            logger.error(log_msg)
        elif level == "INFO":
            logger.info(log_msg)
        else:
            logger.warning(log_msg)

    def _get_configured_futures(self) -> List[Dict]:
        """
        获取数据库中配置的期货合约列表
        
        Returns:
            List[Dict]: 期货配置列表，每个元素包含symbol、contract_symbol等字段
        
        Note:
            - 如果没有配置的合约，返回空列表并记录警告日志
        """
        if not self._futures_db:
            logger.warning('[配置] Futures database not initialized')
            return []
        futures = self._futures_db.get_future_configs()
        if not futures:
            logger.warning('[配置] 未检测到任何已持仓的USDS-M合约，等待交易产生持仓后自动记录')
        return futures
    
    def get_configured_futures_symbols(self) -> List[Dict]:
        """
        【新增方法】获取futures表中配置的所有交易对列表（用于AI交易决策）
        
        此方法用于支持symbol_source='future'的场景，从futures表获取所有已配置的交易对，
        而不是从涨跌榜获取。返回格式与leaderboard格式兼容，确保后续处理逻辑一致。
        
        调用链：
        trading_engine._select_buy_candidates() -> market_data.get_configured_futures_symbols()
        当模型的symbol_source='future'时，会调用此方法获取交易对列表。
        
        注意：
        - 返回的交易对价格、成交量、技术指标等字段初始值为0或空，需要后续实时获取
        - 后续会通过get_current_prices()和_merge_timeframe_data()补充实时数据
        
        Returns:
            交易对列表，格式与leaderboard返回格式兼容，包含：
            - symbol: 交易对符号
            - contract_symbol: 合约符号（如BTCUSDT）
            - name: 交易对名称
            - exchange: 交易所名称
            - price: 价格（初始0.0，需实时获取）
            - quote_volume: 成交量（初始0.0，需实时获取）
            - change_percent: 涨跌幅（初始0.0，需实时获取）
            - timeframes: 技术指标（初始{}，需实时计算）
        """
        if not self._futures_db:
            logger.warning('[配置] Futures database not initialized')
            return []
        futures = self._futures_db.get_future_configs()
        if not futures:
            logger.debug('[Futures] 未检测到任何已配置的USDS-M合约')
            return []
        
        # 【数据格式转换】转换为与leaderboard兼容的格式，确保后续处理逻辑一致
        # 这样无论是从leaderboard还是futures表获取，后续的价格获取、技术指标计算等逻辑都可以复用
        result = []
        for future in futures:
            symbol = future.get('symbol', '')
            if not symbol:
                continue
            
            result.append({
                'symbol': symbol,
                'contract_symbol': future.get('contract_symbol') or f"{symbol}USDT",
                'name': future.get('name', symbol),
                'exchange': future.get('exchange', 'BINANCE_FUTURES'),
                'price': 0.0,  # 【占位符】价格需要后续通过get_current_prices()实时获取
                'quote_volume': 0.0,  # 【占位符】成交量需要后续实时获取
                'change_percent': 0.0,  # 【占位符】涨跌幅需要后续实时获取
                'timeframes': {}  # 【占位符】技术指标需要后续通过_merge_timeframe_data()实时计算
            })
        
        logger.debug(f'[Futures] 获取到 {len(result)} 个已配置的交易对')
        return result

    # ============ 价格获取方法 ============

    def get_prices(self, symbols: Optional[List[str]] = None) -> Dict[str, Dict]:
        """
        获取最新价格数据（从24_market_tickers表获取）
        
        从数据库的24_market_tickers表中获取最新价格数据，包括价格、涨跌百分比和当日成交额。
        如果无法获取数据库数据，则返回空字典。
        
        Args:
            symbols: 可选的交易对符号列表，如果为None则返回所有已配置的交易对
            
        Returns:
            价格数据字典，key为交易对符号，value为价格信息。如果数据库获取失败，返回空字典。
        """
        now = datetime.now(timezone(timedelta(hours=8)))
        
        # 从数据库24_market_tickers表获取价格数据
        if self._mysql_db:
            try:
                # 构建查询SQL
                query = """
                SELECT 
                    `symbol`, `last_price`, `change_percent_text`, `quote_volume`,
                    `event_time`
                FROM `24_market_tickers`
                WHERE 1=1
                """
                
                params = []
                if symbols and len(symbols) > 0:
                    placeholders = ', '.join(['%s'] * len(symbols))
                    query += f" AND `symbol` IN ({placeholders})"
                    params.extend(symbols)
                
                # 执行查询
                rows = self._mysql_db.query(query, tuple(params))
                
                # 处理查询结果
                result = {}
                for row in rows:
                    if len(row) >= 5:
                        symbol = row[0]
                        result[symbol] = {
                            'symbol': symbol,
                            'price': float(row[1]) if row[1] is not None else 0.0,
                            'last_price': float(row[1]) if row[1] is not None else 0.0,
                            'change_percent_text': row[2] if row[2] is not None else '0.00%',
                            'change_percent': float(row[2].rstrip('%')) if row[2] and row[2] != 'N/A' else 0.0,
                            'change_24h': float(row[2].rstrip('%')) if row[2] and row[2] != 'N/A' else 0.0,
                            'quote_volume': float(row[3]) if row[3] is not None else 0.0,
                            'event_time': row[4] if row[4] is not None else now,
                            'source': 'database',
                            'price_date': now.strftime('%Y-%m-%d'),
                            # 保留原有结构的兼容字段
                            'name': symbol.replace('USDT', '') if symbol.endswith('USDT') else symbol,
                            'exchange': 'BINANCE_FUTURES',
                            'contract_symbol': symbol
                        }
                
                logger.info(f'[Prices] Retrieved {len(result)} price records from database')
                return result
                
            except Exception as e:
                logger.error(f'[Prices] Failed to retrieve prices from database: {e}')
        
        # 如果数据库不可用或查询失败，返回空字典
        logger.warning('[Prices] No price data available from database')
        return {}

    def get_current_prices(self, symbols: List[str] = None) -> Dict[str, Dict]:
        """
        获取当前期货价格（从API获取实时价格）
        
        此方法从币安API获取实时价格数据，确保数据的最高实时性。
        
        Args:
            symbols: 交易对符号列表，必须提供，如果为None或空列表则返回空字典
            
        Returns:
            价格数据字典，key为交易对符号，value为价格信息
        """
        # 如果没有提供symbols参数或为空，直接返回空字典
        if not symbols:
            return {}

        # 确保所有symbol都以USDT结尾
        quote_asset = getattr(self, '_futures_quote_asset', 'USDT')
        formatted_symbols = [_ensure_usdt_suffix(symbol, quote_asset) for symbol in symbols]
        
        # 从API获取实时价格数据
        if self._futures_client:
            try:
                # 调用get_symbol_prices方法获取实时价格
                api_prices = self._futures_client.get_symbol_prices(formatted_symbols)
                
                # 处理查询结果，确保返回格式与原来一致
                result = {}
                symbol_mapping = dict(zip(formatted_symbols, symbols))  # formatted -> original
                now = datetime.now(timezone(timedelta(hours=8)))
                
                for formatted_symbol, price_data in api_prices.items():
                    original_symbol = symbol_mapping.get(formatted_symbol, formatted_symbol)
                    
                    # 从API返回的数据中提取价格
                    price = float(price_data.get('price', 0.0)) if price_data.get('price') else 0.0
                    
                    # 由于API只返回价格，没有涨跌幅和成交量，我们需要使用默认值
                    # 这些字段将在get_prices方法中从数据库获取
                    result[original_symbol] = {
                        'symbol': original_symbol,
                        'price': price,
                        'last_price': price,
                        'change_percent_text': '0.00%',
                        'change_percent': 0.0,
                        'change_24h': 0.0,  # 兼容前端使用的字段名
                        'quote_volume': 0.0,
                        'event_time': now,
                        'source': 'api',
                        'price_date': now.strftime('%Y-%m-%d'),
                        'name': original_symbol.replace('USDT', '') if original_symbol.endswith('USDT') else original_symbol,
                        'exchange': 'BINANCE_FUTURES',
                        'contract_symbol': formatted_symbol
                    }
                
                logger.info(f'[Current Prices] Retrieved {len(result)} price records from API')
                return result
                
            except Exception as e:
                logger.error(f'[Current Prices] Failed to retrieve prices from API: {e}')
        
        # 如果API不可用或查询失败，返回空字典
        logger.warning('[Current Prices] No price data available from API')
        return {}
    
    def get_current_prices_by_contract(self, contract_symbols: List[str]) -> Dict[str, Dict]:
        """
        通过合约符号获取当前期货价格（从API获取实时价格）
        
        此方法与get_current_prices类似，但接受合约符号列表而不是基础符号列表，
        并以合约符号为键返回价格数据。
        
        Args:
            contract_symbols: 合约符号列表（如['BTCUSDT', 'ETHUSDT']）
            
        Returns:
            价格数据字典，key为合约符号，value为价格信息
        """
        if not contract_symbols:
            return {}
        
        # 确保所有contract_symbol都以USDT结尾
        quote_asset = getattr(self, '_futures_quote_asset', 'USDT')
        formatted_contract_symbols = [_ensure_usdt_suffix(symbol, quote_asset) for symbol in contract_symbols]
        
        # 从API获取实时价格数据
        if self._futures_client:
            try:
                # 调用get_symbol_prices方法获取实时价格
                api_prices = self._futures_client.get_symbol_prices(formatted_contract_symbols)
                
                # 处理查询结果，确保返回格式与原来一致
                prices = {}
                symbol_mapping = dict(zip(formatted_contract_symbols, contract_symbols))  # formatted -> original
                now = datetime.now(timezone(timedelta(hours=8)))
                
                for formatted_symbol, price_data in api_prices.items():
                    original_symbol = symbol_mapping.get(formatted_symbol, formatted_symbol)
                    
                    # 从API返回的数据中提取价格
                    price = float(price_data.get('price', 0.0)) if price_data.get('price') else 0.0
                    
                    # 由于API只返回价格，没有涨跌幅和成交量，我们需要使用默认值
                    # 这些字段将在get_prices方法中从数据库获取
                    prices[original_symbol] = {
                        'price': price,
                        'last_price': price,  # 同时提供last_price字段以便兼容
                        'change_percent': 0.0,
                        'change_percent_text': '0.00%',
                        'quote_volume': 0.0,
                        'event_time': now,
                        'source': 'api'
                    }
                
                logger.info(f'[Current Prices By Contract] Retrieved {len(prices)} price records from API')
                return prices
                
            except Exception as e:
                logger.error(f'[Current Prices By Contract] Failed to retrieve prices from API: {e}')
        
        # 如果API不可用或查询失败，返回空字典
        logger.warning('[Current Prices By Contract] No price data available from API')
        return {}

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
        quote_asset = getattr(self, '_futures_quote_asset', 'USDT')
        for future in futures:
            base_symbol = future['symbol']
            # 确保base_symbol以USDT结尾
            formatted_base_symbol = _ensure_usdt_suffix(base_symbol, quote_asset)
            contract_symbol = future.get('contract_symbol')
            if contract_symbol:
                # 如果提供了contract_symbol，也确保它以USDT结尾
                contract_symbol = _ensure_usdt_suffix(contract_symbol, quote_asset)
            else:
                # 如果没有提供contract_symbol，使用format_symbol方法（该方法已实现防重复逻辑）
                contract_symbol = self._futures_client.format_symbol(formatted_base_symbol)
            symbol_map[base_symbol] = contract_symbol.upper()
        tickers = self._futures_client.get_24h_ticker(list(symbol_map.values()))
        spot_prices = self._futures_client.get_symbol_prices(list(symbol_map.values()))

        for symbol, futures_symbol in symbol_map.items():
            payload = tickers.get(futures_symbol)
            if not payload:
                continue
            try:
                last_price = round(float(
                    payload.get('lastPrice')
                    or spot_prices.get(futures_symbol, {}).get('price', 0)
                ), 7)  # 价格保留7位小数
                change_percent = float(payload.get('priceChangePercent', 0))
                quote_volume = float(payload.get('quoteVolume', payload.get('volume', 0)))
            except (ValueError, TypeError):
                continue

            future_meta = next((f for f in futures if f['symbol'] == symbol), {})
            prices[symbol] = {
                'price': last_price,
                'name': future_meta.get('name', symbol),
                'exchange': future_meta.get('exchange', 'BINANCE_FUTURES'),
                'change_24h': change_percent,
                'quote_volume': quote_volume,
                'timeframes': {},
            }

        return prices

    # ============ 市场数据获取方法 ============
    
    def _get_market_data_by_interval(self, symbol: str, interval: str, limit: int, return_count: int) -> Dict:
        """
        通用方法：获取指定交易对和时间周期的K线数据（预计算技术指标）。

        指标由 binance-service 的 KlineIndicatorCalculator 计算（与 MCP / Java 一致），
        本方法仅请求 ``get_klines_with_indicators`` 并裁剪为 return_count 根。

        Args:
            symbol: 交易对符号（如 'BTC' 或 'BTCUSDT'）
            interval: 时间周期（如 '1m', '5m', '1h', '4h', '1d'）
            limit: 请求的K线数量（至少500，以满足历史窗口）
            return_count: 返回最近若干根带完整指标的K线

        Returns:
            市场数据字典，包含symbol、timeframe、klines（每根K线含indicators字段）和metadata字段
        """
        if not self._futures_client:
            logger.warning(f'[MarketData] Futures client unavailable for {symbol}')
            return {}

        # 确保symbol以USDT结尾，防止重复添加
        quote_asset = getattr(self, '_futures_quote_asset', 'USDT')
        formatted_symbol = _ensure_usdt_suffix(symbol, quote_asset)

        # 格式化交易对符号（format_symbol方法也有防重复逻辑，双重保险）
        symbol_key = self._futures_client.format_symbol(formatted_symbol)

        try:
            fetch_limit = max(limit, 500)
            klines_with_indicators = self._futures_client.get_klines_with_indicators(
                symbol_key,
                interval,
                limit=fetch_limit,
            )

            if not klines_with_indicators:
                logger.warning(
                    f'[MarketData] 无带指标K线 {symbol} {interval}（limit={fetch_limit}）；'
                    f'需启用 BINANCE_SERVICE 且原始K线≥99 根，或检查服务可用性'
                )
                return {}

            actual_return_count = min(return_count, len(klines_with_indicators))
            klines = (
                klines_with_indicators[-actual_return_count:]
                if len(klines_with_indicators) > actual_return_count
                else klines_with_indicators
            )

            logger.debug(
                f'[MarketData] Returning {len(klines)} klines for {symbol} {interval} '
                f'(requested: {return_count}, available from service: {len(klines_with_indicators)})'
            )

            # 构建K线数据列表（已包含指标数据）
            kline_data_list = []

            def _bar_float(x: object, default: float = 0.0) -> float:
                try:
                    if x is None:
                        return default
                    return float(x)
                except (TypeError, ValueError):
                    return default

            for kline in klines:
                try:
                    ot = kline.get('open_time', 0)
                    open_time_ms = int(float(ot)) if ot not in (None, '') else 0
                    open_time_dt_str = kline.get('open_time_dt_str')
                    close_time_ms = kline.get('close_time')
                    close_time_dt_str = kline.get('close_time_dt_str')

                    # 将毫秒时间戳转换为 datetime 字符串（精确到秒后两位小数）
                    dt = datetime.fromtimestamp(open_time_ms / 1000.0, tz=timezone.utc)
                    milliseconds = open_time_ms % 1000
                    time_str = dt.strftime('%Y-%m-%d %H:%M:%S') + f'.{milliseconds // 10:02d}'

                    # 构建K线数据（包含所有字段和指标）
                    kline_data = {
                        'time': time_str,
                        'open': _bar_float(kline.get('open')),
                        'high': _bar_float(kline.get('high')),
                        'low': _bar_float(kline.get('low')),
                        'close': _bar_float(kline.get('close')),
                        'volume': _bar_float(kline.get('volume')),
                        'open_time': open_time_ms,
                        'open_time_dt_str': open_time_dt_str,
                        'indicators': kline.get('indicators', {}) if isinstance(kline.get('indicators'), dict) else {}
                    }
                    # 币安 API 第 8 列为计价成交额；服务端键名为 quote_asset_volume。策略常写 quote_volume，一并提供。
                    qv_raw = kline.get('quote_asset_volume')
                    if qv_raw is not None and str(qv_raw).strip() != '':
                        try:
                            qv = float(qv_raw)
                            kline_data['quote_asset_volume'] = qv
                            kline_data['quote_volume'] = qv
                        except (TypeError, ValueError):
                            pass

                    if close_time_ms:
                        kline_data['close_time'] = close_time_ms
                    if close_time_dt_str:
                        kline_data['close_time_dt_str'] = close_time_dt_str

                    kline_data_list.append(kline_data)
                except (ValueError, TypeError, KeyError, IndexError) as e:
                    logger.warning(f'[MarketData] Failed to parse kline: {e}')
                    continue
            
            if not kline_data_list or len(kline_data_list) < 1:
                logger.debug(f'[MarketData] Insufficient data for {symbol} {interval}: {len(kline_data_list)} klines')
                return {}
            
            # 组装返回数据（不包含indicators）
            now = datetime.now(timezone.utc)
            result = {
                'symbol': symbol,
                'timeframe': interval,
                'klines': kline_data_list,
                'metadata': {
                    'source': 'Binance Futures (indicators: binance-service)',
                    'last_update': now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-4],  # 精确到秒后两位小数
                    'total_bars': len(kline_data_list)
                }
            }
            
            return result
            
        except Exception as e:
            logger.warning(f'[MarketData] 获取 {symbol} {interval} 数据失败: {e}', exc_info=True)
            return {}

    def get_market_data_1m(self, symbol: str) -> Dict:
        """
        获取1分钟时间周期的市场数据（包含预计算的技术指标）

        Args:
            symbol: 交易对符号（如 'BTC'）

        Returns:
            市场数据字典，包含symbol、timeframe、klines（每根K线含indicators字段）和metadata字段
        """
        return self._get_market_data_by_interval(symbol, '1m', limit=500, return_count=400)

    def get_market_data_5m(self, symbol: str) -> Dict:
        """
        获取5分钟时间周期的市场数据（包含预计算的技术指标）

        Args:
            symbol: 交易对符号（如 'BTC'）

        Returns:
            市场数据字典，包含symbol、timeframe、klines（每根K线含indicators字段）和metadata字段
        """
        return self._get_market_data_by_interval(symbol, '5m', limit=500, return_count=400)

    def get_market_data_15m(self, symbol: str) -> Dict:
        """
        获取15分钟时间周期的市场数据（包含预计算的技术指标）

        Args:
            symbol: 交易对符号（如 'BTC'）

        Returns:
            市场数据字典，包含symbol、timeframe、klines（每根K线含indicators字段）和metadata字段
        """
        return self._get_market_data_by_interval(symbol, '15m', limit=500, return_count=400)

    def get_market_data_30m(self, symbol: str) -> Dict:
        """
        获取30分钟时间周期的市场数据（包含预计算的技术指标）

        Args:
            symbol: 交易对符号（如 'BTC'）

        Returns:
            市场数据字典，包含symbol、timeframe、klines（每根K线含indicators字段）和metadata字段
        """
        return self._get_market_data_by_interval(symbol, '30m', limit=500, return_count=400)

    def get_market_data_1h(self, symbol: str) -> Dict:
        """
        获取1小时时间周期的市场数据（包含预计算的技术指标）

        Args:
            symbol: 交易对符号（如 'BTC'）

        Returns:
            市场数据字典，包含symbol、timeframe、klines（每根K线含indicators字段）和metadata字段
        """
        return self._get_market_data_by_interval(symbol, '1h', limit=400, return_count=300)

    def get_market_data_4h(self, symbol: str) -> Dict:
        """
        获取4小时时间周期的市场数据（包含预计算的技术指标）

        Args:
            symbol: 交易对符号（如 'BTC'）

        Returns:
            市场数据字典，包含symbol、timeframe、klines（每根K线含indicators字段）和metadata字段
        """
        return self._get_market_data_by_interval(symbol, '4h', limit=400, return_count=300)

    def get_market_data_1d(self, symbol: str) -> Dict:
        """
        获取1天时间周期的市场数据（包含预计算的技术指标）

        Args:
            symbol: 交易对符号（如 'BTC'）

        Returns:
            市场数据字典，包含symbol、timeframe、klines（每根K线含indicators字段）和metadata字段
        """
        return self._get_market_data_by_interval(symbol, '1d', limit=200, return_count=100)

    def merge_timeframe_klines_for_contract(self, contract_symbol: str) -> Dict:
        """
        合并多周期带指标 K 线（不含周线 1w，避免周线历史不足导致服务端无数据告警）。
        与 look_engine.merge_timeframe_klines / TradingEngine._merge_timeframe_data 对齐。
        """
        symbol_upper = contract_symbol.upper()
        if not symbol_upper.endswith("USDT"):
            formatted_symbol = f"{symbol_upper}USDT"
        else:
            formatted_symbol = symbol_upper

        timeframe_methods = {
            "1m": self.get_market_data_1m,
            "5m": self.get_market_data_5m,
            "15m": self.get_market_data_15m,
            "30m": self.get_market_data_30m,
            "1h": self.get_market_data_1h,
            "4h": self.get_market_data_4h,
            "1d": self.get_market_data_1d,
        }

        merged_data: Dict[str, Dict] = {formatted_symbol: {}}
        errors: List[str] = []

        for timeframe, method in timeframe_methods.items():
            try:
                data = method(formatted_symbol)
                if data:
                    klines = data.get("klines", [])
                    if klines:
                        merged_data[formatted_symbol][timeframe] = {"klines": klines}
                    else:
                        errors.append(f"{timeframe}: K线数据为空")
                else:
                    errors.append(f"{timeframe}: 返回数据为空")
            except Exception as e:
                errors.append(f"{timeframe}: {e}")
                logger.warning(
                    "[MarketData] 获取 %s %s 失败: %s", formatted_symbol, timeframe, e
                )

        if not merged_data[formatted_symbol] and errors:
            logger.warning(
                "[MarketData] 获取 %s 全周期失败: %s", formatted_symbol, errors
            )

        return merged_data

    # ============ Leaderboard Methods ===========

    def sync_leaderboard(self, force: bool = False, limit: Optional[int] = None) -> Dict[str, List[Dict]]:
        """
        同步涨幅榜数据（从 24_market_tickers 表查询）
        
        Args:
            force: 是否强制刷新（保留参数以兼容现有调用，但实际不使用）
            limit: 返回的数据条数限制
            
        Returns:
            涨幅榜数据字典，包含 gainers 和 losers
        """
        if limit is None:
            limit = getattr(app_config, 'FUTURES_TOP_GAINERS_LIMIT', 10)

        logger.info(
            '[Leaderboard] sync_leaderboard called | limit=%s (from 24_market_tickers)',
            limit
        )

        # 如果没有可用的 MySQL 连接，返回空数据
        if not self._mysql_db:
            logger.error('[Leaderboard] MySQL unavailable, returning empty data')
            return {'gainers': [], 'losers': []}

        try:
            # 从 24_market_tickers 表直接查询涨跌幅榜数据（一次查询获取）
            formatted_data = self._mysql_db.get_leaderboard_from_tickers(limit=limit)
            
            logger.info('[Leaderboard] Returning leaderboard payload from 24_market_tickers: gainers=%s losers=%s',
                        len(formatted_data.get('gainers', [])), len(formatted_data.get('losers', [])))
            return formatted_data
            
        except Exception as exc:
            logger.error('[Leaderboard] Failed to get leaderboard from 24_market_tickers: %s', exc, exc_info=True)
            return {'gainers': [], 'losers': []}

    def get_leaderboard(self, limit: Optional[int] = None) -> Dict[str, List[Dict]]:
        """Get leaderboard data (wrapper for sync_leaderboard)"""
        return self.sync_leaderboard(force=False, limit=limit)