"""Async agent entrypoint for background data synchronization jobs."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import signal
import sys
from typing import Awaitable, Callable, Dict, Optional

# 检查Python版本
if sys.version_info < (3, 10):
    raise RuntimeError(
        f"Python 3.10+ is required. Current version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}\n"
        "Please upgrade Python or use Python 3.10+ in your Docker image."
    )

import config as app_config

logger = logging.getLogger(__name__)


def _lazy_import_market_streams():
    """延迟导入market_streams模块，避免在Python 3.9上导入时出错"""
    from market_streams import run_market_ticker_stream, run_kline_sync_agent
    return run_market_ticker_stream, run_kline_sync_agent


def _lazy_import_kline_cleanup():
    """延迟导入kline_cleanup模块"""
    from kline_cleanup import run_cleanup_scheduler
    return run_cleanup_scheduler


def _lazy_import_price_refresh():
    """延迟导入price_refresh_service模块"""
    from price_refresh_service import run_price_refresh_scheduler
    return run_price_refresh_scheduler


def _lazy_import_leaderboard_cleanup():
    """延迟导入leaderboard_cleanup模块"""
    from leaderboard_cleanup import run_cleanup_scheduler
    return run_cleanup_scheduler


def _lazy_import_data_agent_manager():
    """延迟导入data_agent_manager模块"""
    from data_agent_manager import DataAgentManager, run_manager_http_server
    return DataAgentManager, run_manager_http_server


async def _run_market_tickers(duration: Optional[int] = None) -> None:
    run_market_ticker_stream, _ = _lazy_import_market_streams()
    await run_market_ticker_stream(run_seconds=duration)


async def _run_kline_sync(duration: Optional[int] = None) -> None:
    """运行K线同步服务"""
    _, run_kline_sync_agent = _lazy_import_market_streams()
    check_interval = getattr(app_config, 'KLINE_SYNC_CHECK_INTERVAL', 10)
    await run_kline_sync_agent(check_interval=check_interval)


async def _run_kline_cleanup(duration: Optional[int] = None) -> None:
    """运行K线清理服务"""
    run_cleanup_scheduler = _lazy_import_kline_cleanup()
    await run_cleanup_scheduler()


async def _run_price_refresh(duration: Optional[int] = None) -> None:
    """运行价格刷新服务
    
    此服务会立即执行一次价格刷新，然后根据配置的定时策略（cron表达式）循环执行
    """
    run_price_refresh_scheduler = _lazy_import_price_refresh()
    await run_price_refresh_scheduler()


async def _run_leaderboard_cleanup(duration: Optional[int] = None) -> None:
    """运行涨跌榜清理服务"""
    run_cleanup_scheduler = _lazy_import_leaderboard_cleanup()
    await run_cleanup_scheduler()


async def _run_data_agent_manager(duration: Optional[int] = None) -> None:
    """运行data_agent管理服务"""
    DataAgentManager, run_manager_http_server = _lazy_import_data_agent_manager()
    from database_clickhouse import ClickHouseDatabase
    
    db = ClickHouseDatabase()
    manager = DataAgentManager(db)
    
    # 获取配置
    register_host = '0.0.0.0'
    register_port = getattr(app_config, 'DATA_AGENT_REGISTER_PORT', 8888)
    symbol_check_interval = getattr(app_config, 'DATA_AGENT_SYMBOL_CHECK_INTERVAL', 30)
    status_check_interval = getattr(app_config, 'DATA_AGENT_STATUS_CHECK_INTERVAL', 60)
    
    # 启动HTTP服务器
    http_task = asyncio.create_task(
        run_manager_http_server(manager, register_host, register_port)
    )
    
    # 已分配的symbol集合（用于检测新增）
    allocated_symbols: Set[str] = set()
    
    async def sync_symbols_task():
        """同步symbol任务：检查新增symbol并分配任务"""
        while True:
            try:
                await asyncio.sleep(symbol_check_interval)
                
                # 获取所有market ticker中的symbol
                symbols = await asyncio.to_thread(db.get_all_market_ticker_symbols)
                symbol_set = set(symbols)
                
                # 找出新增的symbol
                new_symbols = symbol_set - allocated_symbols
                
                if new_symbols:
                    logger.info("[DataAgentManager] Found %s new symbols: %s", len(new_symbols), sorted(new_symbols)[:10])
                    
                    # 为每个新symbol的所有interval分配任务
                    intervals = ['1m', '5m', '15m', '1h', '4h', '1d', '1w']
                    for symbol in new_symbols:
                        for interval in intervals:
                            # 查找最适合的agent
                            agent_key = await manager.find_best_agent(required_connections=1)
                            if agent_key:
                                ip, port = agent_key
                                success = await manager.add_stream_to_agent(ip, port, symbol, interval)
                                if success:
                                    logger.info("[DataAgentManager] Assigned %s %s to %s:%s", symbol, interval, ip, port)
                                else:
                                    logger.warning("[DataAgentManager] Failed to assign %s %s to %s:%s", symbol, interval, ip, port)
                            else:
                                logger.warning("[DataAgentManager] No available agent for %s %s", symbol, interval)
                    
                    # 更新已分配的symbol集合
                    allocated_symbols.update(new_symbols)
                
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("[DataAgentManager] Error in sync_symbols_task: %s", e, exc_info=True)
    
    async def status_check_task():
        """状态检查任务：定时检查agent状态并刷新到数据库"""
        while True:
            try:
                await asyncio.sleep(status_check_interval)
                
                # 检查所有agent的健康状态
                await manager.check_all_agents_health()
                
                # 刷新所有agent的状态到数据库
                await manager.refresh_all_agents_status()
                
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("[DataAgentManager] Error in status_check_task: %s", e, exc_info=True)
    
    # 启动初始同步
    try:
        symbols = await asyncio.to_thread(db.get_all_market_ticker_symbols)
        allocated_symbols = set(symbols)
        logger.info("[DataAgentManager] Initialized with %s symbols", len(allocated_symbols))
    except Exception as e:
        logger.error("[DataAgentManager] Failed to initialize symbols: %s", e, exc_info=True)
    
    # 启动后台任务
    sync_task = asyncio.create_task(sync_symbols_task())
    status_task = asyncio.create_task(status_check_task())
    
    logger.info("[DataAgentManager] Started data agent manager service")
    
    try:
        if duration:
            await asyncio.sleep(duration)
            http_task.cancel()
            sync_task.cancel()
            status_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await http_task
                await sync_task
                await status_task
        else:
            # 持续运行
            done, pending = await asyncio.wait(
                {http_task, sync_task, status_task},
                return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
    except asyncio.CancelledError:
        raise
    finally:
        logger.info("[DataAgentManager] Data agent manager service stopped")


async def _run_kline_services(duration: Optional[int] = None) -> None:
    """
    运行K线清理服务
    注意：K线同步服务已被data_agent_manager取代，不再使用
    """
    run_cleanup_scheduler = _lazy_import_kline_cleanup()
    
    # 仅创建清理服务任务（移除了kline_sync）
    cleanup_task = asyncio.create_task(run_cleanup_scheduler())
    
    logger.info("[AsyncAgent] Started K-line cleanup service only (kline_sync replaced by data_agent_manager)")
    
    # 等待任务（如果duration指定，则等待指定时间后停止）
    if duration:
        await asyncio.sleep(duration)
        cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup_task
    else:
        # 持续运行，等待任务完成或取消
        await cleanup_task


async def _run_all_services(duration: Optional[int] = None) -> None:
    """
    同时运行所有任务服务：
    - market_tickers: 市场ticker数据流
    - data_agent_manager: 数据代理管理器（负责K线数据同步）
    - kline_cleanup: K线清理服务
    - price_refresh: 价格刷新服务
    - leaderboard_cleanup: 涨跌榜清理服务
    注意：kline_sync服务已被data_agent_manager取代，不再使用
    """
    run_market_ticker_stream, _ = _lazy_import_market_streams()
    run_kline_cleanup_scheduler = _lazy_import_kline_cleanup()
    run_price_refresh_scheduler = _lazy_import_price_refresh()
    run_leaderboard_cleanup_scheduler = _lazy_import_leaderboard_cleanup()
    
    # 创建所有后台任务
    market_tickers_task = asyncio.create_task(run_market_ticker_stream(run_seconds=duration))
    
    # 使用现有的_run_data_agent_manager函数来启动完整的data_agent_manager服务
    data_agent_task = asyncio.create_task(_run_data_agent_manager(duration))
    
    kline_cleanup_task = asyncio.create_task(run_kline_cleanup_scheduler())
    price_refresh_task = asyncio.create_task(run_price_refresh_scheduler())
    leaderboard_cleanup_task = asyncio.create_task(run_leaderboard_cleanup_scheduler())
    
    logger.info("[AsyncAgent] Started all services: market_tickers, data_agent_manager, kline_cleanup, price_refresh, leaderboard_cleanup")
    
    # 等待所有任务（如果duration指定，则等待指定时间后停止）
    if duration:
        await asyncio.sleep(duration)
        market_tickers_task.cancel()
        data_agent_task.cancel()
        kline_cleanup_task.cancel()
        price_refresh_task.cancel()
        leaderboard_cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await market_tickers_task
            await data_agent_task
            await kline_cleanup_task
            await price_refresh_task
            await leaderboard_cleanup_task
    else:
        # 持续运行，等待任一任务完成或取消
        all_tasks = {market_tickers_task, data_agent_task, kline_cleanup_task, price_refresh_task, leaderboard_cleanup_task}
        done, pending = await asyncio.wait(
            all_tasks,
            return_when=asyncio.FIRST_COMPLETED
        )
        # 取消其他任务
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


TASK_REGISTRY: Dict[str, Callable[[Optional[int]], Awaitable[None]]] = {
    "market_tickers": _run_market_tickers,
    "kline_sync": _run_kline_sync,
    "kline_cleanup": _run_kline_cleanup,
    "kline_services": _run_kline_services,  # 同时运行同步和清理服务
    "price_refresh": _run_price_refresh,  # 价格刷新服务
    "leaderboard_cleanup": _run_leaderboard_cleanup,  # 涨跌榜清理服务
    "data_agent_manager": _run_data_agent_manager,  # data_agent管理服务
    "all": _run_all_services,  # 运行所有任务服务
}


class AsyncAgent:
    def __init__(self) -> None:
        self._stop_event = asyncio.Event()

    async def run(self, task: str, duration: Optional[int]) -> None:
        if task not in TASK_REGISTRY:
            raise ValueError(f"Unknown task '{task}'. Available: {list(TASK_REGISTRY)}")

        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGINT, self._stop_event.set)
        loop.add_signal_handler(signal.SIGTERM, self._stop_event.set)

        logger.info("[AsyncAgent] Starting task '%s' (duration=%s)", task, duration)
        task_coro = TASK_REGISTRY[task](duration)
        worker = asyncio.create_task(task_coro)

        done, pending = await asyncio.wait(
            {worker, asyncio.create_task(self._stop_event.wait())},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if self._stop_event.is_set():
            logger.info("[AsyncAgent] Stop signal received, cancelling task...")
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker

        for pending_task in pending:
            pending_task.cancel()

        logger.info("[AsyncAgent] Task '%s' finished", task)


def _setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, app_config.LOG_LEVEL, logging.INFO),
        format=app_config.LOG_FORMAT,
        datefmt=app_config.LOG_DATE_FORMAT,
    )


def main() -> int:
    _setup_logging()

    parser = argparse.ArgumentParser(description="Async agent for ClickHouse sync tasks")
    parser.add_argument(
        "--task",
        choices=TASK_REGISTRY.keys(),
        default="all",  # 默认启动所有任务服务（market_tickers, kline_sync, kline_cleanup）
        help="Name of the async task to run",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Optional runtime in seconds before stopping the task",
    )

    args = parser.parse_args()

    agent = AsyncAgent()
    try:
        asyncio.run(agent.run(task=args.task, duration=args.duration))
    except KeyboardInterrupt:
        logger.info("[AsyncAgent] Interrupted by user")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
