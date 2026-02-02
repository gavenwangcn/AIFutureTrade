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
import threading
import requests
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List, Optional
import trade.common.config as app_config

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
        ChangeMarginTypeMarginTypeEnum,
    )
except ImportError as exc:  # pragma: no cover - handled at runtime
    BINANCE_SDK_AVAILABLE = False
    _BINANCE_IMPORT_ERROR = exc
    ConfigurationRestAPI = None  # type: ignore[assignment]
    DerivativesTradingUsdsFutures = None  # type: ignore[assignment]
    KlineCandlestickDataIntervalEnum = None  # type: ignore[assignment]
    NewOrderSideEnum = None  # type: ignore[assignment]
    TestOrderSideEnum = None  # type: ignore[assignment]
    ChangeMarginTypeMarginTypeEnum = None  # type: ignore[assignment]
    DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL = None  # type: ignore[assignment]
    DERIVATIVES_TRADING_USDS_FUTURES_REST_API_TESTNET_URL = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


def _to_epoch_milli(ts: Any) -> int:
    """将时间戳统一为毫秒，支持 10 位（秒）或 13 位（毫秒），与 Java binance-service 一致。"""
    if ts is None:
        return 0
    try:
        t = int(ts)
        if t < 1_000_000_000_000:
            return t * 1000
        return t
    except (ValueError, TypeError):
        return 0


# ============ Binance Service客户端（用于调用binance-service微服务） ============

class BinanceServiceManager:
    """
    Binance Service管理器
    
    用于管理多个binance-service配置，实现轮询使用。
    只用于查询symbol相关数据的接口（如实时价格、K线信息等）。
    下单和查询账户相关的接口不使用binance-service。
    """
    
    def __init__(self, service_list: List[Dict[str, Any]]):
        """
        初始化Binance Service管理器
        
        Args:
            service_list: Service配置列表，每个元素是一个service配置字典
        """
        self._service_list = service_list if service_list else []
        self._current_index = 0
        self._lock = threading.Lock()
        if self._service_list:
            logger.info(f"[BinanceServiceManager] 初始化，共 {len(self._service_list)} 个Binance Service配置")
            for i, service in enumerate(self._service_list):
                logger.info(f"[BinanceServiceManager] Service {i+1}: {service.get('base_url')}")
        else:
            logger.info("[BinanceServiceManager] 未配置Binance Service，将直接调用SDK")
    
    def get_next_service(self) -> Optional[Dict[str, Any]]:
        """
        获取下一个service配置（轮询方式）
        
        Returns:
            Service配置字典，如果没有配置则返回None
        """
        if not self._service_list:
            return None
        
        with self._lock:
            current_service_index = self._current_index
            service = self._service_list[current_service_index]
            self._current_index = (self._current_index + 1) % len(self._service_list)
            logger.debug(f"[BinanceServiceManager] 使用Service {current_service_index + 1}/{len(self._service_list)}: {service.get('base_url')}")
            return service.copy()  # 返回副本，避免修改原始配置
    
    def has_service(self) -> bool:
        """
        检查是否有可用的service配置
        
        Returns:
            如果有service配置返回True，否则返回False
        """
        return len(self._service_list) > 0


# 全局Binance Service管理器实例
_binance_service_manager: Optional[BinanceServiceManager] = None


def _get_binance_service_manager() -> BinanceServiceManager:
    """
    获取全局Binance Service管理器实例（单例模式）
    
    Returns:
        BinanceServiceManager实例
    """
    global _binance_service_manager
    if _binance_service_manager is None:
        service_list = getattr(app_config, 'BINANCE_SERVICE_LIST', [])
        _binance_service_manager = BinanceServiceManager(service_list)
    return _binance_service_manager


class BinanceServiceClient:
    """
    Binance Service客户端
    
    用于调用binance-service微服务的HTTP接口。
    只用于查询symbol相关数据的接口（如实时价格、K线信息等）。
    """
    
    def __init__(self, base_url: str, timeout: int = 30):
        """
        初始化Binance Service客户端
        
        Args:
            base_url: Binance Service基础URL
            timeout: 请求超时时间（秒）
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        logger.debug(f"[BinanceServiceClient] 初始化: base_url={base_url}, timeout={timeout}")
    
    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None, 
                     data: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """
        发送HTTP请求
        
        Args:
            method: HTTP方法（GET, POST等）
            endpoint: API端点
            params: URL参数
            data: 请求体数据
        
        Returns:
            响应数据字典，如果失败返回None
        """
        url = f"{self.base_url}{endpoint}"
        try:
            if method.upper() == 'GET':
                response = requests.get(url, params=params, timeout=self.timeout)
            elif method.upper() == 'POST':
                response = requests.post(url, json=data, params=params, timeout=self.timeout)
            else:
                logger.error(f"[BinanceServiceClient] 不支持的HTTP方法: {method}")
                return None
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('success'):
                return result.get('data')
            else:
                logger.warning(f"[BinanceServiceClient] API返回失败: {result.get('message')}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"[BinanceServiceClient] HTTP请求失败: {e}, url={url}")
            return None
        except Exception as e:
            logger.error(f"[BinanceServiceClient] 请求处理失败: {e}, url={url}")
            return None
    
    def get_24h_ticker(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        获取24小时价格变动统计
        
        Args:
            symbols: 交易对符号列表
        
        Returns:
            24小时统计数据字典
        """
        logger.debug(f"[BinanceServiceClient] 调用get_24h_ticker: symbols={symbols}")
        result = self._make_request('POST', '/api/market-data/24h-ticker', data=symbols)
        return result if result else {}
    
    def get_symbol_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        获取实时价格
        
        Args:
            symbols: 交易对符号列表
        
        Returns:
            实时价格数据字典
        """
        logger.debug(f"[BinanceServiceClient] 调用get_symbol_prices: symbols={symbols}")
        result = self._make_request('POST', '/api/market-data/symbol-prices', data=symbols)
        return result if result else {}
    
    def get_klines(self, symbol: str, interval: str, limit: int = 120, 
                   startTime: Optional[int] = None, endTime: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        获取K线数据
        
        Args:
            symbol: 交易对符号
            interval: K线间隔
            limit: 返回的K线数量
            startTime: 起始时间戳（毫秒）
            endTime: 结束时间戳（毫秒）
        
        Returns:
            K线数据列表
        """
        logger.debug(f"[BinanceServiceClient] 调用get_klines: symbol={symbol}, interval={interval}, limit={limit}")
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': limit,
        }
        if startTime is not None:
            params['startTime'] = startTime
        if endTime is not None:
            params['endTime'] = endTime
        
        result = self._make_request('GET', '/api/market-data/klines', params=params)
        return result if result else []
    
    def format_symbol(self, base_symbol: str) -> str:
        """
        格式化交易对符号
        
        Args:
            base_symbol: 基础交易对符号
        
        Returns:
            完整交易对符号
        """
        logger.debug(f"[BinanceServiceClient] 调用format_symbol: base_symbol={base_symbol}")
        params = {'baseSymbol': base_symbol}
        result = self._make_request('GET', '/api/market-data/format-symbol', params=params)
        return result if result else base_symbol


# ============ 基类：共享公共方法 ============

