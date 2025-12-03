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
    
    def __init__(self, db: ClickHouseDatabase, max_connections: int = 1000):
        self._db = db
        self._max_connections = max_connections
        configuration_ws_streams = ConfigurationWebSocketStreams(
            stream_url=os.getenv(
                "STREAM_URL",
                DERIVATIVES_TRADING_USDS_FUTURES_WS_STREAMS_PROD_URL,
            )
        )
        self._client = DerivativesTradingUsdsFutures(
            config_ws_streams=configuration_ws_streams
        )
        # 跟踪活跃连接: {(symbol, interval): KlineStreamConnection}
        self._active_connections: Dict[Tuple[str, str], KlineStreamConnection] = {}
        self._lock = asyncio.Lock()
    
    async def _handle_kline_message(self, symbol: str, interval: str, message: Any) -> None:
        """处理K线消息并插入数据库。"""
        try:
            normalized = _normalize_kline(message)
            if normalized:
                await asyncio.to_thread(self._db.insert_market_klines, [normalized])
                logger.debug("[DataAgentKline] Inserted kline: %s %s", symbol, interval)
        except Exception as e:
            logger.error("[DataAgentKline] Error handling kline message: %s", e, exc_info=True)
    
    async def add_stream(self, symbol: str, interval: str) -> bool:
        """添加K线流。
        
        Args:
            symbol: 交易对符号
            interval: 时间间隔
        
        Returns:
            成功返回True，失败返回False
        """
        if interval not in KLINE_INTERVALS:
            logger.warning("[DataAgentKline] Unsupported interval: %s", interval)
            return False
        
        key = (symbol.upper(), interval)
        
        async with self._lock:
            # 检查是否已存在
            if key in self._active_connections:
                conn = self._active_connections[key]
                # 如果连接未过期，直接返回
                if not conn.is_expired():
                    logger.debug("[DataAgentKline] Stream already exists: %s %s", symbol, interval)
                    return True
                # 如果连接已过期，先关闭
                await conn.close()
                del self._active_connections[key]
            
            # 检查连接数限制
            if len(self._active_connections) >= self._max_connections:
                logger.warning(
                    "[DataAgentKline] Max connections reached (%s), cannot add %s %s",
                    self._max_connections, symbol, interval
                )
                return False
            
            try:
                connection = await self._client.websocket_streams.create_connection()
                if not connection:
                    logger.error("[DataAgentKline] Failed to create WebSocket connection: connection is None")
                    return False
                
                stream = await connection.kline_candlestick_streams(
                    symbol=symbol.lower(),
                    interval=interval
                )
                if not stream:
                    logger.error("[DataAgentKline] Failed to create kline stream: stream is None")
                    await connection.close_connection()
                    return False
                
                # 设置消息处理器
                def handler(data: Any) -> None:
                    asyncio.create_task(self._handle_kline_message(symbol, interval, data))
                
                stream.on("message", handler)
                
                conn = KlineStreamConnection(
                    symbol=symbol,
                    interval=interval,
                    connection=connection,
                    stream=stream,
                    created_at=datetime.now(timezone.utc)
                )
                
                self._active_connections[key] = conn
                logger.info("[DataAgentKline] Added stream: %s %s", symbol, interval)
                return True
            except asyncio.CancelledError:
                logger.info("[DataAgentKline] Add stream task cancelled: %s %s", symbol, interval)
                raise
            except RuntimeError as e:
                if "Event loop is closed" in str(e):
                    logger.error("[DataAgentKline] Failed to add stream %s %s: Event loop is closed", symbol, interval)
                else:
                    logger.error("[DataAgentKline] Failed to add stream %s %s: %s", symbol, interval, e)
                return False
            except AttributeError as e:
                logger.error("[DataAgentKline] Failed to add stream %s %s: %s", symbol, interval, e)
                # 如果连接已创建但添加流失败，尝试关闭连接
                if 'connection' in locals() and connection:
                    try:
                        await connection.close_connection()
                    except Exception as close_e:
                        logger.debug("[DataAgentKline] Failed to close connection: %s", close_e)
                return False
            except Exception as e:
                logger.error("[DataAgentKline] Failed to add stream %s %s: %s", symbol, interval, e)
                # 如果连接已创建但添加流失败，尝试关闭连接
                if 'connection' in locals() and connection:
                    try:
                        await connection.close_connection()
                    except Exception as close_e:
                        logger.debug("[DataAgentKline] Failed to close connection: %s", close_e)
                return False
    
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
            # 先清理过期连接
            await self.cleanup_expired_connections()
            return len(self._active_connections)
    
    async def get_connection_list(self) -> List[Dict[str, Any]]:
        """获取当前所有连接的详细信息。"""
        async with self._lock:
            await self.cleanup_expired_connections()
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
    
    async def cleanup_all(self) -> None:
        """清理所有连接。"""
        async with self._lock:
            keys = list(self._active_connections.keys())
            for key in keys:
                conn = self._active_connections[key]
                await conn.close()
                del self._active_connections[key]


