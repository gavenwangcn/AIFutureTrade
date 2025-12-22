"""
系统设置数据表操作模块 - settings 表

本模块提供系统设置的增删改查操作。

主要组件：
- SettingsDatabase: 系统设置数据操作类
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Callable
import pymysql
from .database_basic import create_pooled_db
import common.config as app_config

logger = logging.getLogger(__name__)


class SettingsDatabase:
    """
    系统设置数据操作类
    
    封装settings表的所有数据库操作。
    """
    
    def __init__(self, pool=None):
        """
        初始化系统设置数据库操作类
        
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
        
        self.settings_table = "settings"
    
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
                
                # 如果已获取连接，需要处理连接（关闭）
                # 无论什么异常，都要确保连接被正确释放，防止连接泄露
                if connection_acquired and conn:
                    try:
                        # 回滚事务
                        try:
                            conn.rollback()
                        except Exception as rollback_error:
                            logger.debug(f"[Settings] Error rolling back transaction: {rollback_error}")
                        
                        # 对于所有错误，关闭连接，DBUtils会自动处理损坏的连接
                        try:
                            conn.close()
                        except Exception as close_error:
                            logger.debug(f"[Settings] Error closing connection: {close_error}")
                        finally:
                            # 确保连接引用被清除，即使关闭失败也要标记为已处理
                            conn = None
                    except Exception as close_error:
                        logger.error(f"[Settings] Critical error closing failed connection: {close_error}")
                        # 即使发生异常，也要清除连接引用
                        conn = None
                
                if attempt < max_retries - 1:
                    if not is_network_error:
                        raise
                    
                    is_deadlock = (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213) or 'deadlock' in error_msg.lower()
                    if is_deadlock:
                        wait_time = 1.0 * (1.5 ** attempt)
                        logger.warning(
                            f"[Settings] Deadlock error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    else:
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(
                            f"[Settings] Network error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    
                    import time
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"[Settings] Failed after {max_retries} attempts: "
                        f"{error_type}: {error_msg}"
                    )
                    raise
            finally:
                if connection_acquired and conn:
                    try:
                        logger.warning(
                            f"[Settings] Connection not closed in finally block, closing it"
                        )
                        try:
                            conn.rollback()
                            conn.close()
                        except Exception:
                            pass
                    except Exception as final_error:
                        logger.debug(f"[Settings] Error in finally block: {final_error}")
    
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
    
    def insert_rows(self, table: str, rows: list, column_names: list) -> None:
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
    
    def get_settings(self) -> Dict:
        """
        Get system settings
        
        Returns:
            系统设置字典
        """
        try:
            rows = self.query(f"""
                SELECT buy_frequency_minutes, sell_frequency_minutes, trading_fee_rate, show_system_prompt, conversation_limit
                FROM {self.settings_table}
                ORDER BY updated_at DESC
                LIMIT 1
            """)
            
            if rows:
                columns = ["buy_frequency_minutes", "sell_frequency_minutes", "trading_fee_rate", "show_system_prompt", "conversation_limit"]
                result = self._row_to_dict(rows[0], columns)
                return {
                    'buy_frequency_minutes': int(result.get('buy_frequency_minutes', 5)),
                    'sell_frequency_minutes': int(result.get('sell_frequency_minutes', 5)),
                    'trading_fee_rate': float(result['trading_fee_rate']),
                    'show_system_prompt': int(result.get('show_system_prompt', 0)),
                    'conversation_limit': int(result.get('conversation_limit', 5))
                }
            else:
                # 返回默认设置
                return {
                    'buy_frequency_minutes': 5,
                    'sell_frequency_minutes': 5,
                    'trading_fee_rate': 0.001,
                    'show_system_prompt': 0,
                    'conversation_limit': 5
                }
        except Exception as e:
            logger.error(f"[Settings] Failed to get settings: {e}")
            return {
                'buy_frequency_minutes': 5,
                'sell_frequency_minutes': 5,
                'trading_fee_rate': 0.001,
                'show_system_prompt': 0,
                'conversation_limit': 5
            }
    
    def update_settings(self, buy_frequency_minutes: int, sell_frequency_minutes: int, trading_fee_rate: float,
                        show_system_prompt: int, conversation_limit: int = 5) -> bool:
        """
        Update system settings
        
        Args:
            buy_frequency_minutes: 买入频率（分钟）
            sell_frequency_minutes: 卖出频率（分钟）
            trading_fee_rate: 交易手续费率
            show_system_prompt: 是否显示系统提示词
            conversation_limit: 对话历史限制
        
        Returns:
            bool: 是否成功
        """
        try:
            # 使用 UTC+8 时区时间（北京时间），转换为 naive datetime 存储
            beijing_tz = timezone(timedelta(hours=8))
            current_time = datetime.now(beijing_tz).replace(tzinfo=None)
            
            # 验证频率值
            if not isinstance(buy_frequency_minutes, int) or buy_frequency_minutes < 1:
                logger.warning(f"[Settings] Invalid buy_frequency_minutes value: {buy_frequency_minutes}, using default 5")
                buy_frequency_minutes = 5
            if not isinstance(sell_frequency_minutes, int) or sell_frequency_minutes < 1:
                logger.warning(f"[Settings] Invalid sell_frequency_minutes value: {sell_frequency_minutes}, using default 5")
                sell_frequency_minutes = 5
            
            # 验证conversation_limit值
            if not isinstance(conversation_limit, int) or conversation_limit < 1:
                logger.warning(f"[Settings] Invalid conversation_limit value: {conversation_limit}, using default 5")
                conversation_limit = 5
            
            # 先检查是否存在记录
            existing_rows = self.query(f"""
                SELECT id FROM {self.settings_table}
                ORDER BY updated_at DESC
                LIMIT 1
            """)
            
            if existing_rows and len(existing_rows) > 0:
                # 如果存在记录，使用 UPDATE 更新
                settings_id = existing_rows[0][0]
                self.command(f"""
                    UPDATE {self.settings_table}
                    SET buy_frequency_minutes = %s,
                        sell_frequency_minutes = %s,
                        trading_fee_rate = %s,
                        show_system_prompt = %s,
                        conversation_limit = %s,
                        updated_at = %s
                    WHERE id = %s
                """, (buy_frequency_minutes, sell_frequency_minutes, trading_fee_rate, show_system_prompt, conversation_limit, current_time, settings_id))
            else:
                # 如果不存在记录，使用 INSERT 插入
                settings_id = str(uuid.uuid4())
                self.insert_rows(
                    self.settings_table,
                    [[settings_id, buy_frequency_minutes, sell_frequency_minutes, trading_fee_rate, show_system_prompt, conversation_limit, current_time, current_time]],
                    ["id", "buy_frequency_minutes", "sell_frequency_minutes", "trading_fee_rate", "show_system_prompt", "conversation_limit", "created_at", "updated_at"]
                )
            return True
        except Exception as e:
            logger.error(f"[Settings] Failed to update settings: {e}")
            return False

