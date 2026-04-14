"""
盯盘服务入口：仅从 market_look 表读取 RUNNING 任务并轮询执行。

用法:
    MODEL_ID=1 python -m trade.start.start_market_look

MODEL_ID 用于初始化 LookEngine（策略执行上下文；盯盘行情在 look_engine 内单品种构建，不拉起 TradingEngine）。
"""

import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import trade.common.config as app_config
from trade.common.database.database_basic import Database
from trade.common.database.database_init import init_all_database_tables
from trade.common.database.database_models import ModelsDatabase
from trade.look_engine import LookEngine
from trade.look_loop import market_look_loop
from trade.market.market_data import MarketDataFetcher


def get_log_level():
    log_level_str = getattr(app_config, "LOG_LEVEL", "INFO").upper()
    return getattr(logging, log_level_str, logging.INFO)


class UTC8Formatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=timezone(timedelta(hours=8)))
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%d %H:%M:%S")


formatter = UTC8Formatter(
    getattr(app_config, "LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
    datefmt=getattr(app_config, "LOG_DATE_FORMAT", "%Y-%m-%d %H:%M:%S"),
)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
logging.basicConfig(level=get_log_level(), handlers=[handler])
logger = logging.getLogger(__name__)


def get_model_id_from_env() -> str:
    model_id_str = os.getenv("MODEL_ID")
    if not model_id_str or not str(model_id_str).strip():
        logger.error("MODEL_ID environment variable is not set")
        sys.exit(1)
    return str(model_id_str).strip()


def main():
    model_id_raw = get_model_id_from_env()
    logger.info("Starting market_look service, MODEL_ID=%s", model_id_raw)

    db = Database()
    try:
        init_all_database_tables(db.command)
    except Exception as e:
        logger.error("init tables failed: %s", e)
        sys.exit(1)

    models_db = ModelsDatabase(pool=db._pool if hasattr(db, "_pool") else None)
    model_id_int = models_db._uuid_to_int(model_id_raw) if isinstance(model_id_raw, str) else model_id_raw
    logger.info("Model UUID=%s int_id=%s", model_id_raw, model_id_int)

    market_fetcher = MarketDataFetcher(db)
    look_engine = LookEngine(db=db, market_fetcher=market_fetcher, model_id=model_id_int)

    try:
        market_look_loop(True, look_engine, db)
    except KeyboardInterrupt:
        logger.info("shutdown")


if __name__ == "__main__":
    main()
