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
- kline_cleanup: K线清理服务（默认不启用，仅在data目录相关任务中使用）
- kline_services: K线相关服务（清理，默认不启用，仅在data目录相关任务中使用）
- all: 运行所有服务（不包括K线清理服务）

已废弃的服务：
- kline_sync: 已被data_agent_manager取代（保留在注册表中以兼容旧代码）
- data_agent_manager: 已迁移到独立的data_manager.py服务

K线相关服务说明：
- K线清理服务（kline_cleanup）默认不包含在 `all` 任务中
- K线相关任务应由data目录下的data_manager.py服务管理
- 如需单独运行K线清理，可显式指定：--task kline_cleanup

使用场景：
- Docker容器：通过命令行参数指定要运行的任务
- 后台服务：在docker-compose.yml中配置为独立服务

使用示例：
    # 运行所有服务（不包括K线清理）
    python -m async.async_agent --task all
    
    # 只运行价格刷新服务
    python -m async.async_agent --task price_refresh
    
    # 单独运行K线清理服务（不推荐，应由data_manager管理）
    python -m async.async_agent --task kline_cleanup
    
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
from pathlib import Path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import common.config as app_config

logger = logging.getLogger(__name__)


# ============ 延迟导入函数 ============

def _lazy_import_market_streams():
    """
    延迟导入market_streams模块
    
    延迟导入避免在Python 3.9上导入时出错，同时减少启动时的依赖加载。
    
    Returns:
        Tuple: (run_market_ticker_stream, run_kline_sync_agent)
               run_kline_sync_agent已废弃，但保留以兼容旧代码
    """
    from market.market_streams import run_market_ticker_stream, run_kline_sync_agent
    return run_market_ticker_stream, run_kline_sync_agent


def _lazy_import_kline_cleanup():
    """
    延迟导入kline_cleanup模块
    
    Returns:
        Callable: run_cleanup_scheduler函数
    """
    import importlib
    module = importlib.import_module('async.kline_cleanup')
    return module.run_cleanup_scheduler


def _lazy_import_price_refresh():
    """
    延迟导入price_refresh_service模块
    
    Returns:
        Callable: run_price_refresh_scheduler函数
    """
    import importlib
    module = importlib.import_module('async.price_refresh_service')
    return module.run_price_refresh_scheduler


def _lazy_import_market_symbol_offline():
    """
    延迟导入market_symbol_offline模块
    
    Returns:
        Callable: run_market_symbol_offline_scheduler函数
    """
    import importlib
    module = importlib.import_module('async.market_symbol_offline')
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
    run_market_ticker_stream, _ = _lazy_import_market_streams()
    await run_market_ticker_stream(run_seconds=duration)


async def _run_kline_sync(duration: Optional[int] = None) -> None:
    """
    运行K线同步服务（已废弃）
    
    注意：此服务已废弃，K线流管理现在由data_agent模块处理。
    保留此方法仅用于兼容旧代码。
    
    Args:
        duration: 可选，运行时长（秒），已不再使用
    
    Deprecated:
        此服务已被data_agent_manager取代，请使用data_agent模块的K线流管理功能。
    """
    _, run_kline_sync_agent = _lazy_import_market_streams()
    check_interval = getattr(app_config, 'KLINE_SYNC_CHECK_INTERVAL', 10)
    await run_kline_sync_agent(check_interval=check_interval)


async def _run_kline_cleanup(duration: Optional[int] = None) -> None:
    """
    运行K线清理服务
    
    启动kline_cleanup模块的清理调度器，定期清理过期的K线数据。
    
    Args:
        duration: 可选，运行时长（秒）。如果指定，运行指定时长后停止；
                  如果为None，则无限运行直到被取消
    
    Note:
        - 清理策略：删除超过指定天数的K线数据（默认2天）
        - 按时间周期分表清理（1m, 5m, 15m, 1h, 4h, 1d, 1w）
    """
    run_cleanup_scheduler = _lazy_import_kline_cleanup()
    await run_cleanup_scheduler()


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

