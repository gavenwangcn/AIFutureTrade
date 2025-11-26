"""Executable integration checks for database_clickhouse.

Run with:

    python tests/test_database_clickhouse.py

The script reuses the main ClickHouse configuration from config.py and will
exit with non-zero status if any check fails.
"""
from __future__ import annotations

import logging
import sys
import uuid
from typing import Callable, List, Tuple

from database_clickhouse import ClickHouseDatabase, MARKET_TICKER_TABLE


def _require_clickhouse() -> ClickHouseDatabase:
    try:
        return ClickHouseDatabase(auto_init_tables=False)
    except Exception as exc:
        raise RuntimeError(f"ClickHouse unavailable: {exc}") from exc


def _check_table_exists(db: ClickHouseDatabase) -> None:
    db.ensure_market_ticker_table()
    result = db._client.query(
        "SELECT count() FROM system.tables WHERE name=%(name)s",
        parameters={"name": MARKET_TICKER_TABLE},
    )
    assert result.result_rows[0][0] >= 1, "market ticker table missing"


def _check_insert_rows(db: ClickHouseDatabase) -> None:
    table_name = f"test_insert_rows_{uuid.uuid4().hex[:8]}"
    db.command(f"DROP TABLE IF EXISTS {table_name}")
    db.command(f"CREATE TABLE {table_name} (a UInt64, b String) ENGINE = Memory")
    try:
        db.insert_rows(table_name, [[1, "x"], [2, "y"]], ["a", "b"])
        result = db._client.query(f"SELECT count() FROM {table_name}")
        assert result.result_rows[0][0] == 2, "insert_rows did not write expected data"
    finally:
        db.command(f"DROP TABLE IF EXISTS {table_name}")


def _check_insert_market_tickers(db: ClickHouseDatabase) -> None:
    db.ensure_market_ticker_table()
    symbol = f"TEST_{uuid.uuid4().hex[:8].upper()}"
    row = {
        "event_time": 1764142935194,
        "symbol": symbol,
        "price_change": 0.1,
        "price_change_percent": 0.2,
        "average_price": 0.3,
        "last_price": 0.4,
        "last_trade_volume": 0.5,
        "open_price": 0.6,
        "high_price": 0.7,
        "low_price": 0.8,
        "base_volume": 0.9,
        "quote_volume": 1.0,
        "stats_open_time": 1764056520000,
        "stats_close_time": 1764142935064,
        "first_trade_id": 4,
        "last_trade_id": 5,
        "trade_count": 6,
    }
    db.insert_market_tickers([row])
    result = db._client.query(
        f"""
        SELECT symbol,
               side,
               change_percent_text,
               toUnixTimestamp(event_time) as event_ts,
               toUnixTimestamp(stats_open_time) as open_ts,
               toUnixTimestamp(stats_close_time) as close_ts
        FROM {MARKET_TICKER_TABLE}
        WHERE symbol=%(symbol)s
        ORDER BY event_time DESC
        LIMIT 1
        """,
        parameters={"symbol": symbol},
    )
    assert result.result_rows, "insert_market_tickers failed"
    stored_symbol, side, pct_text, event_ts, open_ts, close_ts = result.result_rows[0]
    assert stored_symbol == symbol, "Symbol mismatch"
    assert side in {"gainer", "loser"}, "Side not derived"
    assert pct_text.endswith("%"), "change_percent_text not formatted"
    assert event_ts > 0 and open_ts > 0 and close_ts > 0, "timestamps not stored"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    try:
        db = _require_clickhouse()
    except RuntimeError as exc:
        logging.error(exc)
        return 1

    checks: List[Tuple[str, Callable[[ClickHouseDatabase], None]]] = [
        ("ensure_table_exists", _check_table_exists),
        ("insert_rows", _check_insert_rows),
        ("insert_market_tickers", _check_insert_market_tickers),
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
        logging.info("All ClickHouse checks passed")
        return 0

    logging.error("One or more ClickHouse checks failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
