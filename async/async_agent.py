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

# 添加项目根目录到Python路径（用于Docker容器中运行）
from pathlib import Path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import common.config as app_config

logger = logging.getLogger(__name__)


def _lazy_import_market_streams():
    """延迟导入market_streams模块，避免在Python 3.9上导入时出错"""
    from market.market_streams import run_market_ticker_stream, run_kline_sync_agent
    return run_market_ticker_stream, run_kline_sync_agent


def _lazy_import_kline_cleanup():
    """延迟导入kline_cleanup模块"""
    from .kline_cleanup import run_cleanup_scheduler
    return run_cleanup_scheduler


def _lazy_import_price_refresh():
    """延迟导入price_refresh_service模块"""
    from .price_refresh_service import run_price_refresh_scheduler
    return run_price_refresh_scheduler


def _lazy_import_leaderboard_cleanup():
    """延迟导入leaderboard_cleanup模块"""
    from .leaderboard_cleanup import run_cleanup_scheduler
    return run_cleanup_scheduler


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
    """运行data_agent管理服务（已废弃，请使用独立的 data_manager.py 服务）
    
    注意：此功能已迁移到独立的 data_manager.py 模块。
    在 docker-compose.yml 中使用 data-manager 服务替代。
    """
    logger.warning("[AsyncAgent] _run_data_agent_manager 已废弃，请使用独立的 data_manager.py 服务")
    logger.warning("[AsyncAgent] 在 docker-compose.yml 中使用 data-manager 服务替代")
    raise NotImplementedError(
        "data_agent_manager 功能已迁移到独立的 data_manager.py 模块。"
        "请使用 docker-compose.yml 中的 data-manager 服务。"
    )


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
    - kline_cleanup: K线清理服务
    - price_refresh: 价格刷新服务
    - leaderboard_cleanup: 涨跌榜清理服务
    
    注意：
    - kline_sync服务已被data_agent_manager取代，不再使用
    - data_agent_manager 已迁移到独立的 data_manager.py 服务，请使用 docker-compose.yml 中的 data-manager 服务
    """
    run_market_ticker_stream, _ = _lazy_import_market_streams()
    run_kline_cleanup_scheduler = _lazy_import_kline_cleanup()
    run_price_refresh_scheduler = _lazy_import_price_refresh()
    run_leaderboard_cleanup_scheduler = _lazy_import_leaderboard_cleanup()
    
    # 创建所有后台任务
    market_tickers_task = asyncio.create_task(run_market_ticker_stream(run_seconds=duration))
    
    # 注意：data_agent_manager 已迁移到独立的 data_manager.py 服务
    # 不再在此处启动，请使用 docker-compose.yml 中的 data-manager 服务
    
    kline_cleanup_task = asyncio.create_task(run_kline_cleanup_scheduler())
    price_refresh_task = asyncio.create_task(run_price_refresh_scheduler())
    leaderboard_cleanup_task = asyncio.create_task(run_leaderboard_cleanup_scheduler())
    
    logger.info("[AsyncAgent] Started all services: market_tickers, kline_cleanup, price_refresh, leaderboard_cleanup")
    logger.info("[AsyncAgent] Note: data_agent_manager is now a separate service (data-manager), see docker-compose.yml")
    
    # 等待所有任务（如果duration指定，则等待指定时间后停止）
    if duration:
        await asyncio.sleep(duration)
        market_tickers_task.cancel()
        kline_cleanup_task.cancel()
        price_refresh_task.cancel()
        leaderboard_cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await market_tickers_task
            await kline_cleanup_task
            await price_refresh_task
            await leaderboard_cleanup_task
    else:
        # 持续运行，等待任一任务完成或取消
        all_tasks = {market_tickers_task, kline_cleanup_task, price_refresh_task, leaderboard_cleanup_task}
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
    # 注意：data_agent_manager 已迁移到独立的 data_manager.py 服务
    # 请使用 docker-compose.yml 中的 data-manager 服务
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
