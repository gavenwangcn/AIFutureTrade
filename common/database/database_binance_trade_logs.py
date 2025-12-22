"""
币安交易日志数据表操作模块 - binance_trade_logs 表

本模块提供币安交易日志的增删改查操作。

主要组件：
- BinanceTradeLogsDatabase: 币安交易日志数据操作类
"""

import logging
import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Callable
import pymysql
from .database_basic import create_pooled_db
import common.config as app_config
from .database_init import BINANCE_TRADE_LOGS_TABLE

logger = logging.getLogger(__name__)


class BinanceTradeLogsDatabase:
    """
    币安交易日志数据操作类
    
    封装binance_trade_logs表的所有数据库操作。
    """
    
    def __init__(self, pool=None):
        """
        初始化币安交易日志数据库操作类
        
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
        
        self.binance_trade_logs_table = BINANCE_TRADE_LOGS_TABLE
    
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
                            logger.debug(f"[BinanceTradeLogs] Error rolling back transaction: {rollback_error}")
                        
                        # 对于所有错误，关闭连接，DBUtils会自动处理损坏的连接
                        try:
                            conn.close()
                        except Exception as close_error:
                            logger.debug(f"[BinanceTradeLogs] Error closing connection: {close_error}")
                        finally:
                            # 确保连接引用被清除，即使关闭失败也要标记为已处理
                            conn = None
                    except Exception as close_error:
                        logger.error(f"[BinanceTradeLogs] Critical error closing failed connection: {close_error}")
                        # 即使发生异常，也要清除连接引用
                        conn = None
                
                if attempt < max_retries - 1:
                    if not is_network_error:
                        raise
                    
                    is_deadlock = (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213) or 'deadlock' in error_msg.lower()
                    if is_deadlock:
                        wait_time = 1.0 * (1.5 ** attempt)
                        logger.warning(
                            f"[BinanceTradeLogs] Deadlock error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    else:
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(
                            f"[BinanceTradeLogs] Network error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    
                    import time
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"[BinanceTradeLogs] Failed after {max_retries} attempts: "
                        f"{error_type}: {error_msg}"
                    )
                    raise
            finally:
                if connection_acquired and conn:
                    try:
                        logger.warning(
                            f"[BinanceTradeLogs] Connection not closed in finally block, closing it"
                        )
                        try:
                            conn.rollback()
                            conn.close()
                        except Exception:
                            pass
                    except Exception as final_error:
                        logger.debug(f"[BinanceTradeLogs] Error in finally block: {final_error}")
    
    def _generate_id(self) -> str:
        """Generate a unique ID (UUID)"""
        return str(uuid.uuid4())
    
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
    
    def add_binance_trade_log(self, model_id: Optional[str] = None, conversation_id: Optional[str] = None, 
                              trade_id: Optional[str] = None, type: str = "test", method_name: str = "",
                              param: Optional[Dict[str, Any]] = None, response_context: Optional[Dict[str, Any]] = None,
                              response_type: Optional[str] = None, error_context: Optional[str] = None):
        """
        添加币安交易日志记录
        
        Args:
            model_id: 模型ID (UUID字符串)
            conversation_id: 对话ID (UUID字符串)
            trade_id: 交易ID (UUID字符串)
            type: 接口类型，'test' 或 'real'
            method_name: 方法名称，如 'stop_loss_trade', 'take_profit_trade' 等
            param: 调用接口的入参，字典格式
            response_context: 接口返回的内容，字典格式
            response_type: 接口返回状态码，如 '200', '4XX', '5XX' 等
            error_context: 接口返回状态不为200时记录相关的返回错误信息
        """
        try:
            log_id = self._generate_id()
            
            # 将字典转换为JSON字符串
            param_json = json.dumps(param) if param else None
            response_json = json.dumps(response_context) if response_context else None
            
            # 使用 UTC+8 时区时间（北京时间），转换为 naive datetime 存储
            beijing_tz = timezone(timedelta(hours=8))
            current_time = datetime.now(beijing_tz).replace(tzinfo=None)
            
            self.insert_rows(
                self.binance_trade_logs_table,
                [[log_id, model_id, conversation_id, trade_id, type, method_name, param_json, response_json, response_type, error_context, current_time]],
                ["id", "model_id", "conversation_id", "trade_id", "type", "method_name", "param", "response_context", "response_type", "error_context", "created_at"]
            )
        except Exception as e:
            logger.error(f"[BinanceTradeLogs] Failed to add binance trade log: {e}")
            # 不抛出异常，避免影响主流程

