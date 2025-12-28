"""
价格刷新服务模块 - 异步刷新24_market_tickers表的开盘价格

本模块提供异步价格刷新服务，用于定期更新24_market_tickers表中的open_price字段。
通过获取币安期货的日K线数据，使用昨天的收盘价作为今天的开盘价。

主要功能：
1. 单个symbol刷新：获取日K线数据并更新open_price
2. 批量刷新：分批处理多个symbol，控制刷新频率
3. 定时调度：根据cron表达式定时执行刷新任务

刷新逻辑：
1. 从24_market_tickers表查询需要刷新的symbol（update_price_date为空或超过1小时未更新）
2. 获取最近2天的日K线数据（limit=2）
3. 使用昨天的收盘价（klines[0]['close']）作为今天的open_price
4. 更新update_price_date为当前UTC+8时间
5. 每分钟最多刷新1000个symbol（可配置，PRICE_REFRESH_MAX_PER_MINUTE）
6. 根据cron表达式定时执行（默认每5分钟，PRICE_REFRESH_CRON）

K线数据格式说明：
- 旧格式：[open_time, open, high, low, close, volume, ...]（列表格式）
- 新格式：{
    "open_time": int,           # 开盘时间（毫秒时间戳）
    "open": str,                # 开盘价
    "high": str,                # 最高价
    "low": str,                 # 最低价
    "close": str,               # 收盘价
    "volume": str,              # 成交量
    ...
  }（字典格式）

使用场景：
- 后台服务：通过async_agent启动定时刷新任务
- 手动执行：可以直接调用refresh_all_prices()执行一次刷新

注意：
- 使用asyncio.to_thread避免阻塞事件循环
- 支持并发刷新多个symbol，提高效率
- 自动处理网络错误和异常情况
"""
import asyncio
import logging
import sys
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import common.config as app_config
from common.binance_futures import BinanceFuturesClient
from common.database.database_market_tickers import MarketTickersDatabase

logger = logging.getLogger(__name__)


# ============ 工具函数 ============

def parse_cron_interval(cron_expr: str) -> int:
    """
    解析cron表达式，返回执行间隔（秒）
    
    支持格式：
    - "0 */1 * * *" (每小时) -> 3600秒
    - "*/30 * * * *" (每30分钟) -> 1800秒
    - "*/5 * * * *" (每5分钟) -> 300秒
    
    Args:
        cron_expr: cron表达式字符串
    
    Returns:
        int: 执行间隔（秒），解析失败时默认返回3600秒（1小时）
    
    Note:
        - 只支持简单的cron表达式格式
        - 优先解析小时部分，其次解析分钟部分
        - 如果解析失败，返回默认值3600秒
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


# ============ 单个Symbol刷新方法 ============

async def refresh_price_for_symbol(
    binance_client: BinanceFuturesClient,
    db: MarketTickersDatabase,
    symbol: str
) -> bool:
    """
    刷新单个symbol的开盘价格
    
    获取最近2天的日K线数据，使用昨天的收盘价作为今天的open_price，
    并更新24_market_tickers表中的open_price和update_price_date字段。
    
    Args:
        binance_client: 币安期货客户端实例
        db: MySQL数据库实例
        symbol: 交易对符号（如'BTCUSDT'）
    
    Returns:
        bool: 刷新是否成功
    
    Note:
        - 使用asyncio.to_thread避免阻塞事件循环
        - 兼容旧列表格式和新字典格式的K线数据
        - 如果K线数据不足或价格无效，返回False
        - update_price_date使用当前UTC+8时间
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
        
        # 兼容旧的列表格式和新的字典格式
        try:
            if isinstance(yesterday_kline, dict):
                # 新的字典格式
                if 'close' not in yesterday_kline:
                    logger.warning("[PriceRefresh] Symbol %s: Invalid kline data format", symbol)
                    return False
                yesterday_close_price = float(yesterday_kline['close'])
            else:
                # 旧的列表格式
                if len(yesterday_kline) < 5:
                    logger.warning("[PriceRefresh] Symbol %s: Invalid kline data format", symbol)
                    return False
                # 昨天的收盘价（索引4是close）
                yesterday_close_price = float(yesterday_kline[4])
        except (ValueError, TypeError, KeyError) as e:
            logger.warning("[PriceRefresh] Symbol %s: Failed to parse close price: %s", symbol, e)
            return False
        
        if yesterday_close_price <= 0:
            logger.warning("[PriceRefresh] Symbol %s: Invalid close price: %s", symbol, yesterday_close_price)
            return False
        
        # 更新open_price和update_price_date
        # 注意：update_open_price方法内部会使用当前UTC+8时间作为update_price_date
        # 传入的update_date参数会被忽略，但为了兼容性仍然传递
        utc8 = timezone(timedelta(hours=8))
        refresh_time = datetime.now(utc8)  # 使用UTC+8时间
        
        # 使用asyncio.to_thread避免阻塞事件循环
        success = await asyncio.to_thread(
            db.update_open_price,
            symbol=symbol,
            open_price=yesterday_close_price,
            update_date=refresh_time  # 此参数会被方法内部忽略，方法会使用当前本地时间
        )
        
        if success:
            logger.info(
                "[PriceRefresh] ✅ Symbol %s: 成功更新open_price = %s (昨天收盘价), update_price_date = %s (当前UTC+8时间)",
                symbol, yesterday_close_price, refresh_time.strftime('%Y-%m-%d %H:%M:%S')
            )
        else:
            logger.warning("[PriceRefresh] ❌ Symbol %s: 更新open_price失败", symbol)
        
        return success
        
    except Exception as e:
        logger.error(
            "[PriceRefresh] Symbol %s: Error refreshing price: %s",
            symbol, e, exc_info=True
        )
        return False


