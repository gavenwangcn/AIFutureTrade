"""
异步刷新实时价格服务

此服务异步调用binance_futures模块中的get_klines方法获取最近两天的日K线数据，
并刷新24_market_tickers表中的open_price字段。

刷新逻辑：
1. 每分钟最多刷新1000个symbol（可配置）
2. 从24_market_tickers表获取update_price_date为空或不为当天的symbol（去重）
3. 分批调用接口刷新价格
4. open_price使用昨天的日K线收盘价，并更新update_price_date为当天时间
5. 每小时执行一次（可配置，使用cron表达式）
"""
import asyncio
import logging
import sys
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import config as app_config
from binance_futures import BinanceFuturesClient
from database_clickhouse import ClickHouseDatabase

logger = logging.getLogger(__name__)


def parse_cron_interval(cron_expr: str) -> int:
    """
    简单解析cron表达式，返回执行间隔（秒）
    支持格式: "0 */1 * * *" (每小时) 或 "*/30 * * * *" (每30分钟)
    默认返回1小时（3600秒）
    """
    try:
        parts = cron_expr.strip().split()
        if len(parts) >= 2:
            minute_part = parts[0]
            hour_part = parts[1]
            
            # 解析小时部分: "*/1" -> 1小时
            if hour_part.startswith('*/'):
                hours = int(hour_part[2:])
                return hours * 3600
            # 解析分钟部分: "*/30" -> 30分钟
            elif minute_part.startswith('*/'):
                minutes = int(minute_part[2:])
                return minutes * 60
    except (ValueError, IndexError):
        pass
    
    # 默认1小时
    return 3600


async def refresh_price_for_symbol(
    binance_client: BinanceFuturesClient,
    db: ClickHouseDatabase,
    symbol: str,
    target_date: datetime
) -> bool:
    """
    刷新单个symbol的open_price
    
    Args:
        binance_client: 币安期货客户端
        db: ClickHouse数据库实例
        symbol: 交易对符号
        target_date: 目标日期（用于计算昨天）
        
    Returns:
        是否刷新成功
    """
    try:
        # 获取最近两天的日K线数据（limit=2）
        # interval='1d' 表示日K线
        # 使用asyncio.to_thread避免阻塞事件循环
        klines = await asyncio.to_thread(
            binance_client.get_klines,
            symbol=symbol,
            interval='1d',
            limit=2
        )
        
        if not klines or len(klines) < 2:
            logger.warning(
                "[PriceRefresh] Symbol %s: Insufficient kline data (got %s, need 2)",
                symbol, len(klines) if klines else 0
            )
            return False
        
        # K线数据格式: [open_time, open, high, low, close, volume]
        # 币安API返回的K线数据按时间升序排列（从旧到新）
        # 我们需要昨天的收盘价作为今天的open_price
        # klines[0] 是昨天的，klines[1] 是今天的（最新的）
        yesterday_kline = klines[0]  # 昨天的K线（较早的）
        
        if len(yesterday_kline) < 5:
            logger.warning("[PriceRefresh] Symbol %s: Invalid kline data format", symbol)
            return False
        
        # 昨天的收盘价（索引4是close）
        yesterday_close_price = float(yesterday_kline[4])
        
        if yesterday_close_price <= 0:
            logger.warning("[PriceRefresh] Symbol %s: Invalid close price: %s", symbol, yesterday_close_price)
            return False
        
        # 更新open_price和update_price_date
        # update_price_date设置为当天的开始时间（00:00:00）
        today_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 使用asyncio.to_thread避免阻塞事件循环
        success = await asyncio.to_thread(
            db.update_open_price,
            symbol=symbol,
            open_price=yesterday_close_price,
            update_date=today_start
        )
        
        if success:
            logger.debug(
                "[PriceRefresh] Symbol %s: Updated open_price to %s (yesterday close)",
                symbol, yesterday_close_price
            )
        else:
            logger.warning("[PriceRefresh] Symbol %s: Failed to update open_price", symbol)
        
        return success
        
    except Exception as e:
        logger.error(
            "[PriceRefresh] Symbol %s: Error refreshing price: %s",
            symbol, e, exc_info=True
        )
        return False


