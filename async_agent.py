"""Async agent entrypoint for background data synchronization jobs."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import signal
from typing import Awaitable, Callable, Dict, Optional

import config as app_config
from market_streams import run_market_ticker_stream, run_kline_sync_agent
from kline_cleanup import run_cleanup_scheduler

logger = logging.getLogger(__name__)


async def _run_market_tickers(duration: Optional[int] = None) -> None:
    await run_market_ticker_stream(run_seconds=duration)


async def _run_kline_sync(duration: Optional[int] = None) -> None:
    """运行K线同步服务"""
    check_interval = getattr(app_config, 'KLINE_SYNC_CHECK_INTERVAL', 10)
    await run_kline_sync_agent(check_interval=check_interval)


async def _run_kline_cleanup(duration: Optional[int] = None) -> None:
    """运行K线清理服务"""
    await run_cleanup_scheduler()


async def _run_kline_services(duration: Optional[int] = None) -> None:
    """
    同时运行K线同步服务和清理服务
    这两个服务会作为后台任务持续运行
    """
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


TASK_REGISTRY: Dict[str, Callable[[Optional[int]], Awaitable[None]]] = {
    "market_tickers": _run_market_tickers,
    "kline_sync": _run_kline_sync,
    "kline_cleanup": _run_kline_cleanup,
    "kline_services": _run_kline_services,  # 同时运行同步和清理服务
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
        default="kline_services",  # 默认启动K线服务（包含同步和清理）
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
