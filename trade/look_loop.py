"""
盯盘轮询：每次拉取 execution_status=RUNNING 的 market_look 行并执行 LookEngine。
"""

import logging
import time
from datetime import datetime, timezone, timedelta

import trade.common.config as app_config
from trade.common.database.database_market_look import MarketLookDatabase
from trade.look_engine import LookEngine

logger = logging.getLogger(__name__)


def market_look_loop(auto_run: bool, look_engine: LookEngine, db):
    """阻塞循环，直至 auto_run=False 或进程退出。"""
    market_look_db = MarketLookDatabase(pool=db._pool if hasattr(db, "_pool") else None)
    interval = int(getattr(app_config, "MARKET_LOOK_POLL_INTERVAL_SECONDS", 60))
    interval = max(5, min(86400, interval))

    logger.info("market_look loop started, poll interval=%ss", interval)

    while auto_run:
        try:
            rows = market_look_db.list_running()
            n = len(rows)
            if n:
                logger.info("LOOK CYCLE: %s, running tasks=%s", _now_cn(), n)
            for row in rows:
                try:
                    look_engine.execute_look_row(row)
                except Exception as e:
                    logger.error("execute_look_row failed id=%s: %s", row.get("id"), e, exc_info=True)
            time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("market_look loop interrupted")
            break
        except Exception as e:
            logger.critical("market_look loop error: %s", e, exc_info=True)
            time.sleep(60)

    logger.info("market_look loop stopped")


def _now_cn() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
