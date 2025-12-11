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
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
import common.config as app_config

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
        NewOrderSideEnum,
        TestOrderSideEnum,
    )
except ImportError as exc:  # pragma: no cover - handled at runtime
    BINANCE_SDK_AVAILABLE = False
    _BINANCE_IMPORT_ERROR = exc
    ConfigurationRestAPI = None  # type: ignore[assignment]
    DerivativesTradingUsdsFutures = None  # type: ignore[assignment]
    KlineCandlestickDataIntervalEnum = None  # type: ignore[assignment]
    NewOrderSideEnum = None  # type: ignore[assignment]
    TestOrderSideEnum = None  # type: ignore[assignment]
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

                    result[source_symbol.upper()] = matched_entry
                    success += 1
                    logger.debug(f"[Binance Futures] {request_symbol} 获取成功, 耗时 {call_duration:.3f} 秒")
                    
                except Exception as symbol_exc:
                    logger.warning(f"[Binance Futures] 获取 {request_symbol} 失败: {symbol_exc}")
                    continue

            total_duration = time.time() - fetch_start
            logger.info(
                f"[Binance Futures] 24小时统计获取完成, 成功 {success}/{total}, 总耗时 {total_duration:.3f} 秒"
            )

        except Exception as exc:
            logger.error(f"[Binance Futures] 获取24小时统计失败: {exc}", exc_info=True)

        return result

    def get_top_gainers(self, limit: Optional[int] = None) -> List[Dict]:
        """
        获取涨幅榜（24小时涨幅最大的交易对）
        
        Args:
            limit: 返回的交易对数量，默认10
            
        Returns:
            交易对列表，按涨幅降序排列
        """
        if limit is None:
            limit = 10

        logger.info(f"[Binance Futures] 开始获取涨幅榜，limit={limit}")

        try:
            # 获取所有交易对的24小时统计
            response = self._rest.ticker24hr_price_change_statistics()
            dict_entries = self._flatten_to_dicts(
                response.data(),
                "ticker24hr_price_change_statistics",
            )

            if not dict_entries:
                logger.warning("[Binance Futures] 涨幅榜无返回数据")
                return []

            # 按价格变动百分比排序（降序）
            sorted_entries = sorted(
                dict_entries,
                key=lambda x: float(x.get("priceChangePercent", x.get("P", 0)) or 0),
                reverse=True,
            )

            # 返回前limit个
            top_gainers = sorted_entries[:limit]
            logger.info(f"[Binance Futures] 涨幅榜获取完成，返回 {len(top_gainers)} 个交易对")

            return top_gainers

        except Exception as exc:
            logger.error(f"[Binance Futures] 获取涨幅榜失败: {exc}", exc_info=True)
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
            K线数据列表，每个元素为包含完整K线信息的字典
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
            
            # 如果提供了startTime和endTime，转换为SDK期望的start_time和end_time格式
            if startTime is not None:
                api_params["start_time"] = startTime
            if endTime is not None:
                api_params["end_time"] = endTime

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
                        open_price = entry.get("open") or entry.get("o")
                        high_price = entry.get("high") or entry.get("h")
                        low_price = entry.get("low") or entry.get("l")
                        close_price = entry.get("close") or entry.get("c")
                        volume = entry.get("volume") or entry.get("v")
                        close_time = entry.get("close_time") or entry.get("closeTime")
                        quote_asset_volume = entry.get("quote_asset_volume") or entry.get("quoteAssetVolume") or entry.get("q")
                        number_of_trades = entry.get("number_of_trades") or entry.get("numberOfTrades") or entry.get("n")
                        taker_buy_base_volume = entry.get("taker_buy_base_volume") or entry.get("takerBuyBaseVolume") or entry.get("V")
                        taker_buy_quote_volume = entry.get("taker_buy_quote_volume") or entry.get("takerBuyQuoteVolume") or entry.get("Q")
                        
                        # 转换时间戳为日期格式
                        open_time_dt = None
                        close_time_dt = None
                        if open_time:
                            try:
                                open_time_ms = int(open_time)
                                open_time_dt = datetime.fromtimestamp(open_time_ms / 1000)
                            except (ValueError, TypeError):
                                pass
                        if close_time:
                            try:
                                close_time_ms = int(close_time)
                                close_time_dt = datetime.fromtimestamp(close_time_ms / 1000)
                            except (ValueError, TypeError):
                                pass
                        
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

            logger.info(f"[Binance Futures] K线数据获取完成, 返回 {len(klines)} 条K线")
            return klines

        except Exception as exc:
            logger.error(
                f"[Binance Futures] 获取K线数据失败: {exc}, "
                f"symbol={symbol}, interval={interval}, limit={limit}",
                exc_info=True
            )
            return []


