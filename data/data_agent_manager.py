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
    ADD_SYMBOLS = "add_symbols"  # K线监听服务构建任务，需要队列管理
    GET_STATUS = "get_status"  # 状态查询，不需要队列管理
    # 探活操作不进入队列，可以并行执行
    
    def requires_queue(self) -> bool:
        """判断该命令类型是否需要队列管理"""
        return self == AgentCommandType.ADD_SYMBOLS


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
    - 全局指令队列：K线监听服务构建任务（ADD_SYMBOLS）进入全局队列，确保顺序执行并返回结果
    - 所有操作（add_symbols_to_agent, get_agent_status）都通过全局队列顺序执行
    - 探活操作（check_agent_health）不进入队列，可以并行执行
    - 确保正在下发指令时，不会同时做同步检查，避免数据不一致
    - 保证下发给各个agent指令执行并返回结果的顺序
    """
    
    # ============ 初始化 ============
    
    def __init__(self, db: ClickHouseDatabase):
        self._db = db
        self._agents: Dict[tuple, DataAgentInfo] = {}  # {(ip, port): DataAgentInfo}，port是指令端口
        self._lock = asyncio.Lock()
        self._max_symbols_per_agent = getattr(app_config, 'DATA_AGENT_MAX_SYMBOL', 100)
        self._heartbeat_timeout = getattr(app_config, 'DATA_AGENT_HEARTBEAT_TIMEOUT', 60)
        self._command_timeout = getattr(app_config, 'DATA_AGENT_COMMAND_TIMEOUT', 120)  # 命令执行超时
        # 状态检查端口（独立端口，避免指令服务阻塞）
        self._status_port = getattr(app_config, 'DATA_AGENT_STATUS_PORT', 9988)
        
        # 全局指令队列：确保所有agent的指令顺序执行并返回结果
        # 所有agent的指令都进入这个全局队列，按顺序执行并返回结果
        # 这样可以避免多个agent的指令并发执行导致数据库操作冲突
        # 保证下发给各个agent指令执行并返回结果的顺序
        self._global_command_queue: asyncio.Queue = asyncio.Queue()
        self._global_queue_processor: Optional[asyncio.Task] = None
        self._global_queue_lock = asyncio.Lock()
    
    # ============ 命令执行相关方法 ============
    
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
        # 检查是否是注册命令
        if command.params.get("_is_register", False):
            return await self._execute_register_command(ip, port)
        elif command.command_type == AgentCommandType.ADD_SYMBOLS:
            # 根据指令参数获取symbols列表
            symbols = command.params.get("symbols", [])
            max_batch_size = command.params.get("max_batch_size", 20)
            return await self._execute_add_symbols_command(ip, port, symbols, max_batch_size)
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
        """执行添加symbols指令（先查询数据库和真实连接状态，过滤已构建的symbol）。
        
        1. 查询market_data_agent表，获取已构建的symbol
        2. 检查agent的真实连接状态（确认真实有长连接stream引用对象）
        3. 过滤掉已有真实连接的symbol，只构建未构建的
        4. 执行构建操作
        5. 等待agent返回结果
        6. 更新数据库（插入或更新market_data_agent表）
        7. 完成后续处理逻辑
        
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
        
        # 2. 检查agent的真实连接状态（确认真实有长连接stream引用对象）
        real_connections = await self.check_agent_real_connections(ip, port)
        
        # 3. 过滤掉已有真实连接的symbol（数据库中有记录且真实连接存在）
        symbols_to_build = []
        skipped_with_real_conn = []
        skipped_db_only = []
        
        for symbol in symbols:
            symbol_upper = symbol.upper()
            if symbol_upper in real_connections and real_connections[symbol_upper]:
                # 有真实连接，跳过
                skipped_with_real_conn.append(symbol_upper)
            elif symbol_upper in existing_symbols:
                # 数据库中有记录但没有真实连接，需要重新构建
                symbols_to_build.append(symbol_upper)
                logger.debug(
                    "[DataAgentManager] Symbol %s exists in DB but no real connection, will rebuild",
                    symbol_upper
                )
            else:
                # 完全新的symbol，需要构建
                symbols_to_build.append(symbol_upper)
        
        if not symbols_to_build:
            logger.info(
                "[DataAgentManager] All symbols already have real connections for %s:%s: %s (skipped: %s)",
                ip, port, len(skipped_with_real_conn), skipped_with_real_conn[:5]
            )
            # 即使没有新symbol，也要返回当前状态
            status = await self._get_agent_status_internal(ip, port)
            return {
                "status": "ok",
                "results": [],
                "current_status": status,
                "skipped_count": len(symbols),
                "skipped_with_real_conn": len(skipped_with_real_conn)
            }
        
        logger.info(
            "[DataAgentManager] Filtered symbols for %s:%s: %s with real connections, %s in DB only, %s to build",
            ip, port, len(skipped_with_real_conn), len(skipped_db_only), len(symbols_to_build)
        )
        
        # 4. 执行构建操作
        result = await self._add_symbols_to_agent_internal(ip, port, symbols_to_build, max_batch_size)
        
        # 5. 等待agent返回结果后，更新数据库
        if result and result.get("status") == "ok":
            # 6. 更新数据库（插入或更新market_data_agent表）
            await self._update_agent_status_after_add_symbols(ip, port, result)
        
        # 7. 完成后续处理逻辑，返回结果
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
    
    # ============ 全局队列管理 ============
    
    async def _process_global_command_queue(self) -> None:
        """处理全局指令队列，确保所有agent的指令顺序执行并返回结果。
        
        全局队列确保：
        1. 所有agent的指令按顺序执行
        2. 每个指令完全执行完成（包括数据库操作和后续处理）后才执行下一个
        3. 指令返回结果的顺序与执行顺序一致
        4. 即使某个agent不响应，也会超时后继续处理下一个指令，避免阻塞队列
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
                    # 执行指令（包括数据库操作和后续处理），添加超时保护
                    # 即使agent不响应，也会在超时后继续处理下一个指令
                    try:
                        result = await asyncio.wait_for(
                            self._execute_command(ip, port, command),
                            timeout=self._command_timeout
                        )
                        
                        # 确保指令完全执行完成（包括数据库操作）后才返回结果
                        if future and not future.done():
                            future.set_result(result)
                    except asyncio.TimeoutError:
                        # 超时处理：agent不响应，记录错误但继续处理下一个指令
                        timeout_error = TimeoutError(
                            f"Command {command.command_type} for {ip}:{port} timed out after {self._command_timeout}s"
                        )
                        logger.error(
                            "[DataAgentManager] ⚠️  Command timeout for %s:%s (command: %s, timeout: %ss). "
                            "Continuing with next command to avoid blocking queue.",
                            ip, port, command.command_type, self._command_timeout
                        )
                        if future and not future.done():
                            future.set_exception(timeout_error)
                        # 标记agent可能有问题
                        async with self._lock:
                            key = (ip, port)
                            if key in self._agents:
                                self._agents[key].error_log = f"Command timeout: {command.command_type}"
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
                    # 即使超时或出错，也会继续处理下一个指令，避免阻塞队列
                    
            except asyncio.CancelledError:
                logger.debug("[DataAgentManager] Global command queue processor cancelled")
                break
            except Exception as e:
                logger.error(
                    "[DataAgentManager] Error in global command queue processor: %s",
                    e, exc_info=True
                )
                # 即使出现未预期的错误，也要标记任务完成，避免阻塞队列
                try:
                    command_data = self._global_command_queue.get_nowait()
                    if command_data:
                        future = command_data.get("future")
                        if future and not future.done():
                            future.set_exception(e)
                        self._global_command_queue.task_done()
                except asyncio.QueueEmpty:
                    pass
    
    async def _enqueue_command(
        self,
        ip: str,
        port: int,
        command: AgentCommand
    ) -> Any:
        """将指令加入全局队列或直接执行。
        
        只有K线监听服务构建任务（ADD_SYMBOLS）进入全局队列，确保顺序执行并返回结果。
        其他命令（GET_STATUS等）直接执行，不进入队列。
        
        添加了超时保护，即使agent不响应也不会无限等待。
        
        Args:
            ip: agent的IP地址
            port: agent的端口号
            command: 指令对象
        
        Returns:
            指令执行结果（包括数据库操作和后续处理都完成后才返回）
            如果超时，会抛出TimeoutError异常
        """
        # 只有ADD_SYMBOLS命令需要队列管理
        if command.command_type.requires_queue():
            # 确保全局队列处理器已启动
            async with self._global_queue_lock:
                if self._global_queue_processor is None or self._global_queue_processor.done():
                    self._global_queue_processor = asyncio.create_task(
                        self._process_global_command_queue()
                    )
                    logger.debug("[DataAgentManager] Started global command queue processor")
            
            future = asyncio.Future()
            
            # 将指令加入全局队列（只有ADD_SYMBOLS进入队列）
            await self._global_command_queue.put({
                "ip": ip,
                "port": port,
                "command": command,
                "future": future
            })
            
            # 等待执行结果（包括数据库操作和后续处理都完成后才返回）
            # 添加超时保护，防止agent不响应时无限等待
            # 超时时间比队列处理器的超时时间稍长，确保队列处理器先超时
            try:
                return await asyncio.wait_for(future, timeout=self._command_timeout + 10)
            except asyncio.TimeoutError:
                logger.error(
                    "[DataAgentManager] ⚠️  Command enqueue timeout for %s:%s (command: %s). "
                    "Future may not be set by queue processor.",
                    ip, port, command.command_type
                )
                # 如果future还没有被设置，设置一个超时异常
                if not future.done():
                    future.set_exception(
                        TimeoutError(
                            f"Command enqueue timeout for {ip}:{port} after {self._command_timeout + 10}s"
                        )
                    )
                raise
        else:
            # 其他命令直接执行，不进入队列
            logger.debug(
                "[DataAgentManager] Command %s for %s:%s executed directly (no queue)",
                command.command_type, ip, port
            )
            try:
                return await asyncio.wait_for(
                    self._execute_command(ip, port, command),
                    timeout=self._command_timeout
                )
            except asyncio.TimeoutError:
                logger.error(
                    "[DataAgentManager] ⚠️  Direct command timeout for %s:%s (command: %s)",
                    ip, port, command.command_type
                )
                raise TimeoutError(
                    f"Direct command timeout for {ip}:{port} after {self._command_timeout}s"
                )
    
    # ============ Agent注册和心跳 ============
    
    async def register_agent(self, ip: str, port: int) -> bool:
        """注册data_agent（使用队列方式防止并发注册）。
        
        Args:
            ip: agent的IP地址
            port: agent的端口号
        
        Returns:
            成功返回True，失败返回False
        """
        import uuid
        
        # 使用队列方式防止并发注册
        command = AgentCommand(
            AgentCommandType.ADD_SYMBOLS,  # 复用队列机制，但实际执行注册逻辑
            command_id=str(uuid.uuid4()),
            _is_register=True,  # 标记为注册命令
            ip=ip,
            port=port
        )
        
        # 将注册命令加入队列（复用全局队列机制）
        future = asyncio.Future()
        
        # 确保全局队列处理器已启动
        async with self._global_queue_lock:
            if self._global_queue_processor is None or self._global_queue_processor.done():
                self._global_queue_processor = asyncio.create_task(
                    self._process_global_command_queue()
                )
                logger.debug("[DataAgentManager] Started global command queue processor")
        
        await self._global_command_queue.put({
            "ip": ip,
            "port": port,
            "command": command,
            "future": future,
            "is_register": True  # 标记为注册操作
        })
        
        try:
            # 等待注册完成
            result = await asyncio.wait_for(future, timeout=10)
            return result
        except asyncio.TimeoutError:
            logger.error("[DataAgentManager] ⚠️  Register timeout for %s:%s", ip, port)
            return False
    
    async def _execute_register_command(self, ip: str, port: int) -> bool:
        """执行注册命令（内部方法，在队列中执行）。
        
        注册后立即将agent状态设置为"online"并更新到数据库。
        
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
                # 重新注册时，确保状态设置为online
                agent.status = "online"
                agent.last_heartbeat = datetime.now(timezone.utc)
                agent.error_log = ""  # 清空错误日志
                if agent.register_time is None:
                    agent.register_time = datetime.now(timezone.utc)
                logger.info("[DataAgentManager] ✅ Re-registered agent: %s:%s, status set to online", ip, port)
            else:
                agent = DataAgentInfo(ip, port)
                # 新注册时，状态设置为online
                agent.status = "online"
                agent.last_heartbeat = datetime.now(timezone.utc)
                agent.register_time = datetime.now(timezone.utc)
                agent.error_log = ""  # 初始化错误日志为空
                self._agents[key] = agent
                logger.info("[DataAgentManager] ✅ Registered new agent: %s:%s, status set to online", ip, port)
            
            # 注册时创建新记录到数据库，状态设置为"online"（create_if_not_exists=True）
            await self._update_agent_in_db(agent, create_if_not_exists=True)
            logger.info("[DataAgentManager] ✅ Agent %s:%s status 'online' saved to database", ip, port)
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
    
    # ============ Agent健康检查和状态查询 ============
    
    async def check_agent_health(self, ip: str, port: int, retries: int = 2) -> bool:
        """检查agent健康状态（主动探测）。
        
        使用重试机制和更长的超时时间，避免在agent处理请求时误判为离线。
        注意：使用独立的状态检查端口（status_port），而不是指令端口（port），
        避免指令服务阻塞时影响健康检查。
        
        Args:
            ip: agent的IP地址
            port: agent的指令端口号（仅用于日志，实际使用status_port）
            retries: 重试次数（默认2次，总共最多3次尝试）
        
        Returns:
            健康返回True，不健康返回False
        """
        # 使用独立的状态检查端口，避免指令服务阻塞
        status_port = self._status_port
        # 增加超时时间到15秒，避免agent处理请求时无法及时响应
        health_check_timeout = 15
        url = f"http://{ip}:{status_port}/ping"
        
        logger.info(
            "[DataAgentManager] 🔍 [健康检查] 开始检查 agent %s:%s (状态端口: %s, 超时: %ss, 最多重试: %s次)",
            ip, port, status_port, health_check_timeout, retries
        )
        
        for attempt in range(retries + 1):
            attempt_start_time = datetime.now(timezone.utc)
            try:
                logger.info(
                    "[DataAgentManager] 📤 [健康检查] 发送ping请求到 %s:%s (状态端口: %s, 尝试 %s/%s) - URL: %s",
                    ip, port, status_port, attempt + 1, retries + 1, url
                )
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=health_check_timeout)) as response:
                        attempt_duration = (datetime.now(timezone.utc) - attempt_start_time).total_seconds()
                        
                        logger.info(
                            "[DataAgentManager] 📥 [健康检查] 收到 %s:%s 的响应 (尝试 %s/%s) - "
                            "状态码: %s, 耗时: %.3fs",
                            ip, port, attempt + 1, retries + 1, response.status, attempt_duration
                        )
                        
                        if response.status == 200:
                            data = await response.json()
                            logger.info(
                                "[DataAgentManager] ✅ [健康检查] %s:%s 响应数据: %s (尝试 %s/%s)",
                                ip, port, data, attempt + 1, retries + 1
                            )
                            
                            if data.get("status") == "ok":
                                total_duration = (datetime.now(timezone.utc) - attempt_start_time).total_seconds()
                                if attempt > 0:
                                    logger.info(
                                        "[DataAgentManager] ✅ [健康检查] %s:%s 健康检查成功 (重试 %s 次后成功, 总耗时: %.3fs)",
                                        ip, port, attempt, total_duration
                                    )
                                else:
                                    logger.info(
                                        "[DataAgentManager] ✅ [健康检查] %s:%s 健康检查成功 (首次尝试成功, 耗时: %.3fs)",
                                        ip, port, total_duration
                                    )
                                return True
                            else:
                                logger.warning(
                                    "[DataAgentManager] ⚠️  [健康检查] %s:%s 响应状态不是'ok': %s (尝试 %s/%s)",
                                    ip, port, data.get("status"), attempt + 1, retries + 1
                                )
                        else:
                            logger.warning(
                                "[DataAgentManager] ⚠️  [健康检查] %s:%s 返回非200状态码: %s (尝试 %s/%s)",
                                ip, port, response.status, attempt + 1, retries + 1
                            )
                        
                        # 如果状态码不是200，记录警告但继续重试
                        if attempt < retries:
                            logger.info(
                                "[DataAgentManager] 🔄 [健康检查] %s:%s 状态码 %s，准备重试...",
                                ip, port, response.status
                            )
            except asyncio.TimeoutError:
                attempt_duration = (datetime.now(timezone.utc) - attempt_start_time).total_seconds()
                if attempt < retries:
                    logger.warning(
                        "[DataAgentManager] ⏱️  [健康检查] %s:%s 请求超时 (尝试 %s/%s, 耗时: %.3fs, 超时设置: %ss), 等待2秒后重试...",
                        ip, port, attempt + 1, retries + 1, attempt_duration, health_check_timeout
                    )
                else:
                    logger.error(
                        "[DataAgentManager] ❌ [健康检查] %s:%s 请求超时 (尝试 %s/%s, 耗时: %.3fs, 超时设置: %ss), 所有尝试均失败",
                        ip, port, retries + 1, retries + 1, attempt_duration, health_check_timeout
                    )
            except aiohttp.ClientConnectorError as e:
                attempt_duration = (datetime.now(timezone.utc) - attempt_start_time).total_seconds()
                if attempt < retries:
                    logger.warning(
                        "[DataAgentManager] 🔌 [健康检查] %s:%s 连接错误 (尝试 %s/%s, 耗时: %.3fs): %s, 等待2秒后重试...",
                        ip, port, attempt + 1, retries + 1, attempt_duration, str(e)
                    )
                else:
                    logger.error(
                        "[DataAgentManager] ❌ [健康检查] %s:%s 连接错误 (尝试 %s/%s, 耗时: %.3fs): %s, 所有尝试均失败",
                        ip, port, retries + 1, retries + 1, attempt_duration, str(e)
                    )
            except Exception as e:
                attempt_duration = (datetime.now(timezone.utc) - attempt_start_time).total_seconds()
                if attempt < retries:
                    logger.warning(
                        "[DataAgentManager] ⚠️  [健康检查] %s:%s 请求异常 (尝试 %s/%s, 耗时: %.3fs): %s, 等待2秒后重试...",
                        ip, port, attempt + 1, retries + 1, attempt_duration, str(e), exc_info=True
                    )
                else:
                    logger.error(
                        "[DataAgentManager] ❌ [健康检查] %s:%s 请求异常 (尝试 %s/%s, 耗时: %.3fs): %s, 所有尝试均失败",
                        ip, port, retries + 1, retries + 1, attempt_duration, str(e), exc_info=True
                    )
            
            # 如果不是最后一次尝试，等待一段时间后重试
            if attempt < retries:
                logger.info(
                    "[DataAgentManager] ⏳ [健康检查] %s:%s 等待2秒后进行第 %s 次重试...",
                    ip, port, attempt + 2
                )
                await asyncio.sleep(2)  # 等待2秒后重试
        
        total_duration = (datetime.now(timezone.utc) - attempt_start_time).total_seconds()
        logger.error(
            "[DataAgentManager] ❌ [健康检查] %s:%s 健康检查最终失败 (总耗时: %.3fs, 尝试次数: %s)",
            ip, port, total_duration, retries + 1
        )
        return False
    
    async def get_agent_connection_list(self, ip: str, port: int) -> List[Dict[str, Any]]:
        """获取agent的真实连接列表（确认真实有长连接stream引用对象）。
        
        Args:
            ip: agent的IP地址
            port: agent的端口号
        
        Returns:
            连接列表，每个连接包含symbol和interval等信息
        """
        try:
            async with aiohttp.ClientSession() as session:
                url = f"http://{ip}:{port}/connections/list"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        # 兼容不同的响应格式
                        if isinstance(data, dict):
                            return data.get("connections", [])
                        return []
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
    
    # ============ Symbol分配相关方法 ============
    
    async def _add_symbols_to_agent_internal(
        self, 
        ip: str, 
        port: int, 
        symbols: List[str],
        max_batch_size: int = 20
    ) -> Optional[Dict[str, Any]]:
        """内部方法：批量向agent下发添加symbol的指令。
        
        添加了超时保护，确保即使agent不响应也不会无限等待。
        """
        if not symbols:
            return None
        
        # 分批处理，每批不超过max_batch_size个symbol
        batch_size = getattr(app_config, 'DATA_AGENT_BATCH_SYMBOL_SIZE', max_batch_size)
        all_results = []
        
        # 计算合理的超时时间：每批最多30秒，但不超过总命令超时时间
        batch_timeout = min(30, self._command_timeout // 2)
        
        for i in range(0, len(symbols), batch_size):
            batch_symbols = symbols[i:i + batch_size]
            try:
                async with aiohttp.ClientSession() as session:
                    url = f"http://{ip}:{port}/symbols/add"
                    payload = {"symbols": batch_symbols}
                    async with session.post(
                        url,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=batch_timeout)  # 使用合理的超时时间
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
            except asyncio.TimeoutError:
                logger.error(
                    "[DataAgentManager] ⚠️  Timeout adding symbols batch to %s:%s (batch size: %s, timeout: %ss)",
                    ip, port, len(batch_symbols), batch_timeout
                )
                # 超时后继续处理下一批，不中断整个流程
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
            # 即使获取状态失败，也返回部分结果
            return {
                "status": "partial",
                "results": all_results,
                "current_status": None,
                "error": str(e)
            }
    
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
    
    # ============ Agent批量管理 ============
    
    async def check_all_agents_health(self) -> None:
        """检查所有agent的健康状态。
        
        当发现agent下线时，会：
        1. 清空agent的symbol持有信息
        2. 更新agent状态到数据库
        3. 标记需要重新分配的symbol（由全量同步任务处理）
        
        使用更宽松的健康检查策略：
        - 增加健康检查超时时间（15秒）
        - 添加重试机制（最多3次尝试）
        - 避免在agent处理请求时误判为离线
        """
        async with self._lock:
            agents_to_check = list(self._agents.items())
        
        for key, agent in agents_to_check:
            check_start_time = datetime.now(timezone.utc)
            logger.info(
                "[DataAgentManager] 🔍 [状态检查] 开始检查 agent %s:%s (当前状态: %s)",
                agent.ip, agent.port, agent.status
            )
            
            # 检查心跳超时
            if agent.last_heartbeat:
                timeout_seconds = (datetime.now(timezone.utc) - agent.last_heartbeat).total_seconds()
                logger.info(
                    "[DataAgentManager] ⏰ [状态检查] agent %s:%s 上次心跳时间: %s (距今: %.1f 秒, 超时阈值: %s 秒)",
                    agent.ip, agent.port, agent.last_heartbeat.isoformat(), timeout_seconds, self._heartbeat_timeout
                )
                
                # 只有当心跳超时时间超过阈值时才进行健康检查
                # 这样可以避免频繁的健康检查，给agent更多时间处理请求
                if timeout_seconds > self._heartbeat_timeout:
                    # 心跳超时，执行主动探测（带重试）
                    logger.warning(
                        "[DataAgentManager] ⚠️  [状态检查] agent %s:%s 心跳超时 (%.1f 秒 > %s 秒)，开始执行健康检查...",
                        agent.ip, agent.port, timeout_seconds, self._heartbeat_timeout
                    )
                    is_healthy = await self.check_agent_health(agent.ip, agent.port, retries=2)
                    
                    health_check_duration = (datetime.now(timezone.utc) - check_start_time).total_seconds()
                    
                    async with self._lock:
                        if key not in self._agents:
                            logger.warning(
                                "[DataAgentManager] ⚠️  [状态检查] agent %s:%s 在健康检查过程中被移除，跳过状态更新",
                                agent.ip, agent.port
                            )
                            continue
                            
                        if is_healthy:
                            # agent恢复在线（只更新内存状态，数据库由agent自己更新）
                            logger.info(
                                "[DataAgentManager] ✅ [状态检查] agent %s:%s 健康检查通过，状态恢复为在线 (健康检查耗时: %.3fs)",
                                agent.ip, agent.port, health_check_duration
                            )
                            self._agents[key].status = "online"
                            self._agents[key].last_heartbeat = datetime.now(timezone.utc)
                            self._agents[key].error_log = ""
                        else:
                            # agent离线，清空symbol持有信息并更新数据库
                            # 只有在多次健康检查都失败的情况下才标记为离线
                            logger.error(
                                "[DataAgentManager] ❌ [状态检查] agent %s:%s 健康检查失败（心跳超时 %.1f 秒），标记为离线... (健康检查耗时: %.3fs)", 
                                agent.ip, agent.port, timeout_seconds, health_check_duration
                            )
                            
                            # 记录离线前的symbol信息（用于日志）
                            offline_symbols = set(self._agents[key].assigned_symbols)
                            if offline_symbols:
                                logger.info(
                                    "[DataAgentManager] Agent %s:%s 离线前负责的symbol数量: %s, symbols: %s", 
                                    agent.ip, agent.port, len(offline_symbols), sorted(list(offline_symbols))[:10]
                                )
                            
                            # 清空agent的symbol持有信息并更新状态
                            self._agents[key].status = "offline"
                            self._agents[key].assigned_symbols = set()
                            self._agents[key].assigned_symbol_count = 0
                            self._agents[key].connection_count = 0
                            self._agents[key].error_log = f"Agent offline since {datetime.now(timezone.utc).isoformat()} (health check failed after {timeout_seconds:.1f}s timeout)"
                            
                            # 更新数据库中的agent状态（agent已离线，无法自己更新）
                            await self._update_agent_in_db(self._agents[key], create_if_not_exists=False)
                            
                            logger.info(
                                "[DataAgentManager] ✅ Agent %s:%s 状态已更新为离线（symbol信息已清空），"
                                "将在下次全量同步时重新分配symbol",
                                agent.ip, agent.port
                            )
            else:
                # 如果没有心跳记录，也进行健康检查
                logger.warning(
                    "[DataAgentManager] ⚠️  [状态检查] agent %s:%s 无心跳记录，开始执行健康检查...",
                    agent.ip, agent.port
                )
                is_healthy = await self.check_agent_health(agent.ip, agent.port, retries=2)
                
                health_check_duration = (datetime.now(timezone.utc) - check_start_time).total_seconds()
                
                async with self._lock:
                    if key not in self._agents:
                        logger.warning(
                            "[DataAgentManager] ⚠️  [状态检查] agent %s:%s 在健康检查过程中被移除，跳过状态更新",
                            agent.ip, agent.port
                        )
                        continue
                    
                    if is_healthy:
                        logger.info(
                            "[DataAgentManager] ✅ [状态检查] agent %s:%s 无心跳记录但健康检查通过，状态设置为在线 (健康检查耗时: %.3fs)",
                            agent.ip, agent.port, health_check_duration
                        )
                        self._agents[key].status = "online"
                        self._agents[key].last_heartbeat = datetime.now(timezone.utc)
                        self._agents[key].error_log = ""
                    else:
                        # 如果没有心跳记录且健康检查失败，标记为离线
                        logger.error(
                            "[DataAgentManager] ❌ [状态检查] agent %s:%s 无心跳记录且健康检查失败，标记为离线 (健康检查耗时: %.3fs)",
                            agent.ip, agent.port, health_check_duration
                        )
                        self._agents[key].status = "offline"
                        self._agents[key].assigned_symbols = set()
                        self._agents[key].assigned_symbol_count = 0
                        self._agents[key].connection_count = 0
                        self._agents[key].error_log = f"Agent offline since {datetime.now(timezone.utc).isoformat()} (no heartbeat and health check failed)"
                        await self._update_agent_in_db(self._agents[key], create_if_not_exists=False)
            
            check_duration = (datetime.now(timezone.utc) - check_start_time).total_seconds()
            logger.info(
                "[DataAgentManager] ✅ [状态检查] agent %s:%s 检查完成 (最终状态: %s, 总耗时: %.3fs)",
                agent.ip, agent.port, self._agents[key].status if key in self._agents else "removed", check_duration
            )
    
    # ============ 数据库操作 ============
    
    async def _update_agent_in_db(self, agent: DataAgentInfo, create_if_not_exists: bool = False) -> None:
        """更新agent信息到数据库。
        
        Args:
            agent: agent信息对象
            create_if_not_exists: 如果记录不存在是否创建，False时只更新不新建（默认False）
        """
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
            await asyncio.to_thread(
                self._db.upsert_market_data_agent, 
                agent_data, 
                create_if_not_exists
            )
        except Exception as e:
            logger.error("[DataAgentManager] Failed to update agent in DB: %s", e, exc_info=True)
    
    # ============ 查询方法 ============
    
    async def get_all_agents(self) -> List[DataAgentInfo]:
        """获取所有agent信息。"""
        async with self._lock:
            return list(self._agents.values())
    
    async def get_online_agents_from_db(self) -> Dict[tuple, Dict[str, Any]]:
        """从数据库查询所有在线agent及其已分配的symbol信息。
        
        Returns:
            {(ip, port): agent_info} 字典，agent_info包含assigned_symbols等信息
        """
        try:
            agents_data = await asyncio.to_thread(self._db.get_market_data_agents, status="online")
            result = {}
            for agent_data in agents_data:
                key = (agent_data["ip"], agent_data["port"])
                result[key] = {
                    "ip": agent_data["ip"],
                    "port": agent_data["port"],
                    "assigned_symbols": set(agent_data.get("assigned_symbols", [])),
                    "assigned_symbol_count": agent_data.get("assigned_symbol_count", 0),
                    "connection_count": agent_data.get("connection_count", 0),
                    "status": agent_data.get("status", "offline")
                }
            return result
        except Exception as e:
            logger.error("[DataAgentManager] Failed to get online agents from DB: %s", e, exc_info=True)
            return {}
    
    async def check_agent_real_connections(self, ip: str, port: int) -> Dict[str, bool]:
        """检查agent的真实连接状态（确认真实有长连接stream引用对象）。
        
        Args:
            ip: agent的IP地址
            port: agent的端口号
        
        Returns:
            {symbol: has_real_connection} 字典，表示每个symbol是否有真实连接
        """
        try:
            # 通过/connections/list接口获取真实的连接列表
            connections = await self.get_agent_connection_list(ip, port)
            symbol_connections = {}
            
            for conn in connections:
                symbol = conn.get("symbol")
                if symbol:
                    # 如果连接列表中存在该symbol的连接，说明有真实连接
                    symbol_connections[symbol.upper()] = True
            
            return symbol_connections
        except Exception as e:
            logger.warning(
                "[DataAgentManager] Failed to check real connections for %s:%s: %s",
                ip, port, e
            )
            return {}


# ============ HTTP请求处理器 ============

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


# ============ HTTP服务器相关 ============

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

