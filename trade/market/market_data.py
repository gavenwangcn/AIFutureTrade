"""
市场数据获取模块 - 从币安USDS-M期货SDK获取实时市场数据

本模块提供MarketDataFetcher类，用于获取和管理实时市场数据，包括：
1. 价格数据：实时获取交易对的最新价格、涨跌幅、成交量等
2. 技术指标：计算MA、MACD、RSI、VOL等技术指标
3. 市场数据：获取不同时间周期的K线数据和指标
4. 涨跌榜：从数据库查询涨跌幅排行榜数据

主要功能：
- 价格获取：实时从币安API获取价格数据（无缓存，保证实时性）
- 技术指标计算：使用TA-Lib库计算多时间框架的技术指标
- 市场数据：提供1m、5m、15m、30m、1h、4h、1d、1w等8个时间周期的数据
- 涨跌榜同步：从24_market_tickers表查询涨跌幅排行榜

使用场景：
- 后端API：为前端提供价格、指标、涨跌榜等数据
- 交易：为交易引擎提供实时价格和技术指标数据
- 前端展示：为K线图、涨跌榜等组件提供数据支持
"""
import time
import logging
import threading
import trade.common.config as app_config
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import talib

from trade.common.binance_futures import BinanceFuturesClient
from trade.common.database.database_market_tickers import MarketTickersDatabase
from trade.common.database.database_futures import FuturesDatabase

logger = logging.getLogger(__name__)