class BinanceFuturesAccountClient:
    """
    币安期货账户客户端 - 专注于账户功能的客户端
    
    提供获取账户信息、账户资产等功能，
    支持传入不同的api_key和api_secret进行操作。
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
        初始化币安期货账户客户端
        
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
    
    def get_account(self) -> str:
        """
        获取账户信息
        
        Returns:
            账户信息的JSON字符串
        
        Raises:
            RuntimeError: 如果SDK不可用
            Exception: 如果API调用失败
        """
        try:
            response = self._rest.account_information_v3()
            return response.data().to_json()
        except Exception as e:
            logger.error(f"[BinanceFuturesAccountClient] Failed to get account information: {e}")
            raise
    
    def get_account_asset(self) -> str:
        """
        获取账户资产信息
        
        Returns:
            账户资产信息的JSON字符串
        
        Raises:
            RuntimeError: 如果SDK不可用
            Exception: 如果API调用失败
        """
        try:
            import json
            response = self._rest.futures_account_balance_v3()
            data = response.data()
            
            # futures_account_balance_v3 返回的是列表，需要特殊处理
            if isinstance(data, list):
                # 将列表中的每个元素转换为字典
                result_list = []
                for item in data:
                    # 使用BinanceFuturesClient的_ensure_dict方法将对象转换为字典
                    dict_item = BinanceFuturesClient._ensure_dict(item)
                    if dict_item:
                        result_list.append(dict_item)
                    elif isinstance(item, dict):
                        # 如果已经是字典，直接使用
                        result_list.append(item)
                    else:
                        # 如果转换失败，尝试其他方法
                        try:
                            if hasattr(item, 'to_json'):
                                parsed = json.loads(item.to_json())
                                result_list.append(parsed)
                            elif hasattr(item, 'model_dump'):
                                result_list.append(item.model_dump())
                            elif hasattr(item, 'dict'):
                                result_list.append(item.dict())
                            else:
                                # 最后尝试直接序列化
                                result_list.append(json.loads(json.dumps(item, default=str)))
                        except Exception as e:
                            logger.warning(f"[BinanceFuturesAccountClient] Failed to convert item to dict: {e}")
                            # 如果都失败了，跳过该元素或使用字符串表示
                            continue
                return json.dumps(result_list, default=str)
            elif hasattr(data, 'to_json'):
                # 如果是对象且有to_json方法，使用to_json
                return data.to_json()
            else:
                # 其他情况，尝试转换为字典后序列化
                dict_data = BinanceFuturesClient._ensure_dict(data)
                if dict_data:
                    return json.dumps(dict_data, default=str)
                elif isinstance(data, dict):
                    return json.dumps(data, default=str)
                else:
                    # 最后尝试直接序列化
                    return json.dumps(data, default=str)
        except Exception as e:
            logger.error(f"[BinanceFuturesAccountClient] Failed to get account balance: {e}")
            raise


class BinanceFuturesOrderClient:
    """
    币安期货订单客户端 - 专注于交易功能的客户端
    
    提供止损交易、止盈交易、跟踪止损单和平仓交易等高级交易功能，
    支持传入不同的api_key和api_secret进行操作。
    positionSide 持仓方向，单向持仓模式下非必填，默认且仅可填BOTH;在双向持仓模式下必填,且仅可选择 LONG(多) 或 SHORT（空）
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
        初始化币安期货订单客户端
        
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

    def change_initial_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """
        修改合约的初始杠杆倍数
        
        Args:
            symbol: 交易对符号，如"BTCUSDT"
            leverage: 杠杆倍数，1-125之间的整数
            
        Returns:
            包含杠杆修改结果的字典
            
        Raises:
            RuntimeError: 如果SDK不可用
            Exception: 如果API调用失败
        """
        try:
            response = self._rest.change_initial_leverage(
                symbol=symbol,
                leverage=leverage
            )
            return response.data()
        except Exception as e:
            logger.error(f"[BinanceFuturesOrderClient] Failed to change initial leverage for {symbol}: {e}")
            raise
            
    def all_orders(self, symbol: str, **kwargs) -> List[Dict[str, Any]]:
        """
        获取交易对的全部订单信息
        
        Args:
            symbol: 交易对符号，如"BTCUSDT"
            **kwargs: 其他可选参数（参考币安API文档）
            
        Returns:
            订单列表，每个订单包含以下字段：
            - avgPrice: 平均成交价
            - clientOrderId: 用户自定义的订单号
            - cumQuote: 成交金额
            - executedQty: 成交量
            - orderId: 系统订单号
            - origQty: 原始委托数量
            - origType: 触发前订单类型
            - price: 委托价格
            - reduceOnly: 是否仅减仓
            - side: 买卖方向
            - positionSide: 持仓方向
            - status: 订单状态
            - stopPrice: 触发价
            - closePosition: 是否条件全平仓
            - symbol: 交易对
            - time: 订单时间
            - timeInForce: 有效方法
            - type: 订单类型
            - activatePrice: 跟踪止损激活价格
            - priceRate: 跟踪止损回调比例
            - updateTime: 更新时间
            - workingType: 条件价格触发类型
            - priceProtect: 是否开启条件单触发保护
            - priceMatch: 盘口价格下单模式
            - selfTradePreventionMode: 订单自成交保护模式
            - goodTillDate: 订单TIF为GTD时的自动取消时间
            
        Raises:
            RuntimeError: 如果SDK不可用
            Exception: 如果API调用失败
        """
        try:
            response = self._rest.all_orders(
                symbol=symbol,
                **kwargs
            )
            return response.data()
        except Exception as e:
            logger.error(f"[BinanceFuturesOrderClient] Failed to get all orders for {symbol}: {e}")
            raise

    def format_symbol(self, base_symbol: str) -> str:
        """
        格式化交易对符号，添加计价资产后缀
        
        Args:
            base_symbol: 基础交易对符号，如 'BTC'
            
        Returns:
            完整交易对符号，如 'BTCUSDT'
        """
        base_symbol = base_symbol.upper()
        # 检查base_symbol是否已经以quote_asset结尾，避免重复添加
        if not base_symbol.endswith(self.quote_asset):
            return f"{base_symbol}{self.quote_asset}"
        return base_symbol

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

    # ============ 交易方法 ============
    
    def _execute_order(self, order_params: Dict[str, Any], context: str = "交易") -> Dict[str, Any]:
        """
        执行订单的统一方法，根据配置选择使用测试接口或真实交易接口
        
        Args:
            order_params: 订单参数字典（包含完整的订单参数）
            context: 上下文信息，用于日志记录
            
        Returns:
            订单响应数据
        """
        # 【交易模式切换】根据配置选择使用测试接口或真实交易接口
        trade_mode = getattr(app_config, 'BINANCE_TRADE_MODE', 'test').lower()
        
        if trade_mode == 'test':
            # 使用测试接口（不会真实下单）
            logger.info(f"[Binance Futures] [{context}] 使用测试接口下单（不会真实成交）")
            # test_order接口只需要symbol、side、type三个基本参数
            # 从order_params中提取side值（可能是枚举值或字符串）
            side_value = order_params.get("side")
            if side_value is None:
                side_str = "BUY"
            elif hasattr(side_value, 'value'):
                # 如果是枚举值，提取其字符串值
                side_str = str(side_value.value).upper()
            else:
                side_str = str(side_value).upper()
            
            # 使用TestOrderSideEnum转换side参数
            if TestOrderSideEnum and side_str in TestOrderSideEnum.__members__:
                test_side = TestOrderSideEnum[side_str].value
            else:
                test_side = side_str
            
            test_params = {
                "symbol": order_params.get("symbol"),
                "side": test_side,
                "type": order_params.get("type"),
            }
            response = self._rest.test_order(**test_params)
            logger.info(f"[Binance Futures] [{context}] 测试接口调用成功（未真实下单）")
            response_context = "test_order"
        else:
            # 使用真实交易接口
            logger.info(f"[Binance Futures] [{context}] 使用真实交易接口下单")
            response = self._rest.new_order(**order_params)
            response_context = "new_order"
        
        # 处理响应
        data = response.data()
        logger.info(f"[Binance Futures] [{context}] 订单执行成功: {data}")
        
        return self._flatten_to_dicts(data, response_context)[0] if data else {}

    def stop_loss_trade(self, symbol: str, side: str, order_type: str = "STOP", quantity: Optional[float] = None, price: Optional[float] = None, stop_price: Optional[float] = None, position_side: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        止损交易 - 使用STOP或STOP_MARKET订单类型
        
        【默认订单类型】
        默认使用'STOP'订单类型，此时quantity、price、stop_price均为必填参数。
        如需使用'STOP_MARKET'订单类型，需显式指定order_type='STOP_MARKET'，此时只需stop_price。
        
        【position_side参数说明】
        在双向持仓模式下，此参数为必填项，用于指定持仓方向：
        - "LONG": 多头持仓（做多）
        - "SHORT": 空头持仓（做空）
        
        在单向持仓模式下，此参数可选，默认为"BOTH"。
        
        Args:
            symbol: 交易对符号，如 'BTCUSDT'
            side: 交易方向，'BUY'或'SELL'
            order_type: 订单类型，'STOP_MARKET'或'STOP'（默认）
            quantity: 订单数量（STOP订单必填，STOP_MARKET订单不需要）
            price: 订单价格（STOP订单必填，STOP_MARKET订单不需要）
            stop_price: 止损触发价格（STOP和STOP_MARKET订单均必填）
            position_side: 持仓方向，'LONG'（多）或'SHORT'（空），双向持仓模式下必填
            止损单：买入:最新合约价格/标记价格高于等于触发价stop_price;卖出:最新合约价格/标记价格低于等于触发价stop_price;
            **kwargs: 其他可选参数
            
        Returns:
            订单响应数据
            
        Raises:
            ValueError: 当STOP订单缺少必填参数（quantity、price、stop_price）时
        """
        # 【参数验证】当order_type为默认值"STOP"时，验证必填参数
        order_type_upper = order_type.upper()
        if order_type_upper == "STOP":
            if quantity is None:
                raise ValueError("STOP订单必须提供quantity参数")
            if price is None:
                raise ValueError("STOP订单必须提供price参数")
            if stop_price is None:
                raise ValueError("STOP订单必须提供stop_price参数")
        elif order_type_upper == "STOP_MARKET":
            if stop_price is None:
                raise ValueError("STOP_MARKET订单必须提供stop_price参数")
        else:
            raise ValueError(f"不支持的订单类型: {order_type}，仅支持'STOP'或'STOP_MARKET'")
        
        logger.info(f"[Binance Futures] 开始止损交易，交易对: {symbol}, 方向: {side}, 类型: {order_type_upper}, 持仓方向: {position_side}")
        
        try:
            # 格式化交易对
            formatted_symbol = self.format_symbol(symbol)
            
            # 【参数验证】验证position_side参数值
            if position_side is not None:
                position_side_upper = position_side.upper()
                if position_side_upper not in ["LONG", "SHORT"]:
                    raise ValueError(f"position_side参数值必须是'LONG'或'SHORT'，当前值: {position_side}")
                position_side = position_side_upper
            
            # 准备订单参数
            order_params = {
                "symbol": formatted_symbol,
                "side": NewOrderSideEnum[side.upper()].value if NewOrderSideEnum else side.upper(),
                "type": order_type_upper,
                "stop_price": stop_price,
            }
            
            # 【添加position_side参数】在双向持仓模式下，此参数为必填项
            if position_side:
                order_params["position_side"] = position_side
            
            # 【添加STOP订单所需的参数】当order_type为STOP时，quantity和price已通过前置验证确保存在
            if order_type_upper == "STOP":
                order_params["quantity"] = quantity
                order_params["price"] = price
                order_params["time_in_force"] = kwargs.get("time_in_force", "GTC")
            
            # 添加可选参数
            order_params.update(kwargs)
            
            # 【统一订单执行】使用辅助方法处理测试/真实交易切换
            return self._execute_order(order_params, context="止损交易")
            
        except Exception as exc:
            logger.error(f"[Binance Futures] 止损交易失败: {exc}", exc_info=True)
            raise

    def take_profit_trade(self, symbol: str, side: str, order_type: str = "TAKE_PROFIT", quantity: Optional[float] = None, price: Optional[float] = None, stop_price: Optional[float] = None, position_side: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        止盈交易 - 使用TAKE_PROFIT或TAKE_PROFIT_MARKET订单类型
        
        【默认订单类型】
        默认使用'TAKE_PROFIT'订单类型，此时quantity、price、stop_price均为必填参数。
        如需使用'TAKE_PROFIT_MARKET'订单类型，需显式指定order_type='TAKE_PROFIT_MARKET'，此时只需stop_price。
        
        【position_side参数说明】
        在双向持仓模式下，此参数为必填项，用于指定持仓方向：
        - "LONG": 多头持仓（做多）
        - "SHORT": 空头持仓（做空）
        
        在单向持仓模式下，此参数可选，默认为"BOTH"。
        
        Args:
            symbol: 交易对符号，如 'BTCUSDT'
            side: 交易方向，'BUY'或'SELL'
            order_type: 订单类型，'TAKE_PROFIT_MARKET'或'TAKE_PROFIT'（默认）
            quantity: 订单数量（TAKE_PROFIT订单必填，TAKE_PROFIT_MARKET订单不需要）
            price: 订单价格（TAKE_PROFIT订单必填，TAKE_PROFIT_MARKET订单不需要）
            stop_price: 止盈触发价格（TAKE_PROFIT和TAKE_PROFIT_MARKET订单均必填）
            position_side: 持仓方向，'LONG'（多）或'SHORT'（空），双向持仓模式下必填
            **kwargs: 其他可选参数
            止盈单：买入:最新合约价格/标记价格低于等于触发价stop_price;卖出:最新合约价格/标记价格高于等于触发价stop_price;
        Returns:
            订单响应数据
            
        Raises:
            ValueError: 当TAKE_PROFIT订单缺少必填参数（quantity、price、stop_price）时
        """
        # 【参数验证】当order_type为默认值"TAKE_PROFIT"时，验证必填参数
        order_type_upper = order_type.upper()
        if order_type_upper == "TAKE_PROFIT":
            if quantity is None:
                raise ValueError("TAKE_PROFIT订单必须提供quantity参数")
            if price is None:
                raise ValueError("TAKE_PROFIT订单必须提供price参数")
            if stop_price is None:
                raise ValueError("TAKE_PROFIT订单必须提供stop_price参数")
        elif order_type_upper == "TAKE_PROFIT_MARKET":
            if stop_price is None:
                raise ValueError("TAKE_PROFIT_MARKET订单必须提供stop_price参数")
        else:
            raise ValueError(f"不支持的订单类型: {order_type}，仅支持'TAKE_PROFIT'或'TAKE_PROFIT_MARKET'")
        
        logger.info(f"[Binance Futures] 开始止盈交易，交易对: {symbol}, 方向: {side}, 类型: {order_type_upper}, 持仓方向: {position_side}")
        
        try:
            # 格式化交易对
            formatted_symbol = self.format_symbol(symbol)
            
            # 【参数验证】验证position_side参数值
            if position_side is not None:
                position_side_upper = position_side.upper()
                if position_side_upper not in ["LONG", "SHORT"]:
                    raise ValueError(f"position_side参数值必须是'LONG'或'SHORT'，当前值: {position_side}")
                position_side = position_side_upper
            
            # 准备订单参数
            order_params = {
                "symbol": formatted_symbol,
                "side": NewOrderSideEnum[side.upper()].value if NewOrderSideEnum else side.upper(),
                "type": order_type_upper,
                "stop_price": stop_price,
            }
            
            # 【添加position_side参数】在双向持仓模式下，此参数为必填项
            if position_side:
                order_params["position_side"] = position_side
            
            # 【添加TAKE_PROFIT订单所需的参数】当order_type为TAKE_PROFIT时，quantity和price已通过前置验证确保存在
            if order_type_upper == "TAKE_PROFIT":
                order_params["quantity"] = quantity
                order_params["price"] = price
                order_params["time_in_force"] = kwargs.get("time_in_force", "GTC")
            
            # 添加可选参数
            order_params.update(kwargs)
            
            # 【统一订单执行】使用辅助方法处理测试/真实交易切换
            return self._execute_order(order_params, context="止盈交易")
            
        except Exception as exc:
            logger.error(f"[Binance Futures] 止盈交易失败: {exc}", exc_info=True)
            raise

    def trailing_stop_market_trade(self, symbol: str, side: str, callback_rate: float = 1.0, position_side: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        市场价格交易- 使用TRAILING_STOP_MARKET订单类型
        
        【position_side参数说明】
        在双向持仓模式下，此参数为必填项，用于指定持仓方向：
        - "LONG": 多头持仓（做多）
        - "SHORT": 空头持仓（做空）
        
        在单向持仓模式下，此参数可选，默认为"BOTH"。
        
        Args:
            symbol: 交易对符号，如 'BTCUSDT'
            side: 交易方向，'BUY'或'SELL'
            callback_rate: 回调幅度百分比，默认1.0（即1%），范围[0.1-10]
            position_side: 【新增参数】持仓方向，'LONG'（多）或'SHORT'（空），双向持仓模式下必填
            **kwargs: 其他可选参数
            
        Returns:
            订单响应数据
        """
        logger.info(f"[Binance Futures] 开始跟踪止损交易，交易对: {symbol}, 方向: {side}, 回调幅度: {callback_rate}%, 持仓方向: {position_side}")
        
        try:
            # 格式化交易对
            formatted_symbol = self.format_symbol(symbol)
            
            # 【参数验证】验证position_side参数值
            if position_side is not None:
                position_side_upper = position_side.upper()
                if position_side_upper not in ["LONG", "SHORT"]:
                    raise ValueError(f"position_side参数值必须是'LONG'或'SHORT'，当前值: {position_side}")
                position_side = position_side_upper
            
            # 准备订单参数
            order_params = {
                "symbol": formatted_symbol,
                "side": NewOrderSideEnum[side.upper()].value if NewOrderSideEnum else side.upper(),
                "type": "TRAILING_STOP_MARKET",
                "callback_rate": callback_rate,
                # 不设置activationPrice参数
            }
            
            # 【添加position_side参数】在双向持仓模式下，此参数为必填项
            if position_side:
                order_params["position_side"] = position_side
            
            # 添加可选参数
            order_params.update(kwargs)
            
            # 【统一订单执行】使用辅助方法处理测试/真实交易切换
            return self._execute_order(order_params, context="跟踪止损交易")
            
        except Exception as exc:
            logger.error(f"[Binance Futures] 跟踪止损交易失败: {exc}", exc_info=True)
            raise

    def close_position_trade(self, symbol: str, side: str, order_type: str="STOP_MARKET", stop_price: Optional[float] = None, position_side: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        平仓交易 - 使用STOP_MARKET或TAKE_PROFIT_MARKET订单类型配合closePosition=true
        
        【position_side参数说明】
        在双向持仓模式下，此参数为必填项，用于指定要平仓的持仓方向：
        - "LONG": 平掉多头持仓（做多）
        - "SHORT": 平掉空头持仓（做空）
        
        在单向持仓模式下，此参数可选，默认为"BOTH"。
        
        Args:
            symbol: 交易对符号，如 'BTCUSDT'
            side: 交易方向，'BUY'或'SELL'
            order_type: 订单类型，'STOP_MARKET'(默认)或'TAKE_PROFIT_MARKET'
            stop_price: 触发价格（可选，取决于order_type）
            position_side: 持仓方向，'LONG'（多）或'SHORT'（空），双向持仓模式下必填
            **kwargs: 其他可选参数
            
        【双开模式校验规则】
        在双向持仓模式下，side和position_side的组合必须符合以下规则：
        - LONG方向上不支持BUY操作（平多仓应使用SELL）
        - SHORT方向上不支持SELL操作（平空仓应使用BUY）
        
        Returns:
            订单响应数据
        """
        logger.info(f"[Binance Futures] 开始平仓交易，交易对: {symbol}, 方向: {side}, 类型: {order_type}, 持仓方向: {position_side}")
        
        try:
            # 格式化交易对
            formatted_symbol = self.format_symbol(symbol)
            
            # 【参数验证】验证position_side参数值
            if position_side is not None:
                position_side_upper = position_side.upper()
                if position_side_upper not in ["LONG", "SHORT"]:
                    raise ValueError(f"position_side参数值必须是'LONG'或'SHORT'，当前值: {position_side}")
                position_side = position_side_upper
                
                # 【双开模式校验】验证side和position_side的组合是否合法
                # LONG方向上不支持BUY（平多仓应该用SELL）
                # SHORT方向上不支持SELL（平空仓应该用BUY）
                side_upper = side.upper()
                if position_side == "LONG" and side_upper == "BUY":
                    raise ValueError(f"双开模式下，LONG方向上不支持BUY操作。平多仓应使用SELL，当前side={side}, position_side={position_side}")
                if position_side == "SHORT" and side_upper == "SELL":
                    raise ValueError(f"双开模式下，SHORT方向上不支持SELL操作。平空仓应使用BUY，当前side={side}, position_side={position_side}")
            
            # 准备订单参数
            order_params = {
                "symbol": formatted_symbol,
                "side": NewOrderSideEnum[side.upper()].value if NewOrderSideEnum else side.upper(),
                "type": order_type.upper(),
                "close_position": True,
            }
            
            # 【添加position_side参数】在双向持仓模式下，此参数为必填项
            if position_side:
                order_params["position_side"] = position_side
            
            # 添加触发价格参数（如果需要）
            if order_type.upper() in ["STOP_MARKET", "TAKE_PROFIT_MARKET"] and stop_price is not None:
                order_params["stop_price"] = stop_price
            
            # 添加可选参数
            order_params.update(kwargs)
            
            # 【统一订单执行】使用辅助方法处理测试/真实交易切换
            return self._execute_order(order_params, context="平仓交易")
            
        except Exception as exc:
            logger.error(f"[Binance Futures] 平仓交易失败: {exc}", exc_info=True)
            raise

    def format_symbol(self, base_symbol: str) -> str:
        """
        格式化交易对符号，添加计价资产后缀
        
        Args:
            base_symbol: 基础交易对符号，如 'BTC'
            
        Returns:
            完整交易对符号，如 'BTCUSDT'
        """
        base_symbol = base_symbol.upper()
        # 检查base_symbol是否已经以quote_asset结尾，避免重复添加
        if not base_symbol.endswith(self.quote_asset):
            return f"{base_symbol}{self.quote_asset}"
        return base_symbol

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
            # SDK的kline_candlestick_data方法支持start_time和end_time参数（小写下划线格式）
            api_params = {
                "symbol": symbol,
                "interval": interval_enum,
                "limit": limit,
            }
            
            # 如果提供了startTime和endTime，转换为SDK期望的start_time和end_time格式
            if startTime is not None:
                api_params["start_time"] = startTime
            if endTime is not None:
                api_params["end_time"] = endTime

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
