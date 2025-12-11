"""Executable integration checks for MySQL leaderboard query functionality.

注意：此测试文件已更新，因为涨跌榜数据现在直接从 24_market_tickers 表查询，
不再使用 futures_leaderboard 表和异步同步任务。

Run with:

    python tests/test_leaderboard_sync.py

The script reuses the main MySQL configuration from common.config and will
exit with non-zero status if any check fails.
"""
from __future__ import annotations

import logging
import sys
from typing import Callable, List, Tuple
from datetime import datetime, timezone

from common.database_mysql import MySQLDatabase


def _require_mysql() -> MySQLDatabase:
    try:
        return MySQLDatabase(auto_init_tables=True)
    except Exception as exc:
        raise RuntimeError(f"MySQL unavailable: {exc}") from exc


def _check_leaderboard_query_functionality(db: MySQLDatabase) -> None:
    """检查涨跌榜查询功能是否正常工作"""
    # 确保 market_ticker_table 存在
    db.ensure_market_ticker_table()
    
    # 插入测试数据
    current_time = datetime.now(timezone.utc)
    test_tickers = [
        {
            "event_time": current_time,
            "symbol": "TEST1USDT",
            "price_change": 10.0,
            "price_change_percent": 5.0,  # Gainer
            "side": "gainer",
            "average_price": 200.0,
            "last_price": 210.0,
            "last_trade_volume": 1.0,
            "open_price": 200.0,
            "high_price": 215.0,
            "low_price": 195.0,
            "base_volume": 100.0,
            "quote_volume": 20000.0,
            "stats_open_time": current_time,
            "stats_close_time": current_time,
            "first_trade_id": 1,
            "last_trade_id": 10,
            "trade_count": 10,
        },
        {
            "event_time": current_time,
            "symbol": "TEST2USDT",
            "price_change": -20.0,
            "price_change_percent": -8.0,  # Loser
            "side": "loser",
            "average_price": 250.0,
            "last_price": 230.0,
            "last_trade_volume": 1.5,
            "open_price": 250.0,
            "high_price": 255.0,
            "low_price": 225.0,
            "base_volume": 150.0,
            "quote_volume": 35000.0,
            "stats_open_time": current_time,
            "stats_close_time": current_time,
            "first_trade_id": 11,
            "last_trade_id": 20,
            "trade_count": 10,
        }
    ]
    
    db.upsert_market_tickers(test_tickers)
    
    # 测试查询涨幅榜
    gainers = db.get_gainers_from_tickers(limit=10)
    assert len(gainers) > 0, "应该能查询到涨幅榜数据"
    assert any(item.get('symbol') == 'TEST1USDT' for item in gainers), "涨幅榜应该包含TEST1USDT"
    
    # 测试查询跌幅榜
    losers = db.get_losers_from_tickers(limit=10)
    assert len(losers) > 0, "应该能查询到跌幅榜数据"
    assert any(item.get('symbol') == 'TEST2USDT' for item in losers), "跌幅榜应该包含TEST2USDT"
    


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    try:
        db = _require_mysql()
    except RuntimeError as exc:
        logging.error(exc)
        return 1

    checks: List[Tuple[str, Callable[[MySQLDatabase], None]]] = [
        ("leaderboard_query_functionality", _check_leaderboard_query_functionality),
    ]

    all_passed = True
    for name, func in checks:
        try:
            logging.info("Running %s...", name)
            func(db)
            logging.info("%s passed", name)
        except AssertionError as err:
            all_passed = False
            logging.error("%s failed: %s", name, err)
        except Exception as err:
            all_passed = False
            logging.exception("%s raised unexpected error", name)

    if all_passed:
        logging.info("All leaderboard query checks passed")
        return 0

    logging.error("One or more leaderboard query checks failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