def _calculate_rsi_tradingview(close_array: np.ndarray, period: int) -> np.ndarray:
    """
    使用TradingView的计算逻辑计算RSI（Wilder's Smoothing方法）

    与前端实现完全一致（frontend/KLineChart/indicators/rsi.ts）：
    - i==0：初始化AvgGain/AvgLoss
    - i < period：累计gain/loss
    - i == period-1：计算初始平均
    - i > period-1：Wilder's Smoothing
    - i >= period-1 输出RSI
    """
    if len(close_array) == 0:
        return np.full(0, np.nan)

    rsi = np.full(len(close_array), np.nan)
    avg_gain = 0.0
    avg_loss = 0.0

    for i in range(len(close_array)):
        prev_close = close_array[i - 1] if i > 0 else close_array[i]
        change = close_array[i] - prev_close
        gain = change if change > 0 else 0.0
        loss = -change if change < 0 else 0.0

        if i == 0:
            avg_gain = gain
            avg_loss = loss
        elif i < period:
            avg_gain += gain
            avg_loss += loss
            if i == period - 1:
                avg_gain = avg_gain / period
                avg_loss = avg_loss / period
        else:
            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period

        if i >= period - 1:
            if avg_loss != 0:
                rs = avg_gain / avg_loss
                rsi[i] = 100 - (100 / (1 + rs))
            else:
                rsi[i] = 100.0 if avg_gain > 0 else 50.0

    return rsi


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
    市场数据获取器
    
    负责从币安USDS-M期货API获取实时市场数据，包括价格、技术指标、K线数据等。
    所有数据均为实时获取，不使用缓存机制，以保证最高实时性。
    
    主要特性：
    - 实时价格获取：每次调用都直接请求交易所API
    - 多时间框架支持：支持1m到1w共7个时间周期
    - 技术指标计算：使用TA-Lib库计算MA、MACD、RSI、VOL等指标
    - 涨跌榜查询：从MySQL数据库的24_market_tickers表查询
    
    使用示例：
        fetcher = MarketDataFetcher(db)
        prices = fetcher.get_prices(['BTC', 'ETH'])
        indicators = fetcher.calculate_technical_indicators('BTC')
        leaderboard = fetcher.get_leaderboard(limit=10)
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

            # 不再实时生成 timeframes 数据，只在 AI 交易时通过 calculate_technical_indicators 计算
            future_meta = next((f for f in futures if f['symbol'] == symbol), {})
            prices[symbol] = {
                'price': last_price,
                'name': future_meta.get('name', symbol),
                'exchange': future_meta.get('exchange', 'BINANCE_FUTURES'),
                'change_24h': change_percent,
                'quote_volume': quote_volume,
                'timeframes': {}  # 不再实时生成，只在 AI 交易时计算
            }

        return prices

    # ============ 技术指标计算方法 ============

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
            '30m': '30m', # 30分钟线：中短期交易的重要参考
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
                    '30m': 120,  # 30分钟线：获取120根30分钟K线（约2.5天）
                    '15m': 120,  # 15分钟线：获取120根15分钟K线（约1.25天）
                    '5m': 120,   # 5分钟线：获取120根5分钟K线（约10小时）
                    '1m': 120    # 1分钟线：获取120根1分钟K线（约2小时）
                }
                limit = limit_map.get(label, 120)  # 默认获取120根K线
                
                # 构造币安API需要的交易对符号（添加计价资产后缀，如BTC -> BTCUSDT）
                symbol_key = self._futures_client.format_symbol(symbol)
                
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
                
                # 提取完整的OHLCV数据（TA-Lib库需要numpy数组格式）
                opens = []
                highs = []
                lows = []
                closes = []
                volumes = []
                timestamps = []
                for item in klines:
                    # 兼容旧的列表格式和新的字典格式
                    try:
                        # 如果是字典格式（新的实现）
                        if isinstance(item, dict):
                            opens.append(float(item.get('open', 0)))
                            highs.append(float(item.get('high', 0)))
                            lows.append(float(item.get('low', 0)))
                            closes.append(float(item.get('close', 0)))
                            volumes.append(float(item.get('volume', 0)))
                            timestamps.append(int(item['open_time']) if item.get('open_time') else 0)
                        # 如果是列表格式（旧的实现）
                        elif isinstance(item, (list, tuple)) and len(item) > 4:
                            opens.append(float(item[1]) if len(item) > 1 else 0.0)
                            highs.append(float(item[2]) if len(item) > 2 else 0.0)
                            lows.append(float(item[3]) if len(item) > 3 else 0.0)
                            closes.append(float(item[4]) if len(item) > 4 else 0.0)
                            volumes.append(float(item[5]) if len(item) > 5 else 0.0)
                            timestamps.append(int(item[0]) if len(item) > 0 and item[0] else 0)
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
                        open_time_ms = int(latest_kline['open_time']) if latest_kline.get('open_time') else None
                        kline_data = {
                            'open_time': open_time_ms,
                            'open_time_date': datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S') if open_time_ms else None,
                            'open': float(latest_kline['open']) if latest_kline.get('open') else 0.0,
                            'high': float(latest_kline['high']) if latest_kline.get('high') else 0.0,
                            'low': float(latest_kline['low']) if latest_kline.get('low') else 0.0,
                            'close': float(latest_kline['close']) if latest_kline.get('close') else 0.0,
                            'volume': float(latest_kline['volume']) if latest_kline.get('volume') else 0.0
                        }
                    else:
                        # 旧的列表格式
                        open_time_ms = int(latest_kline[0]) if len(latest_kline) > 0 and latest_kline[0] else None
                        kline_data = {
                            'open_time': open_time_ms,
                            'open_time_date': datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S') if open_time_ms else None,
                            'open': float(latest_kline[1]) if len(latest_kline) > 1 else 0.0,
                            'high': float(latest_kline[2]) if len(latest_kline) > 2 else 0.0,
                            'low': float(latest_kline[3]) if len(latest_kline) > 3 else 0.0,
                            'close': float(latest_kline[4]) if len(latest_kline) > 4 else 0.0,
                            'volume': float(latest_kline[5]) if len(latest_kline) > 5 else 0.0
                        }
                except (ValueError, TypeError, IndexError) as e:
                    logger.warning(f'[Indicators] Failed to parse kline data for {symbol} {label}: {e}')
                    continue
                
                # 转换为numpy数组用于TA-Lib计算（TA-Lib需要numpy数组格式）
                open_array = np.array(opens, dtype=np.float64)
                high_array = np.array(highs, dtype=np.float64)
                low_array = np.array(lows, dtype=np.float64)
                close_array = np.array(closes, dtype=np.float64)
                volume_array = np.array(volumes, dtype=np.float64)
                
                # 实时计算MA值（简单移动平均）使用TA-Lib
                ma_values = {}
                for length in ma_lengths:
                    if len(closes) >= length:
                        try:
                            ma_result = talib.SMA(close_array, timeperiod=length)
                            if ma_result is not None and len(ma_result) > 0:
                                last_value = ma_result[-1]
                                if not np.isnan(last_value) and not np.isinf(last_value):
                                    ma_values[f'ma{length}'] = float(last_value)
                                else:
                                    ma_values[f'ma{length}'] = 0.0
                            else:
                                ma_values[f'ma{length}'] = 0.0
                        except Exception as e:
                            ma_values[f'ma{length}'] = 0.0
                            logger.warning(
                                f'[MA] 无法计算MA{length}: {e}'
                            )
                    else:
                        ma_values[f'ma{length}'] = 0.0
                        logger.warning(
                            f'[MA] 数据不足: MA{length}需要至少{length}根K线数据，实际只有{len(closes)}根，无法计算'
                        )
                
                # 实时计算MACD指标使用TA-Lib
                macd = {'dif': 0.0, 'dea': 0.0, 'bar': 0.0}
                if len(closes) >= 26:  # MACD需要至少26个数据点
                    try:
                        # TA-Lib的MACD返回三个数组：macd, signal, histogram
                        macd_result, signal_result, histogram_result = talib.MACD(
                            close_array, 
                            fastperiod=12, 
                            slowperiod=26, 
                            signalperiod=9
                        )
                        if macd_result is not None and len(macd_result) > 0:
                            # DIF = MACD线
                            dif_value = macd_result[-1]
                            if not np.isnan(dif_value) and not np.isinf(dif_value):
                                macd['dif'] = float(dif_value)
                            
                            # DEA = Signal线
                            if signal_result is not None and len(signal_result) > 0:
                                dea_value = signal_result[-1]
                                if not np.isnan(dea_value) and not np.isinf(dea_value):
                                    macd['dea'] = float(dea_value)
                            
                            # BAR = Histogram = DIF - DEA
                            if histogram_result is not None and len(histogram_result) > 0:
                                bar_value = histogram_result[-1]
                                if not np.isnan(bar_value) and not np.isinf(bar_value):
                                    macd['bar'] = float(bar_value)
                                else:
                                    # 如果histogram为NaN，手动计算：BAR = DIF - DEA
                                    macd['bar'] = macd['dif'] - macd['dea']
                            else:
                                # 如果没有histogram，手动计算
                                macd['bar'] = macd['dif'] - macd['dea']
                    except Exception as e:
                        logger.warning(f'[MACD] 无法计算MACD: {e}')
                else:
                    logger.warning(f'[MACD] 数据不足: 需要至少26个数据点，实际只有{len(closes)}个')
                
                # 实时计算RSI指标使用TradingView的计算逻辑（Wilder's Smoothing方法）
                rsi = {'rsi6': 50.0, 'rsi9': 50.0}
                # 计算RSI(6)
                if len(closes) >= 7:  # RSI(6)需要至少7个数据点
                    try:
                        rsi6_result = _calculate_rsi_tradingview(close_array, period=6)
                        if rsi6_result is not None and len(rsi6_result) > 0:
                            rsi6_value = rsi6_result[-1]
                            if not np.isnan(rsi6_value) and not np.isinf(rsi6_value):
                                rsi['rsi6'] = float(rsi6_value)
                    except Exception as e:
                        logger.warning(f'[RSI] 无法计算RSI6: {e}')
                
                # 计算RSI(9)
                if len(closes) >= 10:  # RSI(9)需要至少10个数据点
                    try:
                        rsi9_result = _calculate_rsi_tradingview(close_array, period=9)
                        if rsi9_result is not None and len(rsi9_result) > 0:
                            rsi9_value = rsi9_result[-1]
                            if not np.isnan(rsi9_value) and not np.isinf(rsi9_value):
                                rsi['rsi9'] = float(rsi9_value)
                    except Exception as e:
                        logger.warning(f'[RSI] 无法计算RSI9: {e}')
                
                # 计算VOL指标（成交量）和均量线（MAVOL）使用pandas-ta
                vol_data = {}
                # VOL：最新一根K线的成交量
                vol_data['vol'] = volumes[-1] if volumes else 0.0
                
                # 获取最新K线的买入成交量和卖出成交量
                # 从klines中提取买入成交量数据
                buy_volumes = []
                for item in klines:
                    try:
                        # 如果是字典格式（新的实现）
                        if isinstance(item, dict):
                            buy_volume = float(item.get('taker_buy_base_volume', 0))
                            buy_volumes.append(buy_volume)
                        # 如果是列表格式（旧的实现）
                        elif isinstance(item, (list, tuple)) and len(item) > 10:
                            buy_volume = float(item[9])  # taker_buy_base_volume 是第10个元素（索引9）
                            buy_volumes.append(buy_volume)
                        else:
                            buy_volumes.append(0)
                    except (ValueError, TypeError, IndexError):
                        buy_volumes.append(0)
                
                # 计算最新K线的买入量和卖出量
                if buy_volumes:
                    vol_data['buy_vol'] = buy_volumes[-1]
                    vol_data['sell_vol'] = volumes[-1] - buy_volumes[-1] if volumes else 0
                else:
                    vol_data['buy_vol'] = 0
                    vol_data['sell_vol'] = 0
                
                # 计算均量线（MAVOL）- 使用pandas的rolling方法直接计算，更可靠
                for length in mavol_lengths:
                    if len(volumes) >= length:
                        try:
                            # 直接使用pandas的rolling方法计算volume的移动平均
                            mavol_value = df['volume'].rolling(window=length, min_periods=length).mean().iloc[-1]
                            vol_data[f'mavol{length}'] = float(mavol_value) if pd.notna(mavol_value) else 0.0
                        except Exception as e:
                            vol_data[f'mavol{length}'] = 0.0
                            logger.warning(
                                f'[VOL] 无法计算MAVOL{length}: {e}'
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
    
    # ============ 市场数据获取方法 ============

    def _calculate_indicators_for_klines(self, klines: List[Dict], symbol: str, interval: str) -> List[Dict]:
        """
        为所有K线计算技术指标

        此方法接收原始K线数据，为每根K线计算并添加技术指标。
        由于指标计算需要历史数据，不同指标需要不同数量的历史K线：
        - MA5/EMA5/RSI6/ATR7/MACD: 需要较少历史数据
        - MA99/EMA99: 需要99根历史数据
        - 如果K线不足，能计算出多少指标就给多少，计算不出来的指标值为0或默认值

        技术指标包括：
        - MA: 简单移动平均线 (5, 20, 60, 99)
        - EMA: 指数移动平均线 (5, 20, 30, 60, 99)
        - RSI: 相对强弱指数 (6, 9, 14) - 使用Wilder's Smoothing方法
        - MACD: 指数平滑异同移动平均线 (12, 26, 9)
        - KDJ: 随机指标 (60, 20, 5) - 使用TradingView计算逻辑
        - ATR: 平均真实波幅 (7, 14, 21) - 使用Wilder's Smoothing方法
        - VOL: 成交量及均量线 (5, 10, 60)

        Args:
            klines: 原始K线数据列表（可以是任意数量，不足时部分指标为空）
            symbol: 交易对符号
            interval: 时间周期

        Returns:
            包含指标数据的K线列表（返回所有K线，不足历史数据的K线指标部分为空）
        """
        if not klines or len(klines) == 0:
            logger.warning(f'[Indicators] No klines data for {symbol} {interval}')
            return []
        
        # 如果K线不足100根，记录警告但继续计算（能算多少算多少）
        if len(klines) < 100:
            logger.debug(f'[Indicators] Insufficient klines for {symbol} {interval}: {len(klines)} < 100, will calculate partial indicators')

        try:
            # 提取OHLCV数据为numpy数组
            opens = np.array([k['open'] for k in klines], dtype=np.float64)
            highs = np.array([k['high'] for k in klines], dtype=np.float64)
            lows = np.array([k['low'] for k in klines], dtype=np.float64)
            closes = np.array([k['close'] for k in klines], dtype=np.float64)
            volumes = np.array([k['volume'] for k in klines], dtype=np.float64)

            # 计算所有指标（返回与输入长度相同的数组）
            # MA指标
            ma5 = talib.SMA(closes, timeperiod=5)
            ma20 = talib.SMA(closes, timeperiod=20)
            ma60 = talib.SMA(closes, timeperiod=60)
            ma99 = talib.SMA(closes, timeperiod=99)

            # EMA指标（与前端K线一致的初始化逻辑）
            # EMA(t) = Close(t) * α + EMA(t-1) * (1 - α), α = 2 / (N + 1)
            # 初始化规则：
            # - i==0: EMA = close
            # - i < N-1: EMA = 累计均值(closeSums/(i+1))
            # - i == N-1: EMA = N日SMA(closeSums/N)
            # - i > N-1: 使用递推公式
            def _ema_frontend(values: np.ndarray, period: int) -> np.ndarray:
                ema_arr = np.zeros_like(values, dtype=np.float64)
                close_sum = 0.0
                alpha = 2.0 / (period + 1.0)
                for i in range(len(values)):
                    close = float(values[i])
                    if i == 0:
                        ema_arr[i] = close
                        close_sum = close
                    elif i < period - 1:
                        close_sum += close
                        ema_arr[i] = close_sum / (i + 1)
                    elif i == period - 1:
                        close_sum += close
                        ema_arr[i] = close_sum / period
                    else:
                        ema_arr[i] = close * alpha + ema_arr[i - 1] * (1 - alpha)
                return ema_arr

            ema5 = _ema_frontend(closes, 5)
            ema20 = _ema_frontend(closes, 20)
            ema30 = _ema_frontend(closes, 30)
            ema60 = _ema_frontend(closes, 60)
            ema99 = _ema_frontend(closes, 99)

            # RSI指标（使用Wilder's Smoothing方法）
            rsi6 = _calculate_rsi_tradingview(closes, period=6)
            rsi9 = _calculate_rsi_tradingview(closes, period=9)
            rsi14 = _calculate_rsi_tradingview(closes, period=14)

            # MACD指标（与前端K线一致的计算逻辑）
            # DIF/DEA 与前端算法一致，柱值 = (DIF - DEA) * 2
            def _macd_frontend(values: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9):
                dif_arr = np.full(len(values), np.nan)
                dea_arr = np.full(len(values), np.nan)
                bar_arr = np.full(len(values), np.nan)
                ema_short = 0.0
                ema_long = 0.0
                close_sum = 0.0
                dif_sum = 0.0
                dea = 0.0
                max_period = max(fast, slow)

                for i in range(len(values)):
                    close = float(values[i])
                    close_sum += close

                    if i >= fast - 1:
                        if i > fast - 1:
                            ema_short = (2 * close + (fast - 1) * ema_short) / (fast + 1)
                        else:
                            ema_short = close_sum / fast

                    if i >= slow - 1:
                        if i > slow - 1:
                            ema_long = (2 * close + (slow - 1) * ema_long) / (slow + 1)
                        else:
                            ema_long = close_sum / slow

                    if i >= max_period - 1:
                        dif = ema_short - ema_long
                        dif_arr[i] = dif
                        dif_sum += dif
                        if i >= max_period + signal - 2:
                            if i > max_period + signal - 2:
                                dea = (dif * 2 + dea * (signal - 1)) / (signal + 1)
                            else:
                                dea = dif_sum / signal
                            dea_arr[i] = dea
                            bar_arr[i] = (dif - dea) * 2

                return dif_arr, dea_arr, bar_arr

            macd_dif, macd_dea, macd_bar = _macd_frontend(closes, fast=12, slow=26, signal=9)

            # KDJ指标（使用TradingView计算逻辑，参数60,20,5）
            kdj_k, kdj_d, kdj_j = self._calculate_kdj_tradingview(highs, lows, closes, k_period=60, smooth_k=20, smooth_d=5)

            # ATR指标（使用Wilder's Smoothing方法）
            atr7 = self._calculate_atr_tradingview(highs, lows, closes, period=7)
            atr14 = self._calculate_atr_tradingview(highs, lows, closes, period=14)
            atr21 = self._calculate_atr_tradingview(highs, lows, closes, period=21)

            # VOL均量线
            mavol5 = talib.SMA(volumes, timeperiod=5)
            mavol10 = talib.SMA(volumes, timeperiod=10)
            mavol60 = talib.SMA(volumes, timeperiod=60)

            # 为每根K线添加指标数据（返回所有K线，不足历史数据的K线指标部分为空）
            result_klines = []
            for i in range(len(klines)):
                kline = klines[i].copy()

                # 构建指标字典，根据K线索引判断哪些指标可以计算
                # 不同指标需要的最小历史数据量：
                # MA5/EMA5/ATR7/RSI6: 需要5-7根历史数据
                # MA20/EMA20/RSI9/ATR14: 需要20根历史数据
                # MA60/EMA60/RSI14/ATR21: 需要60根历史数据
                # MA99/EMA99: 需要99根历史数据
                # MACD: 需要26根历史数据
                # KDJ(60,20,5): 需要84根历史数据
                
                indicators = {
                    'ma': {
                        'ma5': float(ma5[i]) if i >= 4 and not np.isnan(ma5[i]) else None,
                        'ma20': float(ma20[i]) if i >= 19 and not np.isnan(ma20[i]) else None,
                        'ma60': float(ma60[i]) if i >= 59 and not np.isnan(ma60[i]) else None,
                        'ma99': float(ma99[i]) if i >= 98 and not np.isnan(ma99[i]) else None
                    },
                    'ema': {
                        'ema5': float(ema5[i]) if i >= 4 and not np.isnan(ema5[i]) else None,
                        'ema20': float(ema20[i]) if i >= 19 and not np.isnan(ema20[i]) else None,
                        'ema30': float(ema30[i]) if i >= 29 and not np.isnan(ema30[i]) else None,
                        'ema60': float(ema60[i]) if i >= 59 and not np.isnan(ema60[i]) else None,
                        'ema99': float(ema99[i]) if i >= 98 and not np.isnan(ema99[i]) else None
                    },
                    'rsi': {
                        'rsi6': float(rsi6[i]) if i >= 6 and not np.isnan(rsi6[i]) else None,
                        'rsi9': float(rsi9[i]) if i >= 9 and not np.isnan(rsi9[i]) else None,
                        'rsi14': float(rsi14[i]) if i >= 14 and not np.isnan(rsi14[i]) else None
                    },
                    'macd': {
                        'dif': float(macd_dif[i]) if i >= 25 and not np.isnan(macd_dif[i]) else None,
                        'dea': float(macd_dea[i]) if i >= 25 and not np.isnan(macd_dea[i]) else None,
                        'bar': float(macd_bar[i]) if i >= 25 and not np.isnan(macd_bar[i]) else None
                    },
                    'kdj': {
                        'k': float(kdj_k[i]) if i >= 82 and not np.isnan(kdj_k[i]) else None,
                        'd': float(kdj_d[i]) if i >= 82 and not np.isnan(kdj_d[i]) else None,
                        'j': float(kdj_j[i]) if i >= 82 and not np.isnan(kdj_j[i]) else None
                    },
                    'atr': {
                        'atr7': float(atr7[i]) if i >= 6 and not np.isnan(atr7[i]) else None,
                        'atr14': float(atr14[i]) if i >= 13 and not np.isnan(atr14[i]) else None,
                        'atr21': float(atr21[i]) if i >= 20 and not np.isnan(atr21[i]) else None
                    },
                    'vol': {
                        'vol': float(volumes[i]),
                        'buy_vol': float(klines[i].get('taker_buy_base_volume', 0)),
                        'sell_vol': float(volumes[i] - klines[i].get('taker_buy_base_volume', 0)),
                        'mavol5': float(mavol5[i]) if i >= 4 and not np.isnan(mavol5[i]) else None,
                        'mavol10': float(mavol10[i]) if i >= 9 and not np.isnan(mavol10[i]) else None,
                        'mavol60': float(mavol60[i]) if i >= 59 and not np.isnan(mavol60[i]) else None
                    }
                }

                kline['indicators'] = indicators
                result_klines.append(kline)

            # 统计有多少K线有完整指标（MA99需要99根历史数据）
            full_indicators_count = max(0, len(klines) - 98) if len(klines) >= 99 else 0
            logger.debug(f'[Indicators] Calculated indicators for {symbol} {interval}: {len(result_klines)} total klines, {full_indicators_count} klines with full indicators (MA99/EMA99)')
            return result_klines

        except Exception as e:
            logger.error(f'[Indicators] Failed to calculate indicators for {symbol} {interval}: {e}', exc_info=True)
            return []

    def _calculate_kdj_tradingview(self, high_array: np.ndarray, low_array: np.ndarray, close_array: np.ndarray,
                                   k_period: int = 60, smooth_k: int = 20, smooth_d: int = 5) -> tuple:
        """
        计算与TradingView一致的KDJ指标

        TradingView的KDJ计算逻辑：
        1. 计算原始%K（RSV）：RSV = 100 * (Close - LowestLow) / (HighestHigh - LowestLow)
        2. 第一次平滑得到K值：使用SMA平滑RSV（周期为smooth_k）
        3. 第二次平滑得到D值：使用SMA平滑K值（周期为smooth_d）
        4. 计算J值：J = 3K - 2D

        Args:
            high_array: 最高价数组
            low_array: 最低价数组
            close_array: 收盘价数组
            k_period: K线周期（默认60）
            smooth_k: K值平滑周期（默认20）
            smooth_d: D值平滑周期（默认5）

        Returns:
            (k_line, d_line, j_line): K值、D值、J值数组
        """
        # 1. 计算原始%K（未平滑的随机值）
        lowest_low = talib.MIN(low_array, timeperiod=k_period)
        highest_high = talib.MAX(high_array, timeperiod=k_period)

        raw_k = np.where(
            highest_high != lowest_low,
            100 * (close_array - lowest_low) / (highest_high - lowest_low),
            50  # 如果最高价=最低价，设为50
        )

        # 2. 第一次平滑得到K值（使用SMA）
        k_line = talib.SMA(raw_k, timeperiod=smooth_k)

        # 3. 第二次平滑得到D值（对K值进行SMA平滑）
        d_line = talib.SMA(k_line, timeperiod=smooth_d)

        # 4. 计算J值
        j_line = 3 * k_line - 2 * d_line

        return k_line, d_line, j_line

    def _calculate_atr_tradingview(self, high_array: np.ndarray, low_array: np.ndarray, close_array: np.ndarray,
                                   period: int = 14) -> np.ndarray:
        """
        使用TradingView的计算逻辑计算ATR（使用Wilder's Smoothing/RMA）
        
        完全按照前端JavaScript代码的实现方式计算，确保结果一致。

        前端计算逻辑（frontend/KLineChart/indicators/atr.ts）：
        1. 对于每一根K线（从索引0开始）：
           - 获取前一根K线的收盘价：prevClose = i > 0 ? dataList[i - 1].close : kLineData.close
           - 计算真实波幅（TR）：TR = max(high - low, |high - prevClose|, |low - prevClose|)
           - 将TR添加到数组中
        2. 当索引 i >= period - 1 时计算ATR：
           - 如果 i === period - 1：第一个ATR值 = 前period个TR的简单平均（SMA）
           - 否则：使用Wilder's Smoothing：RMA = (PrevRMA * (period - 1) + CurrentTR) / period

        Args:
            high_array: 最高价数组
            low_array: 最低价数组
            close_array: 收盘价数组
            period: ATR周期（默认14）

        Returns:
            ATR值数组（与输入数组长度相同，前period-1个值为NaN）
        """
        if len(close_array) < period:
            return np.full(len(close_array), np.nan)

        # 初始化结果数组
        atr = np.full(len(close_array), np.nan)
        
        # 存储TR值数组（用于计算第一个ATR值）
        tr_array = []
        
        # 存储当前RMA值（用于Wilder's Smoothing）
        rma_value = None

        # 遍历每一根K线，完全按照前端逻辑计算
        for i in range(len(close_array)):
            # 获取前一根K线的收盘价（与前端逻辑完全一致）
            # 第一根K线（i=0）时，prevClose就是它自己的close
            prev_close = close_array[i - 1] if i > 0 else close_array[i]
            
            # 计算真实波幅TR（与前端逻辑完全一致）
            tr1 = high_array[i] - low_array[i]  # 当日最高价 - 当日最低价
            tr2 = abs(high_array[i] - prev_close)  # |当日最高价 - 前日收盘价|
            tr3 = abs(low_array[i] - prev_close)   # |当日最低价 - 前日收盘价|
            tr = max(tr1, tr2, tr3)  # TR = max(三者)
            
            # 将TR添加到数组（与前端逻辑一致）
            tr_array.append(tr)
            
            # 如果数据足够，计算ATR（使用RMA/Wilder's Smoothing）
            if i >= period - 1:
                if i == period - 1:
                    # 第一个值：使用SMA计算初始RMA（与前端逻辑完全一致）
                    # 使用前period个TR值（索引0到period-1）
                    tr_sum = sum(tr_array[:period])
                    rma_value = tr_sum / period
                    atr[i] = rma_value
                else:
                    # 后续值：使用Wilder's Smoothing（与前端逻辑完全一致）
                    # RMA = (PrevRMA * (period - 1) + CurrentTR) / period
                    rma_value = (rma_value * (period - 1) + tr) / period
                    atr[i] = rma_value

        return atr

    # ============ 市场数据获取方法 ============
    
    def _get_market_data_by_interval(self, symbol: str, interval: str, limit: int, return_count: int) -> Dict:
        """
        通用方法：获取指定交易对和时间周期的K线数据（预计算所有技术指标）

        改造说明：
        - 获取500根K线，计算最后400根K线的技术指标（因为最大指标周期需要99根历史数据）
        - 每根K线包含完整的技术指标数据（MA, EMA, RSI, MACD, KDJ, ATR, VOL）
        - 使用TA-Lib库计算，保持与TradingView计算逻辑一致
        - 策略代码可直接从K线数据中读取指标，无需再自行计算

        Args:
            symbol: 交易对符号（如 'BTC' 或 'BTCUSDT'）
            interval: 时间周期（如 '1m', '5m', '1h', '4h', '1d', '1w'）
            limit: 获取的K线数量（建议500，用于计算指标）
            return_count: 返回的K线数量（建议400，确保所有K线都有完整指标）

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
            # 获取K线数据（获取足够多的数据用于指标计算）
            # 为了计算400根K线的指标，需要获取500根（最大指标周期MA99需要99根历史数据）
            fetch_limit = max(limit, 500)  # 至少获取500根
            all_klines = self._futures_client.get_klines(
                symbol_key,
                interval,
                limit=fetch_limit
            )

            if not all_klines or len(all_klines) == 0:
                logger.debug(f'[MarketData] No klines data for {symbol} {interval}')
                return {}

            # 先提取所有K线的OHLCV数据用于计算指标
            all_klines_parsed = []
            for item in all_klines:
                try:
                    if isinstance(item, dict):
                        open_time_ms = int(item.get('open_time', 0))
                        open_price = float(item.get('open', 0))
                        high_price = float(item.get('high', 0))
                        low_price = float(item.get('low', 0))
                        close_price = float(item.get('close', 0))
                        volume_value = float(item.get('volume', 0))
                        open_time_dt_str = item.get('open_time_dt_str')
                        close_time_dt_str = item.get('close_time_dt_str')
                        close_time_ms = item.get('close_time')
                        taker_buy_base_volume = float(item.get('taker_buy_base_volume', 0))
                    elif isinstance(item, (list, tuple)) and len(item) > 5:
                        open_time_ms = int(item[0])
                        open_price = float(item[1])
                        high_price = float(item[2])
                        low_price = float(item[3])
                        close_price = float(item[4])
                        volume_value = float(item[5])
                        close_time_ms = int(item[6]) if len(item) > 6 else None
                        taker_buy_base_volume = float(item[9]) if len(item) > 9 else 0
                        open_time_dt_str = None
                        close_time_dt_str = None
                    else:
                        continue

                    # 转换时间戳为字符串（如果需要）
                    if open_time_dt_str is None and open_time_ms:
                        utc8 = timezone(timedelta(hours=8))
                        dt = datetime.fromtimestamp(open_time_ms / 1000.0, tz=utc8)
                        open_time_dt_str = dt.strftime('%Y-%m-%d %H:%M:%S')

                    if close_time_dt_str is None and close_time_ms:
                        utc8 = timezone(timedelta(hours=8))
                        dt = datetime.fromtimestamp(close_time_ms / 1000.0, tz=utc8)
                        close_time_dt_str = dt.strftime('%Y-%m-%d %H:%M:%S')

                    all_klines_parsed.append({
                        'open_time': open_time_ms,
                        'open_time_dt_str': open_time_dt_str,
                        'close_time': close_time_ms,
                        'close_time_dt_str': close_time_dt_str,
                        'open': open_price,
                        'high': high_price,
                        'low': low_price,
                        'close': close_price,
                        'volume': volume_value,
                        'taker_buy_base_volume': taker_buy_base_volume
                    })
                except (ValueError, TypeError, KeyError, IndexError):
                    continue

            # 如果K线不足100根，记录警告但继续处理（能算多少算多少）
            if len(all_klines_parsed) < 100:
                logger.debug(f'[MarketData] Insufficient klines for {symbol} {interval}: {len(all_klines_parsed)} < 100, will calculate partial indicators')

            # 计算所有K线的技术指标（即使不足100根也会返回所有K线，部分指标为空）
            klines_with_indicators = self._calculate_indicators_for_klines(all_klines_parsed, symbol, interval)

            # 确保返回return_count数量的K线（如果不足则返回所有可用的K线）
            # 即使某些指标为空，也要返回指定数量的K线
            if len(klines_with_indicators) == 0:
                logger.warning(f'[MarketData] No klines with indicators for {symbol} {interval}')
                return {}
            
            # 返回最后return_count根K线（如果不足则返回所有）
            actual_return_count = min(return_count, len(klines_with_indicators))
            klines = klines_with_indicators[-actual_return_count:] if len(klines_with_indicators) > actual_return_count else klines_with_indicators
            
            logger.debug(f'[MarketData] Returning {len(klines)} klines for {symbol} {interval} (requested: {return_count}, available: {len(klines_with_indicators)})')

            # 构建K线数据列表（已包含指标数据）
            kline_data_list = []

            for kline in klines:
                try:
                    open_time_ms = kline['open_time']
                    open_time_dt_str = kline['open_time_dt_str']
                    close_time_ms = kline.get('close_time')
                    close_time_dt_str = kline.get('close_time_dt_str')

                    # 将毫秒时间戳转换为 datetime 字符串（精确到秒后两位小数）
                    dt = datetime.fromtimestamp(open_time_ms / 1000.0, tz=timezone.utc)
                    milliseconds = open_time_ms % 1000
                    time_str = dt.strftime('%Y-%m-%d %H:%M:%S') + f'.{milliseconds // 10:02d}'

                    # 构建K线数据（包含所有字段和指标）
                    kline_data = {
                        'time': time_str,
                        'open': kline['open'],
                        'high': kline['high'],
                        'low': kline['low'],
                        'close': kline['close'],
                        'volume': kline['volume'],
                        'open_time': open_time_ms,
                        'open_time_dt_str': open_time_dt_str,
                        'indicators': kline.get('indicators', {})  # 包含所有预计算的指标
                    }

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
                    'source': 'Binance Futures',
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

    def get_market_data_1w(self, symbol: str) -> Dict:
        """
        获取1周时间周期的市场数据（包含预计算的技术指标）

        Args:
            symbol: 交易对符号（如 'BTC'）

        Returns:
            市场数据字典，包含symbol、timeframe、klines（每根K线含indicators字段）和metadata字段
        """
        return self._get_market_data_by_interval(symbol, '1w', limit=200, return_count=100)


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