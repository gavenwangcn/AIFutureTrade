"""Data agent for K-line data synchronization.

This module provides a data agent that can be controlled by async_agent to
synchronize K-line data for multiple symbols across different intervals.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import threading
import urllib.parse
import socket

# 检查Python版本
if sys.version_info < (3, 10):
    raise RuntimeError(
        f"Python 3.10+ is required. Current version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}\n"
        "Please upgrade Python or use Python 3.10+ in your Docker image."
    )

# 添加项目根目录到Python路径（用于Docker容器中运行）
from pathlib import Path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import (
    DERIVATIVES_TRADING_USDS_FUTURES_WS_STREAMS_PROD_URL,
    ConfigurationWebSocketStreams,
    DerivativesTradingUsdsFutures,
)

import common.config as app_config
from common.database_mysql import MySQLDatabase
from market.market_streams import _normalize_kline

logger = logging.getLogger(__name__)

# 支持的K线时间间隔（从配置文件读取，默认7个interval）
# 可以通过环境变量 DATA_AGENT_KLINE_INTERVALS 配置，格式：'1m,5m,15m,1h,4h,1d,1w'
KLINE_INTERVALS = getattr(app_config, 'DATA_AGENT_KLINE_INTERVALS', ['1m', '5m', '15m', '1h', '4h', '1d', '1w'])

# WebSocket连接最大有效期（设置为非常长的时间，确保连接长期运行）
# 注意：K线监听是长期运行的异步任务，不应该主动关闭连接
# 只有在服务关闭或连接出错时才关闭
WS_CONNECTION_MAX_AGE = timedelta(days=365)  # 1年，实际上不会过期


class KlineStreamConnection:
    """单个K线WebSocket连接的管理类。"""
    
    def __init__(self, symbol: str, interval: str, connection: Any, stream: Any, created_at: datetime):
        self.symbol = symbol.upper()
        self.interval = interval
        self.connection = connection
        self.stream = stream
        self.created_at = created_at
        self.is_active = True
    
    def is_expired(self) -> bool:
        """检查连接是否已过期（超过24小时）。"""
        return datetime.now(timezone.utc) - self.created_at > WS_CONNECTION_MAX_AGE
    
    async def close(self) -> None:
        """关闭连接。"""
        if not self.is_active:
            return
        
        try:
            if self.stream:
                await self.stream.unsubscribe()
        except Exception as e:
            logger.debug("[KlineStreamConnection] Error unsubscribing stream: %s", e)
        
        try:
            if self.connection:
                await self.connection.close_connection(close_session=True)
        except Exception as e:
            logger.debug("[KlineStreamConnection] Error closing connection: %s", e)
        
        self.is_active = False


class DataAgentKlineManager:
    """管理所有K线WebSocket连接。
    
    该类负责管理多个交易对的K线数据WebSocket连接，每个交易对支持多个时间间隔（默认7个：1m, 5m, 15m, 1h, 4h, 1d, 1w）。
    interval列表可通过配置文件 config.py 中的 DATA_AGENT_KLINE_INTERVALS 进行配置。
    
    **重要说明：K线监听是长期运行的异步任务**
    - 连接构建完成后会一直保持活跃，持续接收K线消息
    - 不会主动关闭连接（除非服务关闭或连接出错）
    - 所有连接会持续运行，同步K线数据到MySQL数据库
    
    主要功能包括：
    - 客户端初始化和连接管理
    - 流的添加、移除和批量操作
    - 连接状态查询和监控（不主动关闭）
    - K线消息处理和数据库存储
    - 订阅频率控制
    - 连接健康检查（不关闭连接）
    """
    
    # ============================================================================
    # 初始化方法
    # ============================================================================
    
    def __init__(self, db: MySQLDatabase, max_symbols: int = 100, intervals: Optional[List[str]] = None):
        """初始化 DataAgentKlineManager。
        
        Args:
            db: MySQL数据库实例
            max_symbols: 最大symbol数量
            intervals: K线时间间隔列表，如果为None则使用全局配置 KLINE_INTERVALS
        """
        self._db = db
        # 使用传入的intervals或全局配置
        self._intervals = intervals if intervals is not None else KLINE_INTERVALS
        # 每个symbol有多个interval，所以最大连接数 = max_symbols * interval数量
        self._max_connections = max_symbols * len(self._intervals)
        self._max_symbols = max_symbols
        # 客户端将在第一次使用时初始化，避免事件循环冲突
        self._client = None
        # 跟踪活跃连接: {(symbol, interval): KlineStreamConnection}
        self._active_connections: Dict[Tuple[str, str], KlineStreamConnection] = {}
        self._lock = asyncio.Lock()
        
        # WebSocket连接管理配置
        self._connection_max_age = WS_CONNECTION_MAX_AGE
        self._ping_interval = timedelta(minutes=5)  # 每5分钟发送一次ping
        self._reconnect_delay = timedelta(seconds=5)  # 重连延迟
        self._max_subscriptions_per_second = 10  # 每秒最多10个订阅消息
        
        # 跟踪上一次订阅时间，用于控制订阅频率
        self._last_subscription_time = datetime.now(timezone.utc)
        self._subscriptions_in_last_second = 0
        
        # 标记是否正在关闭
        self._is_closing = False
        
        # 启动定期检查任务
        self._check_task = asyncio.create_task(self._periodic_connection_check())
        self._ping_task = asyncio.create_task(self._periodic_ping())
    
    # ============================================================================
    # 客户端管理方法
    # ============================================================================
    
    async def _init_client(self) -> None:
        """初始化WebSocket客户端，确保在事件循环中创建。
        
        该方法采用懒加载策略，只在第一次需要时初始化客户端，避免事件循环冲突。
        如果客户端已存在，则跳过初始化。
        """
        if self._client is None:
            logger.info("[DataAgentKline] 🔧 [初始化客户端] 开始初始化WebSocket客户端...")
            stream_url = os.getenv(
                "STREAM_URL",
                DERIVATIVES_TRADING_USDS_FUTURES_WS_STREAMS_PROD_URL,
            )
            logger.info(
                "[DataAgentKline] 🔧 [初始化客户端] 使用流URL: %s",
                stream_url
            )
            
            configuration_ws_streams = ConfigurationWebSocketStreams(
                stream_url=stream_url
            )
            logger.info(
                "[DataAgentKline] 🔧 [初始化客户端] 创建配置对象完成: %s",
                type(configuration_ws_streams).__name__
            )
            
            self._client = DerivativesTradingUsdsFutures(
                config_ws_streams=configuration_ws_streams
            )
            logger.info(
                "[DataAgentKline] ✅ [初始化客户端] 客户端初始化完成: %s",
                type(self._client).__name__
            )
        else:
            logger.debug(
                "[DataAgentKline] ⏭️  [初始化客户端] 客户端已存在，跳过初始化: %s",
                type(self._client).__name__
            )
    
    # ============================================================================
    # 定期任务方法
    # ============================================================================
    
    async def _periodic_connection_check(self) -> None:
        """初始化客户端，确保在事件循环中创建。"""
        if self._client is None:
            logger.info("[DataAgentKline] 🔧 [初始化客户端] 开始初始化WebSocket客户端...")
            stream_url = os.getenv(
                "STREAM_URL",
                DERIVATIVES_TRADING_USDS_FUTURES_WS_STREAMS_PROD_URL,
            )
            logger.info(
                "[DataAgentKline] 🔧 [初始化客户端] 使用流URL: %s",
                stream_url
            )
            
            configuration_ws_streams = ConfigurationWebSocketStreams(
                stream_url=stream_url
            )
            logger.info(
                "[DataAgentKline] 🔧 [初始化客户端] 创建配置对象完成: %s",
                type(configuration_ws_streams).__name__
            )
            
            self._client = DerivativesTradingUsdsFutures(
                config_ws_streams=configuration_ws_streams
            )
            logger.info(
                "[DataAgentKline] ✅ [初始化客户端] 客户端初始化完成: %s",
                type(self._client).__name__
            )
        else:
                logger.debug(
                    "[DataAgentKline] ⏭️  [初始化客户端] 客户端已存在，跳过初始化: %s",
                    type(self._client).__name__
                )
    
    # ============================================================================
    # 流管理方法 - 分步方法（每个步骤都可以单独测试）
    # ============================================================================
    
    async def step1_init_client(self) -> Dict[str, Any]:
        """步骤1: 初始化客户端。
        
        Returns:
            包含执行结果的字典:
            {
                "success": bool,
                "duration": float,
                "client_type": str,
                "error": Optional[str]
            }
        """
        step_start_time = datetime.now(timezone.utc)
        try:
            logger.info("[DataAgentKline] 🔧 [步骤1] 初始化客户端...")
            
            if self._client is None:
                stream_url = os.getenv(
                    "STREAM_URL",
                    DERIVATIVES_TRADING_USDS_FUTURES_WS_STREAMS_PROD_URL,
                )
                logger.info("[DataAgentKline] 🔧 [步骤1] 使用流URL: %s", stream_url)
                
                configuration_ws_streams = ConfigurationWebSocketStreams(
                    stream_url=stream_url
                )
                logger.info(
                    "[DataAgentKline] 🔧 [步骤1] 创建配置对象完成: %s",
                    type(configuration_ws_streams).__name__
                )
                
                self._client = DerivativesTradingUsdsFutures(
                    config_ws_streams=configuration_ws_streams
                )
                logger.info(
                    "[DataAgentKline] ✅ [步骤1] 客户端初始化完成: %s",
                    type(self._client).__name__
                )
            else:
                logger.debug(
                    "[DataAgentKline] ⏭️  [步骤1] 客户端已存在，跳过初始化: %s",
                    type(self._client).__name__
                )
            
            duration = (datetime.now(timezone.utc) - step_start_time).total_seconds()
            return {
                "success": True,
                "duration": duration,
                "client_type": type(self._client).__name__ if self._client else None,
                "error": None
            }
        except Exception as e:
            duration = (datetime.now(timezone.utc) - step_start_time).total_seconds()
            logger.error(
                "[DataAgentKline] ❌ [步骤1] 客户端初始化失败 (耗时: %.3fs): %s",
                duration, e, exc_info=True
            )
            return {
                "success": False,
                "duration": duration,
                "client_type": None,
                "error": str(e)
            }
    
    async def step2_rate_limit_check(self) -> Dict[str, Any]:
        """步骤2: 检查订阅频率限制。
        
        Returns:
            包含执行结果的字典:
            {
                "success": bool,
                "duration": float,
                "waited": bool,
                "wait_time": Optional[float],
                "error": Optional[str]
            }
        """
        step_start_time = datetime.now(timezone.utc)
        try:
            logger.info("[DataAgentKline] ⏱️  [步骤2] 检查订阅频率限制...")
            
            rate_limit_start_time = datetime.now(timezone.utc)
            current_time = datetime.now(timezone.utc)
            time_since_last_subscription = current_time - self._last_subscription_time
            
            logger.debug(
                "[DataAgentKline] ⏱️  [步骤2] 检查订阅频率: 上次订阅时间=%s, 距今=%.3fs, 当前计数=%s/%s",
                self._last_subscription_time.isoformat(),
                time_since_last_subscription.total_seconds(),
                self._subscriptions_in_last_second,
                self._max_subscriptions_per_second
            )
            
            waited = False
            wait_time = None
            
            # 如果已经过了1秒，重置计数器
            if time_since_last_subscription > timedelta(seconds=1):
                self._last_subscription_time = current_time
                self._subscriptions_in_last_second = 1
                logger.debug("[DataAgentKline] ✅ [步骤2] 频率检查通过，重置计数器")
            else:
                # 如果在1秒内订阅次数已达上限，等待剩余时间
                self._subscriptions_in_last_second += 1
                if self._subscriptions_in_last_second > self._max_subscriptions_per_second:
                    wait_time = timedelta(seconds=1) - time_since_last_subscription
                    wait_seconds = wait_time.total_seconds()
                    logger.info(
                        "[DataAgentKline] ⏳ [步骤2] 达到频率限制 (%s/%s)，等待 %.3fs...",
                        self._subscriptions_in_last_second,
                        self._max_subscriptions_per_second,
                        wait_seconds
                    )
                    await asyncio.sleep(wait_seconds)
                    waited = True
                    # 重置计数器
                    self._last_subscription_time = datetime.now(timezone.utc)
                    self._subscriptions_in_last_second = 1
                    logger.info("[DataAgentKline] ✅ [步骤2] 等待完成，重置计数器")
                else:
                    logger.debug(
                        "[DataAgentKline] ✅ [步骤2] 频率检查通过，当前计数: %s/%s",
                        self._subscriptions_in_last_second,
                        self._max_subscriptions_per_second
                    )
            
            duration = (datetime.now(timezone.utc) - step_start_time).total_seconds()
            return {
                "success": True,
                "duration": duration,
                "waited": waited,
                "wait_time": wait_time.total_seconds() if wait_time else None,
                "error": None
            }
        except Exception as e:
            duration = (datetime.now(timezone.utc) - step_start_time).total_seconds()
            logger.error(
                "[DataAgentKline] ❌ [步骤2] 频率检查失败 (耗时: %.3fs): %s",
                duration, e, exc_info=True
            )
            return {
                "success": False,
                "duration": duration,
                "waited": False,
                "wait_time": None,
                "error": str(e)
            }
    
    async def step3_create_connection(self) -> Dict[str, Any]:
        """步骤3: 创建WebSocket连接。
        
        Returns:
            包含执行结果的字典:
            {
                "success": bool,
                "duration": float,
                "connection": Optional[Any],  # 连接对象（供后续步骤使用）
                "connection_type": Optional[str],  # 连接对象的类型名
                "connection_id": Optional[int],  # 连接对象的ID
                "error": Optional[str]
            }
        """
        step_start_time = datetime.now(timezone.utc)
        connection = None
        try:
            logger.info("[DataAgentKline] 🔌 [步骤3] 创建WebSocket连接...")
            
            if self._client is None:
                raise RuntimeError("客户端未初始化，请先调用 step1_init_client")
            
            logger.debug(
                "[DataAgentKline] 🔌 [步骤3] SDK调用前状态: client=%s, websocket_streams=%s",
                type(self._client).__name__,
                type(self._client.websocket_streams).__name__ if hasattr(self._client, 'websocket_streams') else None
            )
            
            sdk_call_start = datetime.now(timezone.utc)
            logger.debug(
                "[DataAgentKline] 🔌 [步骤3] 开始调用SDK: self._client.websocket_streams.create_connection()"
            )
            
            # 为 create_connection 添加超时保护（最多等待15秒）
            connection = await asyncio.wait_for(
                self._client.websocket_streams.create_connection(),
                timeout=15.0
            )
            
            sdk_call_duration = (datetime.now(timezone.utc) - sdk_call_start).total_seconds()
            duration = (datetime.now(timezone.utc) - step_start_time).total_seconds()
            
            logger.info(
                "[DataAgentKline] ✅ [步骤3] WebSocket连接创建成功 (总耗时: %.3fs, SDK调用耗时: %.3fs, 连接对象: %s, 连接ID: %s)",
                duration, sdk_call_duration,
                type(connection).__name__,
                id(connection) if connection else None
            )
            
            return {
                "success": True,
                "duration": duration,
                "connection": connection,  # 返回连接对象供后续步骤使用
                "connection_type": type(connection).__name__ if connection else None,
                "connection_id": id(connection) if connection else None,
                "error": None
            }
        except asyncio.TimeoutError as e:
            duration = (datetime.now(timezone.utc) - step_start_time).total_seconds()
            logger.error(
                "[DataAgentKline] ❌ [步骤3] SDK调用超时 (耗时: %.3fs, 超时设置: 15s): %s",
                duration, e
            )
            return {
                "success": False,
                "duration": duration,
                "connection": None,
                "connection_type": None,
                "connection_id": None,
                "error": f"Timeout: {str(e)}"
            }
        except Exception as e:
            duration = (datetime.now(timezone.utc) - step_start_time).total_seconds()
            logger.error(
                "[DataAgentKline] ❌ [步骤3] SDK调用异常 (耗时: %.3fs): %s",
                duration, e, exc_info=True
            )
            return {
                "success": False,
                "duration": duration,
                "connection": None,
                "connection_type": None,
                "connection_id": None,
                "error": str(e)
            }
    
    async def step4_register_connection_error_handler(
        self, connection: Any, symbol: str, interval: str
    ) -> Dict[str, Any]:
        """步骤4: 注册连接错误处理器。
        
        Args:
            connection: WebSocket连接对象
            symbol: 交易对符号
            interval: 时间间隔
        
        Returns:
            包含执行结果的字典:
            {
                "success": bool,
                "duration": float,
                "handler_registered": bool,
                "error": Optional[str]
            }
        """
        step_start_time = datetime.now(timezone.utc)
        symbol_upper = symbol.upper()
        try:
            logger.info(
                "[DataAgentKline] 🛡️  [步骤4] 注册连接错误处理器 %s %s...",
                symbol_upper, interval
            )
            
            def connection_error_handler(error: Any) -> None:
                logger.error(
                    "[DataAgentKline] ❌ [连接错误] %s %s 连接错误: %s",
                    symbol_upper, interval, error
                )
                asyncio.create_task(self._remove_broken_connection(symbol_upper, interval))
            
            handler_registered = False
            if hasattr(connection, 'on'):
                try:
                    connection.on("error", connection_error_handler)
                    handler_registered = True
                    logger.info(
                        "[DataAgentKline] ✅ [步骤4] 连接错误处理器注册成功 %s %s",
                        symbol_upper, interval
                    )
                except (AttributeError, TypeError, ValueError) as e:
                    logger.debug(
                        "[DataAgentKline] ⚠️  [步骤4] 连接不支持'error'事件或已注册 %s %s: %s",
                        symbol_upper, interval, e
                    )
                except Exception as e:
                    logger.warning(
                        "[DataAgentKline] ⚠️  [步骤4] 注册连接错误处理器失败（非关键）%s %s: %s",
                        symbol_upper, interval, e
                    )
            else:
                logger.debug(
                    "[DataAgentKline] ⚠️  [步骤4] 连接对象不支持'on'方法 %s %s",
                    symbol_upper, interval
                )
            
            duration = (datetime.now(timezone.utc) - step_start_time).total_seconds()
            return {
                "success": True,
                "duration": duration,
                "handler_registered": handler_registered,
                "error": None
            }
        except Exception as e:
            duration = (datetime.now(timezone.utc) - step_start_time).total_seconds()
            logger.error(
                "[DataAgentKline] ❌ [步骤4] 注册连接错误处理器失败 %s %s (耗时: %.3fs): %s",
                symbol_upper, interval, duration, e, exc_info=True
            )
            return {
                "success": False,
                "duration": duration,
                "handler_registered": False,
                "error": str(e)
            }
    
    async def step5_subscribe_kline_stream(
        self, connection: Any, symbol: str, interval: str
    ) -> Dict[str, Any]:
        """步骤5: 订阅K线流。
        
        Args:
            connection: WebSocket连接对象
            symbol: 交易对符号
            interval: 时间间隔
        
        Returns:
            包含执行结果的字典:
            {
                "success": bool,
                "duration": float,
                "stream": Optional[Any],  # 流对象（供后续步骤使用）
                "stream_type": Optional[str],  # 流对象的类型名
                "stream_id": Optional[int],  # 流对象的ID
                "error": Optional[str]
            }
        """
        step_start_time = datetime.now(timezone.utc)
        symbol_upper = symbol.upper()
        stream = None
        try:
            logger.info(
                "[DataAgentKline] 📡 [步骤5] 订阅K线流 %s %s (symbol=%s, interval=%s)...",
                symbol_upper, interval, symbol.lower(), interval
            )
            
            logger.debug(
                "[DataAgentKline] 📡 [步骤5] SDK调用前状态: connection=%s, connection_id=%s",
                type(connection).__name__ if connection else None,
                id(connection) if connection else None
            )
            
            subscribe_sdk_start = datetime.now(timezone.utc)
            logger.debug(
                "[DataAgentKline] 📡 [步骤5] 开始调用SDK: connection.kline_candlestick_streams(symbol='%s', interval='%s')",
                symbol.lower(), interval
            )
            
            # 为 kline_candlestick_streams 添加超时保护（最多等待15秒）
            stream = await asyncio.wait_for(
                connection.kline_candlestick_streams(
                    symbol=symbol.lower(),
                    interval=interval
                ),
                timeout=15.0
            )
            
            subscribe_sdk_duration = (datetime.now(timezone.utc) - subscribe_sdk_start).total_seconds()
            duration = (datetime.now(timezone.utc) - step_start_time).total_seconds()
            
            logger.info(
                "[DataAgentKline] ✅ [步骤5] K线流订阅成功 %s %s (总耗时: %.3fs, SDK调用耗时: %.3fs, 流对象: %s, 流ID: %s)",
                symbol_upper, interval, duration, subscribe_sdk_duration,
                type(stream).__name__,
                id(stream) if stream else None
            )
            
            return {
                "success": True,
                "duration": duration,
                "stream": stream,  # 返回流对象供后续步骤使用
                "stream_type": type(stream).__name__ if stream else None,
                "stream_id": id(stream) if stream else None,
                "error": None
            }
        except asyncio.TimeoutError as e:
            duration = (datetime.now(timezone.utc) - step_start_time).total_seconds()
            logger.error(
                "[DataAgentKline] ❌ [步骤5] SDK调用超时 %s %s (耗时: %.3fs, 超时设置: 15s): %s",
                symbol_upper, interval, duration, e
            )
            return {
                "success": False,
                "duration": duration,
                "stream": None,
                "stream_type": None,
                "stream_id": None,
                "error": f"Timeout: {str(e)}"
            }
        except Exception as e:
            duration = (datetime.now(timezone.utc) - step_start_time).total_seconds()
            logger.error(
                "[DataAgentKline] ❌ [步骤5] SDK调用异常 %s %s (耗时: %.3fs): %s",
                symbol_upper, interval, duration, e, exc_info=True
            )
            return {
                "success": False,
                "duration": duration,
                "stream": None,
                "stream_type": None,
                "stream_id": None,
                "error": str(e)
            }
    
    async def step6_register_message_handler(
        self, stream: Any, symbol: str, interval: str
    ) -> Dict[str, Any]:
        """步骤6: 注册消息和错误处理器。
        
        Args:
            stream: K线流对象
            symbol: 交易对符号
            interval: 时间间隔
        
        Returns:
            包含执行结果的字典:
            {
                "success": bool,
                "duration": float,
                "message_handler_registered": bool,
                "error_handler_registered": bool,
                "error": Optional[str]
            }
        """
        step_start_time = datetime.now(timezone.utc)
        symbol_upper = symbol.upper()
        try:
            logger.info(
                "[DataAgentKline] 📨 [步骤6] 注册消息和错误处理器 %s %s...",
                symbol_upper, interval
            )
            
            def handler(data: Any) -> None:
                """K线消息处理器，记录消息接收时间，便于排查性能问题。"""
                message_received_time = datetime.now(timezone.utc)
                logger.debug(
                    "[DataAgentKline] 📨 [消息处理] 收到K线消息 %s %s (消息时间: %s)",
                    symbol_upper, interval, message_received_time.isoformat()
                )
                try:
                    task = asyncio.create_task(self._handle_kline_message(symbol_upper, interval, data))
                    logger.debug(
                        "[DataAgentKline] 📨 [消息处理] 已创建异步任务处理消息 %s %s (任务ID: %s)",
                        symbol_upper, interval, id(task)
                    )
                except Exception as e:
                    logger.error(
                        "[DataAgentKline] ❌ [消息处理] 创建异步任务失败 %s %s: %s",
                        symbol_upper, interval, e, exc_info=True
                    )
            
            def stream_error_handler(error: Any) -> None:
                """流错误处理器。"""
                logger.error(
                    "[DataAgentKline] ❌ [流错误] %s %s 流错误: %s",
                    symbol_upper, interval, error
                )
                asyncio.create_task(self._remove_broken_connection(symbol_upper, interval))
            
            message_handler_registered = False
            stream_error_handler_registered = False
            
            try:
                if hasattr(stream, 'on'):
                    stream.on("message", handler)
                    message_handler_registered = True
                    logger.info(
                        "[DataAgentKline] ✅ [步骤6] 消息处理器注册成功 %s %s",
                        symbol_upper, interval
                    )
                else:
                    logger.warning(
                        "[DataAgentKline] ⚠️  [步骤6] 流对象不支持'on'方法 %s %s",
                        symbol_upper, interval
                    )
            except Exception as e:
                logger.error(
                    "[DataAgentKline] ❌ [步骤6] 注册消息处理器失败 %s %s: %s",
                    symbol_upper, interval, e, exc_info=True
                )
            
            # 尝试注册流级别的错误处理器（如果SDK支持）
            try:
                if hasattr(stream, 'on'):
                    stream.on("error", stream_error_handler)
                    stream_error_handler_registered = True
                    logger.info(
                        "[DataAgentKline] ✅ [步骤6] 流错误处理器注册成功 %s %s",
                        symbol_upper, interval
                    )
            except (AttributeError, TypeError, ValueError) as e:
                logger.debug(
                    "[DataAgentKline] ⚠️  [步骤6] 流不支持'error'事件或已注册 %s %s: %s",
                    symbol_upper, interval, e
                )
            except Exception as e:
                logger.warning(
                    "[DataAgentKline] ⚠️  [步骤6] 注册流错误处理器失败（非关键）%s %s: %s",
                    symbol_upper, interval, e
                )
            
            duration = (datetime.now(timezone.utc) - step_start_time).total_seconds()
            return {
                "success": True,
                "duration": duration,
                "message_handler_registered": message_handler_registered,
                "error_handler_registered": stream_error_handler_registered,
                "error": None
            }
        except Exception as e:
            duration = (datetime.now(timezone.utc) - step_start_time).total_seconds()
            logger.error(
                "[DataAgentKline] ❌ [步骤6] 注册处理器失败 %s %s (耗时: %.3fs): %s",
                symbol_upper, interval, duration, e, exc_info=True
            )
            return {
                "success": False,
                "duration": duration,
                "message_handler_registered": False,
                "error_handler_registered": False,
                "error": str(e)
            }
    
    async def step7_save_connection(
        self, symbol: str, interval: str, connection: Any, stream: Any
    ) -> Dict[str, Any]:
        """步骤7: 保存连接对象到map。
        
        Args:
            symbol: 交易对符号
            interval: 时间间隔
            connection: WebSocket连接对象
            stream: K线流对象
        
        Returns:
            包含执行结果的字典:
            {
                "success": bool,
                "duration": float,
                "connection_count": int,
                "error": Optional[str]
            }
        """
        step_start_time = datetime.now(timezone.utc)
        symbol_upper = symbol.upper()
        key = (symbol_upper, interval)
        try:
            logger.info(
                "[DataAgentKline] 💾 [步骤7] 保存连接对象到map %s %s...",
                symbol_upper, interval
            )
            
            async with self._lock:
                conn = KlineStreamConnection(
                    symbol=symbol_upper,
                    interval=interval,
                    connection=connection,
                    stream=stream,
                    created_at=datetime.now(timezone.utc)
                )
                
                self._active_connections[key] = conn
                connection_count = len(self._active_connections)
            
            duration = (datetime.now(timezone.utc) - step_start_time).total_seconds()
            logger.info(
                "[DataAgentKline] ✅ [步骤7] 连接对象已保存 %s %s (耗时: %.3fs, 当前连接数: %s)",
                symbol_upper, interval, duration, connection_count
            )
            
            return {
                "success": True,
                "duration": duration,
                "connection_count": connection_count,
                "error": None
            }
        except Exception as e:
            duration = (datetime.now(timezone.utc) - step_start_time).total_seconds()
            logger.error(
                "[DataAgentKline] ❌ [步骤7] 保存连接对象失败 %s %s (耗时: %.3fs): %s",
                symbol_upper, interval, duration, e, exc_info=True
            )
            return {
                "success": False,
                "duration": duration,
                "connection_count": len(self._active_connections),
                "error": str(e)
            }
    
    # ============================================================================
    # 流管理方法 - 完整流程
    # ============================================================================
    
    async def add_stream(self, symbol: str, interval: str) -> bool:
        """添加K线流。
        
        Args:
            symbol: 交易对符号
            interval: 时间间隔
        
        Returns:
            成功返回True，失败返回False
        """
        stream_start_time = datetime.now(timezone.utc)
        
        if interval not in self._intervals:
            logger.warning("[DataAgentKline] ⚠️  [添加流] 不支持的interval: %s", interval)
            return False
        
        symbol_upper = symbol.upper()
        key = (symbol_upper, interval)
        
        logger.debug(
            "[DataAgentKline] 🔨 [添加流] 开始添加 %s %s 的K线流",
            symbol_upper, interval
        )
        
        lock_acquire_start = datetime.now(timezone.utc)
        logger.debug(
            "[DataAgentKline] 🔒 [添加流] 尝试获取锁 %s %s...",
            symbol_upper, interval
        )
        async with self._lock:
            lock_acquire_duration = (datetime.now(timezone.utc) - lock_acquire_start).total_seconds()
            logger.debug(
                "[DataAgentKline] ✅ [添加流] 锁获取成功 %s %s (耗时: %.3fs)",
                symbol_upper, interval, lock_acquire_duration
            )
            
            # 检查map中是否已经构建过对应的symbol+interval的同步链接
            logger.debug(
                "[DataAgentKline] 🔍 [添加流] 检查连接是否已存在 %s %s (当前连接数: %s)...",
                symbol_upper, interval, len(self._active_connections)
            )
            
            if key in self._active_connections:
                conn = self._active_connections[key]
                logger.info(
                    "[DataAgentKline] 🔍 [添加流] %s %s 连接已存在 (创建时间: %s, is_active: %s)",
                    symbol_upper, interval, conn.created_at.isoformat(), conn.is_active
                )
                
                # 检查连接是否仍然活跃且未过期
                is_expired = conn.is_expired()
                logger.debug(
                    "[DataAgentKline] 🔍 [添加流] %s %s 连接状态检查: is_active=%s, is_expired=%s",
                    symbol_upper, interval, conn.is_active, is_expired
                )
                
                if conn.is_active and not is_expired:
                    logger.info(
                        "[DataAgentKline] ✅ [添加流] %s %s 已存在活跃连接，跳过构建",
                        symbol_upper, interval
                    )
                    return True
                
                # 如果连接不活跃或已过期，先关闭并从map中删除
                logger.info(
                    "[DataAgentKline] 🔄 [添加流] %s %s 的连接已过期或不活跃，开始清理 (is_active: %s, is_expired: %s)",
                    symbol_upper, interval, conn.is_active, is_expired
                )
                try:
                    close_start = datetime.now(timezone.utc)
                    await conn.close()
                    close_duration = (datetime.now(timezone.utc) - close_start).total_seconds()
                    logger.info(
                        "[DataAgentKline] ✅ [添加流] %s %s 过期连接已关闭 (耗时: %.3fs)",
                        symbol_upper, interval, close_duration
                    )
                except Exception as e:
                    logger.warning(
                        "[DataAgentKline] ⚠️  [添加流] 清理过期连接时出错 %s %s: %s",
                        symbol_upper, interval, e
                    )
                
                del self._active_connections[key]
                logger.info(
                    "[DataAgentKline] ✅ [添加流] %s %s 过期连接已从map中删除 (当前连接数: %s)",
                    symbol_upper, interval, len(self._active_connections)
                )
            else:
                logger.debug(
                    "[DataAgentKline] ℹ️  [添加流] %s %s 连接不存在，需要创建新连接",
                    symbol_upper, interval
                )
            
            # 检查symbol数量限制（每个symbol有7个interval）
            # 计算当前已持有的symbol数量
            logger.debug(
                "[DataAgentKline] 🔍 [添加流] 检查symbol数量限制 %s %s (最大symbol数: %s)...",
                symbol_upper, interval, self._max_symbols
            )
            
            current_symbols = set()
            for key, conn in self._active_connections.items():
                current_symbols.add(conn.symbol)
            
            logger.debug(
                "[DataAgentKline] 📊 [添加流] 当前已持有symbol数量: %s/%s, symbols: %s",
                len(current_symbols), self._max_symbols, sorted(list(current_symbols))[:10]
            )
            
            # 如果当前symbol不在已持有的symbol中，检查是否超过最大symbol数量
            if symbol_upper not in current_symbols and len(current_symbols) >= self._max_symbols:
                logger.warning(
                    "[DataAgentKline] ⚠️  [添加流] 已达到最大symbol数量限制 (%s/%s)，无法添加 %s %s",
                    len(current_symbols), self._max_symbols, symbol_upper, interval
                )
                return False
            
            logger.debug(
                "[DataAgentKline] ✅ [添加流] symbol数量检查通过 %s %s (当前: %s/%s)",
                symbol_upper, interval, len(current_symbols), self._max_symbols
            )
        
        logger.debug(
            "[DataAgentKline] 🔓 [添加流] 锁已释放 %s %s",
            symbol_upper, interval
        )
        
        try:
            # 步骤1: 初始化客户端
            step1_result = await self.step1_init_client()
            if not step1_result["success"]:
                logger.error(
                    "[DataAgentKline] ❌ [添加流] 步骤1失败 %s %s: %s",
                    symbol_upper, interval, step1_result.get("error")
                )
                return False
            
            # 步骤2: 检查订阅频率限制
            step2_result = await self.step2_rate_limit_check()
            if not step2_result["success"]:
                logger.error(
                    "[DataAgentKline] ❌ [添加流] 步骤2失败 %s %s: %s",
                    symbol_upper, interval, step2_result.get("error")
                )
                return False
            
            # 步骤3: 创建WebSocket连接
            step3_result = await self.step3_create_connection()
            if not step3_result["success"]:
                logger.error(
                    "[DataAgentKline] ❌ [添加流] 步骤3失败 %s %s: %s",
                    symbol_upper, interval, step3_result.get("error")
                )
                return False
            
            connection = step3_result["connection"]
            if connection is None:
                logger.error(
                    "[DataAgentKline] ❌ [添加流] 步骤3返回的连接对象为None %s %s",
                    symbol_upper, interval
                )
                return False
            
            # 步骤4: 注册连接错误处理器
            step4_result = await self.step4_register_connection_error_handler(
                connection, symbol_upper, interval
            )
            if not step4_result["success"]:
                logger.warning(
                    "[DataAgentKline] ⚠️  [添加流] 步骤4失败（非关键）%s %s: %s",
                    symbol_upper, interval, step4_result.get("error")
                )
                # 步骤4失败不影响后续流程，继续执行
            
            # 步骤5: 订阅K线流
            step5_result = await self.step5_subscribe_kline_stream(
                connection, symbol_upper, interval
            )
            if not step5_result["success"]:
                logger.error(
                    "[DataAgentKline] ❌ [添加流] 步骤5失败 %s %s: %s",
                    symbol_upper, interval, step5_result.get("error")
                )
                # 清理连接
                try:
                    await connection.close_connection()
                except Exception:
                    pass
                return False
            
            stream = step5_result["stream"]
            if stream is None:
                logger.error(
                    "[DataAgentKline] ❌ [添加流] 步骤5返回的流对象为None %s %s",
                    symbol_upper, interval
                )
                # 清理连接
                try:
                    await connection.close_connection()
                except Exception:
                    pass
                return False
            
            # 步骤6: 注册消息和错误处理器
            step6_result = await self.step6_register_message_handler(
                stream, symbol_upper, interval
            )
            if not step6_result["success"]:
                logger.error(
                    "[DataAgentKline] ❌ [添加流] 步骤6失败 %s %s: %s",
                    symbol_upper, interval, step6_result.get("error")
                )
                # 清理连接和流
                try:
                    await connection.close_connection()
                except Exception:
                    pass
                return False
            
            # 步骤7: 保存连接对象
            step7_result = await self.step7_save_connection(
                symbol_upper, interval, connection, stream
            )
            if not step7_result["success"]:
                logger.error(
                    "[DataAgentKline] ❌ [添加流] 步骤7失败 %s %s: %s",
                    symbol_upper, interval, step7_result.get("error")
                )
                # 清理连接和流
                try:
                    await connection.close_connection()
                except Exception:
                    pass
                return False
            
            stream_duration = (datetime.now(timezone.utc) - stream_start_time).total_seconds()
            logger.info(
                "[DataAgentKline] ✅ [添加流] %s %s 全部完成！(总耗时: %.3fs, 步骤耗时: 步骤1=%.3fs, 步骤2=%.3fs, 步骤3=%.3fs, 步骤4=%.3fs, 步骤5=%.3fs, 步骤6=%.3fs, 步骤7=%.3fs)",
                symbol_upper, interval, stream_duration,
                step1_result["duration"], step2_result["duration"], step3_result["duration"],
                step4_result["duration"], step5_result["duration"], step6_result["duration"],
                step7_result["duration"]
            )
            return True
        except asyncio.CancelledError:
            stream_duration = (datetime.now(timezone.utc) - stream_start_time).total_seconds()
            logger.warning(
                "[DataAgentKline] ⚠️  [添加流] %s %s 任务被取消 (耗时: %.3fs)",
                symbol_upper, interval, stream_duration
            )
            raise
        except Exception as e:
                stream_duration = (datetime.now(timezone.utc) - stream_start_time).total_seconds()
                logger.error(
                    "[DataAgentKline] ❌ [添加流] %s %s 添加失败 (耗时: %.3fs): %s",
                    symbol_upper, interval, stream_duration, e, exc_info=True
                )
                
                # 如果连接已创建但添加流失败，尝试关闭连接并从map中删除
                cleanup_start = datetime.now(timezone.utc)
                logger.info(
                    "[DataAgentKline] 🧹 [添加流] 开始清理失败的连接 %s %s...",
                    symbol_upper, interval
                )
                
                if 'connection' in locals() and connection:
                    try:
                        logger.debug(
                            "[DataAgentKline] 🔌 [添加流] 关闭失败的连接 %s %s...",
                            symbol_upper, interval
                        )
                        await connection.close_connection()
                        logger.info(
                            "[DataAgentKline] ✅ [添加流] 失败的连接已关闭 %s %s",
                            symbol_upper, interval
                        )
                    except Exception as close_e:
                        logger.warning(
                            "[DataAgentKline] ⚠️  [添加流] 关闭失败连接时出错 %s %s: %s",
                            symbol_upper, interval, close_e
                        )
                
                # 确保从map中删除
                logger.debug(
                    "[DataAgentKline] 🔒 [添加流] 获取锁以清理失败的连接 %s %s...",
                    symbol_upper, interval
                )
                async with self._lock:
                    if key in self._active_connections:
                        logger.info(
                            "[DataAgentKline] 🗑️  [添加流] 从map中删除失败的连接 %s %s (当前连接数: %s)",
                            symbol_upper, interval, len(self._active_connections) - 1
                        )
                        del self._active_connections[key]
                    else:
                        logger.debug(
                            "[DataAgentKline] ℹ️  [添加流] 失败的连接不在map中 %s %s",
                            symbol_upper, interval
                        )
                
                cleanup_duration = (datetime.now(timezone.utc) - cleanup_start).total_seconds()
                logger.info(
                    "[DataAgentKline] ✅ [添加流] 清理完成 %s %s (清理耗时: %.3fs)",
                    symbol_upper, interval, cleanup_duration
                )
                
                return False
    
    async def _remove_broken_connection(self, symbol: str, interval: str) -> None:
        """移除断开的连接（从map中删除）。
        
        当检测到连接错误或流错误时，调用此方法清理断开的连接。
        该方法会标记连接为非活跃状态，关闭连接，并从活跃连接字典中删除。
        
        Args:
            symbol: 交易对符号
            interval: 时间间隔
        """
        """移除断开的连接（从map中删除）。"""
        key = (symbol.upper(), interval)
        async with self._lock:
            if key in self._active_connections:
                conn = self._active_connections[key]
                conn.is_active = False
                try:
                    await conn.close()
                except Exception as e:
                    logger.debug("[DataAgentKline] Error closing broken connection: %s", e)
                del self._active_connections[key]
                logger.info("[DataAgentKline] Removed broken connection: %s %s", symbol, interval)
    
    async def add_symbol_streams(self, symbol: str) -> Dict[str, Any]:
        """为指定symbol添加所有interval的K线流。
        
        在构建每个interval的监听连接前，会检查map中是否已经存在对应的连接。
        使用的interval列表由初始化时的intervals参数决定（如果未提供则使用全局配置）。
        
        Args:
            symbol: 交易对符号
        
        Returns:
            包含成功和失败数量的字典
            {
                "success_count": int,
                "failed_count": int,
                "total_count": int,
                "skipped_count": int  # 已存在的连接数量
            }
        """
        method_start_time = datetime.now(timezone.utc)
        symbol_upper = symbol.upper()
        
        logger.info(
            "[DataAgentKline] 🔨 [构建K线监听] 开始为 symbol %s 构建所有interval的K线流 (时间: %s)",
            symbol_upper, method_start_time.isoformat()
        )
        
        success_count = 0
        failed_count = 0
        skipped_count = 0
        
        # 先检查map中已经存在的连接
        logger.debug("[DataAgentKline] 🔍 [构建K线监听] 检查 %s 的已有连接...", symbol_upper)
        lock_acquire_start = datetime.now(timezone.utc)
        logger.debug("[DataAgentKline] 🔒 [构建K线监听] 尝试获取锁以检查已有连接 %s...", symbol_upper)
        async with self._lock:
            lock_acquire_duration = (datetime.now(timezone.utc) - lock_acquire_start).total_seconds()
            logger.debug(
                "[DataAgentKline] ✅ [构建K线监听] 锁获取成功 %s (耗时: %.3fs)",
                symbol_upper, lock_acquire_duration
            )
            
            existing_intervals = set()
            for interval in self._intervals:
                key = (symbol_upper, interval)
                if key in self._active_connections:
                    conn = self._active_connections[key]
                    if conn.is_active and not conn.is_expired():
                        existing_intervals.add(interval)
                        logger.debug(
                            "[DataAgentKline] ✅ [构建K线监听] %s %s 已存在活跃连接 (创建时间: %s)",
                            symbol_upper, interval, conn.created_at.isoformat()
                        )
                    else:
                        logger.debug(
                            "[DataAgentKline] ⚠️  [构建K线监听] %s %s 连接存在但不活跃或已过期 (is_active: %s, created_at: %s)",
                            symbol_upper, interval, conn.is_active, conn.created_at.isoformat()
                        )
                else:
                    logger.debug(
                        "[DataAgentKline] ℹ️  [构建K线监听] %s %s 连接不存在，需要创建",
                        symbol_upper, interval
                    )
        
        logger.debug(
            "[DataAgentKline] 🔓 [构建K线监听] 锁已释放 %s",
            symbol_upper
        )
        
        logger.info(
            "[DataAgentKline] 📊 [构建K线监听] %s 已有连接数: %s/%s",
            symbol_upper, len(existing_intervals), len(self._intervals)
        )
        
        # 只为不存在的interval创建连接
        for idx, interval in enumerate(self._intervals):
            interval_start_time = datetime.now(timezone.utc)
            
            if interval in existing_intervals:
                skipped_count += 1
                logger.debug(
                    "[DataAgentKline] ⏭️  [构建K线监听] 跳过 %s %s (已存在活跃连接)",
                    symbol_upper, interval
                )
                continue
            
            logger.info(
                "[DataAgentKline] 🔨 [构建K线监听] 开始构建 %s %s (%s/%s) (时间: %s)",
                symbol_upper, interval, idx + 1, len(self._intervals), interval_start_time.isoformat()
            )
            
            try:
                # add_stream内部会再次检查map，确保不会重复创建
                # 为每个 interval 的 add_stream 添加超时保护（最多等待25秒，留出一些余量）
                success = await asyncio.wait_for(
                    self.add_stream(symbol_upper, interval),
                    timeout=25.0
                )
                interval_duration = (datetime.now(timezone.utc) - interval_start_time).total_seconds()
                
                if success:
                    success_count += 1
                    logger.info(
                        "[DataAgentKline] ✅ [构建K线监听] %s %s 构建成功 (耗时: %.3fs)",
                        symbol_upper, interval, interval_duration
                    )
                else:
                    failed_count += 1
                    logger.warning(
                        "[DataAgentKline] ⚠️  [构建K线监听] %s %s 构建失败 (耗时: %.3fs)",
                        symbol_upper, interval, interval_duration
                    )
            except asyncio.TimeoutError as e:
                interval_duration = (datetime.now(timezone.utc) - interval_start_time).total_seconds()
                failed_count += 1
                logger.error(
                    "[DataAgentKline] ❌ [构建K线监听] %s %s 构建超时 (耗时: %.3fs, 超时设置: 25s): %s",
                    symbol_upper, interval, interval_duration, e
                )
            except Exception as e:
                interval_duration = (datetime.now(timezone.utc) - interval_start_time).total_seconds()
                failed_count += 1
                logger.error(
                    "[DataAgentKline] ❌ [构建K线监听] %s %s 构建异常 (耗时: %.3fs): %s",
                    symbol_upper, interval, interval_duration, e, exc_info=True
                )
        
        method_duration = (datetime.now(timezone.utc) - method_start_time).total_seconds()
        
        result = {
            "success_count": success_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "total_count": len(self._intervals)
        }
        
        logger.info(
            "[DataAgentKline] ✅ [构建K线监听] %s 构建完成 (总耗时: %.3fs, 结果: %s)",
            symbol_upper, method_duration, result
        )
        
        return result
    
    async def remove_stream(self, symbol: str, interval: str) -> bool:
        """移除K线流（手动调用，用于停止监听某个symbol的某个interval）。
        
        注意：正常情况下，K线监听应该长期运行，不应该主动调用此方法。
        此方法主要用于：
        - 手动停止监听某个symbol的某个interval
        - 服务关闭时清理所有连接
        - 错误处理时清理无法使用的连接
        
        Args:
            symbol: 交易对符号
            interval: 时间间隔
        
        Returns:
            成功返回True，失败返回False
        """
        key = (symbol.upper(), interval)
        
        async with self._lock:
            if key not in self._active_connections:
                return True
            
            try:
                conn = self._active_connections[key]
                await conn.close()
                del self._active_connections[key]
                logger.info("[DataAgentKline] Removed stream: %s %s", symbol, interval)
                return True
            except Exception as e:
                logger.error("[DataAgentKline] Failed to remove stream %s %s: %s", symbol, interval, e)
                if key in self._active_connections:
                    del self._active_connections[key]
                return False
    
    # ============================================================================
    # 状态查询方法
    # ============================================================================
    
    async def get_connection_count(self) -> int:
        """获取当前连接数。"""
        async with self._lock:
            return len(self._active_connections)
    
    async def _cleanup_broken_connections(self) -> None:
        """检查断开的连接（但不主动关闭，因为K线监听应该长期运行）。
        
        注意：K线监听是长期运行的异步任务，不应该主动关闭连接。
        此方法只检查连接状态，不关闭连接。
        只有在连接确实无法使用时（通过错误处理器检测到）才会关闭。
        """
        # 只检查连接状态，不关闭连接
        async with self._lock:
            total_connections = len(self._active_connections)
            broken_count = 0
            for key, conn in self._active_connections.items():
                if not conn.is_active:
                    broken_count += 1
                    logger.debug(
                        "[DataAgentKline] 🔍 [检查] 发现非活跃连接（但不会主动关闭）: %s %s",
                        key[0], key[1]
                    )
            
            if broken_count > 0:
                logger.info(
                    "[DataAgentKline] 📊 [检查] 连接状态: 总数=%s, 非活跃数=%s (非活跃连接不会自动关闭，等待错误处理器处理)",
                    total_connections, broken_count
                )
            else:
                logger.debug(
                    "[DataAgentKline] ✅ [检查] 所有连接状态正常: 总数=%s",
                    total_connections
                )
        
        # 不再主动关闭连接，让连接长期运行
        # 只有在错误处理器检测到连接确实无法使用时才会关闭
        return
    
    async def get_connection_status(self) -> Dict[str, Any]:
        """获取当前连接状态（JSON格式）。
        
        Returns:
            包含总连接数和详细symbol列表的字典
            {
                "connection_count": int,  # 总连接数（根据symbol数量 * 7个interval计算）
                "symbols": [str, ...]  # symbol列表，不包含interval信息
            }
        """
        # 只检查连接状态，不清理连接（K线监听应该长期运行）
        await self.cleanup_expired_connections()  # 只检查，不关闭
        await self._cleanup_broken_connections()  # 只检查，不关闭
        
        async with self._lock:
            # 获取所有唯一的symbol（不包含interval信息）
            symbols_set = set()
            for key, conn in self._active_connections.items():
                symbols_set.add(conn.symbol)
            
            # 计算总连接数（每个symbol有7个interval）
            connection_count = len(symbols_set) * len(self._intervals)
            
            return {
                "connection_count": connection_count,
                "symbols": sorted(list(symbols_set))
            }
    
    async def get_connection_list(self) -> List[Dict[str, Any]]:
        """获取当前所有连接的详细信息。"""
        async with self._lock:
            connections = []
            for key, conn in self._active_connections.items():
                connections.append({
                    "symbol": conn.symbol,
                    "interval": conn.interval,
                    "created_at": conn.created_at.isoformat(),
                    "is_active": conn.is_active,
                })
            return connections
    
    async def cleanup_all(self) -> None:
        """清理所有连接。
        
        该方法会：
        1. 标记为正在关闭
        2. 取消后台任务
        3. 关闭所有连接
        4. 清空连接字典
        """
        logger.info("[DataAgentKline] 🧹 [清理] 开始清理所有连接...")
        self._is_closing = True
        
        # 取消后台任务
        if hasattr(self, '_check_task'):
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning("[DataAgentKline] Error cancelling check task: %s", e)
        
        if hasattr(self, '_ping_task'):
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning("[DataAgentKline] Error cancelling ping task: %s", e)
        
        # 收集所有连接，在锁外关闭它们
        connections_to_close = []
        async with self._lock:
            connections_to_close = list(self._active_connections.values())
            self._active_connections.clear()
        
        logger.info("[DataAgentKline] 🧹 [清理] 需要关闭 %s 个连接", len(connections_to_close))
        
        # 在锁外关闭所有连接，避免阻塞
        for idx, conn in enumerate(connections_to_close, 1):
            try:
                logger.debug(
                    "[DataAgentKline] 🧹 [清理] 关闭连接 %s/%s: %s %s",
                    idx, len(connections_to_close), conn.symbol, conn.interval
                )
                # 添加超时保护，避免关闭连接时卡住
                await asyncio.wait_for(conn.close(), timeout=5.0)
                logger.debug(
                    "[DataAgentKline] ✅ [清理] 连接已关闭 %s/%s: %s %s",
                    idx, len(connections_to_close), conn.symbol, conn.interval
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "[DataAgentKline] ⚠️  [清理] 关闭连接超时 %s/%s: %s %s",
                    idx, len(connections_to_close), conn.symbol, conn.interval
                )
            except Exception as e:
                logger.warning(
                    "[DataAgentKline] ⚠️  [清理] 关闭连接失败 %s/%s: %s %s: %s",
                    idx, len(connections_to_close), conn.symbol, conn.interval, e
                )
        
        logger.info("[DataAgentKline] ✅ [清理] 所有连接清理完成")
    
    async def get_symbols(self) -> Set[str]:
        """获取当前所有正在同步的symbol。"""
        # 先清理过期连接（在锁外执行，避免阻塞）
        await self.cleanup_expired_connections()
        
        async with self._lock:
            symbols = set()
            for key, conn in self._active_connections.items():
                symbols.add(conn.symbol)
            return symbols
    
    # ============================================================================
    # 消息处理方法
    # ============================================================================
    
    async def _handle_kline_message(self, symbol: str, interval: str, message: Any) -> None:
        """处理K线消息并插入数据库。
        
        当WebSocket接收到K线数据时，会调用此方法处理消息。
        该方法会：
        1. 规范化K线数据格式
        2. 只处理完结的K线（x=True），跳过未完结的K线
        3. 将数据插入MySQL数据库
        
        注意：
        - 空消息会被跳过（不记录为错误）
        - 未完结的K线（x=False）会被跳过（不记录为错误，这是正常行为）
        - 只有完结的K线（x=True）才会被处理并插入数据库
        
        Args:
            symbol: 交易对符号
            interval: 时间间隔
            message: 原始K线消息数据
        """
        try:
            # Check for empty message
            if message is None:
                logger.debug("[DataAgentKline] ⏭️  跳过空消息 %s %s", symbol, interval)
                return
            
            # 规范化K线数据（_normalize_kline 只负责数据格式转换，不进行业务逻辑判断）
            normalized = _normalize_kline(message)
            if normalized:
                # 检查是否完结：只有完结的K线（is_closed=1）才会被插入数据库
                is_closed = normalized.get("is_closed", 0)
                if is_closed != 1:
                    # 未完结的K线，正常跳过，不插入数据库
                    logger.debug(
                        "[DataAgentKline] ⏭️  跳过未完结的K线（is_closed=%s） %s %s",
                        is_closed, symbol, interval
                    )
                    return
                
                # 只有完结的K线（x=True, is_closed=1）才会被插入数据库
                await asyncio.to_thread(self._db.insert_market_klines, [normalized])
                logger.debug("[DataAgentKline] ✅ 已插入完结K线: %s %s", symbol, interval)
            else:
                # normalized is None means:
                # 1. Empty message (already checked above)
                # 2. Invalid message format - already logged in _normalize_kline
                logger.debug("[DataAgentKline] ⏭️  跳过无效K线: %s %s", symbol, interval)
        except Exception as e:
            logger.error("[DataAgentKline] ❌ 处理K线消息时出错 %s %s: %s", symbol, interval, e, exc_info=True)
    
    # ============================================================================
    # 清理方法
    # ============================================================================
    
    async def cleanup_expired_connections(self) -> None:
        """检查并处理过期的连接（实际上不会执行清理，因为连接应该长期运行）。
        
        注意：K线监听是长期运行的异步任务，不应该主动关闭连接。
        此方法保留用于检查连接状态，但不会主动关闭连接。
        只有在连接出错或服务关闭时才会关闭连接。
        
        该方法会检查所有活跃连接的状态，但不关闭它们。
        """
        # 只检查连接状态，不关闭连接
        async with self._lock:
            total_connections = len(self._active_connections)
            expired_count = 0
            for key, conn in self._active_connections.items():
                if conn.is_expired():
                    expired_count += 1
                    logger.debug(
                        "[DataAgentKline] 🔍 [检查] 发现过期连接（但不会关闭）: %s %s (创建时间: %s)",
                        key[0], key[1], conn.created_at.isoformat()
                    )
            
            if expired_count > 0:
                logger.info(
                    "[DataAgentKline] 📊 [检查] 连接状态: 总数=%s, 过期数=%s (过期连接不会自动关闭，保持长期运行)",
                    total_connections, expired_count
                )
            else:
                logger.debug(
                    "[DataAgentKline] ✅ [检查] 所有连接状态正常: 总数=%s",
                    total_connections
                )
    
    async def _periodic_ping(self) -> None:
        """定期发送ping请求，保持WebSocket连接活跃。"""
        while not self._is_closing:
            try:
                await asyncio.sleep(self._ping_interval.total_seconds())
                
                async with self._lock:
                    # 复制当前连接列表，避免在迭代过程中修改
                    connections = list(self._active_connections.values())
                
                for conn in connections:
                    try:
                        # 发送ping请求
                        # 注意：根据SDK错误信息，WebSocketCommon.ping()需要connection参数，不是实例方法
                        # 暂时注释掉ping发送，避免错误
                        # if conn.connection and hasattr(conn.connection, 'ping'):
                        #     await conn.connection.ping()
                        #     logger.debug("[DataAgentKline] Sent ping to %s %s", conn.symbol, conn.interval)
                        pass
                    except Exception as e:
                        logger.error("[DataAgentKline] Error sending ping to %s %s: %s", 
                                  conn.symbol, conn.interval, e)
            except asyncio.CancelledError:
                logger.info("[DataAgentKline] Periodic ping task cancelled")
                raise
            except Exception as e:
                logger.error("[DataAgentKline] Error in periodic ping: %s", e, exc_info=True)
    
    # ============================================================================
    # 频率控制方法
    # ============================================================================
    
    async def _rate_limit_subscription(self) -> None:
        """控制订阅频率，确保每秒不超过10个订阅消息。"""
        rate_limit_start_time = datetime.now(timezone.utc)
        current_time = datetime.now(timezone.utc)
        time_since_last_subscription = current_time - self._last_subscription_time
        
        logger.debug(
            "[DataAgentKline] ⏱️  [频率限制] 检查订阅频率: 上次订阅时间=%s, 距今=%.3fs, 当前计数=%s/%s",
            self._last_subscription_time.isoformat(),
            time_since_last_subscription.total_seconds(),
            self._subscriptions_in_last_second,
            self._max_subscriptions_per_second
        )
        
        # 如果已经过了1秒，重置计数器
        if time_since_last_subscription > timedelta(seconds=1):
            self._last_subscription_time = current_time
            self._subscriptions_in_last_second = 1
            rate_limit_duration = (datetime.now(timezone.utc) - rate_limit_start_time).total_seconds()
            logger.debug(
                "[DataAgentKline] ✅ [频率限制] 频率检查通过，重置计数器 (耗时: %.3fs)",
                rate_limit_duration
            )
            return
        
        # 如果在1秒内订阅次数已达上限，等待剩余时间
        self._subscriptions_in_last_second += 1
        if self._subscriptions_in_last_second > self._max_subscriptions_per_second:
            wait_time = timedelta(seconds=1) - time_since_last_subscription
            wait_seconds = wait_time.total_seconds()
            logger.info(
                "[DataAgentKline] ⏳ [频率限制] 达到频率限制 (%s/%s)，等待 %.3fs...",
                self._subscriptions_in_last_second,
                self._max_subscriptions_per_second,
                wait_seconds
            )
            await asyncio.sleep(wait_seconds)
            # 重置计数器
            self._last_subscription_time = datetime.now(timezone.utc)
            self._subscriptions_in_last_second = 1
            rate_limit_duration = (datetime.now(timezone.utc) - rate_limit_start_time).total_seconds()
            logger.info(
                "[DataAgentKline] ✅ [频率限制] 等待完成，重置计数器 (总耗时: %.3fs)",
                rate_limit_duration
            )
        else:
            rate_limit_duration = (datetime.now(timezone.utc) - rate_limit_start_time).total_seconds()
            logger.debug(
                "[DataAgentKline] ✅ [频率限制] 频率检查通过，当前计数: %s/%s (耗时: %.3fs)",
                self._subscriptions_in_last_second,
                self._max_subscriptions_per_second,
                rate_limit_duration
            )


# ============================================================================
# HTTP服务器和处理器类
# ============================================================================
        """清理所有连接。"""
        self._is_closing = True
        
        # 取消后台任务
        if hasattr(self, '_check_task'):
            self._check_task.cancel()
        if hasattr(self, '_ping_task'):
            self._ping_task.cancel()
        
        async with self._lock:
            keys = list(self._active_connections.keys())
            for key in keys:
                conn = self._active_connections[key]
                await conn.close()
                del self._active_connections[key]


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """支持多线程的HTTP服务器，每个请求在独立线程中处理，避免阻塞。"""
    daemon_threads = True  # 设置为守护线程，主进程退出时自动退出


class DataAgentStatusHandler(BaseHTTPRequestHandler):
    """处理data_agent的状态检查请求（独立端口，避免指令服务阻塞）。"""
    
    def __init__(self, kline_manager: DataAgentKlineManager, main_loop: asyncio.AbstractEventLoop, *args, **kwargs):
        self.kline_manager = kline_manager
        self._main_loop = main_loop
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """处理GET请求（仅ping接口，用于健康检查）。"""
        try:
            parsed_path = urllib.parse.urlparse(self.path)
            path = parsed_path.path
            
            if path == '/ping':
                # 探测接口（轻量级，不阻塞）
                self._handle_ping()
            else:
                self._send_error(404, "Not Found")
        except Exception as e:
            logger.error("[DataAgentStatus] Error handling GET request: %s", e, exc_info=True)
            self._send_error(500, str(e))
    
    def _handle_ping(self):
        """处理ping请求（轻量级响应，不执行任何异步操作）。"""
        request_start_time = datetime.now(timezone.utc)
        client_address = f"{self.client_address[0]}:{self.client_address[1]}"
        
        logger.debug(
            "[DataAgentStatus] 📥 [Ping请求] 收到来自 %s 的健康检查请求 (路径: %s)",
            client_address, self.path
        )
        
        try:
            # 轻量级响应，不执行任何异步操作，避免阻塞
            response_data = {"status": "ok", "message": "pong"}
            self._send_json(response_data)
            
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.debug(
                "[DataAgentStatus] 📤 [Ping响应] 已向 %s 发送健康检查响应: %s (耗时: %.3fs)",
                client_address, response_data, request_duration
            )
        except Exception as e:
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.error(
                "[DataAgentStatus] ❌ [Ping响应] 向 %s 发送健康检查响应失败 (耗时: %.3fs): %s",
                client_address, request_duration, e, exc_info=True
            )
            raise
    
    def _send_json(self, data: Dict[str, Any]):
        """发送JSON响应。"""
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response_body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.wfile.write(response_body)
            self.wfile.flush()  # 立即刷新输出缓冲区，确保响应立即发送
        except BrokenPipeError:
            logger.debug("[DataAgentStatus] Broken pipe error when sending JSON response")
        except Exception as e:
            logger.warning("[DataAgentStatus] Error when sending JSON response: %s", e)
    
    def _send_error(self, code: int, message: str):
        """发送错误响应。"""
        try:
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            error_body = json.dumps({"error": message}, ensure_ascii=False).encode('utf-8')
            self.wfile.write(error_body)
            self.wfile.flush()  # 立即刷新输出缓冲区，确保响应立即发送
        except BrokenPipeError:
            logger.debug("[DataAgentStatus] Broken pipe error when sending error response")
        except Exception as e:
            logger.warning("[DataAgentStatus] Error when sending error response: %s", e)
    
    def log_message(self, format, *args):
        """重写日志方法，使用自定义logger。"""
        logger.debug("[DataAgentStatus] %s", format % args)


class DataAgentCommandHandler(BaseHTTPRequestHandler):
    """处理data_agent的HTTP指令请求。
    
    该类处理所有来自async_agent的指令请求，包括：
    - 添加/移除K线流
    - 批量添加symbol
    - 查询连接状态和列表
    - 获取symbol列表
    
    所有异步操作都通过主事件循环执行，并设置了超时保护。
    """
    
    def __init__(self, kline_manager: DataAgentKlineManager, main_loop: asyncio.AbstractEventLoop, *args, **kwargs):
        self.kline_manager = kline_manager
        self._main_loop = main_loop
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """处理GET请求。"""
        try:
            parsed_path = urllib.parse.urlparse(self.path)
            path = parsed_path.path
            query_params = urllib.parse.parse_qs(parsed_path.query)
            
            if path == '/ping':
                # 探测接口
                self._handle_ping()
            elif path == '/connections/count':
                # 获取连接数
                self._handle_get_connection_count()
            elif path == '/connections/list':
                # 获取连接列表
                self._handle_get_connection_list()
            elif path == '/symbols':
                # 获取当前同步的symbol列表
                self._handle_get_symbols()
            elif path == '/status':
                # 获取连接状态（JSON格式：总连接数和symbol列表）
                self._handle_get_status()
            else:
                self._send_error(404, "Not Found")
        except Exception as e:
            logger.error("[DataAgentCommand] Error handling GET request: %s", e, exc_info=True)
            self._send_error(500, str(e))
    
    def do_POST(self):
        """处理POST请求。
        
        支持的POST接口：
        - /streams/add: 添加单个K线流
        - /streams/remove: 移除单个K线流
        - /symbols/add: 批量添加symbol（为每个symbol创建7个interval的流）
        """
        request_start_time = datetime.now(timezone.utc)
        client_address = f"{self.client_address[0]}:{self.client_address[1]}"
        
        logger.info(
            "[DataAgentCommand] 📥 [POST请求] 收到来自 %s 的POST请求 (路径: %s, 时间: %s)",
            client_address, self.path, request_start_time.isoformat()
        )
        logger.debug(
            "[DataAgentCommand] 📥 [POST请求] 请求头: %s",
            dict(self.headers)
        )
        
        try:
            parsed_path = urllib.parse.urlparse(self.path)
            path = parsed_path.path
            
            logger.info(
                "[DataAgentCommand] 📥 [POST请求] 解析路径: %s -> %s",
                self.path, path
            )
            
            if path == '/streams/add':
                # 添加K线流
                logger.info("[DataAgentCommand] 📥 [POST请求] 路由到 /streams/add")
                self._handle_add_stream()
            elif path == '/streams/remove':
                # 移除K线流
                logger.info("[DataAgentCommand] 📥 [POST请求] 路由到 /streams/remove")
                self._handle_remove_stream()
            elif path == '/symbols/add':
                # 批量添加symbol（为每个symbol创建7个interval的流）
                logger.info("[DataAgentCommand] 📥 [POST请求] 路由到 /symbols/add")
                self._handle_add_symbols()
            else:
                logger.warning(
                    "[DataAgentCommand] ⚠️  [POST请求] 未知路径: %s (来自 %s)",
                    path, client_address
                )
                self._send_error(404, "Not Found")
        except Exception as e:
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.error(
                "[DataAgentCommand] ❌ [POST请求] 处理请求失败 (路径: %s, 来自: %s, 耗时: %.3fs): %s",
                self.path, client_address, request_duration, e, exc_info=True
            )
            self._send_error(500, str(e))
    
    def _handle_ping(self):
        """处理ping请求。"""
        request_start_time = datetime.now(timezone.utc)
        client_address = f"{self.client_address[0]}:{self.client_address[1]}"
        
        logger.info(
            "[DataAgentCommand] 📥 [Ping请求] 收到来自 %s 的健康检查请求 (路径: %s)",
            client_address, self.path
        )
        
        try:
            response_data = {"status": "ok", "message": "pong"}
            self._send_json(response_data)
            
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.info(
                "[DataAgentCommand] 📤 [Ping响应] 已向 %s 发送健康检查响应: %s (耗时: %.3fs)",
                client_address, response_data, request_duration
            )
        except Exception as e:
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.error(
                "[DataAgentCommand] ❌ [Ping响应] 向 %s 发送健康检查响应失败 (耗时: %.3fs): %s",
                client_address, request_duration, e, exc_info=True
            )
            raise
    
    def _handle_get_connection_count(self):
        """处理获取连接数请求。"""
        request_start_time = datetime.now(timezone.utc)
        try:
            # 使用主事件循环执行异步操作
            coro = self.kline_manager.get_connection_count()
            future = asyncio.run_coroutine_threadsafe(coro, self._main_loop)
            # 添加超时保护，避免HTTP请求一直等待
            count = future.result(timeout=10)  # 最多等待10秒
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.debug(
                "[DataAgentCommand] ✅ [获取连接数] 成功 (耗时: %.3fs, 连接数: %s)",
                request_duration, count
            )
            self._send_json({"connection_count": count})
        except TimeoutError:
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.error(
                "[DataAgentCommand] ❌ [获取连接数] 超时 (耗时: %.3fs)",
                request_duration
            )
            self._send_error(500, "Timeout getting connection count")
        except Exception as e:
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.error(
                "[DataAgentCommand] ❌ [获取连接数] 错误 (耗时: %.3fs): %s",
                request_duration, e, exc_info=True
            )
            self._send_error(500, str(e))
    
    def _handle_get_connection_list(self):
        """处理获取连接列表请求。"""
        request_start_time = datetime.now(timezone.utc)
        try:
            # 使用主事件循环执行异步操作
            coro = self.kline_manager.get_connection_list()
            future = asyncio.run_coroutine_threadsafe(coro, self._main_loop)
            # 添加超时保护，避免HTTP请求一直等待
            connections = future.result(timeout=10)  # 最多等待10秒
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.debug(
                "[DataAgentCommand] ✅ [获取连接列表] 成功 (耗时: %.3fs, 连接数: %s)",
                request_duration, len(connections)
            )
            self._send_json({"connections": connections, "count": len(connections)})
        except TimeoutError:
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.error(
                "[DataAgentCommand] ❌ [获取连接列表] 超时 (耗时: %.3fs)",
                request_duration
            )
            self._send_error(500, "Timeout getting connection list")
        except Exception as e:
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.error(
                "[DataAgentCommand] ❌ [获取连接列表] 错误 (耗时: %.3fs): %s",
                request_duration, e, exc_info=True
            )
            self._send_error(500, str(e))
    
    def _handle_get_symbols(self):
        """处理获取symbol列表请求。"""
        request_start_time = datetime.now(timezone.utc)
        try:
            # 使用主事件循环执行异步操作
            coro = self.kline_manager.get_symbols()
            future = asyncio.run_coroutine_threadsafe(coro, self._main_loop)
            # 添加超时保护，避免HTTP请求一直等待
            symbols = future.result(timeout=10)  # 最多等待10秒
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.debug(
                "[DataAgentCommand] ✅ [获取Symbol列表] 成功 (耗时: %.3fs, symbol数: %s)",
                request_duration, len(symbols)
            )
            self._send_json({"symbols": sorted(list(symbols)), "count": len(symbols)})
        except TimeoutError:
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.error(
                "[DataAgentCommand] ❌ [获取Symbol列表] 超时 (耗时: %.3fs)",
                request_duration
            )
            self._send_error(500, "Timeout getting symbols")
        except Exception as e:
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.error(
                "[DataAgentCommand] ❌ [获取Symbol列表] 错误 (耗时: %.3fs): %s",
                request_duration, e, exc_info=True
            )
            self._send_error(500, str(e))
    
    def _handle_get_status(self):
        """处理获取连接状态请求（返回JSON格式：总连接数和symbol列表）。"""
        request_start_time = datetime.now(timezone.utc)
        try:
            coro = self.kline_manager.get_connection_status()
            future = asyncio.run_coroutine_threadsafe(coro, self._main_loop)
            # 添加超时保护，避免HTTP请求一直等待
            status = future.result(timeout=10)  # 最多等待10秒
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.debug(
                "[DataAgentCommand] ✅ [获取状态] 成功 (耗时: %.3fs, 状态: %s)",
                request_duration, status
            )
            self._send_json({"status": "ok", **status})
        except TimeoutError:
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.error(
                "[DataAgentCommand] ❌ [获取状态] 超时 (耗时: %.3fs)",
                request_duration
            )
            self._send_error(500, "Timeout getting status")
        except Exception as e:
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.error(
                "[DataAgentCommand] ❌ [获取状态] 错误 (耗时: %.3fs): %s",
                request_duration, e, exc_info=True
            )
            self._send_error(500, str(e))
    
    def _handle_add_symbols(self):
        """处理批量添加symbol请求（为每个symbol创建7个interval的流）。"""
        request_start_time = datetime.now(timezone.utc)
        client_address = f"{self.client_address[0]}:{self.client_address[1]}"
        
        logger.info(
            "[DataAgentCommand] 📥 [添加Symbol] 收到来自 %s 的批量添加symbol请求 (时间: %s)",
            client_address, request_start_time.isoformat()
        )
        
        try:
            # 读取请求体
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                logger.warning("[DataAgentCommand] ⚠️  [添加Symbol] 请求体为空")
                self._send_error(400, "Missing request body")
                return
            
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            symbols = data.get('symbols', [])
            if not symbols or not isinstance(symbols, list):
                logger.warning("[DataAgentCommand] ⚠️  [添加Symbol] 无效的symbols列表: %s", symbols)
                self._send_error(400, "Missing or invalid symbols list")
                return
            
            logger.info(
                "[DataAgentCommand] 📋 [添加Symbol] 开始处理 %s 个symbol: %s",
                len(symbols), symbols[:10] if len(symbols) > 10 else symbols
            )
            
            # 设置超时时间：每个symbol最多30秒，总超时时间不超过5分钟
            per_symbol_timeout = 30  # 每个symbol最多30秒
            total_timeout = min(300, len(symbols) * per_symbol_timeout)  # 总超时不超过5分钟
            
            results = []
            failed_symbols = []
            
            for idx, symbol in enumerate(symbols):
                symbol_start_time = datetime.now(timezone.utc)
                symbol_clean = symbol.upper().strip()
                
                if not symbol_clean:
                    logger.warning("[DataAgentCommand] ⚠️  [添加Symbol] 跳过空symbol: %s", symbol)
                    continue
                
                logger.info(
                    "[DataAgentCommand] 🔨 [添加Symbol] 开始处理 symbol %s (%s/%s) (时间: %s)",
                    symbol_clean, idx + 1, len(symbols), symbol_start_time.isoformat()
                )
                
                try:
                    logger.debug(
                        "[DataAgentCommand] 🔨 [添加Symbol] 创建异步任务处理 symbol %s",
                        symbol_clean
                    )
                    coro = self.kline_manager.add_symbol_streams(symbol_clean)
                    task_creation_start = datetime.now(timezone.utc)
                    future = asyncio.run_coroutine_threadsafe(coro, self._main_loop)
                    task_creation_duration = (datetime.now(timezone.utc) - task_creation_start).total_seconds()
                    logger.debug(
                        "[DataAgentCommand] ✅ [添加Symbol] 异步任务创建完成 symbol %s (任务创建耗时: %.3fs)",
                        symbol_clean, task_creation_duration
                    )
                    
                    # 添加超时保护，避免无限等待
                    try:
                        result = future.result(timeout=per_symbol_timeout)
                        symbol_duration = (datetime.now(timezone.utc) - symbol_start_time).total_seconds()
                        
                        logger.info(
                            "[DataAgentCommand] ✅ [添加Symbol] symbol %s 处理完成 (耗时: %.3fs, 结果: %s)",
                            symbol_clean, symbol_duration, result
                        )
                        
                        results.append({
                            "symbol": symbol_clean,
                            **result
                        })
                    except TimeoutError:
                        symbol_duration = (datetime.now(timezone.utc) - symbol_start_time).total_seconds()
                        logger.error(
                            "[DataAgentCommand] ❌ [添加Symbol] symbol %s 处理超时 (耗时: %.3fs, 超时设置: %ss)",
                            symbol_clean, symbol_duration, per_symbol_timeout
                        )
                        failed_symbols.append(symbol_clean)
                        results.append({
                            "symbol": symbol_clean,
                            "success_count": 0,
                            "failed_count": 0,
                            "skipped_count": 0,
                            "total_count": 7,
                            "error": f"Timeout after {per_symbol_timeout}s"
                        })
                    except Exception as e:
                        symbol_duration = (datetime.now(timezone.utc) - symbol_start_time).total_seconds()
                        logger.error(
                            "[DataAgentCommand] ❌ [添加Symbol] symbol %s 处理失败 (耗时: %.3fs): %s",
                            symbol_clean, symbol_duration, e, exc_info=True
                        )
                        failed_symbols.append(symbol_clean)
                        results.append({
                            "symbol": symbol_clean,
                            "success_count": 0,
                            "failed_count": 0,
                            "skipped_count": 0,
                            "total_count": 7,
                            "error": str(e)
                        })
                except Exception as e:
                    symbol_duration = (datetime.now(timezone.utc) - symbol_start_time).total_seconds()
                    logger.error(
                        "[DataAgentCommand] ❌ [添加Symbol] symbol %s 创建任务失败 (耗时: %.3fs): %s",
                        symbol_clean, symbol_duration, e, exc_info=True
                    )
                    failed_symbols.append(symbol_clean)
                    results.append({
                        "symbol": symbol_clean,
                        "success_count": 0,
                        "failed_count": 0,
                        "skipped_count": 0,
                        "total_count": 7,
                        "error": f"Task creation failed: {str(e)}"
                    })
            
            logger.info(
                "[DataAgentCommand] 📊 [添加Symbol] 所有symbol处理完成: 成功 %s 个, 失败 %s 个",
                len(results) - len(failed_symbols), len(failed_symbols)
            )
            
            # 获取当前连接状态（添加超时保护）
            logger.info("[DataAgentCommand] 📊 [添加Symbol] 获取当前连接状态...")
            try:
                status_coro = self.kline_manager.get_connection_status()
                status_future = asyncio.run_coroutine_threadsafe(status_coro, self._main_loop)
                status = status_future.result(timeout=10)  # 状态查询最多10秒
                logger.info(
                    "[DataAgentCommand] ✅ [添加Symbol] 连接状态获取成功: %s",
                    status
                )
            except Exception as e:
                logger.error(
                    "[DataAgentCommand] ⚠️  [添加Symbol] 获取连接状态失败: %s",
                    e, exc_info=True
                )
                # 即使获取状态失败，也返回结果
                status = {
                    "connection_count": 0,
                    "symbols": []
                }
            
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            
            response_data = {
                "status": "ok" if not failed_symbols else "partial",
                "results": results,
                "current_status": status,
                "summary": {
                    "total_symbols": len(symbols),
                    "success_count": len(results) - len(failed_symbols),
                    "failed_count": len(failed_symbols),
                    "failed_symbols": failed_symbols,
                    "duration_seconds": round(request_duration, 3)
                }
            }
            
            logger.info(
                "[DataAgentCommand] 📤 [添加Symbol] 向 %s 发送响应 (总耗时: %.3fs, 状态: %s)",
                client_address, request_duration, response_data["status"]
            )
            
            self._send_json(response_data)
            
        except json.JSONDecodeError as e:
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.error(
                "[DataAgentCommand] ❌ [添加Symbol] JSON解析失败 (耗时: %.3fs): %s",
                request_duration, e, exc_info=True
            )
            self._send_error(400, f"Invalid JSON: {str(e)}")
        except Exception as e:
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.error(
                "[DataAgentCommand] ❌ [添加Symbol] 处理请求失败 (耗时: %.3fs): %s",
                request_duration, e, exc_info=True
            )
            self._send_error(500, str(e))
    
    def _handle_add_stream(self):
        """处理添加K线流请求。"""
        request_start_time = datetime.now(timezone.utc)
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        data = json.loads(body.decode('utf-8'))
        
        symbol = data.get('symbol', '').upper()
        interval = data.get('interval', '')
        
        if not symbol or not interval:
            self._send_error(400, "Missing symbol or interval")
            return
        
        try:
            # 使用主事件循环执行异步操作
            coro = self.kline_manager.add_stream(symbol, interval)
            future = asyncio.run_coroutine_threadsafe(coro, self._main_loop)
            # 添加超时保护，避免HTTP请求一直等待（添加流可能需要较长时间，设置30秒超时）
            success = future.result(timeout=30)  # 最多等待30秒
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.info(
                "[DataAgentCommand] ✅ [添加流] %s %s 完成 (耗时: %.3fs, 成功: %s)",
                symbol, interval, request_duration, success
            )
            if success:
                self._send_json({"status": "ok", "message": f"Added stream for {symbol} {interval}"})
            else:
                self._send_error(500, f"Failed to add stream for {symbol} {interval}")
        except TimeoutError:
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.error(
                "[DataAgentCommand] ❌ [添加流] %s %s 超时 (耗时: %.3fs)",
                symbol, interval, request_duration
            )
            self._send_error(500, f"Timeout adding stream for {symbol} {interval}")
        except Exception as e:
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.error(
                "[DataAgentCommand] ❌ [添加流] %s %s 错误 (耗时: %.3fs): %s",
                symbol, interval, request_duration, e, exc_info=True
            )
            self._send_error(500, str(e))
    
    def _handle_remove_stream(self):
        """处理移除K线流请求。"""
        request_start_time = datetime.now(timezone.utc)
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        data = json.loads(body.decode('utf-8'))
        
        symbol = data.get('symbol', '').upper()
        interval = data.get('interval', '')
        
        if not symbol or not interval:
            self._send_error(400, "Missing symbol or interval")
            return
        
        try:
            # 使用主事件循环执行异步操作
            coro = self.kline_manager.remove_stream(symbol, interval)
            future = asyncio.run_coroutine_threadsafe(coro, self._main_loop)
            # 添加超时保护，避免HTTP请求一直等待
            success = future.result(timeout=10)  # 最多等待10秒
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.info(
                "[DataAgentCommand] ✅ [移除流] %s %s 完成 (耗时: %.3fs, 成功: %s)",
                symbol, interval, request_duration, success
            )
            if success:
                self._send_json({"status": "ok", "message": f"Removed stream for {symbol} {interval}"})
            else:
                self._send_error(500, f"Failed to remove stream for {symbol} {interval}")
        except TimeoutError:
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.error(
                "[DataAgentCommand] ❌ [移除流] %s %s 超时 (耗时: %.3fs)",
                symbol, interval, request_duration
            )
            self._send_error(500, f"Timeout removing stream for {symbol} {interval}")
        except Exception as e:
            request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
            logger.error(
                "[DataAgentCommand] ❌ [移除流] %s %s 错误 (耗时: %.3fs): %s",
                symbol, interval, request_duration, e, exc_info=True
            )
            self._send_error(500, str(e))
    
    def _send_json(self, data: Dict[str, Any]):
        """发送JSON响应。"""
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response_body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.wfile.write(response_body)
            self.wfile.flush()  # 立即刷新输出缓冲区，确保响应立即发送
            logger.debug(
                "[DataAgentCommand] 📤 [发送响应] JSON响应已发送 (大小: %s bytes)",
                len(response_body)
            )
        except BrokenPipeError:
            # 客户端已断开连接，记录日志但不抛出异常
            logger.debug("[DataAgentCommand] Broken pipe error when sending JSON response")
        except Exception as e:
            # 其他异常情况
            logger.warning("[DataAgentCommand] Error when sending JSON response: %s", e)
    
    def _send_error(self, code: int, message: str):
        """发送错误响应。"""
        try:
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            error_body = json.dumps({"error": message}, ensure_ascii=False).encode('utf-8')
            self.wfile.write(error_body)
            self.wfile.flush()  # 立即刷新输出缓冲区，确保响应立即发送
            logger.debug(
                "[DataAgentCommand] 📤 [发送错误] 错误响应已发送 (状态码: %s, 大小: %s bytes)",
                code, len(error_body)
            )
        except BrokenPipeError:
            # 客户端已断开连接，记录日志但不抛出异常
            logger.debug("[DataAgentCommand] Broken pipe error when sending error response")
        except Exception as e:
            # 其他异常情况
            logger.warning("[DataAgentCommand] Error when sending error response: %s", e)
    
    def log_message(self, format, *args):
        """重写日志方法，使用自定义logger。"""
        logger.debug("[DataAgentCommand] %s", format % args)


def create_command_handler(kline_manager: DataAgentKlineManager, main_loop: asyncio.AbstractEventLoop):
    """创建指令请求处理器工厂函数。"""
    def handler(*args, **kwargs):
        return DataAgentCommandHandler(kline_manager, main_loop, *args, **kwargs)
    return handler


def create_status_handler(kline_manager: DataAgentKlineManager, main_loop: asyncio.AbstractEventLoop):
    """创建状态检查请求处理器工厂函数。"""
    def handler(*args, **kwargs):
        return DataAgentStatusHandler(kline_manager, main_loop, *args, **kwargs)
    return handler


async def run_data_agent_command_server(
    kline_manager: DataAgentKlineManager,
    host: str = '0.0.0.0',
    port: int = 9999
) -> None:
    """运行data_agent的HTTP指令服务器。"""
    logger.info("[DataAgent] 📡 [指令服务] 开始启动指令服务器 %s:%s...", host, port)
    
    main_loop = asyncio.get_event_loop()
    handler = create_command_handler(kline_manager, main_loop)
    
    try:
        # 使用 ThreadingHTTPServer 确保每个请求在独立线程中处理，避免阻塞
        server = ThreadingHTTPServer((host, port), handler)
        logger.info("[DataAgent] ✅ [指令服务] HTTP服务器对象创建成功 %s:%s (使用多线程模式)", host, port)
    except Exception as e:
        logger.error("[DataAgent] ❌ [指令服务] 创建HTTP服务器失败 %s:%s: %s", host, port, e, exc_info=True)
        raise
    
    def run_server():
        try:
            logger.info("[DataAgent] 📡 [指令服务] 线程中启动服务器监听 %s:%s...", host, port)
            server.serve_forever()
            logger.info("[DataAgent] 📡 [指令服务] 服务器已停止监听 %s:%s", host, port)
        except Exception as e:
            logger.error("[DataAgent] ❌ [指令服务] 服务器运行异常 %s:%s: %s", host, port, e, exc_info=True)
    
    server_thread = threading.Thread(target=run_server, daemon=True, name="DataAgentCommandServer")
    server_thread.start()
    logger.info("[DataAgent] ✅ [指令服务] 服务器线程已启动 (线程名: %s, 线程ID: %s)", 
               server_thread.name, server_thread.ident)
    
    # 等待服务器启动并验证
    await asyncio.sleep(1)
    
    # 验证服务器是否真的在监听
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host if host != '0.0.0.0' else '127.0.0.1', port))
        sock.close()
        if result == 0:
            logger.info("[DataAgent] ✅ [指令服务] 验证成功：端口 %s 正在监听", port)
        else:
            logger.warning("[DataAgent] ⚠️  [指令服务] 验证失败：端口 %s 可能未正确监听 (错误码: %s)", port, result)
    except Exception as e:
        logger.warning("[DataAgent] ⚠️  [指令服务] 验证端口时出错: %s", e)
    
    logger.info("[DataAgent] ✅ [指令服务] 指令服务器已启动并运行中 (监听地址: %s:%s)", host, port)
    
    try:
        # 保持运行
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        raise
    finally:
        server.shutdown()
        logger.info("[DataAgent] 🛑 [指令服务] 指令服务器已停止")


async def run_data_agent_status_server(
    kline_manager: DataAgentKlineManager,
    host: str = '0.0.0.0',
    port: int = 9988
) -> None:
    """运行data_agent的HTTP状态检查服务器（独立端口，避免指令服务阻塞）。"""
    main_loop = asyncio.get_event_loop()
    handler = create_status_handler(kline_manager, main_loop)
    # 使用 ThreadingHTTPServer 确保每个请求在独立线程中处理，避免阻塞
    server = ThreadingHTTPServer((host, port), handler)
    logger.info("[DataAgent] 💚 [状态服务] 启动状态检查服务器 %s:%s", host, port)
    
    def run_server():
        try:
            server.serve_forever()
        except Exception as e:
            logger.error("[DataAgent] ❌ [状态服务] 服务器运行异常: %s", e, exc_info=True)
    
    server_thread = threading.Thread(target=run_server, daemon=True, name="DataAgentStatusServer")
    server_thread.start()
    
    # 等待服务器启动
    await asyncio.sleep(0.5)
    logger.info("[DataAgent] ✅ [状态服务] 状态检查服务器已启动并运行中")
    
    try:
        # 保持运行
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        raise
    finally:
        server.shutdown()
        logger.info("[DataAgent] 🛑 [状态服务] 状态检查服务器已停止")


async def register_to_async_agent(register_ip: str, register_port: int, agent_ip: str, agent_port: int) -> bool:
    """注册到async_agent。
    
    Args:
        register_ip: async_agent的IP地址
        register_port: async_agent的端口号
        agent_ip: 当前data_agent的IP地址
        agent_port: 当前data_agent的端口号
    
    Returns:
        成功返回True，失败返回False
    """
    import aiohttp
    
    # 使用连接器确保连接正确关闭，避免CLOSE_WAIT状态
    # force_close=True 确保连接在使用后立即关闭
    connector = aiohttp.TCPConnector(limit=10, limit_per_host=5, force_close=True)
    timeout = aiohttp.ClientTimeout(total=10, connect=5)
    
    try:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            url = f"http://{register_ip}:{register_port}/register"
            payload = {"ip": agent_ip, "port": agent_port}
            async with session.post(url, json=payload) as response:
                # 确保响应体被完全读取，避免连接处于CLOSE_WAIT状态
                if response.status == 200:
                    data = await response.json()
                    return data.get("status") == "ok"
                else:
                    # 即使状态码不是200，也要读取响应体以确保连接正确关闭
                    await response.read()
                return False
    except Exception as e:
        logger.error("[DataAgent] Failed to register to async_agent: %s", e)
        return False


async def run_data_agent(
    max_symbols: int = 100,
    command_host: str = '0.0.0.0',
    command_port: int = 9999,
    status_host: str = '0.0.0.0',
    status_port: int = 9988,
    register_ip: Optional[str] = None,
    register_port: Optional[int] = None,
    agent_ip: Optional[str] = None
) -> None:
    """运行data_agent主服务。
    
    Args:
        max_symbols: 最大symbol数量（每个symbol会自动创建7个interval的连接）
        command_host: 指令服务器监听地址
        command_port: 指令服务器端口（用于接收指令，如添加symbol等）
        status_host: 状态检查服务器监听地址
        status_port: 状态检查服务器端口（用于健康检查，独立端口避免指令服务阻塞）
        register_ip: async_agent的IP地址（用于注册和心跳）
        register_port: async_agent的端口号
        agent_ip: 当前data_agent的IP地址（用于注册）
    """
    db = MySQLDatabase()
    kline_manager = DataAgentKlineManager(db, max_symbols=max_symbols)
    
    # 启动指令服务器（处理添加symbol等指令）
    command_task = asyncio.create_task(
        run_data_agent_command_server(kline_manager, command_host, command_port)
    )
    
    # 启动状态检查服务器（独立端口，仅处理ping请求，避免指令服务阻塞）
    status_task = asyncio.create_task(
        run_data_agent_status_server(kline_manager, status_host, status_port)
    )
    
    # 等待服务器启动
    await asyncio.sleep(1)
    
    # 注册到async_agent（只注册一次，之后由manager主动轮询状态）
    register_task_obj = None
    # 确保agent_ip已定义（用于后续的定时更新任务）
    if not agent_ip:
        # 自动获取本机IP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            agent_ip = s.getsockname()[0]
            s.close()
        except Exception:
            agent_ip = "127.0.0.1"
    
    if register_ip and register_port:
        
        async def register_once_task():
            """注册任务：只尝试注册一次，成功后不再重试
            
            注意：注册成功后，agent的状态将由manager通过主动轮询来维护，
            不需要agent自己发送心跳。manager会通过market_data_agent表中的
            agent ip+port调用固定的接口（如/ping）来检查agent状态。
            """
            max_retries = 5  # 最多重试5次
            retry_interval = 10  # 重试间隔（秒）
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    retry_count += 1
                    logger.info("[DataAgent] Attempting to register to async_agent at %s:%s (attempt %s/%s)...", 
                               register_ip, register_port, retry_count, max_retries)
                    
                    success = await register_to_async_agent(register_ip, register_port, agent_ip, command_port)
                    if success:
                        logger.info("[DataAgent] ✅ Successfully registered to async_agent at %s:%s", 
                                   register_ip, register_port)
                        logger.info("[DataAgent] 📝 Note: Agent status will be maintained by manager through active polling")
                        return  # 注册成功，退出任务
                    else:
                        if retry_count < max_retries:
                            logger.warning("[DataAgent] Failed to register to async_agent, will retry in %s seconds (attempt %s/%s)", 
                                          retry_interval, retry_count, max_retries)
                            await asyncio.sleep(retry_interval)
                        else:
                            logger.error("[DataAgent] ❌ Failed to register after %s attempts, giving up", max_retries)
                            logger.error("[DataAgent] ⚠️  Agent will continue running but may not be managed by manager")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    if retry_count < max_retries:
                        logger.warning("[DataAgent] Registration attempt failed: %s, will retry in %s seconds (attempt %s/%s)", 
                                      e, retry_interval, retry_count, max_retries)
                        await asyncio.sleep(retry_interval)
                    else:
                        logger.error("[DataAgent] ❌ Registration failed after %s attempts: %s", max_retries, e)
        
        # 启动注册任务（只注册一次）
        register_task_obj = asyncio.create_task(register_once_task())
    
    # 定期检查连接状态（不关闭连接，因为K线监听应该长期运行）
    async def connection_check_task():
        """定期检查连接状态，但不关闭连接。
        
        注意：K线监听是长期运行的异步任务，连接应该一直保持活跃状态。
        此任务只用于监控连接状态，不会主动关闭连接。
        """
        while True:
            try:
                await asyncio.sleep(3600)  # 每小时检查一次
                await kline_manager.cleanup_expired_connections()  # 只检查，不关闭
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("[DataAgent] Error in connection check task: %s", e, exc_info=True)
    
    connection_check_task_obj = asyncio.create_task(connection_check_task())
    
    # 定期更新agent状态到数据库（只更新不新建）
    # 使用闭包变量确保agent_ip和command_port可用
    final_agent_ip = agent_ip or "127.0.0.1"
    final_command_port = command_port
    
    async def self_update_status_task():
        """定时更新agent自己的状态到数据库（只更新不新建）。"""
        from datetime import datetime, timezone
        import common.config as app_config
        
        update_interval = getattr(app_config, 'DATA_AGENT_SELF_UPDATE_INTERVAL', 60)  # 默认1分钟
        
        # 等待注册完成（最多等待60秒）
        if register_task_obj:
            try:
                await asyncio.wait_for(register_task_obj, timeout=60)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        
        while True:
            try:
                await asyncio.sleep(update_interval)
                
                # 获取当前agent状态
                status = await kline_manager.get_connection_status()
                connection_count = status.get("connection_count", 0)
                symbols_list = status.get("symbols", [])
                assigned_symbol_count = len(symbols_list)
                
                # 只更新connection_count和assigned_symbol_count字段，其他字段不更新
                db.update_agent_connection_info(
                    final_agent_ip,
                    final_command_port,
                    connection_count,
                    assigned_symbol_count
                )
                logger.debug(
                    "[DataAgent] Updated own connection info to DB: %s:%s, connections: %s, symbols: %s",
                    final_agent_ip, final_command_port, connection_count, assigned_symbol_count
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("[DataAgent] Error in self-update status task: %s", e, exc_info=True)
    
    self_update_task_obj = asyncio.create_task(self_update_status_task())
    
    try:
        logger.info("[DataAgent] ✅ Data agent started (指令端口: %s:%s, 状态端口: %s:%s)", 
                   command_host, command_port, status_host, status_port)
        tasks = [command_task, status_task, connection_check_task_obj, self_update_task_obj]
        if register_task_obj:
            tasks.append(register_task_obj)
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        raise
    finally:
        command_task.cancel()
        status_task.cancel()
        connection_check_task_obj.cancel()
        self_update_task_obj.cancel()
        if register_task_obj:
            register_task_obj.cancel()
        await kline_manager.cleanup_all()
        logger.info("[DataAgent] 🛑 Data agent stopped")


def _setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, app_config.LOG_LEVEL, logging.INFO),
        format=app_config.LOG_FORMAT,
        datefmt=app_config.LOG_DATE_FORMAT,
    )


def main() -> int:
    _setup_logging()
    
    max_symbols = getattr(app_config, 'DATA_AGENT_MAX_SYMBOL', 100)
    command_host = '0.0.0.0'
    command_port = getattr(app_config, 'DATA_AGENT_PORT', 9999)
    status_host = '0.0.0.0'
    status_port = getattr(app_config, 'DATA_AGENT_STATUS_PORT', 9988)
    register_ip = getattr(app_config, 'DATA_AGENT_REGISTER_IP', None)
    register_port = getattr(app_config, 'DATA_AGENT_REGISTER_PORT', None)
    agent_ip = getattr(app_config, 'DATA_AGENT_IP', None)
    
    logger.info("[DataAgent] 📋 配置信息:")
    logger.info("[DataAgent]   - 最大symbol数: %s", max_symbols)
    logger.info("[DataAgent]   - 指令服务: %s:%s", command_host, command_port)
    logger.info("[DataAgent]   - 状态服务: %s:%s", status_host, status_port)
    logger.info("[DataAgent]   - 注册地址: %s:%s", register_ip, register_port)
    logger.info("[DataAgent]   - Agent IP: %s", agent_ip)
    
    try:
        asyncio.run(run_data_agent(
            max_symbols=max_symbols,
            command_host=command_host,
            command_port=command_port,
            status_host=status_host,
            status_port=status_port,
            register_ip=register_ip,
            register_port=register_port,
            agent_ip=agent_ip
        ))
    except KeyboardInterrupt:
        logger.info("[DataAgent] Interrupted by user")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

