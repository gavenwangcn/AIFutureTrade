"""Executable integration checks for common.database.database_market_tickers.

Run with:

    python tests/test_database_clickhouse.py

The script reuses the main MySQL configuration from common.config and will
exit with non-zero status if any check fails.
"""
from __future__ import annotations

import logging
import sys
import uuid
from typing import Callable, List, Tuple
from datetime import datetime, timezone

from common.database.database_market_tickers import MarketTickersDatabase, MARKET_TICKER_TABLE


def _require_mysql() -> MarketTickersDatabase:
    try:
        return MarketTickersDatabase()
    except Exception as exc:
        raise RuntimeError(f"MySQL unavailable: {exc}") from exc


def _check_table_exists(db: MarketTickersDatabase) -> None:
    db.ensure_market_ticker_table()
    result = db.query(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s",
        (MARKET_TICKER_TABLE,)
    )
    assert result[0][0] >= 1, "market ticker table missing"


def _check_insert_rows(db: MarketTickersDatabase) -> None:
    table_name = f"test_insert_rows_{uuid.uuid4().hex[:8]}"
    db.command(f"DROP TABLE IF EXISTS `{table_name}`")
    db.command(f"CREATE TABLE `{table_name}` (`a` BIGINT UNSIGNED, `b` VARCHAR(255)) ENGINE=InnoDB")
    try:
        db.insert_rows(table_name, [[1, "x"], [2, "y"]], ["a", "b"])
        result = db.query(f"SELECT COUNT(*) FROM `{table_name}`")
        assert result[0][0] == 2, "insert_rows did not write expected data"
    finally:
        db.command(f"DROP TABLE IF EXISTS `{table_name}`")





def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    try:
        db = _require_mysql()
    except RuntimeError as exc:
        logging.error(exc)
        return 1

    checks: List[Tuple[str, Callable[[MarketTickersDatabase], None]]] = [
        ("ensure_table_exists", _check_table_exists),
        ("insert_rows", _check_insert_rows),
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
        logging.info("All MySQL checks passed")
        return 0

    logging.error("One or more MySQL checks failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
