"""Data agent manager for async_agent.

This module manages data_agent registration, heartbeat, and task distribution.
"""
from __future__ import annotations

import asyncio
import json
import logging
import socket
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import urllib.parse
import aiohttp

import common.config as app_config
from common.database_clickhouse import ClickHouseDatabase

logger = logging.getLogger(__name__)


class DataAgentInfo:
    """Data agent信息类。"""
    
    def __init__(self, ip: str, port: int):
        self.ip = ip
        self.port = port
        self.status = "offline"
        self.connection_count = 0
        self.assigned_symbol_count = 0
        self.assigned_symbols: Set[str] = set()
        self.error_log = ""
        self.last_heartbeat: Optional[datetime] = None
        self.register_time: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "ip": self.ip,
            "port": self.port,
            "status": self.status,
            "connection_count": self.connection_count,
            "assigned_symbol_count": self.assigned_symbol_count,
            "assigned_symbols": sorted(list(self.assigned_symbols)),
            "error_log": self.error_log,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "register_time": self.register_time.isoformat() if self.register_time else None,
        }


class DataAgentManager:
    """管理所有data_agent。"""
    
    def __init__(self, db: ClickHouseDatabase):
        self._db = db
        self._agents: Dict[tuple, DataAgentInfo] = {}  # {(ip, port): DataAgentInfo}
        self._lock = asyncio.Lock()
        self._max_connections_per_agent = getattr(app_config, 'DATA_AGENT_MAX_CONNECTIONS', 1000)
        self._heartbeat_timeout = getattr(app_config, 'DATA_AGENT_HEARTBEAT_TIMEOUT', 60)
    
    async def register_agent(self, ip: str, port: int) -> bool:
        """注册data_agent。
        
        Args:
            ip: agent的IP地址
            port: agent的端口号
        
        Returns:
            成功返回True，失败返回False
        """
        async with self._lock:
            key = (ip, port)
            if key in self._agents:
                agent = self._agents[key]
                agent.status = "online"
                agent.last_heartbeat = datetime.now(timezone.utc)
                if agent.register_time is None:
                    agent.register_time = datetime.now(timezone.utc)
            else:
                agent = DataAgentInfo(ip, port)
                agent.status = "online"
                agent.last_heartbeat = datetime.now(timezone.utc)
                agent.register_time = datetime.now(timezone.utc)
                self._agents[key] = agent
                logger.info("[DataAgentManager] Registered agent: %s:%s", ip, port)
            
            # 更新数据库
            await self._update_agent_in_db(agent)
            return True
    
    async def heartbeat(self, ip: str, port: int) -> bool:
        """更新agent心跳。
        
        Args:
            ip: agent的IP地址
            port: agent的端口号
        
        Returns:
            成功返回True，失败返回False
        """
        async with self._lock:
            key = (ip, port)
            if key not in self._agents:
                return False
            
            agent = self._agents[key]
            agent.last_heartbeat = datetime.now(timezone.utc)
            agent.status = "online"
            await self._update_agent_in_db(agent)
            return True
    
    async def check_agent_health(self, ip: str, port: int) -> bool:
        """检查agent健康状态（主动探测）。
        
        Args:
            ip: agent的IP地址
            port: agent的端口号
        
        Returns:
            健康返回True，不健康返回False
        """
        try:
            async with aiohttp.ClientSession() as session:
                url = f"http://{ip}:{port}/ping"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("status") == "ok"
                    return False
        except Exception as e:
            logger.debug("[DataAgentManager] Health check failed for %s:%s: %s", ip, port, e)
            return False
    
    async def get_agent_connection_count(self, ip: str, port: int) -> Optional[int]:
        """获取agent的连接数。
        
        Args:
            ip: agent的IP地址
            port: agent的端口号
        
        Returns:
            连接数，失败返回None
        """
        try:
            async with aiohttp.ClientSession() as session:
                url = f"http://{ip}:{port}/connections/count"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("connection_count")
                    return None
        except Exception as e:
            logger.debug("[DataAgentManager] Failed to get connection count for %s:%s: %s", ip, port, e)
            return None
    
    async def get_agent_connection_list(self, ip: str, port: int) -> List[Dict[str, Any]]:
        """获取agent的连接列表。
        
        Args:
            ip: agent的IP地址
            port: agent的端口号
        
        Returns:
            连接列表
        """
        try:
            async with aiohttp.ClientSession() as session:
                url = f"http://{ip}:{port}/connections/list"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("connections", [])
                    return []
        except Exception as e:
            logger.debug("[DataAgentManager] Failed to get connection list for %s:%s: %s", ip, port, e)
            return []
    
    async def get_agent_symbols(self, ip: str, port: int) -> Set[str]:
        """获取agent当前同步的symbol列表。
        
        Args:
            ip: agent的IP地址
            port: agent的端口号
        
        Returns:
            symbol集合
        """
        try:
            async with aiohttp.ClientSession() as session:
                url = f"http://{ip}:{port}/symbols"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return set(data.get("symbols", []))
                    return set()
        except Exception as e:
            logger.debug("[DataAgentManager] Failed to get symbols for %s:%s: %s", ip, port, e)
            return set()
    
    async def add_stream_to_agent(self, ip: str, port: int, symbol: str, interval: str) -> bool:
        """向agent下发添加K线流的指令。
        
        Args:
            ip: agent的IP地址
            port: agent的端口号
            symbol: 交易对符号
            interval: 时间间隔
        
        Returns:
            成功返回True，失败返回False
        """
        try:
            async with aiohttp.ClientSession() as session:
                url = f"http://{ip}:{port}/streams/add"
                payload = {"symbol": symbol, "interval": interval}
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
            logger.error("[DataAgentManager] Failed to add stream to %s:%s: %s", ip, port, e)
            return False
    
    async def find_best_agent(self, required_connections: int = 1) -> Optional[tuple]:
        """查找最适合的agent（负载最低）。
        
        Args:
            required_connections: 需要的连接数
        
        Returns:
            (ip, port)元组，如果没有可用agent则返回None
        """
        async with self._lock:
            available_agents = []
            for key, agent in self._agents.items():
                if agent.status == "online":
                    available = self._max_connections_per_agent - agent.connection_count
                    if available >= required_connections:
                        available_agents.append((key, agent, available))
            
            if not available_agents:
                return None
            
            # 选择可用连接数最多的agent
            available_agents.sort(key=lambda x: x[2], reverse=True)
            return available_agents[0][0]
    
    async def check_all_agents_health(self) -> None:
        """检查所有agent的健康状态。"""
        async with self._lock:
            agents_to_check = list(self._agents.items())
        
        for key, agent in agents_to_check:
            # 检查心跳超时
            if agent.last_heartbeat:
                timeout_seconds = (datetime.now(timezone.utc) - agent.last_heartbeat).total_seconds()
                if timeout_seconds > self._heartbeat_timeout:
                    # 心跳超时，执行主动探测
                    is_healthy = await self.check_agent_health(agent.ip, agent.port)
                    async with self._lock:
                        if key in self._agents:
                            if is_healthy:
                                self._agents[key].status = "online"
                                self._agents[key].last_heartbeat = datetime.now(timezone.utc)
                            else:
                                self._agents[key].status = "offline"
                            await self._update_agent_in_db(self._agents[key])
    
    async def refresh_all_agents_status(self) -> None:
        """刷新所有agent的状态到数据库。"""
        async with self._lock:
            agents_to_refresh = list(self._agents.items())
        
        for key, agent in agents_to_refresh:
            # 获取实时连接数和symbol列表
            connection_count = await self.get_agent_connection_count(agent.ip, agent.port)
            if connection_count is not None:
                agent.connection_count = connection_count
            
            symbols = await self.get_agent_symbols(agent.ip, agent.port)
            agent.assigned_symbols = symbols
            agent.assigned_symbol_count = len(symbols)
            
            await self._update_agent_in_db(agent)
    
    async def _update_agent_in_db(self, agent: DataAgentInfo) -> None:
        """更新agent信息到数据库。"""
        try:
            agent_data = {
                "ip": agent.ip,
                "port": agent.port,
                "status": agent.status,
                "connection_count": agent.connection_count,
                "assigned_symbol_count": agent.assigned_symbol_count,
                "assigned_symbols": sorted(list(agent.assigned_symbols)),
                "error_log": agent.error_log,
                "last_heartbeat": agent.last_heartbeat,
            }
            await asyncio.to_thread(self._db.upsert_market_data_agent, agent_data)
        except Exception as e:
            logger.error("[DataAgentManager] Failed to update agent in DB: %s", e, exc_info=True)
    
    async def get_all_agents(self) -> List[DataAgentInfo]:
        """获取所有agent信息。"""
        async with self._lock:
            return list(self._agents.values())