async def refresh_prices_batch(
    binance_client: BinanceFuturesClient,
    db: ClickHouseDatabase,
    symbols: List[str],
    target_date: datetime,
    max_per_minute: int = 1000
) -> dict:
    """
    分批刷新价格
    
    Args:
        binance_client: 币安期货客户端
        db: ClickHouse数据库实例
        symbols: 需要刷新的symbol列表
        target_date: 目标日期
        max_per_minute: 每分钟最多刷新的symbol数量（默认1000）
        
    Returns:
        刷新结果统计
    """
    if not symbols:
        logger.info("[PriceRefresh] No symbols to refresh")
        return {"total": 0, "success": 0, "failed": 0}
    
    total = len(symbols)
    success_count = 0
    failed_count = 0
    
    logger.info(
        "[PriceRefresh] Starting batch refresh: %s symbols, max %s per minute",
        total, max_per_minute
    )
    
    # 分批处理，每批最多max_per_minute个
    batch_size = max_per_minute
    batches = [symbols[i:i + batch_size] for i in range(0, total, batch_size)]
    
    for batch_idx, batch in enumerate(batches, 1):
        logger.info(
            "[PriceRefresh] Processing batch %s/%s: %s symbols",
            batch_idx, len(batches), len(batch)
        )
        
        # 并发刷新当前批次的所有symbol
        tasks = [
            refresh_price_for_symbol(binance_client, db, symbol, target_date)
            for symbol in batch
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 统计结果
        for symbol, result in zip(batch, results):
            if isinstance(result, Exception):
                logger.error(
                    "[PriceRefresh] Symbol %s: Exception: %s",
                    symbol, result
                )
                failed_count += 1
            elif result:
                success_count += 1
            else:
                failed_count += 1
        
        # 如果不是最后一批，等待1分钟再处理下一批
        if batch_idx < len(batches):
            logger.info(
                "[PriceRefresh] Batch %s completed. Waiting 60 seconds before next batch...",
                batch_idx
            )
            await asyncio.sleep(60)
    
    logger.info(
        "[PriceRefresh] Batch refresh completed: %s total, %s success, %s failed",
        total, success_count, failed_count
    )
    
    return {
        "total": total,
        "success": success_count,
        "failed": failed_count
    }


async def refresh_all_prices() -> None:
    """刷新所有需要更新价格的symbol"""
    try:
        # 初始化数据库和币安客户端
        db = ClickHouseDatabase(auto_init_tables=False)
        
        binance_client = BinanceFuturesClient(
            api_key=app_config.BINANCE_API_KEY,
            api_secret=app_config.BINANCE_API_SECRET,
            quote_asset=getattr(app_config, 'FUTURES_QUOTE_ASSET', 'USDT')
        )
        
        # 获取需要刷新的symbol列表
        # 使用asyncio.to_thread避免阻塞事件循环
        symbols = await asyncio.to_thread(db.get_symbols_needing_price_refresh)
        
        if not symbols:
            logger.info("[PriceRefresh] No symbols need price refresh")
            return
        
        logger.info("[PriceRefresh] Found %s symbols needing price refresh", len(symbols))
        
        # 获取配置
        max_per_minute = getattr(
            app_config,
            'PRICE_REFRESH_MAX_PER_MINUTE',
            1000
        )
        
        # 当前日期（用于计算昨天）
        target_date = datetime.now(timezone.utc)
        
        # 执行批量刷新
        result = await refresh_prices_batch(
            binance_client=binance_client,
            db=db,
            symbols=symbols,
            target_date=target_date,
            max_per_minute=max_per_minute
        )
        
        logger.info(
            "[PriceRefresh] Refresh completed: %s total, %s success, %s failed",
            result["total"], result["success"], result["failed"]
        )
        
    except Exception as e:
        logger.error("[PriceRefresh] Error refreshing prices: %s", e, exc_info=True)


async def run_price_refresh_scheduler() -> None:
    """运行价格刷新调度器"""
    cron_expr = getattr(
        app_config,
        'PRICE_REFRESH_CRON',
        '0 */1 * * *'  # 默认每小时执行一次
    )
    max_per_minute = getattr(
        app_config,
        'PRICE_REFRESH_MAX_PER_MINUTE',
        1000
    )
    
    # 解析执行间隔
    interval_seconds = parse_cron_interval(cron_expr)
    
    logger.info(
        "[PriceRefresh] Scheduler started with interval: %s seconds (%s), max_per_minute: %s",
        interval_seconds,
        cron_expr,
        max_per_minute
    )
    
    try:
        # 立即执行一次
        await refresh_all_prices()
        
        # 定时执行
        while True:
            await asyncio.sleep(interval_seconds)
            await refresh_all_prices()
    except KeyboardInterrupt:
        logger.info("[PriceRefresh] Scheduler stopped by user")
    except Exception as e:
        logger.error("[PriceRefresh] Scheduler error: %s", e, exc_info=True)


if __name__ == "__main__":
    logging.basicConfig(
        level=getattr(logging, app_config.LOG_LEVEL, logging.INFO),
        format=app_config.LOG_FORMAT,
        datefmt=app_config.LOG_DATE_FORMAT,
    )
    
    try:
        asyncio.run(run_price_refresh_scheduler())
    except KeyboardInterrupt:
        logger.info("[PriceRefresh] Interrupted by user")
        sys.exit(0)

