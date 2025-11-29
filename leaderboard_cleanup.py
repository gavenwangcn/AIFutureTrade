"""
ClickHouse 涨跌榜数据定时清理服务

定期清除 ClickHouse futures_leaderboard 表中超过保留期的历史批次数据，
防止由于频繁插入最新涨跌榜导致数据量无限增长。
"""
import asyncio
import logging
import sys

import config as app_config
from database_clickhouse import ClickHouseDatabase

logger = logging.getLogger(__name__)


async def cleanup_old_leaderboard(minutes: int = 10) -> None:
    """清理超过指定分钟数的涨跌榜历史数据."""
    try:
        db = ClickHouseDatabase(auto_init_tables=False)
        db.cleanup_old_leaderboard(minutes=minutes)
        logger.info(
            "[LeaderboardCleanup] Cleanup initiated for leaderboard rows older than %s minutes",
            minutes,
        )
    except Exception as e:
        logger.error("[LeaderboardCleanup] Cleanup failed: %s", e, exc_info=True)


async def run_cleanup_scheduler() -> None:
    """运行定时清理调度器，固定间隔执行."""
    interval_minutes = getattr(app_config, "CLICKHOUSE_LEADERBOARD_CLEANUP_INTERVAL_MINUTES", 10)
    retention_minutes = getattr(app_config, "CLICKHOUSE_LEADERBOARD_RETENTION_MINUTES", 10)

    interval_minutes = max(1, int(interval_minutes))
    retention_minutes = max(1, int(retention_minutes))

    interval_seconds = interval_minutes * 60

    logger.info(
        "[LeaderboardCleanup] Scheduler started: interval=%s minutes (%s seconds), retention=%s minutes",
        interval_minutes,
        interval_seconds,
        retention_minutes,
    )

    try:
        # 立即执行一次
        await cleanup_old_leaderboard(retention_minutes)

        # 按配置的间隔循环执行
        while True:
            await asyncio.sleep(interval_seconds)
            await cleanup_old_leaderboard(retention_minutes)
    except KeyboardInterrupt:
        logger.info("[LeaderboardCleanup] Scheduler stopped by user")


if __name__ == "__main__":
    logging.basicConfig(
        level=getattr(logging, app_config.LOG_LEVEL, logging.INFO),
        format=app_config.LOG_FORMAT,
        datefmt=app_config.LOG_DATE_FORMAT,
    )

    try:
        asyncio.run(run_cleanup_scheduler())
    except KeyboardInterrupt:
        logger.info("[LeaderboardCleanup] Interrupted by user")
        sys.exit(0)


