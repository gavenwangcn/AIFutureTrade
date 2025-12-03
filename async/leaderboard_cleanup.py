"""
ClickHouse 涨跌榜数据定时清理服务

定期清除 ClickHouse futures_leaderboard 表中超过保留期的历史批次数据，
防止由于频繁插入最新涨跌榜导致数据量无限增长。
"""
import asyncio
import logging
import sys
import time
from datetime import datetime, timezone

import common.config as app_config
from common.database_clickhouse import ClickHouseDatabase

logger = logging.getLogger(__name__)


async def cleanup_old_leaderboard(minutes: int = 10) -> dict:
    """清理超过指定分钟数的涨跌榜历史数据.
    
    Args:
        minutes: 保留时间窗口（分钟）
        
    Returns:
        包含清理统计信息的字典
    """
    cleanup_start_time = time.time()
    cleanup_time_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    
    logger.info(
        "[LeaderboardCleanup] 🚀 开始执行清理任务 | 时间: %s | 保留时间: %s 分钟",
        cleanup_time_str,
        minutes,
    )
    
    try:
        logger.debug("[LeaderboardCleanup] 🔌 正在初始化 ClickHouse 数据库连接...")
        db = ClickHouseDatabase(auto_init_tables=False)
        logger.debug("[LeaderboardCleanup] ✅ ClickHouse 数据库连接已建立")
        
        logger.debug("[LeaderboardCleanup] 📞 调用 cleanup_old_leaderboard 方法...")
        stats = db.cleanup_old_leaderboard(minutes=minutes)
        logger.debug("[LeaderboardCleanup] ✅ cleanup_old_leaderboard 方法执行完成")
        
        cleanup_end_time = time.time()
        total_execution_time = cleanup_end_time - cleanup_start_time
        
        # 检查是否有错误
        if stats.get('error'):
            logger.error(
                "[LeaderboardCleanup] ❌ 清理任务返回错误 | 错误信息: %s",
                stats.get('error'),
            )
            return stats
        
        # 记录详细的清理结果
        logger.info(
            "[LeaderboardCleanup] ✅ 清理任务完成 | 总耗时: %.3f 秒 | "
            "清理前: %s 条 | 待删除: %s 条 | 清理后: %s 条",
            total_execution_time,
            stats.get('total_before', 0),
            stats.get('to_delete_count', 0),
            stats.get('total_after', 0),
        )
        
        # 计算数据减少比例
        if stats.get('total_before', 0) > 0:
            reduction_percent = (stats.get('to_delete_count', 0) / stats.get('total_before', 1)) * 100
            logger.info(
                "[LeaderboardCleanup] 📊 数据减少比例: %.2f%% | 截止时间: %s",
                reduction_percent,
                stats.get('cutoff_time', 'N/A'),
            )
        else:
            logger.info("[LeaderboardCleanup] ℹ️ 清理前数据量为 0，无需清理")
        
        # 验证清理是否成功
        if stats.get('to_delete_count', 0) > 0:
            logger.info(
                "[LeaderboardCleanup] ✅ 清理操作已成功提交 | 待删除: %s 条数据（ClickHouse 异步执行中）",
                stats.get('to_delete_count', 0),
            )
        else:
            logger.info("[LeaderboardCleanup] ℹ️ 没有需要清理的数据")
        
        # 性能警告
        if total_execution_time > 30:
            logger.warning(
                "[LeaderboardCleanup] ⚠️ 清理任务执行时间较长: %.3f 秒，建议检查数据库性能",
                total_execution_time,
            )
        elif total_execution_time > 10:
            logger.info(
                "[LeaderboardCleanup] ⏱️ 清理任务执行时间: %.3f 秒（正常范围）",
                total_execution_time,
            )
        
        return stats
        
    except Exception as e:
        cleanup_end_time = time.time()
        total_execution_time = cleanup_end_time - cleanup_start_time
        logger.error(
            "[LeaderboardCleanup] ❌ 清理任务失败 | 耗时: %.3f 秒 | 错误: %s",
            total_execution_time,
            e,
            exc_info=True,
        )
        return {
            'total_before': 0,
            'total_after': 0,
            'to_delete_count': 0,
            'execution_time': total_execution_time,
            'error': str(e),
        }


