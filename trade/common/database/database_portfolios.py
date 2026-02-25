"""
Portfolio database table operation module - portfolios table

This module provides CRUD operations for portfolio data.

Main components:
- PortfoliosDatabase: Portfolio data operations
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Callable
import pymysql
from .database_basic import create_pooled_db
import trade.common.config as app_config
from .database_init import PORTFOLIOS_TABLE, FUTURES_TABLE

logger = logging.getLogger(__name__)


class PortfoliosDatabase:
    """
    Portfolio data operations
    
    Encapsulates all database operations for the portfolios table.
    """
    
    def __init__(self, pool=None):
        """
        Initialize portfolio database operations
        
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
        
        self.portfolios_table = PORTFOLIOS_TABLE
        self.futures_table = FUTURES_TABLE
    
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
                            logger.debug(f"[Portfolios] Error rolling back transaction: {rollback_error}")
                        
                        # For all errors, close connection, DBUtils will automatically handle damaged connections
                        try:
                            conn.close()
                        except Exception as close_error:
                            logger.debug(f"[Portfolios] Error closing connection: {close_error}")
                        finally:
                            # Ensure connection reference is cleared, mark as processed even if close fails
                            conn = None
                    except Exception as close_error:
                        logger.error(f"[Portfolios] Critical error closing failed connection: {close_error}")
                        # Even if exception occurs, clear connection reference
                        conn = None
                
                if attempt < max_retries - 1:
                    if not is_network_error:
                        raise
                    
                    is_deadlock = (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213) or 'deadlock' in error_msg.lower()
                    if is_deadlock:
                        wait_time = 1.0 * (1.5 ** attempt)
                        logger.warning(
                            f"[Portfolios] Deadlock error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    else:
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(
                            f"[Portfolios] Network error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    
                    import time
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"[Portfolios] Failed after {max_retries} attempts: "
                        f"{error_type}: {error_msg}"
                    )
                    raise
            finally:
                if connection_acquired and conn:
                    try:
                        logger.warning(
                            f"[Portfolios] Connection not closed in finally block, closing it"
                        )
                        try:
                            conn.rollback()
                            conn.close()
                        except Exception:
                            pass
                    except Exception as final_error:
                        logger.debug(f"[Portfolios] Error in finally block: {final_error}")
    
    def _generate_id(self) -> str:
        """Generate a unique ID (UUID)"""
        return str(uuid.uuid4())
    
    def _row_to_dict(self, row: tuple, columns: list) -> Dict:
        """Convert a row tuple to a dictionary"""
        return dict(zip(columns, row))
    
    def _rows_to_dicts(self, rows: List[tuple], columns: list) -> List[Dict]:
        """Convert rows to list of dictionaries"""
        return [self._row_to_dict(row, columns) for row in rows]
    
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
    
    def update_position(self, model_id: int, symbol: str, position_amt: float,
                       avg_price: float, leverage: int = 1, position_side: str = 'LONG',
                       initial_margin: float = 0.0, unrealized_profit: float = 0.0,
                       model_id_mapping: Dict[int, str] = None):
        """
        Update position
        
        Args:
            model_id: Model ID
            symbol: Trading pair symbol (e.g., BTCUSDT)
            position_amt: Position amount
            avg_price: Average price
            leverage: Leverage multiplier
            position_side: Position direction, 'LONG' (long) or 'SHORT' (short)
            initial_margin: Initial margin required for position (based on latest mark price)
            unrealized_profit: Unrealized profit of position
            model_id_mapping: Optional model ID mapping dictionary
        """
        try:
            if model_id_mapping is None:
                # If mapping not provided, need to query from database
                rows = self.query(f"SELECT id FROM models")
                model_id_mapping = {}
                for row in rows:
                    uuid_str = row[0]
                    int_id = abs(hash(uuid_str)) % (10 ** 9)
                    model_id_mapping[int_id] = uuid_str
            
            model_uuid = model_id_mapping.get(model_id)
            if not model_uuid:
                logger.warning(f"[Portfolios] Model {model_id} not found for position update")
                return
            
            # Normalize position_side
            position_side_upper = position_side.upper()
            if position_side_upper not in ['LONG', 'SHORT']:
                raise ValueError(f"position_side must be 'LONG' or 'SHORT', got: {position_side}")
            
            # Use INSERT ... ON DUPLICATE KEY UPDATE to implement UPSERT operation
            # If record exists (same model_id, symbol, position_side), update; otherwise insert new record
            # created_at/updated_at 使用代码插入：获取当前 UTC+8 时间
            beijing_tz = timezone(timedelta(hours=8))
            current_time_utc8 = datetime.now(beijing_tz).replace(tzinfo=None)
            
            normalized_symbol = symbol.upper()
            position_id = self._generate_id()
            
            # Use INSERT ... ON DUPLICATE KEY UPDATE to implement atomic UPSERT operation
            # When unique key (model_id, symbol, position_side) conflicts, update existing record
            # position_init: 仅在首次买入时记录（INSERT时设置为position_amt），后续买入/卖出时保持不变（UPDATE时不更新）
            def _execute_upsert(conn):
                cursor = None
                try:
                    # Check if record exists
                    check_sql = f"""
                    SELECT `position_init` FROM `{self.portfolios_table}`
                    WHERE `model_id` = %s AND `symbol` = %s AND `position_side` = %s
                    """
                    cursor = conn.cursor()
                    cursor.execute(check_sql, (model_uuid, normalized_symbol, position_side_upper))
                    existing_row = cursor.fetchone()
                    
                    # Determine position_init value: 只有首次买入（新记录）时才设置
                    if existing_row is None:
                        # New record (首次买入): set position_init to position_amt
                        position_init_value = position_amt
                        logger.debug(f"[Portfolios] 首次买入，设置 position_init={position_init_value}")
                    else:
                        # Existing record (后续买入/卖出): position_init 保持不变，使用 NULL（UPDATE时不会更新该字段）
                        position_init_value = None
                        # Access by column name since cursor returns dict
                        existing_position_init = existing_row.get('position_init') if existing_row else None
                        logger.debug(f"[Portfolios] 后续交易，position_init 保持不变={existing_position_init}")
                    
                    sql = f"""
                    INSERT INTO `{self.portfolios_table}` 
                    (`id`, `model_id`, `symbol`, `position_amt`, `position_init`, `avg_price`, `leverage`, 
                     `position_side`, `initial_margin`, `unrealized_profit`, `created_at`, `updated_at`)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        `position_amt` = VALUES(`position_amt`),
                        `position_init` = `position_init`,
                        `avg_price` = VALUES(`avg_price`),
                        `leverage` = VALUES(`leverage`),
                        `initial_margin` = VALUES(`initial_margin`),
                        `unrealized_profit` = VALUES(`unrealized_profit`),
                        `updated_at` = VALUES(`updated_at`)
                    """
                    cursor.execute(sql, (
                        position_id, model_uuid, normalized_symbol, position_amt, position_init_value, avg_price,
                        leverage, position_side_upper, initial_margin, unrealized_profit,
                        current_time_utc8, current_time_utc8
                    ))
                    # Check if insert or update
                    # Note: INSERT ... ON DUPLICATE KEY UPDATE returns:
                    # - rowcount = 1: New row inserted
                    # - rowcount = 2: Existing row updated
                    # - rowcount = 0: No rows affected (should not happen normally)
                    if cursor.rowcount == 1:
                        logger.debug(f"[Portfolios] Position inserted: model_id={model_uuid}, symbol={normalized_symbol}, position_side={position_side_upper}, id={position_id}, position_init={position_init_value} (首次买入)")
                    elif cursor.rowcount == 2:
                        # Access by column name since cursor returns dict
                        existing_position_init = existing_row.get('position_init') if existing_row else None
                        logger.debug(f"[Portfolios] Position updated: model_id={model_uuid}, symbol={normalized_symbol}, position_side={position_side_upper}, position_amt={position_amt}, position_init={existing_position_init} (保持不变)")
                    elif cursor.rowcount == 0:
                        # This should not happen normally, but log a warning instead of raising an exception
                        logger.warning(f"[Portfolios] UPSERT returned rowcount=0 (no rows affected): model_id={model_uuid}, symbol={normalized_symbol}, position_side={position_side_upper}, position_amt={position_amt}. This may indicate a database constraint issue.")
                    else:
                        # Unexpected rowcount value
                        logger.warning(f"[Portfolios] UPSERT returned unexpected rowcount={cursor.rowcount}: model_id={model_uuid}, symbol={normalized_symbol}, position_side={position_side_upper}, position_amt={position_amt}")
                except Exception as inner_e:
                    # Log detailed error information before re-raising
                    logger.error(
                        f"[Portfolios] Error in _execute_upsert: "
                        f"model_id={model_id}, model_uuid={model_uuid}, symbol={symbol}, "
                        f"normalized_symbol={normalized_symbol}, position_side={position_side}, "
                        f"position_side_upper={position_side_upper}, position_amt={position_amt}, "
                        f"error_type={type(inner_e).__name__}, error={inner_e}, "
                        f"error_args={inner_e.args if hasattr(inner_e, 'args') else 'N/A'}"
                    )
                    raise
                finally:
                    if cursor:
                        try:
                            cursor.close()
                        except Exception as close_err:
                            logger.debug(f"[Portfolios] Error closing cursor: {close_err}")
            
            self._with_connection(_execute_upsert)
        except Exception as e:
            logger.error(f"[Portfolios] Failed to update position: model_id={model_id}, symbol={symbol}, position_side={position_side}, position_amt={position_amt}, error_type={type(e).__name__}, error={e}")
            raise
    
    def get_portfolio(self, model_id: int, current_prices: Dict = None,
                     model_id_mapping: Dict[int, str] = None,
                     get_model_func: Callable[[int], Optional[Dict]] = None,
                     trades_table: str = None) -> Dict:
        """
        Get portfolio with positions and P&L
        
        Args:
            model_id: Model ID
            current_prices: Current price dictionary
            model_id_mapping: Optional model ID mapping dictionary
            get_model_func: Optional function to get model information
            trades_table: Optional trades table name
        
        Returns:
            Portfolio information dictionary
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
                logger.warning(f"[Portfolios] Model {model_id} not found in mapping, returning empty portfolio")
                return {
                    'model_id': model_id,
                    'initial_capital': 0,
                    'cash': 0,
                    'positions': [],
                    'positions_value': 0,
                    'margin_used': 0,
                    'total_value': 0,
                    'realized_pnl': 0,
                    'unrealized_pnl': 0
                }
            
            # Get positions（含 created_at 用于派生 open_time 开仓时间，与开仓价 avg_price 对应）
            # 显式指定列名，确保顺序与 columns 列表一致，避免字段映射错误
            columns = ["id", "model_id", "symbol", "position_amt", "position_init", "avg_price", "leverage",
                      "position_side", "initial_margin", "unrealized_profit", "created_at", "updated_at"]
            columns_str = ", ".join([f"`{col}`" for col in columns])
            rows = self.query(f"""
                SELECT {columns_str} FROM {self.portfolios_table}
                WHERE model_id = '{model_uuid}' AND position_amt != 0
            """)
            positions = self._rows_to_dicts(rows, columns)
            # 为策略传递开仓时间：open_time 取自 portfolios.created_at，与 avg_price 对应
            for pos in positions:
                created_at = pos.get('created_at')
                if hasattr(created_at, 'strftime'):
                    pos['open_time'] = created_at.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    pos['open_time'] = created_at if created_at is not None else None
            
            # Get initial capital
            if get_model_func:
                model = get_model_func(model_id)
            else:
                # If function not provided, query from database
                from .database_models import ModelsDatabase
                models_db = ModelsDatabase(pool=self._pool)
                model = models_db.get_model(model_id)
            
            if not model:
                logger.warning(f"[Portfolios] Model {model_id} not found when getting model info, returning empty portfolio")
                return {
                    'model_id': model_id,
                    'initial_capital': 0,
                    'cash': 0,
                    'positions': [],
                    'positions_value': 0,
                    'margin_used': 0,
                    'total_value': 0,
                    'realized_pnl': 0,
                    'unrealized_pnl': 0
                }
            initial_capital = model['initial_capital']
            
            # Calculate realized P&L (need to query from trades table)
            if trades_table:
                pnl_rows = self.query(f"""
                    SELECT COALESCE(SUM(pnl), 0) as total_pnl 
                    FROM {trades_table}
                    WHERE model_id = '{model_uuid}'
                """)
                realized_pnl = float(pnl_rows[0][0]) if pnl_rows and pnl_rows[0][0] is not None else 0.0
            else:
                # If trades_table not provided, query from trades table
                from .database_init import TRADES_TABLE
                pnl_rows = self.query(f"""
                    SELECT COALESCE(SUM(pnl), 0) as total_pnl 
                    FROM {TRADES_TABLE}
                    WHERE model_id = '{model_uuid}'
                """)
                realized_pnl = float(pnl_rows[0][0]) if pnl_rows and pnl_rows[0][0] is not None else 0.0
            
            # Calculate margin used (use initial_margin field if available, otherwise calculate)
            # 优先使用 initial_margin 字段（开仓时已正确设置），如果字段不存在或为 None 则使用公式计算
            # 注意：initial_margin 为 0 是合法值（虽然罕见），应该直接使用，不需要 fallback
            margin_used = 0.0
            for p in positions:
                initial_margin = p.get('initial_margin')
                if initial_margin is not None:
                    # 使用 initial_margin 字段（开仓时已正确设置，即使为 0 也使用）
                    margin_used += initial_margin
                else:
                    # Fallback: 如果 initial_margin 为 None（字段不存在），使用公式计算（兼容历史数据）
                    position_amt = abs(p.get('position_amt', 0))
                    avg_price = p.get('avg_price', 0)
                    leverage = p.get('leverage', 1)
                    if leverage > 0:
                        calculated_margin = (position_amt * avg_price) / leverage
                        margin_used += calculated_margin
                        logger.debug(f"[Portfolios] Using calculated margin for {p.get('symbol')}: {calculated_margin} (initial_margin is None)")
            
            # Calculate unrealized P&L (prefer unrealized_profit field, if not available calculate)
            # Helper function to safely convert unrealized_profit to float
            def safe_get_unrealized_profit(pos_dict):
                """Safely get unrealized_profit as float, handling type errors"""
                val = pos_dict.get('unrealized_profit')
                if val is None:
                    return None
                # If already a number type, return it
                if isinstance(val, (int, float)):
                    return float(val)
                # If it's a datetime or other non-numeric type, log warning and return None
                # This handles cases where field mapping might be incorrect
                logger.warning(
                    f"[Portfolios] unrealized_profit has unexpected type {type(val).__name__} "
                    f"for symbol {pos_dict.get('symbol')}, value: {val}. Will calculate instead."
                )
                # Try to convert, but if it fails, return None
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return None
            
            unrealized_pnl = 0
            if current_prices:
                for pos in positions:
                    symbol = pos['symbol']
                    if symbol in current_prices:
                        current_price = current_prices[symbol]
                        entry_price = pos['avg_price']
                        position_amt = abs(pos['position_amt'])  # Use absolute value
                        pos['current_price'] = current_price
                        
                        # Prefer unrealized_profit field from database
                        db_unrealized_profit = safe_get_unrealized_profit(pos)
                        if db_unrealized_profit is not None and db_unrealized_profit != 0:
                            pos_pnl = db_unrealized_profit
                        else:
                            # If not available, calculate
                            if pos['position_side'] == 'LONG':
                                pos_pnl = (current_price - entry_price) * position_amt
                            else:  # SHORT
                                pos_pnl = (entry_price - current_price) * position_amt
                        
                        pos['pnl'] = pos_pnl
                        unrealized_pnl += pos_pnl
                    else:
                        pos['current_price'] = None
                        # Use unrealized_profit field from database
                        db_unrealized_profit = safe_get_unrealized_profit(pos)
                        pos['pnl'] = db_unrealized_profit if db_unrealized_profit is not None else 0.0
                        unrealized_pnl += pos['pnl']
            else:
                for pos in positions:
                    pos['current_price'] = None
                    # Use unrealized_profit field from database
                    db_unrealized_profit = safe_get_unrealized_profit(pos)
                    pos['pnl'] = db_unrealized_profit if db_unrealized_profit is not None else 0.0
                    unrealized_pnl += pos['pnl']
            
            cash = initial_capital + realized_pnl - margin_used
            positions_value = sum([abs(p['position_amt']) * p['avg_price'] for p in positions])
            total_value = initial_capital + realized_pnl + unrealized_pnl
            
            return {
                'model_id': model_id,
                'initial_capital': initial_capital,
                'cash': cash,
                'positions': positions,
                'positions_value': positions_value,
                'margin_used': margin_used,
                'total_value': total_value,
                'realized_pnl': realized_pnl,
                'unrealized_pnl': unrealized_pnl
            }
        except Exception as e:
            logger.error(f"[Portfolios] Failed to get portfolio for model {model_id}: {e}")
            raise
    
    def close_position(self, model_id: int, symbol: str, position_side: str = 'LONG',
                      model_id_mapping: Dict[int, str] = None):
        """
        Close position and clean up futures universe if unused
        
        Args:
            model_id: Model ID
            symbol: Trading pair symbol (e.g., BTCUSDT)
            position_side: Position direction, 'LONG' (long) or 'SHORT' (short)
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
                return
            
            normalized_symbol = symbol.upper()
            position_side_upper = position_side.upper()
            if position_side_upper not in ['LONG', 'SHORT']:
                raise ValueError(f"position_side must be 'LONG' or 'SHORT', got: {position_side}")
            
            # Use MySQL DELETE FROM syntax
            delete_sql = f"DELETE FROM {self.portfolios_table} WHERE model_id = '{model_uuid}' AND symbol = '{normalized_symbol}' AND position_side = '{position_side_upper}'"
            logger.debug(f"[Portfolios] Executing SQL: {delete_sql}")
            self.command(delete_sql)
            
            # Check if there are other positions
            remaining_rows = self.query(f"""
                SELECT COUNT(*) as cnt FROM {self.portfolios_table}
                WHERE symbol = '{normalized_symbol}' AND position_amt != 0
            """)
            if remaining_rows and remaining_rows[0][0] == 0:
                # Note: Auto-cleanup of futures table is disabled to preserve symbol configurations
                # Previously would delete: DELETE FROM futures WHERE symbol = '{normalized_symbol}'
                logger.debug(f"[Portfolios] All positions closed for {normalized_symbol}, but keeping futures table record")
                pass
        except Exception as e:
            logger.error(f"[Portfolios] Failed to close position: model_id={model_id}, symbol={symbol}, position_side={position_side}, error_type={type(e).__name__}, error={e}")
            raise
    
    def get_model_held_symbols(self, model_id: int, model_id_mapping: Dict[int, str] = None) -> List[str]:
        """
        Get list of futures contract symbols currently held by model (deduplicated)
        
        Get symbols with positions (position_amt != 0) from portfolios table by associating model_id,
        used by sell service to get market status.
        
        Args:
            model_id: Model ID
            model_id_mapping: Optional model ID mapping dictionary
        
        Returns:
            List[str]: List of contract symbols currently held (e.g., ['BTC', 'ETH'])
        """
        try:
            if model_id_mapping is None:
                from .database_models import ModelsDatabase
                models_db = ModelsDatabase(pool=self._pool)
                model_id_mapping = models_db._get_model_id_mapping()
            
            model_uuid = model_id_mapping.get(model_id)
            if not model_uuid:
                logger.warning(f"[Portfolios] Model {model_id} UUID not found")
                return []
            
            # Get deduplicated symbol contracts with positions from portfolios table (position_amt != 0)
            # Use parameterized query to avoid SQL injection
            rows = self.query(f"""
                SELECT DISTINCT symbol
                FROM `{self.portfolios_table}`
                WHERE model_id = %s AND position_amt != 0
                ORDER BY symbol ASC
            """, (model_uuid,))
            
            symbols = [row[0] for row in rows] if rows else []
            return symbols
        except Exception as e:
            logger.error(f"[Portfolios] Failed to get model held symbols for model {model_id}: {e}")
            return []
