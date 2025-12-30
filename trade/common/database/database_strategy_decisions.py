"""
Strategy decision database table operation module - strategy_decisions table

This module provides CRUD operations for strategy decisions.

Main components:
- StrategyDecisionsDatabase: Strategy decision data operations
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Callable
import pymysql
from .database_basic import create_pooled_db
import trade.common.config as app_config
from .database_init import STRATEGY_DECISIONS_TABLE

logger = logging.getLogger(__name__)


class StrategyDecisionsDatabase:
    """
    Strategy decision data operations
    
    Encapsulates all database operations for the strategy_decisions table.
    """
    
    def __init__(self, pool=None):
        """
        Initialize strategy decision database operations
        
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
        
        self.strategy_decisions_table = STRATEGY_DECISIONS_TABLE
    
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
                
                if connection_acquired and conn:
                    try:
                        try:
                            conn.rollback()
                        except Exception as rollback_error:
                            logger.debug(f"[StrategyDecisions] Error rolling back transaction: {rollback_error}")
                        
                        try:
                            conn.close()
                        except Exception as close_error:
                            logger.debug(f"[StrategyDecisions] Error closing connection: {close_error}")
                        finally:
                            conn = None
                    except Exception as close_error:
                        logger.error(f"[StrategyDecisions] Critical error closing failed connection: {close_error}")
                        conn = None
                
                if attempt < max_retries - 1:
                    if not is_network_error:
                        raise
                    
                    is_deadlock = (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213) or 'deadlock' in error_msg.lower()
                    if is_deadlock:
                        wait_time = 1.0 * (1.5 ** attempt)
                        logger.warning(
                            f"[StrategyDecisions] Deadlock error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    else:
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(
                            f"[StrategyDecisions] Network error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    
                    import time
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"[StrategyDecisions] Failed after {max_retries} attempts: "
                        f"{error_type}: {error_msg}"
                    )
                    raise
            finally:
                if connection_acquired and conn:
                    try:
                        logger.warning(
                            f"[StrategyDecisions] Connection not closed in finally block, closing it"
                        )
                        try:
                            conn.rollback()
                            conn.close()
                        except Exception:
                            pass
                    except Exception as final_error:
                        logger.debug(f"[StrategyDecisions] Error in finally block: {final_error}")
    
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
    
    def add_strategy_decision(
        self,
        model_id: str,
        strategy_name: str,
        strategy_type: str,
        signal: str,
        symbol: Optional[str] = None,
        quantity: Optional[float] = None,
        leverage: Optional[int] = None,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        justification: Optional[str] = None
    ):
        """
        Add strategy decision record
        
        Args:
            model_id: Model ID (UUID string)
            strategy_name: Strategy name
            strategy_type: Strategy type ('buy' or 'sell')
            signal: Trading signal
            symbol: Contract name (optional)
            quantity: Quantity (optional, if provided will be converted to integer)
            leverage: Leverage (optional)
            price: Expected price (optional)
            stop_price: Trigger price (optional)
            justification: Trigger reason (optional)
        """
        try:
            decision_id = self._generate_id()
            
            # Ensure quantity is integer (if provided)
            if quantity is not None:
                quantity = int(float(quantity))
            
            # Use UTC+8 timezone (Beijing time), convert to naive datetime for storage
            beijing_tz = timezone(timedelta(hours=8))
            current_time = datetime.now(beijing_tz).replace(tzinfo=None)
            
            self.insert_rows(
                self.strategy_decisions_table,
                [[decision_id, model_id, strategy_name, strategy_type, signal, symbol, quantity, leverage, price, stop_price, justification, current_time]],
                ["id", "model_id", "strategy_name", "strategy_type", "signal", "symbol", "quantity", "leverage", "price", "stop_price", "justification", "created_at"]
            )
            logger.debug(f"[StrategyDecisions] Added strategy decision: model_id={model_id}, strategy_name={strategy_name}, signal={signal}, symbol={symbol}")
        except Exception as e:
            logger.error(f"[StrategyDecisions] Failed to add strategy decision: {e}")
            raise
    
    def add_strategy_decisions_batch(
        self,
        model_id: str,
        strategy_name: str,
        strategy_type: str,
        decisions: List[Dict]
    ):
        """
        Batch add strategy decision records
        
        Args:
            model_id: Model ID (UUID string)
            strategy_name: Strategy name
            strategy_type: Strategy type ('buy' or 'sell')
            decisions: Decision list, each decision is a dictionary containing signal, quantity, leverage, price, stop_price, justification and other fields
        """
        try:
            if not decisions:
                return
            
            beijing_tz = timezone(timedelta(hours=8))
            current_time = datetime.now(beijing_tz).replace(tzinfo=None)
            
            rows = []
            for decision in decisions:
                decision_id = self._generate_id()
                signal = decision.get('signal', '')
                symbol = decision.get('symbol')  # Get symbol field
                quantity = decision.get('quantity')
                # Ensure quantity is integer (if provided)
                if quantity is not None:
                    quantity = int(float(quantity))
                leverage = decision.get('leverage')
                price = decision.get('price')
                stop_price = decision.get('stop_price')
                justification = decision.get('justification') or decision.get('reason')  # Compatible with reason field
                
                rows.append([decision_id, model_id, strategy_name, strategy_type, signal, symbol, quantity, leverage, price, stop_price, justification, current_time])
            
            if rows:
                self.insert_rows(
                    self.strategy_decisions_table,
                    rows,
                    ["id", "model_id", "strategy_name", "strategy_type", "signal", "symbol", "quantity", "leverage", "price", "stop_price", "justification", "created_at"]
                )
                logger.info(f"[StrategyDecisions] Added {len(rows)} strategy decisions: model_id={model_id}, strategy_name={strategy_name}")
        except Exception as e:
            logger.error(f"[StrategyDecisions] Failed to add strategy decisions batch: {e}")
            raise
    
    def get_strategy_decisions_by_model_id(
        self,
        model_id: str,
        limit: Optional[int] = None,
        order_by: str = "created_at DESC"
    ) -> List[Dict]:
        """
        Query strategy decision records by model ID
        
        Args:
            model_id: Model ID (UUID string)
            limit: Limit number of results (optional)
            order_by: Sort order (default by creation time descending)
        
        Returns:
            Strategy decision record list
        """
        try:
            def _execute_query(conn):
                from pymysql import cursors
                cursor = conn.cursor(cursors.DictCursor)
                try:
                    sql = f"""
                        SELECT id, model_id, strategy_name, strategy_type, signal, symbol, quantity, 
                               leverage, price, stop_price, justification, created_at
                        FROM {self.strategy_decisions_table}
                        WHERE model_id = %s
                        ORDER BY {order_by}
                    """
                    if limit:
                        sql += f" LIMIT {limit}"
                    cursor.execute(sql, (model_id,))
                    rows = cursor.fetchall()
                    return [dict(row) for row in rows] if rows else []
                finally:
                    cursor.close()
            
            return self._with_connection(_execute_query)
        except Exception as e:
            logger.error(f"[StrategyDecisions] Failed to get strategy decisions for model {model_id}: {e}")
            return []

