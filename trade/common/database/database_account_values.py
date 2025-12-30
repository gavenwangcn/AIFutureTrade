"""
账户价值数据表操作模块 - account_values �?

本模块提供账户价值数据的增删改查操作�?

主要组件�?
- AccountValuesDatabase: 账户价值数据操作类
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Callable
import pymysql
from .database_basic import create_pooled_db
import trade.common.config as app_config
from .database_init import ACCOUNT_VALUES_TABLE

logger = logging.getLogger(__name__)


class AccountValuesDatabase:
    """
    账户价值数据操作类
    
    封装account_values表的所有数据库操作�?
    """
    
    def __init__(self, pool=None):
        """
        初始化账户价值数据库操作�?
        
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
        
        self.account_values_table = ACCOUNT_VALUES_TABLE
    
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
                            logger.debug(f"[AccountValues] Error rolling back transaction: {rollback_error}")
                        
                        # 对于所有错误，关闭连接，DBUtils会自动处理损坏的连接
                        try:
                            conn.close()
                        except Exception as close_error:
                            logger.debug(f"[AccountValues] Error closing connection: {close_error}")
                        finally:
                            # 确保连接引用被清除，即使关闭失败也要标记为已处理
                            conn = None
                    except Exception as close_error:
                        logger.error(f"[AccountValues] Critical error closing failed connection: {close_error}")
                        # 即使发生异常，也要清除连接引�?
                        conn = None
                
                if attempt < max_retries - 1:
                    if not is_network_error:
                        raise
                    
                    is_deadlock = (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213) or 'deadlock' in error_msg.lower()
                    if is_deadlock:
                        wait_time = 1.0 * (1.5 ** attempt)
                        logger.warning(
                            f"[AccountValues] Deadlock error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    else:
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(
                            f"[AccountValues] Network error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    
                    import time
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"[AccountValues] Failed after {max_retries} attempts: "
                        f"{error_type}: {error_msg}"
                    )
                    raise
            finally:
                if connection_acquired and conn:
                    try:
                        logger.warning(
                            f"[AccountValues] Connection not closed in finally block, closing it"
                        )
                        try:
                            conn.rollback()
                            conn.close()
                        except Exception:
                            pass
                    except Exception as final_error:
                        logger.debug(f"[AccountValues] Error in finally block: {final_error}")
    
    def _generate_id(self) -> str:
        """Generate a unique ID (UUID)"""
        return str(uuid.uuid4())
    
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
    
    def record_account_value(self, model_id: int, balance: float,
                            available_balance: float, cross_wallet_balance: float,
                            account_alias: str = '', cross_un_pnl: float = 0.0,
                            model_id_mapping: Dict[int, str] = None,
                            get_model_func: Callable[[int], Optional[Dict]] = None,
                            account_value_historys_table: str = None):
        """
        Record account value snapshot
        
        注意：每个model_id应该只有一条记录，如果已存在则UPDATE，不存在则INSERT�?
        如果传入的account_alias为空，则从models表获取或保留原有值�?
        
        Args:
            model_id: 模型ID
            balance: 总余�?
            available_balance: 下单可用余额
            cross_wallet_balance: 全仓余额
            account_alias: 账户唯一识别码（可选，默认空字符串�?
            cross_un_pnl: 全仓持仓未实现盈亏（可选，默认0.0�?
            model_id_mapping: 可选的模型ID映射字典
            get_model_func: 可选的获取模型信息的函�?
            account_value_historys_table: 可选的账户价值历史表�?
        """
        try:
            logger.debug(f"[AccountValues] [开始记录账户价值] model_id={model_id}, balance=${balance:.2f}, "
                       f"available_balance=${available_balance:.2f}, cross_wallet_balance=${cross_wallet_balance:.2f}, "
                       f"account_alias={account_alias}")
            
            if model_id_mapping is None:
                rows = self.query(f"SELECT id FROM models")
                model_id_mapping = {}
                for row in rows:
                    uuid_str = row[0]
                    int_id = abs(hash(uuid_str)) % (10 ** 9)
                    model_id_mapping[int_id] = uuid_str
            
            model_uuid = model_id_mapping.get(model_id)
            if not model_uuid:
                logger.warning(f"[AccountValues] Model {model_id} not found for account value record")
                return
            
            logger.debug(f"[AccountValues] [模型ID映射] model_id={model_id} -> model_uuid={model_uuid}")
            
            # 检查是否已存在记录
            logger.debug(f"[AccountValues] [检查现有记录] 查询account_values表，model_uuid={model_uuid}")
            existing_rows = self.query(f"""
                SELECT id, account_alias 
                FROM {self.account_values_table}
                WHERE model_id = %s
                ORDER BY timestamp DESC
                LIMIT 1
            """, (model_uuid,))
            
            if existing_rows:
                logger.debug(f"[AccountValues] [检查现有记录] 找到现有记录: id={existing_rows[0][0]}, account_alias={existing_rows[0][1]}")
            else:
                logger.debug(f"[AccountValues] [检查现有记录] 未找到现有记录，将执行INSERT操作")
            
            # 如果account_alias为空，尝试从models表获�?
            if not account_alias:
                logger.debug(f"[AccountValues] [处理account_alias] 传入的account_alias为空，尝试获�?)
                if existing_rows:
                    # 如果已存在记录，保留原有的account_alias
                    account_alias = existing_rows[0][1] or ''
                    logger.debug(f"[AccountValues] [处理account_alias] 从现有记录获�? account_alias={account_alias}")
                else:
                    # 如果不存在记录，从models表获取account_alias
                    logger.debug(f"[AccountValues] [处理account_alias] 从models表获取account_alias")
                    if get_model_func:
                        model = get_model_func(model_id)
                    else:
                        from .database_models import ModelsDatabase
                        models_db = ModelsDatabase(pool=self._pool)
                        model = models_db.get_model(model_id)
                    
                    if model and model.get('account_alias'):
                        account_alias = model['account_alias']
                        logger.debug(f"[AccountValues] [处理account_alias] 从models表获�? account_alias={account_alias}")
                    else:
                        account_alias = ''
                        logger.warning(f"[AccountValues] [处理account_alias] account_alias为空，使用空字符�?)
            else:
                logger.debug(f"[AccountValues] [处理account_alias] 使用传入的account_alias: {account_alias}")
            
            # 确定最终使用的 account_alias（用于后续的 INSERT 操作�?
            final_account_alias_for_history = account_alias
            if existing_rows:
                # 已存在记录，执行UPDATE（保留原有的account_alias如果传入的为空）
                existing_id = existing_rows[0][0]
                existing_account_alias = existing_rows[0][1] or ''
                # 如果传入的account_alias为空，使用原有的account_alias
                final_account_alias = account_alias if account_alias else existing_account_alias
                final_account_alias_for_history = final_account_alias
                
                # 使用UTC+8时区时间
                beijing_tz = timezone(timedelta(hours=8))
                current_time = datetime.now(beijing_tz)
                
                logger.debug(f"[AccountValues] [更新account_values表] model_id={model_id} (uuid={model_uuid}), "
                           f"balance=${balance:.2f}, available_balance=${available_balance:.2f}, "
                           f"cross_wallet_balance=${cross_wallet_balance:.2f}, account_alias={final_account_alias}")
                
                self.command(f"""
                    UPDATE {self.account_values_table}
                    SET account_alias = %s,
                        balance = %s,
                        available_balance = %s,
                        cross_wallet_balance = %s,
                        cross_un_pnl = %s,
                        timestamp = %s
                    WHERE id = %s
                """, (final_account_alias, balance, available_balance, cross_wallet_balance, cross_un_pnl, current_time, existing_id))
                logger.debug(f"[AccountValues] [更新account_values表] 成功更新记录: model_id={model_id} (id={existing_id}), "
                           f"account_alias={final_account_alias}, timestamp={current_time}")
            else:
                # 不存在记录，执行INSERT
                # 使用UTC+8时区时间
                beijing_tz = timezone(timedelta(hours=8))
                current_time = datetime.now(beijing_tz)
                av_id = self._generate_id()
                
                logger.debug(f"[AccountValues] [插入account_values表] model_id={model_id} (uuid={model_uuid}), "
                           f"balance=${balance:.2f}, available_balance=${available_balance:.2f}, "
                           f"cross_wallet_balance=${cross_wallet_balance:.2f}, account_alias={account_alias}")
                
                self.insert_rows(
                    self.account_values_table,
                    [[av_id, model_uuid, account_alias, balance, available_balance, cross_wallet_balance, cross_un_pnl, current_time]],
                    ["id", "model_id", "account_alias", "balance", "available_balance", "cross_wallet_balance", "cross_un_pnl", "timestamp"]
                )
                logger.debug(f"[AccountValues] [插入account_values表] 成功插入记录: model_id={model_id} (id={av_id}), "
                           f"account_alias={account_alias}, timestamp={current_time}")
                final_account_alias_for_history = account_alias
            
            # 【新增】同时写�?account_value_historys 表（用于历史图表，只INSERT，不UPDATE�?
            # 每次记录都插入一条新记录，保留完整历�?
            # 使用UTC+8时间（北京时间）
            if account_value_historys_table:
                try:
                    history_id = self._generate_id()
                    # 使用UTC+8时区时间
                    beijing_tz = timezone(timedelta(hours=8))
                    current_time = datetime.now(beijing_tz)
                    
                    logger.debug(f"[AccountValues] [插入account_value_historys表] model_id={model_id} (uuid={model_uuid}), "
                               f"balance=${balance:.2f}, available_balance=${available_balance:.2f}, "
                               f"cross_wallet_balance=${cross_wallet_balance:.2f}, account_alias={final_account_alias_for_history}")
                    
                    self.insert_rows(
                        account_value_historys_table,
                        [[history_id, model_uuid, final_account_alias_for_history, balance, available_balance, cross_wallet_balance, cross_un_pnl, current_time]],
                        ["id", "model_id", "account_alias", "balance", "available_balance", "cross_wallet_balance", "cross_un_pnl", "timestamp"]
                    )
                    logger.debug(f"[AccountValues] [插入account_value_historys表] 成功插入历史记录: model_id={model_id} (id={history_id}), "
                               f"account_alias={final_account_alias_for_history}, timestamp={current_time}")
                except Exception as history_err:
                    # 历史记录插入失败不影响主流程，但记录详细错误信息
                    logger.error(f"[AccountValues] [插入account_value_historys表] 插入历史记录失败: model_id={model_id}, "
                               f"model_uuid={model_uuid}, balance=${balance:.2f}, error={history_err}", exc_info=True)
                    # 不抛出异常，避免影响主流�?
            else:
                logger.warning(f"[AccountValues] [插入account_value_historys表] account_value_historys_table参数未提供，跳过历史记录插入: model_id={model_id}")
            
            # 记录方法执行完成
            logger.debug(f"[AccountValues] [记录账户价值完成] model_id={model_id}, "
                       f"account_values表操�?{'UPDATE' if existing_rows else 'INSERT'}, "
                       f"account_value_historys表操�?{'INSERT' if account_value_historys_table else 'SKIP'}")
        except Exception as e:
            logger.error(f"[AccountValues] [记录账户价值失败] model_id={model_id}, error={e}", exc_info=True)
            raise
    
    def get_latest_account_value(self, model_id: int,
                                model_id_mapping: Dict[int, str] = None) -> Optional[Dict]:
        """
        获取模型最新的账户价值记录（从account_values表）
        
        Args:
            model_id: 模型ID
            model_id_mapping: 可选的模型ID映射字典
        
        Returns:
            账户价值信息字典，如果不存在则返回None
            包含字段：balance, available_balance, cross_wallet_balance, cross_un_pnl, account_alias
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
                return None
            
            rows = self.query(f"""
                SELECT `account_alias`, `balance`, `available_balance`, 
                       `cross_wallet_balance`, `cross_un_pnl`, `timestamp`
                FROM `{self.account_values_table}`
                WHERE `model_id` = %s
                ORDER BY `timestamp` DESC
                LIMIT 1
            """, (model_uuid,))
            
            if not rows:
                return None
            
            columns = ["account_alias", "balance", "available_balance", 
                      "cross_wallet_balance", "cross_un_pnl", "timestamp"]
            result = self._row_to_dict(rows[0], columns)
            
            return {
                "account_alias": result["account_alias"] or '',
                "balance": float(result["balance"]) if result["balance"] is not None else 0.0,
                "available_balance": float(result["available_balance"]) if result["available_balance"] is not None else 0.0,
                "cross_wallet_balance": float(result["cross_wallet_balance"]) if result["cross_wallet_balance"] is not None else 0.0,
                "cross_un_pnl": float(result["cross_un_pnl"]) if result["cross_un_pnl"] is not None else 0.0
            }
        except Exception as e:
            logger.error(f"[AccountValues] Failed to get latest account value for model {model_id}: {e}")
            return None

