"""
基础数据库操作模块 - MySQL实现

本模块提供Database类，封装所有业务数据的MySQL数据库操作，包括：
1. 提供商管理：LLM提供商的增删改查
2. 模型管理：交易模型的增删改查、配置管理
3. 投资组合管理：持仓、账户价值记录
4. 交易记录：交易历史的记录和查询
5. 对话记录：AI对话历史的记录和查询
6. 合约配置：期货合约配置管理
7. 账户资产：账户资产信息管理
8. 提示词管理：模型买卖提示词配置

主要组件：
- Database: 基础数据库操作封装类

使用场景：
- 后端API：为所有业务API提供数据访问
- 交易引擎：trading_engine模块使用Database管理模型、持仓、交易记录
- 前端展示：通过后端API间接使用Database查询数据

注意：
- 使用MySQL连接池管理数据库连接
- 所有表结构在init_db()中自动创建
- UUID和整数ID之间的转换用于兼容性
"""
import json
import logging
import time
import uuid
import common.config as app_config
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any, Callable, Tuple
from .database_init import (
    init_database_tables, 
    PROVIDERS_TABLE, MODELS_TABLE, PORTFOLIOS_TABLE, TRADES_TABLE,
    CONVERSATIONS_TABLE, ACCOUNT_VALUES_TABLE, ACCOUNT_VALUE_HISTORYS_TABLE,
    SETTINGS_TABLE, MODEL_PROMPTS_TABLE, MODEL_FUTURES_TABLE, FUTURES_TABLE,
    ACCOUNT_ASSET_TABLE, ASSET_TABLE, BINANCE_TRADE_LOGS_TABLE, LLM_API_ERROR_TABLE,
    STRATEGYS_TABLE, MODEL_STRATEGY_TABLE
)
import pymysql
from pymysql import cursors
from DBUtils.PooledDB import PooledDB

logger = logging.getLogger(__name__)


def create_pooled_db(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    charset: str = 'utf8mb4',
    mincached: int = 5,
    maxconnections: int = 50,
    blocking: bool = True
) -> PooledDB:
    """
    创建DBUtils连接池
    
    Args:
        host: MySQL host
        port: MySQL port
        user: MySQL username
        password: MySQL password
        database: MySQL database name
        charset: Character set, default utf8mb4
        mincached: Minimum number of cached connections
        maxconnections: Maximum number of connections allowed
        blocking: Whether to block when pool is exhausted
        
    Returns:
        DBUtils PooledDB instance
    """
    def _create_connection():
        """创建单个连接的工厂函数"""
        return pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset=charset,
            cursorclass=cursors.DictCursor,
            autocommit=False
        )
    
    return PooledDB(
        creator=_create_connection,
        mincached=mincached,
        maxconnections=maxconnections,
        maxshared=maxconnections,  # 最大共享连接数
        maxcached=maxconnections,  # 最大缓存连接数
        blocking=blocking,
        maxusage=None,  # 每个连接的最大使用次数，None表示无限制
        setsession=None,  # 设置会话的SQL语句列表
        reset=True,  # 连接归还时重置
        failures=None,  # 失败重试次数
        ping=1,  # 在获取连接时ping数据库（1=每次获取时ping）
    )


