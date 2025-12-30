"""
Model prompt database table operation module - model_prompts table

This module provides CRUD operations for model prompt configuration.

Main components:
- ModelPromptsDatabase: Model prompt data operations class
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional, Any, Callable
import pymysql
from .database_basic import create_pooled_db
import trade.common.config as app_config

logger = logging.getLogger(__name__)


class ModelPromptsDatabase:
    """
    Model prompt data operations class
    
    Encapsulates all database operations for the model_prompts table.
    """
    
    def __init__(self, pool=None):
        """
        Initialize model prompt database operations class
        
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
        
        self.model_prompts_table = "model_prompts"
    
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
                            logger.debug(f"[ModelPrompts] Error rolling back transaction: {rollback_error}")
                        
                        # For all errors, close connection, DBUtils will automatically handle damaged connections
                        try:
                            conn.close()
                        except Exception as close_error:
                            logger.debug(f"[ModelPrompts] Error closing connection: {close_error}")
                        finally:
                            # Ensure connection reference is cleared, mark as processed even if close fails
                            conn = None
                    except Exception as close_error:
                        logger.error(f"[ModelPrompts] Critical error closing failed connection: {close_error}")
                        # Even if exception occurs, clear connection reference
                        conn = None
                
                if attempt < max_retries - 1:
                    if not is_network_error:
                        raise
                    
                    is_deadlock = (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213) or 'deadlock' in error_msg.lower()
                    if is_deadlock:
                        wait_time = 1.0 * (1.5 ** attempt)
                        logger.warning(
                            f"[ModelPrompts] Deadlock error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    else:
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(
                            f"[ModelPrompts] Network error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    
                    import time
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"[ModelPrompts] Failed after {max_retries} attempts: "
                        f"{error_type}: {error_msg}"
                    )
                    raise
            finally:
                if connection_acquired and conn:
                    try:
                        logger.warning(
                            f"[ModelPrompts] Connection not closed in finally block, closing it"
                        )
                        try:
                            conn.rollback()
                            conn.close()
                        except Exception:
                            pass
                    except Exception as final_error:
                        logger.debug(f"[ModelPrompts] Error in finally block: {final_error}")
    
    def _uuid_to_int(self, uuid_str: str) -> int:
        """Convert UUID string to int ID for compatibility"""
        return abs(hash(uuid_str)) % (10 ** 9)
    
    def _row_to_dict(self, row: tuple, columns: list) -> Dict:
        """Convert a row tuple to a dictionary"""
        return dict(zip(columns, row))
    
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
    
    def get_model_prompt(self, model_id: int, model_id_mapping: Dict[int, str] = None) -> Optional[Dict]:
        """
        Get model prompt configuration
        
        Args:
            model_id: Model ID (integer)
            model_id_mapping: Optional model ID mapping dictionary, if not provided, query from database
        
        Returns:
            Model prompt configuration dictionary, returns None if not found
        """
        try:
            # If mapping not provided, need to query from database (simplified handling here, should actually be provided by caller)
            if model_id_mapping is None:
                # Query all model IDs
                rows = self.query(f"SELECT id FROM models")
                model_id_mapping = {}
                for row in rows:
                    uuid_str = row[0]
                    int_id = self._uuid_to_int(uuid_str)
                    model_id_mapping[int_id] = uuid_str
            
            model_uuid = model_id_mapping.get(model_id)
            if not model_uuid:
                return None
            
            rows = self.query(f"""
                SELECT `id`, `model_id`, `buy_prompt`, `sell_prompt`, `updated_at`
                FROM `{self.model_prompts_table}`
                WHERE `model_id` = %s
                LIMIT 1
            """, (model_uuid,))
            if not rows:
                return None
            
            columns = ["id", "model_id", "buy_prompt", "sell_prompt", "updated_at"]
            result = self._row_to_dict(rows[0], columns)
            result['model_id'] = model_id  # Convert to int ID
            return result
        except Exception as e:
            logger.error(f"[ModelPrompts] Failed to get model prompt for model {model_id}: {e}")
            return None
    
    def upsert_model_prompt(self, model_id: int, buy_prompt: Optional[str], sell_prompt: Optional[str], 
                           model_id_mapping: Dict[int, str] = None) -> bool:
        """
        Insert or update model prompt configuration
        
        Args:
            model_id: Model ID (integer)
            buy_prompt: Buy prompt
            sell_prompt: Sell prompt
            model_id_mapping: Optional model ID mapping dictionary
        
        Returns:
            bool: Whether successful
        """
        try:
            if model_id_mapping is None:
                rows = self.query(f"SELECT id FROM models")
                model_id_mapping = {}
                for row in rows:
                    uuid_str = row[0]
                    int_id = self._uuid_to_int(uuid_str)
                    model_id_mapping[int_id] = uuid_str
            
            model_uuid = model_id_mapping.get(model_id)
            if not model_uuid:
                return False
            
            # MySQL uses INSERT ... ON DUPLICATE KEY UPDATE
            prompt_id = str(uuid.uuid4())
            buy_prompt_value = buy_prompt.strip() if buy_prompt and buy_prompt.strip() else ''
            sell_prompt_value = sell_prompt.strip() if sell_prompt and sell_prompt.strip() else ''
            updated_at = datetime.now(timezone.utc)
            
            def _execute_upsert(conn):
                cursor = conn.cursor()
                try:
                    sql = f"""
                        INSERT INTO `{self.model_prompts_table}` 
                        (`id`, `model_id`, `buy_prompt`, `sell_prompt`, `updated_at`)
                        VALUES (%s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                        `buy_prompt` = VALUES(`buy_prompt`),
                        `sell_prompt` = VALUES(`sell_prompt`),
                        `updated_at` = VALUES(`updated_at`)
                    """
                    cursor.execute(sql, (prompt_id, model_uuid, buy_prompt_value, sell_prompt_value, updated_at))
                    conn.commit()
                finally:
                    cursor.close()
            
            self._with_connection(_execute_upsert)
            return True
        except Exception as e:
            logger.error(f"[ModelPrompts] Failed to upsert model prompt for model {model_id}: {e}")
            return False
