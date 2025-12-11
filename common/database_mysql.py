"""MySQL database utilities for market data storage."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
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
        min_connections: int = 10,
        max_connections: int = 50,
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
        
        # 检查连接对象是否有必要的属性（基本有效性检查）
        if not hasattr(conn, 'ping') or not hasattr(conn, '_sock'):
            return False
        
        # 检查 socket 是否已关闭
        try:
            if conn._sock is None:
                logger.debug("[MySQL] Connection socket is None")
                return False
        except (AttributeError, OSError):
            logger.debug("[MySQL] Error accessing connection socket")
            return False
        
        # 检查文件描述符是否有效
        try:
            if hasattr(conn._sock, 'fileno'):
                fileno = conn._sock.fileno()
                if fileno < 0:
                    logger.debug("[MySQL] Connection socket has invalid file descriptor")
                    return False
        except (AttributeError, OSError):
            logger.debug("[MySQL] Error checking socket file descriptor")
            return False
        
        try:
            # 使用ping方法检查连接是否活跃
            conn.ping(reconnect=False)
            return True
        except (AttributeError, OSError, TypeError, ValueError) as e:
            # 连接对象已损坏或已关闭
            # 特别检查"read of closed file"错误
            error_type = type(e).__name__
            error_msg = str(e)
            if "read of closed file" in error_msg.lower():
                logger.debug("[MySQL] Connection health check failed: read of closed file")
            else:
                logger.debug(
                    f"[MySQL] Connection health check failed (connection may be closed): "
                    f"{error_type}: {error_msg}"
                )
            return False
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            is_network_error = any(keyword in error_msg.lower() for keyword in [
                'connection', 'broken', 'lost', 'timeout', 'reset', 'gone away',
                'bad file descriptor', 'settimeout', 'read of closed file'
            ]) or any(keyword in error_type.lower() for keyword in [
                'connection', 'timeout', 'operationalerror', 'attributeerror', 'oserror', 'valueerror'
            ])
            
            if is_network_error:
                logger.debug(
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
                logger.debug(f"[MySQL] Connection from pool is unhealthy, closing and creating new one")
                try:
                    conn.close()
                except (AttributeError, OSError, TypeError) as close_error:
                    # 连接可能已经关闭或损坏，忽略错误
                    logger.debug(f"[MySQL] Error closing unhealthy connection (may already be closed): {close_error}")
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
                    logger.debug(f"[MySQL] Connection from pool is unhealthy after waiting")
                    try:
                        conn.close()
                    except (AttributeError, OSError, TypeError) as close_error:
                        # 连接可能已经关闭或损坏，忽略错误
                        logger.debug(f"[MySQL] Error closing unhealthy connection (may already be closed): {close_error}")
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
        
        # 检查连接是否已关闭或损坏
        try:
            # 检查连接对象是否有必要的属性
            if not hasattr(conn, 'rollback') or not hasattr(conn, '_sock'):
                logger.debug("[MySQL] Connection object is invalid, skipping release")
                with self._lock:
                    if self._current_connections > 0:
                        self._current_connections -= 1
                return
            
            # 检查 socket 是否已关闭
            if conn._sock is None:
                logger.debug("[MySQL] Connection socket is closed, skipping release")
                with self._lock:
                    if self._current_connections > 0:
                        self._current_connections -= 1
                return
            
            # 检查文件描述符是否有效
            if hasattr(conn._sock, 'fileno'):
                try:
                    fileno = conn._sock.fileno()
                    if fileno < 0:
                        logger.debug("[MySQL] Connection socket has invalid file descriptor, skipping release")
                        with self._lock:
                            if self._current_connections > 0:
                                self._current_connections -= 1
                        return
                except (AttributeError, OSError):
                    logger.debug("[MySQL] Error checking socket file descriptor, skipping release")
                    with self._lock:
                        if self._current_connections > 0:
                            self._current_connections -= 1
                    return
        except (AttributeError, OSError) as e:
            logger.debug(f"[MySQL] Connection check failed, skipping release: {e}")
            with self._lock:
                if self._current_connections > 0:
                    self._current_connections -= 1
            return
        
        try:
            # 回滚未提交的事务
            try:
                conn.rollback()
            except (AttributeError, OSError, TypeError, ValueError) as rollback_error:
                # 连接已关闭或损坏，不能回滚
                error_msg = str(rollback_error)
                # 特别检查"read of closed file"错误
                if "read of closed file" in error_msg.lower():
                    logger.debug("[MySQL] Connection has closed file error during rollback, skipping release")
                else:
                    logger.debug(f"[MySQL] Failed to rollback connection: {rollback_error}")
                # 不将损坏的连接放回池中
                try:
                    conn.close()
                except Exception:
                    pass
                with self._lock:
                    if self._current_connections > 0:
                        self._current_connections -= 1
                return
            
            # 直接将连接放回池中，健康检查在 acquire() 时进行
            self._pool.put(conn)
            logger.debug(f"[MySQL] Released connection back to pool")
        except (AttributeError, OSError, TypeError, ValueError) as e:
            # 连接已关闭或损坏，不能放回池中
            error_msg = str(e)
            # 特别检查"read of closed file"错误
            if "read of closed file" in error_msg.lower():
                logger.debug("[MySQL] Connection has closed file error during release, closing connection")
            elif 'bad file descriptor' not in error_msg.lower():
                logger.debug(f"[MySQL] Failed to release connection to pool: {e}, closing connection")
            try:
                conn.close()
            except Exception:
                pass
            with self._lock:
                if self._current_connections > 0:
                    self._current_connections -= 1
        except Exception as e:
            # 其他错误（例如池已满）
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
    """Convert various datetime formats to naive datetime object (consistent with ingestion_time format).
    
    Args:
        value: Input value (datetime, timestamp, string, etc.)
        
    Returns:
        naive datetime object (without timezone) or None, consistent with ingestion_time format
        
    Note:
        - Handles both Unix timestamps (seconds) and millisecond timestamps
        - Binance WebSocket returns millisecond timestamps (13 digits)
        - Invalid or out-of-range timestamps return None
        - All datetime objects are converted to naive datetime (no timezone) to match ingestion_time format
        - If input datetime has timezone info, it's converted to UTC first, then timezone is removed
    """
    if value is None:
        return None
    
    if isinstance(value, datetime):
        # 如果已经是 datetime 对象，确保转换为 naive datetime（不带时区）
        # 与 ingestion_time 格式保持一致
        if value.tzinfo is not None:
            # 如果有时区信息，先转换为 UTC，然后移除时区信息
            # 使用 UTC 作为标准，确保时间一致性
            utc_value = value.astimezone(timezone.utc)
            return utc_value.replace(tzinfo=None)
        else:
            # 如果没有时区信息，直接返回（已经是 naive datetime）
            return value
    
    if isinstance(value, (int, float)):
        # Handle timestamp (could be seconds or milliseconds)
        timestamp = float(value)
        
        # Check if timestamp is valid (not zero or negative)
        if timestamp <= 0:
            logger.warning("[MySQL] Invalid timestamp value: %s", timestamp)
            return None
        
        # Determine if timestamp is in seconds or milliseconds
        # Unix timestamps before year 2000 are around 946684800 (seconds)
        # Millisecond timestamps are typically 13 digits (e.g., 1700000000000)
        # If timestamp is less than a reasonable minimum (year 2000 in seconds), skip
        MIN_VALID_TIMESTAMP_SECONDS = 946684800  # 2000-01-01 00:00:00 UTC
        
        if timestamp < MIN_VALID_TIMESTAMP_SECONDS:
            # This is likely an invalid timestamp (too small)
            logger.warning("[MySQL] Timestamp value too small, likely invalid: %s", timestamp)
            return None
        
        # If timestamp is larger than reasonable seconds (year 2100), assume milliseconds
        MAX_REASONABLE_TIMESTAMP_SECONDS = 4102444800  # 2100-01-01 00:00:00 UTC
        
        if timestamp > MAX_REASONABLE_TIMESTAMP_SECONDS:
            # This is likely a millisecond timestamp, convert to seconds
            timestamp = timestamp / 1000.0
        
        try:
            # datetime.fromtimestamp() 返回本地时间的 naive datetime
            # 为了与 ingestion_time 保持一致，使用相同的方式
            return datetime.fromtimestamp(timestamp)
        except (ValueError, OSError) as e:
            logger.warning("[MySQL] Failed to convert timestamp %s to datetime: %s", value, e)
            return None
    
    if isinstance(value, str):
        # Try to parse string
        try:
            # Try ISO format first
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            # 如果解析出的 datetime 有时区信息，转换为 UTC 后移除时区
            if dt.tzinfo is not None:
                utc_dt = dt.astimezone(timezone.utc)
                return utc_dt.replace(tzinfo=None)
            return dt
        except ValueError:
            try:
                # Try common formats (这些格式都是 naive datetime)
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d']:
                    try:
                        return datetime.strptime(value, fmt)
                    except ValueError:
                        continue
            except Exception:
                pass
    
    return None


def _to_beijing_datetime(value: Any) -> Optional[datetime]:
    """Convert various datetime formats to naive datetime object in Beijing time (UTC+8).
    
    Args:
        value: Input value (datetime, timestamp, string, etc.)
        
    Returns:
        naive datetime object (without timezone) in Beijing time (UTC+8) or None
    
    Note:
        - Handles both Unix timestamps (seconds) and millisecond timestamps
        - Binance WebSocket returns millisecond timestamps (13 digits)
        - Invalid or out-of-range timestamps return None
        - All datetime objects are converted to Beijing time (UTC+8) as naive datetime
        - If input datetime has timezone info, it's converted to UTC+8 first, then timezone is removed
    """
    # 先使用 _to_datetime 函数将输入转换为 UTC naive datetime
    utc_naive_dt = _to_datetime(value)
    
    if utc_naive_dt is None:
        return None
    
    try:
        # 将 UTC naive datetime 转换为带 UTC 时区的 datetime
        utc_dt = utc_naive_dt.replace(tzinfo=timezone.utc)
        
        # 转换为北京时区 (UTC+8)
        beijing_tz = timezone(timedelta(hours=8))
        beijing_dt = utc_dt.astimezone(beijing_tz)
        
        # 移除时区信息，返回 naive datetime
        return beijing_dt.replace(tzinfo=None)
    except Exception as e:
        logger.warning("[MySQL] Failed to convert to Beijing time: %s", e)
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
    
    def cleanup_old_klines(self, days: int = 2) -> Dict[str, int]:
        """清理超过指定天数的K线数据
        
        Args:
            days: 保留天数，超过该天数的数据将被删除
            
        Returns:
            Dict[str, int]: 各表清理的记录数
        """
        result = {}
        
        def _cleanup(conn, days):
            # 计算截止时间
            cutoff_time = datetime.now(timezone(timedelta(hours=8))) - timedelta(days=days)
            logger.info(f"[KlineCleanup] Cleaning up klines older than {cutoff_time} from all tables")
            
            for interval, table_name in self.market_klines_tables.items():
                try:
                    cursor = conn.cursor()
                    sql = f"DELETE FROM `{table_name}` WHERE `event_time` < %s"
                    affected_rows = cursor.execute(sql, (cutoff_time,))
                    result[interval] = affected_rows
                    logger.info(f"[KlineCleanup] Cleaned {affected_rows} records from {table_name}")
                    cursor.close()
                except Exception as e:
                    logger.error(f"[KlineCleanup] Error cleaning {table_name}: {e}")
                    result[interval] = 0
            
            return result
        
        try:
            return self._with_connection(_cleanup, days)
        except Exception as e:
            logger.error(f"[KlineCleanup] Failed to cleanup klines: {e}")
            return result

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
                
                # 判断是否为网络/协议错误或死锁错误，需要重试
                # 包括 "Packet sequence number wrong" 错误，这通常表示连接状态不一致
                # 包括 MySQL 死锁错误 (1213)，这是一种需要重试的资源竞争错误
                # 包括 "read of closed file" 错误，这通常表示底层连接已关闭
                is_network_error = any(keyword in error_msg.lower() for keyword in [
                    'connection', 'broken', 'lost', 'timeout', 'reset', 'gone away',
                    'operationalerror', 'interfaceerror', 'packet sequence', 'internalerror',
                    'deadlock found', 'read of closed file'
                ]) or any(keyword in error_type.lower() for keyword in [
                    'connection', 'timeout', 'operationalerror', 'interfaceerror', 'internalerror',
                    'valueerror'
                ]) or (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213)
                
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
                    # 计算等待时间
                    # 为死锁错误使用特殊的重试策略（更长的初始延迟和更慢的增长）
                    if is_network_error and (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213 or 'deadlock' in error_msg.lower()):
                        # 死锁错误：初始延迟1秒，增长因子1.5（更慢的增长）
                        wait_time = 1.0 * (1.5 ** attempt)
                        logger.warning(
                            f"[MySQL] Deadlock error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    else:
                        # 其他错误使用原有指数退避策略
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
                    if result is None:
                        return False
                    elif isinstance(result, dict):
                        # 字典格式游标，获取第一个值
                        return list(result.values())[0] > 0 if result else False
                    elif isinstance(result, (list, tuple)):
                        # 元组格式游标
                        return result[0] > 0 if len(result) > 0 else False
                    else:
                        return int(result) > 0 if result else False
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
        - 直接查询指定的symbol列表
        - 由于symbol是主键，每个交易对只有一条记录
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
            FROM `{self.market_ticker_table}`
            WHERE symbol IN ({placeholders})
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
    
    def upsert_market_tickers(self, rows: Iterable[Dict[str, Any]]) -> None:
        """更新或插入市场行情数据（upsert操作）。
        
        功能说明：
        1. 筛选出以USDT结尾的交易对
        2. 对每一条接收的symbol数据都执行upsert操作（无去重，每条数据都处理）
        3. 查询数据库中已有的symbol数据，获取open_price和update_price_date信息
        4. 根据已有open_price计算涨跌幅相关字段（price_change, price_change_percent, side等）
        5. 对每条数据执行UPDATE操作，如果symbol不存在则执行INSERT操作
        
        核心逻辑：
        - 数据接收：从MarketTickerStream接收原始行情数据
        - 数据过滤：只处理USDT交易对
        - 数据保护：移除接口数据中的open_price和update_price_date字段，这些字段只能由异步价格刷新服务更新
        - 价格计算：基于数据库中已有的open_price计算涨跌幅指标
        - 数据存储：对每条数据执行UPDATE或INSERT操作，确保ingestion_time字段被正确更新
        
        数据处理规则：
        1. 时间字段规范化：将event_time, stats_open_time, stats_close_time转换为datetime对象
        2. 字段类型保证：确保DOUBLE字段使用0.0作为默认值，BIGINT字段使用0作为默认值，String字段使用空字符串作为默认值
        3. ingestion_time更新：无论UPDATE还是INSERT操作，都会更新ingestion_time为当前时间
        4. open_price保护：首次插入时设置为0.0且update_price_date为None，表示"未设置"状态
        
        
        设计决策：
        - 取消symbol去重：每条接收到的数据都会被处理，确保数据的实时性和完整性
        - open_price管理：采用异步价格刷新服务更新，避免接口数据覆盖开盘价
        - 涨跌幅计算：只有当数据库中存在有效open_price时才计算涨跌幅
        
        Args:
            rows: 市场行情数据的迭代器，每个元素是包含行情信息的字典
        
        Returns:
            None
        """
        logger.info("[MySQL] Starting upsert_market_tickers")
        
        if not rows:
            logger.info("[MySQL] No rows provided for upsert, returning")
            return
        
        # 筛选出USDT交易对：只处理以"USDT"结尾的交易对
        # 这是业务需求，系统只关注USDT计价的交易对
        rows_list = list(rows)
        usdt_rows = [row for row in rows_list if row.get("symbol", "").endswith("USDT")]
        logger.info("[MySQL] 从%d条总数据中筛选出%d条USDT交易对数据", len(rows_list), len(usdt_rows))
        
        if not usdt_rows:
            logger.debug("[MySQL] No USDT symbols to upsert")
            return
        
        # 数据处理列表：存储经过预处理的symbol数据
        # 注意：根据业务需求，不再对同一批数据中的重复symbol进行去重
        # 每条接收到的数据都会被处理，确保数据的实时性和完整性
        processed_rows = []
        
        for row in usdt_rows:
            normalized = dict(row)
            
            symbol = normalized.get("symbol")
            if not symbol:
                logger.debug("[MySQL] Skipping row without symbol: %s", row)
                continue
            
            # 重要：移除接口数据中的 open_price 和 update_price_date 字段
            # 数据保护机制：这两个字段只能由异步价格刷新服务(price_refresh_service)更新
            # 避免接口数据覆盖开盘价，确保涨跌幅计算的准确性
            if "open_price" in normalized:
                del normalized["open_price"]
                logger.debug("[MySQL] 移除了%s的open_price字段(该字段只能由异步价格刷新服务更新)", symbol)
            if "update_price_date" in normalized:
                del normalized["update_price_date"]
                logger.debug("[MySQL] 移除了%s的update_price_date字段(该字段只能由异步价格刷新服务更新)", symbol)
            
            normalized["event_time"] = _to_beijing_datetime(normalized.get("event_time"))
            normalized["stats_open_time"] = _to_beijing_datetime(normalized.get("stats_open_time"))
            normalized["stats_close_time"] = _to_beijing_datetime(normalized.get("stats_close_time"))
            
            logger.debug("[MySQL] Adding symbol %s to upsert list", symbol)
            processed_rows.append((symbol, normalized))
        
        logger.debug("[MySQL] Processed %d USDT symbols for upsert", len(processed_rows))
        
        if not processed_rows:
            logger.debug("[MySQL] No symbols to upsert after processing, returning")
            return
        
        # 获取所有需要处理的symbol列表
        symbols_to_process = [symbol for symbol, _ in processed_rows]
        
        # 获取数据库中已存在的symbol数据，用于计算价格变化
        existing_data = self.get_existing_symbol_data(symbols_to_process)
        logger.debug("[MySQL] Retrieved existing data for %d symbols", len(existing_data))
        
        # 处理每条symbol数据，执行UPDATE或INSERT操作
        total_upserted = 0
        total_updated = 0
        total_inserted = 0
        total_failed = 0
        
        # 使用整个SDK返回的批次作为一个批量处理单元
        logger.debug("[MySQL] Processing %d symbols as one batch (SDK returned batch)", len(processed_rows))
        
        def _execute_upsert_batch(conn, batch):
            nonlocal total_upserted, total_updated, total_inserted, total_failed
            
            # 准备批量插入的SQL语句
            insert_sql = f"""
            INSERT INTO `{self.market_ticker_table}` 
            (`event_time`, `symbol`, `price_change`, `price_change_percent`, 
             `side`, `change_percent_text`, `average_price`, `last_price`, 
             `last_trade_volume`, `open_price`, `high_price`, `low_price`, 
             `base_volume`, `quote_volume`, `stats_open_time`, `stats_close_time`, 
             `first_trade_id`, `last_trade_id`, `trade_count`, `update_price_date`,
             `ingestion_time`)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                event_time = VALUES(event_time),
                price_change = VALUES(price_change),
                price_change_percent = VALUES(price_change_percent),
                side = VALUES(side),
                change_percent_text = VALUES(change_percent_text),
                average_price = VALUES(average_price),
                last_price = VALUES(last_price),
                last_trade_volume = VALUES(last_trade_volume),
                high_price = VALUES(high_price),
                low_price = VALUES(low_price),
                base_volume = VALUES(base_volume),
                quote_volume = VALUES(quote_volume),
                stats_open_time = VALUES(stats_open_time),
                stats_close_time = VALUES(stats_close_time),
                first_trade_id = VALUES(first_trade_id),
                last_trade_id = VALUES(last_trade_id),
                trade_count = VALUES(trade_count),
                ingestion_time = VALUES(ingestion_time)
                /* 注意：不更新open_price和update_price_date字段，这些字段由异步价格刷新服务管理 */
            """
            
            batch_params = []
            valid_symbols = []
            
            # 预处理所有批次数据
            for symbol, normalized in batch:
                try:
                    logger.debug("[MySQL] Processing symbol: %s", symbol)
                    logger.debug("[MySQL] Raw data for %s: %s", symbol, normalized)
                    
                    # 获取当前报文的last_price
                    try:
                        current_last_price = float(normalized.get("last_price", 0))
                        logger.debug("[MySQL] Extracted last_price for %s: %f", symbol, current_last_price)
                    except (TypeError, ValueError) as e:
                        current_last_price = 0.0
                        logger.warning("[MySQL] Failed to extract last_price for %s, defaulting to 0: %s", symbol, e)
                    
                    # 判断是插入还是更新
                    existing_symbol_data = existing_data.get(symbol)
                    existing_open_price = existing_symbol_data.get("open_price") if existing_symbol_data else None
                    existing_update_price_date = existing_symbol_data.get("update_price_date") if existing_symbol_data else None
                    
                    logger.debug("[MySQL] Existing data for %s: open_price=%s, update_price_date=%s", 
                               symbol, existing_open_price, existing_update_price_date)
                    
                    # 关键逻辑：判断open_price是否已设置
                    # existing_open_price为None表示未设置（即使数据库中存储的是0.0，如果update_price_date为None也视为未设置）
                    # existing_open_price不为None且不为0表示已设置且有有效值
                    # 如果是更新且open_price有值（不为None且不为0），则计算涨跌幅相关字段
                    if existing_open_price is not None and existing_open_price != 0 and current_last_price != 0:
                        logger.debug("[MySQL] Calculating price change for %s (existing_open_price: %s, current_last_price: %s)", 
                                   symbol, existing_open_price, current_last_price)
                        
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
                            
                            logger.debug("[MySQL] Calculated price change for %s: %f (%.2f%%), side: %s", 
                                       symbol, price_change, price_change_percent, side)
                            
                            # 重要：保持原有的open_price和update_price_date，不更新
                            # 这两个字段只能由异步价格刷新服务更新，接口数据不能覆盖它们
                            normalized["price_change"] = price_change
                            normalized["price_change_percent"] = price_change_percent
                            normalized["side"] = side
                            normalized["change_percent_text"] = change_percent_text
                            normalized["open_price"] = existing_open_price_float  # 保留数据库中的值
                            normalized["update_price_date"] = existing_update_price_date  # 保留数据库中的值（可能为None）
                        except (TypeError, ValueError) as e:
                            logger.warning("[MySQL] Failed to calculate price change for symbol %s: %s", symbol, e)
                            # 计算失败时，设置为0.0（DOUBLE字段不能为None）
                            normalized["price_change"] = 0.0
                            normalized["price_change_percent"] = 0.0
                            normalized["side"] = ""  # String字段不能为None，使用空字符串
                            normalized["change_percent_text"] = ""  # String字段不能为None，使用空字符串
                            # 重要：保留数据库中的open_price和update_price_date
                            try:
                                existing_open_price_float = float(existing_open_price) if existing_open_price else 0.0
                            except (TypeError, ValueError):
                                existing_open_price_float = 0.0
                            normalized["open_price"] = existing_open_price_float
                            normalized["update_price_date"] = existing_update_price_date  # 保留数据库中的值（可能为None）
                    else:
                        logger.debug("[MySQL] Not calculating price change for %s (existing_open_price: %s, current_last_price: %s)", 
                                   symbol, existing_open_price, current_last_price)
                        
                        # 第一次插入或open_price未设置的情况
                        # DOUBLE字段设置为0.0而不是None
                        # 但逻辑上，open_price=0.0且update_price_date=None表示"未设置"
                        # 这样下次查询时，get_existing_symbol_data会返回open_price=None，保持原有判断逻辑正确
                        normalized["price_change"] = 0.0
                        normalized["price_change_percent"] = 0.0
                        normalized["side"] = ""  # String字段不能为None，使用空字符串
                        normalized["change_percent_text"] = ""  # String字段不能为None，使用空字符串
                        # 重要：如果是更新操作，保留数据库中的update_price_date；如果是插入操作，设置为None
                        normalized["open_price"] = 0.0  # 存储为0.0，但逻辑上视为"未设置"（因为update_price_date=None）
                        normalized["update_price_date"] = existing_update_price_date if existing_symbol_data else None
                    
                    # 确保所有DOUBLE字段不为None，使用0.0作为默认值
                    double_fields = [
                        "price_change", "price_change_percent", "average_price", "last_price",
                        "last_trade_volume", "open_price", "high_price", "low_price",
                        "base_volume", "quote_volume"
                    ]
                    for field in double_fields:
                        if normalized.get(field) is None:
                            normalized[field] = 0.0
                            logger.debug("[MySQL] Set %s.%s to 0.0 (was None)", symbol, field)
                    
                    # 确保BIGINT字段不为None
                    bigint_fields = ["first_trade_id", "last_trade_id", "trade_count"]
                    for field in bigint_fields:
                        if normalized.get(field) is None:
                            normalized[field] = 0
                            logger.debug("[MySQL] Set %s.%s to 0 (was None)", symbol, field)
                    
                    # 确保String字段不为None，使用空字符串作为默认值
                    string_fields = ["side", "change_percent_text"]
                    for field in string_fields:
                        if normalized.get(field) is None:
                            normalized[field] = ""
                            logger.debug("[MySQL] Set %s.%s to empty string (was None)", symbol, field)
                    
                    # DateTime字段处理：确保所有非Nullable的DateTime字段都不为None
                    # 所有时间字段都使用与 ingestion_time 相同的格式（naive datetime，不带时区）
                    datetime_fields = ["event_time", "stats_open_time", "stats_close_time"]
                    for field in datetime_fields:
                        field_value = normalized.get(field)
                        if field_value is None:
                            normalized[field] = datetime.now(timezone(timedelta(hours=8)))
                            logger.debug("[MySQL] 设置%s.%s为当前时间(原值为None)", symbol, field)
                        elif isinstance(field_value, datetime) and field_value.tzinfo is not None:
                            # 如果有时区信息，转换为 UTC 后移除时区（与 ingestion_time 格式一致）
                            normalized[field] = field_value.astimezone(timezone.utc).replace(tzinfo=None)
                            logger.debug("[MySQL] 转换%s.%s为naive datetime（移除时区信息，与ingestion_time格式一致）", symbol, field)
                    
                    # 如果 event_time 无效，跳过这条记录（event_time 是必需字段）
                    if normalized.get("event_time") is None:
                        logger.warning(
                            "[MySQL] Skipping market ticker for symbol %s: invalid event_time value",
                            symbol
                        )
                        continue
                    
                    logger.debug("[MySQL] Final normalized data for %s: %s", symbol, normalized)
                    
                    # 处理open_price和update_price_date字段
                    insert_open_price = normalized.get("open_price", 0.0)
                    insert_update_price_date = normalized.get("update_price_date")
                    
                    # 如果是新插入（existing_symbol_data不存在），确保open_price为0.0，update_price_date为None
                    if not existing_symbol_data:
                        insert_open_price = 0.0
                        insert_update_price_date = None
                        logger.debug("[MySQL] 设置%s的open_price为0.0，update_price_date为None（新插入，未设置状态）", symbol)
                    
                    # 准备插入参数
                    insert_params = (
                        normalized.get("event_time"),
                        symbol,
                        normalized.get("price_change", 0.0),
                        normalized.get("price_change_percent", 0.0),
                        normalized.get("side", ""),
                        normalized.get("change_percent_text", ""),
                        normalized.get("average_price", 0.0),
                        normalized.get("last_price", 0.0),
                        normalized.get("last_trade_volume", 0.0),
                        insert_open_price,
                        normalized.get("high_price", 0.0),
                        normalized.get("low_price", 0.0),
                        normalized.get("base_volume", 0.0),
                        normalized.get("quote_volume", 0.0),
                        normalized.get("stats_open_time"),
                        normalized.get("stats_close_time"),
                        normalized.get("first_trade_id", 0),
                        normalized.get("last_trade_id", 0),
                        normalized.get("trade_count", 0),
                        insert_update_price_date,
                        _to_beijing_datetime(datetime.now(timezone.utc))  # ingestion_time (converted to Beijing time UTC+8)
                    )
                    
                    batch_params.append(insert_params)
                    valid_symbols.append(symbol)
                    
                except Exception as e:
                    logger.error("[MySQL] Failed to prepare data for symbol %s: %s", symbol, e, exc_info=True)
                    total_failed += 1
                    continue
            
            # 如果没有有效的数据，直接返回
            if not batch_params:
                logger.debug("[MySQL] No valid data to upsert in this batch")
                return
            
            cursor = None
            try:
                # 在执行SQL前检查连接是否健康
                try:
                    # 尝试ping连接以检查是否有效，如果连接断开则自动重新连接
                    conn.ping(reconnect=True)
                    logger.debug("[MySQL] Connection ping successful for batch upsert")
                except (AttributeError, Exception) as ping_error:
                    # 连接已断开，抛出异常让外层重试机制处理
                    logger.warning("[MySQL] Connection is not healthy for batch upsert: %s, will retry", ping_error)
                    raise Exception(f"Connection lost: {ping_error}")
                
                # 再次检查连接状态，确保不会使用已关闭的连接
                if hasattr(conn, '_sock') and conn._sock is None:
                    logger.warning("[MySQL] Connection socket is closed for batch upsert, will retry")
                    raise Exception("Connection socket is closed")
                
                # 为批量操作创建游标
                cursor = conn.cursor()
                
                # 使用executemany执行批量插入/更新操作
                logger.debug("[MySQL] Executing batch upsert for %d symbols", len(batch_params))
                cursor.executemany(insert_sql, batch_params)
                
                # 批量操作影响的总行数（插入+更新）
                affected_rows = cursor.rowcount
                logger.debug("[MySQL] Batch upsert affected %d rows", affected_rows)
                
                # 由于无法直接区分插入和更新的数量（executemany返回的是影响的总行数）
                # 我们使用一种近似方法：假设大部分操作是更新
                # 如果需要精确统计，可以在批量操作后查询每个symbol的状态，但会增加额外开销
                total_upserted += affected_rows
                total_updated += affected_rows
                
                # 提交事务
                conn.commit()
                logger.debug("[MySQL] Batch upsert committed successfully")
                
            except (pymysql.err.InterfaceError, pymysql.err.OperationalError, pymysql.err.InternalError, ValueError, Exception) as db_error:
                # 连接错误或参数错误，关闭游标并抛出异常让外层重试
                if cursor:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                cursor = None
                error_type = type(db_error).__name__
                error_msg = str(db_error)
                
                # 检查是否为连接相关错误、内存视图错误或数据包序列错误
                if (isinstance(db_error, (pymysql.err.InterfaceError, pymysql.err.OperationalError, pymysql.err.InternalError)) or 
                    'interface' in error_type.lower() or 'operational' in error_type.lower() or 
                    'internalerror' in error_type.lower() or
                    'PyMemoryView_FromBuffer' in error_msg or 'buf must not be NULL' in error_msg or
                    'Packet sequence number' in error_msg):
                    logger.warning("[MySQL] Database connection or memory error for batch upsert: %s, will retry", db_error)
                    raise Exception(f"Database connection or memory error: {db_error}")
                else:
                    # 其他错误，继续抛出
                    raise
            
            # 立即关闭游标，释放资源
            if cursor:
                cursor.close()
                cursor = None
        
        # 对整个SDK返回的批次执行upsert操作
        batch_symbols = [symbol for symbol, _ in processed_rows]
        logger.debug("[MySQL] Processing SDK batch: symbols %s", ", ".join(batch_symbols))
        
        # 为SDK返回的批次创建一个闭包函数
        def _execute_current_batch(conn):
            return _execute_upsert_batch(conn, processed_rows)
        
        # 执行当前批次的upsert操作
        self._with_connection(_execute_current_batch)
        
        logger.debug("[MySQL] SDK batch completed: total_upserted=%d, total_updated=%d, total_inserted=%d, total_failed=%d", 
                   total_upserted, total_updated, total_inserted, total_failed)
        
        logger.debug("[MySQL] Upsert completed: %d total symbols processed, %d updated, %d inserted, %d failed",
            len(processed_rows), total_updated, total_inserted, total_failed
        )
        
        logger.debug(
            "[MySQL] Final stats: Upserted %d rows into %s",
            total_upserted, self.market_ticker_table
        )

    def update_open_price(self, symbol: str, open_price: float, update_date: datetime) -> bool:
        """更新指定symbol的open_price和update_price_date。
        
        Args:
            symbol: 交易对符号
            open_price: 开盘价（昨天的日K线收盘价）
            update_date: 更新日期时间参数（已废弃，方法内部始终使用当前本地时间，非UTC格式）
            
        Returns:
            是否更新成功
        """
        try:
            # 使用UTC+8时间作为update_price_date
            # 忽略传入的update_date参数，始终使用当前UTC+8时间
            utc8 = timezone(timedelta(hours=8))
            update_price_date = datetime.now(utc8)
            new_open_price = float(open_price)
            
            # 使用单个原子SQL语句完成更新，避免先查询后更新的两步操作
            # 这样可以减少死锁风险，因为所有操作都在一个事务中完成
            update_query = f"""
            UPDATE `{self.market_ticker_table}`
            SET `open_price` = %s,
                `price_change` = CASE 
                    WHEN `last_price` > 0 AND %s > 0 THEN `last_price` - %s
                    ELSE 0.0
                END,
                `price_change_percent` = CASE 
                    WHEN `last_price` > 0 AND %s > 0 THEN ((`last_price` - %s) / %s) * 100
                    ELSE 0.0
                END,
                `side` = CASE 
                    WHEN `last_price` > 0 AND %s > 0 THEN CASE WHEN ((`last_price` - %s) / %s) * 100 >= 0 THEN 'gainer' ELSE 'loser' END
                    ELSE ''
                END,
                `change_percent_text` = CASE 
                    WHEN `last_price` > 0 AND %s > 0 THEN CONCAT(FORMAT(((`last_price` - %s) / %s) * 100, 2), '%%')
                    ELSE ''
                END,
                `update_price_date` = %s
            WHERE `symbol` = %s
            """
            
            update_params = (
                new_open_price,  # open_price
                new_open_price,  # for price_change calculation
                new_open_price,  # for price_change calculation
                new_open_price,  # for price_change_percent calculation
                new_open_price,  # for price_change_percent calculation
                new_open_price,  # for price_change_percent calculation
                new_open_price,  # for side calculation
                new_open_price,  # for side calculation
                new_open_price,  # for side calculation
                new_open_price,  # for change_percent_text calculation
                new_open_price,  # for change_percent_text calculation
                new_open_price,  # for change_percent_text calculation
                update_price_date,  # update_price_date
                symbol  # where condition
            )
            
            def _execute_update(conn):
                cursor = conn.cursor()
                try:
                    cursor.execute(update_query, update_params)
                    return cursor.rowcount > 0
                finally:
                    cursor.close()
            
            update_success = self._with_connection(_execute_update)
            
            if update_success:
                logger.debug(
                    "[MySQL] Updated open_price for symbol %s: %s | update_price_date: %s (当前时间)",
                    symbol,
                    new_open_price,
                    update_price_date.strftime('%Y-%m-%d %H:%M:%S')
                )
            else:
                logger.warning("[MySQL] No rows updated for symbol %s", symbol)
            
            return update_success
            
        except Exception as e:
            logger.error("[MySQL] Failed to update open_price for symbol %s: %s", symbol, e, exc_info=True)
            return False
    
    def get_symbols_needing_price_refresh(self) -> List[str]:
        """获取需要刷新价格的symbol列表。
        
        刷新逻辑：
        - 获取 update_price_date 为空或比当前时间早1小时以上的 symbol（去重）
        - 返回去重后的 symbol 列表
        
        Returns:
            需要刷新价格的 symbol 列表
        """
        try:
            # 计算1小时前的时间
            one_hour_ago = datetime.now(timezone(timedelta(hours=8))) - timedelta(hours=1)
            
            sql = f"""
            SELECT `symbol`
            FROM `{self.market_ticker_table}`
            WHERE `update_price_date` IS NULL 
               OR `update_price_date` < %s
            ORDER BY `event_time`
            """
            
            def _execute_query(conn):
                cursor = conn.cursor()
                try:
                    # 获取执行的真实SQL（包含参数值）
                    real_sql = cursor.mogrify(sql, (one_hour_ago,))
                    logger.info("[MySQL] Executing get_symbols_needing_price_refresh SQL: %s", real_sql)
                    
                    cursor.execute(sql, (one_hour_ago,))
                    rows = cursor.fetchall()
                    # 处理返回结果（可能是元组或字典）
                    symbols = []
                    for row in rows:
                        if isinstance(row, dict):
                            symbols.append(row['symbol'])
                        elif isinstance(row, (list, tuple)):
                            symbols.append(row[0])
                        else:
                            symbols.append(str(row))
                    return symbols
                finally:
                    cursor.close()
            
            symbols = self._with_connection(_execute_query)
            logger.debug(
                "[MySQL] Found %s symbols needing price refresh (update_price_date is NULL or older than 1 hour)",
                len(symbols)
            )
            return symbols if symbols else []
        except Exception as e:
            logger.error("[MySQL] Failed to get symbols needing price refresh: %s", e)
            return []

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
            `position` TINYINT UNSIGNED DEFAULT 0 COMMENT '排名位置（1表示第1名，2表示第2名，以此类推）',
            `price` DOUBLE DEFAULT 0.0,
            `change_percent` DOUBLE DEFAULT 0.0,
            `quote_volume` DOUBLE DEFAULT 0.0,
            `timeframes` VARCHAR(200) DEFAULT '',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX `idx_symbol_side` (`symbol`, `side`),
            INDEX `idx_event_time` (`event_time`),
            INDEX `idx_position` (`position`)
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
            cutoff_time = datetime.now(timezone(timedelta(hours=8))) - timedelta(seconds=time_window_seconds)
            
            query = f"""
            SELECT 
                `symbol`, `contract_symbol`, `name`, `exchange`, `side`, `position`, 
                `price`, `change_percent`, `quote_volume`, `timeframes`, `updated_at`
            FROM `{self.leaderboard_table}`
            WHERE `side` = %s 
            AND `event_time` >= %s
            ORDER BY `position` ASC
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
                            'position': row[5] if len(row) > 5 else 0,
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
    
    def calculate_leaderboard_from_tickers(
        self,
        top_n: int = 10,
        time_window_seconds: int = 2
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """从市场行情数据计算涨跌榜。
        
        从 24_market_tickers 表查询最近时间窗口内的数据，计算涨跌幅并排序。
        
        Args:
            top_n: 返回前N名数量
            time_window_seconds: 时间窗口（秒），只查询最近N秒内的数据
            
        Returns:
            (long_rows, short_rows) 元组，分别包含涨幅榜和跌幅榜数据
        """
        try:
            cutoff_time = datetime.now(timezone(timedelta(hours=8))) - timedelta(seconds=time_window_seconds)
            
            query = f"""
            SELECT 
                symbol, last_price, open_price, quote_volume, event_time
            FROM `{self.market_ticker_table}`
            WHERE event_time >= %s
            AND open_price > 0
            AND last_price > 0
            ORDER BY event_time DESC
            """
            
            def _execute_query(conn):
                cursor = conn.cursor()
                try:
                    cursor.execute(query, (cutoff_time,))
                    rows = cursor.fetchall()
                    
                    # 转换为字典列表
                    tickers = []
                    for row in rows:
                        if isinstance(row, dict):
                            tickers.append(row)
                        elif isinstance(row, (list, tuple)):
                            tickers.append({
                                'symbol': row[0] if len(row) > 0 else '',
                                'last_price': float(row[1]) if len(row) > 1 and row[1] is not None else 0.0,
                                'open_price': float(row[2]) if len(row) > 2 and row[2] is not None else 0.0,
                                'quote_volume': float(row[3]) if len(row) > 3 and row[3] is not None else 0.0,
                                'event_time': row[4] if len(row) > 4 else None,
                            })
                    
                    return tickers
                finally:
                    cursor.close()
            
            tickers = self._with_connection(_execute_query)
            
            if not tickers:
                logger.debug("[MySQL] No tickers found for leaderboard calculation")
                return [], []
            
            # 计算涨跌幅并分组（每个symbol只保留最新的记录）
            symbol_data = {}
            for ticker in tickers:
                symbol = ticker.get('symbol')
                if not symbol:
                    continue
                
                # 如果该symbol已有数据，保留最新的（event_time更晚的）
                if symbol in symbol_data:
                    existing_time = symbol_data[symbol].get('event_time')
                    current_time = ticker.get('event_time')
                    if existing_time and current_time and current_time < existing_time:
                        continue
                
                open_price = ticker.get('open_price', 0.0)
                last_price = ticker.get('last_price', 0.0)
                
                # 计算涨跌幅
                if open_price > 0:
                    change_percent = ((last_price - open_price) / open_price) * 100.0
                else:
                    change_percent = 0.0
                
                symbol_data[symbol] = {
                    'symbol': symbol,
                    'contract_symbol': symbol,
                    'name': symbol.replace('USDT', '') if symbol.endswith('USDT') else symbol,
                    'exchange': 'BINANCE_FUTURES',
                    'price': last_price,
                    'change_percent': change_percent,
                    'quote_volume': ticker.get('quote_volume', 0.0),
                    'timeframes': '',
                    'event_time': ticker.get('event_time'),
                }
            
            # 转换为列表并排序
            ticker_list = list(symbol_data.values())
            
            # 涨幅榜（change_percent >= 0，按降序排序）
            gainers = [
                {**item, 'position': idx + 1}
                for idx, item in enumerate(
                    sorted(
                        [t for t in ticker_list if t['change_percent'] >= 0],
                        key=lambda x: x['change_percent'],
                        reverse=True
                    )[:top_n]
                )
            ]
            
            # 跌幅榜（change_percent < 0，按升序排序，绝对值大的在前）
            losers = [
                {**item, 'position': idx + 1}
                for idx, item in enumerate(
                    sorted(
                        [t for t in ticker_list if t['change_percent'] < 0],
                        key=lambda x: x['change_percent'],
                        reverse=False
                    )[:top_n]
                )
            ]
            
            logger.debug(
                "[MySQL] Calculated leaderboard: %d gainers, %d losers",
                len(gainers), len(losers)
            )
            
            return gainers, losers
            
        except Exception as e:
            logger.error("[MySQL] Failed to calculate leaderboard from tickers: %s", e, exc_info=True)
            return [], []
    
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
                event_time = datetime.now(timezone(timedelta(hours=8)))
                
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
                             `side`, `position`, `price`, `change_percent`, `quote_volume`, `timeframes`)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                            `event_time` = VALUES(`event_time`),
                            `position` = VALUES(`position`),
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
                                row.get('position', 0),
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
                             `side`, `position`, `price`, `change_percent`, `quote_volume`, `timeframes`)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                            `event_time` = VALUES(`event_time`),
                            `position` = VALUES(`position`),
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
                                row.get('position', 0),
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
            cutoff_time = datetime.now(timezone(timedelta(hours=8))) - timedelta(minutes=minutes)
            
            def _execute_cleanup(conn):
                cursor = conn.cursor()
                try:
                    # 查询要删除的记录数
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM `{self.leaderboard_table}`
                        WHERE event_time < %s
                    """, (cutoff_time,))
                    
                    # 正确处理 fetchone() 的返回值（可能是元组、字典或 None）
                    row = cursor.fetchone()
                    if row is None:
                        count_before = 0
                    elif isinstance(row, dict):
                        # 字典格式游标
                        count_before = row.get('COUNT(*)', 0) or row.get(list(row.keys())[0], 0)
                    elif isinstance(row, (list, tuple)):
                        # 元组格式游标
                        count_before = row[0] if len(row) > 0 else 0
                    else:
                        count_before = int(row) if row else 0
                    
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

