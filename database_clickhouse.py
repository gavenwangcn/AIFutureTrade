"""ClickHouse database utilities for market data storage."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import clickhouse_connect
import config as app_config

MARKET_TICKER_TABLE = "24_market_tickers"

logger = logging.getLogger(__name__)


class ClickHouseDatabase:
    """Encapsulates ClickHouse connectivity and CRUD helpers."""

    def __init__(self, *, auto_init_tables: bool = True) -> None:
        self._client = clickhouse_connect.get_client(
            host=app_config.CLICKHOUSE_HOST,
            port=app_config.CLICKHOUSE_PORT,
            username=app_config.CLICKHOUSE_USER,
            password=app_config.CLICKHOUSE_PASSWORD,
            database=app_config.CLICKHOUSE_DATABASE,
            secure=app_config.CLICKHOUSE_SECURE,
        )
        self.market_ticker_table = MARKET_TICKER_TABLE
        if auto_init_tables:
            self.ensure_market_ticker_table()

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------
    def command(self, sql: str) -> None:
        """Execute a raw SQL command."""
        self._client.command(sql)

    def insert_rows(
        self,
        table: str,
        rows: Iterable[Iterable[Any]],
        column_names: List[str],
    ) -> None:
        payload = list(rows)
        if not payload:
            return
        self._client.insert(table, payload, column_names=column_names)
        logger.debug("[ClickHouse] Inserted %s rows into %s", len(payload), table)

    # ------------------------------------------------------------------
    # Market ticker helpers
    # ------------------------------------------------------------------
    def ensure_market_ticker_table(self) -> None:
        """Create the 24h market ticker table if it does not exist."""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {self.market_ticker_table} (
            event_time DateTime,
            symbol String,
            price_change Float64,
            price_change_percent Float64,
            side String,
            change_percent_text String,
            average_price Float64,
            last_price Float64,
            last_trade_volume Float64,
            open_price Float64,
            high_price Float64,
            low_price Float64,
            base_volume Float64,
            quote_volume Float64,
            stats_open_time DateTime,
            stats_close_time DateTime,
            first_trade_id UInt64,
            last_trade_id UInt64,
            trade_count UInt64,
            ingestion_time DateTime DEFAULT now()
        )
        ENGINE = MergeTree
        ORDER BY (symbol, stats_close_time, event_time)
        """
        self.command(ddl)
        logger.info("[ClickHouse] Ensured table %s exists", self.market_ticker_table)

    def insert_market_tickers(self, rows: Iterable[Dict[str, Any]]) -> None:
        column_names = [
            "event_time",
            "symbol",
            "price_change",
            "price_change_percent",
            "side",
            "change_percent_text",
            "average_price",
            "last_price",
            "last_trade_volume",
            "open_price",
            "high_price",
            "low_price",
            "base_volume",
            "quote_volume",
            "stats_open_time",
            "stats_close_time",
            "first_trade_id",
            "last_trade_id",
            "trade_count",
        ]

        prepared_rows: List[List[Any]] = []
        for row in rows:
            normalized = dict(row)
            normalized["event_time"] = _to_datetime(normalized.get("event_time"))
            normalized["stats_open_time"] = _to_datetime(normalized.get("stats_open_time"))
            normalized["stats_close_time"] = _to_datetime(normalized.get("stats_close_time"))
            percent = normalized.get("price_change_percent")
            normalized.setdefault("side", _derive_side(percent))
            normalized.setdefault("change_percent_text", _format_percent_text(percent))
            prepared_rows.append([normalized.get(name) for name in column_names])

        self.insert_rows(self.market_ticker_table, prepared_rows, column_names)


def _to_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)

    seconds = numeric / 1000.0
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


def _derive_side(percent: Any) -> str:
    try:
        value = float(percent)
    except (TypeError, ValueError):
        value = 0.0
    return "loser" if value < 0 else "gainer"


def _format_percent_text(percent: Any) -> str:
    try:
        value = float(percent)
    except (TypeError, ValueError):
        value = 0.0
    return f"{value:.2f}%"
