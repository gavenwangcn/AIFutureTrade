"""
Futures contract configuration database table operation module - futures table

This module provides CRUD operations for futures contract configuration data.

Main components:
- FuturesDatabase: Futures contract configuration data operations
"""

import logging
import uuid
from typing import Dict, List, Optional, Any, Callable
import pymysql
from .database_basic import create_pooled_db
import trade.common.config as app_config
from .database_init import FUTURES_TABLE, MODEL_FUTURES_TABLE, PORTFOLIOS_TABLE

logger = logging.getLogger(__name__)


class FuturesDatabase:
    """
    Futures contract configuration data operations
    
    Encapsulates all database operations for the futures table.
    """
    
    def __init__(self, pool=None):
        """
        Initialize futures contract configuration database operations
        
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
        
        self.futures_table = FUTURES_TABLE
        self.model_futures_table = MODEL_FUTURES_TABLE
        self.portfolios_table = PORTFOLIOS_TABLE
    
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
                            logger.debug(f"[Futures] Error rolling back transaction: {rollback_error}")
                        
                        # For all errors, close connection, DBUtils will automatically handle damaged connections
                        try:
                            conn.close()
                        except Exception as close_error:
                            logger.debug(f"[Futures] Error closing connection: {close_error}")
                        finally:
                            # Ensure connection reference is cleared, mark as processed even if close fails
                            conn = None
                    except Exception as close_error:
                        logger.error(f"[Futures] Critical error closing failed connection: {close_error}")
                        # Even if exception occurs, clear connection reference
                        conn = None
                
                if attempt < max_retries - 1:
                    if not is_network_error:
                        raise
                    
                    is_deadlock = (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213) or 'deadlock' in error_msg.lower()
                    if is_deadlock:
                        wait_time = 1.0 * (1.5 ** attempt)
                        logger.warning(
                            f"[Futures] Deadlock error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    else:
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(
                            f"[Futures] Network error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    
                    import time
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"[Futures] Failed after {max_retries} attempts: "
                        f"{error_type}: {error_msg}"
                    )
                    raise
            finally:
                if connection_acquired and conn:
                    try:
                        logger.warning(
                            f"[Futures] Connection not closed in finally block, closing it"
                        )
                        try:
                            conn.rollback()
                            conn.close()
                        except Exception:
                            pass
                    except Exception as final_error:
                        logger.debug(f"[Futures] Error in finally block: {final_error}")
    
    def _row_to_dict(self, row: tuple, columns: list) -> Dict:
        """Convert a row tuple to a dictionary"""
        return dict(zip(columns, row))
    
    def _rows_to_dicts(self, rows: List[tuple], columns: list) -> List[Dict]:
        """Convert rows to list of dictionaries"""
        return [self._row_to_dict(row, columns) for row in rows]
    
    def _generate_id(self) -> str:
        """Generate a unique ID (UUID)"""
        return str(uuid.uuid4())
    
    def command(self, sql: str, params: tuple = None) -> None:
        """Execute a raw SQL command."""
        def _execute_command(conn):
            cursor = conn.cursor()
            try:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
            finally:
                cursor.close()
        self._with_connection(_execute_command)
    
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
    
    def get_future_configs(self) -> List[Dict]:
        """
        Get future configurations
        
        Returns:
            List[Dict]: Futures configuration list, each element contains symbol, contract_symbol, name, exchange, link, sort_order fields
        """
        try:
            rows = self.query(f"""
                SELECT symbol, contract_symbol, name, exchange, link, sort_order
                FROM {self.futures_table}
                ORDER BY sort_order DESC, symbol ASC
            """)
            columns = ["symbol", "contract_symbol", "name", "exchange", "link", "sort_order"]
            return self._rows_to_dicts(rows, columns)
        except Exception as e:
            logger.error(f"[Futures] Failed to get future configs: {e}")
            return []
    
    def sync_model_futures_from_portfolio(self, model_id: int) -> bool:
        """
        Sync deduplicated future information from portfolios table to model_futures table
        
        This method will:
        1. Get all distinct future contracts traded by the current model from portfolios table (including closed positions)
        2. Sync these contract information to model_futures table (including add and delete comparison operations)
        3. For newly added contracts, get complete information from global futures table
        4. For contracts no longer appearing in portfolios table, remove from model_futures table
        
        Args:
            model_id: Model ID
        
        Returns:
            bool: Whether sync was successful
        """
        try:
            logger.info(f"[Futures] Starting sync_model_futures_from_portfolio for model {model_id}")
            
            from .database_models import ModelsDatabase
            models_db = ModelsDatabase(pool=self._pool)
            model_mapping = models_db._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                logger.error(f"[Futures] Model {model_id} not found in mapping")
                return False
            
            # 1. Get all distinct symbol contracts traded by current model from portfolios table (including closed positions)
            # Use parameterized query to avoid SQL injection
            rows = self.query(f"""
                SELECT DISTINCT symbol
                FROM `{self.portfolios_table}`
                WHERE model_id = %s
                ORDER BY symbol ASC
            """, (model_uuid,))
            
            portfolio_symbols = [row[0] for row in rows] if rows else []
            logger.info(f"[Futures] Found {len(portfolio_symbols)} distinct symbols in portfolios table for model {model_id}: {portfolio_symbols}")
            
            # 2. Get current contract list in model_futures table
            rows = self.query(f"""
                SELECT id, model_id, symbol
                FROM `{self.model_futures_table}`
                WHERE model_id = %s
                ORDER BY symbol ASC
            """, (model_uuid,))
            
            current_model_futures = []
            for row in rows:
                current_model_futures.append({
                    'id': row[0],
                    'model_id': row[1],
                    'symbol': row[2]
                })
            current_symbols = {future['symbol']: future for future in current_model_futures}
            logger.info(f"[Futures] Found {len(current_symbols)} symbols in model_futures table for model {model_id}: {list(current_symbols.keys())}")
            
            # 3. Determine contracts to add and delete (comparison operation)
            symbols_to_add = set(portfolio_symbols) - set(current_symbols.keys())
            symbols_to_delete = set(current_symbols.keys()) - set(portfolio_symbols)
            
            logger.info(f"[Futures] Sync comparison for model {model_id}: "
                       f"to_add={len(symbols_to_add)} {list(symbols_to_add)}, "
                       f"to_delete={len(symbols_to_delete)} {list(symbols_to_delete)}")
            
            # 4. Add new contracts to model_futures table
            if symbols_to_add:
                logger.info(f"[Futures] Adding {len(symbols_to_add)} new futures to model_futures table for model {model_id}")
                
                # Get complete contract information from global futures table
                # Use parameterized query, handle single and multiple element cases
                symbols_list = list(symbols_to_add)
                if len(symbols_list) == 1:
                    # Use = instead of IN for single element
                    futures_info = self.query(f"""
                        SELECT symbol, contract_symbol, name, exchange, link
                        FROM `{self.futures_table}`
                        WHERE symbol = %s
                    """, (symbols_list[0],))
                else:
                    # Use IN for multiple elements, use parameterized query
                    placeholders = ', '.join(['%s'] * len(symbols_list))
                    futures_info = self.query(f"""
                        SELECT symbol, contract_symbol, name, exchange, link
                        FROM `{self.futures_table}`
                        WHERE symbol IN ({placeholders})
                    """, tuple(symbols_list))
                
                # Build futures dictionary
                futures_dict = {}
                for row in futures_info:
                    futures_dict[row[0]] = {
                        'symbol': row[0],
                        'contract_symbol': row[1] or row[0],
                        'name': row[2] or row[0],
                        'exchange': row[3] or 'BINANCE_FUTURES',
                        'link': row[4] or ''
                    }
                
                # Generate records for each contract to add
                added_count = 0
                for symbol in symbols_to_add:
                    # If contract information not found in global table, create default information
                    if symbol not in futures_dict:
                        futures_dict[symbol] = {
                            'symbol': symbol,
                            'contract_symbol': symbol,
                            'name': symbol,
                            'exchange': 'BINANCE_FUTURES',
                            'link': ''
                        }
                        logger.warning(f"[Futures] Future {symbol} not found in global futures table, using default values")
                    
                    # Generate unique ID
                    future_id = self._generate_id()
                    
                    # Insert into model_futures table
                    try:
                        self.insert_rows(
                            self.model_futures_table,
                            [[future_id, model_uuid, futures_dict[symbol]['symbol'], 
                              futures_dict[symbol]['contract_symbol'], futures_dict[symbol]['name'],
                              futures_dict[symbol]['exchange'], futures_dict[symbol]['link'], 0]],
                            ["id", "model_id", "symbol", "contract_symbol", "name", "exchange", "link", "sort_order"]
                        )
                        added_count += 1
                        logger.debug(f"[Futures] Added future {symbol} to model {model_id} in model_futures table")
                    except Exception as insert_error:
                        logger.error(f"[Futures] Failed to insert future {symbol} for model {model_id}: {insert_error}")
                        # Continue processing other contracts, don't interrupt entire process
                        continue
                
                logger.info(f"[Futures] Successfully added {added_count}/{len(symbols_to_add)} futures to model_futures table for model {model_id}")
            else:
                logger.info(f"[Futures] No new futures to add for model {model_id}")
            
            # 5. Delete contracts from model_futures table that no longer appear in portfolios table
            if symbols_to_delete:
                logger.info(f"[Futures] Deleting {len(symbols_to_delete)} futures from model_futures table for model {model_id}")
                
                # Use parameterized query to delete
                for symbol in symbols_to_delete:
                    try:
                        self.command(f"""
                            DELETE FROM `{self.model_futures_table}`
                            WHERE model_id = %s AND symbol = %s
                        """, (model_uuid, symbol))
                        logger.debug(f"[Futures] Deleted future {symbol} from model {model_id} in model_futures table")
                    except Exception as delete_error:
                        logger.error(f"[Futures] Failed to delete future {symbol} for model {model_id}: {delete_error}")
                        # Continue processing other contracts, don't interrupt entire process
                        continue
                
                logger.info(f"[Futures] Successfully deleted {len(symbols_to_delete)} futures from model_futures table for model {model_id}")
            else:
                logger.info(f"[Futures] No futures to delete for model {model_id}")
            
            logger.info(f"[Futures] Successfully synced model_futures for model {model_id}: "
                        f"added {len(symbols_to_add)}, deleted {len(symbols_to_delete)}")
            return True
            
        except Exception as e:
            logger.error(f"[Futures] Failed to sync model_futures from portfolio for model {model_id}: {e}")
            import traceback
            logger.error(f"[Futures] Error stack: {traceback.format_exc()}")
            return False