class DataAgentCommandHandler(BaseHTTPRequestHandler):
    """处理data_agent的HTTP指令请求。"""
    
    def __init__(self, kline_manager: DataAgentKlineManager, *args, **kwargs):
        self.kline_manager = kline_manager
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
            else:
                self._send_error(404, "Not Found")
        except Exception as e:
            logger.error("[DataAgentCommand] Error handling POST request: %s", e, exc_info=True)
            self._send_error(500, str(e))
    
    def _handle_ping(self):
        """处理ping请求。"""
        self._send_json({"status": "ok", "message": "pong"})
    
    def _handle_get_connection_count(self):
        """处理获取连接数请求。"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            count = loop.run_until_complete(self.kline_manager.get_connection_count())
            self._send_json({"connection_count": count})
        finally:
            loop.close()
    
    def _handle_get_connection_list(self):
        """处理获取连接列表请求。"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            connections = loop.run_until_complete(self.kline_manager.get_connection_list())
            self._send_json({"connections": connections, "count": len(connections)})
        finally:
            loop.close()
    
    def _handle_get_symbols(self):
        """处理获取symbol列表请求。"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            symbols = loop.run_until_complete(self.kline_manager.get_symbols())
            self._send_json({"symbols": sorted(list(symbols)), "count": len(symbols)})
        finally:
            loop.close()
    
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
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            success = loop.run_until_complete(self.kline_manager.add_stream(symbol, interval))
            if success:
                self._send_json({"status": "ok", "message": f"Added stream for {symbol} {interval}"})
            else:
                self._send_error(500, f"Failed to add stream for {symbol} {interval}")
        finally:
            loop.close()
    
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
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            success = loop.run_until_complete(self.kline_manager.remove_stream(symbol, interval))
            if success:
                self._send_json({"status": "ok", "message": f"Removed stream for {symbol} {interval}"})
            else:
                self._send_error(500, f"Failed to remove stream for {symbol} {interval}")
        finally:
            loop.close()
    
    def _send_json(self, data: Dict[str, Any]):
        """发送JSON响应。"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def _send_error(self, code: int, message: str):
        """发送错误响应。"""
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}, ensure_ascii=False).encode('utf-8'))
    
    def log_message(self, format, *args):
        """重写日志方法，使用自定义logger。"""
        logger.debug("[DataAgentCommand] %s", format % args)


def create_handler(kline_manager: DataAgentKlineManager):
    """创建请求处理器工厂函数。"""
    def handler(*args, **kwargs):
        return DataAgentCommandHandler(kline_manager, *args, **kwargs)
    return handler


async def run_data_agent_command_server(
    kline_manager: DataAgentKlineManager,
    host: str = '0.0.0.0',
    port: int = 9999
) -> None:
    """运行data_agent的HTTP指令服务器。"""
    handler = create_handler(kline_manager)
    server = HTTPServer((host, port), handler)
    logger.info("[DataAgent] Command server started on %s:%s", host, port)
    
    def run_server():
        server.serve_forever()
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # 等待服务器启动
    await asyncio.sleep(0.5)
    
    try:
        # 保持运行
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        raise
    finally:
        server.shutdown()
        logger.info("[DataAgent] Command server stopped")


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
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"http://{register_ip}:{register_port}/register"
            payload = {"ip": agent_ip, "port": agent_port}
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("status") == "ok"
                return False
    except Exception as e:
        logger.error("[DataAgent] Failed to register to async_agent: %s", e)
        return False


async def send_heartbeat(register_ip: str, register_port: int, agent_ip: str, agent_port: int) -> bool:
    """发送心跳到async_agent。
    
    Args:
        register_ip: async_agent的IP地址
        register_port: async_agent的端口号
        agent_ip: 当前data_agent的IP地址
        agent_port: 当前data_agent的端口号
    
    Returns:
        成功返回True，失败返回False
    """
    import aiohttp
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"http://{register_ip}:{register_port}/heartbeat"
            payload = {"ip": agent_ip, "port": agent_port}
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    return True
                return False
    except Exception as e:
        logger.debug("[DataAgent] Failed to send heartbeat: %s", e)
        return False


