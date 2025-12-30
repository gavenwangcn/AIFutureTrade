"""
Strategy database table operation module - strategys table and model_strategy table

This module provides CRUD operations for strategy data, including:
1. Strategy queries
2. Model-strategy association queries

Main components:
- StrategysDatabase: Strategy data operations
"""

import logging
from typing import List, Dict, Optional, Any, Callable
from .database_basic import create_pooled_db
import trade.common.config as app_config
import pymysql

logger = logging.getLogger(__name__)


class StrategysDatabase:
    """
    Strategy data operations
    
    Encapsulates all database operations for strategys and model_strategy tables.
    """
    
    def __init__(self, pool=None):
        """
        Initialize strategy database operations
        
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
        
        self.strategys_table = "strategys"
        self.model_strategy_table = "model_strategy"
    
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
                            logger.debug(f"[Strategys] Error rolling back transaction: {rollback_error}")
                        
                        # For all errors, close connection, DBUtils will automatically handle damaged connections
                        try:
                            conn.close()
                        except Exception as close_error:
                            logger.debug(f"[Strategys] Error closing connection: {close_error}")
                        finally:
                            # Ensure connection reference is cleared, mark as processed even if close fails
                            conn = None
                    except Exception as close_error:
                        logger.error(f"[Strategys] Critical error closing failed connection: {close_error}")
                        # Even if exception occurs, clear connection reference
                        conn = None
                
                if attempt < max_retries - 1:
                    if is_network_error and (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213 or 'deadlock' in error_msg.lower()):
                        wait_time = 1.0 * (1.5 ** attempt)
                        logger.warning(
                            f"[Strategys] Deadlock error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    else:
                        wait_time = retry_delay * (2 ** attempt)
                        if is_network_error:
                            logger.warning(
                                f"[Strategys] Network error on attempt {attempt + 1}/{max_retries}: "
                                f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                            )
                        else:
                            logger.warning(
                                f"[Strategys] Error on attempt {attempt + 1}/{max_retries}: "
                                f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                            )
                    
                    import time
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"[Strategys] Failed after {max_retries} attempts. Last error: {error_type}: {error_msg}"
                    )
                    raise
            finally:
                if connection_acquired and conn:
                    try:
                        logger.warning(
                            f"[Strategys] Connection not closed in finally block, closing it"
                        )
                        try:
                            conn.rollback()
                            conn.close()
                        except Exception:
                            pass
                    except Exception as final_error:
                        logger.debug(f"[Strategys] Error in finally block: {final_error}")
    
    def query(self, sql: str, params: tuple = None, as_dict: bool = False) -> List:
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
    
    def get_model_strategies(self, model_id: str, strategy_type: str) -> List[Dict]:
        """
        Get list of strategies associated with a model (sorted by priority and creation time)
        
        Args:
            model_id: Model ID (UUID string)
            strategy_type: Strategy type, 'buy' or 'sell'
        
        Returns:
            List[Dict]: Strategy list, each element contains:
                - id: Association ID
                - model_id: Model ID
                - strategy_id: Strategy ID
                - type: Strategy type
                - priority: Priority
                - created_at: Creation time
                - strategy_name: Strategy name
                - strategy_code: Strategy code
                - strategy_context: Strategy context
        """
        try:
            model_uuid = model_id
            
            # Query model_strategy table, join with strategys table to get strategy details
            sql = f"""
                SELECT 
                    ms.id,
                    ms.model_id,
                    ms.strategy_id,
                    ms.type,
                    ms.priority,
                    ms.created_at,
                    s.name as strategy_name,
                    s.strategy_code,
                    s.strategy_context
                FROM {self.model_strategy_table} ms
                INNER JOIN {self.strategys_table} s ON ms.strategy_id = s.id
                WHERE ms.model_id = %s AND ms.type = %s
                ORDER BY ms.priority DESC, ms.created_at ASC
            """
            
            rows = self.query(sql, (model_uuid, strategy_type), as_dict=True)
            
            strategies = []
            for row in rows:
                strategies.append({
                    'id': row.get('id'),
                    'model_id': row.get('model_id'),
                    'strategy_id': row.get('strategy_id'),
                    'type': row.get('type'),
                    'priority': row.get('priority', 0),
                    'created_at': row.get('created_at'),
                    'strategy_name': row.get('strategy_name'),
                    'strategy_code': row.get('strategy_code'),
                    'strategy_context': row.get('strategy_context')
                })
            
            logger.debug(f"[Strategys] Retrieved {len(strategies)} strategies for model {model_id}, type {strategy_type}")
            return strategies
        except Exception as e:
            logger.error(f"[Strategys] Failed to get model strategies: {e}")
            return []
    
    def get_model_strategies_by_int_id(self, model_id: int, strategy_type: str, 
                                      model_id_mapping: Dict[int, str] = None) -> List[Dict]:
        """
        Get list of strategies associated with a model (sorted by priority and creation time)
        
        This method accepts an integer model_id, internally converts it to UUID string and calls get_model_strategies.
        
        Args:
            model_id: Model ID (integer)
            strategy_type: Strategy type, 'buy' or 'sell'
            model_id_mapping: Optional model ID mapping dictionary, if not provided, query from database
        
        Returns:
            List[Dict]: Strategy list, each element contains:
                - id: Association ID
                - model_id: Model ID
                - strategy_id: Strategy ID
                - type: Strategy type
                - priority: Priority
                - created_at: Creation time
                - strategy_name: Strategy name
                - strategy_code: Strategy code
                - strategy_context: Strategy context
        """
        try:
            # If mapping not provided, query from database
            if model_id_mapping is None:
                rows = self.query(f"SELECT id FROM models")
                model_id_mapping = {}
                for row in rows:
                    uuid_str = row[0]
                    int_id = abs(hash(uuid_str)) % (10 ** 9)
                    model_id_mapping[int_id] = uuid_str
            
            model_uuid = model_id_mapping.get(model_id)
            if not model_uuid:
                logger.warning(f"[Strategys] Model {model_id} not found in mapping, cannot get strategies")
                return []
            
            # Call method that accepts UUID string
            return self.get_model_strategies(model_uuid, strategy_type)
        except Exception as e:
            logger.error(f"[Strategys] Failed to get model strategies by int ID: {e}")
            return []

