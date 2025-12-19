"""
策略数据表操作模块 - strategys 和 model_strategy 表

本模块提供策略数据的增删改查操作，包括：
1. 策略查询
2. 模型策略关联查询

主要组件：
- StrategysDatabase: 策略数据操作类
"""

import logging
from typing import List, Dict, Optional, Any, Callable
from .database_basic import create_pooled_db
import common.config as app_config
import pymysql

logger = logging.getLogger(__name__)


class StrategysDatabase:
    """
    策略数据操作类
    
    封装strategys和model_strategy表的所有数据库操作。
    """
    
    def __init__(self, pool=None):
        """
        初始化策略数据库操作类
        
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
                        logger.debug(f"[Strategys] Error closing failed connection: {close_error}")
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
        获取模型关联的策略列表（按优先级和创建时间排序）
        
        Args:
            model_id: 模型ID（UUID字符串）
            strategy_type: 策略类型，'buy' 或 'sell'
        
        Returns:
            List[Dict]: 策略列表，每个元素包含：
                - id: 关联ID
                - model_id: 模型ID
                - strategy_id: 策略ID
                - type: 策略类型
                - priority: 优先级
                - created_at: 创建时间
                - strategy_name: 策略名称
                - strategy_code: 策略代码
                - strategy_context: 策略上下文
        """
        try:
            model_uuid = model_id
            
            # 查询model_strategy表，关联strategys表获取策略详情
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

