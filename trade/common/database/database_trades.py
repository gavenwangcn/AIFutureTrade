"""
Trade record database table operation module - trades table

This module provides CRUD operations for trade records.

Main components:
- TradesDatabase: Trade record data operations
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Callable
import pymysql
from .database_basic import create_pooled_db
import trade.common.config as app_config
from .database_init import TRADES_TABLE

logger = logging.getLogger(__name__)


class TradesDatabase:
    """
    Trade record data operations
    
    Encapsulates all database operations for the trades table.
    """
    
    def __init__(self, pool=None):
        """
        Initialize trade record database operations
        
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
        
        self.trades_table = TRADES_TABLE
    
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
                            logger.debug(f"[Trades] Error rolling back transaction: {rollback_error}")
                        
                        # For all errors, close connection, DBUtils will automatically handle damaged connections
                        try:
                            conn.close()
                        except Exception as close_error:
                            logger.debug(f"[Trades] Error closing connection: {close_error}")
                        finally:
                            # Ensure connection reference is cleared, mark as processed even if close fails
                            conn = None
                    except Exception as close_error:
                        logger.error(f"[Trades] Critical error closing failed connection: {close_error}")
                        # Even if exception occurs, clear connection reference
                        conn = None
                
                if attempt < max_retries - 1:
                    if not is_network_error:
                        raise
                    
                    is_deadlock = (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213) or 'deadlock' in error_msg.lower()
                    if is_deadlock:
                        wait_time = 1.0 * (1.5 ** attempt)
                        logger.warning(
                            f"[Trades] Deadlock error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    else:
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(
                            f"[Trades] Network error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    
                    import time
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"[Trades] Failed after {max_retries} attempts: "
                        f"{error_type}: {error_msg}"
                    )
                    raise
            finally:
                if connection_acquired and conn:
                    try:
                        logger.warning(
                            f"[Trades] Connection not closed in finally block, closing it"
                        )
                        try:
                            conn.rollback()
                            conn.close()
                        except Exception:
                            pass
                    except Exception as final_error:
                        logger.debug(f"[Trades] Error in finally block: {final_error}")
    
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
    
    def add_trade(self, model_id: int, future: str, signal: str, quantity: float,
              price: float, leverage: int = 1, side: str = 'long', pnl: float = 0, fee: float = 0,
              model_id_mapping: Dict[int, str] = None):
        """
        Add trade record with fee
        
        Args:
            model_id: Model ID
            future: Trading pair symbol
            signal: Trading signal
            quantity: Quantity
            price: Price
            leverage: Leverage multiplier
            side: Direction (long/short)
            pnl: Profit and loss
            fee: Transaction fee
            model_id_mapping: Optional model ID mapping dictionary
        """
        try:
            if model_id_mapping is None:
                rows = self.query(f"SELECT id FROM models")
                model_id_mapping = {}
                for row in rows:
                    uuid_str = row[0]
                    int_id = abs(hash(uuid_str)) % (10 ** 9)
                    model_id_mapping[int_id] = uuid_str
            
            model_uuid = model_id_mapping.get(model_id)
            if not model_uuid:
                logger.warning(f"[Trades] Model {model_id} not found for trade record")
                return
            
            # Use UTC+8 timezone (Beijing time), convert to naive datetime for storage
            beijing_tz = timezone(timedelta(hours=8))
            current_time = datetime.now(beijing_tz).replace(tzinfo=None)
            
            trade_id = self._generate_id()
            self.insert_rows(
                self.trades_table,
                [[trade_id, model_uuid, future.upper(), signal, quantity, price, leverage, side, pnl, fee, current_time]],
                ["id", "model_id", "future", "signal", "quantity", "price", "leverage", "side", "pnl", "fee", "timestamp"]
            )
        except Exception as e:
            logger.error(f"[Trades] Failed to add trade: {e}")
            raise
    
    def get_today_sell_trades(self, model_id: str) -> List[Dict[str, Any]]:
        """
        获取当天的卖出交易记录（当天指从早上8点到第二天早上8点）
        
        Args:
            model_id: 模型ID（UUID格式）
            
        Returns:
            List[Dict]: 卖出交易记录列表，每个记录包含id, signal, pnl, timestamp等字段
        """
        try:
            def _execute_query(conn):
                cursor = conn.cursor()
                try:
                    # 获取当前时间（北京时间）
                    beijing_tz = timezone(timedelta(hours=8))
                    now = datetime.now(beijing_tz)
                    
                    # 计算当天的开始时间（今天早上8点）
                    today_start = now.replace(hour=8, minute=0, second=0, microsecond=0)
                    
                    # 如果当前时间早于8点，则使用昨天早上8点作为开始时间
                    if now.hour < 8:
                        today_start = today_start - timedelta(days=1)
                    
                    # 卖出交易信号列表
                    sell_signals = ['sell_to_long', 'sell_to_short', 'close_position', 'stop_loss', 'take_profit']
                    signals_placeholders = ','.join(['%s'] * len(sell_signals))
                    
                    # 查询当天的卖出交易记录，按时间倒序排列
                    sql = f"""
                    SELECT `id`, `signal`, `pnl`, `timestamp`
                    FROM `{self.trades_table}`
                    WHERE `model_id` = %s 
                    AND `signal` IN ({signals_placeholders})
                    AND `timestamp` >= %s
                    ORDER BY `timestamp` DESC
                    """
                    params = [model_id] + sell_signals + [today_start]
                    cursor.execute(sql, params)
                    rows = cursor.fetchall()
                    
                    trades = []
                    for row in rows:
                        # 处理字典格式（DictCursor）或元组格式（普通cursor）
                        if isinstance(row, dict):
                            trade_id = row.get('id')
                            signal = row.get('signal')
                            pnl = row.get('pnl')
                            timestamp = row.get('timestamp')
                        elif isinstance(row, (tuple, list)):
                            trade_id = row[0]
                            signal = row[1]
                            pnl = row[2]
                            timestamp = row[3]
                        else:
                            logger.warning(f"[Trades] Unexpected row format: {type(row)}")
                            continue
                        
                        trades.append({
                            'id': trade_id,
                            'signal': signal,
                            'pnl': float(pnl) if pnl is not None else 0.0,
                            'timestamp': timestamp
                        })
                    
                    return trades
                finally:
                    cursor.close()
            
            return self._with_connection(_execute_query)
        except Exception as e:
            logger.error(f"[Trades] Failed to get today sell trades for model {model_id}: {e}")
            return []
    
    def query(self, sql: str, params: tuple = None, as_dict: bool = False):
        """Execute a query and return results."""
        def _execute_query(conn):
            from pymysql import cursors
            if as_dict:
                cursor = conn.cursor(cursors.DictCursor)
            else:
                cursor = conn.cursor()
            try:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                rows = cursor.fetchall()
                if as_dict:
                    return [dict(row) for row in rows] if rows else []
                if rows and isinstance(rows[0], dict):
                    return [tuple(row.values()) for row in rows]
                return rows
            finally:
                cursor.close()
        return self._with_connection(_execute_query)