class Database:
    """
    基础数据库操作封装类
    
    封装所有业务数据的MySQL数据库操作，包括提供商、模型、投资组合、交易记录等。
    使用连接池管理数据库连接，支持高并发访问。
    
    主要功能：
    - 提供商管理：LLM提供商的查询（增删改已迁移到Java后端）
    - 模型管理：交易模型的查询和配置（增删改已迁移到Java后端）
    - 投资组合管理：持仓更新、账户价值记录、投资组合查询
    - 交易记录：交易历史的记录和查询
    - 对话记录：AI对话历史的记录和查询
    - 合约配置：期货合约配置查询（增删改已迁移到Java后端）
    - 账户资产：账户资产信息查询（增删改已迁移到Java后端）
    - 提示词管理：模型买卖提示词配置
    
    使用示例：
        db = Database()
        db.init_db()  # 初始化所有表
        from common.database.database_models import ModelsDatabase
        from common.database.database_portfolios import PortfoliosDatabase
        models_db = ModelsDatabase(pool=db._pool)
        portfolios_db = PortfoliosDatabase(pool=db._pool)
        model = models_db.get_model(model_id)
        portfolio = portfolios_db.get_portfolio(model_id, current_prices, ...)
        db.add_trade(model_id, symbol, signal, quantity, price)
        db.close()  # 显式关闭连接池，释放资源
    
    注意：
        - 已从ClickHouse迁移到MySQL，保持方法签名和返回值格式兼容
    """
    
    def __init__(self):
        """
        初始化数据库连接
        
        Note:
            - 创建MySQL连接池（最小5个连接，最大50个连接）
            - 定义所有业务表的表名
            - 不自动初始化表结构，需要调用init_db()方法
            - 使用配置文件中的MySQL连接信息
        """
        # 使用 DBUtils 连接池
        self._pool = create_pooled_db(
            host=app_config.MYSQL_HOST,
            port=app_config.MYSQL_PORT,
            user=app_config.MYSQL_USER,
            password=app_config.MYSQL_PASSWORD,
            database=app_config.MYSQL_DATABASE,
            charset='utf8mb4',
            mincached=15,
            maxconnections=100,
            blocking=True
        )
        
        # 表名定义（从 database_init.py 导入常量）
        self.providers_table = PROVIDERS_TABLE
        self.models_table = MODELS_TABLE
        self.portfolios_table = PORTFOLIOS_TABLE
        self.trades_table = TRADES_TABLE
        self.conversations_table = CONVERSATIONS_TABLE
        self.account_values_table = ACCOUNT_VALUES_TABLE
        self.account_value_historys_table = ACCOUNT_VALUE_HISTORYS_TABLE
        self.settings_table = SETTINGS_TABLE
        self.model_prompts_table = MODEL_PROMPTS_TABLE
        self.model_futures_table = MODEL_FUTURES_TABLE
        self.futures_table = FUTURES_TABLE
        self.account_asset_table = ACCOUNT_ASSET_TABLE
        self.asset_table = ASSET_TABLE
        self.binance_trade_logs_table = BINANCE_TRADE_LOGS_TABLE
        self.llm_api_error_table = LLM_API_ERROR_TABLE
        self.strategys_table = STRATEGYS_TABLE
        self.model_strategy_table = MODEL_STRATEGY_TABLE
    
    def close(self) -> None:
        """
        关闭数据库连接池，释放所有资源
        
        调用此方法将关闭连接池中的所有活跃连接，确保资源被正确释放。
        在不再需要数据库连接时，应显式调用此方法。
        """
        if hasattr(self, '_pool') and self._pool:
            try:
                # DBUtils连接池会自动管理连接，这里只需要关闭连接池
                # 注意：DBUtils的PooledDB没有close_all方法，连接会在对象销毁时自动关闭
                # 但我们可以通过删除引用来触发清理
                self._pool = None
                logger.info("[Database] Connection pool closed successfully")
            except Exception as e:
                logger.warning(f"[Database] Error closing connection pool: {e}")
    
    def __del__(self) -> None:
        """
        析构方法，确保连接池资源被释放
        
        当Database实例被垃圾回收时，会自动调用此方法关闭连接池。
        为了确保资源被及时释放，建议显式调用close()方法。
        """
        self.close()
    
    def _with_connection(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function with a MySQL connection from the pool.
        
        支持自动重试机制，当遇到网络错误时会自动重试（最多3次）。
        
        Args:
            func: 要执行的函数
            *args: 传递给函数的位置参数
            **kwargs: 传递给函数的关键字参数
        
        Returns:
            函数执行结果
        
        Raises:
            Exception: 如果重试3次后仍然失败，抛出最后一个异常
        """
        max_retries = 3
        retry_delay = 0.5  # 初始重试延迟（秒）
        
        for attempt in range(max_retries):
            conn = None
            connection_acquired = False
            try:
                # 使用DBUtils连接池获取连接
                conn = self._pool.connection()
                if not conn:
                    raise Exception("Failed to acquire MySQL connection")
                connection_acquired = True
                
                # 执行函数
                result = func(conn, *args, **kwargs)
                
                # 成功执行，提交事务
                conn.commit()
                # DBUtils会自动管理连接，使用完毕后会自动归还，不需要手动release
                conn = None  # 标记已处理，避免 finally 中重复处理
                return result
                
            except Exception as e:
                # 记录错误信息
                error_type = type(e).__name__
                error_msg = str(e)
                
                # 判断是否为网络/协议错误或死锁错误，需要重试
                # 包括 "Packet sequence number wrong" 错误，这通常表示连接状态不一致
                # 包括 MySQL 死锁错误 (1213)，这是一种需要重试的资源竞争错误
                # 包括 "read of closed file" 错误，这通常表示底层连接已关闭
                is_network_error = any(keyword in error_msg.lower() for keyword in [
                    'connection', 'broken', 'lost', 'timeout', 'reset', 'gone away',
                    'operationalerror', 'interfaceerror', 'packet sequence', 'internalerror',
                    'deadlock found', 'read of closed file'
                ]) or any(keyword in error_type.lower() for keyword in [
                    'connection', 'timeout', 'operationalerror', 'interfaceerror', 'internalerror',
                    'valueerror'
                ]) or (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213)
                
                # 如果已获取连接，需要处理连接（关闭）
                if connection_acquired and conn:
                    try:
                        # 回滚事务
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                        
                        # 对于所有错误，关闭连接，DBUtils会自动处理损坏的连接
                        try:
                            conn.close()
                        except Exception:
                            pass
                        conn = None  # 标记已处理，避免 finally 中重复处理
                    except Exception as close_error:
                        logger.debug(f"[Database] Error closing failed connection: {close_error}")
                        conn = None  # 标记已处理
                
                # 判断是否需要重试
                if attempt < max_retries - 1:
                    # 只有网络错误才重试
                    if not is_network_error:
                        # 非网络错误不重试，直接抛出
                        raise
                    
                    # 计算等待时间
                    # 为死锁错误使用特殊的重试策略（更长的初始延迟和更慢的增长）
                    is_deadlock = (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213) or 'deadlock' in error_msg.lower()
                    if is_deadlock:
                        # 死锁错误：初始延迟1秒，增长因子1.5（更慢的增长）
                        wait_time = 1.0 * (1.5 ** attempt)
                        logger.warning(
                            f"[Database] Deadlock error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    else:
                        # 其他网络错误使用指数退避策略
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(
                            f"[Database] Network error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    
                    # 等待后重试
                    time.sleep(wait_time)
                    continue
                else:
                    # 已达到最大重试次数，抛出异常
                    logger.error(
                        f"[Database] Failed after {max_retries} attempts: "
                        f"{error_type}: {error_msg}"
                    )
                    raise
            finally:
                # 确保连接被正确处理（双重保险）
                if connection_acquired and conn:
                    try:
                        # 如果连接还没有被处理，尝试关闭它
                        logger.warning(
                            f"[Database] Connection not closed in finally block, closing it"
                        )
                        try:
                            conn.rollback()
                            conn.close()
                        except Exception:
                            pass
                        # DBUtils会自动处理连接，不需要手动管理连接计数
                    except Exception as final_error:
                        logger.debug(f"[Database] Error in finally block: {final_error}")
    
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
    
    def query(self, sql: str, params: tuple = None, as_dict: bool = False) -> List:
        """Execute a query and return results.
        
        注意：MySQL 支持参数化查询，使用 %s 作为占位符。
        
        Args:
            sql: SQL查询语句
            params: 查询参数元组
            as_dict: 是否返回字典格式（默认False，返回元组列表以保持兼容性）
        
        Returns:
            List: 查询结果列表，如果as_dict=True则返回字典列表，否则返回元组列表
        """
        def _execute_query(conn):
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
                # 如果使用字典游标，直接返回字典列表
                if as_dict:
                    return [dict(row) for row in rows] if rows else []
                # 否则转换为元组列表以保持兼容性
                if rows and isinstance(rows[0], dict):
                    return [tuple(row.values()) for row in rows]
                return rows
            finally:
                cursor.close()
        return self._with_connection(_execute_query)
    
    def insert_rows(self, table: str, rows: List[List[Any]], column_names: List[str]) -> None:
        """Insert rows into a table."""
        if not rows:
            return
        
        def _execute_insert(conn):
            cursor = conn.cursor()
            try:
                # 构建INSERT语句
                columns_str = ', '.join([f"`{col}`" for col in column_names])
                placeholders = ', '.join(['%s'] * len(column_names))
                sql = f"INSERT INTO `{table}` ({columns_str}) VALUES ({placeholders})"
                
                # 批量插入
                cursor.executemany(sql, rows)
            finally:
                cursor.close()
        
        self._with_connection(_execute_insert)
    
    # ============ 初始化方法 ============
    
    def init_db(self):
        """Initialize database tables - only CREATE TABLE IF NOT EXISTS, no migration logic"""
        logger.info("[Database] Initializing MySQL tables...")
        
        # 使用统一的表初始化模块
        table_names = {
            'providers_table': self.providers_table,
            'models_table': self.models_table,
            'portfolios_table': self.portfolios_table,
            'trades_table': self.trades_table,
            'conversations_table': self.conversations_table,
            'account_values_table': self.account_values_table,
            'account_value_historys_table': self.account_value_historys_table,
            'settings_table': self.settings_table,
            'model_prompts_table': self.model_prompts_table,
            'model_futures_table': self.model_futures_table,
            'futures_table': self.futures_table,
            'account_asset_table': self.account_asset_table,
            'asset_table': self.asset_table,
            'binance_trade_logs_table': self.binance_trade_logs_table,
            'llm_api_error_table': self.llm_api_error_table,
            'strategy_table': self.strategys_table,
            'model_strategy_table': self.model_strategy_table,
        }
        init_database_tables(self.command, table_names)
        
        # Insert default settings if no settings exist
        self._init_default_settings()
        
        logger.info("[Database] MySQL tables initialized")
    
    # 表初始化方法已移至 common/database/database_init.py
    
    @staticmethod
    def _format_timestamp_to_string(timestamp) -> Optional[str]:
        """
        将timestamp转换为ISO格式字符串（UTC+8时区）
        
        Args:
            timestamp: datetime对象或字符串
            
        Returns:
            ISO格式字符串（如 '2024-01-01T12:00:00+08:00'），如果timestamp为None则返回None
        """
        if not timestamp:
            return None
        
        if isinstance(timestamp, datetime):
            # 如果已经是UTC+8时区，直接格式化；否则转换为UTC+8
            if timestamp.tzinfo is None:
                # 如果数据库返回的是naive datetime，假设是UTC+8时间
                beijing_tz = timezone(timedelta(hours=8))
                timestamp = timestamp.replace(tzinfo=beijing_tz)
            elif timestamp.tzinfo != timezone(timedelta(hours=8)):
                # 转换为UTC+8时区
                beijing_tz = timezone(timedelta(hours=8))
                timestamp = timestamp.astimezone(beijing_tz)
            # 格式化为ISO格式字符串（包含时区信息）
            timestamp_str = timestamp.strftime('%Y-%m-%dT%H:%M:%S%z')
            # 格式化时区偏移量为 +08:00 格式
            if timestamp_str.endswith('+0800'):
                timestamp_str = timestamp_str[:-5] + '+08:00'
            elif timestamp_str.endswith('-0800'):
                timestamp_str = timestamp_str[:-5] + '-08:00'
            return timestamp_str
        else:
            # 如果已经是字符串，直接返回
            return str(timestamp)
    
    # 表初始化方法已移至 common/database/database_init.py
    
    def _init_default_settings(self):
        """Initialize default settings if none exist"""
        try:
            # 检查是否有设置记录
            result = self.query(f"SELECT COUNT(*) as cnt FROM `{self.settings_table}`")
            if result and result[0][0] == 0:
                # 使用 UTC+8 时区时间（北京时间），转换为 naive datetime 存储
                beijing_tz = timezone(timedelta(hours=8))
                current_time = datetime.now(beijing_tz).replace(tzinfo=None)
                
                # 插入默认设置
                settings_id = str(uuid.uuid4())
                self.insert_rows(
                    self.settings_table,
                    [[settings_id, 5, 5, 0.002, 0, 5, current_time, current_time]],
                    ["id", "buy_frequency_minutes", "sell_frequency_minutes", "trading_fee_rate", "show_system_prompt", "conversation_limit", "created_at", "updated_at"]
                )
                logger.info("[Database] Default settings initialized")
        except Exception as e:
            logger.warning(f"[Database] Failed to initialize default settings: {e}")
    
    def _generate_id(self) -> str:
        """Generate a unique ID (UUID)"""
        return str(uuid.uuid4())
    
    def _uuid_to_int(self, uuid_str: str) -> int:
        """Convert UUID string to int ID for compatibility"""
        # 使用 UUID 的前 8 个字符的 hash 来生成稳定的 int ID
        return abs(hash(uuid_str)) % (10 ** 9)
    
    def _int_to_uuid(self, int_id: int, table: str) -> Optional[str]:
        """Find UUID string by int ID (for compatibility)"""
        try:
            rows = self.query(f"SELECT id FROM {table}")
            for row in rows:
                uuid_str = row[0]
                if self._uuid_to_int(uuid_str) == int_id:
                    return uuid_str
            return None
        except Exception as e:
            logger.error(f"[Database] Failed to find UUID for int ID {int_id} in table {table}: {e}")
            return None
    
    def _row_to_dict(self, row: Tuple, columns: List[str]) -> Dict:
        """Convert a row tuple to a dictionary"""
        return dict(zip(columns, row))
    
    def _rows_to_dicts(self, rows: List[Tuple], columns: List[str]) -> List[Dict]:
        """Convert rows to list of dictionaries"""
        return [self._row_to_dict(row, columns) for row in rows]
    
    # ============ Provider（提供商）管理方法 ============
    
    def get_provider(self, provider_id: int) -> Optional[Dict]:
        """Get provider information
        
        注意：provider_id 参数类型为 int（兼容性），但实际查询时需要使用 String
        这里需要先查找匹配的 provider
        """
        try:
            # 由于原接口使用 int ID，我们需要查找所有 providers 并匹配
            # 这是一个兼容性处理，实际应该使用 UUID
            rows = self.query(f"SELECT * FROM {self.providers_table} ORDER BY created_at DESC")
            columns = ["id", "name", "api_url", "api_key", "models", "provider_type", "created_at"]
            
            for row in rows:
                row_dict = self._row_to_dict(row, columns)
                # 检查 hash 是否匹配
                if self._uuid_to_int(row_dict['id']) == provider_id:
                    # 转换 ID 为 int 以保持兼容性
                    row_dict['id'] = provider_id
                    return row_dict
            return None
        except Exception as e:
            logger.error(f"[Database] Failed to get provider {provider_id}: {e}")
            return None
    
    # ============ Model（模型）管理方法 ============
    
    # 所有模型相关方法已迁移到 common.database.database_models.ModelsDatabase
    # 请直接使用 ModelsDatabase 类的方法：
    # - _get_model_id_mapping()
    # - _get_provider_id_mapping()
    # - get_model(model_id)
    # - get_all_models()
    # - is_model_auto_buy_enabled(model_id)
    # - is_model_auto_sell_enabled(model_id)
    # - set_model_auto_buy_enabled(model_id, enabled)
    # - set_model_auto_sell_enabled(model_id, enabled)
    # - set_model_leverage(model_id, leverage)
    # - set_model_batch_config(model_id, ...)
    # - set_model_max_positions(model_id, max_positions)
    # - set_model_provider_and_model_name(model_id, provider_id, model_name)
    
    # ============ Portfolio（投资组合）管理方法 ============
    
    # 所有投资组合相关方法已迁移到 common.database.database_portfolios.PortfoliosDatabase
    # 请直接使用 PortfoliosDatabase 类的方法：
    # - update_position(model_id, symbol, position_amt, avg_price, leverage, position_side, initial_margin, unrealized_profit, model_id_mapping)
    # - get_portfolio(model_id, current_prices, model_id_mapping, get_model_func, trades_table)
    # - close_position(model_id, symbol, position_side, model_id_mapping)
    
    # ============ Trade（交易记录）管理方法 ============
    
    def add_trade(self, model_id: int, future: str, signal: str, quantity: float,
              price: float, leverage: int = 1, side: str = 'long', pnl: float = 0, fee: float = 0):
        """
        Add trade record with fee
        
        注意：此方法已迁移到 common.database.database_trades.TradesDatabase
        保留此方法仅用于向后兼容。
        """
        try:
            from .database_trades import TradesDatabase
            from .database_models import ModelsDatabase
            trades_db = TradesDatabase(pool=self._pool)
            models_db = ModelsDatabase(pool=self._pool)
            model_mapping = models_db._get_model_id_mapping()
            trades_db.add_trade(model_id, future, signal, quantity, price, leverage, side, pnl, fee, model_mapping)
        except Exception as e:
            logger.error(f"[Database] Failed to add trade: {e}")
            raise
    
    # ============ Conversation（对话记录）管理方法 ============
    
    def add_conversation(self, model_id: int, user_prompt: str,
                        ai_response: str, cot_trace: str = '', tokens: int = 0, 
                        conversation_type: Optional[str] = None) -> Optional[str]:
        """
        Add conversation record
        
        注意：此方法已迁移到 common.database.database_conversations.ConversationsDatabase
        保留此方法仅用于向后兼容。
        """
        try:
            from .database_conversations import ConversationsDatabase
            from .database_models import ModelsDatabase
            conversations_db = ConversationsDatabase(pool=self._pool)
            models_db = ModelsDatabase(pool=self._pool)
            model_mapping = models_db._get_model_id_mapping()
            return conversations_db.add_conversation(model_id, user_prompt, ai_response, cot_trace, 
                                                  tokens, conversation_type, model_mapping)
        except Exception as e:
            logger.error(f"[Database] Failed to add conversation: {e}")
            raise
    
    def add_binance_trade_log(self, model_id: Optional[str] = None, conversation_id: Optional[str] = None, 
                              trade_id: Optional[str] = None, type: str = "test", method_name: str = "",
                              param: Optional[Dict[str, Any]] = None, response_context: Optional[Dict[str, Any]] = None,
                              response_type: Optional[str] = None, error_context: Optional[str] = None):
        """
        添加币安交易日志记录
        
        注意：此方法已迁移到 common.database.database_binance_trade_logs.BinanceTradeLogsDatabase
        保留此方法仅用于向后兼容。
        """
        try:
            from .database_binance_trade_logs import BinanceTradeLogsDatabase
            binance_trade_logs_db = BinanceTradeLogsDatabase(pool=self._pool)
            binance_trade_logs_db.add_binance_trade_log(model_id, conversation_id, trade_id, type, 
                                                       method_name, param, response_context, response_type, error_context)
        except Exception as e:
            logger.error(f"[Database] Failed to add binance trade log: {e}")
            # 不抛出异常，避免影响主流程
    
    def record_llm_api_error(self, model_id: int, provider_name: str, model: str, error_msg: str):
        """
        记录LLM API调用错误
        
        注意：此方法已迁移到 common.database.database_conversations.ConversationsDatabase
        保留此方法仅用于向后兼容。
        """
        try:
            from .database_conversations import ConversationsDatabase
            from .database_models import ModelsDatabase
            conversations_db = ConversationsDatabase(pool=self._pool)
            models_db = ModelsDatabase(pool=self._pool)
            model_mapping = models_db._get_model_id_mapping()
            conversations_db.record_llm_api_error(model_id, provider_name, model, error_msg, model_mapping)
        except Exception as e:
            logger.error(f"[Database] Failed to record LLM API error: {e}")
            # 不抛出异常，避免影响主流程
    
    # ============ Account Value（账户价值）管理方法 ============
    
    def record_account_value(self, model_id: int, balance: float,
                            available_balance: float, cross_wallet_balance: float,
                            account_alias: str = '', cross_un_pnl: float = 0.0):
        """
        Record account value snapshot
        
        注意：此方法已迁移到 common.database.database_account_values.AccountValuesDatabase
        保留此方法仅用于向后兼容。
        """
        try:
            from .database_account_values import AccountValuesDatabase
            account_values_db = AccountValuesDatabase(pool=self._pool)
            from .database_models import ModelsDatabase
            models_db = ModelsDatabase(pool=self._pool)
            model_mapping = models_db._get_model_id_mapping()
            from .database_init import ACCOUNT_VALUE_HISTORYS_TABLE
            account_values_db.record_account_value(model_id, balance, available_balance, cross_wallet_balance,
                                                  account_alias, cross_un_pnl, model_mapping, 
                                                  models_db.get_model, ACCOUNT_VALUE_HISTORYS_TABLE)
        except Exception as e:
            logger.error(f"[Database] Failed to record account value: {e}")
            raise
    
    def get_account_value_history(self, model_id: int, limit: int = 100) -> List[Dict]:
        """
        Get account value history for a specific model
        
        注意：此方法已迁移到 common.database.database_account_value_historys.AccountValueHistorysDatabase
        保留此方法仅用于向后兼容。
        """
        try:
            from .database_account_value_historys import AccountValueHistorysDatabase
            from .database_models import ModelsDatabase
            account_value_historys_db = AccountValueHistorysDatabase(pool=self._pool)
            models_db = ModelsDatabase(pool=self._pool)
            model_mapping = models_db._get_model_id_mapping()
            return account_value_historys_db.get_account_value_history(model_id, limit, model_mapping)
        except Exception as e:
            logger.error(f"[Database] Failed to get account value history for model {model_id}: {e}")
            return []

    # ============ Futures（合约配置）管理方法 ============
    
    # add_future, delete_future, get_futures, upsert_future 方法已迁移到Java后端，不再需要
    
    def get_future_configs(self) -> List[Dict]:
        """Get future configurations"""
        try:
            rows = self.query(f"""
                SELECT symbol, contract_symbol, name, exchange, link, sort_order
                FROM {self.futures_table}
                ORDER BY sort_order DESC, symbol ASC
            """)
            columns = ["symbol", "contract_symbol", "name", "exchange", "link", "sort_order"]
            return self._rows_to_dicts(rows, columns)
        except Exception as e:
            logger.error(f"[Database] Failed to get future configs: {e}")
            return []
    
    # ============ Model Futures（模型合约关联）管理方法 ============
    
    # add_model_future 和 delete_model_future 方法已迁移到Java后端，不再需要
    
    def get_model_held_symbols(self, model_id: int) -> List[str]:
        """
        获取模型当前持仓的期货合约symbol列表（去重）
        
        从portfolios表中通过关联model_id获取当前有持仓的symbol（position_amt != 0），
        用于卖出服务获取市场状态。
        
        Args:
            model_id: 模型ID
            
        Returns:
            List[str]: 当前持仓的合约symbol列表（如 ['BTC', 'ETH']）
        """
        try:
            from .database_models import ModelsDatabase
            models_db = ModelsDatabase(pool=self._pool)
            model_mapping = models_db._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                logger.warning(f"[Database] Model {model_id} UUID not found")
                return []
            
            # 从portfolios表获取当前模型有持仓的去重symbol合约（position_amt != 0）
            rows = self.query(f"""
                SELECT DISTINCT symbol
                FROM `{self.portfolios_table}`
                WHERE model_id = '{model_uuid}' AND position_amt != 0
                ORDER BY symbol ASC
            """)
            
            symbols = [row[0] for row in rows] if rows else []
            return symbols
        except Exception as e:
            logger.error(f"[Database] Failed to get model held symbols for model {model_id}: {e}")
            return []
    
    def sync_model_futures_from_portfolio(self, model_id: int) -> bool:
        """
        从portfolios表同步去重的future信息到model_future表
        
        此方法会：
        1. 从portfolios表获取当前模型所有交易过的去重future合约（包括已平仓的）
        2. 将这些合约信息同步到model_futures表（包括增、删对比操作）
        3. 对于新增的合约，从全局futures表获取完整信息
        4. 对于不再在portfolios表中出现的合约，从model_futures表移除
        
        Args:
            model_id: 模型ID
        
        Returns:
            bool: 是否同步成功
        """
        try:
            logger.info(f"[Database] Starting sync_model_futures_from_portfolio for model {model_id}")
            
            from .database_models import ModelsDatabase
            models_db = ModelsDatabase(pool=self._pool)
            model_mapping = models_db._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                logger.error(f"[Database] Model {model_id} not found in mapping")
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
            logger.info(f"[Database] Found {len(portfolio_symbols)} distinct symbols in portfolios table for model {model_id}: {portfolio_symbols}")
            
            # 2. 获取当前model_futures表中的合约列表
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
            logger.info(f"[Database] Found {len(current_symbols)} symbols in model_futures table for model {model_id}: {list(current_symbols.keys())}")
            
            # 3. 确定需要添加和删除的合约（对比操作）
            symbols_to_add = set(portfolio_symbols) - set(current_symbols.keys())
            symbols_to_delete = set(current_symbols.keys()) - set(portfolio_symbols)
            
            logger.info(f"[Database] Sync comparison for model {model_id}: "
                       f"to_add={len(symbols_to_add)} {list(symbols_to_add)}, "
                       f"to_delete={len(symbols_to_delete)} {list(symbols_to_delete)}")
            
            # 4. 添加新合约到model_futures表
            if symbols_to_add:
                logger.info(f"[Database] Adding {len(symbols_to_add)} new futures to model_futures table for model {model_id}")
                
                # 从全局futures表获取合约的完整信息
                # 使用参数化查询，处理单个和多个元素的情况
                symbols_list = list(symbols_to_add)
                if len(symbols_list) == 1:
                    # 单个元素时使用 = 而不是 IN
                    futures_info = self.query(f"""
                        SELECT symbol, contract_symbol, name, exchange, link
                        FROM `{self.futures_table}`
                        WHERE symbol = %s
                    """, (symbols_list[0],))
                else:
                    # 多个元素时使用 IN，使用参数化查询
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
                        logger.warning(f"[Database] Future {symbol} not found in global futures table, using default values")
                    
                    # 生成唯一ID
                    future_id = self._generate_id()
                    
                    # 插入到model_futures表
                    try:
                        self.insert_rows(
                            self.model_futures_table,
                            [[future_id, model_uuid, futures_dict[symbol]['symbol'], 
                              futures_dict[symbol]['contract_symbol'], futures_dict[symbol]['name'],
                              futures_dict[symbol]['exchange'], futures_dict[symbol]['link'], 0]],
                            ["id", "model_id", "symbol", "contract_symbol", "name", "exchange", "link", "sort_order"]
                        )
                        added_count += 1
                        logger.debug(f"[Database] Added future {symbol} to model {model_id} in model_futures table")
                    except Exception as insert_error:
                        logger.error(f"[Database] Failed to insert future {symbol} for model {model_id}: {insert_error}")
                        # 继续处理其他合约，不中断整个流程
                        continue
                
                logger.info(f"[Database] Successfully added {added_count}/{len(symbols_to_add)} futures to model_futures table for model {model_id}")
            else:
                logger.info(f"[Database] No new futures to add for model {model_id}")
            
            # 5. 从model_futures表删除不再在portfolios表中出现的合约
            if symbols_to_delete:
                logger.info(f"[Database] Deleting {len(symbols_to_delete)} futures from model_futures table for model {model_id}")
                
                # 使用参数化查询删除
                for symbol in symbols_to_delete:
                    try:
                        self.command(f"""
                            DELETE FROM `{self.model_futures_table}`
                            WHERE model_id = %s AND symbol = %s
                        """, (model_uuid, symbol))
                        logger.debug(f"[Database] Deleted future {symbol} from model {model_id} in model_futures table")
                    except Exception as delete_error:
                        logger.error(f"[Database] Failed to delete future {symbol} for model {model_id}: {delete_error}")
                        # 继续处理其他合约，不中断整个流程
                        continue
                
                logger.info(f"[Database] Successfully deleted {len(symbols_to_delete)} futures from model_futures table for model {model_id}")
            else:
                logger.info(f"[Database] No futures to delete for model {model_id}")
            
            logger.info(f"[Database] Successfully synced model_futures for model {model_id}: "
                        f"added {len(symbols_to_add)}, deleted {len(symbols_to_delete)}")
            return True
            
        except Exception as e:
            logger.error(f"[Database] Failed to sync model_futures from portfolio for model {model_id}: {e}")
            import traceback
            logger.error(f"[Database] Error stack: {traceback.format_exc()}")
            return False
    
    # ============ Settings（系统设置）管理方法 ============
    
    def get_settings(self) -> Dict:
        """
        Get system settings
        
        注意：此方法已迁移到 common.database.database_settings.SettingsDatabase
        保留此方法仅用于向后兼容。
        """
        try:
            from .database_settings import SettingsDatabase
            settings_db = SettingsDatabase(pool=self._pool)
            return settings_db.get_settings()
        except Exception as e:
            logger.error(f"[Database] Failed to get settings: {e}")
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
        
        注意：此方法已迁移到 common.database.database_settings.SettingsDatabase
        保留此方法仅用于向后兼容。
        """
        try:
            from .database_settings import SettingsDatabase
            settings_db = SettingsDatabase(pool=self._pool)
            return settings_db.update_settings(buy_frequency_minutes, sell_frequency_minutes, trading_fee_rate, show_system_prompt, conversation_limit)
        except Exception as e:
            logger.error(f"[Database] Failed to update settings: {e}")
            return False
    
    
    # ==================================================================
    # Accounts Management (账户信息管理) - 已废弃，accounts表已删除
    # 账户管理功能已迁移到 AccountDatabase 类（使用 account_asset 表）
    # ==================================================================
    
    # ============ Account Asset（账户资产）管理方法 ============
    
    # add_account_asset, get_all_account_assets 方法已迁移到AccountDatabase类，不再需要
    
    def get_account_asset(self, account_alias: str) -> Optional[Dict]:
        """
        获取账户资产信息（最新记录）
        
        Args:
            account_alias: 账户唯一识别码
            
        Returns:
            账户资产信息字典，如果不存在则返回None
            返回格式包含字段映射：
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
            logger.error(f"[Database] Failed to get account asset {account_alias}: {e}")
            return None
    
    def get_latest_account_value(self, model_id: int) -> Optional[Dict]:
        """
        获取模型最新的账户价值记录（从account_values表）
        
        Args:
            model_id: 模型ID
            
        Returns:
            账户价值信息字典，如果不存在则返回None
            包含字段：balance, available_balance, cross_wallet_balance, cross_un_pnl, account_alias
        """
        try:
            from .database_account_values import AccountValuesDatabase
            from .database_models import ModelsDatabase
            account_values_db = AccountValuesDatabase(pool=self._pool)
            models_db = ModelsDatabase(pool=self._pool)
            model_mapping = models_db._get_model_id_mapping()
            return account_values_db.get_latest_account_value(model_id, model_mapping)
        except Exception as e:
            logger.error(f"[Database] Failed to get latest account value for model {model_id}: {e}")
            return None
    
    
    # ============ 策略管理方法 ============
    
    def get_model_strategies(self, model_id: int, strategy_type: str) -> List[Dict]:
        """
        获取模型关联的策略列表（按优先级和创建时间排序）
        
        注意：此方法已迁移到 common.database.database_strategys.StrategysDatabase
        保留此方法仅用于向后兼容。
        
        Args:
            model_id: 模型ID（整数）
            strategy_type: 策略类型，'buy' 或 'sell'
        
        Returns:
            List[Dict]: 策略列表
        """
        try:
            from .database_strategys import StrategysDatabase
            from .database_models import ModelsDatabase
            strategys_db = StrategysDatabase(pool=self._pool)
            models_db = ModelsDatabase(pool=self._pool)
            model_mapping = models_db._get_model_id_mapping()
            return strategys_db.get_model_strategies_by_int_id(model_id, strategy_type, model_mapping)
        except Exception as e:
            logger.error(f"[Database] Failed to get model strategies: {e}")
            return []

