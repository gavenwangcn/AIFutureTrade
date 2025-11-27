"""ClickHouse database utilities for market data storage."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import clickhouse_connect
import config as app_config

MARKET_TICKER_TABLE = "24_market_tickers"
LEADERBOARD_TABLE = "futures_leaderboard"
MARKET_KLINES_TABLE = "market_klines"

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
        self.leaderboard_table = getattr(app_config, 'CLICKHOUSE_LEADERBOARD_TABLE', LEADERBOARD_TABLE)
        self.market_klines_table = getattr(app_config, 'CLICKHOUSE_MARKET_KLINES_TABLE', MARKET_KLINES_TABLE)
        if auto_init_tables:
            self.ensure_market_ticker_table()
            self.ensure_leaderboard_table()
            self.ensure_market_klines_table()

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
        
    def upsert_market_tickers(self, rows: Iterable[Dict[str, Any]]) -> None:
        """Update or insert market tickers. If symbol exists, update it, otherwise insert.
        
        Args:
            rows: Iterable of ticker dictionaries
        """
        if not rows:
            return
            
        # Filter rows to only include symbols ending with "USDT"
        usdt_rows = [row for row in rows if row.get("symbol", "").endswith("USDT")]
        if not usdt_rows:
            logger.debug("[ClickHouse] No USDT symbols to upsert")
            return
            
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
        symbols_to_upsert = []
        
        for row in usdt_rows:
            normalized = dict(row)
            normalized["event_time"] = _to_datetime(normalized.get("event_time"))
            normalized["stats_open_time"] = _to_datetime(normalized.get("stats_open_time"))
            normalized["stats_close_time"] = _to_datetime(normalized.get("stats_close_time"))
            percent = normalized.get("price_change_percent")
            normalized.setdefault("side", _derive_side(percent))
            normalized.setdefault("change_percent_text", _format_percent_text(percent))
            prepared_rows.append([normalized.get(name) for name in column_names])
            symbols_to_upsert.append(normalized.get("symbol"))
        
        if not prepared_rows:
            return
        
        # For ClickHouse, the most efficient way to upsert is to delete existing rows first, then insert new ones
        # This is more efficient than UPDATE for MergeTree tables
        if symbols_to_upsert:
            # Delete existing rows with the same symbols
            symbols_str = "', '" .join(symbols_to_upsert)
            delete_query = f"ALTER TABLE {self.market_ticker_table} DELETE WHERE symbol IN ('{symbols_str}')"
            try:
                self.command(delete_query)
                logger.debug("[ClickHouse] Deleted existing rows for symbols: %s", symbols_to_upsert)
            except Exception as e:
                logger.warning("[ClickHouse] Failed to delete existing rows: %s", e)
        
        # Insert new rows
        self.insert_rows(self.market_ticker_table, prepared_rows, column_names)
        logger.debug("[ClickHouse] Upserted %s rows into %s", len(prepared_rows), self.market_ticker_table)

    # ------------------------------------------------------------------
    # Leaderboard helpers
    # ------------------------------------------------------------------
    def ensure_leaderboard_table(self) -> None:
        """Create the futures leaderboard table if it does not exist."""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {self.leaderboard_table} (
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
            ingestion_time DateTime DEFAULT now(),
            rank UInt8
        )
        ENGINE = MergeTree
        ORDER BY (side, rank, symbol)
        """
        self.command(ddl)
        logger.info("[ClickHouse] Ensured table %s exists", self.leaderboard_table)

    def query_recent_tickers(
        self, 
        time_window_seconds: int = 5,
        side: Optional[str] = None,
        top_n: int = 10
    ) -> List[Dict[str, Any]]:
        """Query recent tickers from market_ticker_table.
        
        Args:
            time_window_seconds: Time window in seconds (query tickers with ingestion_time > now() - time_window_seconds)
            side: Filter by side ('gainer' or 'loser'), None for all
            top_n: Number of top items to return
            
        Returns:
            List of ticker dictionaries
        """
        from datetime import timedelta
        
        time_threshold = datetime.now(timezone.utc) - timedelta(seconds=time_window_seconds)
        time_threshold_str = time_threshold.strftime('%Y-%m-%d %H:%M:%S')
        
        # 构建查询SQL：去重，取每个symbol最新的ingestion_time
        if side:
            # 涨幅榜：按 price_change_percent 降序
            # 跌幅榜：按 abs(price_change_percent) 降序（取绝对值）
            if side == 'gainer':
                order_by = "price_change_percent DESC"
            else:  # loser
                order_by = "abs(price_change_percent) DESC"
            
            query = f"""
            SELECT 
                event_time,
                symbol,
                price_change,
                price_change_percent,
                side,
                change_percent_text,
                average_price,
                last_price,
                last_trade_volume,
                open_price,
                high_price,
                low_price,
                base_volume,
                quote_volume,
                stats_open_time,
                stats_close_time,
                first_trade_id,
                last_trade_id,
                trade_count,
                ingestion_time
            FROM (
                SELECT 
                    *,
                    ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY ingestion_time DESC) as rn
                FROM {self.market_ticker_table}
                WHERE ingestion_time > '{time_threshold_str}'
                AND side = '{side}'
            ) AS ranked
            WHERE rn = 1
            ORDER BY {order_by}
            LIMIT {top_n}
            """
        else:
            # 查询所有，不区分涨跌
            query = f"""
            SELECT 
                event_time,
                symbol,
                price_change,
                price_change_percent,
                side,
                change_percent_text,
                average_price,
                last_price,
                last_trade_volume,
                open_price,
                high_price,
                low_price,
                base_volume,
                quote_volume,
                stats_open_time,
                stats_close_time,
                first_trade_id,
                last_trade_id,
                trade_count,
                ingestion_time
            FROM (
                SELECT 
                    *,
                    ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY ingestion_time DESC) as rn
                FROM {self.market_ticker_table}
                WHERE ingestion_time > '{time_threshold_str}'
            ) AS ranked
            WHERE rn = 1
            LIMIT {top_n * 2}
            """
        
        result = self._client.query(query)
        
        # 转换为字典列表
        columns = [
            "event_time", "symbol", "price_change", "price_change_percent", "side",
            "change_percent_text", "average_price", "last_price", "last_trade_volume",
            "open_price", "high_price", "low_price", "base_volume", "quote_volume",
            "stats_open_time", "stats_close_time", "first_trade_id", "last_trade_id",
            "trade_count", "ingestion_time"
        ]
        
        rows = []
        for row in result.result_rows:
            row_dict = dict(zip(columns, row))
            rows.append(row_dict)
        
        return rows

    def sync_leaderboard(
        self,
        time_window_seconds: int = 5,
        top_n: int = 10
    ) -> None:
        """Sync leaderboard data from market_ticker_table to leaderboard_table.
        
        Args:
            time_window_seconds: Time window in seconds for querying recent tickers
            top_n: Number of top gainers and losers to keep
        """
        try:
            # 先删除所有现有数据（使用 TRUNCATE 或 DELETE）
            # ClickHouse 的 DELETE 需要启用 mutations，使用 TRUNCATE 更简单
            try:
                truncate_sql = f"TRUNCATE TABLE {self.leaderboard_table}"
                self.command(truncate_sql)
            except Exception:
                # 如果 TRUNCATE 不支持，使用 DELETE
                delete_sql = f"ALTER TABLE {self.leaderboard_table} DELETE WHERE 1=1"
                self.command(delete_sql)
            
            # 查询涨幅榜前N名
            gainers = self.query_recent_tickers(
                time_window_seconds=time_window_seconds,
                side='gainer',
                top_n=top_n
            )
            
            # 查询跌幅榜前N名
            losers = self.query_recent_tickers(
                time_window_seconds=time_window_seconds,
                side='loser',
                top_n=top_n
            )
            
            # 准备插入数据
            all_rows = []
            column_names = [
                "event_time", "symbol", "price_change", "price_change_percent", "side",
                "change_percent_text", "average_price", "last_price", "last_trade_volume",
                "open_price", "high_price", "low_price", "base_volume", "quote_volume",
                "stats_open_time", "stats_close_time", "first_trade_id", "last_trade_id",
                "trade_count", "ingestion_time", "rank"
            ]
            
            # 添加涨幅榜数据（带排名）
            for idx, row in enumerate(gainers, 1):
                row_data = [
                    _to_datetime(row.get("event_time")),
                    row.get("symbol", ""),
                    float(row.get("price_change", 0)),
                    float(row.get("price_change_percent", 0)),
                    row.get("side", "gainer"),
                    row.get("change_percent_text", ""),
                    float(row.get("average_price", 0)),
                    float(row.get("last_price", 0)),
                    float(row.get("last_trade_volume", 0)),
                    float(row.get("open_price", 0)),
                    float(row.get("high_price", 0)),
                    float(row.get("low_price", 0)),
                    float(row.get("base_volume", 0)),
                    float(row.get("quote_volume", 0)),
                    _to_datetime(row.get("stats_open_time")),
                    _to_datetime(row.get("stats_close_time")),
                    int(row.get("first_trade_id", 0)),
                    int(row.get("last_trade_id", 0)),
                    int(row.get("trade_count", 0)),
                    _to_datetime(row.get("ingestion_time")),
                    idx  # rank
                ]
                all_rows.append(row_data)
            
            # 添加跌幅榜数据（带排名）
            for idx, row in enumerate(losers, 1):
                row_data = [
                    _to_datetime(row.get("event_time")),
                    row.get("symbol", ""),
                    float(row.get("price_change", 0)),
                    float(row.get("price_change_percent", 0)),
                    row.get("side", "loser"),
                    row.get("change_percent_text", ""),
                    float(row.get("average_price", 0)),
                    float(row.get("last_price", 0)),
                    float(row.get("last_trade_volume", 0)),
                    float(row.get("open_price", 0)),
                    float(row.get("high_price", 0)),
                    float(row.get("low_price", 0)),
                    float(row.get("base_volume", 0)),
                    float(row.get("quote_volume", 0)),
                    _to_datetime(row.get("stats_open_time")),
                    _to_datetime(row.get("stats_close_time")),
                    int(row.get("first_trade_id", 0)),
                    int(row.get("last_trade_id", 0)),
                    int(row.get("trade_count", 0)),
                    _to_datetime(row.get("ingestion_time")),
                    idx  # rank
                ]
                all_rows.append(row_data)
            
            # 插入新数据
            if all_rows:
                self.insert_rows(self.leaderboard_table, all_rows, column_names)
                logger.info(
                    "[ClickHouse] Synced leaderboard: %d gainers, %d losers",
                    len(gainers), len(losers)
                )
            else:
                logger.warning("[ClickHouse] No leaderboard data to sync")
                
        except Exception as exc:
            logger.error("[ClickHouse] Failed to sync leaderboard: %s", exc, exc_info=True)

    def get_leaderboard(self, limit: int = 10) -> Dict[str, List[Dict]]:
        """Get leaderboard data from futures_leaderboard table.
        
        Args:
            limit: Number of top items to return for each side
            
        Returns:
            Dictionary with 'gainers' and 'losers' lists
        """
        try:
            # 查询涨幅榜
            gainers_query = f"""
            SELECT 
                symbol,
                last_price,
                price_change_percent,
                side,
                change_percent_text,
                quote_volume,
                rank
            FROM {self.leaderboard_table}
            WHERE side = 'gainer'
            ORDER BY rank ASC
            LIMIT {limit}
            """
            
            # 查询跌幅榜
            losers_query = f"""
            SELECT 
                symbol,
                last_price,
                price_change_percent,
                side,
                change_percent_text,
                quote_volume,
                rank
            FROM {self.leaderboard_table}
            WHERE side = 'loser'
            ORDER BY rank ASC
            LIMIT {limit}
            """
            
            gainers_result = self._client.query(gainers_query)
            losers_result = self._client.query(losers_query)
            
            # 转换涨幅榜数据
            gainers = []
            for row in gainers_result.result_rows:
                try:
                    gainers.append({
                        'symbol': str(row[0]) if row[0] else '',
                        'price': float(row[1]) if row[1] is not None else 0.0,
                        'change_percent': float(row[2]) if row[2] is not None else 0.0,
                        'side': str(row[3]) if row[3] else 'gainer',
                        'change_percent_text': str(row[4]) if row[4] else '',
                        'quote_volume': float(row[5]) if row[5] is not None else 0.0,
                        'rank': int(row[6]) if row[6] is not None else 0
                    })
                except (TypeError, ValueError, IndexError) as e:
                    logger.warning("[ClickHouse] Failed to parse gainer row: %s, error: %s", row, e)
                    continue
            
            # 转换跌幅榜数据
            losers = []
            for row in losers_result.result_rows:
                try:
                    losers.append({
                        'symbol': str(row[0]) if row[0] else '',
                        'price': float(row[1]) if row[1] is not None else 0.0,
                        'change_percent': float(row[2]) if row[2] is not None else 0.0,
                        'side': str(row[3]) if row[3] else 'loser',
                        'change_percent_text': str(row[4]) if row[4] else '',
                        'quote_volume': float(row[5]) if row[5] is not None else 0.0,
                        'rank': int(row[6]) if row[6] is not None else 0
                    })
                except (TypeError, ValueError, IndexError) as e:
                    logger.warning("[ClickHouse] Failed to parse loser row: %s, error: %s", row, e)
                    continue
            
            return {
                'gainers': gainers,
                'losers': losers
            }
        except Exception as exc:
            logger.error("[ClickHouse] Failed to get leaderboard: %s", exc, exc_info=True)
            return {'gainers': [], 'losers': []}

    def get_leaderboard_symbols(self) -> List[str]:
        """Get distinct symbols from leaderboard table."""
        try:
            query = f"""
            SELECT DISTINCT symbol
            FROM {self.leaderboard_table}
            WHERE symbol != ''
            """
            result = self._client.query(query)
            symbols = [row[0] for row in result.result_rows if row[0]]
            return symbols
        except Exception as exc:
            logger.error("[ClickHouse] Failed to get leaderboard symbols: %s", exc, exc_info=True)
            return []

    def ensure_market_klines_table(self) -> None:
        """Create the market_klines table if it does not exist."""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {self.market_klines_table} (
            event_time DateTime,
            symbol String,
            contract_type String,
            kline_start_time DateTime,
            kline_end_time DateTime,
            interval String,
            first_trade_id UInt64,
            last_trade_id UInt64,
            open_price Float64,
            close_price Float64,
            high_price Float64,
            low_price Float64,
            base_volume Float64,
            trade_count UInt64,
            is_closed UInt8,
            quote_volume Float64,
            taker_buy_base_volume Float64,
            taker_buy_quote_volume Float64,
            create_time DateTime DEFAULT now()
        )
        ENGINE = MergeTree
        ORDER BY (symbol, interval, kline_end_time, event_time)
        TTL kline_end_time + INTERVAL 2 DAY
        """
        self.command(ddl)
        logger.info("[ClickHouse] Ensured table %s exists", self.market_klines_table)

    def insert_market_klines(self, rows: Iterable[Dict[str, Any]]) -> None:
        """Insert kline data into market_klines table."""
        if not rows:
            return
        
        column_names = [
            "event_time",
            "symbol",
            "contract_type",
            "kline_start_time",
            "kline_end_time",
            "interval",
            "first_trade_id",
            "last_trade_id",
            "open_price",
            "close_price",
            "high_price",
            "low_price",
            "base_volume",
            "trade_count",
            "is_closed",
            "quote_volume",
            "taker_buy_base_volume",
            "taker_buy_quote_volume",
        ]
        
        # Convert rows to list of tuples
        insert_rows = []
        for row in rows:
            insert_rows.append((
                row.get("event_time"),
                row.get("symbol", ""),
                row.get("contract_type", ""),
                row.get("kline_start_time"),
                row.get("kline_end_time"),
                row.get("interval", ""),
                row.get("first_trade_id", 0),
                row.get("last_trade_id", 0),
                row.get("open_price", 0.0),
                row.get("close_price", 0.0),
                row.get("high_price", 0.0),
                row.get("low_price", 0.0),
                row.get("base_volume", 0.0),
                row.get("trade_count", 0),
                row.get("is_closed", 0),
                row.get("quote_volume", 0.0),
                row.get("taker_buy_base_volume", 0.0),
                row.get("taker_buy_quote_volume", 0.0),
            ))
        
        self.insert_rows(self.market_klines_table, insert_rows, column_names)
        logger.debug("[ClickHouse] Inserted %s kline rows into %s", len(insert_rows), self.market_klines_table)

    def cleanup_old_klines(self, days: int = 2) -> int:
        """Delete klines older than specified days. Returns number of deleted rows."""
        try:
            # ClickHouse DELETE requires mutations, use ALTER TABLE DELETE
            delete_sql = f"""
            ALTER TABLE {self.market_klines_table}
            DELETE WHERE kline_end_time < now() - INTERVAL {days} DAY
            """
            self.command(delete_sql)
            # Note: ClickHouse DELETE is asynchronous, we can't get exact count immediately
            logger.info("[ClickHouse] Initiated cleanup of klines older than %s days", days)
            return 0  # ClickHouse doesn't return count for async DELETE
        except Exception as exc:
            logger.error("[ClickHouse] Failed to cleanup old klines: %s", exc, exc_info=True)
            return 0


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
    def ensure_market_klines_table(self) -> None:
        """Create the market_klines table if it does not exist."""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {self.market_klines_table} (
            event_time DateTime,
            symbol String,
            contract_type String,
            kline_start_time DateTime,
            kline_end_time DateTime,
            interval String,
            first_trade_id UInt64,
            last_trade_id UInt64,
            open_price Float64,
            close_price Float64,
            high_price Float64,
            low_price Float64,
            base_volume Float64,
            trade_count UInt64,
            is_closed UInt8,
            quote_volume Float64,
            taker_buy_base_volume Float64,
            taker_buy_quote_volume Float64,
            create_time DateTime DEFAULT now()
        )
        ENGINE = MergeTree
        ORDER BY (symbol, interval, kline_end_time, event_time)
        TTL kline_end_time + INTERVAL 2 DAY
        """
        self.command(ddl)
        logger.info("[ClickHouse] Ensured table %s exists", self.market_klines_table)

    def insert_market_klines(self, rows: Iterable[Dict[str, Any]]) -> None:
        """Insert kline data into market_klines table."""
        if not rows:
            return
        
        column_names = [
            "event_time",
            "symbol",
            "contract_type",
            "kline_start_time",
            "kline_end_time",
            "interval",
            "first_trade_id",
            "last_trade_id",
            "open_price",
            "close_price",
            "high_price",
            "low_price",
            "base_volume",
            "trade_count",
            "is_closed",
            "quote_volume",
            "taker_buy_base_volume",
            "taker_buy_quote_volume",
        ]
        
        # Convert rows to list of tuples
        insert_rows = []
        for row in rows:
            insert_rows.append((
                row.get("event_time"),
                row.get("symbol", ""),
                row.get("contract_type", ""),
                row.get("kline_start_time"),
                row.get("kline_end_time"),
                row.get("interval", ""),
                row.get("first_trade_id", 0),
                row.get("last_trade_id", 0),
                row.get("open_price", 0.0),
                row.get("close_price", 0.0),
                row.get("high_price", 0.0),
                row.get("low_price", 0.0),
                row.get("base_volume", 0.0),
                row.get("trade_count", 0),
                row.get("is_closed", 0),
                row.get("quote_volume", 0.0),
                row.get("taker_buy_base_volume", 0.0),
                row.get("taker_buy_quote_volume", 0.0),
            ))
        
        self.insert_rows(self.market_klines_table, insert_rows, column_names)
        logger.debug("[ClickHouse] Inserted %s kline rows into %s", len(insert_rows), self.market_klines_table)

    def get_leaderboard_symbols(self) -> List[str]:
        """Get distinct symbols from leaderboard table."""
        try:
            query = f"""
            SELECT DISTINCT symbol
            FROM {self.leaderboard_table}
            WHERE symbol != ''
            """
            result = self._client.query(query)
            symbols = [row[0] for row in result.result_rows if row[0]]
            return symbols
        except Exception as exc:
            logger.error("[ClickHouse] Failed to get leaderboard symbols: %s", exc, exc_info=True)
            return []

    def cleanup_old_klines(self, days: int = 2) -> int:
        """Delete klines older than specified days. Returns number of deleted rows."""
        try:
            # ClickHouse DELETE requires mutations, use ALTER TABLE DELETE
            delete_sql = f"""
            ALTER TABLE {self.market_klines_table}
            DELETE WHERE kline_end_time < now() - INTERVAL {days} DAY
            """
            self.command(delete_sql)
            # Note: ClickHouse DELETE is asynchronous, we can't get exact count immediately
            logger.info("[ClickHouse] Initiated cleanup of klines older than %s days", days)
            return 0  # ClickHouse doesn't return count for async DELETE
        except Exception as exc:
            logger.error("[ClickHouse] Failed to cleanup old klines: %s", exc, exc_info=True)
            return 0
