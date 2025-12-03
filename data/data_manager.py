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
from typing import Optional, Set

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
    
    # 已分配的symbol集合（用于检测新增）
    allocated_symbols: Set[str] = set()
    
    async def sync_symbols_task():
        """同步symbol任务：检查新增symbol并分配任务，同时检查已有symbol的分配状态"""
        logger.info("[DataManager] 🔄 Symbol 同步任务启动")
        cycle_count = 0
        
        while True:
            try:
                cycle_count += 1
                await asyncio.sleep(symbol_check_interval)
                
                logger.debug("[DataManager] [Symbol同步 #%s] 开始检查 symbol...", cycle_count)
                
                # 获取所有market ticker中的symbol
                symbols = await asyncio.to_thread(db.get_all_market_ticker_symbols)
                symbol_set = set(symbols)
                
                logger.info("[DataManager] [Symbol同步 #%s] 当前数据库中有 %s 个 symbol", 
                           cycle_count, len(symbol_set))
                
                # 找出新增的symbol
                new_symbols = symbol_set - allocated_symbols
                
                # 定义需要处理的所有symbol（新增的+已有的）
                symbols_to_process = list(symbol_set)
                intervals = ['1m', '5m', '15m', '1h', '4h', '1d', '1w']
                
                total_assignments = 0
                failed_assignments = 0
                
                if new_symbols:
                    logger.info("[DataManager] [Symbol同步 #%s] ✨ 发现 %s 个新增 symbol: %s", 
                              cycle_count, len(new_symbols), sorted(list(new_symbols))[:10])
                
                # 为所有symbol（包括新增和已有的）分配或重新分配agent
                logger.info("[DataManager] [Symbol同步 #%s] 🚀 开始检查和分配 symbol agent...", cycle_count)
                
                for symbol in symbols_to_process:
                    for interval in intervals:
                        # 查找最适合的agent
                        agent_key = await manager.find_best_agent(required_connections=1)
                        if agent_key:
                            ip, port = agent_key
                            logger.debug("[DataManager] [Symbol同步 #%s] 尝试分配 %s %s 到 agent %s:%s", 
                                       cycle_count, symbol, interval, ip, port)
                            
                            # 直接添加流，不管是否已经存在（agent会处理重复情况）
                            success = await manager.add_stream_to_agent(ip, port, symbol, interval)
                            if success:
                                total_assignments += 1
                                if symbol in new_symbols:
                                    logger.info("[DataManager] [Symbol同步 #%s] ✅ 成功分配新增 %s %s 到 %s:%s", 
                                              cycle_count, symbol, interval, ip, port)
                                else:
                                    logger.debug("[DataManager] [Symbol同步 #%s] ✅ 成功确认/重新分配 %s %s 到 %s:%s", 
                                               cycle_count, symbol, interval, ip, port)
                            else:
                                failed_assignments += 1
                                logger.warning("[DataManager] [Symbol同步 #%s] ⚠️  分配失败 %s %s 到 %s:%s", 
                                             cycle_count, symbol, interval, ip, port)
                        else:
                            failed_assignments += 1
                            logger.warning("[DataManager] [Symbol同步 #%s] ⚠️  没有可用的 agent 用于 %s %s", 
                                         cycle_count, symbol, interval)
                
                logger.info("[DataManager] [Symbol同步 #%s] 📊 分配统计: 成功 %s, 失败 %s", 
                          cycle_count, total_assignments, failed_assignments)
                
                # 检查所有symbol-interval对是否都已分配
                logger.info("[DataManager] [Symbol同步 #%s] 🧐 开始检查所有 symbol-interval 分配状态...", cycle_count)
                
                # 获取所有需要的symbol-interval对
                required_pairs = set()
                for symbol in symbol_set:
                    for interval in intervals:
                        required_pairs.add((symbol, interval))
                
                # 获取当前已分配的symbol-interval对
                allocated_pairs = await manager.get_all_allocated_symbol_intervals()
                
                # 找出缺失的symbol-interval对
                missing_pairs = required_pairs - allocated_pairs
                
                if missing_pairs:
                    logger.warning("[DataManager] [Symbol同步 #%s] ⚠️  发现 %s 个缺失的 symbol-interval 分配", 
                                 cycle_count, len(missing_pairs))
                    
                    # 尝试为缺失的symbol-interval对重新分配agent
                    logger.info("[DataManager] [Symbol同步 #%s] 🚀 开始为缺失的 symbol-interval 重新分配 agent...", cycle_count)
                    
                    missing_total = 0
                    missing_success = 0
                    missing_failed = 0
                    
                    for symbol, interval in missing_pairs:
                        missing_total += 1
                        agent_key = await manager.find_best_agent(required_connections=1)
                        if agent_key:
                            ip, port = agent_key
                            logger.debug("[DataManager] [Symbol同步 #%s] 尝试重新分配缺失的 %s %s 到 agent %s:%s", 
                                       cycle_count, symbol, interval, ip, port)
                            
                            success = await manager.add_stream_to_agent(ip, port, symbol, interval)
                            if success:
                                missing_success += 1
                                logger.info("[DataManager] [Symbol同步 #%s] ✅ 成功重新分配缺失的 %s %s 到 %s:%s", 
                                          cycle_count, symbol, interval, ip, port)
                            else:
                                missing_failed += 1
                                logger.warning("[DataManager] [Symbol同步 #%s] ⚠️  重新分配失败缺失的 %s %s 到 %s:%s", 
                                             cycle_count, symbol, interval, ip, port)
                        else:
                            missing_failed += 1
                            logger.warning("[DataManager] [Symbol同步 #%s] ⚠️  没有可用的 agent 用于缺失的 %s %s", 
                                         cycle_count, symbol, interval)
                    
                    logger.info("[DataManager] [Symbol同步 #%s] 📊 缺失分配修复统计: 总缺失 %s, 成功修复 %s, 修复失败 %s", 
                              cycle_count, missing_total, missing_success, missing_failed)
                else:
                    logger.info("[DataManager] [Symbol同步 #%s] ✅ 所有 symbol-interval 对都已正确分配", cycle_count)
                
                # 更新已分配的symbol集合
                allocated_symbols.update(new_symbols)
                logger.info("[DataManager] [Symbol同步 #%s] 📝 已分配 symbol 总数: %s", 
                          cycle_count, len(allocated_symbols))
                
            except asyncio.CancelledError:
                logger.info("[DataManager] [Symbol同步] 任务被取消")
                raise
            except Exception as e:
                logger.error("[DataManager] [Symbol同步 #%s] ❌ 错误: %s", cycle_count, e, exc_info=True)
    
    async def status_check_task():
        """状态检查任务：定时检查agent状态并刷新到数据库"""
        logger.info("[DataManager] 🔍 Agent 状态检查任务启动")
        cycle_count = 0
        
        while True:
            try:
                cycle_count += 1
                await asyncio.sleep(status_check_interval)
                
                logger.info("[DataManager] [状态检查 #%s] 开始检查所有 agent 的健康状态...", cycle_count)
                
                # 检查所有agent的健康状态
                await manager.check_all_agents_health()
                logger.debug("[DataManager] [状态检查 #%s] 健康检查完成", cycle_count)
                
                # 刷新所有agent的状态到数据库
                logger.debug("[DataManager] [状态检查 #%s] 开始刷新 agent 状态到数据库...", cycle_count)
                await manager.refresh_all_agents_status()
                
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
    
    # 启动初始同步
    logger.info("[DataManager] 🔄 执行初始 symbol 同步...")
    try:
        symbols = await asyncio.to_thread(db.get_all_market_ticker_symbols)
        allocated_symbols = set(symbols)
        logger.info("[DataManager] ✅ 初始同步完成，共 %s 个 symbol", len(allocated_symbols))
        if allocated_symbols:
            logger.info("[DataManager] 📋 初始 symbol 列表（前20个）: %s", 
                      sorted(list(allocated_symbols))[:20])
            
            # 为初始symbol分配agent
            logger.info("[DataManager] 🚀 开始为初始 symbol 分配 agent...")
            intervals = ['1m', '5m', '15m', '1h', '4h', '1d', '1w']
            total_assignments = 0
            failed_assignments = 0
            
            for symbol in allocated_symbols:
                for interval in intervals:
                    # 查找最适合的agent
                    agent_key = await manager.find_best_agent(required_connections=1)
                    if agent_key:
                        ip, port = agent_key
                        logger.debug("[DataManager] [初始分配] 尝试分配 %s %s 到 agent %s:%s", 
                                   symbol, interval, ip, port)
                        
                        success = await manager.add_stream_to_agent(ip, port, symbol, interval)
                        if success:
                            total_assignments += 1
                            logger.debug("[DataManager] [初始分配] ✅ 成功分配 %s %s 到 %s:%s", 
                                       symbol, interval, ip, port)
                        else:
                            failed_assignments += 1
                            logger.warning("[DataManager] [初始分配] ⚠️  分配失败 %s %s 到 %s:%s", 
                                         symbol, interval, ip, port)
                    else:
                        failed_assignments += 1
                        logger.warning("[DataManager] [初始分配] ⚠️  没有可用的 agent 用于 %s %s", 
                                     symbol, interval)
            
            logger.info("[DataManager] 📊 初始分配统计: 成功 %s, 失败 %s", 
                      total_assignments, failed_assignments)
            logger.info("[DataManager] ✅ 初始 agent 分配完成")
    except Exception as e:
        logger.error("[DataManager] ❌ 初始同步失败: %s", e, exc_info=True)
        # 不抛出异常，允许服务继续运行
    
    # 启动后台任务
    logger.info("[DataManager] 🚀 启动后台任务...")
    sync_task = asyncio.create_task(sync_symbols_task())
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
            sync_task.cancel()
            status_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await http_task
                await sync_task
                await status_task
        else:
            # 持续运行
            logger.info("[DataManager] 🔄 服务持续运行中...")
            done, pending = await asyncio.wait(
                {http_task, sync_task, status_task},
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

