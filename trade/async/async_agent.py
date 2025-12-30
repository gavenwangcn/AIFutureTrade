"""
异步代理模块 - 后台数据同步任务入口

本模块提供AsyncAgent类，用于统一管理和调度各种后台异步任务服务。

主要功能：
1. 市场数据流：market_tickers服务，实时接收币安ticker数据
2. 价格刷新：price_refresh服务，刷新24_market_tickers表的开盘价格
3. Symbol下线：market_symbol_offline服务，处理下线的交易对

支持的任务：
- market_tickers: 市场ticker数据流服务
- price_refresh: 价格刷新服务
- market_symbol_offline: 市场Symbol下线服务
- all: 运行所有服务

使用场景：
- Docker容器：通过命令行参数指定要运行的任务
- 后台服务：在docker-compose.yml中配置为独立服务

使用示例：
    # 运行所有服务（不包括K线清理）
    python -m async.async_agent --task all
    
    # 只运行价格刷新服务
    python -m async.async_agent --task price_refresh
    
    
    # 运行指定时长后停止
    python -m async.async_agent --task market_tickers --duration 3600
"""
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
# 注意：代码已合并到trade目录，需要找到trade的父目录
from pathlib import Path
project_root = Path(__file__).parent.parent.parent  # trade/async -> trade -> project root
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import trade.common.config as app_config

logger = logging.getLogger(__name__)


# ============ 延迟导入函数 ============

def _lazy_import_market_streams():
    """
    延迟导入market_streams模块
    
    延迟导入避免在Python 3.9上导入时出错，同时减少启动时的依赖加载。
    
    Returns:
        Callable: run_market_ticker_stream函数
    """
    from trade.market.market_streams import run_market_ticker_stream
    return run_market_ticker_stream


def _lazy_import_price_refresh():
    """
    延迟导入price_refresh_service模块
    
    Returns:
        Callable: run_price_refresh_scheduler函数
    """
    import importlib
    module = importlib.import_module('trade.async.price_refresh_service')
    return module.run_price_refresh_scheduler


def _lazy_import_market_symbol_offline():
    """
    延迟导入market_symbol_offline模块
    
    Returns:
        Callable: run_market_symbol_offline_scheduler函数
    """
    import importlib
    module = importlib.import_module('trade.async.market_symbol_offline')
    return module.run_market_symbol_offline_scheduler


# ============ 单个服务运行方法 ============

async def _run_market_tickers(duration: Optional[int] = None) -> None:
    """
    运行市场ticker数据流服务
    
    启动market_streams模块的ticker流服务，实时接收币安所有交易对的24小时ticker数据，
    并存储到24_market_tickers表。
    
    Args:
        duration: 可选，运行时长（秒）。如果指定，运行指定时长后停止；
                  如果为None，则无限运行直到被取消
    
    Note:
        - Ticker流每30分钟自动重连（币安WebSocket连接限制）
        - 数据实时写入24_market_tickers表
    """
    run_market_ticker_stream = _lazy_import_market_streams()
    await run_market_ticker_stream(run_seconds=duration)


# _run_kline_sync 和 _run_kline_cleanup 方法已删除，K线相关功能不再使用


async def _run_price_refresh(duration: Optional[int] = None) -> None:
    """
    运行价格刷新服务
    
    启动price_refresh_service模块的刷新调度器，定期刷新24_market_tickers表的开盘价格。
    服务会立即执行一次价格刷新，然后根据配置的定时策略（cron表达式）循环执行。
    
    Args:
        duration: 可选，运行时长（秒）。如果指定，运行指定时长后停止；
                  如果为None，则无限运行直到被取消
    
    Note:
        - 刷新逻辑：使用昨天的日K线收盘价作为今天的open_price
        - 执行频率：根据PRICE_REFRESH_CRON配置（默认每5分钟）
        - 限流控制：每分钟最多刷新1000个symbol
    """
    run_price_refresh_scheduler = _lazy_import_price_refresh()
    await run_price_refresh_scheduler()


async def _run_market_symbol_offline(duration: Optional[int] = None) -> None:
    """
    运行市场Symbol下线服务
    
    启动market_symbol_offline模块的下线调度器，定期检查并处理下线的交易对。
    
    Args:
        duration: 可选，运行时长（秒）。如果指定，运行指定时长后停止；
                  如果为None，则无限运行直到被取消
    
    Note:
        - 检测下线的交易对并更新数据库状态
        - 定期执行检查任务
    """
    run_market_symbol_offline_scheduler = _lazy_import_market_symbol_offline()
    await run_market_symbol_offline_scheduler()


# ============ 组合服务运行方法 ============

# _run_kline_services 方法已删除，K线相关功能不再使用


