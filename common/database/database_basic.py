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
import logging
import time
import uuid
import common.config as app_config
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any, Callable
from .database_init import (
    init_database_tables, 
    PROVIDERS_TABLE, MODELS_TABLE, PORTFOLIOS_TABLE, TRADES_TABLE,
    CONVERSATIONS_TABLE, ACCOUNT_VALUES_TABLE, ACCOUNT_VALUE_HISTORYS_TABLE,
    SETTINGS_TABLE, MODEL_PROMPTS_TABLE, MODEL_FUTURES_TABLE, FUTURES_TABLE,
    ACCOUNT_ASSET_TABLE, ASSET_TABLE, BINANCE_TRADE_LOGS_TABLE,
    STRATEGYS_TABLE, MODEL_STRATEGY_TABLE
)
import pymysql
from pymysql import cursors
from dbutils.pooled_db import PooledDB

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
    - 投资组合管理：持仓更新、账户价值记录、投资组合查询（账户价值记录已迁移到 database_account_values.AccountValuesDatabase）
    - 交易记录：交易历史的记录和查询（已迁移到 database_trades.TradesDatabase）
    - 对话记录：AI对话历史的记录和查询（已迁移到 database_conversations.ConversationsDatabase）
    - 账户价值历史：账户价值历史查询（已迁移到 database_account_value_historys.AccountValueHistorysDatabase）
    - 合约配置：期货合约配置查询（增删改已迁移到Java后端）
    - 账户资产：账户资产信息查询（增删改已迁移到Java后端）
    - 提示词管理：模型买卖提示词配置
    
    使用示例：
        db = Database()
        db.init_db()  # 初始化所有表
        from common.database.database_models import ModelsDatabase
        from common.database.database_portfolios import PortfoliosDatabase
        from common.database.database_trades import TradesDatabase
        from common.database.database_conversations import ConversationsDatabase
        from common.database.database_account_values import AccountValuesDatabase
        from common.database.database_account_value_historys import AccountValueHistorysDatabase
        models_db = ModelsDatabase(pool=db._pool)
        portfolios_db = PortfoliosDatabase(pool=db._pool)
        trades_db = TradesDatabase(pool=db._pool)
        conversations_db = ConversationsDatabase(pool=db._pool)
        account_values_db = AccountValuesDatabase(pool=db._pool)
        account_value_historys_db = AccountValueHistorysDatabase(pool=db._pool)
        model = models_db.get_model(model_id)
        portfolio = portfolios_db.get_portfolio(model_id, current_prices, ...)
        trades_db.add_trade(model_id, symbol, signal, quantity, price)
        conversations_db.add_conversation(model_id, user_prompt, ai_response)
        account_values_db.record_account_value(model_id, balance, available_balance, cross_wallet_balance)
        history = account_value_historys_db.get_account_value_history(model_id, limit=100)
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
                # 无论什么异常，都要确保连接被正确释放，防止连接泄露
                if connection_acquired and conn:
                    try:
                        # 回滚事务
                        try:
                            conn.rollback()
                        except Exception as rollback_error:
                            logger.debug(f"[Database] Error rolling back transaction: {rollback_error}")
                        
                        # 对于所有错误，关闭连接，DBUtils会自动处理损坏的连接
                        try:
                            conn.close()
                        except Exception as close_error:
                            logger.debug(f"[Database] Error closing connection: {close_error}")
                        finally:
                            # 确保连接引用被清除，即使关闭失败也要标记为已处理
                            conn = None
                    except Exception as close_error:
                        logger.error(f"[Database] Critical error closing failed connection: {close_error}")
                        # 即使发生异常，也要清除连接引用
                        conn = None
                
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
            'strategy_table': self.strategys_table,
            'model_strategy_table': self.model_strategy_table,
        }
        init_database_tables(self.command, table_names)
        
        # Insert default settings if no settings exist
        self._init_default_settings()
        
        logger.info("[Database] MySQL tables initialized")
    
    # 表初始化方法已移至 common/database/database_init.py
    
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
                    [[settings_id, 5, 5, 0.002, 0, 5, None, None, 0.0, 8192, 0.9, 50, current_time, current_time]],
                    ["id", "buy_frequency_minutes", "sell_frequency_minutes", "trading_fee_rate", "show_system_prompt", "conversation_limit", "strategy_provider", "strategy_model", "strategy_temperature", "strategy_max_tokens", "strategy_top_p", "strategy_top_k", "created_at", "updated_at"]
                )
                logger.info("[Database] Default settings initialized")
        except Exception as e:
            logger.warning(f"[Database] Failed to initialize default settings: {e}")
    
    def _generate_id(self) -> str:
        """Generate a unique ID (UUID)"""
        return str(uuid.uuid4())
    