async def run_data_agent(
    max_connections: int = 1000,
    command_host: str = '0.0.0.0',
    command_port: int = 9999,
    register_ip: Optional[str] = None,
    register_port: Optional[int] = None,
    agent_ip: Optional[str] = None
) -> None:
    """运行data_agent主服务。
    
    Args:
        max_connections: 最大连接数
        command_host: 指令服务器监听地址
        command_port: 指令服务器端口
        register_ip: async_agent的IP地址（用于注册和心跳）
        register_port: async_agent的端口号
        agent_ip: 当前data_agent的IP地址（用于注册）
    """
    db = ClickHouseDatabase()
    kline_manager = DataAgentKlineManager(db, max_connections=max_connections)
    
    # 启动指令服务器
    command_task = asyncio.create_task(
        run_data_agent_command_server(kline_manager, command_host, command_port)
    )
    
    # 等待服务器启动
    await asyncio.sleep(1)
    
    # 注册到async_agent（带重试机制）
    heartbeat_task_obj = None
    register_retry_task_obj = None
    if register_ip and register_port:
        if not agent_ip:
            # 自动获取本机IP
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                agent_ip = s.getsockname()[0]
                s.close()
            except Exception:
                agent_ip = "127.0.0.1"
        
        # 使用 Event 来管理注册状态
        registered_event = asyncio.Event()
        register_retry_interval = 10  # 重试间隔（秒）
        
        async def register_retry_task():
            """注册重试任务，定期尝试注册直到成功"""
            retry_count = 0
            
            while True:
                try:
                    retry_count += 1
                    logger.info("[DataAgent] Attempting to register to async_agent at %s:%s (attempt %s)...", 
                               register_ip, register_port, retry_count)
                    
                    success = await register_to_async_agent(register_ip, register_port, agent_ip, command_port)
                    if success:
                        registered_event.set()
                        logger.info("[DataAgent] Successfully registered to async_agent at %s:%s", 
                                   register_ip, register_port)
                        break  # 注册成功，退出循环
                    else:
                        logger.warning("[DataAgent] Failed to register to async_agent, will retry in %s seconds", 
                                      register_retry_interval)
                        await asyncio.sleep(register_retry_interval)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning("[DataAgent] Registration attempt failed: %s, will retry in %s seconds", 
                                  e, register_retry_interval)
                    await asyncio.sleep(register_retry_interval)
        
        # 启动注册重试任务
        register_retry_task_obj = asyncio.create_task(register_retry_task())
        
        # 定期发送心跳（仅在注册成功后）
        heartbeat_interval = getattr(app_config, 'DATA_AGENT_HEARTBEAT_INTERVAL', 30)
        
        async def heartbeat_task():
            """心跳任务，等待注册成功后再开始发送心跳"""
            # 等待注册成功
            await registered_event.wait()
            
            # 注册成功后开始发送心跳
            while True:
                try:
                    await asyncio.sleep(heartbeat_interval)
                    success = await send_heartbeat(register_ip, register_port, agent_ip, command_port)
                    if not success:
                        # 心跳失败，可能连接已断开，尝试重新注册
                        logger.warning("[DataAgent] Heartbeat failed, attempting to re-register...")
                        registered_event.clear()
                        # 重新启动注册任务
                        asyncio.create_task(register_retry_task())
                        # 等待重新注册成功
                        await registered_event.wait()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error("[DataAgent] Error in heartbeat task: %s", e, exc_info=True)
        
        heartbeat_task_obj = asyncio.create_task(heartbeat_task())
    
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
    
    try:
        logger.info("[DataAgent] Data agent started")
        tasks = [command_task, cleanup_task_obj]
        if heartbeat_task_obj:
            tasks.append(heartbeat_task_obj)
        if register_retry_task_obj:
            tasks.append(register_retry_task_obj)
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        raise
    finally:
        command_task.cancel()
        cleanup_task_obj.cancel()
        if heartbeat_task_obj:
            heartbeat_task_obj.cancel()
        if register_retry_task_obj:
            register_retry_task_obj.cancel()
        await kline_manager.cleanup_all()
        logger.info("[DataAgent] Data agent stopped")


def _setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, app_config.LOG_LEVEL, logging.INFO),
        format=app_config.LOG_FORMAT,
        datefmt=app_config.LOG_DATE_FORMAT,
    )


def main() -> int:
    _setup_logging()
    
    max_connections = getattr(app_config, 'DATA_AGENT_MAX_CONNECTIONS', 1000)
    command_host = '0.0.0.0'
    command_port = getattr(app_config, 'DATA_AGENT_PORT', 9999)
    register_ip = getattr(app_config, 'DATA_AGENT_REGISTER_IP', None)
    register_port = getattr(app_config, 'DATA_AGENT_REGISTER_PORT', None)
    agent_ip = getattr(app_config, 'DATA_AGENT_IP', None)
    
    try:
        asyncio.run(run_data_agent(
            max_connections=max_connections,
            command_host=command_host,
            command_port=command_port,
            register_ip=register_ip,
            register_port=register_port,
            agent_ip=agent_ip
        ))
    except KeyboardInterrupt:
        logger.info("[DataAgent] Interrupted by user")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

