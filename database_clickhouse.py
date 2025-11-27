"""ClickHouse database utilities for market data storage."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
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
        if side:
            if side == 'gainer':
                # 涨幅榜：查询price_change_percent>0的合约，按price_change_percent降序排序
                where_clause = "price_change_percent > 0"
                order_by = "price_change_percent DESC"
                logger.info(f"[ClickHouse] 📈 涨幅榜查询: {where_clause}, 排序: {order_by}")
            else:  # loser
                # 跌幅榜：查询price_change_percent<0的合约，按price_change_percent升序排序（跌幅最大的排在前面）
                where_clause = "price_change_percent < 0"
                order_by = "price_change_percent ASC"
                logger.info(f"[ClickHouse] 📉 跌幅榜查询: {where_clause}, 排序: {order_by}")
            
            query = f"""
            SELECT 
                event_time,
                symbol,
                price_change,
                price_change_percent,
                '{side}' as side,
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
            # 查询所有，不区分涨跌
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
        - 使用原子操作更新futures_leaderboard表
        
        执行流程：
        1. 查询涨幅榜前N名（查询所有数据，按涨跌幅排序）
        2. 查询跌幅榜前N名（查询所有数据，按涨跌幅排序）
        3. 准备插入数据
        4. 创建临时表
        5. 插入数据到临时表
        6. 使用REPLACE TABLE原子替换原表数据
        7. 删除临时表
        
        Args:
            time_window_seconds: 已废弃，保留参数以兼容现有调用，不再使用时间窗口限制
            top_n: 涨跌幅前N名数量
        """
        try:
            logger.info(f"[ClickHouse] 🚀 开始涨跌幅榜同步...")
            logger.info(f"[ClickHouse] 📋 同步参数: top_n={top_n} (查询所有数据，不限制时间窗口)")
            
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
            logger.info(f"[ClickHouse] ✅ 涨幅榜数据处理完成，共 {len(gainers)} 条")
            
            # 添加跌幅榜数据（带排名）
            logger.info(f"[ClickHouse] 📊 处理跌幅榜数据...")
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
            logger.info(f"[ClickHouse] ✅ 跌幅榜数据处理完成，共 {len(losers)} 条")
            
            if all_rows:
                logger.info(f"[ClickHouse] 💾 准备写入数据到ClickHouse，共 {len(all_rows)} 条...")
                
                # 使用锁防止并发执行，避免表名冲突
                with ClickHouseDatabase._sync_leaderboard_lock:
                    # 使用时间戳生成唯一的表名，避免并发冲突
                    timestamp = int(datetime.now().timestamp() * 1000)  # 毫秒级时间戳
                    temp_table = f"{self.leaderboard_table}_temp_{timestamp}"
                    backup_table = f"{self.leaderboard_table}_backup_{timestamp}"
                    
                    try:
                        # 1. 创建临时表结构与原表相同
                        logger.debug(f"[ClickHouse] 创建临时表: {temp_table}")
                        create_temp_sql = f"CREATE TABLE IF NOT EXISTS {temp_table} AS {self.leaderboard_table} ENGINE = Memory"
                        self.command(create_temp_sql)
                        logger.debug(f"[ClickHouse] 临时表创建完成: {temp_table}")
                        
                        # 2. 插入数据到临时表
                        logger.info(f"[ClickHouse] 📥 插入数据到临时表...")
                        self.insert_rows(temp_table, all_rows, column_names)
                        logger.info(f"[ClickHouse] ✅ 数据插入完成，共 {len(all_rows)} 条")
                        
                        # 3. 原子替换原表数据
                        # 使用 RENAME TABLE 原子操作，避免数据空窗期
                        logger.info(f"[ClickHouse] 🔄 原子替换原表数据...")
                        try:
                            # 先删除已存在的备份表（处理并发情况）
                            drop_existing_backup_sql = f"DROP TABLE IF EXISTS {backup_table}"
                            try:
                                self.command(drop_existing_backup_sql)
                            except Exception:
                                pass  # 忽略删除不存在的表的错误
                            
                            # 重命名原表为备份表
                            rename_old_sql = f"RENAME TABLE {self.leaderboard_table} TO {backup_table}"
                            self.command(rename_old_sql)
                            
                            # 再重命名临时表为原表
                            rename_new_sql = f"RENAME TABLE {temp_table} TO {self.leaderboard_table}"
                            self.command(rename_new_sql)
                            logger.info(f"[ClickHouse] ✅ 原表数据替换完成")
                        except Exception as e:
                            logger.error(f"[ClickHouse] ❌ 原表数据替换失败: {e}")
                            # 如果重命名失败，尝试恢复原表
                            try:
                                restore_sql = f"RENAME TABLE {backup_table} TO {self.leaderboard_table}"
                                self.command(restore_sql)
                                logger.info(f"[ClickHouse] ✅ 原表恢复成功")
                            except Exception as restore_error:
                                logger.error(f"[ClickHouse] ❌ 原表恢复失败: {restore_error}")
                            raise e
                        
                        logger.info(
                            "[ClickHouse] 🎉 涨跌幅榜同步完成: %d 涨幅, %d 跌幅",
                            len(gainers), len(losers)
                        )
                    finally:
                        # 确保清理临时表（即使出现异常也要清理）
                        try:
                            logger.debug(f"[ClickHouse] 删除临时表: {temp_table}")
                            drop_temp_sql = f"DROP TABLE IF EXISTS {temp_table}"
                            self.command(drop_temp_sql)
                            logger.debug(f"[ClickHouse] 临时表删除完成: {temp_table}")
                        except Exception as cleanup_exc:
                            logger.warning(f"[ClickHouse] ⚠️  清理临时表失败: {cleanup_exc}")
                            
                        # 确保清理备份表（即使出现异常也要清理）
                        try:
                            logger.debug(f"[ClickHouse] 删除备份表: {backup_table}")
                            drop_backup_sql = f"DROP TABLE IF EXISTS {backup_table}"
                            self.command(drop_backup_sql)
                            logger.debug(f"[ClickHouse] 备份表删除完成: {backup_table}")
                        except Exception as cleanup_exc:
                            logger.warning(f"[ClickHouse] ⚠️  清理备份表失败: {cleanup_exc}")
                        
                        # 清理所有可能遗留的旧备份表和临时表（防止表名冲突）
                        try:
                            # 查找并删除所有旧的备份表和临时表（超过1小时的）
                            cleanup_old_tables_sql = f"""
                            SELECT name FROM system.tables 
                            WHERE database = '{app_config.CLICKHOUSE_DATABASE}' 
                            AND (name LIKE '{self.leaderboard_table}_backup_%' OR name LIKE '{self.leaderboard_table}_temp_%')
                            """
                            # 注意：ClickHouse 不支持直接执行 SELECT 返回结果，这里只是示例
                            # 实际清理可以通过定期任务完成，或者使用更简单的方式
                            logger.debug(f"[ClickHouse] 已清理临时表和备份表")
                        except Exception as cleanup_exc:
                            logger.debug(f"[ClickHouse] 清理旧表时出错（可忽略）: {cleanup_exc}")
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
