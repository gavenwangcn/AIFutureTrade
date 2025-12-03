"""ClickHouse database utilities for market data storage."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from queue import Queue, Empty
from typing import Any, Dict, Iterable, List, Optional, Callable, Tuple

import clickhouse_connect
import common.config as app_config

MARKET_TICKER_TABLE = "24_market_tickers"
LEADERBOARD_TABLE = "futures_leaderboard"
MARKET_KLINES_TABLE = "market_klines"
MARKET_DATA_AGENT_TABLE = "market_data_agent"

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
        """初始化连接池，创建最小数量的连接。
        
        该方法在连接池初始化时调用，根据配置的最小连接数创建并添加连接到池中。
        """
        for _ in range(self._min_connections):
            self._create_connection()
    
    def _create_connection(self) -> Optional[Any]:
        """创建一个新的ClickHouse客户端连接。
        
        Returns:
            成功时返回ClickHouse客户端实例，失败或达到最大连接数时返回None
        """
        with self._lock:
            if self._current_connections >= self._max_connections:
                return None
            
            try:
                # 注意：不设置 timezone，因为某些 ClickHouse 服务器不支持或不允许设置该参数
                # 时区处理在应用层完成，所有时间都使用 UTC 时间戳（create_datetime_long）
                # 清理逻辑使用时间戳比较，不依赖时区设置
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
        if not client:
            return
        
        try:
            # Check if the client is still valid by sending a simple query
            # 使用超时和异常处理，避免长时间阻塞
            try:
                client.query("SELECT 1", settings={'max_execution_time': 2})
                self._pool.put(client)
                logger.debug(f"[ClickHouse] Released connection back to pool")
            except Exception as query_error:
                # 连接可能已损坏，尝试关闭它
                logger.warning(f"[ClickHouse] Connection health check failed: {query_error}, closing connection")
                try:
                    if hasattr(client, 'close'):
                        client.close()
                except Exception as close_error:
                    logger.debug(f"[ClickHouse] Error closing invalid connection: {close_error}")
                with self._lock:
                    self._current_connections -= 1
        except Exception as e:
            # 如果检查连接时发生其他错误，也关闭连接
            logger.error(f"[ClickHouse] Connection is invalid, closing it: {e}")
            try:
                if hasattr(client, 'close'):
                    client.close()
            except Exception as close_error:
                logger.debug(f"[ClickHouse] Error closing invalid connection: {close_error}")
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

    # ==================================================================
    # 初始化和连接管理
    # ==================================================================
    
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
        self.market_data_agent_table = MARKET_DATA_AGENT_TABLE

        # K线表前缀（默认 market_klines），按不同 interval 拆分为多张表：
        # market_klines_1w, market_klines_1d, market_klines_4h, market_klines_1h,
        # market_klines_15m, market_klines_5m, market_klines_1m
        self.market_klines_table: str = getattr(
            app_config,
            "CLICKHOUSE_MARKET_KLINES_TABLE",
            MARKET_KLINES_TABLE,
        )
        prefix = self.market_klines_table
        self.market_klines_tables: Dict[str, str] = {
            "1w": f"{prefix}_1w",
            "1d": f"{prefix}_1d",
            "4h": f"{prefix}_4h",
            "1h": f"{prefix}_1h",
            "15m": f"{prefix}_15m",
            "5m": f"{prefix}_5m",
            "1m": f"{prefix}_1m",
        }
        
        if auto_init_tables:
            # Initialize tables using the connection pool
            self.ensure_market_ticker_table()
            self.ensure_leaderboard_table()
            self.ensure_market_data_agent_table()
            self.ensure_market_klines_table()
    
    # ==================================================================
    # 连接管理方法
    # ==================================================================
    
    def _with_connection(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function with a ClickHouse connection from the pool.
        
        This method acquires a connection from the pool, executes the given function
        with the connection as the first argument, and then releases the connection back to the pool.
        
        支持自动重试机制，当遇到网络错误时会自动重试（最多3次）。
        
        Args:
            func: The function to execute
            *args: Positional arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function
            
        Returns:
            The result of the function call
            
        Raises:
            Exception: 如果重试3次后仍然失败，抛出最后一个异常
        """
        max_retries = 3
        retry_delay = 0.5  # 初始重试延迟（秒）
        
        for attempt in range(max_retries):
            client = None
            connection_acquired = False
            try:
                client = self._pool.acquire()
                if not client:
                    raise Exception("Failed to acquire ClickHouse connection")
                connection_acquired = True
                
                # 执行函数
                result = func(client, *args, **kwargs)
                
                # 成功执行，释放连接并返回结果
                self._pool.release(client)
                return result
                
            except Exception as e:
                # 记录错误信息
                error_type = type(e).__name__
                error_msg = str(e)
                
                # 判断是否为网络/协议错误，需要重试
                is_network_error = any(keyword in error_msg.lower() for keyword in [
                    'connection', 'broken', 'aborted', 'protocol', 'chunk', 
                    'badstatusline', 'invalidchunklength', 'timeout', 'reset',
                    'httperror', 'urlerror'
                ]) or any(keyword in error_type.lower() for keyword in [
                    'connection', 'protocol', 'timeout', 'httperror', 'urlerror'
                ])
                
                # 如果已获取连接，需要处理连接（关闭或释放）
                if connection_acquired and client:
                    try:
                        # 尝试关闭可能已损坏的连接
                        if hasattr(client, 'close'):
                            client.close()
                    except Exception as close_error:
                        logger.debug(f"[ClickHouse] Error closing failed connection: {close_error}")
                    # 减少连接计数（因为连接已损坏，不能放回池中）
                    with self._pool._lock:
                        if self._pool._current_connections > 0:
                            self._pool._current_connections -= 1
                
                # 判断是否需要重试
                if attempt < max_retries - 1:
                    # 计算等待时间（指数退避）
                    wait_time = retry_delay * (2 ** attempt)
                    
                    if is_network_error:
                        logger.warning(
                            f"[ClickHouse] Network/Protocol error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    else:
                        logger.warning(
                            f"[ClickHouse] Error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    
                    time.sleep(wait_time)
                    continue
                else:
                    # 最后一次尝试失败，抛出异常
                    logger.error(
                        f"[ClickHouse] Failed after {max_retries} attempts. Last error: {error_type}: {error_msg}"
                    )
                    raise

    # ==================================================================
    # 通用数据库操作方法
    # ==================================================================
    
    def command(self, sql: str) -> None:
        """执行原始SQL命令。
        
        Args:
            sql: 要执行的SQL命令字符串
        """
        def _execute_command(client):
            client.command(sql)
        
        self._with_connection(_execute_command)
    
    def query(self, sql: str) -> List[Tuple]:
        """执行查询并返回结果。
        
        注意：ClickHouse 的参数化查询支持有限，这里直接执行 SQL 字符串。
        所有参数都应该在调用前通过字符串格式化安全地嵌入到 SQL 中。
        
        Args:
            sql: 要执行的 SQL 查询字符串
            
        Returns:
            查询结果的行列表，每行是一个元组
        """
        def _execute_query(client):
            result = client.query(sql)
            return result.result_rows
        
        return self._with_connection(_execute_query)
    
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
        """向指定表中插入多行数据。
        
        Args:
            table: 目标表名
            rows: 要插入的数据行集合，每行是一个值的集合
            column_names: 列名列表，与数据行中的值一一对应
        """
        payload = list(rows)
        if not payload:
            return
        
        def _execute_insert(client):
            client.insert(table, payload, column_names=column_names)
            logger.debug("[ClickHouse] Inserted %s rows into %s", len(payload), table)
        
        self._with_connection(_execute_insert)

    # ==================================================================
    # Market Ticker 模块：表管理
    # ==================================================================
    
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

    # ==================================================================
    # Market Ticker 模块：数据查询
    # ==================================================================
    
    def get_existing_symbol_data(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """获取数据库中已存在交易对的最新数据，主要用于upsert操作时获取参考价格信息。
        
        功能说明：
        1. 批量查询指定交易对列表的最新行情记录
        2. 为每个交易对获取open_price、last_price和update_price_date字段
        3. 智能处理价格未设置的特殊情况
        4. 返回格式化的字典，方便upsert_market_tickers方法快速查找和使用
        
        查询逻辑：
        - 使用PARTITION BY和ROW_NUMBER()窗口函数为每个交易对筛选最新的一条记录
        - 按event_time降序排序，确保获取最新数据
        - 只查询指定的symbol列表，提高查询效率
        
        特殊处理：
        - 关键逻辑：如果open_price为0.0且update_price_date为None，视为"未设置"状态
        - 这种情况下返回open_price=None，而不是0.0，以保持原有业务逻辑的一致性
        
        错误处理：
        - 查询失败时返回空字典，确保调用方能够继续执行
        - 记录警告日志，便于排查问题
        
        Args:
            symbols: 需要查询的交易对列表，格式如["BTCUSDT", "ETHUSDT"]
            
        Returns:
            嵌套字典，格式为{symbol: {open_price: float, last_price: float, update_price_date: datetime}}
            示例: {"BTCUSDT": {"open_price": 35000.0, "last_price": 36000.0, "update_price_date": datetime(...)}}
            当交易对不存在或open_price未设置时，对应值可能为None
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

    # ==================================================================
    # Market Ticker 模块：数据插入和更新
    # ==================================================================
    
    def insert_market_tickers(self, rows: Iterable[Dict[str, Any]]) -> None:
        """插入市场行情数据到market_ticker表。
        
        此方法会对输入数据进行标准化处理，包括：
        1. 移除接口数据中的open_price和update_price_date字段（这两个字段只能由异步价格刷新服务更新）
        2. 确保日期时间字段格式正确
        3. 为Float64字段设置默认值0.0
        4. 为UInt64字段设置默认值0
        5. 为String字段设置默认值空字符串
        
        Args:
            rows: 市场行情数据字典的可迭代对象
        """
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
        """更新或插入市场行情数据（upsert操作）。
        
        功能说明：
        1. 筛选出以USDT结尾的交易对
        2. 对于同一批数据中的重复symbol，只保留最新的一条（基于stats_close_time）
        3. 查询数据库中已有的symbol数据，获取open_price信息
        4. 根据已有open_price计算涨跌幅相关字段
        5. 执行批量插入操作
        
        核心逻辑：
        - 首次插入时，price_change, price_change_percent, side, change_percent_text, open_price 都为空
        - 更新时，如果数据库中open_price有值，则通过last_price和open_price计算涨跌幅指标
        - 保留原有open_price和update_price_date，这两个字段只能由异步价格刷新服务更新
        
        数据处理：
        1. 规范化时间字段为datetime对象
        2. 移除接口数据中的open_price和update_price_date字段（保护机制）
        3. 智能处理重复数据，确保每个symbol只保留最新记录
        
        Args:
            rows: 市场行情数据的迭代器，每个元素是包含行情信息的字典
        
        Returns:
            None
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
    
    # ==================================================================
    # Market Ticker 模块：价格管理
    # ==================================================================
    
    def get_symbols_needing_price_refresh(self) -> List[str]:
        """获取需要刷新价格的symbol列表。
        
        查询条件：
        - update_price_date 为空
        - 或者 update_price_date 不为当天
        
        Returns:
            需要刷新价格的symbol列表（已去重并按字母顺序排序）
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
                _to_naive_datetime(update_date) if update_date else None  # update_price_date (Nullable(DateTime)) - 转换为naive datetime避免时区问题
            ]
            
            # 删除旧数据并插入新数据（ClickHouse的UPDATE方式）
            delete_query = f"ALTER TABLE {self.market_ticker_table} DELETE WHERE symbol = '{symbol}'"
            try:
                self.command(delete_query)
            except Exception as e:
                logger.warning("[ClickHouse] Failed to delete old row for %s: %s", symbol, e)
            
            # 插入更新后的数据
            self.insert_rows(self.market_ticker_table, [updated_row], column_names)
            
            # 记录时间转换信息，用于调试时区问题
            if update_date:
                naive_dt = _to_naive_datetime(update_date)
                logger.debug(
                    "[ClickHouse] Updated open_price for symbol %s: %s | update_price_date: %s (UTC) -> %s (naive, stored)",
                    symbol,
                    new_open_price,
                    update_date.strftime('%Y-%m-%d %H:%M:%S %Z') if hasattr(update_date, 'strftime') else str(update_date),
                    naive_dt.strftime('%Y-%m-%d %H:%M:%S')
                )
            else:
                logger.debug("[ClickHouse] Updated open_price for symbol %s: %s", symbol, new_open_price)
            
            return True
            
        except Exception as e:
            logger.error("[ClickHouse] Failed to update open_price for symbol %s: %s", symbol, e, exc_info=True)
            return False
    
    # ==================================================================
    # Leaderboard 模块：表管理
    # ==================================================================
    
    def ensure_leaderboard_table(self) -> None:
        """创建期货排行榜表（如果不存在）。
        
        表结构说明：
        - symbol: 交易对符号
        - price_change: 价格变化量
        - price_change_percent: 价格变化百分比
        - side: 涨跌方向（gainer/loser）
        - change_percent_text: 格式化的涨跌幅文本
        - last_price: 最新价格
        - rank: 排名(1-10等)
        - create_datetime: 创建时间
        - create_datetime_long: 毫秒级时间戳(用于批次标识)
        
        表使用MergeTree引擎，按(side, rank, symbol, create_datetime_long)排序，
        确保查询性能和数据组织的合理性。"""
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
            rank UInt8,
            create_datetime DateTime DEFAULT now(),
            create_datetime_long UInt64 DEFAULT 0
        )
        ENGINE = MergeTree
        ORDER BY (side, rank, symbol, create_datetime_long)
        """
        self.command(ddl)
        logger.debug("[ClickHouse] Ensured table %s exists", self.leaderboard_table)

    # ==================================================================
    # Leaderboard 模块：数据查询
    # ==================================================================
    
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
        logger.debug(f"[ClickHouse] 📊 开始查询所有行情数据...")
        logger.debug(f"[ClickHouse] 📋 查询参数: side={side}, top_n={top_n} (已移除时间窗口限制)")
        
        # 构建查询SQL：去重，取每个symbol最新的event_time
        # 重要：只查询side字段不为空字符串的数据（side=''表示价格异步刷新服务还没刷新，没有涨跌数据）
        if side:
            if side == 'gainer':
                # 涨幅榜：查询price_change_percent>0且side不为空的合约，按price_change_percent降序排序
                where_clause = "price_change_percent > 0 AND side != '' AND side IS NOT NULL"
                order_by = "price_change_percent DESC"
                logger.debug(f"[ClickHouse] 📈 涨幅榜查询: {where_clause}, 排序: {order_by}")
            else:  # loser
                # 跌幅榜：查询price_change_percent<0且side不为空的合约，按price_change_percent升序排序（跌幅最大的排在前面）
                where_clause = "price_change_percent < 0 AND side != '' AND side IS NOT NULL"
                order_by = "price_change_percent ASC"
                logger.debug(f"[ClickHouse] 📉 跌幅榜查询: {where_clause}, 排序: {order_by}")
            
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
        
        logger.debug(f"[ClickHouse] 📝 执行查询: {query[:100]}...")
        result = self._with_connection(_execute_query)
        logger.debug(f"[ClickHouse] ✅ 查询执行完成")
        
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
        
        logger.debug(f"[ClickHouse] 📊 查询结果: 共 {len(rows)} 条数据")
        return rows

    # ==================================================================
    # Leaderboard 模块：数据同步
    # ==================================================================
    
    def sync_leaderboard(
        self,
        time_window_seconds: int = 5,
        top_n: int = 10
    ) -> None:
        """Sync leaderboard data from market_ticker_table to leaderboard_table.
        
        核心功能：
        - 从24_market_tickers表查询所有市场数据(不限制时间窗口)
        - 对每个交易对取最新的行情数据(去重)
        - 计算每个合约的涨跌幅
        - 筛选出涨幅前N名和跌幅前N名
        - 使用全量更新方式更新futures_leaderboard表(临时表 + REPLACE TABLE)
        
        执行流程：
        1. 检查leaderboard表是否存在，不存在则创建
        2. 查询涨幅榜前N名(查询所有数据，按涨跌幅排序)
        3. 查询跌幅榜前N名(查询所有数据，按涨跌幅排序)
        4. 准备插入数据
        5. 创建临时表并插入数据
        6. 使用REPLACE TABLE原子替换原表(全量更新)
        7. 清理临时表
        
        Args:
            time_window_seconds: 已废弃，保留参数以兼容现有调用，不再使用时间窗口限制
            top_n: 涨跌幅前N名数量
        """
        try:
            logger.debug("[ClickHouse] 🚀 开始涨跌幅榜同步...")
            logger.debug("[ClickHouse] 📋 同步参数: top_n=%s (查询所有数据，不限制时间窗口)", top_n)
            
            # 重要：检查表是否存在，不存在则创建
            logger.debug("[ClickHouse] 🔍 检查leaderboard表是否存在...")
            table_exists = self._check_table_exists(self.leaderboard_table)
            if not table_exists:
                logger.debug("[ClickHouse] 📋 leaderboard表不存在，创建表...")
                self.ensure_leaderboard_table()
                logger.debug("[ClickHouse] ✅ leaderboard表创建完成")
            else:
                logger.debug("[ClickHouse] ✅ leaderboard表已存在")
            
            # 查询涨幅榜前N名（查询所有数据，按涨跌幅排序）
            logger.debug("[ClickHouse] 🔍 查询涨幅榜前%s名（从所有数据中排序）...", top_n)
            gainers = self.query_recent_tickers(
                time_window_seconds=time_window_seconds,
                side='gainer',
                top_n=top_n
            )
            logger.debug("[ClickHouse] ✅ 涨幅榜查询完成，共 %s 条数据", len(gainers))
            
            # 查询跌幅榜前N名（查询所有数据，按涨跌幅排序）
            logger.debug("[ClickHouse] 🔍 查询跌幅榜前%s名（从所有数据中排序）...", top_n)
            losers = self.query_recent_tickers(
                time_window_seconds=time_window_seconds,
                side='loser',
                top_n=top_n
            )
            logger.debug("[ClickHouse] ✅ 跌幅榜查询完成，共 %s 条数据", len(losers))
            
            # 重要：检查是否有有效数据（side字段不为空）
            # 如果涨幅榜和跌幅榜都没有数据，说明价格异步刷新服务还没刷新，此时不应该执行同步
            if not gainers and not losers:
                logger.warning("[ClickHouse] ⚠️ 涨幅榜和跌幅榜都没有数据（side字段为空），跳过同步操作")
                logger.warning("[ClickHouse] ⚠️ 这可能是因为价格异步刷新服务还没有刷新open_price，导致side字段为空字符串")
                return
            
            # 准备插入数据
            logger.debug("[ClickHouse] 📝 准备插入数据...")
            all_rows = []
            column_names = [
                "event_time", "symbol", "price_change", "price_change_percent", "side",
                "change_percent_text", "average_price", "last_price", "last_trade_volume",
                "open_price", "high_price", "low_price", "base_volume", "quote_volume",
                "stats_open_time", "stats_close_time", "first_trade_id", "last_trade_id",
                "trade_count", "ingestion_time", "rank", "create_datetime", "create_datetime_long"
            ]

            # 本次同步批次的唯一时间戳（整批插入使用相同的 create_datetime 和 create_datetime_long）
            batch_time = datetime.now(timezone.utc)
            # 生成毫秒级时间戳（UInt64），用于精确排序和查询最新批次
            batch_time_long = int(batch_time.timestamp() * 1000)
            
            # 记录时间戳信息，用于调试时区问题
            logger.debug(
                "[ClickHouse] 📅 批次时间戳 | UTC时间: %s | 时间戳(ms): %s | 本地时间: %s",
                batch_time.isoformat(),
                batch_time_long,
                batch_time.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z'),
            )
            
            # 添加涨幅榜数据（带排名）
            logger.debug("[ClickHouse] 📊 处理涨幅榜数据...")
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
                    _normalize_field_value(idx, "UInt8", "rank"),  # UInt8 (rank)
                    batch_time,  # create_datetime，同一批次使用相同时间
                    batch_time_long,  # create_datetime_long，同一批次使用相同的毫秒级时间戳
                ]
                all_rows.append(row_data)
            logger.debug("[ClickHouse] ✅ 涨幅榜数据处理完成，共 %s 条", len(gainers))
            
            # 添加跌幅榜数据（带排名）
            logger.debug("[ClickHouse] 📊 处理跌幅榜数据...")
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
                    _normalize_field_value(idx, "UInt8", "rank"),  # UInt8 (rank)
                    batch_time,  # create_datetime，同一批次使用相同时间
                    batch_time_long,  # create_datetime_long，同一批次使用相同的毫秒级时间戳
                ]
                all_rows.append(row_data)
            logger.debug("[ClickHouse] ✅ 跌幅榜数据处理完成，共 %s 条", len(losers))
            
            if all_rows:
                logger.debug("[ClickHouse] 💾 准备批量插入数据到ClickHouse，共 %s 条...", len(all_rows))

                # 使用锁防止并发执行插入，避免并发批次交织
                with ClickHouseDatabase._sync_leaderboard_lock:
                    # 直接使用 ClickHouse 批量插入，不再使用临时表/全量替换方案
                    self.insert_rows(self.leaderboard_table, all_rows, column_names)
                    logger.debug(
                        "[ClickHouse] ✅ 批量插入完成，本次批次时间戳: %s (create_datetime_long=%s), 涨幅: %d 条, 跌幅: %d 条",
                        batch_time.isoformat(),
                        batch_time_long,
                        len(gainers),
                        len(losers),
                    )
            else:
                logger.warning("[ClickHouse] ⚠️  没有涨跌幅榜数据可同步")
                
        except Exception as exc:
            logger.error("[ClickHouse] ❌ 涨跌幅榜同步失败: %s", exc, exc_info=True)

    def get_leaderboard(self, limit: int = 10) -> Dict[str, List[Dict]]:
        """获取最新批次的期货涨跌幅榜数据。
        
        使用create_datetime_long字段(数值型毫秒级时间戳)查询最新批次，
        避免create_datetime(秒级精度)导致同一秒多条数据无法区分的问题。
        
        实现原理：
        1. 通过子查询获取最大的create_datetime_long值(最新批次标识)
        2. 查询该批次的所有涨幅榜和跌幅榜数据
        3. 在内存中按涨跌幅排序并截取前N名
        4. 返回包含gainers和losers两个列表的字典
        
        Args:
            limit: 每个方向(涨幅/跌幅)返回的最大记录数
            
        Returns:
            包含'gainers'和'losers'两个列表的字典，每个列表包含格式化后的排行榜数据项
        """
        try:
            # 一条 SQL：先锁定最新批次的 create_datetime_long（数值型，毫秒级精度），再取该批次所有涨跌数据
            query = f"""
            SELECT
                symbol,
                last_price,
                price_change_percent,
                side,
                change_percent_text,
                quote_volume,
                rank,
                create_datetime_long
            FROM {self.leaderboard_table}
            WHERE create_datetime_long = (
                SELECT max(create_datetime_long) FROM {self.leaderboard_table}
            )
              AND side IN ('gainer', 'loser')
            """

            def _execute_query(client):
                return client.query(query)

            result = self._with_connection(_execute_query)
            rows = result.result_rows

            if not rows:
                logger.warning("[ClickHouse] get_leaderboard: futures_leaderboard 中没有数据")
                return {'gainers': [], 'losers': []}

            gainers: List[Dict] = []
            losers: List[Dict] = []

            # 先按 side 分类，再在内存中排序 + 截断前 N
            for row in rows:
                try:
                    side = str(row[3]) if row[3] else ''
                    item = {
                        'symbol': str(row[0]) if row[0] else '',
                        'price': float(row[1]) if row[1] is not None else 0.0,
                        'change_percent': float(row[2]) if row[2] is not None else 0.0,
                        'side': side or ('gainer' if (row[2] or 0) >= 0 else 'loser'),
                        'change_percent_text': str(row[4]) if row[4] else '',
                        'quote_volume': float(row[5]) if len(row) > 5 and row[5] is not None else 0.0,
                        'rank': int(row[6]) if len(row) > 6 and row[6] is not None else 0,
                    }

                    if item['side'] == 'gainer':
                        gainers.append(item)
                    elif item['side'] == 'loser':
                        losers.append(item)
                except (TypeError, ValueError, IndexError) as e:
                    logger.warning("[ClickHouse] Failed to parse leaderboard row: %s, error: %s", row, e)
                    continue

            # 在内存中按涨跌幅排序并截取前 N 名
            gainers.sort(key=lambda x: x.get('change_percent', 0.0), reverse=True)
            losers.sort(key=lambda x: x.get('change_percent', 0.0))  # 跌幅越小（更负）排越前

            gainers = gainers[: max(0, int(limit or 0))] if limit else gainers
            losers = losers[: max(0, int(limit or 0))] if limit else losers

            return {
                'gainers': gainers,
                'losers': losers,
            }
        except Exception as exc:
            logger.error("[ClickHouse] Failed to get leaderboard: %s", exc, exc_info=True)
            return {'gainers': [], 'losers': []}

    def get_leaderboard_symbols(self) -> List[str]:
        """获取排行榜中所有不同的交易对符号。
        
        从leaderboard表中查询所有非空的symbol字段，并进行去重处理。
        
        Returns:
            去重后的交易对符号列表
        """
        try:
            query = f"""
            SELECT symbol
            FROM {self.leaderboard_table}
            WHERE symbol != ''
            GROUP BY symbol
            """
            
            def _execute_query(client):
                return client.query(query)
            
            result = self._with_connection(_execute_query)
            symbols = [row[0] for row in result.result_rows if row[0]]
            return symbols
        except Exception as exc:
            logger.error("[ClickHouse] Failed to get leaderboard symbols: %s", exc, exc_info=True)
            return []
    
    def get_all_market_ticker_symbols(self) -> List[str]:
        """获取24_market_tickers表中所有不同的交易对符号。
        
        Returns:
            去重后的交易对符号列表
        """
        try:
            query = f"""
            SELECT DISTINCT symbol
            FROM {self.market_ticker_table}
            WHERE symbol != '' AND symbol LIKE '%USDT'
            ORDER BY symbol
            """
            
            def _execute_query(client):
                return client.query(query)
            
            result = self._with_connection(_execute_query)
            symbols = [row[0] for row in result.result_rows if row[0]]
            return symbols
        except Exception as exc:
            logger.error("[ClickHouse] Failed to get all market ticker symbols: %s", exc, exc_info=True)
            return []

    # ==================================================================
    # Leaderboard 模块：数据清理
    # ==================================================================
    
    def cleanup_old_leaderboard(self, minutes: int = 10) -> dict:
        """清理指定时间之前的旧排行榜数据。
        
        使用 create_datetime_long（数值型毫秒级时间戳）进行清理，避免 create_datetime（秒级精度）
        导致同一秒多条数据无法准确区分的问题。
        
        实现原理：
        1. 计算当前时间减去指定分钟数后的毫秒级时间戳作为截止时间
        2. 查询清理前的数据量统计
        3. 使用ALTER TABLE DELETE语句删除所有早于截止时间的记录
        4. 查询清理后的数据量统计
        5. 记录详细的清理日志并返回统计信息
        
        Args:
            minutes: 保留时间窗口（分钟），删除create_datetime_long早于当前时间该分钟数之前的数据
        
        Returns:
            包含清理统计信息的字典：
            - total_before: 清理前的总数据量
            - total_after: 清理后的总数据量（估算，因为DELETE是异步的）
            - to_delete_count: 待删除的数据量（估算）
            - cutoff_timestamp_ms: 截止时间戳
            - cutoff_time: 截止时间（字符串格式）
        """
        cleanup_start_time = time.time()
        stats = {
            'total_before': 0,
            'total_after': 0,
            'to_delete_count': 0,
            'cutoff_timestamp_ms': 0,
            'cutoff_time': '',
            'execution_time': 0.0
        }
        
        try:
            from datetime import datetime, timezone
            
            logger.debug("[ClickHouse] 🔧 初始化清理参数 | 保留时间: %s 分钟", minutes)
            
            # 计算当前时间减去指定分钟数后的毫秒级时间戳
            current_time = datetime.now(timezone.utc)
            cutoff_time = current_time
            cutoff_timestamp_ms = int((cutoff_time.timestamp() - minutes * 60) * 1000)
            cutoff_time_str = datetime.fromtimestamp(cutoff_timestamp_ms / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
            
            stats['cutoff_timestamp_ms'] = cutoff_timestamp_ms
            stats['cutoff_time'] = cutoff_time_str
            
            logger.debug(
                "[ClickHouse] ✅ 清理参数计算完成 | 截止时间戳(ms): %s | 截止时间: %s",
                cutoff_timestamp_ms,
                cutoff_time_str,
            )
            
            # 记录当前时间和截止时间的详细信息，用于调试时区问题
            logger.info(
                "[ClickHouse] 🧹 开始清理涨跌榜历史数据 | 保留时间: %s 分钟",
                minutes,
            )
            logger.info(
                "[ClickHouse] ⏰ 时间信息 | 当前UTC时间: %s | 截止UTC时间: %s | 截止时间戳(ms): %s",
                current_time.strftime('%Y-%m-%d %H:%M:%S UTC'),
                cutoff_time_str,
                cutoff_timestamp_ms,
            )
            
            # 查询数据库中的最新时间戳，用于对比
            try:
                max_timestamp_sql = f"SELECT max(create_datetime_long) FROM {self.leaderboard_table}"
                def _execute_max_timestamp(client):
                    result = client.query(max_timestamp_sql)
                    return result.result_rows[0][0] if result.result_rows and result.result_rows[0][0] else 0
                
                max_timestamp_in_db = self._with_connection(_execute_max_timestamp)
                if max_timestamp_in_db > 0:
                    max_time_in_db = datetime.fromtimestamp(max_timestamp_in_db / 1000, tz=timezone.utc)
                    time_diff_seconds = (max_timestamp_in_db - cutoff_timestamp_ms) / 1000
                    logger.info(
                        "[ClickHouse] 📊 数据库时间对比 | 数据库最新时间戳(ms): %s | 对应UTC时间: %s | 与截止时间差: %.1f 秒",
                        max_timestamp_in_db,
                        max_time_in_db.strftime('%Y-%m-%d %H:%M:%S UTC'),
                        time_diff_seconds,
                    )
            except Exception as e:
                logger.warning("[ClickHouse] ⚠️ 查询数据库最新时间戳时出错: %s", e)
            
            # 查询清理前的数据量统计
            try:
                count_before_sql = f"SELECT count() FROM {self.leaderboard_table}"
                count_to_delete_sql = f"SELECT count() FROM {self.leaderboard_table} WHERE create_datetime_long < {cutoff_timestamp_ms}"
                
                def _execute_count_before(client):
                    result = client.query(count_before_sql)
                    return result.result_rows[0][0] if result.result_rows else 0
                
                def _execute_count_to_delete(client):
                    result = client.query(count_to_delete_sql)
                    return result.result_rows[0][0] if result.result_rows else 0
                
                stats['total_before'] = self._with_connection(_execute_count_before)
                stats['to_delete_count'] = self._with_connection(_execute_count_to_delete)
                
                logger.info(
                    "[ClickHouse] 📊 清理前数据统计 | 总数据量: %s 条 | 待删除数据量: %s 条 | 保留数据量: %s 条",
                    stats['total_before'],
                    stats['to_delete_count'],
                    stats['total_before'] - stats['to_delete_count'],
                )
            except Exception as count_exc:
                logger.warning(
                    "[ClickHouse] ⚠️ 查询清理前数据量时出错: %s (继续执行清理)",
                    count_exc,
                )
            
            # 执行删除操作
            delete_sql = f"""
            ALTER TABLE {self.leaderboard_table}
            DELETE WHERE create_datetime_long < {cutoff_timestamp_ms}
            """
            
            logger.info("[ClickHouse] 🔨 执行删除操作...")
            logger.debug("[ClickHouse] 📝 DELETE SQL: %s", delete_sql.strip())
            
            try:
                self.command(delete_sql)
                logger.info("[ClickHouse] ✅ DELETE 操作已成功提交到 ClickHouse（异步执行）")
            except Exception as delete_exc:
                logger.error(
                    "[ClickHouse] ❌ DELETE 操作提交失败 | 错误: %s",
                    delete_exc,
                    exc_info=True,
                )
                raise  # 重新抛出异常，让上层处理
            
            # 查询清理后的数据量（由于DELETE是异步的，这里只是估算）
            try:
                # 等待一小段时间让DELETE操作开始执行
                logger.debug("[ClickHouse] ⏳ 等待 500ms 让 DELETE 操作开始执行...")
                time.sleep(0.5)  # 等待500ms
                
                def _execute_count_after(client):
                    result = client.query(count_before_sql)
                    return result.result_rows[0][0] if result.result_rows else 0
                
                stats['total_after'] = self._with_connection(_execute_count_after)
                logger.info(
                    "[ClickHouse] 📊 清理后数据量查询完成 | 当前数据量: %s 条（注意：DELETE 是异步的，实际删除可能尚未完成）",
                    stats['total_after'],
                )
            except Exception as count_after_exc:
                logger.warning(
                    "[ClickHouse] ⚠️ 查询清理后数据量时出错: %s (使用估算值)",
                    count_after_exc,
                )
                # 估算清理后的数据量
                stats['total_after'] = stats['total_before'] - stats['to_delete_count']
                logger.info(
                    "[ClickHouse] 📊 使用估算值 | 清理后数据量(估算): %s 条",
                    stats['total_after'],
                )
            
            cleanup_end_time = time.time()
            stats['execution_time'] = cleanup_end_time - cleanup_start_time
            
            # 记录详细的清理结果日志
            logger.info(
                "[ClickHouse] ✅ 清理操作已完成 | 执行时间: %.3f 秒 | 清理前: %s 条 | 待删除: %s 条 | 清理后(估算): %s 条",
                stats['execution_time'],
                stats['total_before'],
                stats['to_delete_count'],
                stats['total_after'],
            )
            
            # 如果待删除的数据量很大，记录警告
            if stats['to_delete_count'] > 100000:
                logger.warning(
                    "[ClickHouse] ⚠️ 待删除数据量较大: %s 条，可能需要较长时间完成删除操作",
                    stats['to_delete_count'],
                )
            
            # 如果清理后数据量仍然很大，记录警告
            if stats['total_after'] > 50000:
                logger.warning(
                    "[ClickHouse] ⚠️ 清理后数据量仍然较大: %s 条，建议检查数据插入频率或调整保留时间",
                    stats['total_after'],
                )
            
            return stats
            
        except Exception as exc:
            cleanup_end_time = time.time()
            stats['execution_time'] = cleanup_end_time - cleanup_start_time
            logger.error(
                "[ClickHouse] ❌ 清理涨跌榜历史数据失败 | 执行时间: %.3f 秒 | 错误: %s",
                stats['execution_time'],
                exc,
                exc_info=True,
            )
            return stats

    # ==================================================================
    # Market Klines 模块：表管理
    # ==================================================================
    
    def ensure_market_klines_table(self) -> None:
        """Create per-interval market_klines tables if they do not exist.

        拆分原来的单表 market_klines 为 7 张按 interval 划分的表：
        - market_klines_1w, market_klines_1d, market_klines_4h, market_klines_1h,
          market_klines_15m, market_klines_5m, market_klines_1m
        """
        for interval, table_name in self.market_klines_tables.items():
            ddl = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
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
            logger.info("[ClickHouse] Ensured kline table %s (interval=%s) exists", table_name, interval)

    # ==================================================================
    # Market Klines 模块：数据插入
    # ==================================================================
    
    def insert_market_klines(self, rows: Iterable[Dict[str, Any]]) -> None:
        """将K线数据插入到按时间间隔划分的market_klines表中。
        
        功能说明：
        1. 将K线数据按时间间隔（interval）归类到对应的表中
        2. 支持7种时间间隔：1w, 1d, 4h, 1h, 15m, 5m, 1m
        3. 对每条数据进行字段标准化处理
        4. 按不同时间间隔表进行批量插入
        
        Args:
            rows: K线数据字典的可迭代对象，每条数据包含event_time、symbol、interval等字段
        """
        rows = list(rows)
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

        # 按 interval 归类到对应的表
        bucketed: Dict[str, List[Tuple[Any, ...]]] = {}
        for row in rows:
            interval = (row.get("interval") or "").strip()
            table_name = self.market_klines_tables.get(interval)
            if not table_name:
                logger.debug(
                    "[ClickHouse] Skip kline row with unsupported interval: %s (row=%s)",
                    interval,
                    row,
                )
                continue

            values = (
                row.get("event_time"),
                row.get("symbol", ""),
                row.get("contract_type", ""),
                row.get("kline_start_time"),
                row.get("kline_end_time"),
                interval,
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
            )
            bucketed.setdefault(table_name, []).append(values)

        # 批量写入各 interval 对应的表
        for table_name, payload in bucketed.items():
            if not payload:
                continue
            self.insert_rows(table_name, payload, column_names)
            logger.debug(
                "[ClickHouse] Inserted %s kline rows into %s",
                len(payload),
                table_name,
            )

    # ==================================================================
    # Market Klines 模块：数据查询
    # ==================================================================
    
    def get_market_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """查询K线数据
        
        Args:
            symbol: 交易对符号（如 'BTCUSDT'）
            interval: 时间间隔（'1m', '5m', '15m', '1h', '4h', '1d', '1w'）
            limit: 返回的最大记录数，默认500
            start_time: 开始时间（可选）
            end_time: 结束时间（可选）
            
        Returns:
            K线数据列表，每条数据包含：
            - timestamp: 时间戳（毫秒）
            - open: 开盘价
            - high: 最高价
            - low: 最低价
            - close: 收盘价
            - volume: 成交量
            - turnover: 成交额
            - buyVolume: 买入成交量
            - buyTurnover: 买入成交额
        """
        table_name = self.market_klines_tables.get(interval)
        if not table_name:
            logger.warning(f"[ClickHouse] Unsupported interval: {interval}")
            return []
        
        try:
            # 构建查询SQL
            where_conditions = [f"symbol = '{symbol.upper()}'"]
            
            if start_time:
                where_conditions.append(f"kline_end_time >= '{start_time.strftime('%Y-%m-%d %H:%M:%S')}'")
            if end_time:
                where_conditions.append(f"kline_end_time <= '{end_time.strftime('%Y-%m-%d %H:%M:%S')}'")
            
            where_clause = " AND ".join(where_conditions)
            
            query = f"""
            SELECT 
                toUnixTimestamp(kline_end_time) * 1000 as timestamp,
                open_price as open,
                high_price as high,
                low_price as low,
                close_price as close,
                base_volume as volume,
                quote_volume as turnover,
                taker_buy_base_volume as buyVolume,
                taker_buy_quote_volume as buyTurnover
            FROM {table_name}
            WHERE {where_clause}
            ORDER BY kline_end_time ASC
            LIMIT {limit}
            """
            
            result = self.query(query)
            
            # 转换为字典列表
            klines = []
            for row in result:
                klines.append({
                    'timestamp': int(row[0]),
                    'open': float(row[1]),
                    'high': float(row[2]),
                    'low': float(row[3]),
                    'close': float(row[4]),
                    'volume': float(row[5]),
                    'turnover': float(row[6]),
                    'buyVolume': float(row[7]),
                    'buyTurnover': float(row[8])
                })
            
            logger.debug(f"[ClickHouse] Retrieved {len(klines)} klines for {symbol} {interval}")
            return klines
            
        except Exception as exc:
            logger.error(f"[ClickHouse] Failed to get klines: {exc}", exc_info=True)
            return []
    
    # ==================================================================
    # Market Klines 模块：数据清理
    # ==================================================================
    
    def cleanup_old_klines(self, days: int = 2) -> int:
        """清理指定天数之前的旧K线数据。
        
        功能说明：
        1. 遍历所有时间间隔的K线表（1w, 1d, 4h, 1h, 15m, 5m, 1m）
        2. 对每个表执行ALTER TABLE DELETE操作，删除超过指定天数的数据
        3. 记录清理操作日志
        
        注意：ClickHouse的DELETE操作是异步执行的，所以无法立即获取删除的具体行数
        
        Args:
            days: 保留天数，删除kline_end_time早于当前时间减去该天数的数据
            
        Returns:
            由于是异步操作，返回0表示删除任务已提交
        """
        try:
            # ClickHouse DELETE requires mutations, use ALTER TABLE DELETE
            for interval, table_name in self.market_klines_tables.items():
                delete_sql = f"""
                ALTER TABLE {table_name}
                DELETE WHERE kline_end_time < now() - INTERVAL {days} DAY
                """
                self.command(delete_sql)
                logger.info(
                    "[ClickHouse] Initiated cleanup of klines older than %s days for %s (interval=%s)",
                    days,
                    table_name,
                    interval,
                )
            # Note: ClickHouse DELETE is asynchronous, we can't get exact count immediately
            return 0  # ClickHouse doesn't return count for async DELETE
        except Exception as exc:
            logger.error("[ClickHouse] Failed to cleanup old klines: %s", exc, exc_info=True)
            return 0
    
    # ==================================================================
    # Market Data Agent 模块：表管理
    # ==================================================================
    
    def ensure_market_data_agent_table(self) -> None:
        """创建market_data_agent表（如果不存在）。
        
        表结构：
        - ip: String - data_agent的IP地址
        - port: UInt16 - data_agent的端口号
        - status: String - 状态（online/offline）
        - connection_count: UInt32 - 当前使用的长链接数量
        - assigned_symbol_count: UInt32 - 已分配的合约数量
        - assigned_symbols: String - 已分配的合约列表（JSON格式）
        - error_log: String - 异常日志
        - last_heartbeat: DateTime - 最后心跳时间
        - register_time: DateTime - 注册时间
        - update_time: DateTime - 更新时间
        """
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {self.market_data_agent_table} (
            ip String,
            port UInt16,
            status String,
            connection_count UInt32,
            assigned_symbol_count UInt32,
            assigned_symbols String,
            error_log String,
            last_heartbeat DateTime,
            register_time DateTime DEFAULT now(),
            update_time DateTime DEFAULT now()
        )
        ENGINE = ReplacingMergeTree(update_time)
        ORDER BY (ip, port)
        PRIMARY KEY (ip, port)
        """
        self.command(ddl)
        logger.info("[ClickHouse] Ensured table %s exists", self.market_data_agent_table)
    
    def upsert_market_data_agent(self, agent_data: Dict[str, Any]) -> None:
        """更新或插入data_agent信息。
        
        Args:
            agent_data: 包含agent信息的字典，必须包含ip和port字段
        """
        import json
        from datetime import datetime, timezone
        
        ip = agent_data.get("ip", "")
        port = agent_data.get("port", 0)
        status = agent_data.get("status", "offline")
        connection_count = agent_data.get("connection_count", 0)
        assigned_symbol_count = agent_data.get("assigned_symbol_count", 0)
        assigned_symbols = agent_data.get("assigned_symbols", [])
        error_log = agent_data.get("error_log", "")
        last_heartbeat = agent_data.get("last_heartbeat")
        
        if not ip or port == 0:
            logger.warning("[ClickHouse] Invalid agent data: missing ip or port")
            return
        
        # 转换assigned_symbols为JSON字符串
        assigned_symbols_json = json.dumps(assigned_symbols, ensure_ascii=False)
        
        # 处理时间字段
        if isinstance(last_heartbeat, (int, float)):
            last_heartbeat = datetime.fromtimestamp(last_heartbeat, tz=timezone.utc)
        elif not isinstance(last_heartbeat, datetime):
            last_heartbeat = datetime.now(timezone.utc)
        
        update_time = datetime.now(timezone.utc)
        
        try:
            # 检查是否已存在该IP+port的记录
            check_query = f"SELECT count() FROM {self.market_data_agent_table} WHERE ip = '{ip}' AND port = {port}"
            result = self.query(check_query)
            exists = result and result[0] and int(result[0][0]) > 0
            
            if exists:
                # IP+port已存在，执行UPDATE操作
                update_query = f"""
                ALTER TABLE {self.market_data_agent_table} UPDATE 
                    status = '{status}', 
                    connection_count = {connection_count}, 
                    assigned_symbol_count = {assigned_symbol_count}, 
                    assigned_symbols = '{assigned_symbols_json}', 
                    error_log = '{error_log}', 
                    last_heartbeat = '{last_heartbeat.strftime('%Y-%m-%d %H:%M:%S')}', 
                    update_time = '{update_time.strftime('%Y-%m-%d %H:%M:%S')}' 
                WHERE ip = '{ip}' AND port = {port}
                """
                self.command(update_query)
                logger.debug("[ClickHouse] Updated agent: %s:%s", ip, port)
            else:
                # IP+port不存在，执行INSERT操作
                column_names = [
                    "ip", "port", "status", "connection_count", "assigned_symbol_count",
                    "assigned_symbols", "error_log", "last_heartbeat", "update_time"
                ]
                
                row_data = [
                    ip, port, status, connection_count, assigned_symbol_count,
                    assigned_symbols_json, error_log, last_heartbeat, update_time
                ]
                
                self.insert_rows(self.market_data_agent_table, [row_data], column_names)
                logger.debug("[ClickHouse] Inserted agent: %s:%s", ip, port)
            
            # 执行OPTIMIZE TABLE，确保数据实时一致性
            optimize_query = f"OPTIMIZE TABLE {self.market_data_agent_table} FINAL"
            self.command(optimize_query)
            logger.debug("[ClickHouse] Optimized table %s", self.market_data_agent_table)
                
        except Exception as e:
            logger.error("[ClickHouse] Failed to upsert agent %s:%s: %s", ip, port, e, exc_info=True)
    
    def get_market_data_agents(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取所有data_agent信息。
        
        Args:
            status: 可选，过滤状态（online/offline）
        
        Returns:
            data_agent信息列表
        """
        import json
        
        try:
            query = f"""
            SELECT 
                ip, port, status, connection_count, assigned_symbol_count,
                assigned_symbols, error_log, last_heartbeat, register_time, update_time
            FROM {self.market_data_agent_table}
            """
            if status:
                query += f" WHERE status = '{status}'"
            query += " ORDER BY ip, port"
            
            def _execute_query(client):
                return client.query(query)
            
            result = self._with_connection(_execute_query)
            agents = []
            for row in result.result_rows:
                try:
                    assigned_symbols = json.loads(row[5]) if row[5] else []
                except (json.JSONDecodeError, TypeError):
                    assigned_symbols = []
                
                agents.append({
                    "ip": row[0],
                    "port": row[1],
                    "status": row[2],
                    "connection_count": row[3],
                    "assigned_symbol_count": row[4],
                    "assigned_symbols": assigned_symbols,
                    "error_log": row[6] or "",
                    "last_heartbeat": row[7],
                    "register_time": row[8],
                    "update_time": row[9],
                })
            return agents
        except Exception as exc:
            logger.error("[ClickHouse] Failed to get market data agents: %s", exc, exc_info=True)
            return []
    
    def get_market_data_agent(self, ip: str, port: int) -> Optional[Dict[str, Any]]:
        """获取指定data_agent信息。
        
        Args:
            ip: agent的IP地址
            port: agent的端口号
        
        Returns:
            agent信息字典，如果不存在则返回None
        """
        import json
        
        try:
            query = f"""
            SELECT 
                ip, port, status, connection_count, assigned_symbol_count,
                assigned_symbols, error_log, last_heartbeat, register_time, update_time
            FROM {self.market_data_agent_table}
            WHERE ip = '{ip}' AND port = {port}
            ORDER BY update_time DESC
            LIMIT 1
            """
            
            def _execute_query(client):
                return client.query(query)
            
            result = self._with_connection(_execute_query)
            if not result.result_rows:
                return None
            
            row = result.result_rows[0]
            try:
                assigned_symbols = json.loads(row[5]) if row[5] else []
            except (json.JSONDecodeError, TypeError):
                assigned_symbols = []
            
            return {
                "ip": row[0],
                "port": row[1],
                "status": row[2],
                "connection_count": row[3],
                "assigned_symbol_count": row[4],
                "assigned_symbols": assigned_symbols,
                "error_log": row[6] or "",
                "last_heartbeat": row[7],
                "register_time": row[8],
                "update_time": row[9],
            }
        except Exception as exc:
            logger.error("[ClickHouse] Failed to get market data agent: %s", exc, exc_info=True)
            return None


# ==================================================================
# 辅助函数
# ==================================================================

def _to_datetime(value: Any) -> datetime:
    """将值转换为datetime对象，如果无法转换则返回当前UTC时间。
    
    支持的输入类型：
    - datetime对象：直接返回
    - None：返回当前UTC时间
    - 时间戳（整数或浮点数）：自动转换为datetime对象
    - 其他类型：尝试转换为浮点数作为时间戳，失败则返回当前UTC时间
    
    注意：此函数永远不会返回None，确保DateTime字段始终有值
    
    Args:
        value: 需要转换的值
        
    Returns:
        datetime对象，确保有值且带时区信息(UTC)
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


def _to_naive_datetime(value: Any) -> datetime:
    """将datetime对象转换为naive datetime（移除时区信息），用于ClickHouse存储。
    
    ClickHouse的DateTime类型不存储时区信息，如果传入带时区的datetime对象，
    clickhouse_connect库可能会根据服务器时区进行转换，导致时间偏移。
    
    此函数确保：
    1. 如果输入是带时区的datetime（如UTC），先转换为UTC时间，再移除时区信息
    2. 如果输入是naive datetime，直接返回
    3. 如果输入是None，返回当前UTC时间的naive版本
    
    Args:
        value: datetime对象或None
        
    Returns:
        naive datetime对象（无时区信息），时间值为UTC时间
    """
    if value is None:
        # 返回当前UTC时间的naive版本
        return datetime.utcnow()
    
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            # 带时区的datetime，转换为UTC后再移除时区信息
            utc_time = value.astimezone(timezone.utc)
            return utc_time.replace(tzinfo=None)
        else:
            # 已经是naive datetime，直接返回
            return value
    
    # 如果不是datetime对象，尝试转换
    dt = _to_datetime(value)
    if dt.tzinfo is not None:
        utc_time = dt.astimezone(timezone.utc)
        return utc_time.replace(tzinfo=None)
    return dt


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
    """根据涨跌幅百分比确定涨跌方向。
    
    Args:
        percent: 涨跌幅百分比值
        
    Returns:
        "gainer"表示上涨，"loser"表示下跌
    """
    try:
        value = float(percent)
    except (TypeError, ValueError):
        value = 0.0
    return "loser" if value < 0 else "gainer"


def _format_percent_text(percent: Any) -> str:
    """将涨跌幅百分比格式化为字符串，保留两位小数。
    
    Args:
        percent: 涨跌幅百分比值
        
    Returns:
        格式化后的百分比字符串，如"5.25%"
    """
    try:
        value = float(percent)
    except (TypeError, ValueError):
        value = 0.0
    return f"{value:.2f}%"
