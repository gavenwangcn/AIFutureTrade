"""MySQL database utilities for market data storage."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from queue import Queue, Empty
from typing import Any, Dict, Iterable, List, Optional, Callable, Tuple
import pymysql
from pymysql import cursors
import common.config as app_config

MARKET_TICKER_TABLE = "24_market_tickers"
LEADERBOARD_TABLE = "futures_leaderboard"
MARKET_KLINES_TABLE = "market_klines"
MARKET_DATA_AGENT_TABLE = "market_data_agent"

logger = logging.getLogger(__name__)


class MySQLConnectionPool:
    """MySQL connection pool to manage database connections.
    
    This class manages a pool of MySQL connections to avoid creating
    too many connections to the MySQL server. It provides methods to acquire
    and release connections, and supports dynamic expansion up to a maximum
    number of connections.
    """
    
    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        charset: str = 'utf8mb4',
        min_connections: int = 5,
        max_connections: int = 20,
        connection_timeout: int = 30
    ):
        """Initialize the connection pool.
        
        Args:
            host: MySQL host
            port: MySQL port
            user: MySQL username
            password: MySQL password
            database: MySQL database name
            charset: Character set, default utf8mb4
            min_connections: Minimum number of connections to keep in the pool
            max_connections: Maximum number of connections allowed in the pool
            connection_timeout: Timeout for acquiring a connection (seconds)
        """
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._database = database
        self._charset = charset
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
        """创建一个新的MySQL连接。
        
        Returns:
            成功时返回MySQL连接实例，失败或达到最大连接数时返回None
        """
        with self._lock:
            if self._current_connections >= self._max_connections:
                return None
            
            try:
                connection = pymysql.connect(
                    host=self._host,
                    port=self._port,
                    user=self._user,
                    password=self._password,
                    database=self._database,
                    charset=self._charset,
                    cursorclass=cursors.DictCursor,
                    autocommit=False
                )
                self._pool.put(connection)
                self._current_connections += 1
                logger.debug(f"[MySQL] Created new connection. Current connections: {self._current_connections}")
                return connection
            except Exception as e:
                logger.error(f"[MySQL] Failed to create connection: {e}")
                return None
    
    def _is_connection_healthy(self, conn: Any) -> bool:
        """检查连接是否健康。
        
        Args:
            conn: MySQL连接实例
            
        Returns:
            如果连接健康返回True，否则返回False
        """
        if not conn:
            return False
        
        try:
            # 使用ping方法检查连接是否活跃
            conn.ping(reconnect=False)
            return True
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            is_network_error = any(keyword in error_msg.lower() for keyword in [
                'connection', 'broken', 'lost', 'timeout', 'reset', 'gone away'
            ]) or any(keyword in error_type.lower() for keyword in [
                'connection', 'timeout', 'operationalerror'
            ])
            
            if is_network_error:
                logger.warning(
                    f"[MySQL] Connection health check detected network error: "
                    f"{error_type}: {error_msg}"
                )
            else:
                logger.debug(f"[MySQL] Connection health check failed: {error_type}: {error_msg}")
            return False
    
    def acquire(self, timeout: Optional[int] = None) -> Optional[Any]:
        """Acquire a connection from the pool.
        
        Args:
            timeout: Timeout for acquiring a connection (seconds). If None, use the default timeout.
            
        Returns:
            A MySQL connection instance, or None if no connection is available within the timeout.
        """
        timeout = timeout or self._connection_timeout
        
        try:
            # Try to get a connection from the pool
            conn = self._pool.get(timeout=timeout)
            
            # 检查连接是否健康，如果不健康则关闭并创建新连接
            if not self._is_connection_healthy(conn):
                logger.warning(f"[MySQL] Connection from pool is unhealthy, closing and creating new one")
                try:
                    conn.close()
                except Exception as close_error:
                    logger.debug(f"[MySQL] Error closing unhealthy connection: {close_error}")
                with self._lock:
                    if self._current_connections > 0:
                        self._current_connections -= 1
                # 创建新连接
                conn = self._create_connection()
                if not conn:
                    logger.error(f"[MySQL] Failed to create replacement connection")
                    return None
            
            logger.debug(f"[MySQL] Acquired connection from pool")
            return conn
        except Empty:
            # If the pool is empty, try to create a new connection
            logger.debug(f"[MySQL] Pool is empty, creating new connection")
            conn = self._create_connection()
            if conn:
                return conn
            
            # If we can't create a new connection, try again to get from the pool
            try:
                conn = self._pool.get(timeout=timeout)
                # 再次检查连接健康
                if conn and not self._is_connection_healthy(conn):
                    logger.warning(f"[MySQL] Connection from pool is unhealthy after waiting")
                    try:
                        conn.close()
                    except Exception as close_error:
                        logger.debug(f"[MySQL] Error closing unhealthy connection: {close_error}")
                    with self._lock:
                        if self._current_connections > 0:
                            self._current_connections -= 1
                    return None
                logger.debug(f"[MySQL] Acquired connection from pool after waiting")
                return conn
            except Empty:
                logger.error(f"[MySQL] Failed to acquire connection within timeout {timeout} seconds")
                return None
    
    def release(self, conn: Any) -> None:
        """Release a connection back to the pool.
        
        Args:
            conn: The MySQL connection instance to release
        """
        if not conn:
            return
        
        try:
            # 回滚未提交的事务
            conn.rollback()
            # 直接将连接放回池中，健康检查在 acquire() 时进行
            self._pool.put(conn)
            logger.debug(f"[MySQL] Released connection back to pool")
        except Exception as e:
            # 如果放回池中失败（例如池已满），尝试关闭连接
            logger.warning(f"[MySQL] Failed to release connection to pool: {e}, closing connection")
            try:
                conn.close()
            except Exception as close_error:
                logger.debug(f"[MySQL] Error closing connection: {close_error}")
            with self._lock:
                if self._current_connections > 0:
                    self._current_connections -= 1
    
    def close_all(self) -> None:
        """Close all connections in the pool."""
        with self._lock:
            closed_count = 0
            while not self._pool.empty():
                try:
                    conn = self._pool.get_nowait()
                    conn.close()
                    closed_count += 1
                    self._current_connections -= 1
                except Exception as e:
                    logger.error(f"[MySQL] Failed to close connection: {e}")
            
            logger.info(
                f"[MySQL] Closed all connections. Closed: {closed_count}, "
                f"Remaining count: {self._current_connections}"
            )
    
    def get_pool_stats(self) -> Dict[str, int]:
        """获取连接池统计信息。
        
        Returns:
            包含连接池统计信息的字典
        """
        with self._lock:
            return {
                'current_connections': self._current_connections,
                'pool_size': self._pool.qsize(),
                'max_connections': self._max_connections,
                'min_connections': self._min_connections
            }


def _to_datetime(value: Any) -> Optional[datetime]:
    """Convert various datetime formats to datetime object.
    
    Args:
        value: Input value (datetime, timestamp, string, etc.)
        
    Returns:
        datetime object or None
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        # Assume Unix timestamp
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        # Try to parse string
        try:
            # Try ISO format first
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            try:
                # Try common formats
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d']:
                    try:
                        return datetime.strptime(value, fmt)
                    except ValueError:
                        continue
            except Exception:
                pass
    return None