class _BinanceFuturesBase:
    """
    币安期货客户端基类 - 提供公共的工具方法
    
    所有币安期货客户端类都继承此基类，共享数据格式转换等工具方法。
    """
    
    def format_symbol(self, base_symbol: str) -> str:
        """
        格式化交易对符号，添加计价资产后缀
        
        Args:
            base_symbol: 基础交易对符号，如 'BTC'
            
        Returns:
            完整交易对符号，如 'BTCUSDT'
        """
        base_symbol = base_symbol.upper()
        if not base_symbol.endswith(self.quote_asset):
            return f"{base_symbol}{self.quote_asset}"
        return base_symbol

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

        if hasattr(item, "model_dump"):
            try:
                dumped = item.model_dump()
                if isinstance(dumped, dict):
                    return dumped
            except Exception:  # pragma: no cover - defensive
                pass

        if hasattr(item, "dict"):
            try:
                dumped = item.dict()
                if isinstance(dumped, dict):
                    return dumped
            except Exception:
                pass

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

            if isinstance(current, list):
                queue.extend(current)
                continue

            if isinstance(current, dict):
                flattened.append(current)
                continue

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

            normalized = self._ensure_dict(current)
            if normalized:
                flattened.append(normalized)

        return flattened


class BinanceFuturesClient(_BinanceFuturesBase):
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
        # 设置超时时间为10秒（10000毫秒），避免网络超时错误
        # 注意：timeout参数单位是毫秒，默认值是1000毫秒（1秒）
        configuration = ConfigurationRestAPI(
            api_key=api_key,
            api_secret=api_secret,
            base_path=rest_base,
            timeout=10000,  # 超时时间设置为10秒（10000毫秒）
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
        
    # ============ 市场数据获取方法 ============
    
    def get_24h_ticker(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        获取指定交易对的24小时价格变动统计
        
        Args:
            symbols: 交易对符号列表，如 ['BTCUSDT', 'ETHUSDT']
            
        Returns:
            字典，key为交易对符号，value为24小时统计数据
        """
        # 如果配置了binance-service，优先使用binance-service
        service_enabled = getattr(app_config, 'BINANCE_SERVICE_ENABLED', False)
        if service_enabled:
            service_manager = _get_binance_service_manager()
            if service_manager.has_service():
                try:
                    service_config = service_manager.get_next_service()
                    service_client = BinanceServiceClient(
                        base_url=service_config.get('base_url'),
                        timeout=service_config.get('timeout', getattr(app_config, 'BINANCE_SERVICE_DEFAULT_TIMEOUT', 30))
                    )
                    logger.info(f"[Binance Futures] 使用Binance Service获取24小时统计，交易对数量: {len(symbols)}")
                    result = service_client.get_24h_ticker(symbols)
                    if result:
                        return result
                    else:
                        logger.warning(
                            "[Binance Futures] Binance Service返回空结果，回退到SDK调用 | "
                            f"API接口: get_24h_ticker | "
                            f"Service URL: {service_config.get('base_url')} | "
                            f"请求参数: symbols={symbols[:10]}{'...' if len(symbols) > 10 else ''} (共{len(symbols)}个) | "
                            f"返回结果: {result}"
                        )
                except Exception as e:
                    logger.warning(f"[Binance Futures] Binance Service调用失败，回退到SDK调用: {e}")
        
        # 回退到直接调用SDK
        logger.info(f"[Binance Futures] 开始获取24小时价格变动统计，交易对数量: {len(symbols)}")
        
        # 原有的SDK调用逻辑
        return self._get_24h_ticker_from_sdk(symbols)
    
    def _get_24h_ticker_from_sdk(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        获取指定交易对的24小时价格变动统计
        
        Args:
            symbols: 交易对符号列表，如 ['BTCUSDT', 'ETHUSDT']
            
        Returns:
            字典，key为交易对符号，value为24小时统计数据
            {
                "symbol": "BTCUSDT",
                "priceChange": "-94.99999800",    //24小时价格变动
                "priceChangePercent": "-95.960",  //24小时价格变动百分比
                "weightedAvgPrice": "0.29628482", //加权平均价
                "lastPrice": "4.00000200",        //最近一次成交价
                "lastQty": "200.00000000",        //最近一次成交额
                "openPrice": "99.00000000",       //24小时内第一次成交的价格
                "highPrice": "100.00000000",      //24小时最高价
                "lowPrice": "0.10000000",         //24小时最低价
                "volume": "8913.30000000",        //24小时成交量
                "quoteVolume": "15.30000000",     //24小时成交额
                "openTime": 1499783499040,        //24小时内，第一笔交易的发生时间
                "closeTime": 1499869899040,       //24小时内，最后一笔交易的发生时间
                "firstId": 28385,   // 首笔成交id
                "lastId": 28460,    // 末笔成交id
                "count": 76         // 成交笔数
            }
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



    def get_symbol_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        获取指定交易对的实时价格
        
        Args:
            symbols: 交易对符号列表，如 ['BTCUSDT', 'ETHUSDT']
            
        Returns:
            字典，key为交易对符号，value为实时价格数据
        """
        # 如果配置了binance-service，优先使用binance-service
        service_enabled = getattr(app_config, 'BINANCE_SERVICE_ENABLED', False)
        if service_enabled:
            service_manager = _get_binance_service_manager()
            if service_manager.has_service():
                try:
                    service_config = service_manager.get_next_service()
                    service_client = BinanceServiceClient(
                        base_url=service_config.get('base_url'),
                        timeout=service_config.get('timeout', getattr(app_config, 'BINANCE_SERVICE_DEFAULT_TIMEOUT', 30))
                    )
                    logger.debug(f"[Binance Futures] 使用Binance Service获取实时价格，交易对数量: {len(symbols)}")
                    result = service_client.get_symbol_prices(symbols)
                    if result:
                        return result
                    else:
                        logger.warning(
                            "[Binance Futures] Binance Service返回空结果，回退到SDK调用 | "
                            f"API接口: get_symbol_prices | "
                            f"Service URL: {service_config.get('base_url')} | "
                            f"请求参数: symbols={symbols[:10]}{'...' if len(symbols) > 10 else ''} (共{len(symbols)}个) | "
                            f"返回结果: {result}"
                        )
                except Exception as e:
                    logger.warning(f"[Binance Futures] Binance Service调用失败，回退到SDK调用: {e}")
        
        # 回退到直接调用SDK
        logger.debug(f"[Binance Futures] 开始获取实时价格，交易对数量: {len(symbols)}")

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
            logger.debug(
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
        # 如果配置了binance-service，优先使用binance-service
        service_enabled = getattr(app_config, 'BINANCE_SERVICE_ENABLED', False)
        if service_enabled:
            service_manager = _get_binance_service_manager()
            if service_manager.has_service():
                try:
                    service_config = service_manager.get_next_service()
                    service_client = BinanceServiceClient(
                        base_url=service_config.get('base_url'),
                        timeout=service_config.get('timeout', getattr(app_config, 'BINANCE_SERVICE_DEFAULT_TIMEOUT', 30))
                    )
                    logger.debug(f"[Binance Futures] 使用Binance Service获取K线数据, symbol={symbol}, interval={interval}, limit={limit}")
                    result = service_client.get_klines(symbol, interval, limit, startTime, endTime)
                    if result:
                        return result
                    else:
                        logger.warning(
                            "[Binance Futures] Binance Service返回空结果，回退到SDK调用 | "
                            f"API接口: get_klines | "
                            f"Service URL: {service_config.get('base_url')} | "
                            f"请求参数: symbol={symbol}, interval={interval}, limit={limit}, startTime={startTime}, endTime={endTime} | "
                            f"返回结果: {result} (类型: {type(result).__name__}, 长度: {len(result) if isinstance(result, (list, dict)) else 'N/A'})"
                        )
                except Exception as e:
                    logger.warning(f"[Binance Futures] Binance Service调用失败，回退到SDK调用: {e}")
        
        # 回退到直接调用SDK
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

            # 转换K线数据为完整格式（与 Java binance-service 一致：含 open_time_dt_str/close_time_dt_str，UTC+8）
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
                    
                    open_time_ms = _to_epoch_milli(open_time)
                    close_time_ms = _to_epoch_milli(close_time)
                    utc8 = timezone(timedelta(hours=8))
                    open_time_dt = datetime.fromtimestamp(open_time_ms / 1000, tz=utc8) if open_time_ms else None
                    close_time_dt = datetime.fromtimestamp(close_time_ms / 1000, tz=utc8) if close_time_ms else None
                    open_time_dt_str = open_time_dt.strftime('%Y-%m-%d %H:%M:%S') if open_time_dt else None
                    close_time_dt_str = close_time_dt.strftime('%Y-%m-%d %H:%M:%S') if close_time_dt else None
                    
                    kline_dict = {
                        "open_time": open_time,
                        "open_time_dt_str": open_time_dt_str,
                        "open": open_price,
                        "high": high_price,
                        "low": low_price,
                        "close": close_price,
                        "volume": volume,
                        "close_time": close_time,
                        "close_time_dt_str": close_time_dt_str,
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
                        
                        open_time_ms = _to_epoch_milli(open_time)
                        close_time_ms = _to_epoch_milli(close_time)
                        utc8 = timezone(timedelta(hours=8))
                        open_time_dt = datetime.fromtimestamp(open_time_ms / 1000, tz=utc8) if open_time_ms else None
                        close_time_dt = datetime.fromtimestamp(close_time_ms / 1000, tz=utc8) if close_time_ms else None
                        open_time_dt_str = open_time_dt.strftime('%Y-%m-%d %H:%M:%S') if open_time_dt else None
                        close_time_dt_str = close_time_dt.strftime('%Y-%m-%d %H:%M:%S') if close_time_dt else None
                        
                        kline_dict = {
                            "open_time": open_time,
                            "open_time_dt_str": open_time_dt_str,
                            "open": open_price,
                            "high": high_price,
                            "low": low_price,
                            "close": close_price,
                            "volume": volume,
                            "close_time": close_time,
                            "close_time_dt_str": close_time_dt_str,
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


class BinanceFuturesAccountClient(_BinanceFuturesBase):
    """
    币安期货账户客户端 - 专注于账户功能的客户端
    
    提供获取账户信息、账户资产等功能，支持传入不同的api_key和api_secret进行操作。
    主要用于账户管理和资产查询。
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
        # 设置超时时间为10秒（10000毫秒），避免网络超时错误
        # 注意：timeout参数单位是毫秒，默认值是1000毫秒（1秒）
        configuration = ConfigurationRestAPI(
            api_key=api_key,
            api_secret=api_secret,
            base_path=rest_base,
            timeout=10000,  # 超时时间设置为10秒（10000毫秒）
        )

        self.quote_asset = quote_asset.upper()
        self._client = DerivativesTradingUsdsFutures(config_rest_api=configuration)
        self._rest = self._client.rest_api
    
    # ============ 账户信息获取方法 ============
    
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
    
class BinanceFuturesOrderClient(_BinanceFuturesBase):
    """
    币安期货订单客户端 - 专注于交易功能的客户端
    
    提供止损交易、止盈交易、跟踪止损单和平仓交易等高级交易功能，
    支持传入不同的api_key和api_secret进行操作。
    
    【持仓方向说明】
    positionSide 持仓方向：
    - 单向持仓模式下：非必填，默认且仅可填BOTH
    - 双向持仓模式下：必填，且仅可选择 LONG(多) 或 SHORT（空）
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
        # 设置超时时间为10秒（10000毫秒），避免网络超时错误
        # 注意：timeout参数单位是毫秒，默认值是1000毫秒（1秒）
        configuration = ConfigurationRestAPI(
            api_key=api_key,
            api_secret=api_secret,
            base_path=rest_base,
            timeout=10000,  # 超时时间设置为10秒（10000毫秒）
        )

        self.quote_asset = quote_asset.upper()
        self._client = DerivativesTradingUsdsFutures(config_rest_api=configuration)
        self._rest = self._client.rest_api
        
        # 缓存交易规则信息（symbol -> {stepSize, tickSize}）
        self._symbol_precision_cache: Dict[str, Dict[str, float]] = {}
        self._cache_timestamp: float = 0
        self._cache_ttl: float = 3600  # 缓存1小时

    def get_order_book_ticker(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取最优挂单价格（Order Book Ticker）
        
        该接口返回指定交易对或所有交易对的最优买卖挂单价格信息，
        包括当前的买一价、买一量、卖一价、卖一量等数据。
        
        Args:
            symbol: 交易对符号，如 'BTC' 或 'BTCUSDT'（可选）。
                   如果不提供，则返回所有交易对的最优挂单价格。
            
        Returns:
            最优挂单价格信息列表，每个元素包含交易对的最优买卖价格和数量。
        {
            "symbol": "BTCUSDT", // 交易对
            "bidPrice": "4.00000000", //最优买单价
            "bidQty": "431.00000000", //挂单量
            "askPrice": "4.00000200", //最优卖单价
            "askQty": "9.00000000", //挂单量
            "time": 1589437530011   // 撮合引擎时间
        }
        Raises:
            RuntimeError: 如果SDK不可用
            Exception: 如果API调用失败
        """
        try:
            # 如果提供了symbol参数，格式化交易对
            formatted_symbol = None
            if symbol:
                formatted_symbol = self.format_symbol(symbol)
                logger.info(f"[Binance Futures] 获取最优挂单价格，交易对: {formatted_symbol}")
            else:
                logger.info("[Binance Futures] 获取所有交易对的最优挂单价格")
            
            # 调用REST API接口
            response = self._rest.symbol_order_book_ticker(symbol=formatted_symbol)
            
            # 获取响应数据
            data = response.data()
            
            # 处理响应数据
            if isinstance(data, list):
                # 如果返回的是列表，直接转换每个元素为字典
                tickers = [self._ensure_dict(item) for item in data]
            else:
                # 如果返回的是单个对象，转换为字典并包装为列表
                tickers = [self._ensure_dict(data)]
            
            logger.info(f"[Binance Futures] 成功获取最优挂单价格，返回 {len(tickers)} 条数据")
            return tickers
            
        except Exception as e:
            logger.error(f"[Binance Futures] 获取最优挂单价格失败: {e}")
            raise

    def change_initial_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """
        修改初始杠杆倍数
        
        该接口用于修改指定交易对的初始杠杆倍数。
        
        Args:
            symbol: 交易对符号，如 'BTC' 或 'BTCUSDT'
            leverage: 新的杠杆倍数（1-125）
            
        Returns:
            修改后的杠杆信息
        {
            "symbol": "BTCUSDT", // 交易对
            "leverage": 10, // 新的杠杆倍数
            "maxNotionalValue": "1000000" // 最大名义价值
        }
        Raises:
            RuntimeError: 如果SDK不可用
            ValueError: 如果参数不符合要求
            Exception: 如果API调用失败
        """
        try:
            # 验证参数
            if not symbol:
                raise ValueError("交易对不能为空")
            
            if not isinstance(leverage, int) or leverage < 1 or leverage > 125:
                raise ValueError("杠杆倍数必须是1-125之间的整数")
            
            # 格式化交易对
            formatted_symbol = self.format_symbol(symbol)
            logger.info(f"[Binance Futures] 修改初始杠杆，交易对: {formatted_symbol}，杠杆倍数: {leverage}")
            
            # 调用REST API接口
            response = self._rest.change_initial_leverage(symbol=formatted_symbol, leverage=leverage)
            
            # 获取响应数据并转换为字典
            data = self._ensure_dict(response.data())
            
            logger.info(f"[Binance Futures] 成功修改初始杠杆，交易对: {formatted_symbol}，新杠杆: {data.get('leverage')}")
            return data
            
        except ValueError as ve:
            logger.error(f"[Binance Futures] 修改初始杠杆参数错误: {ve}")
            raise
        except Exception as e:
            logger.error(f"[Binance Futures] 修改初始杠杆失败: {e}")
            raise

    def change_margin_isolated(self, symbol: str) -> Dict[str, Any]:
        """
        变换为逐仓模式

        该接口用于将指定交易对的保证金模式变换为逐仓模式（ISOLATED）。

        Args:
            symbol: 交易对符号，如 'BTC' 或 'BTCUSDT'

        Returns:
            修改后的保证金模式信息
        {
            "code": 200,
            "msg": "success"
        }
        Raises:
            RuntimeError: 如果SDK不可用
            ValueError: 如果参数不符合要求
            Exception: 如果API调用失败
        """
        try:
            # 验证参数
            if not symbol:
                raise ValueError("交易对不能为空")

            # 格式化交易对
            formatted_symbol = self.format_symbol(symbol)
            logger.info(f"[Binance Futures] 变换为逐仓模式，交易对: {formatted_symbol}")

            # 调用REST API接口，使用ISOLATED作为margin_type
            response = self._rest.change_margin_type(
                symbol=formatted_symbol,
                margin_type=ChangeMarginTypeMarginTypeEnum["ISOLATED"].value
            )

            # 获取响应数据并转换为字典
            data = self._ensure_dict(response.data())

            # 解析返回状态
            code = data.get('code')
            msg = data.get('msg', '')

            if code == 200:
                logger.info(f"[Binance Futures] 成功变换为逐仓模式，交易对: {formatted_symbol}，响应: {msg}")
            else:
                logger.warning(f"[Binance Futures] 变换逐仓模式返回非200状态码，交易对: {formatted_symbol}，code: {code}，msg: {msg}")

            return data

        except ValueError as ve:
            logger.error(f"[Binance Futures] 变换逐仓模式参数错误: {ve}")
            raise
        except Exception as e:
            logger.error(f"[Binance Futures] 变换逐仓模式失败: {e}")
            raise

    # ============ 交易方法 ============
    
    @staticmethod
    def _serialize_params(params: Dict[str, Any]) -> Dict[str, Any]:
        """
        将参数字典中的枚举值转换为可序列化的格式
        
        Args:
            params: 参数字典
            
        Returns:
            序列化后的参数字典
        """
        serializable_params = {}
        for key, value in params.items():
            if hasattr(value, 'value'):
                serializable_params[key] = str(value.value)
            elif hasattr(value, '__dict__'):
                try:
                    serializable_params[key] = str(value)
                except:
                    serializable_params[key] = repr(value)
            else:
                serializable_params[key] = value
        return serializable_params
    
    @staticmethod
    def _extract_response_type(response_or_exception: Any) -> str:
        """
        从响应对象或异常中提取状态码
        
        Args:
            response_or_exception: 响应对象或异常对象
            
        Returns:
            状态码字符串
        """
        if hasattr(response_or_exception, 'status_code'):
            return str(response_or_exception.status_code)
        elif hasattr(response_or_exception, 'status'):
            return str(response_or_exception.status)
        elif hasattr(response_or_exception, 'code'):
            return str(response_or_exception.code)
        else:
            error_type = type(response_or_exception).__name__
            if any(keyword in error_type for keyword in ['4', 'BadRequest', 'Unauthorized', 'Forbidden', 'NotFound']):
                return "4XX"
            elif any(keyword in error_type for keyword in ['5', 'Server']):
                return "5XX"
            return "ERROR"
    
    def _log_trade(self, db, method_name: str, trade_mode: str, order_params: Dict[str, Any],
                   response_dict: Dict[str, Any], response_type: str, error_context: Optional[str],
                   model_id: Optional[str] = None, conversation_id: Optional[str] = None,
                   trade_id: Optional[str] = None) -> None:
        """
        记录交易日志到数据库
        
        Args:
            db: 数据库实例（可以是 BinanceTradeLogsDatabase 或 Database 实例，为了向后兼容）
            method_name: 方法名称
            trade_mode: 交易模式 ('test' 或 'real')
            order_params: 订单参数字典
            response_dict: 响应数据字典
            response_type: 响应状态码
            error_context: 错误上下文信息
            model_id: 模型ID
            conversation_id: 对话ID
            trade_id: 交易ID
        """
        if not (db and method_name):
            return
        
        try:
            serializable_params = self._serialize_params(order_params)
            # 检查 db 是否有 add_binance_trade_log 方法（BinanceTradeLogsDatabase 或 Database 实例）
            if hasattr(db, 'add_binance_trade_log'):
                db.add_binance_trade_log(
                    model_id=model_id,
                    conversation_id=conversation_id,
                    trade_id=trade_id,
                    type=trade_mode,
                    method_name=method_name,
                    param=serializable_params,
                    response_context=response_dict,
                    response_type=response_type,
                    error_context=error_context
                )
            else:
                # 向后兼容：如果 db 没有 add_binance_trade_log 方法，尝试创建 BinanceTradeLogsDatabase 实例
                from trade.common.database.database_binance_trade_logs import BinanceTradeLogsDatabase
                if hasattr(db, '_pool'):
                    binance_trade_logs_db = BinanceTradeLogsDatabase(pool=db._pool)
                    binance_trade_logs_db.add_binance_trade_log(
                        model_id=model_id,
                        conversation_id=conversation_id,
                        trade_id=trade_id,
                        type=trade_mode,
                        method_name=method_name,
                        param=serializable_params,
                        response_context=response_dict,
                        response_type=response_type,
                        error_context=error_context
                    )
        except Exception as log_err:
            logger.warning(f"[Binance Futures] 记录日志失败: {log_err}")
    
    def _execute_order(self, order_params: Dict[str, Any], context: str = "交易", 
                      model_id: Optional[str] = None, conversation_id: Optional[str] = None,
                      trade_id: Optional[str] = None, method_name: str = "", db = None, **kwargs) -> Dict[str, Any]:
        """
        执行订单的统一方法，根据配置选择使用测试接口或真实交易接口
        
        Args:
            order_params: 订单参数字典（包含完整的订单参数）
            context: 上下文信息，用于日志记录
            model_id: 模型ID (UUID字符串)，用于日志记录
            conversation_id: 对话ID (UUID字符串)，用于日志记录
            trade_id: 交易ID (UUID字符串)，用于日志记录
            method_name: 方法名称，用于日志记录
            db: 数据库实例，用于记录日志
            
        Returns:
            订单响应数据
            {
 	            "clientOrderId": "testOrder", // 用户自定义的订单号
 	            "cumQty": "0",
 	            "cumQuote": "0", // 成交金额
 	            "executedQty": "0", // 成交量
 	            "orderId": 22542179, // 系统订单号
 	            "avgPrice": "0.00000",	// 平均成交价
 	            "origQty": "10", // 原始委托数量
 	            "price": "0", // 委托价格
 	            "reduceOnly": false, // 仅减仓
 	            "side": "SELL", // 买卖方向
 	            "positionSide": "SHORT", // 持仓方向
 	            "status": "NEW", // 订单状态
 	            "stopPrice": "0", // 触发价，对`TRAILING_STOP_MARKET`无效
 	            "closePosition": false,   // 是否条件全平仓
 	            "symbol": "BTCUSDT", // 交易对
 	            "timeInForce": "GTD", // 有效方法
 	            "type": "TRAILING_STOP_MARKET", // 订单类型
 	            "origType": "TRAILING_STOP_MARKET",  // 触发前订单类型
 	            "activatePrice": "9020", // 跟踪止损激活价格, 仅`TRAILING_STOP_MARKET` 订单返回此字段
  	            "priceRate": "0.3",	// 跟踪止损回调比例, 仅`TRAILING_STOP_MARKET` 订单返回此字段
 	            "updateTime": 1566818724722, // 更新时间
 	            "workingType": "CONTRACT_PRICE", // 条件价格触发类型
 	            "priceProtect": false,            // 是否开启条件单触发保护
 	            "priceMatch": "NONE",              //盘口价格下单模式
 	            "selfTradePreventionMode": "NONE", //订单自成交保护模式
 	            "goodTillDate": 1693207680000      //订单TIF为GTD时的自动取消时间
            }
        """
        # 【交易模式切换】根据配置选择使用测试接口或真实交易接口
        # 如果kwargs中传递了trade_mode，优先使用传递的值，否则使用全局配置
        trade_mode = kwargs.pop('trade_mode', None)
        if trade_mode is None:
            trade_mode = getattr(app_config, 'BINANCE_TRADE_MODE', 'test').lower()
        else:
            trade_mode = str(trade_mode).lower()
        
        # 初始化响应相关变量
        response = None
        response_dict = {}
        response_type = "200"  # 默认成功状态码
        error_context = None
        
        try:
            if trade_mode == 'test':
                # 使用测试接口（不会真实下单）
                logger.info(f"[Binance Futures] [{context}] 使用测试接口下单（不会真实成交）")
                
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
                
                # 构建测试参数，统一使用与market_trade相同的方式
                test_params = {
                    "symbol": order_params.get("symbol"),
                    "side": test_side,
                    "type": "MARKET",  # 测试订单统一使用MARKET类型
                }
                
                # 添加quantity参数（必填，默认100）
                if "quantity" in order_params:
                    test_params["quantity"] = order_params["quantity"]
                else:
                    # 无论是否是平仓操作，都添加默认quantity=100
                    test_params["quantity"] = 100
                
                # 添加其他可能需要的参数
                # 注意：测试模式下使用MARKET类型订单，不能同时设置close_position=true
                # if "close_position" in order_params:
                #     test_params["close_position"] = order_params["close_position"]
                if "position_side" in order_params:
                    test_params["position_side"] = order_params["position_side"]
                
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
            
            # 将响应数据转换为字典
            response_dict = self._flatten_to_dicts(data, response_context)[0] if data else {}
            
            # 尝试从响应对象中获取状态码
            if response and hasattr(response, 'status_code'):
                response_type = str(response.status_code)
            elif response and hasattr(response, 'status'):
                response_type = str(response.status)
            else:
                response_type = "200"  # 默认成功
            
        except Exception as e:
            # 捕获异常，提取状态码和错误信息
            error_context = str(e)
            logger.error(f"[Binance Futures] [{context}] 订单执行失败: {e}", exc_info=True)
            
            # 尝试从异常中提取状态码
            if hasattr(e, 'status_code'):
                response_type = str(e.status_code)
            elif hasattr(e, 'status'):
                response_type = str(e.status)
            elif hasattr(e, 'code'):
                response_type = str(e.code)
            else:
                # 根据异常类型推断状态码
                error_type = type(e).__name__
                if '4' in error_type or 'BadRequest' in error_type or 'Unauthorized' in error_type or 'Forbidden' in error_type or 'NotFound' in error_type:
                    response_type = "4XX"
                elif '5' in error_type or 'Server' in error_type:
                    response_type = "5XX"
                else:
                    response_type = "ERROR"
            
            # 记录错误响应（如果有的话）
            try:
                if hasattr(e, 'response') and e.response:
                    error_response = getattr(e.response, 'data', None) or getattr(e.response, 'text', None) or str(e.response)
                    if error_response and error_response != error_context:
                        error_context = f"{error_context} | Response: {error_response}"
            except:
                pass
            
            # 记录日志后再重新抛出异常
            self._log_trade(db, method_name, trade_mode, order_params, {}, response_type,
                          error_context, model_id, conversation_id, trade_id)
            raise
        
        # 记录成功日志
        self._log_trade(db, method_name, trade_mode, order_params, response_dict, response_type,
                      error_context, model_id, conversation_id, trade_id)
        
        return response_dict

    def _execute_algo_order(self, method_name: str, context: str, formatted_symbol: str, side: str, order_type: str, algo_params: dict, model_id: Optional[str] = None, conversation_id: Optional[str] = None, trade_id: Optional[str] = None, db = None) -> Dict[str, Any]:
        """
        执行算法订单的辅助方法 - 封装new_algo_order的调用逻辑
        
        Args:
            method_name: 调用该方法的交易方法名
            context: 交易上下文描述
            formatted_symbol: 格式化后的交易对
            side: 交易方向
            order_type: 订单类型
            algo_params: 算法订单参数
            model_id: 模型ID
            conversation_id: 对话ID
            trade_id: 交易ID
            db: 数据库实例
        Returns:
            订单响应数据
        """
        try:
            from binance_sdk_derivatives_trading_usds_futures.rest_api.models import NewAlgoOrderSideEnum
            
            # 确保algo_type为CONDITIONAL
            algo_params["algo_type"] = "CONDITIONAL"
            # 设置基本参数
            algo_params["symbol"] = formatted_symbol
            algo_params["side"] = NewAlgoOrderSideEnum[side.upper()].value if NewAlgoOrderSideEnum else side.upper()
            algo_params["type"] = order_type.upper()
            
            # 调用new_algo_order方法
            logger.info(f"[Binance Futures] {context}使用new_algo_order方法，参数: {algo_params}")
            response = self._client.rest_api.new_algo_order(**algo_params)
            
            # 处理响应
            data = response.data()
            logger.info(f"[Binance Futures] {context}成功: {data}")
            response_dict = self._flatten_to_dicts(data, "new_algo_order")[0] if data else {}
            
            # 记录成功日志
            response_type = self._extract_response_type(response)
            self._log_trade(db, method_name, 'real', algo_params, response_dict, response_type,
                          None, model_id, conversation_id, trade_id)
            
            return response_dict
        except Exception as exc:
            logger.error(f"[Binance Futures] {context}失败: {exc}", exc_info=True)
            
            # 记录错误日志
            error_context = str(exc)
            response_type = self._extract_response_type(exc)
            self._log_trade(db, method_name, 'real', algo_params, {}, response_type,
                          error_context, model_id, conversation_id, trade_id)
            
            raise

    # ============ 交易订单方法 ============
    # 提供各种类型的交易订单功能：止损、止盈、跟踪买入、平仓等
    
    def _validate_quantity(self, quantity: float) -> None:
        """验证订单数量必须大于0"""
        if quantity <= 0:
            raise ValueError(f"quantity参数必须大于0，当前值: {quantity}")
    
    def _get_symbol_precision(self, symbol: str) -> Dict[str, float]:
        """
        获取交易对的精度要求（stepSize和tickSize）
        
        Args:
            symbol: 交易对符号
            
        Returns:
            包含stepSize和tickSize的字典
        """
        import time
        
        # 检查缓存是否有效
        current_time = time.time()
        if (current_time - self._cache_timestamp) < self._cache_ttl and symbol in self._symbol_precision_cache:
            return self._symbol_precision_cache[symbol]
        
        try:
            # 获取交易所信息
            response = self._rest.exchange_information()
            data = response.data()
            
            # 解析symbols列表
            symbols_data = data.get("symbols", []) if isinstance(data, dict) else []
            
            # 查找目标交易对
            symbol_upper = symbol.upper()
            for symbol_info in symbols_data:
                symbol_name = symbol_info.get("symbol", "")
                if symbol_name.upper() == symbol_upper:
                    # 提取filters
                    filters = symbol_info.get("filters", [])
                    step_size = None
                    tick_size = None
                    
                    for filter_item in filters:
                        filter_type = filter_item.get("filterType", "")
                        if filter_type == "LOT_SIZE":
                            step_size_str = filter_item.get("stepSize", "1")
                            step_size = float(step_size_str)
                        elif filter_type == "PRICE_FILTER":
                            tick_size_str = filter_item.get("tickSize", "0.01")
                            tick_size = float(tick_size_str)
                    
                    # 如果找到了精度信息，缓存并返回
                    if step_size is not None or tick_size is not None:
                        precision_info = {
                            "stepSize": step_size if step_size is not None else 1.0,
                            "tickSize": tick_size if tick_size is not None else 0.01
                        }
                        self._symbol_precision_cache[symbol] = precision_info
                        self._cache_timestamp = current_time
                        logger.debug(f"[Binance Futures] 获取 {symbol} 精度: stepSize={precision_info['stepSize']}, tickSize={precision_info['tickSize']}")
                        return precision_info
            
            # 如果没找到，使用默认值
            logger.warning(f"[Binance Futures] 未找到 {symbol} 的精度信息，使用默认值")
            default_precision = {"stepSize": 1.0, "tickSize": 0.01}
            self._symbol_precision_cache[symbol] = default_precision
            return default_precision
            
        except Exception as e:
            logger.warning(f"[Binance Futures] 获取 {symbol} 精度信息失败: {e}，使用默认值")
            default_precision = {"stepSize": 1.0, "tickSize": 0.01}
            if symbol not in self._symbol_precision_cache:
                self._symbol_precision_cache[symbol] = default_precision
            return default_precision
    
    def _adjust_quantity_precision(self, quantity: float, symbol: str) -> float:
        """
        调整订单数量精度，确保符合 Binance 要求
        
        Args:
            quantity: 原始数量
            symbol: 交易对符号
            
        Returns:
            调整后的数量（根据stepSize精度要求）
        """
        try:
            # 获取交易对的stepSize
            precision_info = self._get_symbol_precision(symbol)
            step_size = precision_info.get("stepSize", 1.0)
            
            # 如果stepSize >= 1，说明数量必须是整数
            if step_size >= 1.0:
                return float(int(quantity / step_size) * int(step_size))
            
            # 计算精度位数（stepSize的小数位数）
            step_size_str = f"{step_size:.10f}".rstrip('0').rstrip('.')
            if '.' in step_size_str:
                precision = len(step_size_str.split('.')[1])
            else:
                precision = 0
            
            # 根据stepSize调整数量
            # 例如：stepSize=0.1，则数量必须是0.1的倍数
            adjusted = round(quantity / step_size) * step_size
            
            # 使用计算出的精度进行四舍五入
            return round(adjusted, precision)
            
        except Exception as e:
            logger.warning(f"[Binance Futures] 调整数量精度失败: {e}，使用保守策略")
            # 如果获取精度失败，使用保守的精度策略
            quantity_str = f"{quantity:.10f}".rstrip('0').rstrip('.')
            if '.' in quantity_str:
                decimal_places = len(quantity_str.split('.')[1])
            else:
                decimal_places = 0
            
            # 使用保守的精度（最多3位小数）
            precision = min(3, decimal_places)
            return round(quantity, precision)
    
    def _adjust_price_precision(self, price: float, symbol: str) -> float:
        """
        调整订单价格精度，确保符合 Binance 要求
        
        Args:
            price: 原始价格
            symbol: 交易对符号
            
        Returns:
            调整后的价格（根据tickSize精度要求）
        """
        try:
            # 获取交易对的tickSize
            precision_info = self._get_symbol_precision(symbol)
            tick_size = precision_info.get("tickSize", 0.01)
            
            # 如果tickSize >= 1，说明价格必须是整数
            if tick_size >= 1.0:
                return float(int(price / tick_size) * int(tick_size))
            
            # 计算精度位数（tickSize的小数位数）
            tick_size_str = f"{tick_size:.10f}".rstrip('0').rstrip('.')
            if '.' in tick_size_str:
                precision = len(tick_size_str.split('.')[1])
            else:
                precision = 0
            
            # 根据tickSize调整价格
            # 例如：tickSize=0.01，则价格必须是0.01的倍数
            adjusted = round(price / tick_size) * tick_size
            
            # 使用计算出的精度进行四舍五入
            return round(adjusted, precision)
            
        except Exception as e:
            logger.warning(f"[Binance Futures] 调整价格精度失败: {e}，使用保守策略")
            # 如果获取精度失败，使用保守的精度策略
            price_str = f"{price:.10f}".rstrip('0').rstrip('.')
            if '.' in price_str:
                decimal_places = len(price_str.split('.')[1])
            else:
                decimal_places = 0
            
            # 使用保守的精度（最多2位小数）
            precision = min(2, decimal_places)
            return round(price, precision)
    
    def _validate_position_side(self, position_side: Optional[str]) -> Optional[str]:
        """
        验证并规范化position_side参数
        
        Args:
            position_side: 持仓方向
            
        Returns:
            规范化后的持仓方向（大写）或None
            
        Raises:
            ValueError: 如果position_side值不合法
        """
        if position_side is not None:
            position_side_upper = position_side.upper()
            if position_side_upper not in ["LONG", "SHORT"]:
                raise ValueError(f"position_side参数值必须是'LONG'或'SHORT'，当前值: {position_side}")
            return position_side_upper
        return None
    
    def _validate_conditional_order_params(self, order_type: str, price: Optional[float], 
                                          stop_price: Optional[float], 
                                          require_price: bool = True) -> None:
        """
        验证条件订单参数（止损/止盈订单）
        
        Args:
            order_type: 订单类型
            price: 订单价格
            stop_price: 触发价格
            require_price: 是否需要price参数
            
        Raises:
            ValueError: 如果参数验证失败
        """
        order_type_upper = order_type.upper()
        if order_type_upper in ["STOP", "TAKE_PROFIT"]:
            if require_price and price is None:
                raise ValueError(f"{order_type_upper}订单必须提供price参数")
            if stop_price is None:
                raise ValueError(f"{order_type_upper}订单必须提供stop_price参数")
        elif order_type_upper in ["STOP_MARKET", "TAKE_PROFIT_MARKET"]:
            if stop_price is None:
                raise ValueError(f"{order_type_upper}订单必须提供stop_price参数")
        else:
            raise ValueError(f"不支持的订单类型: {order_type}")
    
    def _build_order_params(self, formatted_symbol: str, side: str, order_type: str,
                           quantity: Optional[float] = None, price: Optional[float] = None,
                           stop_price: Optional[float] = None, position_side: Optional[str] = None,
                           close_position: bool = False, **kwargs) -> Dict[str, Any]:
        """
        构建订单参数字典
        
        Args:
            formatted_symbol: 格式化后的交易对
            side: 交易方向
            order_type: 订单类型
            quantity: 订单数量
            price: 订单价格
            stop_price: 触发价格
            position_side: 持仓方向
            close_position: 是否平仓
            **kwargs: 其他可选参数
            
        Returns:
            订单参数字典
        """
        order_params = {
            "symbol": formatted_symbol,
            "side": NewOrderSideEnum[side.upper()].value if NewOrderSideEnum else side.upper(),
            "type": order_type.upper(),
        }
        
        if quantity is not None:
            # 调整数量精度，确保符合 Binance 要求，然后转换为整数
            adjusted_quantity = self._adjust_quantity_precision(quantity, formatted_symbol)
            order_params["quantity"] = int(adjusted_quantity)  # 确保quantity是整数
        
        if close_position:
            order_params["close_position"] = True
        
        if position_side:
            order_params["position_side"] = position_side
        
        if stop_price is not None:
            # 调整触发价格精度，确保符合 Binance 要求
            order_params["stop_price"] = self._adjust_price_precision(stop_price, formatted_symbol)
        
        if price is not None:
            # 调整价格精度，确保符合 Binance 要求
            order_params["price"] = self._adjust_price_precision(price, formatted_symbol)
            order_params["time_in_force"] = kwargs.get("time_in_force", "GTC")
        
        order_params.update(kwargs)
        return order_params
    
    def _build_algo_params(self, quantity: Optional[float] = None, price: Optional[float] = None,
                          stop_price: Optional[float] = None, position_side: Optional[str] = None,
                          close_position: bool = False, **kwargs) -> Dict[str, Any]:
        """
        构建算法订单参数字典
        
        Args:
            quantity: 订单数量
            price: 订单价格
            stop_price: 触发价格
            position_side: 持仓方向
            close_position: 是否平仓
            **kwargs: 其他可选参数
            
        Returns:
            算法订单参数字典
        """
        algo_params = {}
        
        if quantity is not None:
            # 确保quantity是整数
            algo_params["quantity"] = int(float(quantity))
        
        if stop_price is not None:
            algo_params["trigger_price"] = stop_price
        
        if position_side:
            algo_params["position_side"] = position_side
        
        if price is not None:
            algo_params["price"] = price
            algo_params["time_in_force"] = kwargs.get("time_in_force", "GTC")
        
        if close_position:
            algo_params["close_position"] = True
        
        algo_params.update(kwargs)
        return algo_params
    
    def stop_loss_trade(self, symbol: str, side: str, quantity: float, order_type: str = "STOP", price: Optional[float] = None, stop_price: Optional[float] = None, position_side: Optional[str] = None, model_id: Optional[str] = None, conversation_id: Optional[str] = None, trade_id: Optional[str] = None, db = None, **kwargs) -> Dict[str, Any]:
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
            quantity: 订单数量（必填，必须大于0）
            order_type: 订单类型，'STOP_MARKET'或'STOP'（默认）
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
        self._validate_quantity(quantity)
        order_type_upper = order_type.upper()
        self._validate_conditional_order_params(order_type_upper, price, stop_price, 
                                                require_price=(order_type_upper == "STOP"))
        
        logger.info(f"[Binance Futures] 开始止损交易，交易对: {symbol}, 方向: {side}, 类型: {order_type_upper}, 持仓方向: {position_side}")
        
        try:
            formatted_symbol = self.format_symbol(symbol)
            position_side = self._validate_position_side(position_side)
            # 如果kwargs中传递了trade_mode，优先使用传递的值，否则使用全局配置
            trade_mode = kwargs.pop('trade_mode', None)
            if trade_mode is None:
                trade_mode = getattr(app_config, 'BINANCE_TRADE_MODE', 'test').lower()
            else:
                trade_mode = str(trade_mode).lower()
            
            if trade_mode == 'test':
                order_params = self._build_order_params(
                    formatted_symbol, side, order_type_upper, quantity, price, stop_price,
                    position_side, **kwargs
                )
                return self._execute_order(order_params, context="止损交易",
                                         model_id=model_id, conversation_id=conversation_id,
                                         trade_id=trade_id, method_name="stop_loss_trade", db=db, trade_mode=trade_mode)
            else:
                algo_params = self._build_algo_params(
                    quantity, price, stop_price, position_side, **kwargs
                )
                return self._execute_algo_order(
                    method_name="stop_loss_trade",
                    context="止损交易",
                    formatted_symbol=formatted_symbol,
                    side=side,
                    order_type=order_type_upper,
                    algo_params=algo_params,
                    model_id=model_id,
                    conversation_id=conversation_id,
                    trade_id=trade_id,
                    db=db
                )
        except Exception as exc:
            logger.error(f"[Binance Futures] 止损交易失败: {exc}", exc_info=True)
            raise

    def take_profit_trade(self, symbol: str, side: str, quantity: float, order_type: str = "TAKE_PROFIT", price: Optional[float] = None, stop_price: Optional[float] = None, position_side: Optional[str] = None, model_id: Optional[str] = None, conversation_id: Optional[str] = None, trade_id: Optional[str] = None, db = None, **kwargs) -> Dict[str, Any]:
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
            quantity: 订单数量（必填）
            order_type: 订单类型，'TAKE_PROFIT_MARKET'或'TAKE_PROFIT'（默认）
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
        self._validate_quantity(quantity)
        order_type_upper = order_type.upper()
        self._validate_conditional_order_params(order_type_upper, price, stop_price,
                                                require_price=(order_type_upper == "TAKE_PROFIT"))
        
        logger.info(f"[Binance Futures] 开始止盈交易，交易对: {symbol}, 方向: {side}, 类型: {order_type_upper}, 持仓方向: {position_side}")
        
        try:
            formatted_symbol = self.format_symbol(symbol)
            position_side = self._validate_position_side(position_side)
            # 如果kwargs中传递了trade_mode，优先使用传递的值，否则使用全局配置
            trade_mode = kwargs.pop('trade_mode', None)
            if trade_mode is None:
                trade_mode = getattr(app_config, 'BINANCE_TRADE_MODE', 'test').lower()
            else:
                trade_mode = str(trade_mode).lower()
            
            if trade_mode == 'test':
                order_params = self._build_order_params(
                    formatted_symbol, side, order_type_upper, quantity, price, stop_price,
                    position_side, **kwargs
                )
                return self._execute_order(order_params, context="止盈交易",
                                         model_id=model_id, conversation_id=conversation_id,
                                         trade_id=trade_id, method_name="take_profit_trade", db=db, trade_mode=trade_mode)
            else:
                algo_params = self._build_algo_params(
                    quantity, price, stop_price, position_side, **kwargs
                )
                return self._execute_algo_order(
                    method_name="take_profit_trade",
                    context="止盈交易",
                    formatted_symbol=formatted_symbol,
                    side=side,
                    order_type=order_type_upper,
                    algo_params=algo_params,
                    model_id=model_id,
                    conversation_id=conversation_id,
                    trade_id=trade_id,
                    db=db
                )
        except Exception as exc:
            logger.error(f"[Binance Futures] 止盈交易失败: {exc}", exc_info=True)
            raise

    def market_trade(self, symbol: str, side: str, quantity: float, order_type: str = "MARKET", position_side: Optional[str] = None, new_order_resp_type: str = "RESULT", model_id: Optional[str] = None, conversation_id: Optional[str] = None, trade_id: Optional[str] = None, db = None, **kwargs) -> Dict[str, Any]:
        """
        市场价格交易- 使用指定订单类型
        
        【position_side参数说明】
        在双向持仓模式下，此参数为必填项，用于指定持仓方向：
        - "LONG": 多头持仓（做多）
        - "SHORT": 空头持仓（做空）
        
        在单向持仓模式下，此参数可选，默认为"BOTH"。
        
        Args:
            symbol: 交易对符号，如 'BTCUSDT'
            side: 交易方向，'BUY'或'SELL'
            quantity: 订单数量（必填，必须大于0）
            order_type: 订单类型，默认"MARKET"
            position_side: 持仓方向，'LONG'（多）或'SHORT'（空），双向持仓模式下必填
            new_order_resp_type: 订单响应类型，默认"RESULT"
            **kwargs: 其他可选参数
            
        Returns:
            订单响应数据
        """
        self._validate_quantity(quantity)
        
        logger.info(f"[Binance Futures] 开始市场交易，交易对: {symbol}, 方向: {side}, 数量: {quantity}, 订单类型: {order_type}, 持仓方向: {position_side}")
        
        try:
            formatted_symbol = self.format_symbol(symbol)
            position_side = self._validate_position_side(position_side)
            
            order_params = self._build_order_params(
                formatted_symbol, side, order_type, quantity, position_side=position_side, **kwargs
            )
            order_params["newOrderRespType"] = new_order_resp_type
            
            return self._execute_order(order_params, context="市场交易",
                                     model_id=model_id, conversation_id=conversation_id,
                                     trade_id=trade_id, method_name="market_trade", db=db, **kwargs)
        except Exception as exc:
            logger.error(f"[Binance Futures] 市场交易失败: {exc}", exc_info=True)
            raise

    def close_position_trade(self, symbol: str, side: str, quantity: float, order_type: str="STOP_MARKET", stop_price: Optional[float] = None, position_side: Optional[str] = None, model_id: Optional[str] = None, conversation_id: Optional[str] = None, trade_id: Optional[str] = None, db = None, **kwargs) -> Dict[str, Any]:
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
            quantity: 订单数量（必填）
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
        self._validate_quantity(quantity)
        
        logger.info(f"[Binance Futures] 开始平仓交易，交易对: {symbol}, 方向: {side}, 类型: {order_type}, 持仓方向: {position_side}")
        
        try:
            formatted_symbol = self.format_symbol(symbol)
            position_side = self._validate_position_side(position_side)
            
            # 【双开模式校验】验证side和position_side的组合是否合法
            if position_side:
                side_upper = side.upper()
                if position_side == "LONG" and side_upper == "BUY":
                    raise ValueError(f"双开模式下，LONG方向上不支持BUY操作。平多仓应使用SELL，当前side={side}, position_side={position_side}")
                if position_side == "SHORT" and side_upper == "SELL":
                    raise ValueError(f"双开模式下，SHORT方向上不支持SELL操作。平空仓应使用BUY，当前side={side}, position_side={position_side}")
            
            # 如果kwargs中传递了trade_mode，优先使用传递的值，否则使用全局配置
            trade_mode = kwargs.pop('trade_mode', None)
            if trade_mode is None:
                trade_mode = getattr(app_config, 'BINANCE_TRADE_MODE', 'test').lower()
            else:
                trade_mode = str(trade_mode).lower()
            order_type_upper = order_type.upper()
            
            if trade_mode == 'test':
                order_params = self._build_order_params(
                    formatted_symbol, side, order_type_upper, position_side=position_side,
                    stop_price=stop_price, close_position=True, **kwargs
                )
                return self._execute_order(order_params, context="平仓交易",
                                          model_id=model_id, conversation_id=conversation_id,
                                          trade_id=trade_id, method_name="close_position_trade", db=db)
            else:
                algo_params = self._build_algo_params(
                    position_side=position_side, stop_price=stop_price,
                    close_position=True, **kwargs
                )
                return self._execute_algo_order(
                    method_name="close_position_trade",
                    context="平仓交易",
                    formatted_symbol=formatted_symbol,
                    side=side,
                    order_type=order_type_upper,
                    algo_params=algo_params,
                    model_id=model_id,
                    conversation_id=conversation_id,
                    trade_id=trade_id,
                    db=db
                )
        except Exception as exc:
            logger.error(f"[Binance Futures] 平仓交易失败: {exc}", exc_info=True)
            raise

    def query_all_algo_orders(self, symbol: str, 
                             model_id: Optional[str] = None, conversation_id: Optional[str] = None, 
                             trade_id: Optional[str] = None, db = None) -> List[Dict[str, Any]]:
        """
        查询指定交易对的所有条件单
        
        Args:
            symbol: 交易对符号（必填）
            model_id: 模型ID（可选，用于日志记录）
            conversation_id: 对话ID（可选，用于日志记录）
            trade_id: 交易ID（可选，用于日志记录）
            db: 数据库实例（可选，用于日志记录）
        
        Returns:
            条件单列表
        """
        try:
            if not symbol:
                raise ValueError("symbol参数不能为空")
            
            formatted_symbol = self.format_symbol(symbol)
            params = {"symbol": formatted_symbol}
            
            logger.info(f"[Binance Futures] 查询所有条件单，参数: {params}")
            response = self._client.rest_api.query_all_algo_orders(**params)
            
            # 处理响应
            data = response.data()
            logger.info(f"[Binance Futures] 查询所有条件单成功: {data}")
            response_dict = self._flatten_to_dicts(data, "query_all_algo_orders") if data else []
            
            # 记录日志
            response_type = self._extract_response_type(response)
            self._log_trade(db, "query_all_algo_orders", 'real', params, response_dict, response_type,
                          None, model_id, conversation_id, trade_id)
            
            return response_dict if isinstance(response_dict, list) else [response_dict] if response_dict else []
        except Exception as exc:
            logger.error(f"[Binance Futures] 查询所有条件单失败: {exc}", exc_info=True)
            
            # 记录错误日志
            error_context = str(exc)
            response_type = self._extract_response_type(exc)
            self._log_trade(db, "query_all_algo_orders", 'real', params if 'params' in locals() else {}, {}, response_type,
                          error_context, model_id, conversation_id, trade_id)
            
            raise

    def cancel_all_algo_open_orders(self, symbol: str, 
                                    model_id: Optional[str] = None, conversation_id: Optional[str] = None, 
                                    trade_id: Optional[str] = None, db = None) -> Dict[str, Any]:
        """
        取消指定交易对的所有条件单
        
        Args:
            symbol: 交易对符号（必填）
            model_id: 模型ID（可选，用于日志记录）
            conversation_id: 对话ID（可选，用于日志记录）
            trade_id: 交易ID（可选，用于日志记录）
            db: 数据库实例（可选，用于日志记录）
        
        Returns:
            取消条件单响应数据
        """
        try:
            formatted_symbol = self.format_symbol(symbol)
            params = {"symbol": formatted_symbol}
            
            logger.info(f"[Binance Futures] 取消所有条件单，参数: {params}")
            response = self._client.rest_api.cancel_all_algo_open_orders(**params)
            
            # 处理响应
            data = response.data()
            logger.info(f"[Binance Futures] 取消所有条件单成功: {data}")
            response_dict = self._flatten_to_dicts(data, "cancel_all_algo_open_orders")[0] if data else {}
            
            # 记录日志
            response_type = self._extract_response_type(response)
            self._log_trade(db, "cancel_all_algo_open_orders", 'real', params, response_dict, response_type,
                          None, model_id, conversation_id, trade_id)
            
            return response_dict
        except Exception as exc:
            logger.error(f"[Binance Futures] 取消所有条件单失败: {exc}", exc_info=True)
            
            # 记录错误日志
            error_context = str(exc)
            response_type = self._extract_response_type(exc)
            self._log_trade(db, "cancel_all_algo_open_orders", 'real', params if 'params' in locals() else {}, {}, response_type,
                          error_context, model_id, conversation_id, trade_id)
            
            raise
