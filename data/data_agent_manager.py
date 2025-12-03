"""Data agent manager for async_agent.

This module manages data_agent registration, heartbeat, and task distribution.
"""
from __future__ import annotations

import asyncio
import json
import logging
import socket
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Callable, Awaitable
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import urllib.parse
import aiohttp
from enum import Enum

import common.config as app_config
from common.database_clickhouse import ClickHouseDatabase

logger = logging.getLogger(__name__)


class AgentCommandType(Enum):
    """Agent命令类型枚举"""
    ADD_SYMBOLS = "add_symbols"
    ADD_STREAM = "add_stream"
    GET_STATUS = "get_status"
    # 探活操作不进入队列，可以并行执行


class AgentCommand:
    """Agent命令指令类（不带业务数据，只包含指令信息）"""
    def __init__(self, command_type: AgentCommandType, command_id: str, **kwargs):
        self.command_type = command_type
        self.command_id = command_id
        self.params = kwargs  # 指令参数，执行端根据参数获取数据


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
    """管理所有data_agent。
    
    使用内部消息队列机制确保与各agent的通讯命令顺序执行：
    - 全局指令队列：所有agent的指令都进入全局队列，确保顺序执行并返回结果
    - 所有操作（add_symbols_to_agent, add_stream_to_agent, get_agent_status）都通过全局队列顺序执行
    - 探活操作（check_agent_health）不进入队列，可以并行执行
    - 确保正在下发指令时，不会同时做同步检查，避免数据不一致
    - 保证下发给各个agent指令执行并返回结果的顺序
    """
    
    def __init__(self, db: ClickHouseDatabase):
        self._db = db
        self._agents: Dict[tuple, DataAgentInfo] = {}  # {(ip, port): DataAgentInfo}
        self._lock = asyncio.Lock()
        self._max_symbols_per_agent = getattr(app_config, 'DATA_AGENT_MAX_SYMBOL', 100)
        self._heartbeat_timeout = getattr(app_config, 'DATA_AGENT_HEARTBEAT_TIMEOUT', 60)
        
        # 全局指令队列：确保所有agent的指令顺序执行并返回结果
        # 所有agent的指令都进入这个全局队列，按顺序执行并返回结果
        # 这样可以避免多个agent的指令并发执行导致数据库操作冲突
        # 保证下发给各个agent指令执行并返回结果的顺序
        self._global_command_queue: asyncio.Queue = asyncio.Queue()
        self._global_queue_processor: Optional[asyncio.Task] = None
        self._global_queue_lock = asyncio.Lock()
    
    async def _execute_command(self, ip: str, port: int, command: AgentCommand) -> Any:
        """执行指令（指令执行端根据指令获取数据并执行）。
        
        确保指令完全执行完成（包括数据库操作和后续处理）后才返回结果。
        
        Args:
            ip: agent的IP地址
            port: agent的端口号
            command: 指令对象
        
        Returns:
            执行结果（包括数据库操作和后续处理都完成后才返回）
        """
        if command.command_type == AgentCommandType.ADD_SYMBOLS:
            # 根据指令参数获取symbols列表
            symbols = command.params.get("symbols", [])
            max_batch_size = command.params.get("max_batch_size", 20)
            return await self._execute_add_symbols_command(ip, port, symbols, max_batch_size)
        elif command.command_type == AgentCommandType.ADD_STREAM:
            symbol = command.params.get("symbol")
            interval = command.params.get("interval")
            return await self._execute_add_stream_command(ip, port, symbol, interval)
        elif command.command_type == AgentCommandType.GET_STATUS:
            return await self._execute_get_status_command(ip, port)
        else:
            raise ValueError(f"Unknown command type: {command.command_type}")
    
    async def _get_agent_existing_symbols(self, ip: str, port: int) -> Set[str]:
        """从数据库查询agent已构建的symbol列表。
        
        Args:
            ip: agent的IP地址
            port: agent的端口号
        
        Returns:
            已构建的symbol集合
        """
        try:
            agent_data = await asyncio.to_thread(self._db.get_market_data_agent, ip, port)
            if agent_data and agent_data.get("assigned_symbols"):
                return set(agent_data["assigned_symbols"])
            return set()
        except Exception as e:
            logger.warning(
                "[DataAgentManager] Failed to get existing symbols from DB for %s:%s: %s",
                ip, port, e
            )
            return set()
    
    async def _execute_add_symbols_command(
        self,
        ip: str,
        port: int,
        symbols: List[str],
        max_batch_size: int
    ) -> Optional[Dict[str, Any]]:
        """执行添加symbols指令（先查询数据库过滤已构建的symbol）。
        
        1. 查询market_data_agent表，获取已构建的symbol
        2. 过滤掉已构建的symbol，只构建未构建的
        3. 执行构建操作
        4. 等待agent返回结果
        5. 更新数据库（插入或更新market_data_agent表）
        6. 完成后续处理逻辑
        
        Args:
            ip: agent的IP地址
            port: agent的端口号
            symbols: 要构建的symbol列表
            max_batch_size: 每批最多处理的symbol数量
        
        Returns:
            执行结果（包括数据库操作完成后才返回）
        """
        if not symbols:
            return None
        
        # 1. 查询数据库，获取已构建的symbol
        existing_symbols = await self._get_agent_existing_symbols(ip, port)
        
        # 2. 过滤掉已构建的symbol
        symbols_to_build = [s for s in symbols if s.upper() not in existing_symbols]
        
        if not symbols_to_build:
            logger.info(
                "[DataAgentManager] All symbols already built for %s:%s: %s",
                ip, port, symbols
            )
            # 即使没有新symbol，也要返回当前状态
            status = await self._get_agent_status_internal(ip, port)
            return {
                "status": "ok",
                "results": [],
                "current_status": status,
                "skipped_count": len(symbols)
            }
        
        logger.info(
            "[DataAgentManager] Filtered symbols for %s:%s: %s already built, %s to build",
            ip, port, len(existing_symbols), len(symbols_to_build)
        )
        
        # 3. 执行构建操作
        result = await self._add_symbols_to_agent_internal(ip, port, symbols_to_build, max_batch_size)
        
        # 4. 等待agent返回结果后，更新数据库
        if result and result.get("status") == "ok":
            # 5. 更新数据库（插入或更新market_data_agent表）
            await self._update_agent_status_after_add_symbols(ip, port, result)
        
        # 6. 完成后续处理逻辑，返回结果
        return result
    
    async def _execute_add_stream_command(
        self,
        ip: str,
        port: int,
        symbol: str,
        interval: str
    ) -> bool:
        """执行添加stream指令。
        
        1. 执行构建操作
        2. 等待agent返回结果
        3. 更新数据库
        4. 完成后续处理逻辑
        
        Args:
            ip: agent的IP地址
            port: agent的端口号
            symbol: 交易对符号
            interval: 时间间隔
        
        Returns:
            执行结果（包括数据库操作完成后才返回）
        """
        # 1. 执行构建操作
        result = await self._add_stream_to_agent_internal(ip, port, symbol, interval)
        
        # 2. 等待agent返回结果后，更新数据库
        if result:
            # 3. 更新数据库
            await self._update_agent_status_after_add_stream(ip, port, symbol, interval)
        
        # 4. 完成后续处理逻辑，返回结果
        return result
    
    async def _execute_get_status_command(self, ip: str, port: int) -> Optional[Dict[str, Any]]:
        """执行获取状态指令。
        
        1. 获取agent状态
        2. 更新数据库
        3. 完成后续处理逻辑
        
        Args:
            ip: agent的IP地址
            port: agent的端口号
        
        Returns:
            执行结果（包括数据库操作完成后才返回）
        """
        # 1. 获取agent状态
        status = await self._get_agent_status_internal(ip, port)
        
        # 2. 更新数据库
        if status is not None:
            await self._update_agent_status_from_status(ip, port, status)
        
        # 3. 完成后续处理逻辑，返回结果
        return status
    
    async def _update_agent_status_after_add_symbols(
        self,
        ip: str,
        port: int,
        result: Dict[str, Any]
    ) -> None:
        """在添加symbols后更新agent状态到数据库。"""
        try:
            async with self._lock:
                key = (ip, port)
                if key not in self._agents:
                    return
                
                agent = self._agents[key]
                current_status = result.get("current_status", {})
                agent.connection_count = current_status.get("connection_count", 0)
                
                # 更新symbol列表（现在返回的是symbol字符串列表，不包含interval）
                symbols_list = current_status.get("symbols", [])
                if symbols_list and isinstance(symbols_list[0], dict):
                    # 兼容旧格式：包含intervals的对象
                    agent.assigned_symbols = {item["symbol"] for item in symbols_list}
                else:
                    # 新格式：直接是symbol字符串列表
                    agent.assigned_symbols = set(symbols_list) if symbols_list else set()
                agent.assigned_symbol_count = len(agent.assigned_symbols)
                
                # 更新数据库
                await self._update_agent_in_db(agent)
        except Exception as e:
            logger.error(
                "[DataAgentManager] Failed to update agent status after add symbols for %s:%s: %s",
                ip, port, e, exc_info=True
            )
    
    async def _update_agent_status_after_add_stream(
        self,
        ip: str,
        port: int,
        symbol: str,
        interval: str
    ) -> None:
        """在添加stream后更新agent状态到数据库。"""
        try:
            # 获取最新状态并更新
            status = await self._get_agent_status_internal(ip, port)
            if status:
                await self._update_agent_status_from_status(ip, port, status)
        except Exception as e:
            logger.error(
                "[DataAgentManager] Failed to update agent status after add stream for %s:%s: %s",
                ip, port, e, exc_info=True
            )
    
    async def _update_agent_status_from_status(
        self,
        ip: str,
        port: int,
        status: Dict[str, Any]
    ) -> None:
        """根据status更新agent状态到数据库。"""
        try:
            async with self._lock:
                key = (ip, port)
                if key not in self._agents:
                    return
                
                agent = self._agents[key]
                agent.connection_count = status.get("connection_count", 0)
                
                # 更新symbol列表（现在返回的是symbol字符串列表，不包含interval）
                symbols_list = status.get("symbols", [])
                if symbols_list and isinstance(symbols_list[0], dict):
                    # 兼容旧格式：包含intervals的对象
                    agent.assigned_symbols = {item["symbol"] for item in symbols_list}
                else:
                    # 新格式：直接是symbol字符串列表
                    agent.assigned_symbols = set(symbols_list) if symbols_list else set()
                agent.assigned_symbol_count = len(agent.assigned_symbols)
                
                # 更新数据库
                await self._update_agent_in_db(agent)
        except Exception as e:
            logger.error(
                "[DataAgentManager] Failed to update agent status from status for %s:%s: %s",
                ip, port, e, exc_info=True
            )
    
    async def _process_global_command_queue(self) -> None:
        """处理全局指令队列，确保所有agent的指令顺序执行并返回结果。
        
        全局队列确保：
        1. 所有agent的指令按顺序执行
        2. 每个指令完全执行完成（包括数据库操作和后续处理）后才执行下一个
        3. 指令返回结果的顺序与执行顺序一致
        """
        logger.debug("[DataAgentManager] Global command queue processor started")
        
        while True:
            try:
                # 从全局队列中获取指令
                command_data = await self._global_command_queue.get()
                
                if command_data is None:  # 停止信号
                    logger.debug("[DataAgentManager] Global command queue processor stopped")
                    break
                
                ip = command_data.get("ip")
                port = command_data.get("port")
                command: AgentCommand = command_data.get("command")
                future = command_data.get("future")
                
                try:
                    # 执行指令（包括数据库操作和后续处理）
                    result = await self._execute_command(ip, port, command)
                    
                    # 确保指令完全执行完成（包括数据库操作）后才返回结果
                    if future and not future.done():
                        future.set_result(result)
                except Exception as e:
                    logger.error(
                        "[DataAgentManager] Error executing global command %s for %s:%s: %s",
                        command.command_type, ip, port, e, exc_info=True
                    )
                    if future and not future.done():
                        future.set_exception(e)
                finally:
                    self._global_command_queue.task_done()
                    # 确保当前指令的所有操作都完成后，才处理下一个指令
                    
            except asyncio.CancelledError:
                logger.debug("[DataAgentManager] Global command queue processor cancelled")
                break
            except Exception as e:
                logger.error(
                    "[DataAgentManager] Error in global command queue processor: %s",
                    e, exc_info=True
                )
    
    async def _enqueue_command(
        self,
        ip: str,
        port: int,
        command: AgentCommand
    ) -> Any:
        """将指令加入全局队列，等待执行结果。
        
        所有agent的指令都进入全局队列，确保顺序执行并返回结果。
        指令不带业务数据，只包含指令信息，执行端根据指令获取数据并执行。
        这样可以防止内部并发，解决并发带来的数据不一致问题。
        
        Args:
            ip: agent的IP地址
            port: agent的端口号
            command: 指令对象
        
        Returns:
            指令执行结果（包括数据库操作和后续处理都完成后才返回）
        """
        # 确保全局队列处理器已启动
        async with self._global_queue_lock:
            if self._global_queue_processor is None or self._global_queue_processor.done():
                self._global_queue_processor = asyncio.create_task(
                    self._process_global_command_queue()
                )
                logger.debug("[DataAgentManager] Started global command queue processor")
        
        future = asyncio.Future()
        
        # 将指令加入全局队列（所有agent的指令都进入这个队列）
        await self._global_command_queue.put({
            "ip": ip,
            "port": port,
            "command": command,
            "future": future
        })
        
        # 等待执行结果（包括数据库操作和后续处理都完成后才返回）
        # 这样可以保证指令执行并返回结果的顺序
        return await future
    
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
    
    async def _add_stream_to_agent_internal(self, ip: str, port: int, symbol: str, interval: str) -> bool:
        """内部方法：向agent下发添加K线流的指令。"""
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
    
    async def add_stream_to_agent(self, ip: str, port: int, symbol: str, interval: str) -> bool:
        """向agent下发添加K线流的指令（通过消息队列顺序执行）。
        
        Args:
            ip: agent的IP地址
            port: agent的端口号
            symbol: 交易对符号
            interval: 时间间隔
        
        Returns:
            成功返回True，失败返回False（包括数据库操作完成后才返回）
        """
        import uuid
        command = AgentCommand(
            AgentCommandType.ADD_STREAM,
            command_id=str(uuid.uuid4()),
            symbol=symbol,
            interval=interval
        )
        return await self._enqueue_command(ip, port, command)
    
    async def _add_symbols_to_agent_internal(
        self, 
        ip: str, 
        port: int, 
        symbols: List[str],
        max_batch_size: int = 20
    ) -> Optional[Dict[str, Any]]:
        """内部方法：批量向agent下发添加symbol的指令。"""
        if not symbols:
            return None
        
        # 分批处理，每批不超过max_batch_size个symbol
        batch_size = getattr(app_config, 'DATA_AGENT_BATCH_SYMBOL_SIZE', max_batch_size)
        all_results = []
        
        for i in range(0, len(symbols), batch_size):
            batch_symbols = symbols[i:i + batch_size]
            try:
                async with aiohttp.ClientSession() as session:
                    url = f"http://{ip}:{port}/symbols/add"
                    payload = {"symbols": batch_symbols}
                    async with session.post(
                        url,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=60)  # 批量操作可能需要更长时间
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get("status") == "ok":
                                all_results.extend(data.get("results", []))
                                # 最后一次请求返回的状态是最新的
                                if i + batch_size >= len(symbols):
                                    return data
                        else:
                            logger.warning(
                                "[DataAgentManager] Failed to add symbols batch to %s:%s: status %s",
                                ip, port, response.status
                            )
            except Exception as e:
                logger.error(
                    "[DataAgentManager] Failed to add symbols batch to %s:%s: %s",
                    ip, port, e
                )
        
        # 如果所有批次都失败，返回None
        if not all_results:
            return None
        
        # 获取最终状态（直接调用内部方法，因为已经在队列中）
        try:
            status = await self._get_agent_status_internal(ip, port)
            return {
                "status": "ok",
                "results": all_results,
                "current_status": status
            }
        except Exception as e:
            logger.error("[DataAgentManager] Failed to get final status from %s:%s: %s", ip, port, e)
            return None
    
    async def add_symbols_to_agent(
        self, 
        ip: str, 
        port: int, 
        symbols: List[str],
        max_batch_size: int = 20
    ) -> Optional[Dict[str, Any]]:
        """批量向agent下发添加symbol的指令（通过消息队列顺序执行）。
        
        在执行前会查询market_data_agent表，过滤掉已构建的symbol。
        
        Args:
            ip: agent的IP地址
            port: agent的端口号
            symbols: 交易对符号列表
            max_batch_size: 每批最多处理的symbol数量（默认20，可配置）
        
        Returns:
            包含当前连接状态和结果的字典，失败返回None（包括数据库操作完成后才返回）
        """
        import uuid
        command = AgentCommand(
            AgentCommandType.ADD_SYMBOLS,
            command_id=str(uuid.uuid4()),
            symbols=symbols,
            max_batch_size=max_batch_size
        )
        return await self._enqueue_command(ip, port, command)
    
    async def _get_agent_status_internal(self, ip: str, port: int) -> Optional[Dict[str, Any]]:
        """内部方法：获取agent的连接状态。"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"http://{ip}:{port}/status"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("status") == "ok":
                            return {
                                "connection_count": data.get("connection_count", 0),
                                "symbols": data.get("symbols", [])
                            }
                    return None
        except Exception as e:
            logger.debug("[DataAgentManager] Failed to get status for %s:%s: %s", ip, port, e)
            return None
    
    async def get_agent_status(self, ip: str, port: int) -> Optional[Dict[str, Any]]:
        """获取agent的连接状态（通过消息队列顺序执行）。
        
        Args:
            ip: agent的IP地址
            port: agent的端口号
        
        Returns:
            连接状态字典，失败返回None（包括数据库操作完成后才返回）
        """
        import uuid
        command = AgentCommand(
            AgentCommandType.GET_STATUS,
            command_id=str(uuid.uuid4())
        )
        return await self._enqueue_command(ip, port, command)
    
    async def find_best_agent(self, required_symbols: int = 1) -> Optional[tuple]:
        """查找最适合的agent（负载最低，基于symbol数量）。
        
        Args:
            required_symbols: 需要的symbol数量
        
        Returns:
            (ip, port)元组，如果没有可用agent则返回None
        """
        async with self._lock:
            available_agents = []
            for key, agent in self._agents.items():
                if agent.status == "online":
                    # 检查agent当前持有的symbol数量
                    current_symbol_count = agent.assigned_symbol_count
                    available = self._max_symbols_per_agent - current_symbol_count
                    if available >= required_symbols:
                        available_agents.append((key, agent, available))
            
            if not available_agents:
                return None
            
            # 选择可用symbol数量最多的agent（负载最低）
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
                                await self._update_agent_in_db(self._agents[key])
                            else:
                                # agent离线，需要重新分配其负责的symbol
                                logger.warning("[DataAgentManager] Agent %s:%s 离线，开始重新分配其负责的symbol...", 
                                             agent.ip, agent.port)
                                
                                # 获取该agent当前的symbol列表
                                symbols_on_agent = await self.get_agent_symbols(agent.ip, agent.port)
                                logger.info("[DataAgentManager] Agent %s:%s 负责的symbol数量: %s", 
                                          agent.ip, agent.port, len(symbols_on_agent))
                                
                                # 更新agent状态为离线
                                self._agents[key].status = "offline"
                                await self._update_agent_in_db(self._agents[key])
                                
                                # 重新分配该agent的symbol到其他可用agent
                                if symbols_on_agent:
                                    await self._reassign_agent_symbols(agent, symbols_on_agent)
    
    async def _reassign_agent_symbols(self, offline_agent: DataAgentInfo, symbols: Set[str]) -> None:
        """重新分配离线agent的symbol到其他可用agent。
        
        Args:
            offline_agent: 离线的agent
            symbols: 该agent负责的symbol集合
        """
        for symbol in symbols:
            # 查找最适合的可用agent（需要1个symbol）
            agent_key = await self.find_best_agent(required_symbols=1)
            if agent_key:
                new_ip, new_port = agent_key
                logger.debug("[DataAgentManager] 尝试将离线agent %s:%s 的 %s 重新分配到 %s:%s", 
                           offline_agent.ip, offline_agent.port, symbol, new_ip, new_port)
                
                # 重新添加symbol到新agent（会为symbol创建7个interval的连接）
                try:
                    result = await self.add_symbols_to_agent(new_ip, new_port, [symbol])
                    if result and result.get("status") == "ok":
                        logger.info("[DataAgentManager] ✅ 成功将 %s 从 %s:%s 重新分配到 %s:%s", 
                                  symbol, offline_agent.ip, offline_agent.port, new_ip, new_port)
                    else:
                        logger.warning("[DataAgentManager] ⚠️  重新分配 %s 失败，将在下次同步时重试", 
                                     symbol)
                except Exception as e:
                    logger.error("[DataAgentManager] ❌ 重新分配 %s 时出错: %s", 
                               symbol, e, exc_info=True)
            else:
                logger.warning("[DataAgentManager] ⚠️  没有可用的agent来重新分配 %s，将在下次同步时重试", 
                             symbol)
    
    async def refresh_all_agents_status(self) -> None:
        """刷新所有agent的状态到数据库（使用/status接口获取详细连接状态）。
        
        注意：get_agent_status 已经通过队列执行并更新了数据库，这里主要是确保内存状态同步。
        """
        async with self._lock:
            agents_to_refresh = list(self._agents.items())
        
        for key, agent in agents_to_refresh:
            # 使用/status接口获取详细的连接状态（通过队列顺序执行，已更新数据库）
            # 这里只需要同步内存状态
            status = await self.get_agent_status(agent.ip, agent.port)
            if status is not None:
                async with self._lock:
                    if key in self._agents:
                        agent = self._agents[key]
                        agent.connection_count = status.get("connection_count", 0)
                        # 从status中提取symbol列表（现在是symbol字符串列表，不包含interval）
                        symbols_list = status.get("symbols", [])
                        if symbols_list and isinstance(symbols_list[0], dict):
                            # 兼容旧格式：包含intervals的对象
                            agent.assigned_symbols = {item["symbol"] for item in symbols_list}
                        else:
                            # 新格式：直接是symbol字符串列表
                            agent.assigned_symbols = set(symbols_list) if symbols_list else set()
                        agent.assigned_symbol_count = len(agent.assigned_symbols)
            else:
                # 如果获取状态失败，尝试使用旧方法（不通过队列，仅用于备用）
                async with self._lock:
                    if key in self._agents:
                        agent = self._agents[key]
                        connection_count = await self.get_agent_connection_count(agent.ip, agent.port)
                        if connection_count is not None:
                            agent.connection_count = connection_count
                        
                        symbols = await self.get_agent_symbols(agent.ip, agent.port)
                        agent.assigned_symbols = symbols
                        agent.assigned_symbol_count = len(symbols)
                        
                        # 备用方法也需要更新数据库
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
    
    async def get_all_allocated_symbol_intervals(self) -> Set[tuple]:
        """获取所有已分配的symbol-interval对。
        
        Returns:
            已分配的(symbol, interval)集合
        """
        async with self._lock:
            online_agents = [agent for agent in self._agents.values() if agent.status == "online"]
        
        allocated_pairs = set()
        
        for agent in online_agents:
            try:
                # 获取agent当前的连接列表
                connections = await self.get_agent_connection_list(agent.ip, agent.port)
                for conn in connections:
                    symbol = conn.get("symbol")
                    interval = conn.get("interval")
                    if symbol and interval:
                        allocated_pairs.add((symbol, interval))
            except Exception as e:
                logger.debug("[DataAgentManager] Failed to get connections for %s:%s: %s", 
                           agent.ip, agent.port, e)
        
        return allocated_pairs
    
    async def get_all_allocated_symbols(self) -> Set[str]:
        """获取所有已分配的symbol（不包含interval信息）。
        
        Returns:
            已分配的symbol集合
        """
        async with self._lock:
            online_agents = [agent for agent in self._agents.values() if agent.status == "online"]
        
        allocated_symbols = set()
        
        for agent in online_agents:
            try:
                # 直接使用agent内存中的symbol集合（更高效）
                allocated_symbols.update(agent.assigned_symbols)
            except Exception as e:
                logger.debug("[DataAgentManager] Failed to get symbols for %s:%s: %s", 
                           agent.ip, agent.port, e)
                # 备用方法：通过API获取
                try:
                    symbols = await self.get_agent_symbols(agent.ip, agent.port)
                    allocated_symbols.update(symbols)
                except Exception as e2:
                    logger.debug("[DataAgentManager] Failed to get symbols via API for %s:%s: %s", 
                               agent.ip, agent.port, e2)
        
        return allocated_symbols


class DataAgentManagerHTTPHandler(BaseHTTPRequestHandler):
    """处理async_agent的HTTP请求（注册、心跳等）。"""
    
    def __init__(self, manager: DataAgentManager, event_loop: asyncio.AbstractEventLoop, *args, **kwargs):
        self.manager = manager
        # 使用传入的事件循环，而不是尝试获取当前线程的事件循环
        self._event_loop = event_loop
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
                # 心跳（保留兼容性，但实际不再使用，由manager主动轮询）
                self._handle_heartbeat(data)
            else:
                self._send_error(404, "Not Found")
        except Exception as e:
            logger.error("[DataAgentManagerHTTP] Error handling POST request: %s", e, exc_info=True)
            self._send_error(500, str(e))
        finally:
            # 确保连接关闭，避免CLOSE_WAIT状态
            self.close_connection = True
    
    def _handle_register(self, data: Dict[str, Any]):
        """处理注册请求。"""
        ip = data.get('ip', '')
        port = data.get('port', 0)
        
        if not ip or port == 0:
            self._send_error(400, "Missing ip or port")
            return
        
        try:
            # 使用manager创建时的事件循环来执行异步操作
            # 不创建新的事件循环，避免锁绑定问题
            success = asyncio.run_coroutine_threadsafe(
                self.manager.register_agent(ip, port),
                self._event_loop
            ).result(timeout=10)
            
            if success:
                self._send_json({"status": "ok", "message": f"Registered agent {ip}:{port}"})
            else:
                self._send_error(500, "Failed to register agent")
        except Exception as e:
            logger.error("[DataAgentManagerHTTP] Error handling register request: %s", e, exc_info=True)
            self._send_error(500, str(e))
    
    def _handle_heartbeat(self, data: Dict[str, Any]):
        """处理心跳请求。"""
        ip = data.get('ip', '')
        port = data.get('port', 0)
        
        if not ip or port == 0:
            self._send_error(400, "Missing ip or port")
            return
        
        try:
            # 使用manager创建时的事件循环来执行异步操作
            # 不创建新的事件循环，避免锁绑定问题
            success = asyncio.run_coroutine_threadsafe(
                self.manager.heartbeat(ip, port),
                self._event_loop
            ).result(timeout=10)
            
            if success:
                self._send_json({"status": "ok", "message": "Heartbeat received"})
            else:
                self._send_error(404, "Agent not found")
        except Exception as e:
            logger.error("[DataAgentManagerHTTP] Error handling heartbeat request: %s", e, exc_info=True)
            self._send_error(500, str(e))
    
    def _send_json(self, data: Dict[str, Any]):
        """发送JSON响应。"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Connection', 'close')  # 确保连接关闭
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        self.wfile.flush()  # 确保数据发送完成
    
    def _send_error(self, code: int, message: str):
        """发送错误响应。"""
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Connection', 'close')  # 确保连接关闭
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}, ensure_ascii=False).encode('utf-8'))
        self.wfile.flush()  # 确保数据发送完成
    
    def log_message(self, format, *args):
        """重写日志方法。"""
        logger.debug("[DataAgentManagerHTTP] %s", format % args)


def create_manager_handler(manager: DataAgentManager, event_loop: asyncio.AbstractEventLoop):
    """创建请求处理器工厂函数。"""
    def handler(*args, **kwargs):
        return DataAgentManagerHTTPHandler(manager, event_loop, *args, **kwargs)
    return handler


async def run_manager_http_server(
    manager: DataAgentManager,
    host: str = '0.0.0.0',
    port: int = 8888
) -> None:
    """运行manager的HTTP服务器。"""
    # 获取当前事件循环
    current_loop = asyncio.get_running_loop()
    handler = create_manager_handler(manager, current_loop)
    server = HTTPServer((host, port), handler)
    # 允许地址重用，避免端口占用问题
    server.allow_reuse_address = True
    # 设置超时，避免连接长时间挂起
    server.timeout = 30
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

