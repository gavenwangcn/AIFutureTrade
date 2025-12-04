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
from common.database_clickhouse import ClickHouseDatabase
from market.market_streams import _normalize_kline

logger = logging.getLogger(__name__)

# 支持的K线时间间隔
KLINE_INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d', '1w']

# WebSocket连接最大有效期（24小时）
WS_CONNECTION_MAX_AGE = timedelta(hours=24)


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
    """管理所有K线WebSocket连接。"""
    
    def __init__(self, db: ClickHouseDatabase, max_symbols: int = 100):
        self._db = db
        # 每个symbol有7个interval，所以最大连接数 = max_symbols * 7
        self._max_connections = max_symbols * len(KLINE_INTERVALS)
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
    
    async def _handle_kline_message(self, symbol: str, interval: str, message: Any) -> None:
        """处理K线消息并插入数据库。"""
        try:
            normalized = _normalize_kline(message)
            if normalized:
                await asyncio.to_thread(self._db.insert_market_klines, [normalized])
                logger.debug("[DataAgentKline] Inserted kline: %s %s", symbol, interval)
        except Exception as e:
            logger.error("[DataAgentKline] Error handling kline message: %s", e, exc_info=True)
    
    async def _init_client(self) -> None:
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
    
    async def add_stream(self, symbol: str, interval: str) -> bool:
        """添加K线流。
        
        Args:
            symbol: 交易对符号
            interval: 时间间隔
        
        Returns:
            成功返回True，失败返回False
        """
        stream_start_time = datetime.now(timezone.utc)
        
        if interval not in KLINE_INTERVALS:
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
            # 确保客户端已初始化（在事件循环中）
            init_client_start = datetime.now(timezone.utc)
            logger.info(
                "[DataAgentKline] 🔧 [添加流] 步骤1/6: 初始化客户端 %s %s...",
                symbol_upper, interval
            )
            await self._init_client()
            init_client_duration = (datetime.now(timezone.utc) - init_client_start).total_seconds()
            logger.info(
                "[DataAgentKline] ✅ [添加流] 步骤1/6: 客户端初始化完成 %s %s (耗时: %.3fs)",
                symbol_upper, interval, init_client_duration
            )
            
            # 控制订阅频率，确保每秒不超过10个订阅消息
            rate_limit_start = datetime.now(timezone.utc)
            logger.info(
                "[DataAgentKline] ⏱️  [添加流] 步骤2/6: 检查订阅频率限制 %s %s...",
                symbol_upper, interval
            )
            await self._rate_limit_subscription()
            rate_limit_duration = (datetime.now(timezone.utc) - rate_limit_start).total_seconds()
            logger.info(
                "[DataAgentKline] ✅ [添加流] 步骤2/6: 订阅频率检查通过 %s %s (耗时: %.3fs)",
                symbol_upper, interval, rate_limit_duration
            )
            
            # 根据SDK最佳实践，为每个symbol-interval对创建独立的WebSocket连接
            # 这是SDK推荐的方式，每个连接可以处理多个流，但为了隔离和管理方便，每个symbol-interval使用独立连接
            create_conn_start = datetime.now(timezone.utc)
            logger.info(
                "[DataAgentKline] 🔌 [添加流] 步骤3/6: 创建WebSocket连接 %s %s...",
                symbol_upper, interval
            )
            logger.debug(
                "[DataAgentKline] 🔌 [WebSocket创建] SDK调用前状态: client=%s, websocket_streams=%s",
                type(self._client).__name__ if self._client else None,
                type(self._client.websocket_streams).__name__ if self._client and hasattr(self._client, 'websocket_streams') else None
            )
            
            # 记录SDK调用前的详细信息
            sdk_call_start = datetime.now(timezone.utc)
            logger.debug(
                "[DataAgentKline] 🔌 [WebSocket创建] 开始调用SDK: self._client.websocket_streams.create_connection()"
            )
            
            try:
                connection = await self._client.websocket_streams.create_connection()
                sdk_call_duration = (datetime.now(timezone.utc) - sdk_call_start).total_seconds()
                logger.info(
                    "[DataAgentKline] 🔌 [WebSocket创建] SDK调用完成 %s %s (SDK调用耗时: %.3fs, 连接对象: %s, 连接ID: %s)",
                    symbol_upper, interval, sdk_call_duration, 
                    type(connection).__name__,
                    id(connection) if connection else None
                )
                logger.debug(
                    "[DataAgentKline] 🔌 [WebSocket创建] 连接对象详细信息: %s, 属性: %s",
                    connection,
                    [attr for attr in dir(connection) if not attr.startswith('_')][:10] if connection else None
                )
            except asyncio.TimeoutError as e:
                sdk_call_duration = (datetime.now(timezone.utc) - sdk_call_start).total_seconds()
                logger.error(
                    "[DataAgentKline] ❌ [WebSocket创建] SDK调用超时 %s %s (耗时: %.3fs): %s",
                    symbol_upper, interval, sdk_call_duration, e
                )
                raise
            except Exception as e:
                sdk_call_duration = (datetime.now(timezone.utc) - sdk_call_start).total_seconds()
                logger.error(
                    "[DataAgentKline] ❌ [WebSocket创建] SDK调用异常 %s %s (耗时: %.3fs): %s",
                    symbol_upper, interval, sdk_call_duration, e, exc_info=True
                )
                raise
            
            create_conn_duration = (datetime.now(timezone.utc) - create_conn_start).total_seconds()
            logger.info(
                "[DataAgentKline] ✅ [添加流] 步骤3/6: WebSocket连接创建成功 %s %s (总耗时: %.3fs, SDK调用耗时: %.3fs)",
                symbol_upper, interval, create_conn_duration, sdk_call_duration
            )
            
            # 设置连接级别的错误处理器（处理连接错误）
            register_error_handler_start = datetime.now(timezone.utc)
            logger.info(
                "[DataAgentKline] 🛡️  [添加流] 步骤4/6: 注册连接错误处理器 %s %s...",
                symbol_upper, interval
            )
            
            def connection_error_handler(error: Any) -> None:
                logger.error(
                    "[DataAgentKline] ❌ [连接错误] %s %s 连接错误: %s",
                    symbol_upper, interval, error
                )
                asyncio.create_task(self._remove_broken_connection(symbol_upper, interval))
            
            # 如果连接对象支持错误事件，注册错误处理器
            # 注意：某些SDK版本可能不支持"error"事件，使用try-except避免崩溃
            error_handler_registered = False
            if hasattr(connection, 'on'):
                try:
                    connection.on("error", connection_error_handler)
                    error_handler_registered = True
                    logger.info(
                        "[DataAgentKline] ✅ [添加流] 连接错误处理器注册成功 %s %s",
                        symbol_upper, interval
                    )
                except (AttributeError, TypeError, ValueError) as e:
                    logger.debug(
                        "[DataAgentKline] ⚠️  [添加流] 连接不支持'error'事件或已注册 %s %s: %s",
                        symbol_upper, interval, e
                    )
                except Exception as e:
                    # 捕获所有其他异常，避免因为事件注册失败导致整个流创建失败
                    logger.warning(
                        "[DataAgentKline] ⚠️  [添加流] 注册连接错误处理器失败（非关键）%s %s: %s",
                        symbol_upper, interval, e
                    )
            else:
                logger.debug(
                    "[DataAgentKline] ⚠️  [添加流] 连接对象不支持'on'方法 %s %s",
                    symbol_upper, interval
                )
            
            register_error_handler_duration = (datetime.now(timezone.utc) - register_error_handler_start).total_seconds()
            logger.info(
                "[DataAgentKline] ✅ [添加流] 步骤4/6: 错误处理器注册完成 %s %s (耗时: %.3fs, 已注册: %s)",
                symbol_upper, interval, register_error_handler_duration, error_handler_registered
            )
            
            # 订阅K线流
            subscribe_start = datetime.now(timezone.utc)
            logger.info(
                "[DataAgentKline] 📡 [添加流] 步骤5/6: 订阅K线流 %s %s (symbol=%s, interval=%s)...",
                symbol_upper, interval, symbol.lower(), interval
            )
            logger.debug(
                "[DataAgentKline] 📡 [订阅流] SDK调用前状态: connection=%s, connection_id=%s",
                type(connection).__name__ if connection else None,
                id(connection) if connection else None
            )
            
            # 记录SDK订阅调用前的详细信息
            subscribe_sdk_start = datetime.now(timezone.utc)
            logger.debug(
                "[DataAgentKline] 📡 [订阅流] 开始调用SDK: connection.kline_candlestick_streams(symbol='%s', interval='%s')",
                symbol.lower(), interval
            )
            
            try:
                stream = await connection.kline_candlestick_streams(
                    symbol=symbol.lower(),
                    interval=interval
                )
                subscribe_sdk_duration = (datetime.now(timezone.utc) - subscribe_sdk_start).total_seconds()
                logger.info(
                    "[DataAgentKline] 📡 [订阅流] SDK调用完成 %s %s (SDK调用耗时: %.3fs, 流对象: %s, 流ID: %s)",
                    symbol_upper, interval, subscribe_sdk_duration,
                    type(stream).__name__,
                    id(stream) if stream else None
                )
                logger.debug(
                    "[DataAgentKline] 📡 [订阅流] 流对象详细信息: %s, 属性: %s",
                    stream,
                    [attr for attr in dir(stream) if not attr.startswith('_')][:10] if stream else None
                )
            except asyncio.TimeoutError as e:
                subscribe_sdk_duration = (datetime.now(timezone.utc) - subscribe_sdk_start).total_seconds()
                logger.error(
                    "[DataAgentKline] ❌ [订阅流] SDK调用超时 %s %s (耗时: %.3fs): %s",
                    symbol_upper, interval, subscribe_sdk_duration, e
                )
                raise
            except Exception as e:
                subscribe_sdk_duration = (datetime.now(timezone.utc) - subscribe_sdk_start).total_seconds()
                logger.error(
                    "[DataAgentKline] ❌ [订阅流] SDK调用异常 %s %s (耗时: %.3fs): %s",
                    symbol_upper, interval, subscribe_sdk_duration, e, exc_info=True
                )
                raise
            
            subscribe_duration = (datetime.now(timezone.utc) - subscribe_start).total_seconds()
            logger.info(
                "[DataAgentKline] ✅ [添加流] 步骤5/6: K线流订阅成功 %s %s (总耗时: %.3fs, SDK调用耗时: %.3fs)",
                symbol_upper, interval, subscribe_duration, subscribe_sdk_duration
            )
            
            # 设置消息处理器
            register_handler_start = datetime.now(timezone.utc)
            logger.info(
                "[DataAgentKline] 📨 [添加流] 步骤6/6: 注册消息和错误处理器 %s %s...",
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
            
            # 设置流级别的错误处理器，当流异常时从map中删除
            def stream_error_handler(error: Any) -> None:
                logger.error(
                    "[DataAgentKline] ❌ [流错误] %s %s 流错误: %s",
                    symbol_upper, interval, error
                )
                asyncio.create_task(self._remove_broken_connection(symbol_upper, interval))
            
            # 注册消息处理器
            message_handler_registered = False
            stream_error_handler_registered = False
            
            try:
                if hasattr(stream, 'on'):
                    stream.on("message", handler)
                    message_handler_registered = True
                    logger.info(
                        "[DataAgentKline] ✅ [添加流] 消息处理器注册成功 %s %s",
                        symbol_upper, interval
                    )
                else:
                    logger.warning(
                        "[DataAgentKline] ⚠️  [添加流] 流对象不支持'on'方法 %s %s",
                        symbol_upper, interval
                    )
            except Exception as e:
                logger.error(
                    "[DataAgentKline] ❌ [添加流] 注册消息处理器失败 %s %s: %s",
                    symbol_upper, interval, e, exc_info=True
                )
            
            # 尝试注册流级别的错误处理器（如果SDK支持）
            # 注意：某些SDK版本可能不支持"error"事件，使用try-except避免崩溃
            try:
                if hasattr(stream, 'on'):
                    stream.on("error", stream_error_handler)
                    stream_error_handler_registered = True
                    logger.info(
                        "[DataAgentKline] ✅ [添加流] 流错误处理器注册成功 %s %s",
                        symbol_upper, interval
                    )
            except (AttributeError, TypeError, ValueError) as e:
                logger.debug(
                    "[DataAgentKline] ⚠️  [添加流] 流不支持'error'事件或已注册 %s %s: %s",
                    symbol_upper, interval, e
                )
            except Exception as e:
                # 捕获所有其他异常，避免因为事件注册失败导致整个流创建失败
                logger.warning(
                    "[DataAgentKline] ⚠️  [添加流] 注册流错误处理器失败（非关键）%s %s: %s",
                    symbol_upper, interval, e
                )
            
            register_handler_duration = (datetime.now(timezone.utc) - register_handler_start).total_seconds()
            logger.info(
                "[DataAgentKline] ✅ [添加流] 步骤6/6: 处理器注册完成 %s %s (耗时: %.3fs, 消息处理器: %s, 错误处理器: %s)",
                symbol_upper, interval, register_handler_duration, message_handler_registered, stream_error_handler_registered
            )
            
            # 创建连接对象并保存到map
            save_conn_start = datetime.now(timezone.utc)
            logger.info(
                "[DataAgentKline] 💾 [添加流] 保存连接对象到map %s %s...",
                symbol_upper, interval
            )
            
            # 需要再次获取锁来保存连接对象
            save_lock_start = datetime.now(timezone.utc)
            logger.debug(
                "[DataAgentKline] 🔒 [添加流] 获取锁以保存连接对象 %s %s...",
                symbol_upper, interval
            )
            async with self._lock:
                save_lock_duration = (datetime.now(timezone.utc) - save_lock_start).total_seconds()
                logger.debug(
                    "[DataAgentKline] ✅ [添加流] 锁获取成功（保存）%s %s (耗时: %.3fs)",
                    symbol_upper, interval, save_lock_duration
                )
                
                conn = KlineStreamConnection(
                    symbol=symbol_upper,
                    interval=interval,
                    connection=connection,
                    stream=stream,
                    created_at=datetime.now(timezone.utc)
                )
                
                self._active_connections[key] = conn
                save_conn_duration = (datetime.now(timezone.utc) - save_conn_start).total_seconds()
                logger.info(
                    "[DataAgentKline] ✅ [添加流] 连接对象已保存 %s %s (耗时: %.3fs, 当前连接数: %s)",
                    symbol_upper, interval, save_conn_duration, len(self._active_connections)
                )
            
            logger.debug(
                "[DataAgentKline] 🔓 [添加流] 锁已释放（保存后）%s %s",
                symbol_upper, interval
            )
            
            stream_duration = (datetime.now(timezone.utc) - stream_start_time).total_seconds()
            logger.info(
                "[DataAgentKline] ✅ [添加流] %s %s 全部完成！(总耗时: %.3fs, 步骤耗时: 初始化=%.3fs, 频率限制=%.3fs, 创建连接=%.3fs, 订阅=%.3fs, 注册处理器=%.3fs, 保存=%.3fs)",
                symbol_upper, interval, stream_duration,
                init_client_duration, rate_limit_duration, create_conn_duration,
                subscribe_duration, register_error_handler_duration + register_handler_duration, save_conn_duration
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
        """为指定symbol添加所有interval的K线流（7个interval）。
        
        在构建每个interval的监听连接前，会检查map中是否已经存在对应的连接。
        
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
            "[DataAgentKline] 🔨 [构建K线监听] 开始为 symbol %s 构建所有interval的K线流",
            symbol_upper
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
            for interval in KLINE_INTERVALS:
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
            symbol_upper, len(existing_intervals), len(KLINE_INTERVALS)
        )
        
        # 只为不存在的interval创建连接
        for idx, interval in enumerate(KLINE_INTERVALS):
            interval_start_time = datetime.now(timezone.utc)
            
            if interval in existing_intervals:
                skipped_count += 1
                logger.debug(
                    "[DataAgentKline] ⏭️  [构建K线监听] 跳过 %s %s (已存在活跃连接)",
                    symbol_upper, interval
                )
                continue
            
            logger.info(
                "[DataAgentKline] 🔨 [构建K线监听] 开始构建 %s %s (%s/%s)",
                symbol_upper, interval, idx + 1, len(KLINE_INTERVALS)
            )
            
            try:
                # add_stream内部会再次检查map，确保不会重复创建
                success = await self.add_stream(symbol_upper, interval)
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
                    "[DataAgentKline] ❌ [构建K线监听] %s %s 构建超时 (耗时: %.3fs): %s",
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
            "total_count": len(KLINE_INTERVALS)
        }
        
        logger.info(
            "[DataAgentKline] ✅ [构建K线监听] %s 构建完成 (总耗时: %.3fs, 结果: %s)",
            symbol_upper, method_duration, result
        )
        
        return result
    
    async def remove_stream(self, symbol: str, interval: str) -> bool:
        """移除K线流。
        
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
    
    async def cleanup_expired_connections(self) -> None:
        """清理过期的连接（超过24小时）。"""
        async with self._lock:
            expired_keys = []
            for key, conn in self._active_connections.items():
                if conn.is_expired():
                    expired_keys.append(key)
            
            for key in expired_keys:
                conn = self._active_connections[key]
                await conn.close()
                del self._active_connections[key]
                logger.info("[DataAgentKline] Cleaned up expired connection: %s %s", key[0], key[1])
    
    async def get_connection_count(self) -> int:
        """获取当前连接数。"""
        async with self._lock:
            # 先清理过期连接和断开的连接
            await self.cleanup_expired_connections()
            await self._cleanup_broken_connections()
            return len(self._active_connections)
    
    async def get_connection_status(self) -> Dict[str, Any]:
        """获取当前连接状态（JSON格式）。
        
        Returns:
            包含总连接数和详细symbol列表的字典
            {
                "connection_count": int,  # 总连接数（根据symbol数量 * 7个interval计算）
                "symbols": [str, ...]  # symbol列表，不包含interval信息
            }
        """
        async with self._lock:
            # 先清理过期连接和断开的连接
            await self.cleanup_expired_connections()
            await self._cleanup_broken_connections()
            
            # 获取所有唯一的symbol（不包含interval信息）
            symbols_set = set()
            for key, conn in self._active_connections.items():
                symbols_set.add(conn.symbol)
            
            # 计算总连接数（每个symbol有7个interval）
            connection_count = len(symbols_set) * len(KLINE_INTERVALS)
            
            return {
                "connection_count": connection_count,
                "symbols": sorted(list(symbols_set))
            }
    
    async def _cleanup_broken_connections(self) -> None:
        """清理断开的连接（检查连接是否仍然活跃）。"""
        broken_keys = []
        for key, conn in self._active_connections.items():
            if not conn.is_active:
                broken_keys.append(key)
        
        for key in broken_keys:
            conn = self._active_connections[key]
            try:
                await conn.close()
            except Exception as e:
                logger.debug("[DataAgentKline] Error closing broken connection: %s", e)
            del self._active_connections[key]
            logger.info("[DataAgentKline] Cleaned up broken connection: %s %s", key[0], key[1])
    
    async def get_connection_list(self) -> List[Dict[str, Any]]:
        """获取当前所有连接的详细信息。"""
        async with self._lock:
            await self.cleanup_expired_connections()
            await self._cleanup_broken_connections()
            connections = []
            for key, conn in self._active_connections.items():
                connections.append({
                    "symbol": conn.symbol,
                    "interval": conn.interval,
                    "created_at": conn.created_at.isoformat(),
                    "is_active": conn.is_active,
                })
            return connections
    
    async def get_symbols(self) -> Set[str]:
        """获取当前所有正在同步的symbol。"""
        async with self._lock:
            await self.cleanup_expired_connections()
            symbols = set()
            for key, conn in self._active_connections.items():
                symbols.add(conn.symbol)
            return symbols
    
    async def _periodic_connection_check(self) -> None:
        """定期检查连接状态，处理过期连接和重连。"""
        while not self._is_closing:
            try:
                await asyncio.sleep(3600)  # 每小时检查一次
                
                async with self._lock:
                    # 复制当前连接列表，避免在迭代过程中修改
                    connections_to_check = list(self._active_connections.items())
                
                for key, conn in connections_to_check:
                    try:
                        # 检查连接是否接近过期（剩余时间少于1小时）
                        time_until_expiry = conn.created_at + self._connection_max_age - datetime.now(timezone.utc)
                        if time_until_expiry < timedelta(hours=1):
                            logger.info("[DataAgentKline] Connection %s %s is approaching expiry, reconnecting...", 
                                      conn.symbol, conn.interval)
                            
                            # 重新连接
                            async with self._lock:
                                if key in self._active_connections:
                                    # 先关闭旧连接
                                    await self._active_connections[key].close()
                                    del self._active_connections[key]
                                    
                                    # 再创建新连接
                                    await self.add_stream(conn.symbol, conn.interval)
                    except Exception as e:
                        logger.error("[DataAgentKline] Error handling connection %s %s: %s", 
                                  conn.symbol, conn.interval, e, exc_info=True)
            except asyncio.CancelledError:
                logger.info("[DataAgentKline] Periodic connection check task cancelled")
                raise
            except Exception as e:
                logger.error("[DataAgentKline] Error in periodic connection check: %s", e, exc_info=True)
    
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
    
    async def cleanup_all(self) -> None:
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
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
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
            self.wfile.write(json.dumps({"error": message}, ensure_ascii=False).encode('utf-8'))
        except BrokenPipeError:
            logger.debug("[DataAgentStatus] Broken pipe error when sending error response")
        except Exception as e:
            logger.warning("[DataAgentStatus] Error when sending error response: %s", e)
    
    def log_message(self, format, *args):
        """重写日志方法，使用自定义logger。"""
        logger.debug("[DataAgentStatus] %s", format % args)


class DataAgentCommandHandler(BaseHTTPRequestHandler):
    """处理data_agent的HTTP指令请求。"""
    
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
        """处理POST请求。"""
        try:
            parsed_path = urllib.parse.urlparse(self.path)
            path = parsed_path.path
            
            if path == '/streams/add':
                # 添加K线流
                self._handle_add_stream()
            elif path == '/streams/remove':
                # 移除K线流
                self._handle_remove_stream()
            elif path == '/symbols/add':
                # 批量添加symbol（为每个symbol创建7个interval的流）
                self._handle_add_symbols()
            else:
                self._send_error(404, "Not Found")
        except Exception as e:
            logger.error("[DataAgentCommand] Error handling POST request: %s", e, exc_info=True)
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
        try:
            # 使用主事件循环执行异步操作
            coro = self.kline_manager.get_connection_count()
            future = asyncio.run_coroutine_threadsafe(coro, self._main_loop)
            count = future.result()  # 等待结果
            self._send_json({"connection_count": count})
        except Exception as e:
            logger.error("[DataAgentCommand] Error in get_connection_count: %s", e, exc_info=True)
            self._send_error(500, str(e))
    
    def _handle_get_connection_list(self):
        """处理获取连接列表请求。"""
        try:
            # 使用主事件循环执行异步操作
            coro = self.kline_manager.get_connection_list()
            future = asyncio.run_coroutine_threadsafe(coro, self._main_loop)
            connections = future.result()  # 等待结果
            self._send_json({"connections": connections, "count": len(connections)})
        except Exception as e:
            logger.error("[DataAgentCommand] Error in get_connection_list: %s", e, exc_info=True)
            self._send_error(500, str(e))
    
    def _handle_get_symbols(self):
        """处理获取symbol列表请求。"""
        try:
            # 使用主事件循环执行异步操作
            coro = self.kline_manager.get_symbols()
            future = asyncio.run_coroutine_threadsafe(coro, self._main_loop)
            symbols = future.result()  # 等待结果
            self._send_json({"symbols": sorted(list(symbols)), "count": len(symbols)})
        except Exception as e:
            logger.error("[DataAgentCommand] Error in get_symbols: %s", e, exc_info=True)
            self._send_error(500, str(e))
    
    def _handle_get_status(self):
        """处理获取连接状态请求（返回JSON格式：总连接数和symbol列表）。"""
        try:
            coro = self.kline_manager.get_connection_status()
            future = asyncio.run_coroutine_threadsafe(coro, self._main_loop)
            status = future.result()
            self._send_json({"status": "ok", **status})
        except Exception as e:
            logger.error("[DataAgentCommand] Error in get_status: %s", e, exc_info=True)
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
            success = future.result()  # 等待结果
            if success:
                self._send_json({"status": "ok", "message": f"Added stream for {symbol} {interval}"})
            else:
                self._send_error(500, f"Failed to add stream for {symbol} {interval}")
        except Exception as e:
            logger.error("[DataAgentCommand] Error in add_stream: %s", e, exc_info=True)
            self._send_error(500, str(e))
    
    def _handle_remove_stream(self):
        """处理移除K线流请求。"""
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
            success = future.result()  # 等待结果
            if success:
                self._send_json({"status": "ok", "message": f"Removed stream for {symbol} {interval}"})
            else:
                self._send_error(500, f"Failed to remove stream for {symbol} {interval}")
        except Exception as e:
            logger.error("[DataAgentCommand] Error in remove_stream: %s", e, exc_info=True)
            self._send_error(500, str(e))
    
    def _send_json(self, data: Dict[str, Any]):
        """发送JSON响应。"""
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
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
            self.wfile.write(json.dumps({"error": message}, ensure_ascii=False).encode('utf-8'))
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
    main_loop = asyncio.get_event_loop()
    handler = create_command_handler(kline_manager, main_loop)
    server = HTTPServer((host, port), handler)
    logger.info("[DataAgent] 📡 [指令服务] 启动指令服务器 %s:%s", host, port)
    
    def run_server():
        try:
            server.serve_forever()
        except Exception as e:
            logger.error("[DataAgent] ❌ [指令服务] 服务器运行异常: %s", e, exc_info=True)
    
    server_thread = threading.Thread(target=run_server, daemon=True, name="DataAgentCommandServer")
    server_thread.start()
    
    # 等待服务器启动
    await asyncio.sleep(0.5)
    logger.info("[DataAgent] ✅ [指令服务] 指令服务器已启动并运行中")
    
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
    server = HTTPServer((host, port), handler)
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
    db = ClickHouseDatabase()
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
    
    # 定期清理过期连接
    async def cleanup_task():
        while True:
            try:
                await asyncio.sleep(3600)  # 每小时清理一次
                await kline_manager.cleanup_expired_connections()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("[DataAgent] Error in cleanup task: %s", e, exc_info=True)
    
    cleanup_task_obj = asyncio.create_task(cleanup_task())
    
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
        tasks = [command_task, status_task, cleanup_task_obj, self_update_task_obj]
        if register_task_obj:
            tasks.append(register_task_obj)
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        raise
    finally:
        command_task.cancel()
        status_task.cancel()
        cleanup_task_obj.cancel()
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

