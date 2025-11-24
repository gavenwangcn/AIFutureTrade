import logging
import threading
import time
from typing import Callable, Dict, List, Optional

BINANCE_SDK_AVAILABLE = True
_BINANCE_IMPORT_ERROR: Optional[ImportError] = None

try:  # pragma: no cover - external dependency optional in many envs
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
except ImportError as exc:  # pragma: no cover - handled at runtime
    BINANCE_SDK_AVAILABLE = False
    _BINANCE_IMPORT_ERROR = exc
    ConfigurationRestAPI = None  # type: ignore[assignment]
    DerivativesTradingUsdsFutures = None  # type: ignore[assignment]
    KlineCandlestickDataIntervalEnum = None  # type: ignore[assignment]
    SymbolPriceTickerResponse = None  # type: ignore[assignment]
    Ticker24hrPriceChangeStatisticsResponse = None  # type: ignore[assignment]
    DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL = None  # type: ignore[assignment]
    DERIVATIVES_TRADING_USDS_FUTURES_REST_API_TESTNET_URL = None  # type: ignore[assignment]


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
        if not BINANCE_SDK_AVAILABLE:
            raise RuntimeError(
                "Binance official futures SDK not available. Install 'binance-common' "
                "and related packages or set BINANCE_API_KEY/SECRET empty to disable."
            ) from _BINANCE_IMPORT_ERROR

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

    def get_24h_ticker(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        获取指定交易对的24小时价格变动统计
        
        Args:
            symbols: 交易对符号列表，如 ['BTCUSDT', 'ETHUSDT']
            
        Returns:
            字典，key为交易对符号，value为24小时统计数据
        """
        logger.info(f"[Binance Futures] ========== 开始获取24小时价格变动统计 ==========")
        logger.info(f"[Binance Futures] 请求交易对数量: {len(symbols)}")
        if symbols:
            logger.info(f"[Binance Futures] 请求交易对列表: {symbols[:10]}{'...' if len(symbols) > 10 else ''}")
        
        result: Dict[str, Dict] = {}
        if not symbols:
            logger.info(f"[Binance Futures] 交易对列表为空，直接返回")
            return result
        
        try:
            # 调用币安API获取24小时统计数据
            logger.info(f"[Binance Futures] [步骤1] 调用币安API: ticker24hr_price_change_statistics()")
            api_start_time = time.time()
            
            response = self._rest.ticker24hr_price_change_statistics()
            all_stats: List[Ticker24hrPriceChangeStatisticsResponse] = response.data()
            
            api_duration = time.time() - api_start_time
            logger.info(f"[Binance Futures] [步骤1] API调用完成, 耗时: {api_duration:.3f} 秒, 返回数据总数: {len(all_stats)}")
            
            # 过滤出请求的交易对
            logger.info(f"[Binance Futures] [步骤2] 过滤匹配的交易对...")
            for stat in all_stats:
                if stat.symbol in symbols:
                    result[stat.symbol] = stat.model_dump()
            
            logger.info(f"[Binance Futures] [步骤2] 过滤完成, 匹配到 {len(result)}/{len(symbols)} 个交易对")
            
            # 记录匹配到的交易对详情
            if result:
                logger.info(f"[Binance Futures] [步骤3] 匹配到的交易对详情:")
                for idx, (symbol, data) in enumerate(list(result.items())[:5]):  # 只记录前5个
                    price = data.get('lastPrice', 0)
                    change_pct = data.get('priceChangePercent', 0)
                    volume = data.get('quoteVolume', 0)
                    logger.info(f"[Binance Futures] [步骤3.{idx+1}] {symbol}: "
                               f"价格=${float(price):.4f}, "
                               f"涨跌幅={float(change_pct):.2f}%, "
                               f"24h成交量=${float(volume):.2f}")
                if len(result) > 5:
                    logger.info(f"[Binance Futures] [步骤3] ... 还有 {len(result) - 5} 个交易对未显示")
            
            # 检查是否有未匹配的交易对
            missing = set(symbols) - set(result.keys())
            if missing:
                logger.warning(f"[Binance Futures] [步骤3] 未匹配到的交易对 ({len(missing)} 个): {list(missing)[:10]}{'...' if len(missing) > 10 else ''}")
            
            logger.info(f"[Binance Futures] ========== 24小时价格变动统计获取完成 ==========")
            
        except Exception as exc:
            logger.error(f"[Binance Futures] ========== 获取24小时价格变动统计失败 ==========")
            logger.error(f"[Binance Futures] 错误信息: {exc}")
            import traceback
            logger.error(f"[Binance Futures] 错误堆栈:\n{traceback.format_exc()}")
        
        return result

    def get_top_gainers(self, limit: int = 10) -> List[Dict]:
        """
        获取涨跌幅榜前N名的合约信息（按涨跌幅降序排列）
        
        Args:
            limit: 返回前N名，默认10
            
        Returns:
            涨跌幅榜列表，每个元素包含合约的24小时统计数据
        """
        logger.info(f"[Binance Futures] ========== 开始获取涨跌幅榜 ==========")
        logger.info(f"[Binance Futures] 请求参数: limit={limit}, quote_asset={self.quote_asset}")
        
        try:
            # 调用币安API获取24小时统计数据
            logger.info(f"[Binance Futures] [步骤1] 调用币安API: ticker24hr_price_change_statistics()")
            api_start_time = time.time()
            
            response = self._rest.ticker24hr_price_change_statistics()
            all_stats: List[Ticker24hrPriceChangeStatisticsResponse] = response.data()
            
            api_duration = time.time() - api_start_time
            logger.info(f"[Binance Futures] [步骤1] API调用完成, 耗时: {api_duration:.3f} 秒, 返回数据总数: {len(all_stats)}")
            
            # 转换为字典列表
            logger.info(f"[Binance Futures] [步骤2] 转换数据格式...")
            data = [stat.model_dump() for stat in all_stats]
            logger.info(f"[Binance Futures] [步骤2] 数据转换完成, 总交易对数: {len(data)}")
            
            # 过滤出指定计价资产的交易对
            logger.info(f"[Binance Futures] [步骤3] 过滤 {self.quote_asset} 计价资产...")
            filtered = [
                item for item in data if item.get("symbol", "").endswith(self.quote_asset)
            ]
            logger.info(f"[Binance Futures] [步骤3] 过滤完成, {self.quote_asset} 计价资产数量: {len(filtered)}")
            
            # 按涨跌幅降序排序
            logger.info(f"[Binance Futures] [步骤4] 按涨跌幅降序排序...")
            filtered.sort(key=lambda x: float(x.get("priceChangePercent", 0)), reverse=True)
            logger.info(f"[Binance Futures] [步骤4] 排序完成")
            
            # 取前N名
            result = filtered[:limit]
            logger.info(f"[Binance Futures] [步骤5] 取前 {limit} 名, 实际返回: {len(result)} 条")
            
            # 记录涨跌幅榜详情
            if result:
                logger.info(f"[Binance Futures] [步骤6] 涨跌幅榜详情:")
                for idx, item in enumerate(result):
                    symbol = item.get("symbol", "N/A")
                    price = item.get("lastPrice", 0)
                    change_pct = item.get("priceChangePercent", 0)
                    volume = item.get("quoteVolume", 0)
                    high = item.get("highPrice", 0)
                    low = item.get("lowPrice", 0)
                    logger.info(f"[Binance Futures] [步骤6.{idx+1}] 排名 #{idx+1}: {symbol} | "
                               f"价格=${float(price):.4f} | "
                               f"涨跌幅={float(change_pct):.2f}% | "
                               f"24h最高=${float(high):.4f} | "
                               f"24h最低=${float(low):.4f} | "
                               f"24h成交量=${float(volume):.2f}")
            
            logger.info(f"[Binance Futures] ========== 涨跌幅榜获取完成 ==========")
            return result
            
        except Exception as exc:
            logger.error(f"[Binance Futures] ========== 获取涨跌幅榜失败 ==========")
            logger.error(f"[Binance Futures] 错误信息: {exc}")
            import traceback
            logger.error(f"[Binance Futures] 错误堆栈:\n{traceback.format_exc()}")
            return []

    def get_all_tickers(self) -> List[Dict]:
        """
        返回所有交易对的24小时价格变动统计
        
        Returns:
            所有交易对的24小时统计数据列表
        """
        logger.info(f"[Binance Futures] ========== 开始获取所有交易对24小时统计 ==========")
        
        try:
            # 调用币安API获取24小时统计数据
            logger.info(f"[Binance Futures] [步骤1] 调用币安API: ticker24hr_price_change_statistics()")
            api_start_time = time.time()
            
            response = self._rest.ticker24hr_price_change_statistics()
            all_stats: List[Ticker24hrPriceChangeStatisticsResponse] = response.data()
            
            api_duration = time.time() - api_start_time
            logger.info(f"[Binance Futures] [步骤1] API调用完成, 耗时: {api_duration:.3f} 秒, 返回数据总数: {len(all_stats)}")
            
            # 转换为字典列表
            logger.info(f"[Binance Futures] [步骤2] 转换数据格式...")
            result = [stat.model_dump() for stat in all_stats]
            logger.info(f"[Binance Futures] [步骤2] 数据转换完成, 总交易对数: {len(result)}")
            
            # 统计信息
            if result:
                usdt_pairs = [item for item in result if item.get("symbol", "").endswith("USDT")]
                logger.info(f"[Binance Futures] [步骤3] 数据统计: USDT交易对数量: {len(usdt_pairs)}/{len(result)}")
            
            logger.info(f"[Binance Futures] ========== 所有交易对24小时统计获取完成 ==========")
            return result
            
        except Exception as exc:
            logger.error(f"[Binance Futures] ========== 获取所有交易对24小时统计失败 ==========")
            logger.error(f"[Binance Futures] 错误信息: {exc}")
            import traceback
            logger.error(f"[Binance Futures] 错误堆栈:\n{traceback.format_exc()}")
            return []

    def get_symbol_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        获取指定交易对的实时价格
        
        Args:
            symbols: 交易对符号列表，如 ['BTCUSDT', 'ETHUSDT']
            
        Returns:
            字典，key为交易对符号，value为实时价格数据
        """
        logger.info(f"[Binance Futures] ========== 开始获取实时价格 ==========")
        logger.info(f"[Binance Futures] 请求交易对数量: {len(symbols)}")
        if symbols:
            logger.info(f"[Binance Futures] 请求交易对列表: {symbols[:10]}{'...' if len(symbols) > 10 else ''}")
        
        payload: Dict[str, Dict] = {}
        if not symbols:
            logger.info(f"[Binance Futures] 交易对列表为空，直接返回")
            return payload
        
        try:
            # 调用币安API获取实时价格
            logger.info(f"[Binance Futures] [步骤1] 调用币安API: symbol_price_ticker()")
            api_start_time = time.time()
            
            response = self._rest.symbol_price_ticker()
            data: List[SymbolPriceTickerResponse] = response.data()
            
            api_duration = time.time() - api_start_time
            logger.info(f"[Binance Futures] [步骤1] API调用完成, 耗时: {api_duration:.3f} 秒, 返回数据总数: {len(data)}")
            
            # 过滤出请求的交易对
            logger.info(f"[Binance Futures] [步骤2] 过滤匹配的交易对...")
            for item in data:
                if item.symbol in symbols:
                    payload[item.symbol] = item.model_dump()
            
            logger.info(f"[Binance Futures] [步骤2] 过滤完成, 匹配到 {len(payload)}/{len(symbols)} 个交易对")
            
            # 记录匹配到的交易对实时价格详情
            if payload:
                logger.info(f"[Binance Futures] [步骤3] 实时价格详情:")
                for idx, (symbol, price_data) in enumerate(list(payload.items())[:10]):  # 记录前10个
                    price = price_data.get('price', 0)
                    logger.info(f"[Binance Futures] [步骤3.{idx+1}] {symbol}: 实时价格=${float(price):.4f}")
                if len(payload) > 10:
                    logger.info(f"[Binance Futures] [步骤3] ... 还有 {len(payload) - 10} 个交易对未显示")
            
            # 检查是否有未匹配的交易对
            missing = set(symbols) - set(payload.keys())
            if missing:
                logger.warning(f"[Binance Futures] [步骤3] 未匹配到的交易对 ({len(missing)} 个): {list(missing)[:10]}{'...' if len(missing) > 10 else ''}")
            
            logger.info(f"[Binance Futures] ========== 实时价格获取完成 ==========")
            
        except Exception as exc:
            logger.error(f"[Binance Futures] ========== 获取实时价格失败 ==========")
            logger.error(f"[Binance Futures] 错误信息: {exc}")
            import traceback
            logger.error(f"[Binance Futures] 错误堆栈:\n{traceback.format_exc()}")
        
        return payload

    def get_klines(self, symbol: str, interval: str, limit: int = 120) -> List[List]:
        """
        获取K线数据
        
        Args:
            symbol: 交易对符号，如 'BTCUSDT'
            interval: K线间隔，如 '1m', '5m', '1h', '1d' 等
            limit: 返回的K线数量，默认120
            
        Returns:
            K线数据列表，每个元素为 [open_time, open, high, low, close, volume]
        """
        logger.info(f"[Binance Futures] ========== 开始获取K线数据 ==========")
        logger.info(f"[Binance Futures] 请求参数: symbol={symbol}, interval={interval}, limit={limit}")
        
        try:
            # 转换间隔枚举
            logger.info(f"[Binance Futures] [步骤1] 转换K线间隔枚举...")
            interval_enum = KlineCandlestickDataIntervalEnum(interval)
            logger.info(f"[Binance Futures] [步骤1] 间隔枚举转换完成: {interval}")
            
            # 调用币安API获取K线数据
            logger.info(f"[Binance Futures] [步骤2] 调用币安API: kline_candlestick_data()")
            api_start_time = time.time()
            
            response = self._rest.kline_candlestick_data(
                symbol=symbol,
                interval=interval_enum,
                limit=limit,
            )
            data = response.data()
            
            api_duration = time.time() - api_start_time
            logger.info(f"[Binance Futures] [步骤2] API调用完成, 耗时: {api_duration:.3f} 秒, 返回K线数量: {len(data)}")
            
            # 将K线数据转换为列表格式
            logger.info(f"[Binance Futures] [步骤3] 转换K线数据格式...")
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
            logger.info(f"[Binance Futures] [步骤3] 数据格式转换完成, 返回K线数量: {len(klines)}")
            
            # 记录K线数据统计信息
            if klines:
                first_kline = klines[0]
                last_kline = klines[-1]
                logger.info(f"[Binance Futures] [步骤4] K线数据统计:")
                logger.info(f"[Binance Futures] [步骤4.1] 第一条K线: 时间={first_kline[0]}, "
                           f"开盘=${float(first_kline[1]):.4f}, "
                           f"最高=${float(first_kline[2]):.4f}, "
                           f"最低=${float(first_kline[3]):.4f}, "
                           f"收盘=${float(first_kline[4]):.4f}, "
                           f"成交量={float(first_kline[5]):.2f}")
                logger.info(f"[Binance Futures] [步骤4.2] 最后一条K线: 时间={last_kline[0]}, "
                           f"开盘=${float(last_kline[1]):.4f}, "
                           f"最高=${float(last_kline[2]):.4f}, "
                           f"最低=${float(last_kline[3]):.4f}, "
                           f"收盘=${float(last_kline[4]):.4f}, "
                           f"成交量={float(last_kline[5]):.2f}")
                
                # 计算价格范围
                all_highs = [float(k[2]) for k in klines]
                all_lows = [float(k[3]) for k in klines]
                max_high = max(all_highs)
                min_low = min(all_lows)
                price_range = max_high - min_low
                price_range_pct = (price_range / min_low) * 100 if min_low > 0 else 0
                logger.info(f"[Binance Futures] [步骤4.3] 价格范围: 最高=${max_high:.4f}, "
                           f"最低=${min_low:.4f}, "
                           f"波动范围=${price_range:.4f} ({price_range_pct:.2f}%)")
            
            logger.info(f"[Binance Futures] ========== K线数据获取完成 ==========")
            return klines
            
        except Exception as exc:
            logger.error(f"[Binance Futures] ========== 获取K线数据失败 ==========")
            logger.error(f"[Binance Futures] 错误信息: {exc}")
            logger.error(f"[Binance Futures] 请求参数: symbol={symbol}, interval={interval}, limit={limit}")
            import traceback
            logger.error(f"[Binance Futures] 错误堆栈:\n{traceback.format_exc()}")
            return []

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
