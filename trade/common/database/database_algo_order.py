"""
Algo Order database table operation module - algo_order table

This module provides CRUD operations for algorithmic orders (conditional orders).

Main components:
- AlgoOrderDatabase: Algorithmic order data operations
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Callable
import pymysql
from .database_basic import create_pooled_db
import trade.common.config as app_config
from .database_init import ALGO_ORDER_TABLE

logger = logging.getLogger(__name__)


class AlgoOrderDatabase:
    """
    Algorithmic order data operations

    Encapsulates all database operations for the algo_order table.
    """

    def __init__(self, pool=None):
        """
        Initialize algo order database operations

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

        self.algo_order_table = ALGO_ORDER_TABLE

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
                            logger.debug(f"[AlgoOrder] Error rolling back transaction: {rollback_error}")

                        try:
                            conn.close()
                        except Exception as close_error:
                            logger.debug(f"[AlgoOrder] Error closing connection: {close_error}")
                        finally:
                            conn = None
                    except Exception as cleanup_error:
                        logger.debug(f"[AlgoOrder] Error during connection cleanup: {cleanup_error}")

                if is_network_error and attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
                    logger.warning(f"[AlgoOrder] Retrying database operation (attempt {attempt + 2}/{max_retries})")
                    continue

                logger.error(f"[AlgoOrder] Database operation failed: {e}")
                raise

        raise Exception("[AlgoOrder] Failed to execute database operation after retries")

    def query_algo_orders(self, model_id: str, symbol: Optional[str] = None,
                         status: Optional[str] = None) -> List[Dict]:
        """
        Query algo orders

        Args:
            model_id: Model ID (UUID string)
            symbol: Optional symbol filter
            status: Optional status filter (e.g., 'NEW', 'cancelled')

        Returns:
            List[Dict]: List of algo order records
        """
        def _query(conn):
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            query = f"SELECT * FROM {self.algo_order_table} WHERE model_id = %s"
            params = [model_id]

            if symbol:
                query += " AND symbol = %s"
                params.append(symbol.upper())

            if status:
                query += " AND algoStatus = %s"
                params.append(status)

            query += " ORDER BY created_at DESC"

            cursor.execute(query, tuple(params))
            results = cursor.fetchall()
            cursor.close()

            return results if results else []

        try:
            return self._with_connection(_query)
        except Exception as e:
            logger.error(f"[AlgoOrder] Failed to query algo orders: {e}")
            return []

    def insert_algo_order(self, algo_order_data: Dict) -> Optional[str]:
        """
        Insert a new algo order

        Args:
            algo_order_data: Dict containing algo order fields:
                - id: UUID string (required)
                - algoId: Binance algo ID (optional, for real mode)
                - clientAlgoId: Client algo ID (required)
                - type: 'real' or 'virtual' (required)
                - algoType: Algorithm type (default: 'CONDITIONAL')
                - orderType: Order type (required, e.g., 'STOP_MARKET')
                - symbol: Trading pair (required)
                - side: 'buy' or 'sell' (required)
                - positionSide: 'LONG' or 'SHORT' (required)
                - quantity: Order quantity (required)
                - algoStatus: Order status (default: 'new')
                - triggerPrice: Trigger price (optional)
                - price: Order price (optional)
                - error_reason: Error reason (optional)
                - model_id: Model ID (required)
                - strategy_decision_id: Strategy decision ID (optional)
                - trade_id: Trade ID (optional)
                - created_at: Creation time (required)

        Returns:
            Optional[str]: The algo order ID if successful, None otherwise
        """
        def _insert(conn):
            cursor = conn.cursor()

            # Required fields
            algo_order_id = algo_order_data.get('id')
            if not algo_order_id:
                raise ValueError("algo_order_data must contain 'id' field")

            # Build INSERT query
            fields = []
            values = []
            placeholders = []

            # Map all possible fields
            field_mapping = {
                'id': 'id',
                'algoId': 'algoId',
                'clientAlgoId': 'clientAlgoId',
                'type': 'type',
                'algoType': 'algoType',
                'orderType': 'orderType',
                'symbol': 'symbol',
                'side': 'side',
                'positionSide': 'positionSide',
                'quantity': 'quantity',
                'algoStatus': 'algoStatus',
                'triggerPrice': 'triggerPrice',
                'price': 'price',
                'error_reason': 'error_reason',
                'model_id': 'model_id',
                'strategy_decision_id': 'strategy_decision_id',
                'trade_id': 'trade_id',
                'created_at': 'created_at'
            }

            for key, db_field in field_mapping.items():
                if key in algo_order_data:
                    fields.append(db_field)
                    values.append(algo_order_data[key])
                    placeholders.append('%s')

            query = f"INSERT INTO {self.algo_order_table} ({', '.join(fields)}) VALUES ({', '.join(placeholders)})"

            cursor.execute(query, tuple(values))
            cursor.close()

            return algo_order_id

        try:
            return self._with_connection(_insert)
        except Exception as e:
            logger.error(f"[AlgoOrder] Failed to insert algo order: {e}")
            return None

    def update_algo_order_status(self, algo_order_id: str, status: str) -> bool:
        """
        Update algo order status

        Args:
            algo_order_id: Algo order ID (UUID string)
            status: New status (e.g., 'cancelled', 'triggered', 'executed', 'failed')

        Returns:
            bool: True if successful, False otherwise
        """
        def _update(conn):
            cursor = conn.cursor()

            query = f"UPDATE {self.algo_order_table} SET algoStatus = %s, updated_at = NOW() WHERE id = %s"
            cursor.execute(query, (status, algo_order_id))
            affected_rows = cursor.rowcount
            cursor.close()

            return affected_rows > 0

        try:
            return self._with_connection(_update)
        except Exception as e:
            logger.error(f"[AlgoOrder] Failed to update algo order status: {e}")
            return False

    def cancel_algo_orders_by_symbol(self, model_id: str, symbol: str) -> int:
        """
        Cancel all NEW algo orders for a specific symbol

        Args:
            model_id: Model ID (UUID string)
            symbol: Trading pair symbol

        Returns:
            int: Number of orders cancelled
        """
        def _cancel(conn):
            cursor = conn.cursor()

            query = f"""
                UPDATE {self.algo_order_table}
                SET algoStatus = 'CANCELLED', updated_at = NOW()
                WHERE model_id = %s AND symbol = %s AND algoStatus = 'NEW'
            """
            cursor.execute(query, (model_id, symbol.upper()))
            affected_rows = cursor.rowcount
            cursor.close()

            return affected_rows

        try:
            return self._with_connection(_cancel)
        except Exception as e:
            logger.error(f"[AlgoOrder] Failed to cancel algo orders: {e}")
            return 0

    def get_new_algo_orders_by_symbol(self, model_id: str, symbol: str) -> List[Dict]:
        """
        Get all NEW algo orders for a specific symbol

        Args:
            model_id: Model ID (UUID string)
            symbol: Trading pair symbol

        Returns:
            List[Dict]: List of NEW algo order records
        """
        def _query(conn):
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            query = f"""
                SELECT id, algoId, orderType, symbol, side, positionSide, quantity, algoStatus, triggerPrice
                FROM {self.algo_order_table}
                WHERE model_id = %s AND symbol = %s AND algoStatus = 'NEW'
                ORDER BY created_at DESC
            """
            cursor.execute(query, (model_id, symbol.upper()))
            results = cursor.fetchall()
            cursor.close()

            return results if results else []

        try:
            return self._with_connection(_query)
        except Exception as e:
            logger.error(f"[AlgoOrder] Failed to get NEW algo orders: {e}")
            return []

    def update_algo_order_error(self, algo_order_id: str, error_reason: str) -> bool:
        """
        Update algo order error reason and set status to 'failed'

        Args:
            algo_order_id: Algo order ID (UUID string)
            error_reason: Error reason text

        Returns:
            bool: True if successful, False otherwise
        """
        def _update(conn):
            cursor = conn.cursor()

            query = f"""
                UPDATE {self.algo_order_table}
                SET algoStatus = 'FAILED', error_reason = %s, updated_at = NOW()
                WHERE id = %s
            """
            cursor.execute(query, (error_reason, algo_order_id))
            affected_rows = cursor.rowcount
            cursor.close()

            return affected_rows > 0

        try:
            return self._with_connection(_update)
        except Exception as e:
            logger.error(f"[AlgoOrder] Failed to update algo order error: {e}")
            return False
