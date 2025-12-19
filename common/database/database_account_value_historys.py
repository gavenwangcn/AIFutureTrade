"""
账户价值历史数据表操作模块 - account_value_historys 表

本模块提供账户价值历史数据的增删改查操作。

主要组件：
- AccountValueHistorysDatabase: 账户价值历史数据操作类
"""

import logging
from typing import Dict, List, Optional, Any, Callable
import pymysql
from .database_basic import create_pooled_db
import common.config as app_config
from .database_init import ACCOUNT_VALUE_HISTORYS_TABLE

logger = logging.getLogger(__name__)


class AccountValueHistorysDatabase:
    """
    账户价值历史数据操作类
    
    封装account_value_historys表的所有数据库操作。
    """
    
    def __init__(self, pool=None):
        """
        初始化账户价值历史数据库操作类
        
        Args:
            pool: 可选的数据库连接池，如果不提供则创建新的连接池
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
        
        self.account_value_historys_table = ACCOUNT_VALUE_HISTORYS_TABLE
    
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
                        except Exception:
                            pass
                        try:
                            conn.close()
                        except Exception:
                            pass
                        conn = None
                    except Exception as close_error:
                        logger.debug(f"[AccountValueHistorys] Error closing failed connection: {close_error}")
                        conn = None
                
                if attempt < max_retries - 1:
                    if not is_network_error:
                        raise
                    
                    is_deadlock = (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213) or 'deadlock' in error_msg.lower()
                    if is_deadlock:
                        wait_time = 1.0 * (1.5 ** attempt)
                        logger.warning(
                            f"[AccountValueHistorys] Deadlock error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    else:
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(
                            f"[AccountValueHistorys] Network error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    
                    import time
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"[AccountValueHistorys] Failed after {max_retries} attempts: "
                        f"{error_type}: {error_msg}"
                    )
                    raise
            finally:
                if connection_acquired and conn:
                    try:
                        logger.warning(
                            f"[AccountValueHistorys] Connection not closed in finally block, closing it"
                        )
                        try:
                            conn.rollback()
                            conn.close()
                        except Exception:
                            pass
                    except Exception as final_error:
                        logger.debug(f"[AccountValueHistorys] Error in finally block: {final_error}")
    
    def _row_to_dict(self, row: tuple, columns: list) -> Dict:
        """Convert a row tuple to a dictionary"""
        return dict(zip(columns, row))
    
    def _rows_to_dicts(self, rows: List[tuple], columns: list) -> List[Dict]:
        """Convert rows to list of dictionaries"""
        return [self._row_to_dict(row, columns) for row in rows]
    
    def _format_timestamp_to_string(self, timestamp) -> str:
        """Format timestamp to string (UTC+8 timezone)"""
        if timestamp is None:
            return ""
        if isinstance(timestamp, str):
            return timestamp
        if hasattr(timestamp, 'strftime'):
            # 如果是datetime对象，转换为字符串（假设已经是UTC+8时区）
            return timestamp.strftime('%Y-%m-%d %H:%M:%S')
        return str(timestamp)
    
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
    
    def get_account_value_history(self, model_id: int, limit: int = 100,
                                model_id_mapping: Dict[int, str] = None) -> List[Dict]:
        """
        Get account value history for a specific model
        
        Args:
            model_id: 模型ID（整数）
            limit: 返回记录数限制
            model_id_mapping: 可选的模型ID映射字典
        
        Returns:
            账户价值历史记录列表，包含新字段名：
            - accountAlias: 账户唯一识别码
            - balance: 总余额
            - availableBalance: 下单可用余额
            - crossWalletBalance: 全仓余额
            - crossUnPnl: 全仓持仓未实现盈亏
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
                logger.warning(f"[AccountValueHistorys] Model {model_id} UUID not found in mapping")
                return []
            
            # 【修改】从 account_value_historys 表查询历史记录（用于图表显示）
            # 使用参数化查询确保只查询当前模型的数据
            rows = self.query(f"""
                SELECT id, model_id, account_alias, balance, available_balance, 
                       cross_wallet_balance, cross_un_pnl, timestamp
                FROM {self.account_value_historys_table}
                WHERE model_id = %s
                ORDER BY timestamp DESC
                LIMIT %s
            """, (model_uuid, limit))
            columns = ["id", "model_id", "account_alias", "balance", "available_balance", 
                      "cross_wallet_balance", "cross_un_pnl", "timestamp"]
            results = self._rows_to_dicts(rows, columns)
            
            # 转换为驼峰命名格式，并将timestamp转换为字符串格式（UTC+8时间）
            formatted_results = []
            for result in results:
                timestamp_str = self._format_timestamp_to_string(result.get("timestamp"))
                
                formatted_results.append({
                    "id": result.get("id"),
                    "model_id": result.get("model_id"),
                    "accountAlias": result.get("account_alias", ""),
                    "balance": result.get("balance", 0.0),
                    "availableBalance": result.get("available_balance", 0.0),
                    "crossWalletBalance": result.get("cross_wallet_balance", 0.0),
                    "crossUnPnl": result.get("cross_un_pnl", 0.0),
                    "timestamp": timestamp_str
                })
            return formatted_results
        except Exception as e:
            logger.error(f"[AccountValueHistorys] Failed to get account value history for model {model_id}: {e}")
            return []

