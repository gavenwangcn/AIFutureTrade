"""
模型提示词数据表操作模块 - model_prompts �?

本模块提供模型提示词配置的增删改查操作�?

主要组件�?
- ModelPromptsDatabase: 模型提示词数据操作类
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
    模型提示词数据操作类
    
    封装model_prompts表的所有数据库操作�?
    """
    
    def __init__(self, pool=None):
        """
        初始化模型提示词数据库操作类
        
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
                
                # 如果已获取连接，需要处理连接（关闭�?
                # 无论什么异常，都要确保连接被正确释放，防止连接泄露
                if connection_acquired and conn:
                    try:
                        # 回滚事务
                        try:
                            conn.rollback()
                        except Exception as rollback_error:
                            logger.debug(f"[ModelPrompts] Error rolling back transaction: {rollback_error}")
                        
                        # 对于所有错误，关闭连接，DBUtils会自动处理损坏的连接
                        try:
                            conn.close()
                        except Exception as close_error:
                            logger.debug(f"[ModelPrompts] Error closing connection: {close_error}")
                        finally:
                            # 确保连接引用被清除，即使关闭失败也要标记为已处理
                            conn = None
                    except Exception as close_error:
                        logger.error(f"[ModelPrompts] Critical error closing failed connection: {close_error}")
                        # 即使发生异常，也要清除连接引�?
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
            model_id: 模型ID（整数）
            model_id_mapping: 可选的模型ID映射字典，如果不提供则从数据库查�?
        
        Returns:
            模型提示词配置字典，如果不存在则返回None
        """
        try:
            # 如果没有提供映射，需要从数据库查询（这里简化处理，实际应该由调用方提供�?
            if model_id_mapping is None:
                # 查询所有模型ID
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
            result['model_id'] = model_id  # 转换�?int ID
            return result
        except Exception as e:
            logger.error(f"[ModelPrompts] Failed to get model prompt for model {model_id}: {e}")
            return None
    
    def upsert_model_prompt(self, model_id: int, buy_prompt: Optional[str], sell_prompt: Optional[str], 
                           model_id_mapping: Dict[int, str] = None) -> bool:
        """
        Insert or update model prompt configuration
        
        Args:
            model_id: 模型ID（整数）
            buy_prompt: 买入提示�?
            sell_prompt: 卖出提示�?
            model_id_mapping: 可选的模型ID映射字典
        
        Returns:
            bool: 是否成功
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
            
            # MySQL使用 INSERT ... ON DUPLICATE KEY UPDATE
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

