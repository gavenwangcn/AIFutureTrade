"""
期货合约配置数据表操作模�?- futures �?

本模块提供期货合约配置数据的增删改查操作�?

主要组件�?
- FuturesDatabase: 期货合约配置数据操作�?
"""

import logging
import uuid
from typing import Dict, List, Optional, Any, Callable
import pymysql
from .database_basic import create_pooled_db
import trade.common.config as app_config
from .database_init import FUTURES_TABLE, MODEL_FUTURES_TABLE, PORTFOLIOS_TABLE

logger = logging.getLogger(__name__)


class FuturesDatabase:
    """
    期货合约配置数据操作�?
    
    封装futures表的所有数据库操作�?
    """
    
    def __init__(self, pool=None):
        """
        初始化期货合约配置数据库操作�?
        
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
        
        self.futures_table = FUTURES_TABLE
        self.model_futures_table = MODEL_FUTURES_TABLE
        self.portfolios_table = PORTFOLIOS_TABLE
    
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
                            logger.debug(f"[Futures] Error rolling back transaction: {rollback_error}")
                        
                        # 对于所有错误，关闭连接，DBUtils会自动处理损坏的连接
                        try:
                            conn.close()
                        except Exception as close_error:
                            logger.debug(f"[Futures] Error closing connection: {close_error}")
                        finally:
                            # 确保连接引用被清除，即使关闭失败也要标记为已处理
                            conn = None
                    except Exception as close_error:
                        logger.error(f"[Futures] Critical error closing failed connection: {close_error}")
                        # 即使发生异常，也要清除连接引�?
                        conn = None
                
                if attempt < max_retries - 1:
                    if not is_network_error:
                        raise
                    
                    is_deadlock = (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213) or 'deadlock' in error_msg.lower()
                    if is_deadlock:
                        wait_time = 1.0 * (1.5 ** attempt)
                        logger.warning(
                            f"[Futures] Deadlock error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    else:
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(
                            f"[Futures] Network error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    
                    import time
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"[Futures] Failed after {max_retries} attempts: "
                        f"{error_type}: {error_msg}"
                    )
                    raise
            finally:
                if connection_acquired and conn:
                    try:
                        logger.warning(
                            f"[Futures] Connection not closed in finally block, closing it"
                        )
                        try:
                            conn.rollback()
                            conn.close()
                        except Exception:
                            pass
                    except Exception as final_error:
                        logger.debug(f"[Futures] Error in finally block: {final_error}")
    
    def _row_to_dict(self, row: tuple, columns: list) -> Dict:
        """Convert a row tuple to a dictionary"""
        return dict(zip(columns, row))
    
    def _rows_to_dicts(self, rows: List[tuple], columns: list) -> List[Dict]:
        """Convert rows to list of dictionaries"""
        return [self._row_to_dict(row, columns) for row in rows]
    
    def _generate_id(self) -> str:
        """Generate a unique ID (UUID)"""
        return str(uuid.uuid4())
    
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
    
    def get_future_configs(self) -> List[Dict]:
        """
        Get future configurations
        
        Returns:
            List[Dict]: 期货配置列表，每个元素包含symbol、contract_symbol、name、exchange、link、sort_order字段
        """
        try:
            rows = self.query(f"""
                SELECT symbol, contract_symbol, name, exchange, link, sort_order
                FROM {self.futures_table}
                ORDER BY sort_order DESC, symbol ASC
            """)
            columns = ["symbol", "contract_symbol", "name", "exchange", "link", "sort_order"]
            return self._rows_to_dicts(rows, columns)
        except Exception as e:
            logger.error(f"[Futures] Failed to get future configs: {e}")
            return []
    
    def sync_model_futures_from_portfolio(self, model_id: int) -> bool:
        """
        从portfolios表同步去重的future信息到model_future�?
        
        此方法会�?
        1. 从portfolios表获取当前模型所有交易过的去重future合约（包括已平仓的）
        2. 将这些合约信息同步到model_futures表（包括增、删对比操作�?
        3. 对于新增的合约，从全局futures表获取完整信�?
        4. 对于不再在portfolios表中出现的合约，从model_futures表移�?
        
        Args:
            model_id: 模型ID
        
        Returns:
            bool: 是否同步成功
        """
        try:
            logger.info(f"[Futures] Starting sync_model_futures_from_portfolio for model {model_id}")
            
            from .database_models import ModelsDatabase
            models_db = ModelsDatabase(pool=self._pool)
            model_mapping = models_db._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                logger.error(f"[Futures] Model {model_id} not found in mapping")
                return False
            
            # 1. 从portfolios表获取当前模型所有交易过的去重symbol合约（包括已平仓的）
            # 使用参数化查询，避免SQL注入
            rows = self.query(f"""
                SELECT DISTINCT symbol
                FROM `{self.portfolios_table}`
                WHERE model_id = %s
                ORDER BY symbol ASC
            """, (model_uuid,))
            
            portfolio_symbols = [row[0] for row in rows] if rows else []
            logger.info(f"[Futures] Found {len(portfolio_symbols)} distinct symbols in portfolios table for model {model_id}: {portfolio_symbols}")
            
            # 2. 获取当前model_futures表中的合约列�?
            rows = self.query(f"""
                SELECT id, model_id, symbol
                FROM `{self.model_futures_table}`
                WHERE model_id = %s
                ORDER BY symbol ASC
            """, (model_uuid,))
            
            current_model_futures = []
            for row in rows:
                current_model_futures.append({
                    'id': row[0],
                    'model_id': row[1],
                    'symbol': row[2]
                })
            current_symbols = {future['symbol']: future for future in current_model_futures}
            logger.info(f"[Futures] Found {len(current_symbols)} symbols in model_futures table for model {model_id}: {list(current_symbols.keys())}")
            
            # 3. 确定需要添加和删除的合约（对比操作�?
            symbols_to_add = set(portfolio_symbols) - set(current_symbols.keys())
            symbols_to_delete = set(current_symbols.keys()) - set(portfolio_symbols)
            
            logger.info(f"[Futures] Sync comparison for model {model_id}: "
                       f"to_add={len(symbols_to_add)} {list(symbols_to_add)}, "
                       f"to_delete={len(symbols_to_delete)} {list(symbols_to_delete)}")
            
            # 4. 添加新合约到model_futures�?
            if symbols_to_add:
                logger.info(f"[Futures] Adding {len(symbols_to_add)} new futures to model_futures table for model {model_id}")
                
                # 从全局futures表获取合约的完整信息
                # 使用参数化查询，处理单个和多个元素的情况
                symbols_list = list(symbols_to_add)
                if len(symbols_list) == 1:
                    # 单个元素时使�?= 而不�?IN
                    futures_info = self.query(f"""
                        SELECT symbol, contract_symbol, name, exchange, link
                        FROM `{self.futures_table}`
                        WHERE symbol = %s
                    """, (symbols_list[0],))
                else:
                    # 多个元素时使�?IN，使用参数化查询
                    placeholders = ', '.join(['%s'] * len(symbols_list))
                    futures_info = self.query(f"""
                        SELECT symbol, contract_symbol, name, exchange, link
                        FROM `{self.futures_table}`
                        WHERE symbol IN ({placeholders})
                    """, tuple(symbols_list))
                
                # 构建futures字典
                futures_dict = {}
                for row in futures_info:
                    futures_dict[row[0]] = {
                        'symbol': row[0],
                        'contract_symbol': row[1] or row[0],
                        'name': row[2] or row[0],
                        'exchange': row[3] or 'BINANCE_FUTURES',
                        'link': row[4] or ''
                    }
                
                # 为每个需要添加的合约生成记录
                added_count = 0
                for symbol in symbols_to_add:
                    # 如果全局表中没有该合约信息，创建默认信息
                    if symbol not in futures_dict:
                        futures_dict[symbol] = {
                            'symbol': symbol,
                            'contract_symbol': symbol,
                            'name': symbol,
                            'exchange': 'BINANCE_FUTURES',
                            'link': ''
                        }
                        logger.warning(f"[Futures] Future {symbol} not found in global futures table, using default values")
                    
                    # 生成唯一ID
                    future_id = self._generate_id()
                    
                    # 插入到model_futures�?
                    try:
                        self.insert_rows(
                            self.model_futures_table,
                            [[future_id, model_uuid, futures_dict[symbol]['symbol'], 
                              futures_dict[symbol]['contract_symbol'], futures_dict[symbol]['name'],
                              futures_dict[symbol]['exchange'], futures_dict[symbol]['link'], 0]],
                            ["id", "model_id", "symbol", "contract_symbol", "name", "exchange", "link", "sort_order"]
                        )
                        added_count += 1
                        logger.debug(f"[Futures] Added future {symbol} to model {model_id} in model_futures table")
                    except Exception as insert_error:
                        logger.error(f"[Futures] Failed to insert future {symbol} for model {model_id}: {insert_error}")
                        # 继续处理其他合约，不中断整个流程
                        continue
                
                logger.info(f"[Futures] Successfully added {added_count}/{len(symbols_to_add)} futures to model_futures table for model {model_id}")
            else:
                logger.info(f"[Futures] No new futures to add for model {model_id}")
            
            # 5. 从model_futures表删除不再在portfolios表中出现的合�?
            if symbols_to_delete:
                logger.info(f"[Futures] Deleting {len(symbols_to_delete)} futures from model_futures table for model {model_id}")
                
                # 使用参数化查询删�?
                for symbol in symbols_to_delete:
                    try:
                        self.command(f"""
                            DELETE FROM `{self.model_futures_table}`
                            WHERE model_id = %s AND symbol = %s
                        """, (model_uuid, symbol))
                        logger.debug(f"[Futures] Deleted future {symbol} from model {model_id} in model_futures table")
                    except Exception as delete_error:
                        logger.error(f"[Futures] Failed to delete future {symbol} for model {model_id}: {delete_error}")
                        # 继续处理其他合约，不中断整个流程
                        continue
                
                logger.info(f"[Futures] Successfully deleted {len(symbols_to_delete)} futures from model_futures table for model {model_id}")
            else:
                logger.info(f"[Futures] No futures to delete for model {model_id}")
            
            logger.info(f"[Futures] Successfully synced model_futures for model {model_id}: "
                        f"added {len(symbols_to_add)}, deleted {len(symbols_to_delete)}")
            return True
            
        except Exception as e:
            logger.error(f"[Futures] Failed to sync model_futures from portfolio for model {model_id}: {e}")
            import traceback
            logger.error(f"[Futures] Error stack: {traceback.format_exc()}")
            return False

