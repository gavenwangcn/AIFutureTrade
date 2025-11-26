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


async def _run_kline_services(duration: Optional[int] = None) -> None:
    """
    同时运行K线同步服务和清理服务
    这两个服务会作为后台任务持续运行
    """
    _, run_kline_sync_agent = _lazy_import_market_streams()
    run_cleanup_scheduler = _lazy_import_kline_cleanup()
    
    check_interval = getattr(app_config, 'KLINE_SYNC_CHECK_INTERVAL', 10)
    
    # 创建两个后台任务
    sync_task = asyncio.create_task(run_kline_sync_agent(check_interval=check_interval))
    cleanup_task = asyncio.create_task(run_cleanup_scheduler())
    
    logger.info("[AsyncAgent] Started K-line sync and cleanup services")
    
    # 等待两个任务（如果duration指定，则等待指定时间后停止）
    if duration:
        await asyncio.sleep(duration)
        sync_task.cancel()
        cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sync_task
            await cleanup_task
    else:
        # 持续运行，等待任一任务完成或取消
        done, pending = await asyncio.wait(
            {sync_task, cleanup_task},
            return_when=asyncio.FIRST_COMPLETED
        )
        # 取消另一个任务
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


async def _run_all_services(duration: Optional[int] = None) -> None:
    """
    同时运行所有任务服务：
    - market_tickers: 市场ticker数据流
    - kline_sync: K线同步服务
    - kline_cleanup: K线清理服务
    """
    run_market_ticker_stream, run_kline_sync_agent = _lazy_import_market_streams()
    run_cleanup_scheduler = _lazy_import_kline_cleanup()
    
    check_interval = getattr(app_config, 'KLINE_SYNC_CHECK_INTERVAL', 10)
    
    # 创建所有后台任务
    market_tickers_task = asyncio.create_task(run_market_ticker_stream(run_seconds=duration))
    sync_task = asyncio.create_task(run_kline_sync_agent(check_interval=check_interval))
    cleanup_task = asyncio.create_task(run_cleanup_scheduler())
    
    logger.info("[AsyncAgent] Started all services: market_tickers, kline_sync, kline_cleanup")
    
    # 等待所有任务（如果duration指定，则等待指定时间后停止）
    if duration:
        await asyncio.sleep(duration)
        market_tickers_task.cancel()
        sync_task.cancel()
        cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await market_tickers_task
            await sync_task
            await cleanup_task
    else:
        # 持续运行，等待任一任务完成或取消
        all_tasks = {market_tickers_task, sync_task, cleanup_task}
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
