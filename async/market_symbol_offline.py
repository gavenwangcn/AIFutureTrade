"""
异步市场Symbol下线服务

此服务定时读取24_market_tickers表中超过指定天数（默认2天）的数据，并批量删除。
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import common.config as app_config
from common.database_clickhouse import ClickHouseDatabase

logger = logging.getLogger(__name__)


def parse_cron_interval(cron_expr: str) -> int:
    """
    简单解析cron表达式，返回执行间隔（秒）
    支持格式: "0 */8 * * *" (每8小时) 或 "*/30 * * * *" (每30分钟)
    默认返回8小时（28800秒）
    """
    try:
        parts = cron_expr.strip().split()
        if len(parts) >= 2:
            minute_part = parts[0]
            hour_part = parts[1]
            
            # 解析小时部分: "*/8" -> 8小时
            if hour_part.startswith('*/'):
                hours = int(hour_part[2:])
                return hours * 3600
            # 解析分钟部分: "*/30" -> 30分钟
            elif minute_part.startswith('*/'):
                minutes = int(minute_part[2:])
                return minutes * 60
    except (ValueError, IndexError):
        pass
    
    # 默认8小时
    return 28800


async def delete_old_symbols() -> None:
    """
    删除超过指定天数的symbol数据
    """
    delete_start_time = datetime.now(timezone.utc)
    logger.info("=" * 80)
    logger.info("[MarketSymbolOffline] ========== 开始执行异步市场Symbol下线任务 ==========")
    logger.info("[MarketSymbolOffline] 执行时间: %s", delete_start_time.strftime('%Y-%m-%d %H:%M:%S UTC'))
    logger.info("=" * 80)
    
    try:
        # 获取配置
        retention_days = getattr(
            app_config,
            'MARKET_SYMBOL_RETENTION_DAYS',
            2  # 默认保留2天
        )
        
        # 初始化数据库
        logger.info("[MarketSymbolOffline] [步骤1] 初始化数据库...")
        db = ClickHouseDatabase(auto_init_tables=False)
        logger.info("[MarketSymbolOffline] [步骤1] ✅ 数据库初始化完成")
        
        # 计算截止日期
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
        logger.info(
            "[MarketSymbolOffline] [步骤2] 计算截止日期: 当前时间 - %s 天 = %s",
            retention_days,
            cutoff_date.strftime('%Y-%m-%d %H:%M:%S UTC')
        )
        
        # 查询要删除的记录数量
        count_query = f"""
        SELECT COUNT(*) FROM {db.market_ticker_table}
        WHERE ingestion_time < %(cutoff_date)s
        """
        
        logger.info("[MarketSymbolOffline] [步骤3] 查询要删除的记录数量...")
        count_start_time = datetime.now(timezone.utc)
        
        # 使用asyncio.to_thread避免阻塞事件循环
        result = await asyncio.to_thread(
            db.query,
            count_query,
            params={"cutoff_date": cutoff_date}
        )
        
        count_duration = (datetime.now(timezone.utc) - count_start_time).total_seconds()
        record_count = int(result[0][0]) if result else 0
        
        if record_count == 0:
            logger.info("[MarketSymbolOffline] [步骤3] ⚠️  没有需要删除的记录")
            logger.info("=" * 80)
            logger.info("[MarketSymbolOffline] ========== Symbol下线任务完成（无数据需要删除） ==========")
            logger.info("=" * 80)
            return
        
        logger.info(
            "[MarketSymbolOffline] [步骤3] ✅ 查询完成，耗时: %.2f秒，找到 %s 条需要删除的记录",
            count_duration, record_count
        )
        
        # 执行删除操作
        delete_query = f"""
        ALTER TABLE {db.market_ticker_table}
        DELETE WHERE ingestion_time < %(cutoff_date)s
        """
        
        logger.info("[MarketSymbolOffline] [步骤4] 执行删除操作...")
        delete_start_time = datetime.now(timezone.utc)
        
        # 使用asyncio.to_thread避免阻塞事件循环
        await asyncio.to_thread(
            db.command,
            delete_query,
            params={"cutoff_date": cutoff_date}
        )
        
        delete_duration = (datetime.now(timezone.utc) - delete_start_time).total_seconds()
        logger.info(
            "[MarketSymbolOffline] [步骤4] ✅ 删除完成，耗时: %.2f秒，成功删除 %s 条记录",
            delete_duration, record_count
        )
        
        # 计算总耗时
        total_duration = (datetime.now(timezone.utc) - delete_start_time).total_seconds()
        
        # 输出详细统计信息
        logger.info("=" * 80)
        logger.info("[MarketSymbolOffline] ========== 异步市场Symbol下线任务执行完成 ==========")
        logger.info("[MarketSymbolOffline] 执行时间: %s", delete_start_time.strftime('%Y-%m-%d %H:%M:%S UTC'))
        logger.info("[MarketSymbolOffline] 完成时间: %s", datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'))
        logger.info("[MarketSymbolOffline] 总耗时: %.2f秒 (%.2f分钟)", total_duration, total_duration / 60)
        logger.info("[MarketSymbolOffline] 统计信息:")
        logger.info("[MarketSymbolOffline]   - 保留天数: %s 天", retention_days)
        logger.info("[MarketSymbolOffline]   - 截止日期: %s", cutoff_date.strftime('%Y-%m-%d %H:%M:%S UTC'))
        logger.info("[MarketSymbolOffline]   - 删除记录数: %s 条", record_count)
        logger.info("=" * 80)
        
    except Exception as e:
        total_duration = (datetime.now(timezone.utc) - delete_start_time).total_seconds()
        logger.error("=" * 80)
        logger.error("[MarketSymbolOffline] ========== 异步市场Symbol下线任务执行失败 ==========")
        logger.error("[MarketSymbolOffline] 执行时间: %s", delete_start_time.strftime('%Y-%m-%d %H:%M:%S UTC'))
        logger.error("[MarketSymbolOffline] 失败时间: %s", datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'))
        logger.error("[MarketSymbolOffline] 总耗时: %.2f秒", total_duration)
        logger.error("[MarketSymbolOffline] 错误信息: %s", e, exc_info=True)
        logger.error("=" * 80)


async def run_market_symbol_offline_scheduler() -> None:
    """
    运行市场Symbol下线调度器
    """
    cron_expr = getattr(
        app_config,
        'MARKET_SYMBOL_OFFLINE_CRON',
        '0 */8 * * *'  # 默认每8小时执行一次
    )
    retention_days = getattr(
        app_config,
        'MARKET_SYMBOL_RETENTION_DAYS',
        2  # 默认保留2天
    )
    
    # 解析执行间隔
    interval_seconds = parse_cron_interval(cron_expr)
    
    logger.info("=" * 80)
    logger.info("[MarketSymbolOffline] ========== 市场Symbol下线调度器启动 ==========")
    logger.info("[MarketSymbolOffline] 启动时间: %s", datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'))
    logger.info("[MarketSymbolOffline] Cron表达式: %s", cron_expr)
    logger.info("[MarketSymbolOffline] 执行间隔: %s 秒 (%.2f 小时)", interval_seconds, interval_seconds / 3600)
    logger.info("[MarketSymbolOffline] 数据保留天数: %s 天", retention_days)
    logger.info("=" * 80)
    
    execution_count = 0
    
    try:
        # 立即执行一次
        execution_count += 1
        logger.info(
            "[MarketSymbolOffline] [调度器] ========== 第 %s 次执行（启动时立即执行） ==========",
            execution_count
        )
        await delete_old_symbols()
        logger.info(
            "[MarketSymbolOffline] [调度器] ✅ 第 %s 次执行完成",
            execution_count
        )
        
        # 定时执行
        while True:
            next_execution_time = datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)
            logger.info(
                "[MarketSymbolOffline] [调度器] 等待 %s 秒后执行下一次删除 (下次执行时间: %s)",
                interval_seconds,
                next_execution_time.strftime('%Y-%m-%d %H:%M:%S UTC')
            )
            await asyncio.sleep(interval_seconds)
            
            execution_count += 1
            logger.info(
                "[MarketSymbolOffline] [调度器] ========== 第 %s 次执行（定时执行） ==========",
                execution_count
            )
            await delete_old_symbols()
            logger.info(
                "[MarketSymbolOffline] [调度器] ✅ 第 %s 次执行完成",
                execution_count
            )
    except KeyboardInterrupt:
        logger.info("=" * 80)
        logger.info("[MarketSymbolOffline] [调度器] ========== 市场Symbol下线调度器被用户停止 ==========")
        logger.info("[MarketSymbolOffline] [调度器] 总执行次数: %s", execution_count)
        logger.info("[MarketSymbolOffline] [调度器] 停止时间: %s", datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'))
        logger.info("=" * 80)
    except Exception as e:
        logger.error("=" * 80)
        logger.error("[MarketSymbolOffline] [调度器] ========== 市场Symbol下线调度器发生错误 ==========")
        logger.error("[MarketSymbolOffline] [调度器] 总执行次数: %s", execution_count)
        logger.error("[MarketSymbolOffline] [调度器] 错误时间: %s", datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'))
        logger.error("[MarketSymbolOffline] [调度器] 错误信息: %s", e, exc_info=True)
        logger.error("=" * 80)