# ============ 批量刷新方法 ============

async def refresh_prices_batch(
    binance_client: BinanceFuturesClient,
    db: MarketTickersDatabase,
    symbols: List[str],
    max_per_minute: int = 1000
) -> dict:
    """
    分批刷新多个symbol的开盘价格
    
    将symbol列表分成多个批次，每批最多max_per_minute个，
    批次内并发刷新，批次间等待60秒以避免API限流。
    
    Args:
        binance_client: 币安期货客户端实例
        db: MySQL数据库实例
        symbols: 需要刷新的symbol列表
        max_per_minute: 每分钟最多刷新的symbol数量（默认1000）
    
    Returns:
        Dict: 刷新结果统计，包含：
            - total: 总数量
            - success: 成功数量
            - failed: 失败数量
    
    Note:
        - 批次内使用asyncio.gather并发执行，提高效率
        - 批次间等待60秒，避免API限流
        - 记录详细的批次统计和累计统计信息
    """
    if not symbols:
        logger.info("[PriceRefresh] [批量刷新] 没有需要刷新的symbol")
        return {"total": 0, "success": 0, "failed": 0}
    
    total = len(symbols)
    success_count = 0
    failed_count = 0
    
    logger.info(
        "[PriceRefresh] [批量刷新] 开始批量刷新: 总计 %s 个symbol, 每分钟最多处理 %s 个",
        total, max_per_minute
    )
    
    # 分批处理，每批最多max_per_minute个
    batch_size = max_per_minute
    batches = [symbols[i:i + batch_size] for i in range(0, total, batch_size)]
    
    logger.info(
        "[PriceRefresh] [批量刷新] 将分为 %s 个批次处理，每批最多 %s 个symbol",
        len(batches), batch_size
    )
    
    for batch_idx, batch in enumerate(batches, 1):
        batch_start_time = datetime.now(timezone.utc)
        logger.info(
            "[PriceRefresh] [批量刷新] [批次 %s/%s] 开始处理，包含 %s 个symbol",
            batch_idx, len(batches), len(batch)
        )
        logger.info(
            "[PriceRefresh] [批量刷新] [批次 %s/%s] Symbol列表（前5个）: %s",
            batch_idx, len(batches), batch[:5]
        )
        
        # 并发刷新当前批次的所有symbol
        tasks = [
            refresh_price_for_symbol(binance_client, db, symbol)
            for symbol in batch
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 统计结果
        batch_success = 0
        batch_failed = 0
        for symbol, result in zip(batch, results):
            if isinstance(result, Exception):
                logger.error(
                    "[PriceRefresh] [批量刷新] [批次 %s/%s] Symbol %s: 异常 - %s",
                    batch_idx, len(batches), symbol, result
                )
                failed_count += 1
                batch_failed += 1
            elif result:
                success_count += 1
                batch_success += 1
            else:
                failed_count += 1
                batch_failed += 1
        
        batch_duration = (datetime.now(timezone.utc) - batch_start_time).total_seconds()
        logger.info(
            "[PriceRefresh] [批量刷新] [批次 %s/%s] 处理完成，耗时: %.2f秒",
            batch_idx, len(batches), batch_duration
        )
        logger.info(
            "[PriceRefresh] [批量刷新] [批次 %s/%s] 批次统计: 成功 %s, 失败 %s, 总计 %s",
            batch_idx, len(batches), batch_success, batch_failed, len(batch)
        )
        logger.info(
            "[PriceRefresh] [批量刷新] [批次 %s/%s] 累计统计: 成功 %s, 失败 %s, 总计 %s",
            batch_idx, len(batches), success_count, failed_count, success_count + failed_count
        )
        
        # 如果不是最后一批，等待1分钟再处理下一批
        if batch_idx < len(batches):
            logger.info(
                "[PriceRefresh] [批量刷新] [批次 %s/%s] 等待60秒后处理下一批次...",
                batch_idx, len(batches)
            )
            await asyncio.sleep(60)
    
    logger.info(
        "[PriceRefresh] [批量刷新] ✅ 批量刷新完成: 总计 %s, 成功 %s (%.2f%%), 失败 %s (%.2f%%)",
        total,
        success_count,
        (success_count / total * 100) if total > 0 else 0,
        failed_count,
        (failed_count / total * 100) if total > 0 else 0
    )
    
    return {
        "total": total,
        "success": success_count,
        "failed": failed_count
    }


# ============ 主刷新方法 ============

async def refresh_all_prices() -> None:
    """
    刷新所有需要更新价格的symbol（主入口方法）
    
    流程：
    1. 初始化数据库和币安客户端
    2. 查询需要刷新的symbol列表（从24_market_tickers表）
    3. 调用批量刷新方法处理所有symbol
    4. 输出详细的执行统计信息
    
    Note:
        - 如果没有需要刷新的symbol，直接返回
        - 记录详细的执行步骤和耗时信息
        - 异常会被捕获并记录，不会中断执行
    """
    refresh_start_time = datetime.now(timezone(timedelta(hours=8)))
    logger.info("=" * 80)
    logger.info("[PriceRefresh] ========== 开始执行异步价格刷新任务 ==========")
    logger.info("[PriceRefresh] 执行时间: %s", refresh_start_time.strftime('%Y-%m-%d %H:%M:%S UTC'))
    logger.info("=" * 80)
    
    try:
        # 初始化数据库和币安客户端
        logger.info("[PriceRefresh] [步骤1] 初始化数据库和币安客户端...")
        logger.info("[PriceRefresh] [步骤1] 开始创建MarketTickersDatabase实例")
        db = MarketTickersDatabase()
        logger.info("[PriceRefresh] [步骤1] 成功创建MarketTickersDatabase实例")
        
        logger.info("[PriceRefresh] [步骤1] 开始创建BinanceFuturesClient实例")
        binance_client = BinanceFuturesClient(
            api_key=app_config.BINANCE_API_KEY,
            api_secret=app_config.BINANCE_API_SECRET,
            quote_asset=getattr(app_config, 'FUTURES_QUOTE_ASSET', 'USDT')
        )
        logger.info("[PriceRefresh] [步骤1] 成功创建BinanceFuturesClient实例")
        logger.info("[PriceRefresh] [步骤1] ✅ 数据库和币安客户端初始化完成")
        
        # 获取需要刷新的symbol列表
        # 使用asyncio.to_thread避免阻塞事件循环
        logger.info("[PriceRefresh] [步骤2] 查询需要刷新价格的symbol列表...")
        query_start_time = datetime.now(timezone(timedelta(hours=8)))
        logger.info("[PriceRefresh] [步骤2] 开始调用db.get_symbols_needing_price_refresh()")
        symbols = await asyncio.to_thread(db.get_symbols_needing_price_refresh)
        logger.info("[PriceRefresh] [步骤2] 成功获取db.get_symbols_needing_price_refresh()返回值")
        query_duration = (datetime.now(timezone(timedelta(hours=8))) - query_start_time).total_seconds()
        
        logger.info(
            "[PriceRefresh] [步骤2] 查询完成，耗时: %.2f秒，返回了 %s 个symbol",
            query_duration, len(symbols) if symbols is not None else "None"
        )
        
        if not symbols:
            logger.info("[PriceRefresh] [步骤2] ⚠️  没有需要刷新价格的symbol")
            logger.info("=" * 80)
            logger.info("[PriceRefresh] ========== 价格刷新任务完成（无数据需要刷新） ==========")
            logger.info("=" * 80)
            return
        
        logger.info("[PriceRefresh] [步骤2] ✅ 找到 %s 个需要刷新的symbol", len(symbols))
        logger.info("[PriceRefresh] [步骤2] 需要刷新的symbol列表（前10个）: %s", symbols[:10])
        
        # 获取配置
        max_per_minute = getattr(
            app_config,
            'PRICE_REFRESH_MAX_PER_MINUTE',
            1000
        )
        logger.info("[PriceRefresh] [步骤3] 配置参数: max_per_minute=%s", max_per_minute)
        
        # 执行批量刷新
        logger.info("[PriceRefresh] [步骤3] 开始执行批量价格刷新...")
        batch_start_time = datetime.now(timezone(timedelta(hours=8)))
        result = await refresh_prices_batch(
            binance_client=binance_client,
            db=db,
            symbols=symbols,
            max_per_minute=max_per_minute
        )
        batch_duration = (datetime.now(timezone(timedelta(hours=8))) - batch_start_time).total_seconds()
        
        # 计算总耗时
        total_duration = (datetime.now(timezone(timedelta(hours=8))) - refresh_start_time).total_seconds()
        
        # 输出详细统计信息
        logger.info("=" * 80)
        logger.info("[PriceRefresh] ========== 异步价格刷新任务执行完成 ==========")
        logger.info("[PriceRefresh] 执行时间: %s", refresh_start_time.strftime('%Y-%m-%d %H:%M:%S UTC'))
        logger.info("[PriceRefresh] 完成时间: %s", datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S UTC'))
        logger.info("[PriceRefresh] 总耗时: %.2f秒 (%.2f分钟)", total_duration, total_duration / 60)
        logger.info("[PriceRefresh] 批量刷新耗时: %.2f秒 (%.2f分钟)", batch_duration, batch_duration / 60)
        logger.info("[PriceRefresh] 统计信息:")
        logger.info("[PriceRefresh]   - 总计: %s 个symbol", result["total"])
        logger.info("[PriceRefresh]   - 成功: %s 个symbol (%.2f%%)", 
                   result["success"], 
                   (result["success"] / result["total"] * 100) if result["total"] > 0 else 0)
        logger.info("[PriceRefresh]   - 失败: %s 个symbol (%.2f%%)", 
                   result["failed"], 
                   (result["failed"] / result["total"] * 100) if result["total"] > 0 else 0)
        logger.info("=" * 80)
        
    except Exception as e:
        total_duration = (datetime.now(timezone(timedelta(hours=8))) - refresh_start_time).total_seconds()
        logger.error("=" * 80)
        logger.error("[PriceRefresh] ========== 异步价格刷新任务执行失败 ==========")
        logger.error("[PriceRefresh] 执行时间: %s", refresh_start_time.strftime('%Y-%m-%d %H:%M:%S UTC'))
        logger.error("[PriceRefresh] 失败时间: %s", datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S UTC'))
        logger.error("[PriceRefresh] 总耗时: %.2f秒", total_duration)
        logger.error("[PriceRefresh] 错误信息: %s", e, exc_info=True)
        logger.error("=" * 80)


# ============ 调度器方法 ============

async def run_price_refresh_scheduler() -> None:
    """
    运行价格刷新调度器（主调度入口）
    
    根据配置的cron表达式定时执行价格刷新任务。
    启动时立即执行一次，然后按配置的间隔循环执行。
    
    配置参数：
    - PRICE_REFRESH_CRON: cron表达式（默认'*/5 * * * *'，每5分钟）
    - PRICE_REFRESH_MAX_PER_MINUTE: 每分钟最多刷新数量（默认1000）
    
    Note:
        - 启动时立即执行一次刷新
        - 然后根据cron表达式解析的间隔循环执行
        - 支持KeyboardInterrupt优雅停止
        - 记录每次执行的详细信息
    """
    cron_expr = getattr(
        app_config,
        'PRICE_REFRESH_CRON',
        '*/5 * * * *'  # 默认每5分钟执行一次
    )
    max_per_minute = getattr(
        app_config,
        'PRICE_REFRESH_MAX_PER_MINUTE',
        1000
    )
    
    # 解析执行间隔
    interval_seconds = parse_cron_interval(cron_expr)
    
    logger.info("=" * 80)
    logger.info("[PriceRefresh] ========== 价格刷新调度器启动 ==========")
    logger.info("[PriceRefresh] 启动时间: %s", datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S UTC'))
    logger.info("[PriceRefresh] Cron表达式: %s", cron_expr)
    logger.info("[PriceRefresh] 执行间隔: %s 秒 (%.2f 分钟)", interval_seconds, interval_seconds / 60)
    logger.info("[PriceRefresh] 每分钟最多刷新: %s 个symbol", max_per_minute)
    logger.info("=" * 80)
    
    execution_count = 0
    
    try:
        # 立即执行一次
        execution_count += 1
        logger.info(
            "[PriceRefresh] [调度器] ========== 第 %s 次执行（启动时立即执行） ==========",
            execution_count
        )
        await refresh_all_prices()
        logger.info(
            "[PriceRefresh] [调度器] ✅ 第 %s 次执行完成",
            execution_count
        )
        
        # 定时执行
        while True:
            next_execution_time = datetime.now(timezone(timedelta(hours=8))) + timedelta(seconds=interval_seconds)
            logger.info(
                "[PriceRefresh] [调度器] 等待 %s 秒后执行下一次刷新 (下次执行时间: %s)",
                interval_seconds,
                next_execution_time.strftime('%Y-%m-%d %H:%M:%S UTC')
            )
            await asyncio.sleep(interval_seconds)
            
            execution_count += 1
            logger.info(
                "[PriceRefresh] [调度器] ========== 第 %s 次执行（定时执行） ==========",
                execution_count
            )
            await refresh_all_prices()
            logger.info(
                "[PriceRefresh] [调度器] ✅ 第 %s 次执行完成",
                execution_count
            )
    except KeyboardInterrupt:
        logger.info("=" * 80)
        logger.info("[PriceRefresh] [调度器] ========== 价格刷新调度器被用户停止 ==========")
        logger.info("[PriceRefresh] [调度器] 总执行次数: %s", execution_count)
        logger.info("[PriceRefresh] [调度器] 停止时间: %s", datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S UTC'))
        logger.info("=" * 80)
    except Exception as e:
        logger.error("=" * 80)
        logger.error("[PriceRefresh] [调度器] ========== 价格刷新调度器发生错误 ==========")
        logger.error("[PriceRefresh] [调度器] 总执行次数: %s", execution_count)
        logger.error("[PriceRefresh] [调度器] 错误时间: %s", datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S UTC'))
        logger.error("[PriceRefresh] [调度器] 错误信息: %s", e, exc_info=True)
        logger.error("=" * 80)


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