async def run_cleanup_scheduler() -> None:
    """运行定时清理调度器，固定间隔执行."""
    interval_minutes = getattr(app_config, "CLICKHOUSE_LEADERBOARD_CLEANUP_INTERVAL_MINUTES", 10)
    retention_minutes = getattr(app_config, "CLICKHOUSE_LEADERBOARD_RETENTION_MINUTES", 10)

    interval_minutes = max(1, int(interval_minutes))
    retention_minutes = max(1, int(retention_minutes))

    interval_seconds = interval_minutes * 60

    scheduler_start_time = datetime.now(timezone.utc)
    scheduler_start_str = scheduler_start_time.strftime('%Y-%m-%d %H:%M:%S UTC')
    
    logger.info("=" * 80)
    logger.info("[LeaderboardCleanup] 🎯 清理调度器启动")
    logger.info("[LeaderboardCleanup] 📅 启动时间: %s", scheduler_start_str)
    logger.info("[LeaderboardCleanup] ⏰ 清理执行间隔: %s 分钟 (%s 秒)", interval_minutes, interval_seconds)
    logger.info("[LeaderboardCleanup] 📦 数据保留时间: %s 分钟", retention_minutes)
    logger.info("=" * 80)

    cycle_count = 0
    total_cleaned = 0
    
    try:
        # 立即执行一次
        logger.info("[LeaderboardCleanup] 🔄 执行首次清理任务...")
        cycle_count += 1
        stats = await cleanup_old_leaderboard(retention_minutes)
        if stats:
            total_cleaned += stats.get('to_delete_count', 0)
        
        logger.info(
            "[LeaderboardCleanup] 💤 等待 %s 分钟 (%s 秒) 后执行下一次清理...",
            interval_minutes,
            interval_seconds,
        )

        # 按配置的间隔循环执行
        while True:
            await asyncio.sleep(interval_seconds)
            cycle_count += 1
            next_run_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
            
            logger.info(
                "[LeaderboardCleanup] 🔄 [第 %s 次] 开始执行清理任务 | 时间: %s",
                cycle_count,
                next_run_time,
            )
            
            stats = await cleanup_old_leaderboard(retention_minutes)
            if stats:
                deleted_count = stats.get('to_delete_count', 0)
                total_cleaned += deleted_count
                if deleted_count > 0:
                    logger.info(
                        "[LeaderboardCleanup] ✅ [第 %s 次] 清理任务成功 | 本次清理: %s 条 | 累计清理: %s 条",
                        cycle_count,
                        deleted_count,
                        total_cleaned,
                    )
                else:
                    logger.debug(
                        "[LeaderboardCleanup] ℹ️ [第 %s 次] 清理任务完成 | 本次无需清理数据",
                        cycle_count,
                    )
            else:
                logger.warning(
                    "[LeaderboardCleanup] ⚠️ [第 %s 次] 清理任务返回空结果",
                    cycle_count,
                )
            
            # 每10次清理输出一次汇总统计
            if cycle_count % 10 == 0:
                uptime = (datetime.now(timezone.utc) - scheduler_start_time).total_seconds() / 3600
                logger.info(
                    "[LeaderboardCleanup] 📈 清理统计汇总 | "
                    "执行次数: %s | 累计清理: %s 条 | 运行时长: %.2f 小时",
                    cycle_count,
                    total_cleaned,
                    uptime,
                )
            
            logger.info(
                "[LeaderboardCleanup] 💤 等待 %s 分钟 (%s 秒) 后执行下一次清理...",
                interval_minutes,
                interval_seconds,
            )
            
    except KeyboardInterrupt:
        scheduler_end_time = datetime.now(timezone.utc)
        uptime = (scheduler_end_time - scheduler_start_time).total_seconds() / 3600
        logger.info("=" * 80)
        logger.info("[LeaderboardCleanup] 🛑 清理调度器已停止（用户中断）")
        logger.info("[LeaderboardCleanup] 📊 最终统计:")
        logger.info("[LeaderboardCleanup]   - 执行次数: %s", cycle_count)
        logger.info("[LeaderboardCleanup]   - 累计清理数据: %s 条", total_cleaned)
        logger.info("[LeaderboardCleanup]   - 运行时长: %.2f 小时", uptime)
        logger.info("=" * 80)
    except Exception as e:
        logger.error(
            "[LeaderboardCleanup] ❌ 清理调度器发生未预期的错误: %s",
            e,
            exc_info=True,
        )
        raise


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


