"""
账户每日价值数据表操作模块 - account_values_daily 表

本模块提供账户每日价值数据的增删改查操作。

主要组件：
- AccountValuesDailyDatabase: 账户每日价值数据操作类
"""

import logging
import uuid
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Callable
import pymysql
from .database_basic import create_pooled_db
import trade.common.config as app_config
from .database_init import ACCOUNT_VALUES_DAILY_TABLE

logger = logging.getLogger(__name__)


class AccountValuesDailyDatabase:
    """
    账户每日价值数据操作类
    
    封装account_values_daily表的所有数据库操作。
    """
    
    def __init__(self, pool=None):
        """
        初始化账户每日价值数据库操作类
        
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
        
        self.account_values_daily_table = ACCOUNT_VALUES_DAILY_TABLE
    
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
                            logger.debug(f"[AccountValuesDaily] Error rolling back transaction: {rollback_error}")
                        
                        try:
                            conn.close()
                        except Exception as close_error:
                            logger.debug(f"[AccountValuesDaily] Error closing connection: {close_error}")
                        finally:
                            conn = None
                    except Exception as cleanup_error:
                        logger.debug(f"[AccountValuesDaily] Error during cleanup: {cleanup_error}")
                
                if not is_network_error or attempt == max_retries - 1:
                    logger.error(f"[AccountValuesDaily] Database operation failed (attempt {attempt + 1}/{max_retries}): {error_type}: {error_msg}", exc_info=True)
                    raise
                
                logger.warning(f"[AccountValuesDaily] Network error occurred (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay *= 2
    
    def record_daily_account_value(self, model_id: str, balance: float, available_balance: float) -> bool:
        """
        记录每日账户价值（每天8点调用）
        
        Args:
            model_id: 模型ID（UUID格式）
            balance: 账户总值
            available_balance: 可用现金
            
        Returns:
            bool: 是否成功
        """
        try:
            def _execute_insert(conn):
                cursor = conn.cursor()
                try:
                    # 获取当前时间（北京时间）
                    beijing_tz = timezone(timedelta(hours=8))
                    now = datetime.now(beijing_tz)
                    
                    # 生成ID
                    record_id = str(uuid.uuid4())
                    
                    sql = f"""
                    INSERT INTO `{self.account_values_daily_table}` 
                    (`id`, `model_id`, `balance`, `available_balance`, `created_at`)
                    VALUES (%s, %s, %s, %s, %s)
                    """
                    cursor.execute(sql, (record_id, model_id, balance, available_balance, now))
                    logger.info(f"[AccountValuesDaily] Recorded daily account value for model {model_id}: balance={balance:.2f}, available_balance={available_balance:.2f}")
                    return True
                finally:
                    cursor.close()
            
            return self._with_connection(_execute_insert)
        except Exception as e:
            logger.error(f"[AccountValuesDaily] Failed to record daily account value for model {model_id}: {e}")
            return False
    
    def get_today_account_value(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        获取当天的账户价值记录（当天指从早上8点到第二天早上8点）
        
        Args:
            model_id: 模型ID（UUID格式）
            
        Returns:
            Optional[Dict]: 包含balance和available_balance的字典，如果不存在则返回None
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
                    
                    # 查询当天的记录（从今天早上8点开始）
                    sql = f"""
                    SELECT `balance`, `available_balance`, `created_at`
                    FROM `{self.account_values_daily_table}`
                    WHERE `model_id` = %s 
                    AND `created_at` >= %s
                    ORDER BY `created_at` DESC
                    LIMIT 1
                    """
                    cursor.execute(sql, (model_id, today_start))
                    row = cursor.fetchone()
                    
                    if row:
                        # 处理字典格式（DictCursor）或元组格式（普通cursor）
                        if isinstance(row, dict):
                            balance = row.get('balance')
                            available_balance = row.get('available_balance')
                            created_at = row.get('created_at')
                        elif isinstance(row, (tuple, list)):
                            balance = row[0]
                            available_balance = row[1]
                            created_at = row[2]
                        else:
                            logger.warning(f"[AccountValuesDaily] Unexpected row format for model {model_id}: {type(row)}")
                            return None
                        
                        return {
                            'balance': float(balance) if balance is not None else 0.0,
                            'available_balance': float(available_balance) if available_balance is not None else 0.0,
                            'created_at': created_at
                        }
                    return None
                finally:
                    cursor.close()
            
            return self._with_connection(_execute_query)
        except Exception as e:
            logger.error(f"[AccountValuesDaily] Failed to get today account value for model {model_id}: {e}")
            return None
    
    def has_any_record(self, model_id: str) -> bool:
        """
        检查模型是否有任何记录
        
        Args:
            model_id: 模型ID（UUID格式）
            
        Returns:
            bool: 是否有记录
        """
        try:
            def _execute_query(conn):
                cursor = conn.cursor()
                try:
                    sql = f"""
                    SELECT COUNT(*) as count
                    FROM `{self.account_values_daily_table}`
                    WHERE `model_id` = %s
                    """
                    cursor.execute(sql, (model_id,))
                    row = cursor.fetchone()
                    if row is None:
                        logger.warning(f"[AccountValuesDaily] COUNT query returned None for model {model_id}")
                        return False
                    
                    # 处理字典格式（DictCursor）或元组格式（普通cursor）
                    if isinstance(row, dict):
                        count = row.get('count') or row.get('COUNT(*)')
                    elif isinstance(row, (tuple, list)):
                        count = row[0]
                    else:
                        count = row
                    
                    if count is None:
                        logger.warning(f"[AccountValuesDaily] COUNT value is None for model {model_id}")
                        return False
                    
                    # 确保count是数字类型
                    try:
                        count_int = int(count)
                        return count_int > 0
                    except (ValueError, TypeError) as e:
                        logger.error(f"[AccountValuesDaily] Failed to convert count to int for model {model_id}: count={count}, type={type(count)}, error={e}")
                        return False
                finally:
                    cursor.close()
            
            return self._with_connection(_execute_query)
        except Exception as e:
            logger.error(f"[AccountValuesDaily] Failed to check records for model {model_id}: {e}", exc_info=True)
            return False
