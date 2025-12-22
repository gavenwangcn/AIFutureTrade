"""
投资组合数据表操作模块 - portfolios 表

本模块提供投资组合数据的增删改查操作。

主要组件：
- PortfoliosDatabase: 投资组合数据操作类
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Callable
import pymysql
from .database_basic import create_pooled_db
import common.config as app_config
from .database_init import PORTFOLIOS_TABLE, FUTURES_TABLE

logger = logging.getLogger(__name__)


class PortfoliosDatabase:
    """
    投资组合数据操作类
    
    封装portfolios表的所有数据库操作。
    """
    
    def __init__(self, pool=None):
        """
        初始化投资组合数据库操作类
        
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
        
        self.portfolios_table = PORTFOLIOS_TABLE
        self.futures_table = FUTURES_TABLE
    
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
                            logger.debug(f"[Portfolios] Error rolling back transaction: {rollback_error}")
                        
                        # 对于所有错误，关闭连接，DBUtils会自动处理损坏的连接
                        try:
                            conn.close()
                        except Exception as close_error:
                            logger.debug(f"[Portfolios] Error closing connection: {close_error}")
                        finally:
                            # 确保连接引用被清除，即使关闭失败也要标记为已处理
                            conn = None
                    except Exception as close_error:
                        logger.error(f"[Portfolios] Critical error closing failed connection: {close_error}")
                        # 即使发生异常，也要清除连接引用
                        conn = None
                
                if attempt < max_retries - 1:
                    if not is_network_error:
                        raise
                    
                    is_deadlock = (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213) or 'deadlock' in error_msg.lower()
                    if is_deadlock:
                        wait_time = 1.0 * (1.5 ** attempt)
                        logger.warning(
                            f"[Portfolios] Deadlock error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    else:
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(
                            f"[Portfolios] Network error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    
                    import time
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"[Portfolios] Failed after {max_retries} attempts: "
                        f"{error_type}: {error_msg}"
                    )
                    raise
            finally:
                if connection_acquired and conn:
                    try:
                        logger.warning(
                            f"[Portfolios] Connection not closed in finally block, closing it"
                        )
                        try:
                            conn.rollback()
                            conn.close()
                        except Exception:
                            pass
                    except Exception as final_error:
                        logger.debug(f"[Portfolios] Error in finally block: {final_error}")
    
    def _generate_id(self) -> str:
        """Generate a unique ID (UUID)"""
        return str(uuid.uuid4())
    
    def _row_to_dict(self, row: tuple, columns: list) -> Dict:
        """Convert a row tuple to a dictionary"""
        return dict(zip(columns, row))
    
    def _rows_to_dicts(self, rows: List[tuple], columns: list) -> List[Dict]:
        """Convert rows to list of dictionaries"""
        return [self._row_to_dict(row, columns) for row in rows]
    
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
    
    def update_position(self, model_id: int, symbol: str, position_amt: float,
                       avg_price: float, leverage: int = 1, position_side: str = 'LONG',
                       initial_margin: float = 0.0, unrealized_profit: float = 0.0,
                       model_id_mapping: Dict[int, str] = None):
        """
        Update position
        
        Args:
            model_id: 模型ID
            symbol: 交易对符号（如BTCUSDT）
            position_amt: 持仓数量
            avg_price: 平均价格
            leverage: 杠杆倍数
            position_side: 持仓方向，'LONG'（多）或'SHORT'（空）
            initial_margin: 持仓所需起始保证金（基于最新标记价格）
            unrealized_profit: 持仓未实现盈亏
            model_id_mapping: 可选的模型ID映射字典
        """
        try:
            if model_id_mapping is None:
                # 如果没有提供映射，需要从数据库查询
                rows = self.query(f"SELECT id FROM models")
                model_id_mapping = {}
                for row in rows:
                    uuid_str = row[0]
                    int_id = abs(hash(uuid_str)) % (10 ** 9)
                    model_id_mapping[int_id] = uuid_str
            
            model_uuid = model_id_mapping.get(model_id)
            if not model_uuid:
                logger.warning(f"[Portfolios] Model {model_id} not found for position update")
                return
            
            # 规范化position_side
            position_side_upper = position_side.upper()
            if position_side_upper not in ['LONG', 'SHORT']:
                raise ValueError(f"position_side must be 'LONG' or 'SHORT', got: {position_side}")
            
            # MySQL 使用唯一索引 (uk_model_symbol_side) 和 INSERT 实现去重
            # 使用 UTC+8 时区时间（北京时间），转换为 naive datetime 存储
            beijing_tz = timezone(timedelta(hours=8))
            current_time = datetime.now(beijing_tz).replace(tzinfo=None)
            
            position_id = self._generate_id()
            self.insert_rows(
                self.portfolios_table,
                [[position_id, model_uuid, symbol.upper(), position_amt, avg_price, leverage, 
                  position_side_upper, initial_margin, unrealized_profit, current_time]],
                ["id", "model_id", "symbol", "position_amt", "avg_price", "leverage", 
                 "position_side", "initial_margin", "unrealized_profit", "updated_at"]
            )
        except Exception as e:
            logger.error(f"[Portfolios] Failed to update position: {e}")
            raise
    
    def get_portfolio(self, model_id: int, current_prices: Dict = None,
                     model_id_mapping: Dict[int, str] = None,
                     get_model_func: Callable[[int], Optional[Dict]] = None,
                     trades_table: str = None) -> Dict:
        """
        Get portfolio with positions and P&L
        
        Args:
            model_id: 模型ID
            current_prices: 当前价格字典
            model_id_mapping: 可选的模型ID映射字典
            get_model_func: 可选的获取模型信息的函数
            trades_table: 可选的交易表名
        
        Returns:
            投资组合信息字典
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
                logger.warning(f"[Portfolios] Model {model_id} not found in mapping, returning empty portfolio")
                return {
                    'model_id': model_id,
                    'initial_capital': 0,
                    'cash': 0,
                    'positions': [],
                    'positions_value': 0,
                    'margin_used': 0,
                    'total_value': 0,
                    'realized_pnl': 0,
                    'unrealized_pnl': 0
                }
            
            # 获取持仓
            rows = self.query(f"""
                SELECT * FROM {self.portfolios_table}
                WHERE model_id = '{model_uuid}' AND position_amt != 0
            """)
            columns = ["id", "model_id", "symbol", "position_amt", "avg_price", "leverage", 
                      "position_side", "initial_margin", "unrealized_profit", "updated_at"]
            positions = self._rows_to_dicts(rows, columns)
            
            # 获取初始资金
            if get_model_func:
                model = get_model_func(model_id)
            else:
                # 如果没有提供函数，从数据库查询
                from .database_models import ModelsDatabase
                models_db = ModelsDatabase(pool=self._pool)
                model = models_db.get_model(model_id)
            
            if not model:
                logger.warning(f"[Portfolios] Model {model_id} not found when getting model info, returning empty portfolio")
                return {
                    'model_id': model_id,
                    'initial_capital': 0,
                    'cash': 0,
                    'positions': [],
                    'positions_value': 0,
                    'margin_used': 0,
                    'total_value': 0,
                    'realized_pnl': 0,
                    'unrealized_pnl': 0
                }
            initial_capital = model['initial_capital']
            
            # 计算已实现盈亏（需要从trades表查询）
            if trades_table:
                pnl_rows = self.query(f"""
                    SELECT COALESCE(SUM(pnl), 0) as total_pnl 
                    FROM {trades_table}
                    WHERE model_id = '{model_uuid}'
                """)
                realized_pnl = float(pnl_rows[0][0]) if pnl_rows and pnl_rows[0][0] is not None else 0.0
            else:
                # 如果没有提供trades_table，从trades表查询
                from .database_init import TRADES_TABLE
                pnl_rows = self.query(f"""
                    SELECT COALESCE(SUM(pnl), 0) as total_pnl 
                    FROM {TRADES_TABLE}
                    WHERE model_id = '{model_uuid}'
                """)
                realized_pnl = float(pnl_rows[0][0]) if pnl_rows and pnl_rows[0][0] is not None else 0.0
            
            # 计算已用保证金（优先使用initial_margin字段，如果没有则使用传统计算方式）
            margin_used = sum([p.get('initial_margin', 0) or (abs(p['position_amt']) * p['avg_price'] / p['leverage']) for p in positions])
            
            # 计算未实现盈亏（优先使用unrealized_profit字段，如果没有则计算）
            unrealized_pnl = 0
            if current_prices:
                for pos in positions:
                    symbol = pos['symbol']
                    if symbol in current_prices:
                        current_price = current_prices[symbol]
                        entry_price = pos['avg_price']
                        position_amt = abs(pos['position_amt'])  # 使用绝对值
                        pos['current_price'] = current_price
                        
                        # 优先使用数据库中的unrealized_profit字段
                        if pos.get('unrealized_profit') is not None and pos['unrealized_profit'] != 0:
                            pos_pnl = pos['unrealized_profit']
                        else:
                            # 如果没有，则计算
                            if pos['position_side'] == 'LONG':
                                pos_pnl = (current_price - entry_price) * position_amt
                            else:  # SHORT
                                pos_pnl = (entry_price - current_price) * position_amt
                        
                        pos['pnl'] = pos_pnl
                        unrealized_pnl += pos_pnl
                    else:
                        pos['current_price'] = None
                        # 使用数据库中的unrealized_profit字段
                        pos['pnl'] = pos.get('unrealized_profit', 0)
                        unrealized_pnl += pos.get('unrealized_profit', 0)
            else:
                for pos in positions:
                    pos['current_price'] = None
                    # 使用数据库中的unrealized_profit字段
                    pos['pnl'] = pos.get('unrealized_profit', 0)
                    unrealized_pnl += pos.get('unrealized_profit', 0)
            
            cash = initial_capital + realized_pnl - margin_used
            positions_value = sum([abs(p['position_amt']) * p['avg_price'] for p in positions])
            total_value = initial_capital + realized_pnl + unrealized_pnl
            
            return {
                'model_id': model_id,
                'initial_capital': initial_capital,
                'cash': cash,
                'positions': positions,
                'positions_value': positions_value,
                'margin_used': margin_used,
                'total_value': total_value,
                'realized_pnl': realized_pnl,
                'unrealized_pnl': unrealized_pnl
            }
        except Exception as e:
            logger.error(f"[Portfolios] Failed to get portfolio for model {model_id}: {e}")
            raise
    
    def close_position(self, model_id: int, symbol: str, position_side: str = 'LONG',
                      model_id_mapping: Dict[int, str] = None):
        """
        Close position and clean up futures universe if unused
        
        Args:
            model_id: 模型ID
            symbol: 交易对符号（如BTCUSDT）
            position_side: 持仓方向，'LONG'（多）或'SHORT'（空）
            model_id_mapping: 可选的模型ID映射字典
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
                return
            
            normalized_symbol = symbol.upper()
            position_side_upper = position_side.upper()
            if position_side_upper not in ['LONG', 'SHORT']:
                raise ValueError(f"position_side must be 'LONG' or 'SHORT', got: {position_side}")
            
            # 使用 MySQL 的 DELETE FROM 语法
            delete_sql = f"DELETE FROM {self.portfolios_table} WHERE model_id = '{model_uuid}' AND symbol = '{normalized_symbol}' AND position_side = '{position_side_upper}'"
            logger.debug(f"[Portfolios] Executing SQL: {delete_sql}")
            self.command(delete_sql)
            
            # 检查是否还有其他持仓
            remaining_rows = self.query(f"""
                SELECT COUNT(*) as cnt FROM {self.portfolios_table}
                WHERE symbol = '{normalized_symbol}' AND position_amt != 0
            """)
            if remaining_rows and remaining_rows[0][0] == 0:
                # 删除 futures 表中的记录（使用 MySQL 的 DELETE FROM 语法）
                delete_futures_sql = f"DELETE FROM {self.futures_table} WHERE symbol = '{normalized_symbol}'"
                logger.debug(f"[Portfolios] Executing SQL: {delete_futures_sql}")
                self.command(delete_futures_sql)
        except Exception as e:
            logger.error(f"[Portfolios] Failed to close position: {e}")
            raise
    
    def get_model_held_symbols(self, model_id: int, model_id_mapping: Dict[int, str] = None) -> List[str]:
        """
        获取模型当前持仓的期货合约symbol列表（去重）
        
        从portfolios表中通过关联model_id获取当前有持仓的symbol（position_amt != 0），
        用于卖出服务获取市场状态。
        
        Args:
            model_id: 模型ID
            model_id_mapping: 可选的模型ID映射字典
        
        Returns:
            List[str]: 当前持仓的合约symbol列表（如 ['BTC', 'ETH']）
        """
        try:
            if model_id_mapping is None:
                from .database_models import ModelsDatabase
                models_db = ModelsDatabase(pool=self._pool)
                model_id_mapping = models_db._get_model_id_mapping()
            
            model_uuid = model_id_mapping.get(model_id)
            if not model_uuid:
                logger.warning(f"[Portfolios] Model {model_id} UUID not found")
                return []
            
            # 从portfolios表获取当前模型有持仓的去重symbol合约（position_amt != 0）
            # 使用参数化查询，避免SQL注入
            rows = self.query(f"""
                SELECT DISTINCT symbol
                FROM `{self.portfolios_table}`
                WHERE model_id = %s AND position_amt != 0
                ORDER BY symbol ASC
            """, (model_uuid,))
            
            symbols = [row[0] for row in rows] if rows else []
            return symbols
        except Exception as e:
            logger.error(f"[Portfolios] Failed to get model held symbols for model {model_id}: {e}")
            return []