class MySQLDatabase:
    """Encapsulates MySQL connectivity and CRUD helpers."""
    
    # 类级别的锁，用于防止并发执行 sync_leaderboard
    _sync_leaderboard_lock = threading.Lock()

    # ==================================================================
    # 初始化和连接管理
    # ==================================================================
    
    def __init__(self, *, auto_init_tables: bool = True) -> None:
        # Create a connection pool instead of individual connections
        self._pool = MySQLConnectionPool(
            host=app_config.MYSQL_HOST,
            port=app_config.MYSQL_PORT,
            user=app_config.MYSQL_USER,
            password=app_config.MYSQL_PASSWORD,
            database=app_config.MYSQL_DATABASE,
            charset='utf8mb4',
            min_connections=5,
            max_connections=50,
            connection_timeout=30
        )
        
        self.market_ticker_table = MARKET_TICKER_TABLE
        self.leaderboard_table = getattr(app_config, 'MYSQL_LEADERBOARD_TABLE', LEADERBOARD_TABLE)
        self.market_data_agent_table = MARKET_DATA_AGENT_TABLE

        # K线表前缀（默认 market_klines），按不同 interval 拆分为多张表：
        # market_klines_1w, market_klines_1d, market_klines_4h, market_klines_1h,
        # market_klines_15m, market_klines_5m, market_klines_1m
        self.market_klines_table: str = getattr(
            app_config,
            "MYSQL_MARKET_KLINES_TABLE",
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
        """Execute a function with a MySQL connection from the pool.
        
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
            conn = None
            connection_acquired = False
            try:
                conn = self._pool.acquire()
                if not conn:
                    raise Exception("Failed to acquire MySQL connection")
                connection_acquired = True
                
                # 执行函数
                result = func(conn, *args, **kwargs)
                
                # 成功执行，提交事务并释放连接
                conn.commit()
                self._pool.release(conn)
                conn = None  # 标记已释放，避免 finally 中重复处理
                return result
                
            except Exception as e:
                # 记录错误信息
                error_type = type(e).__name__
                error_msg = str(e)
                
                # 判断是否为网络/协议错误，需要重试
                is_network_error = any(keyword in error_msg.lower() for keyword in [
                    'connection', 'broken', 'lost', 'timeout', 'reset', 'gone away',
                    'operationalerror', 'interfaceerror'
                ]) or any(keyword in error_type.lower() for keyword in [
                    'connection', 'timeout', 'operationalerror', 'interfaceerror'
                ])
                
                # 如果已获取连接，需要处理连接（关闭或释放）
                if connection_acquired and conn:
                    try:
                        # 回滚事务
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                        
                        # 对于网络错误，连接很可能已损坏，应该关闭而不是放回池中
                        if is_network_error:
                            logger.warning(
                                f"[MySQL] Network error detected, closing damaged connection: "
                                f"{error_type}: {error_msg}"
                            )
                            try:
                                conn.close()
                            except Exception:
                                pass
                            # 减少连接计数（因为连接已损坏，不能放回池中）
                            with self._pool._lock:
                                if self._pool._current_connections > 0:
                                    self._pool._current_connections -= 1
                            conn = None  # 标记已处理，避免 finally 中重复处理
                        else:
                            # 对于非网络错误，尝试释放连接回池中
                            try:
                                self._pool.release(conn)
                                conn = None  # 标记已释放
                            except Exception as release_error:
                                # 如果释放失败，关闭连接
                                logger.warning(
                                    f"[MySQL] Failed to release connection, closing it: {release_error}"
                                )
                                try:
                                    conn.close()
                                except Exception:
                                    pass
                                with self._pool._lock:
                                    if self._pool._current_connections > 0:
                                        self._current_connections -= 1
                                conn = None  # 标记已处理
                    except Exception as close_error:
                        logger.debug(f"[MySQL] Error closing failed connection: {close_error}")
                        # 确保连接计数被减少
                        with self._pool._lock:
                            if self._pool._current_connections > 0:
                                self._pool._current_connections -= 1
                        conn = None  # 标记已处理
                
                # 判断是否需要重试
                if attempt < max_retries - 1:
                    # 计算等待时间（指数退避）
                    wait_time = retry_delay * (2 ** attempt)
                    
                    if is_network_error:
                        logger.warning(
                            f"[MySQL] Network error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    else:
                        logger.warning(
                            f"[MySQL] Error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    
                    time.sleep(wait_time)
                    continue
                else:
                    # 最后一次尝试失败，抛出异常
                    logger.error(
                        f"[MySQL] Failed after {max_retries} attempts. Last error: {error_type}: {error_msg}"
                    )
                    raise
            finally:
                # 确保连接被正确处理（双重保险）
                if connection_acquired and conn:
                    try:
                        # 如果连接还没有被释放，尝试关闭它
                        logger.warning(
                            f"[MySQL] Connection not released in finally block, closing it"
                        )
                        try:
                            conn.rollback()
                            conn.close()
                        except Exception:
                            pass
                        with self._pool._lock:
                            if self._pool._current_connections > 0:
                                self._pool._current_connections -= 1
                    except Exception as final_error:
                        logger.debug(f"[MySQL] Error in finally block: {final_error}")

    # ==================================================================
    # 通用数据库操作方法
    # ==================================================================
    
    def command(self, sql: str, params: tuple = None) -> Any:
        """执行原始SQL命令并返回结果。
        
        Args:
            sql: 要执行的SQL命令字符串
            params: 可选的参数元组，用于参数化查询
        
        Returns:
            执行结果，可能包含影响的行数等信息
        """
        def _execute_command(conn):
            cursor = conn.cursor()
            try:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                result = cursor.rowcount
                return result
            finally:
                cursor.close()
        
        return self._with_connection(_execute_command)
    
    def query(self, sql: str, params: tuple = None) -> List[Tuple]:
        """执行查询并返回结果。
        
        Args:
            sql: 要执行的 SQL 查询字符串
            params: 可选的参数元组，用于参数化查询
            
        Returns:
            查询结果的行列表，每行是一个元组
        """
        def _execute_query(conn):
            cursor = conn.cursor()
            try:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                # 转换为元组列表以保持与ClickHouse兼容
                rows = cursor.fetchall()
                # 如果是字典游标，转换为元组
                if rows and isinstance(rows[0], dict):
                    return [tuple(row.values()) for row in rows]
                return rows
            finally:
                cursor.close()
        
        return self._with_connection(_execute_query)
    
    def _check_table_exists(self, table_name: str) -> bool:
        """Check if a table exists in MySQL.
        
        Args:
            table_name: The name of the table to check
            
        Returns:
            True if the table exists, False otherwise
        """
        def _execute_check(conn):
            try:
                cursor = conn.cursor()
                try:
                    cursor.execute("""
                        SELECT COUNT(*) 
                        FROM information_schema.tables 
                        WHERE table_schema = DATABASE() 
                        AND table_name = %s
                    """, (table_name,))
                    result = cursor.fetchone()
                    return result[0] > 0 if result else False
                finally:
                    cursor.close()
            except Exception as e:
                logger.warning(f"[MySQL] 检查表是否存在时出错: {e}")
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
        
        def _execute_insert(conn):
            cursor = conn.cursor()
            try:
                # 构建INSERT语句
                columns_str = ', '.join([f"`{col}`" for col in column_names])
                placeholders = ', '.join(['%s'] * len(column_names))
                sql = f"INSERT INTO `{table}` ({columns_str}) VALUES ({placeholders})"
                
                # 批量插入
                cursor.executemany(sql, payload)
                logger.debug("[MySQL] Inserted %s rows into %s", len(payload), table)
            finally:
                cursor.close()
        
        self._with_connection(_execute_insert)

    # ==================================================================
    # Market Ticker 模块：表管理
    # ==================================================================
    
    def ensure_market_ticker_table(self) -> None:
        """Create the 24h market ticker table if it does not exist."""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{self.market_ticker_table}` (
            `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            `event_time` DATETIME NOT NULL,
            `symbol` VARCHAR(50) NOT NULL UNIQUE,
            `price_change` DOUBLE DEFAULT 0.0,
            `price_change_percent` DOUBLE DEFAULT 0.0,
            `side` VARCHAR(10) DEFAULT '',
            `change_percent_text` VARCHAR(50) DEFAULT '',
            `average_price` DOUBLE DEFAULT 0.0,
            `last_price` DOUBLE DEFAULT 0.0,
            `last_trade_volume` DOUBLE DEFAULT 0.0,
            `open_price` DOUBLE DEFAULT 0.0,
            `high_price` DOUBLE DEFAULT 0.0,
            `low_price` DOUBLE DEFAULT 0.0,
            `base_volume` DOUBLE DEFAULT 0.0,
            `quote_volume` DOUBLE DEFAULT 0.0,
            `stats_open_time` DATETIME,
            `stats_close_time` DATETIME,
            `first_trade_id` BIGINT UNSIGNED DEFAULT 0,
            `last_trade_id` BIGINT UNSIGNED DEFAULT 0,
            `trade_count` BIGINT UNSIGNED DEFAULT 0,
            `ingestion_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
            `update_price_date` DATETIME NULL,
            INDEX `idx_symbol` (`symbol`),
            INDEX `idx_event_time` (`event_time`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.info("[MySQL] Ensured table %s exists", self.market_ticker_table)

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
        - 使用窗口函数为每个交易对筛选最新的一条记录
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
            placeholders = ', '.join(['%s'] * len(symbols))
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
                FROM `{self.market_ticker_table}`
                WHERE symbol IN ({placeholders})
            ) AS ranked
            WHERE rn = 1
            """
            
            def _execute_query(conn):
                cursor = conn.cursor()
                try:
                    cursor.execute(query, symbols)
                    return cursor.fetchall()
                finally:
                    cursor.close()
            
            result = self._with_connection(_execute_query)
            
            symbol_data = {}
            for row in result:
                # 处理字典或元组格式的结果
                if isinstance(row, dict):
                    symbol = row['symbol']
                    open_price_raw = row['open_price']
                    last_price = row.get('last_price')
                    update_price_date = row.get('update_price_date')
                else:
                    symbol = row[0]
                    open_price_raw = row[1]
                    last_price = row[2] if len(row) > 2 else None
                    update_price_date = row[3] if len(row) > 3 else None
                
                # 关键逻辑：如果open_price为0.0且update_price_date为None，视为"未设置"
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
            logger.warning("[MySQL] Failed to get existing symbol data: %s", e)
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
                logger.debug("[MySQL] 移除接口数据中的 open_price 字段（只能由异步价格刷新服务更新）")
            if "update_price_date" in normalized:
                del normalized["update_price_date"]
                logger.debug("[MySQL] 移除接口数据中的 update_price_date 字段（只能由异步价格刷新服务更新）")
            
            normalized["event_time"] = _to_datetime(normalized.get("event_time"))
            normalized["stats_open_time"] = _to_datetime(normalized.get("stats_open_time"))
            normalized["stats_close_time"] = _to_datetime(normalized.get("stats_close_time"))
            
            # 确保所有DOUBLE字段不为None，使用0.0作为默认值
            float_fields = [
                "price_change", "price_change_percent", "average_price", "last_price",
                "last_trade_volume", "open_price", "high_price", "low_price",
                "base_volume", "quote_volume"
            ]
            for field in float_fields:
                if normalized.get(field) is None:
                    normalized[field] = 0.0
            
            # 确保所有BIGINT字段不为None，使用0作为默认值
            int_fields = ["first_trade_id", "last_trade_id", "trade_count"]
            for field in int_fields:
                if normalized.get(field) is None:
                    normalized[field] = 0
            
            # 确保所有String字段不为None，使用空字符串作为默认值
            string_fields = ["side", "change_percent_text"]
            for field in string_fields:
                if normalized.get(field) is None:
                    normalized[field] = ""
            
            # 构建行数据
            row_data = [normalized.get(col, None) for col in column_names]
            prepared_rows.append(row_data)
        
        if prepared_rows:
            self.insert_rows(self.market_ticker_table, prepared_rows, column_names)

    def upsert_market_tickers(self, rows: Iterable[Dict[str, Any]]) -> None:
        """Upsert市场行情数据（插入或更新）。
        
        优化后的upsert逻辑：
        1. 先执行UPDATE操作（基于symbol唯一主键）
        2. 如果UPDATE返回受影响行数为0，说明记录不存在，则执行INSERT
        3. 单行操作，不使用批量更新，提高效率
        
        注意：
        - 不再需要先查询SELECT，直接尝试UPDATE即可
        - UPDATE操作会排除open_price和update_price_date字段（这些字段由价格刷新服务管理）
        
        Args:
            rows: 市场行情数据字典的可迭代对象
        """
        rows_list = list(rows)
        if not rows_list:
            return
        
        def _execute_upsert(conn):
            cursor = conn.cursor()
            try:
                for row in rows_list:
                    normalized = dict(row)
                    symbol = normalized.get("symbol")
                    
                    if not symbol:
                        continue
                    
                    # 移除open_price和update_price_date（这些字段由价格刷新服务管理）
                    normalized.pop("open_price", None)
                    normalized.pop("update_price_date", None)
                    
                    # 数据标准化处理
                    normalized["event_time"] = _to_datetime(normalized.get("event_time"))
                    normalized["stats_open_time"] = _to_datetime(normalized.get("stats_open_time"))
                    normalized["stats_close_time"] = _to_datetime(normalized.get("stats_close_time"))
                    
                    # 确保所有DOUBLE字段不为None，使用0.0作为默认值
                    float_fields = [
                        "price_change", "price_change_percent", "average_price", "last_price",
                        "last_trade_volume", "high_price", "low_price",
                        "base_volume", "quote_volume"
                    ]
                    for field in float_fields:
                        if normalized.get(field) is None:
                            normalized[field] = 0.0
                    
                    # 确保所有BIGINT字段不为None，使用0作为默认值
                    int_fields = ["first_trade_id", "last_trade_id", "trade_count"]
                    for field in int_fields:
                        if normalized.get(field) is None:
                            normalized[field] = 0
                    
                    # 确保所有String字段不为None，使用空字符串作为默认值
                    string_fields = ["side", "change_percent_text"]
                    for field in string_fields:
                        if normalized.get(field) is None:
                            normalized[field] = ""
                    
                    # 先尝试UPDATE操作（基于symbol唯一主键）
                    update_fields = []
                    update_values = []
                    for key, value in normalized.items():
                        if key != "symbol":
                            update_fields.append(f"`{key}` = %s")
                            update_values.append(value)
                    
                    # 构建UPDATE SQL语句
                    update_sql = f"""
                    UPDATE `{self.market_ticker_table}`
                    SET {', '.join(update_fields)}
                    WHERE `symbol` = %s
                    """
                    
                    # 执行UPDATE，参数顺序：更新字段值 + symbol
                    update_params = tuple(update_values) + (symbol,)
                    cursor.execute(update_sql, update_params)
                    
                    # 检查UPDATE受影响的行数
                    affected_rows = cursor.rowcount
                    
                    # 如果UPDATE没有更新任何行（affected_rows == 0），说明记录不存在，执行INSERT
                    if affected_rows == 0:
                        # 构建INSERT SQL语句
                        insert_sql = f"""
                        INSERT INTO `{self.market_ticker_table}` 
                        (`symbol`, `event_time`, `price_change`, `price_change_percent`, 
                         `side`, `change_percent_text`, `average_price`, `last_price`, 
                         `last_trade_volume`, `high_price`, `low_price`, `base_volume`, 
                         `quote_volume`, `stats_open_time`, `stats_close_time`, 
                         `first_trade_id`, `last_trade_id`, `trade_count`)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """
                        
                        insert_params = (
                            symbol,
                            normalized.get("event_time"),
                            normalized.get("price_change", 0.0),
                            normalized.get("price_change_percent", 0.0),
                            normalized.get("side", ""),
                            normalized.get("change_percent_text", ""),
                            normalized.get("average_price", 0.0),
                            normalized.get("last_price", 0.0),
                            normalized.get("last_trade_volume", 0.0),
                            normalized.get("high_price", 0.0),
                            normalized.get("low_price", 0.0),
                            normalized.get("base_volume", 0.0),
                            normalized.get("quote_volume", 0.0),
                            normalized.get("stats_open_time"),
                            normalized.get("stats_close_time"),
                            normalized.get("first_trade_id", 0),
                            normalized.get("last_trade_id", 0),
                            normalized.get("trade_count", 0),
                        )
                        
                        cursor.execute(insert_sql, insert_params)
                        logger.debug(f"[MySQL] Inserted new market ticker: {symbol}")
                    else:
                        logger.debug(f"[MySQL] Updated market ticker: {symbol} (affected rows: {affected_rows})")
            finally:
                cursor.close()
        
        self._with_connection(_execute_upsert)

    def update_open_price(self, symbol: str, open_price: float, update_date: datetime) -> bool:
        """更新指定交易对的开盘价和更新日期。
        
        Args:
            symbol: 交易对符号
            open_price: 开盘价
            update_date: 更新日期
            
        Returns:
            是否更新成功
        """
        try:
            sql = f"""
            UPDATE `{self.market_ticker_table}`
            SET `open_price` = %s, `update_price_date` = %s
            WHERE `symbol` = %s
            ORDER BY `event_time` DESC
            LIMIT 1
            """
            self.command(sql, (open_price, update_date, symbol))
            return True
        except Exception as e:
            logger.error("[MySQL] Failed to update open price for %s: %s", symbol, e)
            return False

    # ==================================================================
    # Leaderboard 模块：表管理
    # ==================================================================
    
    def ensure_leaderboard_table(self) -> None:
        """Create the leaderboard table if it does not exist."""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{self.leaderboard_table}` (
            `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            `event_time` DATETIME NOT NULL,
            `symbol` VARCHAR(50) NOT NULL,
            `contract_symbol` VARCHAR(100) DEFAULT '',
            `name` VARCHAR(200) DEFAULT '',
            `exchange` VARCHAR(50) DEFAULT 'BINANCE_FUTURES',
            `side` VARCHAR(10) NOT NULL,
            `rank` TINYINT UNSIGNED DEFAULT 0,
            `price` DOUBLE DEFAULT 0.0,
            `change_percent` DOUBLE DEFAULT 0.0,
            `quote_volume` DOUBLE DEFAULT 0.0,
            `timeframes` VARCHAR(200) DEFAULT '',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX `idx_symbol_side` (`symbol`, `side`),
            INDEX `idx_event_time` (`event_time`),
            INDEX `idx_rank` (`rank`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.info("[MySQL] Ensured table %s exists", self.leaderboard_table)

    # ==================================================================
    # Leaderboard 模块：数据查询
    # ==================================================================
    
    def get_leaderboard(
        self,
        side: str,
        limit: int = 10,
        time_window_seconds: int = 2
    ) -> List[Dict[str, Any]]:
        """获取涨跌榜数据。
        
        Args:
            side: 'LONG' 或 'SHORT'
            limit: 返回的记录数限制
            time_window_seconds: 时间窗口（秒），只查询最近N秒内的数据
            
        Returns:
            涨跌榜数据列表
        """
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=time_window_seconds)
            
            query = f"""
            SELECT 
                symbol, contract_symbol, name, exchange, side, rank, 
                price, change_percent, quote_volume, timeframes, updated_at
            FROM `{self.leaderboard_table}`
            WHERE side = %s 
            AND event_time >= %s
            ORDER BY rank ASC
            LIMIT %s
            """
            
            def _execute_query(conn):
                cursor = conn.cursor()
                try:
                    cursor.execute(query, (side, cutoff_time, limit))
                    rows = cursor.fetchall()
                    # 转换为字典列表
                    if rows and isinstance(rows[0], dict):
                        return rows
                    # 如果是元组，转换为字典
                    result = []
                    for row in rows:
                        result.append({
                            'symbol': row[0],
                            'contract_symbol': row[1] if len(row) > 1 else '',
                            'name': row[2] if len(row) > 2 else '',
                            'exchange': row[3] if len(row) > 3 else 'BINANCE_FUTURES',
                            'side': row[4] if len(row) > 4 else side,
                            'rank': row[5] if len(row) > 5 else 0,
                            'price': row[6] if len(row) > 6 else 0.0,
                            'change_percent': row[7] if len(row) > 7 else 0.0,
                            'quote_volume': row[8] if len(row) > 8 else 0.0,
                            'timeframes': row[9] if len(row) > 9 else '',
                            'updated_at': row[10] if len(row) > 10 else None,
                        })
                    return result
                finally:
                    cursor.close()
            
            return self._with_connection(_execute_query)
        except Exception as e:
            logger.error("[MySQL] Failed to get leaderboard: %s", e)
            return []

    # ==================================================================
    # Leaderboard 模块：数据插入和更新
    # ==================================================================
    
    def sync_leaderboard(
        self,
        long_rows: List[Dict[str, Any]],
        short_rows: List[Dict[str, Any]]
    ) -> dict:
        """同步涨跌榜数据。
        
        Args:
            long_rows: 涨幅榜数据
            short_rows: 跌幅榜数据
            
        Returns:
            同步统计信息
        """
        with self._sync_leaderboard_lock:
            stats = {
                'long_inserted': 0,
                'short_inserted': 0,
                'long_updated': 0,
                'short_updated': 0,
            }
            
            try:
                event_time = datetime.now(timezone.utc)
                
                def _execute_sync(conn):
                    cursor = conn.cursor()
                    try:
                        # 处理涨幅榜
                        for row in long_rows:
                            row['event_time'] = event_time
                            row['side'] = 'LONG'
                            
                            # 使用INSERT ... ON DUPLICATE KEY UPDATE
                            sql = f"""
                            INSERT INTO `{self.leaderboard_table}`
                            (`event_time`, `symbol`, `contract_symbol`, `name`, `exchange`, 
                             `side`, `rank`, `price`, `change_percent`, `quote_volume`, `timeframes`)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                            `event_time` = VALUES(`event_time`),
                            `rank` = VALUES(`rank`),
                            `price` = VALUES(`price`),
                            `change_percent` = VALUES(`change_percent`),
                            `quote_volume` = VALUES(`quote_volume`),
                            `timeframes` = VALUES(`timeframes`),
                            `updated_at` = CURRENT_TIMESTAMP
                            """
                            
                            cursor.execute(sql, (
                                row.get('event_time'),
                                row.get('symbol'),
                                row.get('contract_symbol', ''),
                                row.get('name', ''),
                                row.get('exchange', 'BINANCE_FUTURES'),
                                row.get('side'),
                                row.get('rank', 0),
                                row.get('price', 0.0),
                                row.get('change_percent', 0.0),
                                row.get('quote_volume', 0.0),
                                row.get('timeframes', ''),
                            ))
                            
                            if cursor.rowcount == 1:
                                stats['long_inserted'] += 1
                            else:
                                stats['long_updated'] += 1
                        
                        # 处理跌幅榜
                        for row in short_rows:
                            row['event_time'] = event_time
                            row['side'] = 'SHORT'
                            
                            sql = f"""
                            INSERT INTO `{self.leaderboard_table}`
                            (`event_time`, `symbol`, `contract_symbol`, `name`, `exchange`, 
                             `side`, `rank`, `price`, `change_percent`, `quote_volume`, `timeframes`)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                            `event_time` = VALUES(`event_time`),
                            `rank` = VALUES(`rank`),
                            `price` = VALUES(`price`),
                            `change_percent` = VALUES(`change_percent`),
                            `quote_volume` = VALUES(`quote_volume`),
                            `timeframes` = VALUES(`timeframes`),
                            `updated_at` = CURRENT_TIMESTAMP
                            """
                            
                            cursor.execute(sql, (
                                row.get('event_time'),
                                row.get('symbol'),
                                row.get('contract_symbol', ''),
                                row.get('name', ''),
                                row.get('exchange', 'BINANCE_FUTURES'),
                                row.get('side'),
                                row.get('rank', 0),
                                row.get('price', 0.0),
                                row.get('change_percent', 0.0),
                                row.get('quote_volume', 0.0),
                                row.get('timeframes', ''),
                            ))
                            
                            if cursor.rowcount == 1:
                                stats['short_inserted'] += 1
                            else:
                                stats['short_updated'] += 1
                    finally:
                        cursor.close()
                
                self._with_connection(_execute_sync)
                
                logger.info(
                    "[MySQL] Leaderboard sync completed: long_inserted=%d, long_updated=%d, "
                    "short_inserted=%d, short_updated=%d",
                    stats['long_inserted'], stats['long_updated'],
                    stats['short_inserted'], stats['short_updated']
                )
            except Exception as e:
                logger.error("[MySQL] Failed to sync leaderboard: %s", e, exc_info=True)
            
            return stats

    def cleanup_old_leaderboard(self, minutes: int = 10) -> dict:
        """清理旧的涨跌榜数据。
        
        Args:
            minutes: 保留最近N分钟的数据
            
        Returns:
            清理统计信息
        """
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)
            
            def _execute_cleanup(conn):
                cursor = conn.cursor()
                try:
                    # 查询要删除的记录数
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM `{self.leaderboard_table}`
                        WHERE event_time < %s
                    """, (cutoff_time,))
                    count_before = cursor.fetchone()[0] if cursor.rowcount > 0 else 0
                    
                    # 执行删除
                    cursor.execute(f"""
                        DELETE FROM `{self.leaderboard_table}`
                        WHERE event_time < %s
                    """, (cutoff_time,))
                    
                    deleted_count = cursor.rowcount
                    
                    return {
                        'deleted': deleted_count,
                        'count_before': count_before
                    }
                finally:
                    cursor.close()
            
            stats = self._with_connection(_execute_cleanup)
            logger.info(
                "[MySQL] Cleaned up %d old leaderboard records (older than %d minutes)",
                stats.get('deleted', 0), minutes
            )
            return stats
        except Exception as e:
            logger.error("[MySQL] Failed to cleanup old leaderboard: %s", e, exc_info=True)
            return {'deleted': 0, 'count_before': 0}

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
            CREATE TABLE IF NOT EXISTS `{table_name}` (
                `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                `event_time` DATETIME NOT NULL,
                `symbol` VARCHAR(50) NOT NULL,
                `contract_type` VARCHAR(50) DEFAULT '',
                `kline_start_time` DATETIME NOT NULL,
                `kline_end_time` DATETIME NOT NULL,
                `interval` VARCHAR(10) NOT NULL,
                `first_trade_id` BIGINT UNSIGNED DEFAULT 0,
                `last_trade_id` BIGINT UNSIGNED DEFAULT 0,
                `open_price` DOUBLE DEFAULT 0.0,
                `close_price` DOUBLE DEFAULT 0.0,
                `high_price` DOUBLE DEFAULT 0.0,
                `low_price` DOUBLE DEFAULT 0.0,
                `base_volume` DOUBLE DEFAULT 0.0,
                `trade_count` BIGINT UNSIGNED DEFAULT 0,
                `is_closed` TINYINT UNSIGNED DEFAULT 0,
                `quote_volume` DOUBLE DEFAULT 0.0,
                `taker_buy_base_volume` DOUBLE DEFAULT 0.0,
                `taker_buy_quote_volume` DOUBLE DEFAULT 0.0,
                `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX `idx_symbol_interval_endtime` (`symbol`, `interval`, `kline_end_time`),
                INDEX `idx_event_time` (`event_time`),
                INDEX `idx_kline_end_time` (`kline_end_time`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
            self.command(ddl)
            logger.info("[MySQL] Ensured kline table %s (interval=%s) exists", table_name, interval)

    # ==================================================================
    # Market Klines 模块：数据插入
    # ==================================================================
    
    def insert_market_klines(self, rows: Iterable[Dict[str, Any]]) -> None:
        """插入K线数据到对应的interval表中。
        
        Args:
            rows: K线数据字典的可迭代对象，必须包含interval字段
        """
        # 按interval分组
        rows_by_interval: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            interval = row.get('interval', '').lower()
            if interval not in self.market_klines_tables:
                logger.warning("[MySQL] Unknown interval %s, skipping", interval)
                continue
            if interval not in rows_by_interval:
                rows_by_interval[interval] = []
            rows_by_interval[interval].append(row)
        
        # 为每个interval插入数据
        for interval, interval_rows in rows_by_interval.items():
            table_name = self.market_klines_tables[interval]
            column_names = [
                "event_time", "symbol", "contract_type", "kline_start_time", "kline_end_time",
                "interval", "first_trade_id", "last_trade_id", "open_price", "close_price",
                "high_price", "low_price", "base_volume", "trade_count", "is_closed",
                "quote_volume", "taker_buy_base_volume", "taker_buy_quote_volume"
            ]
            
            prepared_rows: List[List[Any]] = []
            for row in interval_rows:
                row_data = [
                    _to_datetime(row.get("event_time")),
                    row.get("symbol", ""),
                    row.get("contract_type", ""),
                    _to_datetime(row.get("kline_start_time")),
                    _to_datetime(row.get("kline_end_time")),
                    row.get("interval", interval),
                    row.get("first_trade_id", 0),
                    row.get("last_trade_id", 0),
                    row.get("open_price", 0.0),
                    row.get("close_price", 0.0),
                    row.get("high_price", 0.0),
                    row.get("low_price", 0.0),
                    row.get("base_volume", 0.0),
                    row.get("trade_count", 0),
                    1 if row.get("is_closed", False) else 0,
                    row.get("quote_volume", 0.0),
                    row.get("taker_buy_base_volume", 0.0),
                    row.get("taker_buy_quote_volume", 0.0),
                ]
                prepared_rows.append(row_data)
            
            if prepared_rows:
                self.insert_rows(table_name, prepared_rows, column_names)
                logger.debug("[MySQL] Inserted %d klines into %s", len(prepared_rows), table_name)

    def get_market_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """获取K线数据。
        
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
        table_name = self.market_klines_tables.get(interval.lower())
        if not table_name:
            logger.warning(f"[MySQL] Unsupported interval: {interval}")
            return []
        
        try:
            # 构建查询SQL
            where_conditions = ["symbol = %s"]
            params = [symbol.upper()]
            
            if start_time:
                where_conditions.append("kline_end_time >= %s")
                params.append(start_time)
            if end_time:
                where_conditions.append("kline_end_time <= %s")
                params.append(end_time)
            
            where_clause = " AND ".join(where_conditions)
            
            query = f"""
            SELECT 
                UNIX_TIMESTAMP(kline_end_time) * 1000 as timestamp,
                open_price as open,
                high_price as high,
                low_price as low,
                close_price as close,
                base_volume as volume,
                quote_volume as turnover,
                taker_buy_base_volume as buyVolume,
                taker_buy_quote_volume as buyTurnover
            FROM `{table_name}`
            WHERE {where_clause}
            ORDER BY kline_end_time ASC
            LIMIT %s
            """
            params.append(limit)
            
            result = self.query(query, tuple(params))
            
            # 转换为字典列表，价格保留6位小数
            klines = []
            for row in result:
                klines.append({
                    'timestamp': int(row[0]),
                    'open': round(float(row[1]), 6),
                    'high': round(float(row[2]), 6),
                    'low': round(float(row[3]), 6),
                    'close': round(float(row[4]), 6),
                    'volume': float(row[5]),
                    'turnover': float(row[6]),
                    'buyVolume': float(row[7]),
                    'buyTurnover': float(row[8])
                })
            
            logger.debug(f"[MySQL] Retrieved {len(klines)} klines for {symbol} {interval}")
            return klines
            
        except Exception as exc:
            logger.error(f"[MySQL] Failed to get klines: {exc}", exc_info=True)
            return []

    # ==================================================================
    # Market Data Agent 模块：表管理
    # ==================================================================
    
    def ensure_market_data_agent_table(self) -> None:
        """Create the market data agent table if it does not exist."""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{self.market_data_agent_table}` (
            `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            `ip` VARCHAR(50) NOT NULL,
            `port` INT UNSIGNED NOT NULL,
            `connection_count` INT UNSIGNED DEFAULT 0,
            `assigned_symbol_count` INT UNSIGNED DEFAULT 0,
            `last_heartbeat` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY `uk_ip_port` (`ip`, `port`),
            INDEX `idx_last_heartbeat` (`last_heartbeat`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.info("[MySQL] Ensured table %s exists", self.market_data_agent_table)

    def update_agent_connection_info(
        self, 
        ip: str, 
        port: int, 
        connection_count: int, 
        assigned_symbol_count: int
    ) -> None:
        """更新agent的连接信息。
        
        Args:
            ip: Agent IP地址
            port: Agent端口
            connection_count: 连接数
            assigned_symbol_count: 分配的symbol数量
        """
        try:
            sql = f"""
            INSERT INTO `{self.market_data_agent_table}`
            (`ip`, `port`, `connection_count`, `assigned_symbol_count`, `last_heartbeat`)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON DUPLICATE KEY UPDATE
            `connection_count` = VALUES(`connection_count`),
            `assigned_symbol_count` = VALUES(`assigned_symbol_count`),
            `last_heartbeat` = CURRENT_TIMESTAMP
            """
            self.command(sql, {
                'ip': ip,
                'port': port,
                'connection_count': connection_count,
                'assigned_symbol_count': assigned_symbol_count
            })
        except Exception as e:
            logger.error("[MySQL] Failed to update agent connection info: %s", e)

    def get_agent_connection_info(self) -> List[Dict[str, Any]]:
        """获取所有agent的连接信息。
        
        Returns:
            Agent连接信息列表
        """
        try:
            query = f"""
            SELECT ip, port, connection_count, assigned_symbol_count, last_heartbeat
            FROM `{self.market_data_agent_table}`
            ORDER BY last_heartbeat DESC
            """
            
            def _execute_query(conn):
                cursor = conn.cursor()
                try:
                    cursor.execute(query)
                    rows = cursor.fetchall()
                    # 转换为字典列表
                    if rows and isinstance(rows[0], dict):
                        return rows
                    # 如果是元组，转换为字典
                    result = []
                    for row in rows:
                        result.append({
                            'ip': row[0],
                            'port': row[1],
                            'connection_count': row[2],
                            'assigned_symbol_count': row[3],
                            'last_heartbeat': row[4] if len(row) > 4 else None,
                        })
                    return result
                finally:
                    cursor.close()
            
            return self._with_connection(_execute_query)
        except Exception as e:
            logger.error("[MySQL] Failed to get agent connection info: %s", e)
            return []

