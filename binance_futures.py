import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

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

    @staticmethod
    def _normalize_list(payload: Any) -> List[Any]:
        """Handle SDK responses that may wrap lists inside data/items attributes."""
        if payload is None:
            return []
        if isinstance(payload, list):
            return payload

        for attr in ("data", "items", "list", "records"):
            attr_value = getattr(payload, attr, None)
            if callable(attr_value):
                try:
                    attr_value = attr_value()
                except TypeError:
                    attr_value = getattr(payload, attr, None)
            if isinstance(attr_value, list):
                return attr_value

        if hasattr(payload, "model_dump"):
            try:
                dumped = payload.model_dump()
            except Exception:  # pragma: no cover - defensive
                dumped = None
            if isinstance(dumped, dict):
                for key in ("data", "items", "list", "records"):
                    value = dumped.get(key)
                    if isinstance(value, list):
                        return value

        return [payload]

    @staticmethod
    def _ensure_dict(item: Any) -> Dict[str, Any]:
        """Convert SDK model/objects into plain dictionaries for downstream use."""
        if isinstance(item, dict):
            return item

        if hasattr(item, "model_dump"):
            try:
                dumped = item.model_dump()
            except Exception:  # pragma: no cover - defensive against SDK quirks
                dumped = None
            if isinstance(dumped, dict):
                return dumped

        if hasattr(item, "dict"):
            try:
                dumped = item.dict()
            except Exception:
                dumped = None
            if isinstance(dumped, dict):
                return dumped

        if hasattr(item, "__dict__"):
            data = {
                key: value for key, value in vars(item).items() if not key.startswith("_")
            }
            if data:
                return data

        return {}

    @staticmethod
    def _to_dict(payload: Any) -> Optional[Dict[str, Any]]:
        """Best-effort conversion of SDK models to plain dicts."""
        if payload is None:
            return None
        if isinstance(payload, dict):
            return payload
        if hasattr(payload, "model_dump"):
            try:
                dumped = payload.model_dump()
            except Exception:  # pragma: no cover - defensive
                return None
            if isinstance(dumped, dict):
                return dumped
        return None

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
            all_stats: List[Ticker24hrPriceChangeStatisticsResponse] = self._normalize_list(response.data())
            
            api_duration = time.time() - api_start_time
            logger.info(f"[Binance Futures] [步骤1] API调用完成, 耗时: {api_duration:.3f} 秒, 返回数据总数: {len(all_stats)}")
            
            # 过滤出请求的交易对
            logger.info(f"[Binance Futures] [步骤2] 过滤匹配的交易对...")
            for stat in all_stats:
                stat_dict = self._to_dict(stat)
                if not stat_dict:
                    continue
                symbol = stat_dict.get("symbol")
                if symbol in symbols:
                    result[symbol] = stat_dict
            
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
            # Step 1 —— 调用API并记录耗时
            logger.info(f"[Binance Futures] [步骤1] 调用币安API: ticker24hr_price_change_statistics()")
            api_start_time = time.time()
            response = self._rest.ticker24hr_price_change_statistics()
            data_obj = response.data()

            # Step 2 —— 通过一个简单队列把任意嵌套结构摊平为 dict 列表
            raw_items: List[Dict[str, Any]] = []
            queue: List[Any] = [data_obj]
            while queue:
                current = queue.pop(0)
                if current is None:
                    continue

                if isinstance(current, list):
                    queue.extend(current)
                    continue

                if hasattr(current, "to_dict"):
                    try:
                        queue.append(current.to_dict())
                    except Exception:
                        logger.debug("[Binance Futures] to_dict() 调用失败, 跳过当前项")
                    continue

                if isinstance(current, dict):
                    nested = next((current.get(key) for key in ("data", "items", "list", "records")
                                    if isinstance(current.get(key), list)), None)
                    if nested is not None:
                        queue.extend(nested)
                        continue
                    normalized = self._ensure_dict(current)
                    if normalized:
                        raw_items.append(normalized)
                    continue

                normalized = self._ensure_dict(current)
                if normalized:
                    raw_items.append(normalized)

            api_duration = time.time() - api_start_time
            logger.info(
                f"[Binance Futures] [步骤1] API调用完成, 耗时: {api_duration:.3f} 秒, 返回数据总数: {len(raw_items)}"
            )

            def _safe_float(value: Any, default: float = 0.0) -> float:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return default

            # Step 3 —— 过滤指定计价资产并求出涨跌幅
            logger.info(f"[Binance Futures] [步骤2] 过滤 {self.quote_asset} 计价资产...")
            filtered: List[tuple[Dict[str, Any], float]] = []
            skipped_no_symbol = 0
            skipped_quote_asset = 0
            for stat in raw_items:
                symbol = stat.get("symbol") or stat.get("s")
                if not symbol:
                    skipped_no_symbol += 1
                    continue
                contract_symbol = str(symbol).upper()
                if not contract_symbol.endswith(self.quote_asset):
                    skipped_quote_asset += 1
                    continue

                change_raw = (
                    stat.get("price_change_percent")
                    or stat.get("priceChangePercent")
                    or stat.get("P")
                )
                change_percent = _safe_float(change_raw)
                filtered.append((stat, change_percent))

            logger.info(
                f"[Binance Futures] [步骤2] 过滤完成, {self.quote_asset} 计价资产数量: {len(filtered)} | "
                f"跳过无symbol={skipped_no_symbol} | 跳过不同计价资产={skipped_quote_asset}"
            )

            if not filtered:
                logger.warning("[Binance Futures] [步骤2] 未找到任何符合条件的 {self.quote_asset} 交易对")
                return []

            # Step 4 —— 排序并限制数量
            logger.info(f"[Binance Futures] [步骤3] 按涨跌幅降序排序...")
            filtered.sort(key=lambda x: x[1], reverse=True)
            logger.info(f"[Binance Futures] [步骤3] 排序完成")

            selected = filtered[: max(0, limit)]
            result_payload: List[Dict[str, Any]] = []
            for stat, change_percent in selected:
                payload = dict(stat)
                payload.setdefault("priceChangePercent", change_percent)
                payload.setdefault("price_change_percent", change_percent)
                payload.setdefault("lastPrice", payload.get("last_price") or payload.get("close"))
                payload.setdefault("quoteVolume", payload.get("quote_volume") or payload.get("volume"))
                payload.setdefault("highPrice", payload.get("high_price"))
                payload.setdefault("lowPrice", payload.get("low_price"))
                result_payload.append(payload)

            logger.info(f"[Binance Futures] [步骤4] 取前 {limit} 名, 实际返回: {len(result_payload)} 条")

            # Step 5 —— 输出结果详情
            if result_payload:
                logger.info(f"[Binance Futures] [步骤5] 涨跌幅榜详情:")
                for idx, item in enumerate(result_payload):
                    symbol = item.get("symbol", "N/A")
                    price = item.get("lastPrice") or item.get("last_price")
                    change_pct = item.get("price_change_percent") or item.get("priceChangePercent")
                    volume = item.get("quoteVolume") or item.get("quote_volume")
                    high = item.get("highPrice") or item.get("high_price")
                    low = item.get("lowPrice") or item.get("low_price")
                    logger.info(
                        f"[Binance Futures] [步骤5.{idx+1}] #{idx+1}: {symbol} | "
                        f"价格=${_safe_float(price):.4f} | "
                        f"涨跌幅={_safe_float(change_pct):.2f}% | "
                        f"24h最高=${_safe_float(high):.4f} | "
                        f"24h最低=${_safe_float(low):.4f} | "
                        f"24h成交量=${_safe_float(volume):.2f}"
                    )

            logger.info(f"[Binance Futures] ========== 涨跌幅榜获取完成 ==========")
            return result_payload

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
            data: List[SymbolPriceTickerResponse] = self._normalize_list(response.data())
            
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
            data = self._normalize_list(response.data())
            
            api_duration = time.time() - api_start_time
            logger.info(f"[Binance Futures] [步骤2] API调用完成, 耗时: {api_duration:.3f} 秒, 返回K线数量: {len(data)}")
            
            # 将K线数据转换为列表格式
            logger.info(f"[Binance Futures] [步骤3] 转换K线数据格式...")
            klines: List[List[Any]] = []
            for item in data:
                if isinstance(item, (list, tuple)):
                    if len(item) >= 6:
                        klines.append(list(item[:6]))
                    else:
                        logger.debug("[Binance Futures] [KLines] 忽略长度不足的数据项: %s", item)
                    continue

                entry = self._to_dict(item)
                if entry:
                    klines.append(
                        [
                            entry.get("open_time"),
                            entry.get("open"),
                            entry.get("high"),
                            entry.get("low"),
                            entry.get("close"),
                            entry.get("volume"),
                        ]
                    )
                else:
                    # 尝试直接读取属性，兼容 SDK 模型
                    try:
                        klines.append(
                            [
                                getattr(item, "open_time"),
                                getattr(item, "open"),
                                getattr(item, "high"),
                                getattr(item, "low"),
                                getattr(item, "close"),
                                getattr(item, "volume"),
                            ]
                        )
                    except AttributeError:
                        logger.debug("[Binance Futures] [KLines] 无法解析的数据项: %s", item)
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