async def _run_all_services(duration: Optional[int] = None) -> None:
    """
    同时运行所有任务服务（不包括K线清理服务）：
    - market_tickers: 市场ticker数据流
    - price_refresh: 价格刷新服务
    - market_symbol_offline: 市场Symbol下线服务
    
    """
    run_market_ticker_stream = _lazy_import_market_streams()
    run_price_refresh_scheduler = _lazy_import_price_refresh()
    run_market_symbol_offline_scheduler = _lazy_import_market_symbol_offline()
    
    # 创建所有后台任务
    market_tickers_task = asyncio.create_task(run_market_ticker_stream(run_seconds=duration))
    price_refresh_task = asyncio.create_task(run_price_refresh_scheduler())
    market_symbol_offline_task = asyncio.create_task(run_market_symbol_offline_scheduler())
    
    logger.info("[AsyncAgent] Started all services: market_tickers, price_refresh, market_symbol_offline")
    
    # 等待所有任务（如果duration指定，则等待指定时间后停止）
    if duration:
        await asyncio.sleep(duration)
        market_tickers_task.cancel()
        price_refresh_task.cancel()
        market_symbol_offline_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await market_tickers_task
            await price_refresh_task
            await market_symbol_offline_task
    else:
        # 持续运行，等待任一任务完成或取消
        all_tasks = {market_tickers_task, price_refresh_task, market_symbol_offline_task}
        done, pending = await asyncio.wait(
            all_tasks,
            return_when=asyncio.FIRST_COMPLETED
        )
        # 取消其他任务
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


# ============ 任务注册表 ============

TASK_REGISTRY: Dict[str, Callable[[Optional[int]], Awaitable[None]]] = {
    "market_tickers": _run_market_tickers,  # 市场ticker数据流服务
    "price_refresh": _run_price_refresh,  # 价格刷新服务
    "market_symbol_offline": _run_market_symbol_offline,  # 市场Symbol下线服务
    "all": _run_all_services,  # 运行所有任务服务
}


# ============ 异步代理类 ============

class AsyncAgent:
    """
    异步代理类
    
    统一管理和调度各种后台异步任务服务，支持信号处理和优雅停止。
    
    主要特性：
    - 任务注册表：通过TASK_REGISTRY管理所有可用任务
    - 信号处理：支持SIGINT和SIGTERM信号优雅停止
    - 任务管理：支持指定运行时长或无限运行
    
    使用示例：
        agent = AsyncAgent()
        await agent.run(task='all', duration=None)  # 无限运行所有服务
        await agent.run(task='price_refresh', duration=3600)  # 运行1小时后停止
    """
    
    def __init__(self) -> None:
        """
        初始化异步代理
        
        创建停止事件，用于接收停止信号。
        """
        self._stop_event = asyncio.Event()

    async def run(self, task: str, duration: Optional[int]) -> None:
        """
        运行指定的异步任务
        
        Args:
            task: 任务名称，必须在TASK_REGISTRY中注册
            duration: 可选，运行时长（秒）。如果指定，运行指定时长后停止；
                      如果为None，则无限运行直到收到停止信号
        
        Raises:
            ValueError: 如果任务名称不在TASK_REGISTRY中
        
        Note:
            - 注册SIGINT和SIGTERM信号处理器
            - 如果收到停止信号，会优雅地取消任务
            - 任务完成后会记录日志
        """
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


# ============ 工具函数 ============

def _setup_logging() -> None:
    """
    设置日志配置
    
    从app_config读取日志级别、格式和日期格式配置。
    """
    logging.basicConfig(
        level=getattr(logging, app_config.LOG_LEVEL, logging.INFO),
        format=app_config.LOG_FORMAT,
        datefmt=app_config.LOG_DATE_FORMAT,
    )


# ============ 主入口函数 ============

def main() -> int:
    """
    主入口函数
    
    解析命令行参数，创建AsyncAgent实例并运行指定的任务。
    
    命令行参数：
    --task: 任务名称，可选值：
        - market_tickers: 市场ticker数据流服务
        - price_refresh: 价格刷新服务
        - market_symbol_offline: 市场Symbol下线服务
        - all: 运行所有服务（默认，不包括K线清理服务）
    --duration: 可选，运行时长（秒），运行指定时长后停止
    
    Returns:
        int: 退出码，0表示成功
    
    Note:
        - 默认运行所有服务（--task all）
        - 支持KeyboardInterrupt优雅停止
    """
    _setup_logging()

    parser = argparse.ArgumentParser(description="Async agent for MySQL sync tasks")
    parser.add_argument(
        "--task",
        choices=TASK_REGISTRY.keys(),
        default="all",  # 默认启动所有任务服务
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
