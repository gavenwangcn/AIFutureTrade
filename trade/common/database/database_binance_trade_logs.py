"""
Binance trade logs database table operation module - binance_trade_logs table

This module provides CRUD operations for Binance trade logs.

Main components:
- BinanceTradeLogsDatabase: Binance trade logs data operations
"""

import logging
import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Callable
import pymysql
from .database_basic import create_pooled_db
import trade.common.config as app_config
from .database_init import BINANCE_TRADE_LOGS_TABLE

logger = logging.getLogger(__name__)


class BinanceTradeLogsDatabase:
    """
    Binance trade logs data operations
    
    Encapsulates all database operations for the binance_trade_logs table.
    """
    
    def __init__(self, pool=None):
        """
        Initialize Binance trade logs database operations
        
        Args:
            pool: Optional database connection pool, if not provided, create a new connection pool
        """
        if pool is None:
            self._pool = create_pooled_db(
                host=app_config.MYSQL_HOST,
                port=app_config.MYSQL_PORT,
                user=app_config.MYSQL_USER,
                password=app_config.MYSQL_PASSWORD,
                database=app_config.MYSQL_DATABASE,
                charset='utf8mb4',
                mincached=5,
                maxconnections=50,
                blocking=True
            )
        else:
            self._pool = pool
        
        self.binance_trade_logs_table = BINANCE_TRADE_LOGS_TABLE
    
    def _with_connection(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function with a MySQL connection from the pool."""
        max_retries = 3
        retry_delay = 0.5
        
        for attempt in range(max_retries):
            conn = None
            connection_acquired = False
            try:
                conn = self._pool.connection()
                if not conn:
                    raise Exception("Failed to acquire MySQL connection")
                connection_acquired = True
                
                result = func(conn, *args, **kwargs)
                conn.commit()
                conn = None
                return result
                
            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                
                is_network_error = any(keyword in error_msg.lower() for keyword in [
                    'connection', 'broken', 'lost', 'timeout', 'reset', 'gone away',
                    'operationalerror', 'interfaceerror', 'packet sequence', 'internalerror',
                    'deadlock found', 'read of closed file'
                ]) or any(keyword in error_type.lower() for keyword in [
                    'connection', 'timeout', 'operationalerror', 'interfaceerror', 'internalerror',
                    'valueerror'
                ]) or (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213)
                
                # If connection has been acquired, need to handle connection (close it)
                # Regardless of exception type, ensure connection is properly released to prevent connection leak
                if connection_acquired and conn:
                    try:
                        # Rollback transaction
                        try:
                            conn.rollback()
                        except Exception as rollback_error:
                            logger.debug(f"[BinanceTradeLogs] Error rolling back transaction: {rollback_error}")
                        
                        # For all errors, close connection, DBUtils will automatically handle damaged connections
                        try:
                            conn.close()
                        except Exception as close_error:
                            logger.debug(f"[BinanceTradeLogs] Error closing connection: {close_error}")
                        finally:
                            # Ensure connection reference is cleared, mark as processed even if close fails
                            conn = None
                    except Exception as close_error:
                        logger.error(f"[BinanceTradeLogs] Critical error closing failed connection: {close_error}")
                        # Even if exception occurs, clear connection reference
                        conn = None
                
                if attempt < max_retries - 1:
                    if not is_network_error:
                        raise
                    
                    is_deadlock = (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213) or 'deadlock' in error_msg.lower()
                    if is_deadlock:
                        wait_time = 1.0 * (1.5 ** attempt)
                        logger.warning(
                            f"[BinanceTradeLogs] Deadlock error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    else:
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(
                            f"[BinanceTradeLogs] Network error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    
                    import time
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"[BinanceTradeLogs] Failed after {max_retries} attempts: "
                        f"{error_type}: {error_msg}"
                    )
                    raise
            finally:
                if connection_acquired and conn:
                    try:
                        logger.warning(
                            f"[BinanceTradeLogs] Connection not closed in finally block, closing it"
                        )
                        try:
                            conn.rollback()
                            conn.close()
                        except Exception:
                            pass
                    except Exception as final_error:
                        logger.debug(f"[BinanceTradeLogs] Error in finally block: {final_error}")
    
    def _generate_id(self) -> str:
        """Generate a unique ID (UUID)"""
        return str(uuid.uuid4())
    
    def insert_rows(self, table: str, rows: List[List[Any]], column_names: List[str]) -> None:
        """Insert rows into a table."""
        if not rows:
            return
        
        def _execute_insert(conn):
            cursor = conn.cursor()
            try:
                columns_str = ', '.join([f"`{col}`" for col in column_names])
                placeholders = ', '.join(['%s'] * len(column_names))
                sql = f"INSERT INTO `{table}` ({columns_str}) VALUES ({placeholders})"
                cursor.executemany(sql, rows)
            finally:
                cursor.close()
        
        self._with_connection(_execute_insert)
    
    def add_binance_trade_log(self, model_id: Optional[str] = None, conversation_id: Optional[str] = None, 
                              trade_id: Optional[str] = None, type: str = "test", method_name: str = "",
                              param: Optional[Dict[str, Any]] = None, response_context: Optional[Dict[str, Any]] = None,
                              response_type: Optional[str] = None, error_context: Optional[str] = None):
        """
        Add Binance trade log record
        
        Args:
            model_id: Model ID (UUID string)
            conversation_id: Conversation ID (UUID string)
            trade_id: Trade ID (UUID string)
            type: Interface type, 'test' or 'real'
            method_name: Method name, such as 'stop_loss_trade', 'take_profit_trade', etc.
            param: Input parameters for calling interface, dictionary format
            response_context: Content returned by interface, dictionary format
            response_type: Interface return status code, such as '200', '4XX', '5XX', etc.
            error_context: When interface return status is not 200, record related return error information
        """
        try:
            log_id = self._generate_id()
            
            # Convert dictionary to JSON string
            param_json = json.dumps(param) if param else None
            response_json = json.dumps(response_context) if response_context else None
            
            # Use UTC+8 timezone (Beijing time), convert to naive datetime for storage
            beijing_tz = timezone(timedelta(hours=8))
            current_time = datetime.now(beijing_tz).replace(tzinfo=None)
            
            self.insert_rows(
                self.binance_trade_logs_table,
                [[log_id, model_id, conversation_id, trade_id, type, method_name, param_json, response_json, response_type, error_context, current_time]],
                ["id", "model_id", "conversation_id", "trade_id", "type", "method_name", "param", "response_context", "response_type", "error_context", "created_at"]
            )
        except Exception as e:
            logger.error(f"[BinanceTradeLogs] Failed to add binance trade log: {e}")
            # Don't throw exception, avoid affecting main flow
