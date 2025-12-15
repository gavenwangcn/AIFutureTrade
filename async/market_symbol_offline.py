"""
异步市场Symbol下线服务

此服务定时读取24_market_tickers表中超过指定分钟数（默认15分钟）的数据，并批量删除。

主要功能：
1. 统计需要删除的记录数量
2. 批量删除过期的ticker数据
3. 根据cron表达式定时执行清理任务

数据清理逻辑：
- 使用ingestion_time字段作为判断标准
- 删除ingestion_time早于（当前时间 - 保留分钟数）的所有记录
- 默认保留30分钟数据（可通过MARKET_SYMBOL_RETENTION_MINUTES配置）

使用场景：
- 后台服务：通过async_agent启动定时清理任务
- 手动执行：可以直接调用delete_old_symbols()执行一次清理

注意：
- 删除操作不可逆，请谨慎配置保留天数
- 使用asyncio.to_thread避免阻塞事件循环
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import common.config as app_config
from common.database_mysql import MySQLDatabase

logger = logging.getLogger(__name__)


# ============ 工具函数 ============

def parse_cron_interval(cron_expr: str) -> int:
    """
    解析cron表达式，返回执行间隔（秒）
    
    支持格式：
    - "0 */8 * * *" (每8小时) -> 28800秒
    - "*/30 * * * *" (每30分钟) -> 1800秒
    - "*/5 * * * *" (每5分钟) -> 300秒
    
    Args:
        cron_expr: cron表达式字符串
    
    Returns:
        int: 执行间隔（秒），解析失败时默认返回28800秒（8小时）
    
    Note:
        - 只支持简单的cron表达式格式
        - 优先解析小时部分，其次解析分钟部分
        - 如果解析失败，返回默认值28800秒
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


# ============ 数据清理方法 ============

async def delete_old_symbols() -> None:
    """
    删除超过指定天数的symbol数据（主入口方法）
    
    流程：
    1. 初始化数据库连接
    2. 计算截止日期（当前时间 - 保留天数）
    3. 统计需要删除的记录数量
    4. 执行批量删除操作
    5. 输出详细的执行统计信息
    
    Note:
        - 如果没有需要删除的记录，直接返回
        - 记录详细的执行步骤和耗时信息
        - 异常会被捕获并记录，不会中断执行
        - 所有时间使用UTC+8（北京时区）
    """
    # 使用UTC+8（北京时区）
    utc8 = timezone(timedelta(hours=8))
    delete_start_time = datetime.now(utc8)
    logger.info("=" * 80)
    logger.info("[MarketSymbolOffline] ========== 开始执行异步市场Symbol下线任务 ==========")
    logger.info("[MarketSymbolOffline] 执行时间: %s", delete_start_time.strftime('%Y-%m-%d %H:%M:%S UTC+8'))
    logger.info("=" * 80)
    
    try:
        # 获取配置
        retention_minutes = getattr(
            app_config,
            'MARKET_SYMBOL_RETENTION_MINUTES',
            30  # 默认保留30分钟
        )
        
        # 初始化数据库
        logger.info("[MarketSymbolOffline] [步骤1] 初始化数据库...")
        db = MySQLDatabase(auto_init_tables=False)
        logger.info("[MarketSymbolOffline] [步骤1] ✅ 数据库初始化完成")
        
        # 计算截止日期
        cutoff_date = datetime.now(utc8) - timedelta(minutes=retention_minutes)
        logger.info(
            "[MarketSymbolOffline] [步骤2] 计算截止日期: 当前时间 - %s 分钟 = %s",
            retention_minutes,
            cutoff_date.strftime('%Y-%m-%d %H:%M:%S UTC+8')
        )
        
        # 查询要删除的记录数量
        logger.info("[MarketSymbolOffline] [步骤3] 查询要删除的记录数量...")
        count_start_time = datetime.now(utc8)
        
        # 使用asyncio.to_thread避免阻塞事件循环
        record_count = await asyncio.to_thread(
            db.count_old_tickers,
            cutoff_date
        )
        
        count_duration = (datetime.now(utc8) - count_start_time).total_seconds()
        
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
        logger.info("[MarketSymbolOffline] [步骤4] 执行删除操作...")
        delete_start_time_inner = datetime.now(utc8)
        
        # 使用asyncio.to_thread避免阻塞事件循环
        deleted_count = await asyncio.to_thread(
            db.delete_old_tickers,
            cutoff_date
        )
        
        delete_duration = (datetime.now(utc8) - delete_start_time_inner).total_seconds()
        logger.info(
            "[MarketSymbolOffline] [步骤4] ✅ 删除完成，耗时: %.2f秒，成功删除 %s 条记录",
            delete_duration, deleted_count
        )
        
        # 计算总耗时
        total_duration = (datetime.now(utc8) - delete_start_time).total_seconds()
        
        # 输出详细统计信息
        logger.info("=" * 80)
        logger.info("[MarketSymbolOffline] ========== 异步市场Symbol下线任务执行完成 ==========")
        logger.info("[MarketSymbolOffline] 执行时间: %s", delete_start_time.strftime('%Y-%m-%d %H:%M:%S UTC+8'))
        logger.info("[MarketSymbolOffline] 完成时间: %s", datetime.now(utc8).strftime('%Y-%m-%d %H:%M:%S UTC+8'))
        logger.info("[MarketSymbolOffline] 总耗时: %.2f秒 (%.2f分钟)", total_duration, total_duration / 60)
        logger.info("[MarketSymbolOffline] 统计信息:")
        logger.info("[MarketSymbolOffline]   - 保留分钟: %s 分钟", retention_minutes)
        logger.info("[MarketSymbolOffline]   - 截止日期: %s", cutoff_date.strftime('%Y-%m-%d %H:%M:%S UTC+8'))
        logger.info("[MarketSymbolOffline]   - 删除记录数: %s 条", deleted_count)
        logger.info("=" * 80)
        
    except Exception as e:
        total_duration = (datetime.now(utc8) - delete_start_time).total_seconds()
        logger.error("=" * 80)
        logger.error("[MarketSymbolOffline] ========== 异步市场Symbol下线任务执行失败 ==========")
        logger.error("[MarketSymbolOffline] 执行时间: %s", delete_start_time.strftime('%Y-%m-%d %H:%M:%S UTC+8'))
        logger.error("[MarketSymbolOffline] 失败时间: %s", datetime.now(utc8).strftime('%Y-%m-%d %H:%M:%S UTC+8'))
        logger.error("[MarketSymbolOffline] 总耗时: %.2f秒", total_duration)
        logger.error("[MarketSymbolOffline] 错误信息: %s", e, exc_info=True)
        logger.error("=" * 80)


