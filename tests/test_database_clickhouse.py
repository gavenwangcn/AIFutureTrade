"""Integration tests for database_clickhouse using a real ClickHouse instance."""
from __future__ import annotations

import uuid

import pytest

from database_clickhouse import ClickHouseDatabase, MARKET_TICKER_TABLE


def _require_clickhouse() -> ClickHouseDatabase:
    try:
        return ClickHouseDatabase(auto_init_tables=False)
    except Exception as exc:  # pragma: no cover - integration guard
        pytest.skip(f"ClickHouse unavailable: {exc}")


@pytest.fixture(scope="module")
def real_db() -> ClickHouseDatabase:
    db = _require_clickhouse()
    yield db


def test_ensure_table_exists(real_db: ClickHouseDatabase) -> None:
    real_db.ensure_market_ticker_table()
    result = real_db._client.query(
        "SELECT count() FROM system.tables WHERE name=%(name)s",
        parameters={"name": MARKET_TICKER_TABLE},
    )
    assert result.result_rows[0][0] >= 1


def test_insert_rows_into_temp_table(real_db: ClickHouseDatabase) -> None:
    table_name = f"test_insert_rows_{uuid.uuid4().hex[:8]}"
    real_db.command(f"DROP TABLE IF EXISTS {table_name}")
    real_db.command(
        f"CREATE TABLE {table_name} (a UInt64, b String) ENGINE = Memory"
    )
    try:
        real_db.insert_rows(table_name, [[1, "x"], [2, "y"]], ["a", "b"])
        result = real_db._client.query(
            f"SELECT count() FROM {table_name}"
        )
        assert result.result_rows[0][0] == 2
    finally:
        real_db.command(f"DROP TABLE IF EXISTS {table_name}")


def test_insert_market_tickers_real_table(real_db: ClickHouseDatabase) -> None:
    real_db.ensure_market_ticker_table()
    symbol = f"TEST_{uuid.uuid4().hex[:8].upper()}"
    row = {
        "event_time": 1,
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
        "stats_open_time": 2,
        "stats_close_time": 3,
        "first_trade_id": 4,
        "last_trade_id": 5,
        "trade_count": 6,
    }
    real_db.insert_market_tickers([row])
    result = real_db._client.query(
        f"SELECT symbol, price_change FROM {MARKET_TICKER_TABLE} WHERE symbol=%(symbol)s LIMIT 1",
        parameters={"symbol": symbol},
    )
    assert result.result_rows, "expected inserted row"
    assert result.result_rows[0][0] == symbol
