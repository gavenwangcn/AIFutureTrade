"""ClickHouse database utilities for market data storage."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone, timedelta
from queue import Queue, Empty
from typing import Any, Dict, Iterable, List, Optional, Callable

import clickhouse_connect
import config as app_config

MARKET_TICKER_TABLE = "24_market_tickers"
LEADERBOARD_TABLE = "futures_leaderboard"
MARKET_KLINES_TABLE = "market_klines"

logger = logging.getLogger(__name__)


class ClickHouseConnectionPool:
    """ClickHouse connection pool to manage client instances.
    
    This class manages a pool of ClickHouse client instances to avoid creating
    too many connections to the ClickHouse server. It provides methods to acquire
    and release connections, and supports dynamic expansion up to a maximum
    number of connections.
    """
    
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        database: str,
        secure: bool,
        min_connections: int = 5,
        max_connections: int = 20,
        connection_timeout: int = 30
    ):
        """Initialize the connection pool.
        
        Args:
            host: ClickHouse host
            port: ClickHouse port
            username: ClickHouse username
            password: ClickHouse password
            database: ClickHouse database
            secure: Whether to use secure connection
            min_connections: Minimum number of connections to keep in the pool
            max_connections: Maximum number of connections allowed in the pool
            connection_timeout: Timeout for acquiring a connection (seconds)
        """
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._database = database
        self._secure = secure
        self._min_connections = min_connections
        self._max_connections = max_connections
        self._connection_timeout = connection_timeout
        
        # Create a queue to hold the connections
        self._pool = Queue(maxsize=max_connections)
        
        # Create a lock to protect the connection count
        self._lock = threading.Lock()
        
        # Current number of connections in the pool
        self._current_connections = 0
        
        # Initialize the pool with min_connections
        self._initialize_pool()
    
    def _initialize_pool(self):
        """Initialize the pool with minimum connections."""
        for _ in range(self._min_connections):
            self._create_connection()
    
    def _create_connection(self):
        """Create a new ClickHouse client connection."""
        with self._lock:
            if self._current_connections >= self._max_connections:
                return None
            
            try:
                client = clickhouse_connect.get_client(
                    host=self._host,
                    port=self._port,
                    username=self._username,
                    password=self._password,
                    database=self._database,
                    secure=self._secure
                )
                self._pool.put(client)
                self._current_connections += 1
                logger.debug(f"[ClickHouse] Created new connection. Current connections: {self._current_connections}")
                return client
            except Exception as e:
                logger.error(f"[ClickHouse] Failed to create connection: {e}")
                return None
    
    def acquire(self, timeout: Optional[int] = None) -> Optional[Any]:
        """Acquire a connection from the pool.
        
        Args:
            timeout: Timeout for acquiring a connection (seconds). If None, use the default timeout.
            
        Returns:
            A ClickHouse client instance, or None if no connection is available within the timeout.
        """
        timeout = timeout or self._connection_timeout
        
        try:
            # Try to get a connection from the pool
            client = self._pool.get(timeout=timeout)
            logger.debug(f"[ClickHouse] Acquired connection from pool")
            return client
        except Empty:
            # If the pool is empty, try to create a new connection
            logger.debug(f"[ClickHouse] Pool is empty, creating new connection")
            client = self._create_connection()
            if client:
                return client
            
            # If we can't create a new connection, try again to get from the pool
            try:
                client = self._pool.get(timeout=timeout)
                logger.debug(f"[ClickHouse] Acquired connection from pool after waiting")
                return client
            except Empty:
                logger.error(f"[ClickHouse] Failed to acquire connection within timeout {timeout} seconds")
                return None
    
    def release(self, client: Any) -> None:
        """Release a connection back to the pool.
        
        Args:
            client: The ClickHouse client instance to release
        """
        try:
            # Check if the client is still valid by sending a simple query
            client.query("SELECT 1")
            self._pool.put(client)
            logger.debug(f"[ClickHouse] Released connection back to pool")
        except Exception as e:
            # If the client is invalid, close it and don't return it to the pool
            logger.error(f"[ClickHouse] Connection is invalid, closing it: {e}")
            with self._lock:
                self._current_connections -= 1
    
    def close_all(self) -> None:
        """Close all connections in the pool."""
        with self._lock:
            while not self._pool.empty():
                try:
                    client = self._pool.get_nowait()
                    client.close()
                    self._current_connections -= 1
                except Exception as e:
                    logger.error(f"[ClickHouse] Failed to close connection: {e}")
            
            logger.info(f"[ClickHouse] Closed all connections. Current connections: {self._current_connections}")


class ClickHouseDatabase:
    """Encapsulates ClickHouse connectivity and CRUD helpers."""
    
    # 类级别的锁，用于防止并发执行 sync_leaderboard
    _sync_leaderboard_lock = threading.Lock()

    def __init__(self, *, auto_init_tables: bool = True) -> None:
        # Create a connection pool instead of individual client instances
        self._pool = ClickHouseConnectionPool(
            host=app_config.CLICKHOUSE_HOST,
            port=app_config.CLICKHOUSE_PORT,
            username=app_config.CLICKHOUSE_USER,
            password=app_config.CLICKHOUSE_PASSWORD,
            database=app_config.CLICKHOUSE_DATABASE,
            secure=app_config.CLICKHOUSE_SECURE,
            min_connections=5,
            max_connections=50,
            connection_timeout=30
        )
        
        self.market_ticker_table = MARKET_TICKER_TABLE
        self.leaderboard_table = getattr(app_config, 'CLICKHOUSE_LEADERBOARD_TABLE', LEADERBOARD_TABLE)
        self.market_klines_table = getattr(app_config, 'CLICKHOUSE_MARKET_KLINES_TABLE', MARKET_KLINES_TABLE)
        
        if auto_init_tables:
            # Initialize tables using the connection pool
            self.ensure_market_ticker_table()
            self.ensure_leaderboard_table()
            self.ensure_market_klines_table()
    
    def _with_connection(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function with a ClickHouse connection from the pool.
        
        This method acquires a connection from the pool, executes the given function
        with the connection as the first argument, and then releases the connection back to the pool.
        
        Args:
            func: The function to execute
            *args: Positional arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function
            
        Returns:
            The result of the function call
        """
        client = self._pool.acquire()
        if not client:
            raise Exception("Failed to acquire ClickHouse connection")
        
        try:
            return func(client, *args, **kwargs)
        finally:
            self._pool.release(client)

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------
    def command(self, sql: str) -> None:
        """Execute a raw SQL command."""
        def _execute_command(client):
            client.command(sql)
        
        self._with_connection(_execute_command)
    
    def _check_table_exists(self, table_name: str) -> bool:
        """Check if a table exists in ClickHouse.
        
        Args:
            table_name: The name of the table to check
            
        Returns:
            True if the table exists, False otherwise
        """
        def _execute_check(client):
            try:
                # 查询系统表检查表是否存在
                check_sql = f"""
                SELECT count() 
                FROM system.tables 
                WHERE database = currentDatabase() 
                AND name = '{table_name}'
                """
                result = client.query(check_sql)
                return result.result_rows[0][0] > 0 if result.result_rows else False
            except Exception as e:
                logger.warning(f"[ClickHouse] 检查表是否存在时出错: {e}")
                return False
        
        return self._with_connection(_execute_check)

    def insert_rows(
        self,
        table: str,
        rows: Iterable[Iterable[Any]],
        column_names: List[str],
    ) -> None:
        payload = list(rows)
        if not payload:
            return
        
        def _execute_insert(client):
            client.insert(table, payload, column_names=column_names)
            logger.debug("[ClickHouse] Inserted %s rows into %s", len(payload), table)
        
        self._with_connection(_execute_insert)

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
            ingestion_time DateTime DEFAULT now(),
            update_price_date Nullable(DateTime)
        )
        ENGINE = MergeTree
        ORDER BY (symbol, stats_close_time, event_time)
        """
        self.command(ddl)
        logger.info("[ClickHouse] Ensured table %s exists", self.market_ticker_table)
        
        # 如果表已存在，添加新字段（如果不存在）或修改字段类型为Nullable
        try:
            # 检查字段是否存在
            check_column_sql = f"""
            SELECT name, type FROM system.columns 
            WHERE database = '{app_config.CLICKHOUSE_DATABASE}' 
            AND table = '{self.market_ticker_table}' 
            AND name = 'update_price_date'
            """
            def _check_column(client):
                result = client.query(check_column_sql)
                if len(result.result_rows) > 0:
                    return result.result_rows[0][1]  # 返回字段类型
                return None
            
            column_type = self._with_connection(_check_column)
            
            if column_type is None:
                # 字段不存在，添加为Nullable
                add_column_sql = f"""
                ALTER TABLE {self.market_ticker_table} 
                ADD COLUMN IF NOT EXISTS update_price_date Nullable(DateTime)
                """
                self.command(add_column_sql)
                logger.info("[ClickHouse] Added update_price_date column to %s", self.market_ticker_table)
            elif 'Nullable' not in str(column_type):
                # 字段存在但不是Nullable，尝试修改为Nullable
                try:
                    modify_column_sql = f"""
                    ALTER TABLE {self.market_ticker_table} 
                    MODIFY COLUMN update_price_date Nullable(DateTime)
                    """
                    self.command(modify_column_sql)
                    logger.info("[ClickHouse] Modified update_price_date column to Nullable(DateTime)")
                except Exception as modify_exc:
                    logger.warning("[ClickHouse] Failed to modify update_price_date to Nullable (may not be supported): %s", modify_exc)
        except Exception as e:
            logger.warning("[ClickHouse] Failed to check/modify update_price_date column: %s", e)

    def get_existing_symbol_data(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """查询现有symbol的数据，返回字典 {symbol: {open_price: ..., update_price_date: ..., ...}}
        
        注意：为了保持原有逻辑，如果open_price为0.0且update_price_date为None，
        则视为"未设置"，返回open_price=None而不是0.0
        """
        if not symbols:
            return {}
        
        try:
            symbols_str = "', '".join(symbols)
            query = f"""
            SELECT 
                symbol,
                open_price,
                last_price,
                update_price_date
            FROM (
                SELECT 
                    *,
                    ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY event_time DESC) as rn
                FROM {self.market_ticker_table}
                WHERE symbol IN ('{symbols_str}')
            ) AS ranked
            WHERE rn = 1
            """
            
            def _execute_query(client):
                return client.query(query)
            
            result = self._with_connection(_execute_query)
            
            symbol_data = {}
            for row in result.result_rows:
                symbol = row[0]
                open_price_raw = row[1]  # 可能是0.0或实际价格
                last_price = row[2] if row[2] is not None else None
                update_price_date = row[3] if len(row) > 3 else None
                
                # 关键逻辑：如果open_price为0.0且update_price_date为None，视为"未设置"
                # 返回None以保持原有判断逻辑的正确性
                if open_price_raw == 0.0 and update_price_date is None:
                    open_price = None  # 视为未设置
                else:
                    open_price = open_price_raw if open_price_raw is not None else None
                
                symbol_data[symbol] = {
                    "open_price": open_price,
                    "last_price": last_price,
                    "update_price_date": update_price_date
                }
            
            return symbol_data
        except Exception as e:
            logger.warning("[ClickHouse] Failed to get existing symbol data: %s", e)
            return {}

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
            "update_price_date",
        ]

        prepared_rows: List[List[Any]] = []
        for row in rows:
            normalized = dict(row)
            
            # 重要：移除接口数据中的 open_price 和 update_price_date 字段
            # 这两个字段只能由异步价格刷新服务更新，接口数据不能覆盖它们
            if "open_price" in normalized:
                del normalized["open_price"]
                logger.debug("[ClickHouse] 移除接口数据中的 open_price 字段（只能由异步价格刷新服务更新）")
            if "update_price_date" in normalized:
                del normalized["update_price_date"]
                logger.debug("[ClickHouse] 移除接口数据中的 update_price_date 字段（只能由异步价格刷新服务更新）")
            
            normalized["event_time"] = _to_datetime(normalized.get("event_time"))
            normalized["stats_open_time"] = _to_datetime(normalized.get("stats_open_time"))
            normalized["stats_close_time"] = _to_datetime(normalized.get("stats_close_time"))
            
            # 确保所有Float64字段不为None，使用0.0作为默认值
            # Float64字段列表：price_change, price_change_percent, average_price, last_price,
            # last_trade_volume, open_price, high_price, low_price, base_volume, quote_volume
            float64_fields = [
                "price_change", "price_change_percent", "average_price", "last_price",
                "last_trade_volume", "open_price", "high_price", "low_price",
                "base_volume", "quote_volume"
            ]
            for field in float64_fields:
                if normalized.get(field) is None:
                    normalized[field] = 0.0
            
            # 确保UInt64字段不为None
            uint64_fields = ["first_trade_id", "last_trade_id", "trade_count"]
            for field in uint64_fields:
                if normalized.get(field) is None:
                    normalized[field] = 0
            
            # 确保String字段不为None，使用空字符串作为默认值
            # String字段：side, change_percent_text（表结构中这些字段不是Nullable）
            string_fields = ["side", "change_percent_text"]
            for field in string_fields:
                if normalized.get(field) is None:
                    normalized[field] = ""
            
            # DateTime字段处理：确保所有非Nullable的DateTime字段都不为None
            # event_time, stats_open_time, stats_close_time 已经在前面通过_to_datetime处理过了
            # ingestion_time 如果没有值，使用当前时间
            # update_price_date 可以为None（因为表结构中是Nullable(DateTime)）
            datetime_fields = ["event_time", "stats_open_time", "stats_close_time"]
            for field in datetime_fields:
                if normalized.get(field) is None:
                    normalized[field] = datetime.now(timezone.utc)
            
            # ingestion_time 字段处理（如果有的话）
            if "ingestion_time" in normalized and normalized.get("ingestion_time") is None:
                normalized["ingestion_time"] = datetime.now(timezone.utc)
            
            # update_price_date 可以为None（Nullable字段）
            normalized.setdefault("update_price_date", None)
            
            # 准备行数据，确保所有字段都有值
            row_data = []
            for name in column_names:
                value = normalized.get(name)
                # 对于非Nullable的DateTime字段，确保不为None
                if name in ["event_time", "stats_open_time", "stats_close_time", "ingestion_time"]:
                    if value is None:
                        value = datetime.now(timezone.utc)
                row_data.append(value)
            
            prepared_rows.append(row_data)

        self.insert_rows(self.market_ticker_table, prepared_rows, column_names)
        
    def upsert_market_tickers(self, rows: Iterable[Dict[str, Any]]) -> None:
        """Update or insert market tickers. If symbol exists, update it, otherwise insert.
        
        处理逻辑：
        1. 第一次插入时，price_change, price_change_percent, side, change_percent_text, open_price 都为空
        2. 更新时，如果 open_price 有值，则通过 last_price 和 open_price 计算涨跌幅相关字段
        
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
            "update_price_date",
        ]

        # 处理数据：对于同一批数据中的重复symbol，只保留最新的一条（基于stats_close_time）
        symbol_data_map: Dict[str, Dict[str, Any]] = {}
        
        for row in usdt_rows:
            normalized = dict(row)
            
            # 重要：移除接口数据中的 open_price 和 update_price_date 字段
            # 这两个字段只能由异步价格刷新服务更新，接口数据不能覆盖它们
            if "open_price" in normalized:
                del normalized["open_price"]
                logger.debug("[ClickHouse] 移除接口数据中的 open_price 字段（只能由异步价格刷新服务更新）")
            if "update_price_date" in normalized:
                del normalized["update_price_date"]
                logger.debug("[ClickHouse] 移除接口数据中的 update_price_date 字段（只能由异步价格刷新服务更新）")
            
            normalized["event_time"] = _to_datetime(normalized.get("event_time"))
            normalized["stats_open_time"] = _to_datetime(normalized.get("stats_open_time"))
            normalized["stats_close_time"] = _to_datetime(normalized.get("stats_close_time"))
            
            symbol = normalized.get("symbol")
            if not symbol:
                continue
            
            stats_close_time = normalized.get("stats_close_time")
            
            # 如果该symbol已存在，比较stats_close_time，只保留最新的
            if symbol in symbol_data_map:
                existing_stats_close_time = symbol_data_map[symbol].get("stats_close_time")
                if stats_close_time and existing_stats_close_time:
                    if stats_close_time > existing_stats_close_time:
                        symbol_data_map[symbol] = normalized
                elif stats_close_time:
                    # 当前数据有stats_close_time，保留当前数据
                    symbol_data_map[symbol] = normalized
            else:
                symbol_data_map[symbol] = normalized
        
        if not symbol_data_map:
            return
        
        # 查询现有symbol的数据，获取open_price
        symbols_to_upsert = list(symbol_data_map.keys())
        existing_data = self.get_existing_symbol_data(symbols_to_upsert)
        
        # 准备插入数据（每个symbol只有一条最新数据）
        prepared_rows: List[List[Any]] = []
        
        for symbol, normalized in symbol_data_map.items():
            # 获取当前报文的last_price
            try:
                current_last_price = float(normalized.get("last_price", 0))
            except (TypeError, ValueError):
                current_last_price = 0.0
            
            # 判断是插入还是更新
            existing_symbol_data = existing_data.get(symbol)
            existing_open_price = existing_symbol_data.get("open_price") if existing_symbol_data else None
            existing_update_price_date = existing_symbol_data.get("update_price_date") if existing_symbol_data else None
            
            # 关键逻辑：判断open_price是否已设置
            # existing_open_price为None表示未设置（即使数据库中存储的是0.0，如果update_price_date为None也视为未设置）
            # existing_open_price不为None且不为0表示已设置且有有效值
            # 如果是更新且open_price有值（不为None且不为0），则计算涨跌幅相关字段
            if existing_open_price is not None and existing_open_price != 0 and current_last_price != 0:
                try:
                    existing_open_price_float = float(existing_open_price)
                    current_last_price_float = float(current_last_price)
                    
                    # 计算 price_change = last_price - open_price
                    price_change = current_last_price_float - existing_open_price_float
                    
                    # 计算 price_change_percent = (last_price - open_price) / open_price * 100
                    price_change_percent = (price_change / existing_open_price_float) * 100
                    
                    # 根据正负设置 side（0为正，即gainer）
                    side = "gainer" if price_change_percent >= 0 else "loser"
                    
                    # 设置 change_percent_text = price_change_percent + "%"
                    change_percent_text = f"{price_change_percent:.2f}%"
                    
                    # 重要：保持原有的open_price和update_price_date，不更新
                    # 这两个字段只能由异步价格刷新服务更新，接口数据不能覆盖它们
                    normalized["price_change"] = price_change
                    normalized["price_change_percent"] = price_change_percent
                    normalized["side"] = side
                    normalized["change_percent_text"] = change_percent_text
                    normalized["open_price"] = existing_open_price_float  # 保留数据库中的值
                    normalized["update_price_date"] = existing_update_price_date  # 保留数据库中的值（可能为None）
                except (TypeError, ValueError) as e:
                    logger.warning("[ClickHouse] Failed to calculate price change for symbol %s: %s", symbol, e)
                    # 计算失败时，设置为0.0（Float64字段不能为None）
                    normalized["price_change"] = 0.0
                    normalized["price_change_percent"] = 0.0
                    normalized["side"] = ""  # String字段不能为None，使用空字符串
                    normalized["change_percent_text"] = ""  # String字段不能为None，使用空字符串
                    # 重要：保留数据库中的open_price和update_price_date
                    normalized["open_price"] = existing_open_price_float if existing_open_price_float else 0.0
                    normalized["update_price_date"] = existing_update_price_date  # 保留数据库中的值（可能为None）
            else:
                # 第一次插入或open_price未设置的情况
                # Float64字段设置为0.0而不是None（因为ClickHouse Float64不接受None）
                # 但逻辑上，open_price=0.0且update_price_date=None表示"未设置"
                # 这样下次查询时，get_existing_symbol_data会返回open_price=None，保持原有判断逻辑正确
                normalized["price_change"] = 0.0
                normalized["price_change_percent"] = 0.0
                normalized["side"] = ""  # String字段不能为None，使用空字符串
                normalized["change_percent_text"] = ""  # String字段不能为None，使用空字符串
                # 重要：如果是更新操作，保留数据库中的update_price_date；如果是插入操作，设置为None
                normalized["open_price"] = 0.0  # 存储为0.0，但逻辑上视为"未设置"（因为update_price_date=None）
                normalized["update_price_date"] = existing_update_price_date if existing_symbol_data else None
            
            # 确保所有Float64字段不为None，使用0.0作为默认值
            # Float64字段列表：price_change, price_change_percent, average_price, last_price,
            # last_trade_volume, open_price, high_price, low_price, base_volume, quote_volume
            float64_fields = [
                "price_change", "price_change_percent", "average_price", "last_price",
                "last_trade_volume", "open_price", "high_price", "low_price",
                "base_volume", "quote_volume"
            ]
            for field in float64_fields:
                if normalized.get(field) is None:
                    normalized[field] = 0.0
            
            # 确保UInt64字段不为None
            uint64_fields = ["first_trade_id", "last_trade_id", "trade_count"]
            for field in uint64_fields:
                if normalized.get(field) is None:
                    normalized[field] = 0
            
            # 确保String字段不为None，使用空字符串作为默认值
            # String字段：side, change_percent_text（表结构中这些字段不是Nullable）
            string_fields = ["side", "change_percent_text"]
            for field in string_fields:
                if normalized.get(field) is None:
                    normalized[field] = ""
            
            # DateTime字段处理：确保所有非Nullable的DateTime字段都不为None
            # event_time, stats_open_time, stats_close_time 已经在前面通过_to_datetime处理过了
            # ingestion_time 如果没有值，使用当前时间
            # update_price_date 可以为None（因为表结构中是Nullable(DateTime)）
            datetime_fields = ["event_time", "stats_open_time", "stats_close_time"]
            for field in datetime_fields:
                if normalized.get(field) is None:
                    normalized[field] = datetime.now(timezone.utc)
            
            # ingestion_time 字段处理（如果有的话）
            if "ingestion_time" in normalized and normalized.get("ingestion_time") is None:
                normalized["ingestion_time"] = datetime.now(timezone.utc)
            
            # 准备行数据，确保所有字段都有值
            row_data = []
            for name in column_names:
                value = normalized.get(name)
                # 对于非Nullable的DateTime字段，确保不为None
                if name in ["event_time", "stats_open_time", "stats_close_time", "ingestion_time"]:
                    if value is None:
                        value = datetime.now(timezone.utc)
                row_data.append(value)
            
            prepared_rows.append(row_data)
        
        # For ClickHouse, the most efficient way to upsert is to delete existing rows first, then insert new ones
        # This is more efficient than UPDATE for MergeTree tables
        if symbols_to_upsert:
            # Delete existing rows with the same symbols
            # 使用去重后的symbol列表，避免重复删除
            unique_symbols = list(set(symbols_to_upsert))
            symbols_str = "', '".join(unique_symbols)
            delete_query = f"ALTER TABLE {self.market_ticker_table} DELETE WHERE symbol IN ('{symbols_str}')"
            try:
                self.command(delete_query)
                logger.debug("[ClickHouse] Deleted existing rows for symbols: %s", unique_symbols)
            except Exception as e:
                logger.warning("[ClickHouse] Failed to delete existing rows: %s", e)
        
        # Insert new rows (每个symbol只有一条数据)
        self.insert_rows(self.market_ticker_table, prepared_rows, column_names)
        logger.debug(
            "[ClickHouse] Upserted %s rows into %s (ensured no duplicate symbols)",
            len(prepared_rows), self.market_ticker_table
        )
    
    def get_symbols_needing_price_refresh(self) -> List[str]:
        """获取需要刷新价格的symbol列表
        
        查询条件：
        - update_price_date 为空
        - 或者 update_price_date 不为当天
        
        Returns:
            需要刷新价格的symbol列表（去重）
        """
        try:
            query = f"""
            SELECT DISTINCT symbol
            FROM {self.market_ticker_table}
            WHERE symbol != ''
            AND (
                update_price_date IS NULL
                OR toDate(update_price_date) != today()
            )
            ORDER BY symbol
            """
            
            def _execute_query(client):
                return client.query(query)
            
            result = self._with_connection(_execute_query)
            symbols = [row[0] for row in result.result_rows if row[0]]
            logger.debug("[ClickHouse] Found %s symbols needing price refresh", len(symbols))
            return symbols
        except Exception as e:
            logger.error("[ClickHouse] Failed to get symbols needing price refresh: %s", e, exc_info=True)
            return []
    
    def update_open_price(self, symbol: str, open_price: float, update_date: datetime) -> bool:
        """更新指定symbol的open_price和update_price_date
        
        Args:
            symbol: 交易对符号
            open_price: 开盘价（昨天的日K线收盘价）
            update_date: 更新日期时间（当前刷新时间，用于记录刷新时间戳）
            
        Returns:
            是否更新成功
        """
        try:
            # 使用ALTER TABLE UPDATE来更新数据
            # 由于ClickHouse的UPDATE操作是异步的，我们使用DELETE + INSERT的方式更可靠
            # 但为了性能，我们可以使用ALTER TABLE UPDATE
            
            # 先查询当前数据
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
                    ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY event_time DESC) as rn
                FROM {self.market_ticker_table}
                WHERE symbol = '{symbol}'
            ) AS ranked
            WHERE rn = 1
            """
            
            def _execute_query(client):
                return client.query(query)
            
            result = self._with_connection(_execute_query)
            
            if not result.result_rows:
                logger.warning("[ClickHouse] Symbol %s not found for price update", symbol)
                return False
            
            # 获取最新的一条数据
            row = result.result_rows[0]
            
            # 准备更新后的数据
            column_names = [
                "event_time", "symbol", "price_change", "price_change_percent", "side",
                "change_percent_text", "average_price", "last_price", "last_trade_volume",
                "open_price", "high_price", "low_price", "base_volume", "quote_volume",
                "stats_open_time", "stats_close_time", "first_trade_id", "last_trade_id",
                "trade_count", "ingestion_time", "update_price_date"
            ]
            
            # 重新计算涨跌幅相关字段（基于新的open_price和当前的last_price）
            # 查询返回的列顺序：event_time, symbol, price_change, price_change_percent, side,
            # change_percent_text, average_price, last_price, last_trade_volume, high_price,
            # low_price, base_volume, quote_volume, stats_open_time, stats_close_time,
            # first_trade_id, last_trade_id, trade_count, ingestion_time
            last_price = float(row[7]) if row[7] is not None else 0.0  # last_price在索引7
            new_open_price = float(open_price)
            
            if new_open_price != 0 and last_price != 0:
                price_change = last_price - new_open_price
                price_change_percent = (price_change / new_open_price) * 100
                side = "gainer" if price_change_percent >= 0 else "loser"
                change_percent_text = f"{price_change_percent:.2f}%"
            else:
                # 如果无法计算，使用默认值（不能为None）
                price_change = 0.0
                price_change_percent = 0.0
                side = ""
                change_percent_text = ""
            
            # 构建更新后的行数据
            # 确保所有字段都有正确的类型和默认值
            updated_row = [
                _to_datetime(row[0]),  # event_time (DateTime)
                _normalize_field_value(row[1], "String", "symbol"),  # symbol (String)
                _normalize_field_value(price_change, "Float64", "price_change"),  # price_change (Float64)
                _normalize_field_value(price_change_percent, "Float64", "price_change_percent"),  # price_change_percent (Float64)
                _normalize_field_value(side, "String", "side"),  # side (String)
                _normalize_field_value(change_percent_text, "String", "change_percent_text"),  # change_percent_text (String)
                _normalize_field_value(row[6], "Float64", "average_price"),  # average_price (Float64)
                _normalize_field_value(row[7], "Float64", "last_price"),  # last_price (Float64)
                _normalize_field_value(row[8], "Float64", "last_trade_volume"),  # last_trade_volume (Float64)
                _normalize_field_value(new_open_price, "Float64", "open_price"),  # open_price (Float64)
                _normalize_field_value(row[9], "Float64", "high_price"),  # high_price (Float64)
                _normalize_field_value(row[10], "Float64", "low_price"),  # low_price (Float64)
                _normalize_field_value(row[11], "Float64", "base_volume"),  # base_volume (Float64)
                _normalize_field_value(row[12], "Float64", "quote_volume"),  # quote_volume (Float64)
                _to_datetime(row[13]),  # stats_open_time (DateTime)
                _to_datetime(row[14]),  # stats_close_time (DateTime)
                _normalize_field_value(row[15], "UInt64", "first_trade_id"),  # first_trade_id (UInt64)
                _normalize_field_value(row[16], "UInt64", "last_trade_id"),  # last_trade_id (UInt64)
                _normalize_field_value(row[17], "UInt64", "trade_count"),  # trade_count (UInt64)
                _to_datetime(row[18]) if row[18] else datetime.now(timezone.utc),  # ingestion_time (DateTime)
                update_date  # update_price_date (Nullable(DateTime)) - 可以为None
            ]
            
            # 删除旧数据并插入新数据（ClickHouse的UPDATE方式）
            delete_query = f"ALTER TABLE {self.market_ticker_table} DELETE WHERE symbol = '{symbol}'"
            try:
                self.command(delete_query)
            except Exception as e:
                logger.warning("[ClickHouse] Failed to delete old row for %s: %s", symbol, e)
            
            # 插入更新后的数据
            self.insert_rows(self.market_ticker_table, [updated_row], column_names)
            logger.debug("[ClickHouse] Updated open_price for symbol %s: %s", symbol, new_open_price)
            return True
            
        except Exception as e:
            logger.error("[ClickHouse] Failed to update open_price for symbol %s: %s", symbol, e, exc_info=True)
            return False
    
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
        """查询所有市场行情数据，用于生成涨跌幅榜
        
        核心功能：
        - 从24_market_tickers表查询所有数据（不限制时间窗口）
        - 对每个交易对取最新的行情数据（去重）
        - 根据price_change_percent字段判断涨跌：正为涨，负为跌
        - 返回涨幅或跌幅前十的数据
        
        执行流程：
        1. 根据side参数确定查询逻辑：
           - gainer：查询price_change_percent>0的合约，按降序排序
           - loser：查询price_change_percent<0的合约，按升序排序
        2. 构建查询SQL，包含去重逻辑（按symbol分组，取最新event_time）
        3. 执行查询并返回结果
        
        Args:
            time_window_seconds: 已废弃，保留参数以兼容现有调用，不再使用
            side: 筛选方向，可选值：'gainer'（涨幅榜）、'loser'（跌幅榜），None表示全部
            top_n: 返回前N名数据
            
        Returns:
            List[Dict[str, Any]]: 行情数据字典列表
        """
        logger.info(f"[ClickHouse] 📊 开始查询所有行情数据...")
        logger.info(f"[ClickHouse] 📋 查询参数: side={side}, top_n={top_n} (已移除时间窗口限制)")
        
        # 构建查询SQL：去重，取每个symbol最新的event_time
        # 重要：只查询side字段不为空字符串的数据（side=''表示价格异步刷新服务还没刷新，没有涨跌数据）
        if side:
            if side == 'gainer':
                # 涨幅榜：查询price_change_percent>0且side不为空的合约，按price_change_percent降序排序
                where_clause = "price_change_percent > 0 AND side != '' AND side IS NOT NULL"
                order_by = "price_change_percent DESC"
                logger.info(f"[ClickHouse] 📈 涨幅榜查询: {where_clause}, 排序: {order_by}")
            else:  # loser
                # 跌幅榜：查询price_change_percent<0且side不为空的合约，按price_change_percent升序排序（跌幅最大的排在前面）
                where_clause = "price_change_percent < 0 AND side != '' AND side IS NOT NULL"
                order_by = "price_change_percent ASC"
                logger.info(f"[ClickHouse] 📉 跌幅榜查询: {where_clause}, 排序: {order_by}")
            
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
                    ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY event_time DESC) as rn
                FROM {self.market_ticker_table}
                WHERE {where_clause}
            ) AS ranked
            WHERE rn = 1
            ORDER BY {order_by}
            LIMIT {top_n}
            """
        else:
            # 查询所有，不区分涨跌，但只查询side字段不为空的数据
            query = f"""
            SELECT 
                event_time,
                symbol,
                price_change,
                price_change_percent,
                CASE 
                    WHEN price_change_percent > 0 THEN 'gainer' 
                    WHEN price_change_percent < 0 THEN 'loser' 
                    ELSE 'neutral' 
                END as side,
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
                    ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY event_time DESC) as rn
                FROM {self.market_ticker_table}
                WHERE side != '' AND side IS NOT NULL
            ) AS ranked
            WHERE rn = 1
            LIMIT {top_n * 2}
            """
        
        def _execute_query(client):
            return client.query(query)
        
        logger.info(f"[ClickHouse] 📝 执行查询: {query[:100]}...")
        result = self._with_connection(_execute_query)
        logger.info(f"[ClickHouse] ✅ 查询执行完成")
        
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
        
        # 调试日志：检查前3条数据的volume字段
        if rows and len(rows) > 0:
            for i, row_dict in enumerate(rows[:3]):
                logger.debug(
                    f"[ClickHouse] [查询结果 #{i+1}] Symbol: {row_dict.get('symbol')}, "
                    f"base_volume: {row_dict.get('base_volume')}, quote_volume: {row_dict.get('quote_volume')}"
                )
        
        logger.info(f"[ClickHouse] 📊 查询结果: 共 {len(rows)} 条数据")
        return rows

    def sync_leaderboard(
        self,
        time_window_seconds: int = 5,
        top_n: int = 10
    ) -> None:
        """Sync leaderboard data from market_ticker_table to leaderboard_table.
        
        核心功能：
        - 从24_market_tickers表查询所有市场数据（不限制时间窗口）
        - 对每个交易对取最新的行情数据（去重）
        - 计算每个合约的涨跌幅
        - 筛选出涨幅前N名和跌幅前N名
        - 使用全量更新方式更新futures_leaderboard表（临时表 + REPLACE TABLE）
        
        执行流程：
        1. 检查leaderboard表是否存在，不存在则创建
        2. 查询涨幅榜前N名（查询所有数据，按涨跌幅排序）
        3. 查询跌幅榜前N名（查询所有数据，按涨跌幅排序）
        4. 准备插入数据
        5. 创建临时表并插入数据
        6. 使用REPLACE TABLE原子替换原表（全量更新）
        7. 清理临时表
        
        Args:
            time_window_seconds: 已废弃，保留参数以兼容现有调用，不再使用时间窗口限制
            top_n: 涨跌幅前N名数量
        """
        try:
            logger.info(f"[ClickHouse] 🚀 开始涨跌幅榜同步...")
            logger.info(f"[ClickHouse] 📋 同步参数: top_n={top_n} (查询所有数据，不限制时间窗口)")
            
            # 重要：检查表是否存在，不存在则创建
            logger.info(f"[ClickHouse] 🔍 检查leaderboard表是否存在...")
            table_exists = self._check_table_exists(self.leaderboard_table)
            if not table_exists:
                logger.info(f"[ClickHouse] 📋 leaderboard表不存在，创建表...")
                self.ensure_leaderboard_table()
                logger.info(f"[ClickHouse] ✅ leaderboard表创建完成")
            else:
                logger.info(f"[ClickHouse] ✅ leaderboard表已存在")
            
            # 查询涨幅榜前N名（查询所有数据，按涨跌幅排序）
            logger.info(f"[ClickHouse] 🔍 查询涨幅榜前{top_n}名（从所有数据中排序）...")
            gainers = self.query_recent_tickers(
                time_window_seconds=time_window_seconds,
                side='gainer',
                top_n=top_n
            )
            logger.info(f"[ClickHouse] ✅ 涨幅榜查询完成，共 {len(gainers)} 条数据")
            
            # 查询跌幅榜前N名（查询所有数据，按涨跌幅排序）
            logger.info(f"[ClickHouse] 🔍 查询跌幅榜前{top_n}名（从所有数据中排序）...")
            losers = self.query_recent_tickers(
                time_window_seconds=time_window_seconds,
                side='loser',
                top_n=top_n
            )
            logger.info(f"[ClickHouse] ✅ 跌幅榜查询完成，共 {len(losers)} 条数据")
            
            # 重要：检查是否有有效数据（side字段不为空）
            # 如果涨幅榜和跌幅榜都没有数据，说明价格异步刷新服务还没刷新，此时不应该执行同步
            if not gainers and not losers:
                logger.warning(f"[ClickHouse] ⚠️ 涨幅榜和跌幅榜都没有数据（side字段为空），跳过同步操作")
                logger.warning(f"[ClickHouse] ⚠️ 这可能是因为价格异步刷新服务还没有刷新open_price，导致side字段为空字符串")
                return
            
            # 准备插入数据
            logger.info(f"[ClickHouse] 📝 准备插入数据...")
            all_rows = []
            column_names = [
                "event_time", "symbol", "price_change", "price_change_percent", "side",
                "change_percent_text", "average_price", "last_price", "last_trade_volume",
                "open_price", "high_price", "low_price", "base_volume", "quote_volume",
                "stats_open_time", "stats_close_time", "first_trade_id", "last_trade_id",
                "trade_count", "ingestion_time", "rank"
            ]
            
            # 添加涨幅榜数据（带排名）
            logger.info(f"[ClickHouse] 📊 处理涨幅榜数据...")
            for idx, row in enumerate(gainers, 1):
                symbol = row.get("symbol", "")
                base_volume_raw = row.get("base_volume")
                quote_volume_raw = row.get("quote_volume")
                
                # 调试日志：检查原始数据
                if idx <= 3:  # 只记录前3条，避免日志过多
                    logger.debug(
                        f"[ClickHouse] [涨幅榜 #{idx}] Symbol: {symbol}, "
                        f"base_volume_raw: {base_volume_raw}, quote_volume_raw: {quote_volume_raw}"
                    )
                
                row_data = [
                    _to_datetime(row.get("event_time")),  # DateTime
                    _normalize_field_value(row.get("symbol"), "String", "symbol"),  # String
                    _normalize_field_value(row.get("price_change"), "Float64", "price_change"),  # Float64
                    _normalize_field_value(row.get("price_change_percent"), "Float64", "price_change_percent"),  # Float64
                    _normalize_field_value(row.get("side", "gainer"), "String", "side"),  # String
                    _normalize_field_value(row.get("change_percent_text"), "String", "change_percent_text"),  # String
                    _normalize_field_value(row.get("average_price"), "Float64", "average_price"),  # Float64
                    _normalize_field_value(row.get("last_price"), "Float64", "last_price"),  # Float64
                    _normalize_field_value(row.get("last_trade_volume"), "Float64", "last_trade_volume"),  # Float64
                    _normalize_field_value(row.get("open_price"), "Float64", "open_price"),  # Float64
                    _normalize_field_value(row.get("high_price"), "Float64", "high_price"),  # Float64
                    _normalize_field_value(row.get("low_price"), "Float64", "low_price"),  # Float64
                    _normalize_field_value(base_volume_raw, "Float64", "base_volume"),  # Float64
                    _normalize_field_value(quote_volume_raw, "Float64", "quote_volume"),  # Float64
                    _to_datetime(row.get("stats_open_time")),  # DateTime
                    _to_datetime(row.get("stats_close_time")),  # DateTime
                    _normalize_field_value(row.get("first_trade_id"), "UInt64", "first_trade_id"),  # UInt64
                    _normalize_field_value(row.get("last_trade_id"), "UInt64", "last_trade_id"),  # UInt64
                    _normalize_field_value(row.get("trade_count"), "UInt64", "trade_count"),  # UInt64
                    _to_datetime(row.get("ingestion_time")),  # DateTime
                    _normalize_field_value(idx, "UInt8", "rank")  # UInt8 (rank)
                ]
                all_rows.append(row_data)
            logger.info(f"[ClickHouse] ✅ 涨幅榜数据处理完成，共 {len(gainers)} 条")
            
            # 添加跌幅榜数据（带排名）
            logger.info(f"[ClickHouse] 📊 处理跌幅榜数据...")
            for idx, row in enumerate(losers, 1):
                symbol = row.get("symbol", "")
                base_volume_raw = row.get("base_volume")
                quote_volume_raw = row.get("quote_volume")
                
                # 调试日志：检查原始数据
                if idx <= 3:  # 只记录前3条，避免日志过多
                    logger.debug(
                        f"[ClickHouse] [跌幅榜 #{idx}] Symbol: {symbol}, "
                        f"base_volume_raw: {base_volume_raw}, quote_volume_raw: {quote_volume_raw}"
                    )
                
                row_data = [
                    _to_datetime(row.get("event_time")),  # DateTime
                    _normalize_field_value(row.get("symbol"), "String", "symbol"),  # String
                    _normalize_field_value(row.get("price_change"), "Float64", "price_change"),  # Float64
                    _normalize_field_value(row.get("price_change_percent"), "Float64", "price_change_percent"),  # Float64
                    _normalize_field_value(row.get("side", "loser"), "String", "side"),  # String
                    _normalize_field_value(row.get("change_percent_text"), "String", "change_percent_text"),  # String
                    _normalize_field_value(row.get("average_price"), "Float64", "average_price"),  # Float64
                    _normalize_field_value(row.get("last_price"), "Float64", "last_price"),  # Float64
                    _normalize_field_value(row.get("last_trade_volume"), "Float64", "last_trade_volume"),  # Float64
                    _normalize_field_value(row.get("open_price"), "Float64", "open_price"),  # Float64
                    _normalize_field_value(row.get("high_price"), "Float64", "high_price"),  # Float64
                    _normalize_field_value(row.get("low_price"), "Float64", "low_price"),  # Float64
                    _normalize_field_value(base_volume_raw, "Float64", "base_volume"),  # Float64
                    _normalize_field_value(quote_volume_raw, "Float64", "quote_volume"),  # Float64
                    _to_datetime(row.get("stats_open_time")),  # DateTime
                    _to_datetime(row.get("stats_close_time")),  # DateTime
                    _normalize_field_value(row.get("first_trade_id"), "UInt64", "first_trade_id"),  # UInt64
                    _normalize_field_value(row.get("last_trade_id"), "UInt64", "last_trade_id"),  # UInt64
                    _normalize_field_value(row.get("trade_count"), "UInt64", "trade_count"),  # UInt64
                    _to_datetime(row.get("ingestion_time")),  # DateTime
                    _normalize_field_value(idx, "UInt8", "rank")  # UInt8 (rank)
                ]
                all_rows.append(row_data)
            logger.info(f"[ClickHouse] ✅ 跌幅榜数据处理完成，共 {len(losers)} 条")
            
            if all_rows:
                logger.info(f"[ClickHouse] 💾 准备全量更新数据到ClickHouse，共 {len(all_rows)} 条...")
                
                # 使用锁防止并发执行，避免表名冲突
                with ClickHouseDatabase._sync_leaderboard_lock:
                    # 使用时间戳生成唯一的临时表名，避免并发冲突
                    timestamp = int(datetime.now().timestamp() * 1000)  # 毫秒级时间戳
                    temp_table = f"{self.leaderboard_table}_temp_{timestamp}"
                    
                    try:
                        # 1. 创建临时表（结构与原表相同）
                        logger.info(f"[ClickHouse] 📋 创建临时表: {temp_table}")
                        # 先获取原表的结构
                        table_exists = self._check_table_exists(self.leaderboard_table)
                        if table_exists:
                            # 如果表存在，使用 AS 语法复制表结构
                            create_temp_sql = f"""
                            CREATE TABLE {temp_table}
                            ENGINE = MergeTree
                            ORDER BY (side, rank, symbol)
                            AS {self.leaderboard_table}
                            """
                        else:
                            # 如果表不存在，直接创建表（使用ensure_leaderboard_table的DDL）
                            create_temp_sql = f"""
                            CREATE TABLE {temp_table} (
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
                        self.command(create_temp_sql)
                        logger.info(f"[ClickHouse] ✅ 临时表创建完成")
                        
                        # 2. 插入数据到临时表
                        logger.info(f"[ClickHouse] 📥 插入数据到临时表...")
                        self.insert_rows(temp_table, all_rows, column_names)
                        logger.info(f"[ClickHouse] ✅ 数据插入完成，共 {len(all_rows)} 条")
                        
                        # 3. 使用RENAME TABLE原子替换原表（全量更新）
                        # ClickHouse的RENAME TABLE是原子操作，可以同时重命名多个表
                        # 如果原表存在，先备份原表，然后删除，再重命名临时表
                        logger.info(f"[ClickHouse] 🔄 执行全量更新（RENAME TABLE原子替换）...")
                        if table_exists:
                            # 生成备份表名
                            backup_table = f"{self.leaderboard_table}_backup_{timestamp}"
                            # 原子操作：先备份原表，再重命名临时表
                            rename_sql = f"""
                            RENAME TABLE 
                                {self.leaderboard_table} TO {backup_table},
                                {temp_table} TO {self.leaderboard_table}
                            """
                            self.command(rename_sql)
                            logger.info(f"[ClickHouse] ✅ 表重命名完成（原表已备份为: {backup_table}）")
                            
                            # 删除备份表（异步删除，不影响主流程）
                            try:
                                drop_backup_sql = f"DROP TABLE IF EXISTS {backup_table}"
                                self.command(drop_backup_sql)
                                logger.debug(f"[ClickHouse] 🧹 备份表已删除: {backup_table}")
                            except Exception as drop_exc:
                                logger.warning(f"[ClickHouse] ⚠️  删除备份表失败（可稍后手动清理）: {drop_exc}")
                        else:
                            # 如果原表不存在，直接重命名临时表
                            rename_sql = f"RENAME TABLE {temp_table} TO {self.leaderboard_table}"
                            self.command(rename_sql)
                            logger.info(f"[ClickHouse] ✅ 表重命名完成（新表创建）")
                        
                        logger.info(f"[ClickHouse] ✅ 全量更新完成")
                        
                        logger.info(
                            "[ClickHouse] 🎉 涨跌幅榜同步完成: %d 涨幅, %d 跌幅",
                            len(gainers), len(losers)
                        )
                    except Exception as e:
                        logger.error(f"[ClickHouse] ❌ 涨跌幅榜同步失败: {e}", exc_info=True)
                        # 如果失败，尝试清理临时表
                        try:
                            drop_temp_sql = f"DROP TABLE IF EXISTS {temp_table}"
                            self.command(drop_temp_sql)
                            logger.info(f"[ClickHouse] 🧹 临时表已清理: {temp_table}")
                        except Exception as cleanup_exc:
                            logger.warning(f"[ClickHouse] ⚠️  清理临时表失败: {cleanup_exc}")
                        raise
            else:
                logger.warning("[ClickHouse] ⚠️  没有涨跌幅榜数据可同步")
                
        except Exception as exc:
            logger.error("[ClickHouse] ❌ 涨跌幅榜同步失败: %s", exc, exc_info=True)

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
            
            def _execute_gainers_query(client):
                return client.query(gainers_query)
            
            def _execute_losers_query(client):
                return client.query(losers_query)
            
            gainers_result = self._with_connection(_execute_gainers_query)
            losers_result = self._with_connection(_execute_losers_query)
            
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
                        'quote_volume': float(row[5]) if len(row) > 5 and row[5] is not None else 0.0,
                        'rank': int(row[6]) if len(row) > 6 and row[6] is not None else 0
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
                        'quote_volume': float(row[5]) if len(row) > 5 and row[5] is not None else 0.0,
                        'rank': int(row[6]) if len(row) > 6 and row[6] is not None else 0
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
            
            def _execute_query(client):
                return client.query(query)
            
            result = self._with_connection(_execute_query)
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
    """将值转换为datetime对象，如果无法转换则返回当前UTC时间
    
    注意：此函数永远不会返回None，确保DateTime字段始终有值
    """
    if isinstance(value, datetime):
        return value
    if value is None:
        return datetime.now(timezone.utc)
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)

    seconds = numeric / 1000.0
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


def _normalize_field_value(value: Any, field_type: str, field_name: str = "") -> Any:
    """规范化字段值，确保符合ClickHouse字段类型要求
    
    Args:
        value: 原始值
        field_type: 字段类型 ('Float64', 'UInt64', 'UInt8', 'String', 'DateTime')
        field_name: 字段名称（用于日志）
        
    Returns:
        规范化后的值，确保不为None（除非字段类型允许）
    """
    if value is None:
        if field_type == 'Float64':
            return 0.0
        elif field_type == 'UInt64':
            return 0
        elif field_type == 'UInt8':
            return 0
        elif field_type == 'String':
            return ""
        elif field_type == 'DateTime':
            return datetime.now(timezone.utc)
        else:
            logger.warning(f"[ClickHouse] Unknown field type {field_type} for field {field_name}, using None")
            return None
    
    # 类型转换
    try:
        if field_type == 'Float64':
            return float(value)
        elif field_type == 'UInt64':
            return int(value)
        elif field_type == 'UInt8':
            return int(value)
        elif field_type == 'String':
            return str(value) if value else ""
        elif field_type == 'DateTime':
            return _to_datetime(value)
    except (TypeError, ValueError) as e:
        logger.warning(f"[ClickHouse] Failed to convert field {field_name} ({field_type}): {e}, using default")
        # 返回默认值
        if field_type == 'Float64':
            return 0.0
        elif field_type == 'UInt64':
            return 0
        elif field_type == 'UInt8':
            return 0
        elif field_type == 'String':
            return ""
        elif field_type == 'DateTime':
            return datetime.now(timezone.utc)
    
    return value


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
