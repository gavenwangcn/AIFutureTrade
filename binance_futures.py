"""
币安期货客户端 - 封装币安官方衍生品SDK的高级接口

提供简洁易用的接口来获取币安USDS-M期货合约的市场数据，包括：
- 24小时价格变动统计
- 实时价格查询
- K线数据获取
- 涨跌幅榜查询
"""
import logging
import time
from typing import Any, Callable, Dict, List, Optional

# ============ SDK导入和可用性检查 ============

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
    )
except ImportError as exc:  # pragma: no cover - handled at runtime
    BINANCE_SDK_AVAILABLE = False
    _BINANCE_IMPORT_ERROR = exc
    ConfigurationRestAPI = None  # type: ignore[assignment]
    DerivativesTradingUsdsFutures = None  # type: ignore[assignment]
    KlineCandlestickDataIntervalEnum = None  # type: ignore[assignment]
    DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL = None  # type: ignore[assignment]
    DERIVATIVES_TRADING_USDS_FUTURES_REST_API_TESTNET_URL = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


class BinanceFuturesClient:
    """
    币安期货客户端 - 封装币安官方衍生品SDK的高级接口
    
    提供简洁易用的方法来获取市场数据，自动处理SDK响应格式转换。
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        quote_asset: str = "USDT",
        base_path: Optional[str] = None,
        testnet: bool = False,
    ):
        """
        初始化币安期货客户端
        
        Args:
            api_key: 币安API密钥
            api_secret: 币安API密钥
            quote_asset: 计价资产，默认为USDT
            base_path: 自定义REST API基础路径（可选）
            testnet: 是否使用测试网络，默认False
        """
        if not BINANCE_SDK_AVAILABLE:
            raise RuntimeError(
                "Binance official futures SDK not available. Install 'binance-common' "
                "and related packages or set BINANCE_API_KEY/SECRET empty to disable."
            ) from _BINANCE_IMPORT_ERROR

        # 确定REST API基础路径
        rest_base = base_path or (
            DERIVATIVES_TRADING_USDS_FUTURES_REST_API_TESTNET_URL
            if testnet
            else DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL
        )

        # 创建SDK配置和客户端
        configuration = ConfigurationRestAPI(
            api_key=api_key,
            api_secret=api_secret,
            base_path=rest_base,
        )

        self.quote_asset = quote_asset.upper()
        self._client = DerivativesTradingUsdsFutures(config_rest_api=configuration)
        self._rest = self._client.rest_api

    # ============ 工具方法：数据格式转换 ============

    def format_symbol(self, base_symbol: str) -> str:
        """
        格式化交易对符号，添加计价资产后缀
        
        Args:
            base_symbol: 基础交易对符号，如 'BTC'
            
        Returns:
            完整交易对符号，如 'BTCUSDT'
        """
        return f"{base_symbol.upper()}{self.quote_asset}"

    @staticmethod
    def _normalize_list(payload: Any) -> List[Any]:
        """
        规范化SDK响应为列表格式
        
        SDK响应可能以多种格式返回：
        - 直接是列表
        - 包装在对象的data/items/list/records属性中
        - 是单个对象
        
        Args:
            payload: SDK响应数据
            
        Returns:
            规范化后的列表
        """
        if payload is None:
            return []
        if isinstance(payload, list):
            return payload

        # 尝试从常见属性中提取列表
        for attr in ("data", "items", "list", "records"):
            attr_value = getattr(payload, attr, None)
            if callable(attr_value):
                try:
                    attr_value = attr_value()
                except TypeError:
                    attr_value = getattr(payload, attr, None)
            if isinstance(attr_value, list):
                return attr_value

        # 尝试从model_dump中提取
        if hasattr(payload, "model_dump"):
            try:
                dumped = payload.model_dump()
                if isinstance(dumped, dict):
                    for key in ("data", "items", "list", "records"):
                        value = dumped.get(key)
                        if isinstance(value, list):
                            return value
            except Exception:  # pragma: no cover - defensive
                pass

        # 如果都不是，包装为列表
        return [payload]

    @staticmethod
    def _ensure_dict(item: Any) -> Dict[str, Any]:
        """
        将SDK模型对象转换为普通字典
        
        Args:
            item: SDK模型对象或字典
            
        Returns:
            普通字典
        """
        if isinstance(item, dict):
            return item

        # 尝试使用model_dump方法
        if hasattr(item, "model_dump"):
            try:
                dumped = item.model_dump()
                if isinstance(dumped, dict):
                    return dumped
            except Exception:  # pragma: no cover - defensive
                pass

        # 尝试使用dict方法
        if hasattr(item, "dict"):
            try:
                dumped = item.dict()
                if isinstance(dumped, dict):
                    return dumped
            except Exception:
                pass

        # 尝试使用__dict__属性
        if hasattr(item, "__dict__"):
            data = {
                key: value
                for key, value in vars(item).items()
                if not key.startswith("_")
            }
            if data:
                return data

        return {}

    @staticmethod
    def _to_dict(payload: Any) -> Optional[Dict[str, Any]]:
        """
        将SDK响应转换为字典（如果可能）
        
        Args:
            payload: SDK响应数据
            
        Returns:
            字典或None
        """
        if payload is None:
            return None
        if isinstance(payload, dict):
            return payload
        if hasattr(payload, "model_dump"):
            try:
                dumped = payload.model_dump()
                if isinstance(dumped, dict):
                    return dumped
            except Exception:  # pragma: no cover - defensive
                pass
        return None

    def _flatten_to_dicts(self, payload: Any, context: str) -> List[Dict[str, Any]]:
        """
        将SDK响应扁平化为字典列表
        
        递归处理嵌套的列表、字典和模型对象，最终返回字典列表。
        
        Args:
            payload: SDK响应数据
            context: 上下文信息，用于日志记录
            
        Returns:
            字典列表
        """
        flattened: List[Dict[str, Any]] = []
        queue: List[Any] = [payload]

        while queue:
            current = queue.pop(0)
            if current is None:
                continue

            # 如果是列表，展开添加到队列
            if isinstance(current, list):
                queue.extend(current)
                continue

            # 如果是字典，直接添加
            if isinstance(current, dict):
                flattened.append(current)
                continue

            # 尝试使用to_dict方法
            to_dict_method = getattr(current, "to_dict", None)
            if callable(to_dict_method):
                try:
                    queue.append(to_dict_method())
                    continue
                except Exception:
                    logger.debug(
                        "[Binance Futures] %s to_dict() 失败, 尝试 fallback",
                        context,
                        exc_info=True,
                    )

            # 尝试使用model_dump方法
            model_dump_method = getattr(current, "model_dump", None)
            if callable(model_dump_method):
                try:
                    queue.append(model_dump_method())
                    continue
                except Exception:
                    logger.debug(
                        "[Binance Futures] %s model_dump() 失败, 尝试 fallback",
                        context,
                        exc_info=True,
                    )

            # 使用_ensure_dict作为最后手段
            normalized = self._ensure_dict(current)
            if normalized:
                flattened.append(normalized)

        return flattened

    # ============ 市场数据获取方法 ============

    def get_24h_ticker(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        获取指定交易对的24小时价格变动统计
        
        Args:
            symbols: 交易对符号列表，如 ['BTCUSDT', 'ETHUSDT']
            
        Returns:
            字典，key为交易对符号，value为24小时统计数据
        """
        logger.info(f"[Binance Futures] 开始获取24小时价格变动统计，交易对数量: {len(symbols)}")
        
        result: Dict[str, Dict] = {}
        if not symbols:
            return result

        try:
            # 逐个调用API获取每个交易对的数据
            prepared_symbols = [(symbol, symbol.upper()) for symbol in symbols]
            total = len(prepared_symbols)
            fetch_start = time.time()
            success = 0

            for idx, (source_symbol, request_symbol) in enumerate(prepared_symbols, start=1):
                logger.debug(f"[Binance Futures] 获取 {request_symbol} 24小时统计 ({idx}/{total})")
                
                try:
                    call_start = time.time()
                    response = self._rest.ticker24hr_price_change_statistics(symbol=request_symbol)
                    call_duration = time.time() - call_start
                    
                    # 转换响应为字典列表
                    dict_entries = self._flatten_to_dicts(
                        response.data(),
                        "ticker24hr_price_change_statistics",
                    )
                    
                    if not dict_entries:
                        logger.warning(f"[Binance Futures] {request_symbol} 无返回数据，跳过")
                        continue

                    # 匹配正确的交易对数据
                    normalized_symbol = request_symbol.upper()
                    matched_entry = None
                    for item in dict_entries:
                        symbol_value = item.get("symbol") or item.get("s")
                        if symbol_value and str(symbol_value).upper() == normalized_symbol:
                            matched_entry = item
                            break
                    
                    # 如果没找到精确匹配，使用第一条数据
                    if matched_entry is None:
                        matched_entry = dict_entries[0]

                    result[source_symbol] = matched_entry
                    success += 1
                    logger.debug(f"[Binance Futures] {request_symbol} 获取成功, 耗时 {call_duration:.3f} 秒")
                    
                except Exception as symbol_exc:
                    logger.warning(f"[Binance Futures] 获取 {request_symbol} 失败: {symbol_exc}")
                    continue

            total_duration = time.time() - fetch_start
            logger.info(
                f"[Binance Futures] 24小时统计获取完成, 成功 {success}/{total}, 总耗时 {total_duration:.3f} 秒"
            )

            # 记录未匹配的交易对
            missing = set(symbols) - set(result.keys())
            if missing:
                logger.warning(
                    f"[Binance Futures] 未匹配到的交易对 ({len(missing)} 个): {list(missing)[:10]}{'...' if len(missing) > 10 else ''}"
                )

        except Exception as exc:
            logger.error(f"[Binance Futures] 获取24小时价格变动统计失败: {exc}", exc_info=True)

        return result

    def get_top_gainers(self, limit: Optional[int] = None) -> List[Dict]:
        """
        获取所有符合条件的合约涨跌幅数据（已包含 side 标记）
        
        每条返回的数据都会包含 'side' 字段，用于标识是涨幅榜还是跌幅榜：
        - 'gainer': 涨跌幅 >= 0（上涨或持平）
        - 'loser': 涨跌幅 < 0（下跌）
        
        注意：此方法默认返回所有过滤后的数据，以便调用方自行分离涨幅榜和跌幅榜。
        如果传入 limit 参数，则返回涨幅前 limit 名 + 跌幅前 limit 名（各自独立限制）。
        
        Args:
            limit: 可选，如果指定则返回涨幅前N名（用于向后兼容），否则返回所有数据
            
        Returns:
            合约24小时统计数据列表，每个元素包含：
            - 合约的完整信息（价格、成交量等）
            - 'side' 字段：'gainer' 或 'loser'，标识涨跌方向
            - 'priceChangePercent' 字段：涨跌幅百分比
        """
        if limit is not None:
            logger.info(f"[Binance Futures] 开始获取涨跌幅榜, limit={limit}, quote_asset={self.quote_asset}")
        else:
            logger.info(f"[Binance Futures] 开始获取所有涨跌幅数据, quote_asset={self.quote_asset}")

        try:
            # 调用API获取所有交易对的24小时统计
            api_start_time = time.time()
            response = self._rest.ticker24hr_price_change_statistics()
            raw_items = self._flatten_to_dicts(
                response.data(), "ticker24hr_price_change_statistics"
            )
            api_duration = time.time() - api_start_time
            logger.debug(
                f"[Binance Futures] API调用完成, 耗时: {api_duration:.3f} 秒, 返回数据总数: {len(raw_items)}"
            )

            # 辅助函数：安全转换为浮点数
            def _safe_float(value: Any, default: float = 0.0) -> float:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return default

            # 过滤指定计价资产的交易对并提取涨跌幅
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

                # 提取涨跌幅百分比
                change_raw = (
                    stat.get("price_change_percent")
                    or stat.get("priceChangePercent")
                    or stat.get("P")
                )
                change_percent = _safe_float(change_raw)
                filtered.append((stat, change_percent))

            logger.debug(
                f"[Binance Futures] 过滤完成, {self.quote_asset} 计价资产数量: {len(filtered)} | "
                f"跳过无symbol={skipped_no_symbol} | 跳过不同计价资产={skipped_quote_asset}"
            )

            if not filtered:
                logger.warning(f"[Binance Futures] 未找到任何符合条件的 {self.quote_asset} 交易对")
                return []

            # 按涨跌幅降序排序，便于默认（limit=None）返回整体榜单
            filtered.sort(key=lambda x: x[1], reverse=True)

            if limit is not None:
                per_side_limit = max(0, limit)
                if per_side_limit == 0:
                    logger.info("[Binance Futures] limit<=0, 返回空榜单")
                    return []

                gainers_only = [item for item in filtered if item[1] >= 0]
                losers_only = [item for item in filtered if item[1] < 0]

                top_gainers = gainers_only[:per_side_limit]
                top_losers = sorted(losers_only, key=lambda x: x[1])[:per_side_limit]

                selected = top_gainers + top_losers
            else:
                selected = filtered

            result_payload: List[Dict[str, Any]] = []
            
            for stat, change_percent in selected:
                payload = dict(stat)
                # 确保关键字段存在
                payload.setdefault("priceChangePercent", change_percent)
                payload.setdefault("price_change_percent", change_percent)
                payload.setdefault("lastPrice", payload.get("last_price") or payload.get("close"))
                payload.setdefault("quoteVolume", payload.get("quote_volume") or payload.get("volume"))
                payload.setdefault("highPrice", payload.get("high_price"))
                payload.setdefault("lowPrice", payload.get("low_price"))
                
                # 设置 side 标记：根据涨跌幅判断是涨幅榜还是跌幅榜
                # priceChangePercent >= 0 表示上涨，标记为 'gainer'
                # priceChangePercent < 0 表示下跌，标记为 'loser'
                payload['side'] = 'gainer' if change_percent >= 0 else 'loser'
                
                result_payload.append(payload)

            if limit is not None:
                logger.info(f"[Binance Futures] 涨跌幅榜获取完成, 返回涨幅前 {len(result_payload)} 条数据")
            else:
                logger.info(f"[Binance Futures] 所有涨跌幅数据获取完成, 返回 {len(result_payload)} 条数据")
            return result_payload

        except Exception as exc:
            logger.error(f"[Binance Futures] 获取涨跌幅榜失败: {exc}", exc_info=True)
            return []

    def get_symbol_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        获取指定交易对的实时价格
        
        Args:
            symbols: 交易对符号列表，如 ['BTCUSDT', 'ETHUSDT']
            
        Returns:
            字典，key为交易对符号，value为实时价格数据
        """
        logger.info(f"[Binance Futures] 开始获取实时价格，交易对数量: {len(symbols)}")

        payload: Dict[str, Dict] = {}
        if not symbols:
            return payload

        try:
            # 逐个调用API获取每个交易对的实时价格
            prepared_symbols = [(symbol, symbol.upper()) for symbol in symbols]
            total = len(prepared_symbols)
            fetch_start = time.time()
            success = 0

            for idx, (source_symbol, request_symbol) in enumerate(prepared_symbols, start=1):
                logger.debug(f"[Binance Futures] 获取 {request_symbol} 实时价格 ({idx}/{total})")
                
                try:
                    call_start = time.time()
                    response = self._rest.symbol_price_ticker(symbol=request_symbol)
                    call_duration = time.time() - call_start
                    
                    # 转换响应为字典列表
                    dict_entries = self._flatten_to_dicts(
                        response.data(), "symbol_price_ticker"
                    )
                    
                    if not dict_entries:
                        logger.warning(f"[Binance Futures] {request_symbol} 无返回数据，跳过")
                        continue

                    # 匹配正确的交易对数据
                    normalized_symbol = request_symbol.upper()
                    matched_entry = None
                    for item in dict_entries:
                        symbol_value = item.get("symbol") or item.get("s")
                        if symbol_value and str(symbol_value).upper() == normalized_symbol:
                            matched_entry = item
                            break
                    
                    # 如果没找到精确匹配，使用第一条数据
                    if matched_entry is None:
                        matched_entry = dict_entries[0]

                    payload[source_symbol.upper()] = matched_entry
                    success += 1
                    logger.debug(f"[Binance Futures] {request_symbol} 获取成功, 耗时 {call_duration:.3f} 秒")
                    
                except Exception as symbol_exc:
                    logger.warning(f"[Binance Futures] 获取 {request_symbol} 失败: {symbol_exc}")
                    continue

            total_duration = time.time() - fetch_start
            logger.info(
                f"[Binance Futures] 实时价格获取完成, 成功 {success}/{total}, 总耗时 {total_duration:.3f} 秒"
            )

            # 记录未匹配的交易对
            missing = set(symbols) - set(payload.keys())
            if missing:
                logger.warning(
                    f"[Binance Futures] 未匹配到的交易对 ({len(missing)} 个): {list(missing)[:10]}{'...' if len(missing) > 10 else ''}"
                )

        except Exception as exc:
            logger.error(f"[Binance Futures] 获取实时价格失败: {exc}", exc_info=True)

        return payload

    def get_klines(self, symbol: str, interval: str, limit: int = 120, startTime: Optional[int] = None, endTime: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        获取K线数据
        
        Args:
            symbol: 交易对符号，如 'BTCUSDT'
            interval: K线间隔，如 '1m', '5m', '1h', '1d' 等
            limit: 返回的K线数量，默认120
            startTime: 起始时间戳（毫秒）
            endTime: 结束时间戳（毫秒）
            
        Returns:
            K线数据列表，每个元素为包含完整K线信息的字典：
            {
                "open_time": int,           # 开盘时间（毫秒时间戳）
                "open_time_dt": datetime,   # 开盘时间（日期格式）
                "open": str,                # 开盘价
                "high": str,                # 最高价
                "low": str,                 # 最低价
                "close": str,               # 收盘价
                "volume": str,              # 成交量
                "close_time": int,          # 收盘时间（毫秒时间戳）
                "close_time_dt": datetime,  # 收盘时间（日期格式）
                "quote_asset_volume": str,  # 成交额
                "number_of_trades": int,    # 成交笔数
                "taker_buy_base_volume": str,   # 主动买入成交量
                "taker_buy_quote_volume": str   # 主动买入成交额
            }
        """
        logger.info(f"[Binance Futures] 开始获取K线数据, symbol={symbol}, interval={interval}, limit={limit}, startTime={startTime}, endTime={endTime}")

        try:
            # 转换间隔为枚举类型
            interval_enum = KlineCandlestickDataIntervalEnum(interval)

            # 构建API调用参数
            api_params = {
                "symbol": symbol,
                "interval": interval_enum,
                "limit": limit,
            }
            
            # 添加可选的时间参数
            if startTime is not None:
                api_params["startTime"] = startTime
            if endTime is not None:
                api_params["endTime"] = endTime

            # 调用API获取K线数据
            api_start_time = time.time()
            response = self._rest.kline_candlestick_data(**api_params)
            data = self._normalize_list(response.data())
            api_duration = time.time() - api_start_time
            logger.debug(
                f"[Binance Futures] API调用完成, 耗时: {api_duration:.3f} 秒, 返回K线数量: {len(data)}"
            )

            # 转换K线数据为完整格式
            klines: List[Dict[str, Any]] = []
            for item in data:
                # 如果是列表/元组格式（Binance API标准格式）
                if isinstance(item, (list, tuple)) and len(item) >= 11:
                    open_time = item[0]
                    open_price = item[1]
                    high_price = item[2]
                    low_price = item[3]
                    close_price = item[4]
                    volume = item[5]
                    close_time = item[6]
                    quote_asset_volume = item[7]
                    number_of_trades = item[8]
                    taker_buy_base_volume = item[9]
                    taker_buy_quote_volume = item[10]
                    
                    # 转换时间戳为日期格式
                    open_time_dt = datetime.fromtimestamp(open_time / 1000) if open_time else None
                    close_time_dt = datetime.fromtimestamp(close_time / 1000) if close_time else None
                    
                    kline_dict = {
                        "open_time": open_time,
                        "open_time_dt": open_time_dt,
                        "open": open_price,
                        "high": high_price,
                        "low": low_price,
                        "close": close_price,
                        "volume": volume,
                        "close_time": close_time,
                        "close_time_dt": close_time_dt,
                        "quote_asset_volume": quote_asset_volume,
                        "number_of_trades": number_of_trades,
                        "taker_buy_base_volume": taker_buy_base_volume,
                        "taker_buy_quote_volume": taker_buy_quote_volume
                    }
                    klines.append(kline_dict)
                # 如果是字典或模型对象
                elif isinstance(item, dict) or hasattr(item, '__dict__'):
                    entry = self._to_dict(item) if not isinstance(item, dict) else item
                    if entry and len(entry) >= 6:
                        open_time = entry.get("open_time") or entry.get("openTime") or entry.get("t")
                        close_time = entry.get("close_time") or entry.get("closeTime") or entry.get("T")
                        
                        # 转换时间戳为日期格式
                        open_time_dt = datetime.fromtimestamp(open_time / 1000) if open_time else None
                        close_time_dt = datetime.fromtimestamp(close_time / 1000) if close_time else None
                        
                        kline_dict = {
                            "open_time": open_time,
                            "open_time_dt": open_time_dt,
                            "open": entry.get("open") or entry.get("o"),
                            "high": entry.get("high") or entry.get("h"),
                            "low": entry.get("low") or entry.get("l"),
                            "close": entry.get("close") or entry.get("c"),
                            "volume": entry.get("volume") or entry.get("v"),
                            "close_time": close_time,
                            "close_time_dt": close_time_dt,
                            "quote_asset_volume": entry.get("quote_asset_volume") or entry.get("q"),
                            "number_of_trades": entry.get("number_of_trades") or entry.get("n"),
                            "taker_buy_base_volume": entry.get("taker_buy_base_volume") or entry.get("V"),
                            "taker_buy_quote_volume": entry.get("taker_buy_quote_volume") or entry.get("Q")
                        }
                        klines.append(kline_dict)
                else:
                    logger.debug("[Binance Futures] 无法解析的数据项: %s", item)

            logger.info(f"[Binance Futures] K线数据获取完成, 返回 {len(klines)} 条K线")
            return klines

        except Exception as exc:
            logger.error(
                f"[Binance Futures] 获取K线数据失败: {exc}, "
                f"symbol={symbol}, interval={interval}, limit={limit}",
                exc_info=True
            )
            return []
