"""Data Manager Service - 独立的数据代理管理服务

此模块负责管理所有 data_agent 实例，包括：
- 接收 data_agent 的注册和心跳
- 监控 data_agent 的健康状态
- 分配 K线数据同步任务到各个 data_agent
- 检测新增的 symbol 并自动分配任务
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import signal
import sys
from typing import Optional, Set, Dict, List

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

import common.config as app_config
from data.data_agent_manager import DataAgentManager, run_manager_http_server
from common.database_clickhouse import ClickHouseDatabase

logger = logging.getLogger(__name__)


async def run_data_manager_service(duration: Optional[int] = None) -> None:
    """运行 data_agent 管理服务
    
    Args:
        duration: 运行时长（秒），None 表示持续运行
    """
    logger.info("=" * 80)
    logger.info("[DataManager] 🚀 启动 Data Manager 服务")
    logger.info("=" * 80)
    
    # 初始化数据库连接
    logger.info("[DataManager] 📊 初始化 ClickHouse 数据库连接...")
    try:
        db = ClickHouseDatabase()
        logger.info("[DataManager] ✅ ClickHouse 数据库连接成功")
    except Exception as e:
        logger.error("[DataManager] ❌ ClickHouse 数据库连接失败: %s", e, exc_info=True)
        raise
    
    # 初始化 DataAgentManager
    logger.info("[DataManager] 🔧 初始化 DataAgentManager...")
    try:
        manager = DataAgentManager(db)
        logger.info("[DataManager] ✅ DataAgentManager 初始化成功")
    except Exception as e:
        logger.error("[DataManager] ❌ DataAgentManager 初始化失败: %s", e, exc_info=True)
        raise
    
    # 获取配置
    register_host = '0.0.0.0'
    register_port = getattr(app_config, 'DATA_AGENT_REGISTER_PORT', 8888)
    symbol_check_interval = getattr(app_config, 'DATA_AGENT_SYMBOL_CHECK_INTERVAL', 30)
    status_check_interval = getattr(app_config, 'DATA_AGENT_STATUS_CHECK_INTERVAL', 60)
    
    logger.info("[DataManager] 📋 配置信息:")
    logger.info("[DataManager]   - 注册服务地址: %s:%s", register_host, register_port)
    logger.info("[DataManager]   - Symbol 检查间隔: %s 秒", symbol_check_interval)
    logger.info("[DataManager]   - 状态检查间隔: %s 秒", status_check_interval)
    
    # 启动HTTP服务器（用于接收 data_agent 的注册和心跳）
    logger.info("[DataManager] 🌐 启动 HTTP 服务器 (端口: %s)...", register_port)
    try:
        http_task = asyncio.create_task(
            run_manager_http_server(manager, register_host, register_port)
        )
        # 等待服务器启动
        await asyncio.sleep(0.5)
        logger.info("[DataManager] ✅ HTTP 服务器启动成功，监听地址: %s:%s", register_host, register_port)
    except Exception as e:
        logger.error("[DataManager] ❌ HTTP 服务器启动失败: %s", e, exc_info=True)
        raise
    
    async def full_sync_task():
        """全量同步任务：合并初始同步和定时同步，智能分配symbol到agent。
        
        执行流程：
        1. 计算所有symbol任务总数
        2. 查询数据库中在线agent的已有分配信息
        3. 智能分配：已有symbol继续分配给原agent，新增symbol均匀分配
        4. 将分配关系存入数据库
        5. 通过全局队列下发任务到agent执行（agent会检查真实连接状态）
        """
        logger.info("[DataManager] 🔄 全量同步任务启动")
        cycle_count = 0
        full_sync_interval = getattr(app_config, 'DATA_AGENT_FULL_SYNC_INTERVAL', 180)
        
        while True:
            try:
                cycle_count += 1
                if cycle_count == 1:
                    # 第一次执行，立即开始
                    logger.info("[DataManager] [全量同步 #%s] 🚀 开始首次全量同步...", cycle_count)
                else:
                    await asyncio.sleep(full_sync_interval)
                    logger.info("[DataManager] [全量同步 #%s] 🚀 开始定时全量同步...", cycle_count)
                
                # 1. 计算所有symbol任务总数
                logger.info("[DataManager] [全量同步 #%s] 📊 步骤1: 计算所有symbol任务总数...", cycle_count)
                symbols = await asyncio.to_thread(db.get_all_market_ticker_symbols)
                symbol_set = set(symbols)
                total_symbols = len(symbol_set)
                logger.info("[DataManager] [全量同步 #%s] ✅ 当前数据库中有 %s 个 symbol", cycle_count, total_symbols)
                
                if not symbol_set:
                    logger.warning("[DataManager] [全量同步 #%s] ⚠️  没有symbol需要处理", cycle_count)
                    continue
                
                # 2. 查询数据库中在线agent的已有分配信息
                logger.info("[DataManager] [全量同步 #%s] 📊 步骤2: 查询数据库中在线agent的已有分配信息...", cycle_count)
                online_agents_from_db = await manager.get_online_agents_from_db()
                logger.info("[DataManager] [全量同步 #%s] ✅ 查询到 %s 个在线agent", cycle_count, len(online_agents_from_db))
                
                # 构建symbol到agent的映射（已有分配）
                symbol_to_agent: Dict[str, tuple] = {}  # {symbol: (ip, port)}
                agent_symbol_count: Dict[tuple, int] = {}  # {(ip, port): count}
                
                for agent_key, agent_info in online_agents_from_db.items():
                    ip, port = agent_key
                    assigned_symbols = agent_info.get("assigned_symbols", set())
                    agent_symbol_count[agent_key] = len(assigned_symbols)
                    
                    for symbol in assigned_symbols:
                        symbol_upper = symbol.upper()
                        if symbol_upper in symbol_set:
                            # 只保留当前存在的symbol
                            symbol_to_agent[symbol_upper] = agent_key
                
                logger.info(
                    "[DataManager] [全量同步 #%s] ✅ 已有分配: %s 个symbol已分配给agent",
                    cycle_count, len(symbol_to_agent)
                )
                
                # 3. 智能分配：已有symbol继续分配给原agent，新增symbol均匀分配
                logger.info("[DataManager] [全量同步 #%s] 📊 步骤3: 智能分配symbol到agent...", cycle_count)
                
                # 找出需要分配的symbol（新增的或需要重新分配的）
                symbols_to_assign = symbol_set - set(symbol_to_agent.keys())
                logger.info(
                    "[DataManager] [全量同步 #%s] ✅ 需要分配的symbol: %s 个（已有 %s 个继续使用原分配）",
                    cycle_count, len(symbols_to_assign), len(symbol_to_agent)
                )
                
                # 获取所有在线agent（从内存中）
                all_agents = await manager.get_all_agents()
                online_agents_mem = [
                    ((agent.ip, agent.port), agent) for agent in all_agents
                    if agent.status == "online"
                ]
                
                if not online_agents_mem:
                    logger.error("[DataManager] [全量同步 #%s] ❌ 没有可用的在线agent", cycle_count)
                    continue
                
                # 均匀分配新增symbol到agent
                symbols_per_agent: Dict[tuple, List[str]] = {}  # {(ip, port): [symbols]}
                
                # 先为已有分配的symbol分组
                for symbol, agent_key in symbol_to_agent.items():
                    if agent_key not in symbols_per_agent:
                        symbols_per_agent[agent_key] = []
                    symbols_per_agent[agent_key].append(symbol)
                
                # 均匀分配新增symbol
                agent_list = [(key, agent) for key, agent in online_agents_mem]
                max_symbols_per_agent = getattr(app_config, 'DATA_AGENT_MAX_SYMBOL', 150)
                
                for idx, symbol in enumerate(sorted(symbols_to_assign)):
                    # 找到负载最低的agent
                    best_agent_key = None
                    min_load = float('inf')
                    
                    for agent_key, agent in agent_list:
                        current_count = len(symbols_per_agent.get(agent_key, []))
                        if current_count < max_symbols_per_agent:
                            load = current_count / max_symbols_per_agent
                            if load < min_load:
                                min_load = load
                                best_agent_key = agent_key
                    
                    if best_agent_key:
                        if best_agent_key not in symbols_per_agent:
                            symbols_per_agent[best_agent_key] = []
                        symbols_per_agent[best_agent_key].append(symbol)
                    else:
                        logger.warning(
                            "[DataManager] [全量同步 #%s] ⚠️  所有agent已满，无法分配symbol: %s",
                            cycle_count, symbol
                        )
                
                logger.info(
                    "[DataManager] [全量同步 #%s] ✅ 分配完成: %s 个agent将处理symbol",
                    cycle_count, len(symbols_per_agent)
                )
                
                # 4. 将分配关系存入数据库（通过更新agent状态）
                logger.info("[DataManager] [全量同步 #%s] 📊 步骤4: 更新分配关系到数据库...", cycle_count)
                all_agents_dict = {((agent.ip, agent.port), agent) for agent in await manager.get_all_agents()}
                for agent_key, symbols_list in symbols_per_agent.items():
                    ip, port = agent_key
                    # 更新内存中的agent信息并同步到数据库
                    agent_found = None
                    for (a_ip, a_port), agent in all_agents_dict:
                        if a_ip == ip and a_port == port:
                            agent_found = agent
                            break
                    
                    if agent_found:
                        agent_found.assigned_symbols = set(symbols_list)
                        agent_found.assigned_symbol_count = len(symbols_list)
                        # 更新数据库
                        await manager._update_agent_in_db(agent_found)
                
                logger.info("[DataManager] [全量同步 #%s] ✅ 分配关系已更新到数据库", cycle_count)
                
                # 5. 通过全局队列下发任务到agent执行
                logger.info("[DataManager] [全量同步 #%s] 📊 步骤5: 通过全局队列下发任务到agent执行...", cycle_count)
                
                # 在执行K线监听指令下发前，再次检查是否有在线agent
                all_agents_check = await manager.get_all_agents()
                online_agents_check = [
                    agent for agent in all_agents_check
                    if agent.status == "online"
                ]
                
                if not online_agents_check:
                    logger.warning(
                        "[DataManager] [全量同步 #%s] ⚠️  没有在线agent，跳过K线监听指令下发，等待下一个循环",
                        cycle_count
                    )
                    continue
                
                logger.info(
                    "[DataManager] [全量同步 #%s] ✅ 检测到 %s 个在线agent，开始下发K线监听指令",
                    cycle_count, len(online_agents_check)
                )
                
                batch_size = getattr(app_config, 'DATA_AGENT_BATCH_SYMBOL_SIZE', 20)
                success_count = 0
                failed_assignments = 0
                
                for agent_key, symbols_list in symbols_per_agent.items():
                    ip, port = agent_key
                    
                    # 检查该agent是否仍然在线
                    agent_still_online = False
                    for agent in online_agents_check:
                        if agent.ip == ip and agent.port == port:
                            agent_still_online = True
                            break
                    
                    if not agent_still_online:
                        logger.warning(
                            "[DataManager] [全量同步 #%s] ⚠️  Agent %s:%s 已离线，跳过K线监听指令下发",
                            cycle_count, ip, port
                        )
                        failed_assignments += len(symbols_list)
                        continue
                    
                    # 分批处理，每批不超过batch_size个symbol
                    for i in range(0, len(symbols_list), batch_size):
                        batch_symbols = symbols_list[i:i + batch_size]
                        logger.info(
                            "[DataManager] [全量同步 #%s] 🚀 批量分配 %s 个 symbol 到 agent %s:%s (批次 %s/%s)",
                            cycle_count, len(batch_symbols), ip, port,
                            i // batch_size + 1, (len(symbols_list) + batch_size - 1) // batch_size
                        )
                        
                        try:
                            result = await manager.add_symbols_to_agent(ip, port, batch_symbols, batch_size)
                            if result and result.get("status") == "ok":
                                # 统计成功和失败数量
                                results = result.get("results", [])
                                for r in results:
                                    success_count += r.get("success_count", 0)
                                    failed_count = r.get("failed_count", 0)
                                    failed_assignments += failed_count
                                
                                # 获取当前状态
                                current_status = result.get("current_status", {})
                                logger.info(
                                    "[DataManager] [全量同步 #%s] ✅ 批量分配完成，agent %s:%s 当前连接数: %s",
                                    cycle_count, ip, port, current_status.get("connection_count", 0)
                                )
                            else:
                                # 批量失败
                                failed_assignments += len(batch_symbols)
                                logger.warning(
                                    "[DataManager] [全量同步 #%s] ⚠️  批量分配失败，agent %s:%s",
                                    cycle_count, ip, port
                                )
                        except Exception as e:
                            failed_assignments += len(batch_symbols)
                            logger.error(
                                "[DataManager] [全量同步 #%s] ❌ 批量分配异常，agent %s:%s: %s",
                                cycle_count, ip, port, e, exc_info=True
                            )
                
                logger.info(
                    "[DataManager] [全量同步 #%s] 📊 执行统计: 成功 %s, 失败 %s, 总symbol数: %s",
                    cycle_count, success_count, failed_assignments, total_symbols
                )
                logger.info("[DataManager] [全量同步 #%s] ✅ 全量同步完成", cycle_count)
                
            except asyncio.CancelledError:
                logger.info("[DataManager] [全量同步] 任务被取消")
                raise
            except Exception as e:
                logger.error("[DataManager] [全量同步 #%s] ❌ 错误: %s", cycle_count, e, exc_info=True)
    
    async def status_check_task():
        """状态检查任务：定时检查agent状态并刷新到数据库"""
        logger.info("[DataManager] 🔍 Agent 状态检查任务启动")
        cycle_count = 0
        
        while True:
            try:
                cycle_count += 1
                await asyncio.sleep(status_check_interval)
                
                logger.info("[DataManager] [状态检查 #%s] 开始检查所有 agent 的健康状态...", cycle_count)
                
                # 检查所有agent的健康状态（不再同步连接数信息，由agent自己更新）
                await manager.check_all_agents_health()
                logger.debug("[DataManager] [状态检查 #%s] 健康检查完成", cycle_count)
                
                # 获取所有agent信息并记录
                agents = await manager.get_all_agents()
                online_count = sum(1 for agent in agents if agent.status == "online")
                offline_count = len(agents) - online_count
                total_connections = sum(agent.connection_count for agent in agents)
                
                logger.info("[DataManager] [状态检查 #%s] 📊 Agent 状态统计:", cycle_count)
                logger.info("[DataManager]   - 总 agent 数: %s", len(agents))
                logger.info("[DataManager]   - 在线: %s", online_count)
                logger.info("[DataManager]   - 离线: %s", offline_count)
                logger.info("[DataManager]   - 总连接数: %s", total_connections)
                
                # 记录每个agent的详细信息
                for agent in agents:
                    logger.debug("[DataManager]   - Agent %s:%s - 状态: %s, 连接数: %s, Symbol数: %s", 
                               agent.ip, agent.port, agent.status, agent.connection_count, 
                               agent.assigned_symbol_count)
                
            except asyncio.CancelledError:
                logger.info("[DataManager] [状态检查] 任务被取消")
                raise
            except Exception as e:
                logger.error("[DataManager] [状态检查 #%s] ❌ 错误: %s", cycle_count, e, exc_info=True)
    
    # 启动后台任务（全量同步任务已合并初始同步和定时同步）
    logger.info("[DataManager] 🚀 启动后台任务...")
    full_sync_task_instance = asyncio.create_task(full_sync_task())
    status_task = asyncio.create_task(status_check_task())
    logger.info("[DataManager] ✅ 所有后台任务已启动")
    
    logger.info("=" * 80)
    logger.info("[DataManager] ✅ Data Manager 服务启动完成，所有组件运行正常")
    logger.info("=" * 80)
    
    try:
        if duration:
            logger.info("[DataManager] ⏱️  服务将在 %s 秒后停止", duration)
            await asyncio.sleep(duration)
            logger.info("[DataManager] 🛑 停止服务...")
            http_task.cancel()
            full_sync_task_instance.cancel()
            status_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await http_task
                await full_sync_task_instance
                await status_task
        else:
            # 持续运行
            logger.info("[DataManager] 🔄 服务持续运行中...")
            done, pending = await asyncio.wait(
                {http_task, full_sync_task_instance, status_task},
                return_when=asyncio.FIRST_COMPLETED
            )
            logger.warning("[DataManager] ⚠️  检测到任务完成，开始停止其他任务...")
            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
    except asyncio.CancelledError:
        logger.info("[DataManager] 🛑 收到取消信号")
        raise
    finally:
        logger.info("=" * 80)
        logger.info("[DataManager] 🛑 Data Manager 服务已停止")
        logger.info("=" * 80)


class DataManager:
    """Data Manager 服务主类"""
    
    def __init__(self) -> None:
        self._stop_event = asyncio.Event()
    
    async def run(self, duration: Optional[int] = None) -> None:
        """运行 Data Manager 服务
        
        Args:
            duration: 运行时长（秒），None 表示持续运行
        """
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGINT, self._stop_event.set)
        loop.add_signal_handler(signal.SIGTERM, self._stop_event.set)
        
        logger.info("[DataManager] 启动 Data Manager 服务 (duration=%s)", duration)
        service_task = asyncio.create_task(run_data_manager_service(duration))
        
        done, pending = await asyncio.wait(
            {service_task, asyncio.create_task(self._stop_event.wait())},
            return_when=asyncio.FIRST_COMPLETED,
        )
        
        if self._stop_event.is_set():
            logger.info("[DataManager] 收到停止信号，正在取消服务...")
            service_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await service_task
        
        for pending_task in pending:
            pending_task.cancel()
        
        logger.info("[DataManager] Data Manager 服务已结束")


def _setup_logging() -> None:
    """设置日志配置"""
    logging.basicConfig(
        level=getattr(logging, app_config.LOG_LEVEL, logging.INFO),
        format=app_config.LOG_FORMAT,
        datefmt=app_config.LOG_DATE_FORMAT,
    )


def main() -> int:
    """主入口函数"""
    _setup_logging()
    
    parser = argparse.ArgumentParser(description="Data Manager Service for managing data agents")
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Optional runtime in seconds before stopping the service",
    )
    
    args = parser.parse_args()
    
    manager = DataManager()
    try:
        asyncio.run(manager.run(duration=args.duration))
    except KeyboardInterrupt:
        logger.info("[DataManager] 被用户中断")
    except Exception as e:
        logger.error("[DataManager] 服务异常退出: %s", e, exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

