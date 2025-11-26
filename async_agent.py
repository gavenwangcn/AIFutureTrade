"""Async agent entrypoint for background data synchronization jobs."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import signal
from typing import Awaitable, Callable, Dict, Optional

import config as app_config
from market_streams import run_market_ticker_stream

logger = logging.getLogger(__name__)


async def _run_market_tickers(duration: Optional[int] = None) -> None:
    await run_market_ticker_stream(run_seconds=duration)


TASK_REGISTRY: Dict[str, Callable[[Optional[int]], Awaitable[None]]] = {
    "market_tickers": _run_market_tickers,
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
        default="market_tickers",
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