class DataAgentManagerHTTPHandler(BaseHTTPRequestHandler):
    """处理async_agent的HTTP请求（注册、心跳等）。"""
    
    def __init__(self, manager: DataAgentManager, *args, **kwargs):
        self.manager = manager
        super().__init__(*args, **kwargs)
    
    def do_POST(self):
        """处理POST请求。"""
        try:
            parsed_path = urllib.parse.urlparse(self.path)
            path = parsed_path.path
            
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8')) if content_length > 0 else {}
            
            if path == '/register':
                # 注册agent
                self._handle_register(data)
            elif path == '/heartbeat':
                # 心跳
                self._handle_heartbeat(data)
            else:
                self._send_error(404, "Not Found")
        except Exception as e:
            logger.error("[DataAgentManagerHTTP] Error handling POST request: %s", e, exc_info=True)
            self._send_error(500, str(e))
    
    def _handle_register(self, data: Dict[str, Any]):
        """处理注册请求。"""
        ip = data.get('ip', '')
        port = data.get('port', 0)
        
        if not ip or port == 0:
            self._send_error(400, "Missing ip or port")
            return
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            success = loop.run_until_complete(self.manager.register_agent(ip, port))
            if success:
                self._send_json({"status": "ok", "message": f"Registered agent {ip}:{port}"})
            else:
                self._send_error(500, "Failed to register agent")
        finally:
            loop.close()
    
    def _handle_heartbeat(self, data: Dict[str, Any]):
        """处理心跳请求。"""
        ip = data.get('ip', '')
        port = data.get('port', 0)
        
        if not ip or port == 0:
            self._send_error(400, "Missing ip or port")
            return
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            success = loop.run_until_complete(self.manager.heartbeat(ip, port))
            if success:
                self._send_json({"status": "ok", "message": "Heartbeat received"})
            else:
                self._send_error(404, "Agent not found")
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
        """重写日志方法。"""
        logger.debug("[DataAgentManagerHTTP] %s", format % args)


def create_manager_handler(manager: DataAgentManager):
    """创建请求处理器工厂函数。"""
    def handler(*args, **kwargs):
        return DataAgentManagerHTTPHandler(manager, *args, **kwargs)
    return handler


async def run_manager_http_server(
    manager: DataAgentManager,
    host: str = '0.0.0.0',
    port: int = 8888
) -> None:
    """运行manager的HTTP服务器。"""
    handler = create_manager_handler(manager)
    server = HTTPServer((host, port), handler)
    logger.info("[DataAgentManager] HTTP server started on %s:%s", host, port)
    
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
        logger.info("[DataAgentManager] HTTP server stopped")