# ============ 调度器方法 ============

async def run_market_symbol_offline_scheduler() -> None:
    """
    运行市场Symbol下线调度器（主调度入口）
    
    根据配置的cron表达式定时执行数据清理任务。
    启动时立即执行一次，然后按配置的间隔循环执行。
    
    配置参数：
- MARKET_SYMBOL_OFFLINE_CRON: cron表达式（默认'*/20 * * * *'，每20分钟）
- MARKET_SYMBOL_RETENTION_MINUTES: 数据保留分钟数（默认15分钟）
    
    Note:
        - 启动时立即执行一次清理
        - 然后根据cron表达式解析的间隔循环执行
        - 支持KeyboardInterrupt优雅停止
        - 记录每次执行的详细信息
        - 所有时间使用UTC+8（北京时区）
    """
    # 使用UTC+8（北京时区）
    utc8 = timezone(timedelta(hours=8))
    
    cron_expr = getattr(
        app_config,
        'MARKET_SYMBOL_OFFLINE_CRON',
        '*/30 * * * *'  # 默认每30分钟执行一次
    )
    retention_minutes = getattr(
        app_config,
        'MARKET_SYMBOL_RETENTION_MINUTES',
        15  # 默认保留15分钟
    )
    
    # 解析执行间隔
    interval_seconds = parse_cron_interval(cron_expr)
    
    logger.info("=" * 80)
    logger.info("[MarketSymbolOffline] ========== 市场Symbol下线调度器启动 ==========")
    logger.info("[MarketSymbolOffline] 启动时间: %s", datetime.now(utc8).strftime('%Y-%m-%d %H:%M:%S UTC+8'))
    logger.info("[MarketSymbolOffline] Cron表达式: %s", cron_expr)
    logger.info("[MarketSymbolOffline] 执行间隔: %s 秒 (%.2f 分钟)", interval_seconds, interval_seconds / 60)
    logger.info("[MarketSymbolOffline] 数据保留分钟: %s 分钟", retention_minutes)
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
            next_execution_time = datetime.now(utc8) + timedelta(seconds=interval_seconds)
            logger.info(
                "[MarketSymbolOffline] [调度器] 等待 %s 秒后执行下一次删除 (下次执行时间: %s)",
                interval_seconds,
                next_execution_time.strftime('%Y-%m-%d %H:%M:%S UTC+8')
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
        logger.info("[MarketSymbolOffline] [调度器] 停止时间: %s", datetime.now(utc8).strftime('%Y-%m-%d %H:%M:%S UTC+8'))
        logger.info("=" * 80)
    except Exception as e:
        logger.error("=" * 80)
        logger.error("[MarketSymbolOffline] [调度器] ========== 市场Symbol下线调度器发生错误 ==========")
        logger.error("[MarketSymbolOffline] [调度器] 总执行次数: %s", execution_count)
        logger.error("[MarketSymbolOffline] [调度器] 错误时间: %s", datetime.now(utc8).strftime('%Y-%m-%d %H:%M:%S UTC+8'))
        logger.error("[MarketSymbolOffline] [调度器] 错误信息: %s", e, exc_info=True)
        logger.error("=" * 80)