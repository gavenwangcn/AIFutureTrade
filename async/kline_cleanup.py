"""
K线数据定时清理服务

定时清除ClickHouse中超过保留期的K线数据。
"""
import asyncio
import logging
import sys
from datetime import datetime

import common.config as app_config
from common.database_clickhouse import ClickHouseDatabase

logger = logging.getLogger(__name__)


async def cleanup_old_klines(days: int = 2) -> None:
    """清理超过指定天数的K线数据"""
    try:
        db = ClickHouseDatabase(auto_init_tables=False)
        result = db.cleanup_old_klines(days=days)
        logger.info("[KlineCleanup] Cleanup initiated for klines older than %s days", days)
    except Exception as e:
        logger.error("[KlineCleanup] Cleanup failed: %s", e, exc_info=True)


def parse_cron_interval(cron_expr: str) -> int:
    """
    简单解析cron表达式，返回执行间隔（秒）
    支持格式: "0 */2 * * *" (每2小时) 或 "*/30 * * * *" (每30分钟)
    默认返回2小时（7200秒）
    """
    try:
        parts = cron_expr.strip().split()
        if len(parts) >= 2:
            minute_part = parts[0]
            hour_part = parts[1]
            
            # 解析小时部分: "*/2" -> 2小时
            if hour_part.startswith('*/'):
                hours = int(hour_part[2:])
                return hours * 3600
            # 解析分钟部分: "*/30" -> 30分钟
            elif minute_part.startswith('*/'):
                minutes = int(minute_part[2:])
                return minutes * 60
    except (ValueError, IndexError):
        pass
    
    # 默认2小时
    return 2 * 3600


async def run_cleanup_scheduler() -> None:
    """运行定时清理调度器（简化版，使用固定间隔）"""
    cron_expr = getattr(app_config, 'KLINE_CLEANUP_CRON', '0 */2 * * *')
    retention_days = getattr(app_config, 'KLINE_CLEANUP_RETENTION_DAYS', 2)
    
    # 解析执行间隔
    interval_seconds = parse_cron_interval(cron_expr)
    
    logger.info(
        "[KlineCleanup] Scheduler started with interval: %s seconds (%s), retention: %s days",
        interval_seconds,
        cron_expr,
        retention_days
    )
    
    try:
        # 立即执行一次
        await cleanup_old_klines(retention_days)
        
        # 定时执行
        while True:
            await asyncio.sleep(interval_seconds)
            await cleanup_old_klines(retention_days)
    except KeyboardInterrupt:
        logger.info("[KlineCleanup] Scheduler stopped by user")


if __name__ == "__main__":
    logging.basicConfig(
        level=getattr(logging, app_config.LOG_LEVEL, logging.INFO),
        format=app_config.LOG_FORMAT,
        datefmt=app_config.LOG_DATE_FORMAT,
    )
    
    try:
        asyncio.run(run_cleanup_scheduler())
    except KeyboardInterrupt:
        logger.info("[KlineCleanup] Interrupted by user")
        sys.exit(0)