async def _run_kline_services(duration: Optional[int] = None) -> None:
    """
    运行K线相关服务（组合服务）
    
    注意：K线同步服务已被data_agent_manager取代，不再使用。
    此方法现在只运行K线清理服务。
    
    Args:
        duration: 可选，运行时长（秒）。如果指定，运行指定时长后停止；
                  如果为None，则无限运行直到被取消
    
    Note:
        - 原本同时运行kline_sync和kline_cleanup
        - 现在只运行kline_cleanup（kline_sync已被data_agent_manager取代）
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
    同时运行所有任务服务（不包括K线清理服务）：
    - market_tickers: 市场ticker数据流
    - price_refresh: 价格刷新服务
    - market_symbol_offline: 市场Symbol下线服务
    
    注意：
    - kline_cleanup服务默认不包含在此方法中，K线相关任务应由data目录下的data_manager.py服务管理
    - kline_sync服务已被data_agent_manager取代，不再使用
    - data_agent_manager 已迁移到独立的 data_manager.py 服务，请使用 docker-compose.yml 中的 data-manager 服务
    - leaderboard_cleanup服务已移除，涨跌榜数据现在直接从24_market_tickers表查询，无需清理
    """
    run_market_ticker_stream, _ = _lazy_import_market_streams()
    run_price_refresh_scheduler = _lazy_import_price_refresh()
    run_market_symbol_offline_scheduler = _lazy_import_market_symbol_offline()
    
    # 创建所有后台任务
    market_tickers_task = asyncio.create_task(run_market_ticker_stream(run_seconds=duration))
    
    # 注意：data_agent_manager 已迁移到独立的 data_manager.py 服务
    # 不再在此处启动，请使用 docker-compose.yml 中的 data-manager 服务
    
    # 注意：kline_cleanup服务默认不包含在all任务中
    # K线相关任务应由data目录下的data_manager.py服务管理
    
    price_refresh_task = asyncio.create_task(run_price_refresh_scheduler())
    market_symbol_offline_task = asyncio.create_task(run_market_symbol_offline_scheduler())
    
    logger.info("[AsyncAgent] Started all services: market_tickers, price_refresh, market_symbol_offline")
    logger.info("[AsyncAgent] Note: kline_cleanup service is not included by default - K-line tasks should be managed by data_manager.py in data directory")
    logger.info("[AsyncAgent] Note: data_agent_manager is now a separate service (data-manager), see docker-compose.yml")
    logger.info("[AsyncAgent] Note: leaderboard_cleanup service removed - leaderboard data now queried directly from 24_market_tickers table")
    
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
    "kline_sync": _run_kline_sync,  # K线同步服务（已废弃，保留以兼容旧代码）
    "kline_cleanup": _run_kline_cleanup,  # K线清理服务（默认不启用，仅在data目录相关任务中使用）
    "kline_services": _run_kline_services,  # K线相关服务（清理，默认不启用，仅在data目录相关任务中使用）
    "price_refresh": _run_price_refresh,  # 价格刷新服务
    "market_symbol_offline": _run_market_symbol_offline,  # 市场Symbol下线服务
    "all": _run_all_services,  # 运行所有任务服务（不包括K线清理服务）
    # 注意：
    # - kline_sync已废弃，已被data_agent_manager取代
    # - kline_cleanup和kline_services默认不包含在all任务中，应由data目录下的data_manager.py服务管理
    # - data_agent_manager已迁移到独立的data_manager.py服务，请使用docker-compose.yml中的data-manager服务
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
        - kline_sync: K线同步服务（已废弃）
        - kline_cleanup: K线清理服务（默认不启用，仅在data目录相关任务中使用）
        - kline_services: K线相关服务（清理，默认不启用，仅在data目录相关任务中使用）
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
