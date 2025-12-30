"""
账户资产数据表操作模�?- account_asset �?

本模块提供账户资产数据的增删改查操作�?

主要组件�?
- AccountAssetDatabase: 账户资产数据操作�?
"""

import logging
from typing import Dict, List, Optional, Any, Callable
import pymysql
from .database_basic import create_pooled_db
import trade.common.config as app_config
from .database_init import ACCOUNT_ASSET_TABLE

logger = logging.getLogger(__name__)


class AccountAssetDatabase:
    """
    账户资产数据操作�?
    
    封装account_asset表的所有数据库操作�?
    """
    
    def __init__(self, pool=None):
        """
        初始化账户资产数据库操作�?
        
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
        
        self.account_asset_table = ACCOUNT_ASSET_TABLE
    
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
                
                # 如果已获取连接，需要处理连接（关闭�?
                # 无论什么异常，都要确保连接被正确释放，防止连接泄露
                if connection_acquired and conn:
                    try:
                        # 回滚事务
                        try:
                            conn.rollback()
                        except Exception as rollback_error:
                            logger.debug(f"[AccountAsset] Error rolling back transaction: {rollback_error}")
                        
                        # 对于所有错误，关闭连接，DBUtils会自动处理损坏的连接
                        try:
                            conn.close()
                        except Exception as close_error:
                            logger.debug(f"[AccountAsset] Error closing connection: {close_error}")
                        finally:
                            # 确保连接引用被清除，即使关闭失败也要标记为已处理
                            conn = None
                    except Exception as close_error:
                        logger.error(f"[AccountAsset] Critical error closing failed connection: {close_error}")
                        # 即使发生异常，也要清除连接引�?
                        conn = None
                
                if attempt < max_retries - 1:
                    if not is_network_error:
                        raise
                    
                    is_deadlock = (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213) or 'deadlock' in error_msg.lower()
                    if is_deadlock:
                        wait_time = 1.0 * (1.5 ** attempt)
                        logger.warning(
                            f"[AccountAsset] Deadlock error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    else:
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(
                            f"[AccountAsset] Network error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    
                    import time
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"[AccountAsset] Failed after {max_retries} attempts: "
                        f"{error_type}: {error_msg}"
                    )
                    raise
            finally:
                if connection_acquired and conn:
                    try:
                        logger.warning(
                            f"[AccountAsset] Connection not closed in finally block, closing it"
                        )
                        try:
                            conn.rollback()
                            conn.close()
                        except Exception:
                            pass
                    except Exception as final_error:
                        logger.debug(f"[AccountAsset] Error in finally block: {final_error}")
    
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
    
    def get_account_asset(self, account_alias: str) -> Optional[Dict]:
        """
        获取账户资产信息（最新记录）
        
        Args:
            account_alias: 账户唯一识别�?
            
        Returns:
            账户资产信息字典，如果不存在则返回None
            返回格式包含字段映射�?
            - balance: total_wallet_balance
            - cross_wallet_balance: total_cross_wallet_balance
            - available_balance: available_balance
            - cross_un_pnl: total_cross_un_pnl
        """
        try:
            rows = self.query(f"""
                SELECT `account_alias`, `total_initial_margin`, `total_maint_margin`, `total_wallet_balance`,
                       `total_unrealized_profit`, `total_margin_balance`, `total_position_initial_margin`,
                       `total_open_order_initial_margin`, `total_cross_wallet_balance`, `total_cross_un_pnl`,
                       `available_balance`, `max_withdraw_amount`, `update_time`, `created_at`
                FROM `{self.account_asset_table}`
                WHERE `account_alias` = %s
                ORDER BY `update_time` DESC
                LIMIT 1
            """, (account_alias,))
            
            if not rows:
                return None
            
            columns = ["account_alias", "total_initial_margin", "total_maint_margin", "total_wallet_balance",
                      "total_unrealized_profit", "total_margin_balance", "total_position_initial_margin",
                      "total_open_order_initial_margin", "total_cross_wallet_balance", "total_cross_un_pnl",
                      "available_balance", "max_withdraw_amount", "update_time", "created_at"]
            result = self._row_to_dict(rows[0], columns)
            
            # 返回标准格式，字段映射为AI需要的格式
            return {
                "account_alias": result["account_alias"],
                "balance": float(result["total_wallet_balance"]) if result["total_wallet_balance"] is not None else 0.0,
                "cross_wallet_balance": float(result["total_cross_wallet_balance"]) if result["total_cross_wallet_balance"] is not None else 0.0,
                "available_balance": float(result["available_balance"]) if result["available_balance"] is not None else 0.0,
                "cross_un_pnl": float(result["total_cross_un_pnl"]) if result["total_cross_un_pnl"] is not None else 0.0
            }
        except Exception as e:
            logger.error(f"[AccountAsset] Failed to get account asset {account_alias}: {e}")
            return None

