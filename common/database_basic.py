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
from common.database_mysql import MySQLConnectionPool
import pymysql
from pymysql import cursors

logger = logging.getLogger(__name__)


class Database:
    """
    基础数据库操作封装类
    
    封装所有业务数据的MySQL数据库操作，包括提供商、模型、投资组合、交易记录等。
    使用连接池管理数据库连接，支持高并发访问。
    
    主要功能：
    - 提供商管理：LLM提供商的增删改查
    - 模型管理：交易模型的增删改查、自动交易开关、杠杆设置
    - 投资组合管理：持仓更新、账户价值记录、投资组合查询
    - 交易记录：交易历史的记录和查询
    - 对话记录：AI对话历史的记录和查询
    - 合约配置：期货合约配置管理
    - 账户资产：账户资产信息管理
    - 提示词管理：模型买卖提示词配置
    
    使用示例：
        db = Database()
        db.init_db()  # 初始化所有表
        model = db.get_model(model_id)
        portfolio = db.get_portfolio(model_id, current_prices)
        db.add_trade(model_id, symbol, signal, quantity, price)
    
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
        # 使用 MySQL 连接池，参考 database_mysql.py 的模式
        self._pool = MySQLConnectionPool(
            host=app_config.MYSQL_HOST,
            port=app_config.MYSQL_PORT,
            user=app_config.MYSQL_USER,
            password=app_config.MYSQL_PASSWORD,
            database=app_config.MYSQL_DATABASE,
            charset='utf8mb4',
            min_connections=15,
            max_connections=100,
            connection_timeout=30
        )
        
        # 表名定义
        self.providers_table = "providers"
        self.models_table = "models"
        self.portfolios_table = "portfolios"
        self.trades_table = "trades"
        self.conversations_table = "conversations"
        self.account_values_table = "account_values"
        self.settings_table = "settings"
        self.model_prompts_table = "model_prompts"
        self.model_futures_table = "model_futures"
        self.futures_table = "futures"
        self.account_asset_table = "account_asset"
        self.asset_table = "asset"
        self.binance_trade_logs_table = "binance_trade_logs"
    
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
                conn = self._pool.acquire()
                if not conn:
                    raise Exception("Failed to acquire MySQL connection")
                connection_acquired = True
                
                # 执行函数
                result = func(conn, *args, **kwargs)
                
                # 成功执行，提交事务并释放连接
                conn.commit()
                self._pool.release(conn)
                conn = None  # 标记已释放，避免 finally 中重复处理
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
                
                # 如果已获取连接，需要处理连接（关闭或释放）
                if connection_acquired and conn:
                    try:
                        # 回滚事务
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                        
                        # 对于网络错误，连接很可能已损坏，应该关闭而不是放回池中
                        if is_network_error:
                            logger.warning(
                                f"[Database] Network error detected, closing damaged connection: "
                                f"{error_type}: {error_msg}"
                            )
                            try:
                                conn.close()
                            except Exception:
                                pass
                            # 减少连接计数（因为连接已损坏，不能放回池中）
                            with self._pool._lock:
                                if self._pool._current_connections > 0:
                                    self._pool._current_connections -= 1
                            conn = None  # 标记已处理，避免 finally 中重复处理
                        else:
                            # 对于非网络错误，尝试释放连接回池中
                            try:
                                self._pool.release(conn)
                                conn = None  # 标记已释放
                            except Exception as release_error:
                                # 如果释放失败，关闭连接
                                logger.warning(
                                    f"[Database] Failed to release connection, closing it: {release_error}"
                                )
                                try:
                                    conn.close()
                                except Exception:
                                    pass
                                with self._pool._lock:
                                    if self._pool._current_connections > 0:
                                        self._pool._current_connections -= 1
                                conn = None  # 标记已处理
                    except Exception as close_error:
                        logger.debug(f"[Database] Error closing failed connection: {close_error}")
                        # 确保连接计数被减少
                        with self._pool._lock:
                            if self._pool._current_connections > 0:
                                self._pool._current_connections -= 1
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
    
    def query(self, sql: str, params: tuple = None) -> List[Tuple]:
        """Execute a query and return results.
        
        注意：MySQL 支持参数化查询，使用 %s 作为占位符。
        """
        def _execute_query(conn):
            cursor = conn.cursor()
            try:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                rows = cursor.fetchall()
                # 转换为元组列表以保持兼容性
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
        
        # Providers table (API提供方)
        self._ensure_providers_table()
        
        # Models table
        self._ensure_models_table()
        
        # Portfolios table
        self._ensure_portfolios_table()
        
        # Trades table
        self._ensure_trades_table()
        
        # Conversations table
        self._ensure_conversations_table()
        
        # Account values history table
        self._ensure_account_values_table()
        
        # Settings table
        self._ensure_settings_table()
        
        # Model prompts table
        self._ensure_model_prompts_table()
        
        # Model-specific futures configuration table
        self._ensure_model_futures_table()
        
        # Futures table (USDS-M contract universe)
        self._ensure_futures_table()
        
        
        # Account asset table (accounts表已废弃，不再创建)
        self._ensure_account_asset_table()
        
        # Asset table
        self._ensure_asset_table()
        
        # Binance trade logs table
        self._ensure_binance_trade_logs_table()
        
        # Insert default settings if no settings exist
        self._init_default_settings()
        
        logger.info("[Database] MySQL tables initialized")
    
    def _ensure_providers_table(self):
        """Create providers table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{self.providers_table}` (
            `id` VARCHAR(36) PRIMARY KEY,
            `name` VARCHAR(200) NOT NULL,
            `api_url` VARCHAR(500) NOT NULL,
            `api_key` VARCHAR(500) NOT NULL,
            `models` TEXT,
            `provider_type` VARCHAR(50) DEFAULT 'openai',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX `idx_created_at` (`created_at`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.providers_table} exists")
    
    def _ensure_models_table(self):
        """Create models table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{self.models_table}` (
            `id` VARCHAR(36) PRIMARY KEY,
            `name` VARCHAR(200) NOT NULL,
            `provider_id` VARCHAR(36) NOT NULL,
            `model_name` VARCHAR(200) NOT NULL,
            `initial_capital` DOUBLE DEFAULT 10000,
            `leverage` TINYINT UNSIGNED DEFAULT 10,
            `auto_trading_enabled` TINYINT UNSIGNED DEFAULT 1,
            `max_positions` TINYINT UNSIGNED DEFAULT 3,
            `api_key` VARCHAR(500),
            `api_secret` VARCHAR(500),
            `account_alias` VARCHAR(100),
            `is_virtual` TINYINT UNSIGNED DEFAULT 0,
            `symbol_source` VARCHAR(50) DEFAULT 'leaderboard',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX `idx_provider_id` (`provider_id`),
            INDEX `idx_account_alias` (`account_alias`),
            INDEX `idx_created_at` (`created_at`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.models_table} exists")
    
    def _ensure_portfolios_table(self):
        """Create portfolios table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{self.portfolios_table}` (
            `id` VARCHAR(36) PRIMARY KEY,
            `model_id` VARCHAR(36) NOT NULL,
            `symbol` VARCHAR(50) NOT NULL,
            `position_amt` DOUBLE DEFAULT 0.0,
            `avg_price` DOUBLE DEFAULT 0.0,
            `leverage` TINYINT UNSIGNED DEFAULT 1,
            `position_side` VARCHAR(10) DEFAULT 'LONG',
            `initial_margin` DOUBLE DEFAULT 0.0,
            `unrealized_profit` DOUBLE DEFAULT 0.0,
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY `uk_model_symbol_side` (`model_id`, `symbol`, `position_side`),
            INDEX `idx_model_id` (`model_id`),
            INDEX `idx_updated_at` (`updated_at`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.portfolios_table} exists")
    
    def _ensure_trades_table(self):
        """Create trades table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{self.trades_table}` (
            `id` VARCHAR(36) PRIMARY KEY,
            `model_id` VARCHAR(36) NOT NULL,
            `future` VARCHAR(50) NOT NULL,
            `signal` VARCHAR(50) NOT NULL,
            `quantity` DOUBLE DEFAULT 0.0,
            `price` DOUBLE DEFAULT 0.0,
            `leverage` TINYINT UNSIGNED DEFAULT 1,
            `side` VARCHAR(10) DEFAULT 'long',
            `pnl` DOUBLE DEFAULT 0,
            `fee` DOUBLE DEFAULT 0,
            `timestamp` DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX `idx_model_timestamp` (`model_id`, `timestamp`),
            INDEX `idx_future` (`future`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.trades_table} exists")
    
    def _ensure_conversations_table(self):
        """Create conversations table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{self.conversations_table}` (
            `id` VARCHAR(36) PRIMARY KEY,
            `model_id` VARCHAR(36) NOT NULL,
            `user_prompt` LONGTEXT,
            `ai_response` LONGTEXT,
            `cot_trace` LONGTEXT,
            `tokens` INT DEFAULT 0,
            `timestamp` DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX `idx_model_timestamp` (`model_id`, `timestamp`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.conversations_table} exists with index for efficient timestamp DESC sorting")
    
    def _ensure_account_values_table(self):
        """Create account_values table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{self.account_values_table}` (
            `id` VARCHAR(36) PRIMARY KEY,
            `model_id` VARCHAR(36) NOT NULL,
            `account_alias` VARCHAR(100) DEFAULT '',
            `balance` DOUBLE DEFAULT 0.0,
            `available_balance` DOUBLE DEFAULT 0.0,
            `cross_wallet_balance` DOUBLE DEFAULT 0.0,
            `cross_un_pnl` DOUBLE DEFAULT 0.0,
            `timestamp` DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX `idx_model_alias_timestamp` (`model_id`, `account_alias`, `timestamp`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.account_values_table} exists")
    
    def _ensure_settings_table(self):
        """Create settings table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{self.settings_table}` (
            `id` VARCHAR(36) PRIMARY KEY,
            `trading_frequency_minutes` INT UNSIGNED DEFAULT 5,
            `trading_fee_rate` DOUBLE DEFAULT 0.002,
            `show_system_prompt` TINYINT UNSIGNED DEFAULT 0,
            `conversation_limit` INT UNSIGNED DEFAULT 5,
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.settings_table} exists")
    
    def _ensure_model_prompts_table(self):
        """Create model_prompts table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{self.model_prompts_table}` (
            `id` VARCHAR(36) PRIMARY KEY,
            `model_id` VARCHAR(36) NOT NULL,
            `buy_prompt` TEXT,
            `sell_prompt` TEXT,
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY `uk_model_id` (`model_id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.model_prompts_table} exists")
    
    def _ensure_model_futures_table(self):
        """Create model_futures table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{self.model_futures_table}` (
            `id` VARCHAR(36) PRIMARY KEY,
            `model_id` VARCHAR(36) NOT NULL,
            `symbol` VARCHAR(50) NOT NULL,
            `contract_symbol` VARCHAR(100) DEFAULT '',
            `name` VARCHAR(200) DEFAULT '',
            `exchange` VARCHAR(50) DEFAULT 'BINANCE_FUTURES',
            `link` VARCHAR(500) DEFAULT '',
            `sort_order` INT DEFAULT 0,
            UNIQUE KEY `uk_model_symbol` (`model_id`, `symbol`),
            INDEX `idx_sort_order` (`sort_order`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.model_futures_table} exists")
    
    def _ensure_futures_table(self):
        """Create futures table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{self.futures_table}` (
            `id` VARCHAR(36) PRIMARY KEY,
            `symbol` VARCHAR(50) NOT NULL,
            `contract_symbol` VARCHAR(100) DEFAULT '',
            `name` VARCHAR(200) DEFAULT '',
            `exchange` VARCHAR(50) DEFAULT 'BINANCE_FUTURES',
            `link` VARCHAR(500) DEFAULT '',
            `sort_order` INT DEFAULT 0,
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY `uk_symbol` (`symbol`),
            INDEX `idx_sort_order` (`sort_order`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.futures_table} exists")
    
    
    # accounts表已废弃，不再创建
    
    def _ensure_account_asset_table(self):
        """Create account_asset table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{self.account_asset_table}` (
            `account_alias` VARCHAR(100) PRIMARY KEY,
            `account_name` VARCHAR(200) NOT NULL,
            `api_key` VARCHAR(500) NOT NULL,
            `api_secret` VARCHAR(500) NOT NULL,
            `total_initial_margin` DOUBLE DEFAULT 0.0,
            `total_maint_margin` DOUBLE DEFAULT 0.0,
            `total_wallet_balance` DOUBLE DEFAULT 0.0,
            `total_unrealized_profit` DOUBLE DEFAULT 0.0,
            `total_margin_balance` DOUBLE DEFAULT 0.0,
            `total_position_initial_margin` DOUBLE DEFAULT 0.0,
            `total_open_order_initial_margin` DOUBLE DEFAULT 0.0,
            `total_cross_wallet_balance` DOUBLE DEFAULT 0.0,
            `total_cross_un_pnl` DOUBLE DEFAULT 0.0,
            `available_balance` DOUBLE DEFAULT 0.0,
            `max_withdraw_amount` DOUBLE DEFAULT 0.0,
            `update_time` BIGINT UNSIGNED DEFAULT 0,
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE INDEX `idx_account_alias` (`account_alias`),
            INDEX `idx_update_time` (`update_time`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.account_asset_table} exists")
    
    def _ensure_asset_table(self):
        """Create asset table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{self.asset_table}` (
            `account_alias` VARCHAR(100) NOT NULL,
            `asset` VARCHAR(50) NOT NULL,
            `wallet_balance` DOUBLE DEFAULT 0.0,
            `unrealized_profit` DOUBLE DEFAULT 0.0,
            `margin_balance` DOUBLE DEFAULT 0.0,
            `maint_margin` DOUBLE DEFAULT 0.0,
            `initial_margin` DOUBLE DEFAULT 0.0,
            `position_initial_margin` DOUBLE DEFAULT 0.0,
            `open_order_initial_margin` DOUBLE DEFAULT 0.0,
            `cross_wallet_balance` DOUBLE DEFAULT 0.0,
            `cross_un_pnl` DOUBLE DEFAULT 0.0,
            `available_balance` DOUBLE DEFAULT 0.0,
            `max_withdraw_amount` DOUBLE DEFAULT 0.0,
            `update_time` BIGINT UNSIGNED DEFAULT 0,
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (`account_alias`, `asset`),
            INDEX `idx_account_alias` (`account_alias`),
            INDEX `idx_update_time` (`update_time`),
            FOREIGN KEY (`account_alias`) REFERENCES `{self.account_asset_table}`(`account_alias`) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.asset_table} exists")
    
    def _ensure_binance_trade_logs_table(self):
        """Create binance_trade_logs table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{self.binance_trade_logs_table}` (
            `id` VARCHAR(36) PRIMARY KEY,
            `model_id` VARCHAR(36),
            `conversation_id` VARCHAR(36),
            `trade_id` VARCHAR(36),
            `type` VARCHAR(10) NOT NULL COMMENT 'test or real',
            `method_name` VARCHAR(50) NOT NULL COMMENT 'stop_loss_trade, take_profit_trade, trailing_stop_market_trade, close_position_trade',
            `param` JSON COMMENT '所有调用接口的入参数，JSON格式存储',
            `response_context` JSON COMMENT '接口返回的内容，JSON格式',
            `response_type` VARCHAR(10) COMMENT '接口返回状态码：200, 4XX, 5XX等',
            `error_context` TEXT COMMENT '接口返回状态不为200时记录相关的返回错误信息',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX `idx_model_id` (`model_id`),
            INDEX `idx_conversation_id` (`conversation_id`),
            INDEX `idx_trade_id` (`trade_id`),
            INDEX `idx_type` (`type`),
            INDEX `idx_method_name` (`method_name`),
            INDEX `idx_response_type` (`response_type`),
            INDEX `idx_created_at` (`created_at`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.binance_trade_logs_table} exists")
    
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
                    [[settings_id, 5, 0.002, 0, current_time, current_time]],
                    ["id", "trading_frequency_minutes", "trading_fee_rate", "show_system_prompt", "created_at", "updated_at"]
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
    
    def add_provider(self, name: str, api_url: str, api_key: str, models: str = '', provider_type: str = 'openai') -> int:
        """Add new API provider
        
        注意：返回类型保持为 int 以兼容原接口，但实际存储的是 String (UUID)
        """
        provider_id = self._generate_id()
        try:
            self.insert_rows(
                self.providers_table,
                [[provider_id, name, api_url, api_key, models or '', provider_type.lower(), datetime.now(timezone.utc)]],
                ["id", "name", "api_url", "api_key", "models", "provider_type", "created_at"]
            )
            # 为了兼容性，返回一个数字 ID（使用 UUID 的 hash）
            return self._uuid_to_int(provider_id)
        except Exception as e:
            logger.error(f"[Database] Failed to add provider: {e}")
            raise
    
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
    
    def get_all_providers(self) -> List[Dict]:
        """Get all API providers"""
        try:
            rows = self.query(f"SELECT * FROM {self.providers_table} ORDER BY created_at DESC")
            columns = ["id", "name", "api_url", "api_key", "models", "provider_type", "created_at"]
            results = self._rows_to_dicts(rows, columns)
            # 转换 ID 为 int 以保持兼容性
            for result in results:
                result['id'] = self._uuid_to_int(result['id'])
            return results
        except Exception as e:
            logger.error(f"[Database] Failed to get all providers: {e}")
            return []
    
    def update_provider(self, provider_id: int, name: str, api_url: str, api_key: str, models: str, provider_type: str = 'openai'):
        """Update provider information"""
        try:
            # 查找匹配的 provider
            provider = self.get_provider(provider_id)
            if not provider:
                logger.warning(f"[Database] Provider {provider_id} not found for update")
                return
            
            actual_id = provider['id']
            # MySQL 使用 DELETE + INSERT 来实现 UPDATE
            self.command(f"DELETE FROM {self.providers_table} WHERE id = '{actual_id}'")
            self.insert_rows(
                self.providers_table,
                [[actual_id, name, api_url, api_key, models or '', provider_type.lower(), provider.get('created_at', datetime.now(timezone.utc))]],
                ["id", "name", "api_url", "api_key", "models", "provider_type", "created_at"]
            )
        except Exception as e:
            logger.error(f"[Database] Failed to update provider {provider_id}: {e}")
            raise
    
    def delete_provider(self, provider_id: int):
        """Delete provider"""
        try:
            provider = self.get_provider(provider_id)
            if not provider:
                logger.warning(f"[Database] Provider {provider_id} not found for deletion")
                return
            
            actual_id = provider['id']
            self.command(f"DELETE FROM {self.providers_table} WHERE id = '{actual_id}'")
        except Exception as e:
            logger.error(f"[Database] Failed to delete provider {provider_id}: {e}")
            raise
    
    # ============ Model（模型）管理方法 ============
    
    def _get_model_id_mapping(self) -> Dict[int, str]:
        """Get mapping from int ID to UUID string ID for models"""
        try:
            rows = self.query(f"SELECT id FROM {self.models_table}")
            mapping = {}
            for row in rows:
                uuid_str = row[0]
                int_id = self._uuid_to_int(uuid_str)
                mapping[int_id] = uuid_str
            return mapping
        except Exception as e:
            logger.error(f"[Database] Failed to get model ID mapping: {e}")
            return {}
    
    def _get_provider_id_mapping(self) -> Dict[int, str]:
        """Get mapping from int ID to UUID string ID for providers"""
        try:
            rows = self.query(f"SELECT id FROM {self.providers_table}")
            mapping = {}
            for row in rows:
                uuid_str = row[0]
                int_id = self._uuid_to_int(uuid_str)
                mapping[int_id] = uuid_str
            return mapping
        except Exception as e:
            logger.error(f"[Database] Failed to get provider ID mapping: {e}")
            return {}
    
    def add_model(self, name: str, provider_id: int, model_name: str,
                 initial_capital: float = 10000, leverage: int = 10, api_key: str = '', api_secret: str = '', 
                 account_alias: str = '', is_virtual: bool = True, symbol_source: str = 'leaderboard', 
                 max_positions: int = 3) -> int:
        """
        Add new trading model
        
        【symbol_source字段说明】
        此字段用于AI交易买入决策时确定交易对数据来源：
        - 'leaderboard': 从涨跌榜（24_market_tickers表）获取交易对，这是默认值，保持向后兼容
        - 'future': 从合约配置信息表（futures表）获取所有已配置的交易对
        
        该字段仅在buy类型的AI交互中使用，sell逻辑不受影响。
        相关调用链：trading_engine._select_buy_candidates() -> market_data.get_leaderboard() 或 get_configured_futures_symbols()
        
        Args:
            name: 模型名称
            provider_id: 提供方ID
            model_name: 模型名称
            initial_capital: 初始资金
            leverage: 杠杆倍数
            api_key: API密钥（如果提供了account_alias，则从account_asset表获取）
            api_secret: API密钥（如果提供了account_alias，则从account_asset表获取）
            account_alias: 账户别名（可选，如果提供则从account_asset表获取api_key和api_secret）
            is_virtual: 是否虚拟账户，默认False
            symbol_source: 交易对来源，'future'（合约配置信息）或'leaderboard'（涨跌榜），默认'leaderboard'
            max_positions: 最大持仓数量，默认3
        """
        model_id = self._generate_id()
        provider_mapping = self._get_provider_id_mapping()
        provider_uuid = provider_mapping.get(provider_id, '')
        
        # 【数据验证】确保symbol_source值合法，非法值自动回退到默认值'leaderboard'
        if symbol_source not in ['future', 'leaderboard']:
            logger.warning(f"[Database] Invalid symbol_source value '{symbol_source}', using default 'leaderboard'")
            symbol_source = 'leaderboard'
        
        # 如果提供了account_alias，从account_asset表获取api_key和api_secret
        final_api_key = api_key
        final_api_secret = api_secret
        if account_alias:
            try:
                account_rows = self.query(f"""
                    SELECT api_key, api_secret FROM `{self.account_asset_table}`
                    WHERE account_alias = %s
                    LIMIT 1
                """, (account_alias,))
                if account_rows and len(account_rows) > 0:
                    final_api_key = account_rows[0][0] if account_rows[0][0] else api_key
                    final_api_secret = account_rows[0][1] if account_rows[0][1] else api_secret
                    # 验证从数据库获取的api_key和api_secret不能为空
                    if not final_api_key or not final_api_key.strip():
                        raise ValueError(f"Account {account_alias} has empty api_key in database")
                    if not final_api_secret or not final_api_secret.strip():
                        raise ValueError(f"Account {account_alias} has empty api_secret in database")
                else:
                    raise ValueError(f"Account {account_alias} not found in database")
            except Exception as e:
                logger.error(f"[Database] Failed to get account credentials for {account_alias}: {e}")
                raise
        
        # 验证最终使用的api_key和api_secret不能为空
        if not final_api_key or not final_api_key.strip():
            raise ValueError("api_key is required and cannot be empty")
        if not final_api_secret or not final_api_secret.strip():
            raise ValueError("api_secret is required and cannot be empty")
        
        try:
            # 验证max_positions值
            if not isinstance(max_positions, int) or max_positions < 1:
                logger.warning(f"[Database] Invalid max_positions value: {max_positions}, using default 3")
                max_positions = 3
            
            self.insert_rows(
                self.models_table,
                [[model_id, name, provider_uuid, model_name, initial_capital, leverage, 1, max_positions, final_api_key, final_api_secret, account_alias, 1 if is_virtual else 0, symbol_source, datetime.now(timezone.utc)]],
                ["id", "name", "provider_id", "model_name", "initial_capital", "leverage", "auto_trading_enabled", "max_positions", "api_key", "api_secret", "account_alias", "is_virtual", "symbol_source", "created_at"]
            )
            
            # 初始化account_values表的一条记录（确保account_alias插入到account_values表中）
            try:
                av_id = self._generate_id()
                # 初始值使用initial_capital作为balance
                self.insert_rows(
                    self.account_values_table,
                    [[av_id, model_id, account_alias or '', initial_capital, initial_capital, initial_capital, 0.0, datetime.now(timezone.utc)]],
                    ["id", "model_id", "account_alias", "balance", "available_balance", "cross_wallet_balance", "cross_un_pnl", "timestamp"]
                )
                logger.debug(f"[Database] Initialized account_values record for model {self._uuid_to_int(model_id)} with account_alias={account_alias}")
            except Exception as av_err:
                logger.warning(f"[Database] Failed to initialize account_values record for model {self._uuid_to_int(model_id)}: {av_err}")
                # 不阻止模型创建，account_values初始化失败不影响模型创建
            
            return self._uuid_to_int(model_id)
        except Exception as e:
            logger.error(f"[Database] Failed to add model: {e}")
            raise
    
    def get_model(self, model_id: int) -> Optional[Dict]:
        """Get model information"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return None
            
            # 查询 model 和关联的 provider
            rows = self.query(f"""
                SELECT m.id, m.name, m.provider_id, m.model_name, m.initial_capital, 
                       m.leverage, m.auto_trading_enabled, m.max_positions, m.account_alias, m.is_virtual, m.symbol_source, m.created_at,
                       p.api_key, p.api_url, p.provider_type
                FROM {self.models_table} m
                LEFT JOIN {self.providers_table} p ON m.provider_id = p.id
                WHERE m.id = '{model_uuid}'
            """)
            
            if not rows:
                return None
            
            columns = ["id", "name", "provider_id", "model_name", "initial_capital", 
                      "leverage", "auto_trading_enabled", "max_positions", "account_alias", "is_virtual", "symbol_source", "created_at",
                      "api_key", "api_url", "provider_type"]
            result = self._row_to_dict(rows[0], columns)
            # 转换 ID 为 int 以保持兼容性
            result['id'] = model_id
            if result.get('provider_id'):
                provider_mapping = self._get_provider_id_mapping()
                for pid, puuid in provider_mapping.items():
                    if puuid == result['provider_id']:
                        result['provider_id'] = pid
                        break
            # 【兼容性处理】确保symbol_source有默认值（处理旧数据或字段缺失的情况）
            # 如果数据库中没有该字段或值为空，默认使用'leaderboard'以保持向后兼容
            if not result.get('symbol_source'):
                result['symbol_source'] = 'leaderboard'
            # 【兼容性处理】确保is_virtual有默认值
            if result.get('is_virtual') is None:
                result['is_virtual'] = False
            else:
                result['is_virtual'] = bool(result.get('is_virtual', 0))
            return result
        except Exception as e:
            logger.error(f"[Database] Failed to get model {model_id}: {e}")
            return None
    
    def get_all_models(self) -> List[Dict]:
        """Get all trading models"""
        try:
            rows = self.query(f"""
                SELECT m.id, m.name, m.provider_id, m.model_name, m.initial_capital,
                       m.leverage, m.auto_trading_enabled, m.max_positions, m.account_alias, m.is_virtual, m.symbol_source, m.created_at,
                       p.name as provider_name
                FROM {self.models_table} m
                LEFT JOIN {self.providers_table} p ON m.provider_id = p.id
                ORDER BY m.created_at DESC
            """)
            columns = ["id", "name", "provider_id", "model_name", "initial_capital",
                      "leverage", "auto_trading_enabled", "max_positions", "account_alias", "is_virtual", "symbol_source", "created_at", "provider_name"]
            results = self._rows_to_dicts(rows, columns)
            
            # 转换 ID 为 int 以保持兼容性
            provider_mapping = self._get_provider_id_mapping()
            for result in results:
                result['id'] = self._uuid_to_int(result['id'])
                if result.get('provider_id'):
                    for pid, puuid in provider_mapping.items():
                        if puuid == result['provider_id']:
                            result['provider_id'] = pid
                            break
                # 【兼容性处理】确保symbol_source有默认值（处理旧数据或字段缺失的情况）
                if not result.get('symbol_source'):
                    result['symbol_source'] = 'leaderboard'
                # 【兼容性处理】确保is_virtual有默认值
                if result.get('is_virtual') is None:
                    result['is_virtual'] = False
                # 【兼容性处理】确保max_positions有默认值
                if result.get('max_positions') is None:
                    result['max_positions'] = 3
                else:
                    result['is_virtual'] = bool(result.get('is_virtual', 0))
            return results
        except Exception as e:
            logger.error(f"[Database] Failed to get all models: {e}")
            return []
    
    def delete_model(self, model_id: int):
        """
        删除模型及其所有相关数据
        
        删除顺序（先删除依赖表，再删除主表）：
        1. portfolios - 持仓数据
        2. trades - 交易记录
        3. conversations - 对话记录
        4. account_values - 账户价值历史
        5. model_futures - 模型关联的期货合约
        6. model_prompts - 模型提示词配置
        7. models - 模型主表
        
        Args:
            model_id: 模型ID（整数ID）
        """
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                logger.warning(f"[Database] Model {model_id} not found for deletion")
                return
            
            logger.info(f"[Database] Starting deletion of model {model_id} (UUID: {model_uuid}) and all related data")
            
            # 删除相关数据（按依赖顺序删除）
            # 1. 删除持仓数据
            self.command(f"DELETE FROM `{self.portfolios_table}` WHERE model_id = %s", (model_uuid,))
            logger.debug(f"[Database] Deleted portfolios for model {model_id}")
            
            # 2. 删除交易记录
            self.command(f"DELETE FROM `{self.trades_table}` WHERE model_id = %s", (model_uuid,))
            logger.debug(f"[Database] Deleted trades for model {model_id}")
            
            # 3. 删除对话记录
            self.command(f"DELETE FROM `{self.conversations_table}` WHERE model_id = %s", (model_uuid,))
            logger.debug(f"[Database] Deleted conversations for model {model_id}")
            
            # 4. 删除账户价值历史
            self.command(f"DELETE FROM `{self.account_values_table}` WHERE model_id = %s", (model_uuid,))
            logger.debug(f"[Database] Deleted account_values for model {model_id}")
            
            # 5. 删除模型关联的期货合约
            self.command(f"DELETE FROM `{self.model_futures_table}` WHERE model_id = %s", (model_uuid,))
            logger.debug(f"[Database] Deleted model_futures for model {model_id}")
            
            # 6. 删除模型提示词配置
            self.command(f"DELETE FROM `{self.model_prompts_table}` WHERE model_id = %s", (model_uuid,))
            logger.debug(f"[Database] Deleted model_prompts for model {model_id}")
            
            # 7. 最后删除模型主表
            self.command(f"DELETE FROM `{self.models_table}` WHERE id = %s", (model_uuid,))
            logger.info(f"[Database] Successfully deleted model {model_id} and all related data")
            
        except Exception as e:
            logger.error(f"[Database] Failed to delete model {model_id}: {e}")
            raise
    
    def set_model_auto_trading(self, model_id: int, enabled: bool) -> bool:
        """Enable or disable auto trading for a model"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return False
            
            # 获取当前 model 数据
            model = self.get_model(model_id)
            if not model:
                return False
            
            # 获取 provider UUID
            provider_id_int = model.get('provider_id')
            provider_uuid = ''
            if provider_id_int:
                provider_mapping = self._get_provider_id_mapping()
                provider_uuid = provider_mapping.get(provider_id_int, '')
            
            # 使用 UPDATE 语句更新（MySQL支持UPDATE）
            self.command(f"""
                UPDATE `{self.models_table}` 
                SET `auto_trading_enabled` = %s
                WHERE `id` = %s
            """, (1 if enabled else 0, model_uuid))
            return True
        except Exception as e:
            logger.error(f"[Database] Failed to update auto trading flag for model {model_id}: {e}")
            return False
    
    def is_model_auto_trading_enabled(self, model_id: int) -> bool:
        """Check auto trading flag for a model"""
        try:
            model = self.get_model(model_id)
            if not model:
                return False
            return bool(model.get('auto_trading_enabled', 0))
        except Exception as e:
            logger.error(f"[Database] Failed to check auto trading flag for model {model_id}: {e}")
            return False
    
    def set_model_leverage(self, model_id: int, leverage: int) -> bool:
        """Update model leverage"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return False
            
            # 使用 UPDATE 语句更新（MySQL支持UPDATE）
            self.command(f"""
                UPDATE `{self.models_table}` 
                SET `leverage` = %s
                WHERE `id` = %s
            """, (leverage, model_uuid))
            return True
        except Exception as e:
            logger.error(f"[Database] Failed to update leverage for model {model_id}: {e}")
            return False
    
    def set_model_max_positions(self, model_id: int, max_positions: int) -> bool:
        """Update model max_positions (最大持仓数量)"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return False
            
            # 验证 max_positions 值
            if not isinstance(max_positions, int) or max_positions < 1:
                logger.error(f"[Database] Invalid max_positions value: {max_positions}, must be >= 1")
                return False
            
            # 使用 UPDATE 语句更新（MySQL支持UPDATE）
            self.command(f"""
                UPDATE `{self.models_table}` 
                SET `max_positions` = %s
                WHERE `id` = %s
            """, (max_positions, model_uuid))
            logger.info(f"[Database] Updated max_positions to {max_positions} for model {model_id}")
            return True
        except Exception as e:
            logger.error(f"[Database] Failed to update max_positions for model {model_id}: {e}")
            return False
    
    # ============ Portfolio（投资组合）管理方法 ============
    
    def update_position(self, model_id: int, symbol: str, position_amt: float,
                       avg_price: float, leverage: int = 1, position_side: str = 'LONG',
                       initial_margin: float = 0.0, unrealized_profit: float = 0.0):
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
        """
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                logger.warning(f"[Database] Model {model_id} not found for position update")
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
            logger.error(f"[Database] Failed to update position: {e}")
            raise
    
    def get_portfolio(self, model_id: int, current_prices: Dict = None) -> Dict:
        """Get portfolio with positions and P&L"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                logger.warning(f"[Database] Model {model_id} not found in mapping, returning empty portfolio")
                # 返回默认的空持仓信息，避免抛出异常导致交易周期失败
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
            model = self.get_model(model_id)
            if not model:
                logger.warning(f"[Database] Model {model_id} not found when getting model info, returning empty portfolio")
                # 返回默认的空持仓信息，避免抛出异常导致交易周期失败
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
            
            # 计算已实现盈亏
            pnl_rows = self.query(f"""
                SELECT COALESCE(SUM(pnl), 0) as total_pnl 
                FROM {self.trades_table}
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
            logger.error(f"[Database] Failed to get portfolio for model {model_id}: {e}")
            raise
    
    def close_position(self, model_id: int, symbol: str, position_side: str = 'LONG'):
        """
        Close position and clean up futures universe if unused
        
        Args:
            model_id: 模型ID
            symbol: 交易对符号（如BTCUSDT）
            position_side: 持仓方向，'LONG'（多）或'SHORT'（空）
        """
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return
            
            normalized_symbol = symbol.upper()
            position_side_upper = position_side.upper()
            if position_side_upper not in ['LONG', 'SHORT']:
                raise ValueError(f"position_side must be 'LONG' or 'SHORT', got: {position_side}")
            
            # 使用 MySQL 的 DELETE FROM 语法
            delete_sql = f"DELETE FROM {self.portfolios_table} WHERE model_id = '{model_uuid}' AND symbol = '{normalized_symbol}' AND position_side = '{position_side_upper}'"
            logger.debug(f"[Database] Executing SQL: {delete_sql}")
            self.command(delete_sql)
            
            # 检查是否还有其他持仓
            remaining_rows = self.query(f"""
                SELECT COUNT(*) as cnt FROM {self.portfolios_table}
                WHERE symbol = '{normalized_symbol}' AND position_amt != 0
            """)
            if remaining_rows and remaining_rows[0][0] == 0:
                # 删除 futures 表中的记录（使用 MySQL 的 DELETE FROM 语法）
                delete_futures_sql = f"DELETE FROM {self.futures_table} WHERE symbol = '{normalized_symbol}'"
                logger.debug(f"[Database] Executing SQL: {delete_futures_sql}")
                self.command(delete_futures_sql)
        except Exception as e:
            logger.error(f"[Database] Failed to close position: {e}")
            raise
    
    # ============ Trade（交易记录）管理方法 ============
    
    def add_trade(self, model_id: int, future: str, signal: str, quantity: float,
              price: float, leverage: int = 1, side: str = 'long', pnl: float = 0, fee: float = 0):
        """Add trade record with fee"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                logger.warning(f"[Database] Model {model_id} not found for trade record")
                return
            
            # 使用 UTC+8 时区时间（北京时间），转换为 naive datetime 存储
            beijing_tz = timezone(timedelta(hours=8))
            current_time = datetime.now(beijing_tz).replace(tzinfo=None)
            
            trade_id = self._generate_id()
            self.insert_rows(
                self.trades_table,
                [[trade_id, model_uuid, future.upper(), signal, quantity, price, leverage, side, pnl, fee, current_time]],
                ["id", "model_id", "future", "signal", "quantity", "price", "leverage", "side", "pnl", "fee", "timestamp"]
            )
        except Exception as e:
            logger.error(f"[Database] Failed to add trade: {e}")
            raise
    
    def get_trades(self, model_id: int, limit: int = 50) -> List[Dict]:
        """Get trade history"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return []
            
            rows = self.query(f"""
                SELECT * FROM {self.trades_table}
                WHERE model_id = '{model_uuid}'
                ORDER BY timestamp DESC
                LIMIT {limit}
            """)
            columns = ["id", "model_id", "future", "signal", "quantity", "price", "leverage", "side", "pnl", "fee", "timestamp"]
            return self._rows_to_dicts(rows, columns)
        except Exception as e:
            logger.error(f"[Database] Failed to get trades for model {model_id}: {e}")
            return []
    
    # ============ Conversation（对话记录）管理方法 ============
    
    def add_conversation(self, model_id: int, user_prompt: str,
                        ai_response: str, cot_trace: str = '', tokens: int = 0):
        """Add conversation record"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                logger.warning(f"[Database] Model {model_id} not found for conversation record")
                return
            
            # 使用 UTC+8 时区时间（北京时间），转换为 naive datetime 存储
            beijing_tz = timezone(timedelta(hours=8))
            current_time = datetime.now(beijing_tz).replace(tzinfo=None)
            
            conv_id = self._generate_id()
            self.insert_rows(
                self.conversations_table,
                [[conv_id, model_uuid, user_prompt, ai_response, cot_trace or '', tokens, current_time]],
                ["id", "model_id", "user_prompt", "ai_response", "cot_trace", "tokens", "timestamp"]
            )
        except Exception as e:
            logger.error(f"[Database] Failed to add conversation: {e}")
            raise
    
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
            logger.error(f"[Database] Failed to add binance trade log: {e}")
            # 不抛出异常，避免影响主流程
    
    def get_conversations(self, model_id: int, limit: int = 20) -> List[Dict]:
        """Get conversation history for a specific model
        
        Args:
            model_id: 模型ID（整数）
            limit: 返回记录数限制，默认20
            
        Returns:
            对话记录列表，只包含指定 model_id 的记录
        """
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                logger.warning(f"[Database] Model {model_id} not found in mapping, returning empty conversations list")
                return []
            
            # 使用参数化查询，确保只查询指定 model_id 的对话记录
            # 按 timestamp DESC 排序，确保返回最新的对话记录
            rows = self.query(f"""
                SELECT * FROM `{self.conversations_table}`
                WHERE model_id = %s
                ORDER BY timestamp DESC
                LIMIT %s
            """, (model_uuid, limit))
            
            columns = ["id", "model_id", "user_prompt", "ai_response", "cot_trace", "timestamp"]
            results = self._rows_to_dicts(rows, columns)
            
            # 额外验证：确保返回的所有记录都属于指定的 model_id（双重保险）
            filtered_results = []
            for result in results:
                if result.get('model_id') == model_uuid:
                    filtered_results.append(result)
                else:
                    logger.warning(f"[Database] Found conversation with mismatched model_id: expected {model_uuid}, got {result.get('model_id')}")
            
            # 再次按 timestamp 降序排序，确保即使数据库返回顺序有问题，也能正确排序（双重保险）
            filtered_results.sort(key=lambda x: x.get('timestamp') or '', reverse=True)
            
            logger.debug(f"[Database] Retrieved {len(filtered_results)} conversations for model {model_id} (limit={limit}), sorted by timestamp DESC")
            return filtered_results
        except Exception as e:
            logger.error(f"[Database] Failed to get conversations for model {model_id}: {e}")
            return []
    
    # ============ Account Value（账户价值）管理方法 ============
    
    def record_account_value(self, model_id: int, balance: float,
                            available_balance: float, cross_wallet_balance: float,
                            account_alias: str = '', cross_un_pnl: float = 0.0):
        """
        Record account value snapshot
        
        Args:
            model_id: 模型ID
            balance: 总余额
            available_balance: 下单可用余额
            cross_wallet_balance: 全仓余额
            account_alias: 账户唯一识别码（可选，默认空字符串）
            cross_un_pnl: 全仓持仓未实现盈亏（可选，默认0.0）
        """
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                logger.warning(f"[Database] Model {model_id} not found for account value record")
                return
            
            av_id = self._generate_id()
            self.insert_rows(
                self.account_values_table,
                [[av_id, model_uuid, account_alias, balance, available_balance, cross_wallet_balance, cross_un_pnl, datetime.now(timezone.utc)]],
                ["id", "model_id", "account_alias", "balance", "available_balance", "cross_wallet_balance", "cross_un_pnl", "timestamp"]
            )
        except Exception as e:
            logger.error(f"[Database] Failed to record account value: {e}")
            raise
    
    def get_account_value_history(self, model_id: int, limit: int = 100) -> List[Dict]:
        """
        Get account value history
        
        Returns:
            账户价值历史记录列表，包含新字段名：
            - accountAlias: 账户唯一识别码
            - balance: 总余额
            - availableBalance: 下单可用余额
            - crossWalletBalance: 全仓余额
            - crossUnPnl: 全仓持仓未实现盈亏
        """
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return []
            
            rows = self.query(f"""
                SELECT id, model_id, account_alias, balance, available_balance, 
                       cross_wallet_balance, cross_un_pnl, timestamp
                FROM {self.account_values_table}
                WHERE model_id = '{model_uuid}'
                ORDER BY timestamp DESC
                LIMIT {limit}
            """)
            columns = ["id", "model_id", "account_alias", "balance", "available_balance", 
                      "cross_wallet_balance", "cross_un_pnl", "timestamp"]
            results = self._rows_to_dicts(rows, columns)
            
            # 转换为驼峰命名格式
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "id": result.get("id"),
                    "model_id": result.get("model_id"),
                    "accountAlias": result.get("account_alias", ""),
                    "balance": result.get("balance", 0.0),
                    "availableBalance": result.get("available_balance", 0.0),
                    "crossWalletBalance": result.get("cross_wallet_balance", 0.0),
                    "crossUnPnl": result.get("cross_un_pnl", 0.0),
                    "timestamp": result.get("timestamp")
                })
            return formatted_results
        except Exception as e:
            logger.error(f"[Database] Failed to get account value history for model {model_id}: {e}")
            return []
    
    def get_aggregated_account_value_history(self, limit: int = 100) -> List[Dict]:
        """
        Get aggregated account value history across all models
        
        Returns:
            聚合账户价值历史记录列表，包含新字段名：
            - balance: 总余额（聚合）
            - availableBalance: 下单可用余额（聚合）
            - crossWalletBalance: 全仓余额（聚合）
            - crossUnPnl: 全仓持仓未实现盈亏（聚合）
        """
        try:
            # MySQL 日期函数：DATE() 和 HOUR()
            rows = self.query(f"""
                SELECT 
                    timestamp,
                    SUM(balance) as balance,
                    SUM(available_balance) as available_balance,
                    SUM(cross_wallet_balance) as cross_wallet_balance,
                    SUM(cross_un_pnl) as cross_un_pnl,
                    COUNT(DISTINCT model_id) as model_count
                FROM (
                    SELECT 
                        timestamp,
                        balance,
                        available_balance,
                        cross_wallet_balance,
                        cross_un_pnl,
                        model_id,
                        ROW_NUMBER() OVER (PARTITION BY model_id, DATE(timestamp) ORDER BY timestamp DESC) as rn
                    FROM {self.account_values_table}
                ) grouped
                WHERE rn <= 10
                GROUP BY DATE(timestamp), HOUR(timestamp), timestamp
                ORDER BY timestamp DESC
                LIMIT {limit}
            """)
            columns = ["timestamp", "balance", "available_balance", "cross_wallet_balance", "cross_un_pnl", "model_count"]
            results = self._rows_to_dicts(rows, columns)
            
            # 转换为驼峰命名格式
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "timestamp": result.get("timestamp"),
                    "balance": result.get("balance", 0.0),
                    "availableBalance": result.get("available_balance", 0.0),
                    "crossWalletBalance": result.get("cross_wallet_balance", 0.0),
                    "crossUnPnl": result.get("cross_un_pnl", 0.0),
                    "model_count": result.get("model_count")
                })
            return formatted_results
        except Exception as e:
            logger.error(f"[Database] Failed to get aggregated account value history: {e}")
            return []
    
    def get_multi_model_chart_data(self, limit: int = 100) -> List[Dict]:
        """
        Get chart data for all models to display in multi-line chart
        
        Returns:
            图表数据列表，使用新字段名balance作为value
        """
        try:
            # 获取所有 models
            models = self.get_all_models()
            chart_data = []
            
            for model in models:
                model_id = model['id']
                model_name = model['name']
                history = self.get_account_value_history(model_id, limit)
                
                if history:
                    model_data = {
                        'model_id': model_id,
                        'model_name': model_name,
                        'data': [
                            {
                                'timestamp': row['timestamp'],
                                'value': row['balance']  # 使用新字段名balance
                            } for row in history
                        ]
                    }
                    chart_data.append(model_data)
            
            return chart_data
        except Exception as e:
            logger.error(f"[Database] Failed to get multi-model chart data: {e}")
            return []
    
    # ============ Prompt（提示词）管理方法 ============
    
    def get_model_prompt(self, model_id: int) -> Optional[Dict]:
        """Get model prompt configuration"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
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
            result['model_id'] = model_id  # 转换为 int ID
            return result
        except Exception as e:
            logger.error(f"[Database] Failed to get model prompt for model {model_id}: {e}")
            return None
    
    def upsert_model_prompt(self, model_id: int, buy_prompt: Optional[str], sell_prompt: Optional[str]) -> bool:
        """Insert or update model prompt configuration"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return False
            
            # MySQL使用 INSERT ... ON DUPLICATE KEY UPDATE
            prompt_id = self._generate_id()
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
            logger.error(f"[Database] Failed to upsert model prompt for model {model_id}: {e}")
            return False
    
    # ============ Futures（合约配置）管理方法 ============
    
    def get_futures(self) -> List[Dict]:
        """Get all futures configurations"""
        try:
            rows = self.query(f"""
                SELECT * FROM {self.futures_table}
                ORDER BY sort_order DESC, created_at DESC, symbol ASC
            """)
            columns = ["id", "symbol", "contract_symbol", "name", "exchange", "link", "sort_order", "created_at"]
            results = self._rows_to_dicts(rows, columns)
            # 转换 ID 为 int 以保持与前端兼容性（类似 get_all_providers 和 get_all_models）
            for result in results:
                if result.get('id'):
                    result['id'] = self._uuid_to_int(result['id'])
            return results
        except Exception as e:
            logger.error(f"[Database] Failed to get futures: {e}")
            return []
    
    def add_future(self, symbol: str, contract_symbol: str, name: str,
                   exchange: str = 'BINANCE_FUTURES', link: Optional[str] = None, sort_order: int = 0) -> int:
        """Add new future configuration"""
        future_id = self._generate_id()
        try:
            self.insert_rows(
                self.futures_table,
                [[future_id, symbol.upper(), contract_symbol.upper(), name, exchange.upper(), (link or '').strip() or '', sort_order, datetime.now(timezone.utc)]],
                ["id", "symbol", "contract_symbol", "name", "exchange", "link", "sort_order", "created_at"]
            )
            return self._uuid_to_int(future_id)
        except Exception as e:
            logger.error(f"[Database] Failed to add future: {e}")
            raise
    
    def upsert_future(self, symbol: str, contract_symbol: str, name: str,
                     exchange: str = 'BINANCE_FUTURES', link: Optional[str] = None, sort_order: int = 0):
        """Insert or update a futures configuration identified by symbol"""
        try:
            # MySQL 使用唯一索引 (uk_symbol) 和 INSERT 实现去重
            future_id = self._generate_id()
            self.insert_rows(
                self.futures_table,
                [[future_id, symbol.upper(), contract_symbol.upper(), name, exchange.upper(), (link or '').strip() or '', sort_order, datetime.now(timezone.utc)]],
                ["id", "symbol", "contract_symbol", "name", "exchange", "link", "sort_order", "created_at"]
            )
        except Exception as e:
            logger.error(f"[Database] Failed to upsert future: {e}")
            raise
    
    def delete_future(self, future_id: int):
        """Delete future configuration"""
        try:
            # 查找匹配的 future
            futures = self.get_futures()
            for future in futures:
                if self._uuid_to_int(future['id']) == future_id:
                    actual_id = future['id']
                    self.command(f"DELETE FROM {self.futures_table} WHERE id = '{actual_id}'")
                    return
            logger.warning(f"[Database] Future {future_id} not found for deletion")
        except Exception as e:
            logger.error(f"[Database] Failed to delete future {future_id}: {e}")
            raise
    
    # ============ Futures（合约配置）管理方法 ============
    
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
    
    def get_future_symbols(self) -> List[str]:
        """Get list of future symbols"""
        return [future['symbol'] for future in self.get_future_configs()]
    
    # ============ Model Futures（模型合约关联）管理方法 ============
    
    def add_model_future(self, model_id: int, symbol: str, contract_symbol: str,
                         name: str, exchange: str = 'BINANCE_FUTURES',
                         link: Optional[str] = None, sort_order: int = 0) -> int:
        """Add model-specific future configuration"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                raise ValueError(f"Model {model_id} not found")
            
            mf_id = self._generate_id()
            self.insert_rows(
                self.model_futures_table,
                [[mf_id, model_uuid, symbol.upper(), contract_symbol.upper(), name, exchange.upper(), (link or '').strip() or '', sort_order]],
                ["id", "model_id", "symbol", "contract_symbol", "name", "exchange", "link", "sort_order"]
            )
            return self._uuid_to_int(mf_id)
        except Exception as e:
            logger.error(f"[Database] Failed to add model future: {e}")
            raise
    
    def delete_model_future(self, model_id: int, symbol: str):
        """Delete model-specific future configuration"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return
            
            self.command(f"DELETE FROM {self.model_futures_table} WHERE model_id = '{model_uuid}' AND symbol = '{symbol.upper()}'")
        except Exception as e:
            logger.error(f"[Database] Failed to delete model future: {e}")
            raise
    
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
            model_mapping = self._get_model_id_mapping()
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
            
            model_mapping = self._get_model_id_mapping()
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
    
    def clear_model_futures(self, model_id: int):
        """Clear all model-specific future configurations"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return
            
            self.command(f"DELETE FROM {self.model_futures_table} WHERE model_id = '{model_uuid}'")
        except Exception as e:
            logger.error(f"[Database] Failed to clear model futures for model {model_id}: {e}")
            raise
    
    # ============ Settings（系统设置）管理方法 ============
    
    def get_settings(self) -> Dict:
        """Get system settings"""
        try:
            rows = self.query(f"""
                SELECT trading_frequency_minutes, trading_fee_rate, show_system_prompt, conversation_limit
                FROM {self.settings_table}
                ORDER BY updated_at DESC
                LIMIT 1
            """)
            
            if rows:
                columns = ["trading_frequency_minutes", "trading_fee_rate", "show_system_prompt", "conversation_limit"]
                result = self._row_to_dict(rows[0], columns)
                return {
                    'trading_frequency_minutes': int(result['trading_frequency_minutes']),
                    'trading_fee_rate': float(result['trading_fee_rate']),
                    'show_system_prompt': int(result.get('show_system_prompt', 0)),
                    'conversation_limit': int(result.get('conversation_limit', 5))
                }
            else:
                # 返回默认设置
                return {
                    'trading_frequency_minutes': 5,
                    'trading_fee_rate': 0.001,
                    'show_system_prompt': 0,
                    'conversation_limit': 5
                }
        except Exception as e:
            logger.error(f"[Database] Failed to get settings: {e}")
            return {
                'trading_frequency_minutes': 5,
                'trading_fee_rate': 0.001,
                'show_system_prompt': 0,
                'conversation_limit': 5
            }
    
    def update_settings(self, trading_frequency_minutes: int, trading_fee_rate: float,
                        show_system_prompt: int, conversation_limit: int = 5) -> bool:
        """Update system settings"""
        try:
            # 使用 UTC+8 时区时间（北京时间），转换为 naive datetime 存储
            beijing_tz = timezone(timedelta(hours=8))
            current_time = datetime.now(beijing_tz).replace(tzinfo=None)
            
            # 验证conversation_limit值
            if not isinstance(conversation_limit, int) or conversation_limit < 1:
                logger.warning(f"[Database] Invalid conversation_limit value: {conversation_limit}, using default 5")
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
                    SET trading_frequency_minutes = %s,
                        trading_fee_rate = %s,
                        show_system_prompt = %s,
                        conversation_limit = %s,
                        updated_at = %s
                    WHERE id = %s
                """, (trading_frequency_minutes, trading_fee_rate, show_system_prompt, conversation_limit, current_time, settings_id))
            else:
                # 如果不存在记录，使用 INSERT 插入
                settings_id = self._generate_id()
                self.insert_rows(
                    self.settings_table,
                    [[settings_id, trading_frequency_minutes, trading_fee_rate, show_system_prompt, conversation_limit, current_time, current_time]],
                    ["id", "trading_frequency_minutes", "trading_fee_rate", "show_system_prompt", "conversation_limit", "created_at", "updated_at"]
                )
            return True
        except Exception as e:
            logger.error(f"[Database] Failed to update settings: {e}")
            return False
    
    
    # ==================================================================
    # Accounts Management (账户信息管理) - 已废弃，accounts表已删除
    # 账户管理功能已迁移到 AccountDatabase 类（使用 account_asset 表）
    # ==================================================================
    
    # ============ Account Asset（账户资产）管理方法 ============
    
    def add_account_asset(self, account_alias: str,
                         total_initial_margin: float = 0.0,
                         total_maint_margin: float = 0.0,
                         total_wallet_balance: float = 0.0,
                         total_unrealized_profit: float = 0.0,
                         total_margin_balance: float = 0.0,
                         total_position_initial_margin: float = 0.0,
                         total_open_order_initial_margin: float = 0.0,
                         total_cross_wallet_balance: float = 0.0,
                         total_cross_un_pnl: float = 0.0,
                         available_balance: float = 0.0,
                         max_withdraw_amount: float = 0.0,
                         update_time: int = None) -> bool:
        """
        添加或更新账户资产信息
        
        Args:
            account_alias: 账户唯一识别码
            total_initial_margin: 当前所需起始保证金总额（仅计算USDT资产）
            total_maint_margin: 维持保证金总额（仅计算USDT资产）
            total_wallet_balance: 账户总余额（仅计算USDT资产）
            total_unrealized_profit: 持仓未实现盈亏总额（仅计算USDT资产）
            total_margin_balance: 保证金总余额（仅计算USDT资产）
            total_position_initial_margin: 持仓所需起始保证金（基于最新标记价格，仅计算USDT资产）
            total_open_order_initial_margin: 当前挂单所需起始保证金（基于最新标记价格，仅计算USDT资产）
            total_cross_wallet_balance: 全仓账户余额（仅计算USDT资产）
            total_cross_un_pnl: 全仓持仓未实现盈亏总额（仅计算USDT资产）
            available_balance: 可用余额（仅计算USDT资产）
            max_withdraw_amount: 最大可转出余额（仅计算USDT资产）
            update_time: 更新时间（毫秒时间戳，如果为None则使用当前时间戳）
            
        Returns:
            操作是否成功
        """
        try:
            if update_time is None:
                import time
                update_time = int(time.time() * 1000)
            
            self.insert_rows(
                self.account_asset_table,
                [[account_alias, total_initial_margin, total_maint_margin, total_wallet_balance,
                  total_unrealized_profit, total_margin_balance, total_position_initial_margin,
                  total_open_order_initial_margin, total_cross_wallet_balance, total_cross_un_pnl,
                  available_balance, max_withdraw_amount, update_time, datetime.now(timezone.utc)]],
                ["account_alias", "total_initial_margin", "total_maint_margin", "total_wallet_balance",
                 "total_unrealized_profit", "total_margin_balance", "total_position_initial_margin",
                 "total_open_order_initial_margin", "total_cross_wallet_balance", "total_cross_un_pnl",
                 "available_balance", "max_withdraw_amount", "update_time", "created_at"]
            )
            logger.debug(f"[Database] Added/Updated account asset: {account_alias}")
            return True
        except Exception as e:
            logger.error(f"[Database] Failed to add account asset {account_alias}: {e}")
            raise
    
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
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
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
            logger.error(f"[Database] Failed to get latest account value for model {model_id}: {e}")
            return None
    
    def get_all_account_assets(self, account_alias: str = None) -> List[Dict]:
        """
        获取所有账户资产信息或指定账户的资产历史
        
        Args:
            account_alias: 账户唯一识别码（可选，如果指定则只返回该账户的资产历史）
            
        Returns:
            账户资产信息列表
        """
        try:
            if account_alias:
                rows = self.query(f"""
                    SELECT account_alias, total_initial_margin, total_maint_margin, total_wallet_balance,
                           total_unrealized_profit, total_margin_balance, total_position_initial_margin,
                           total_open_order_initial_margin, total_cross_wallet_balance, total_cross_un_pnl,
                           available_balance, max_withdraw_amount, update_time, created_at
                    FROM {self.account_asset_table}
                    WHERE account_alias = '{account_alias}'
                    ORDER BY update_time DESC
                """)
            else:
                rows = self.query(f"""
                    SELECT account_alias, total_initial_margin, total_maint_margin, total_wallet_balance,
                           total_unrealized_profit, total_margin_balance, total_position_initial_margin,
                           total_open_order_initial_margin, total_cross_wallet_balance, total_cross_un_pnl,
                           available_balance, max_withdraw_amount, update_time, created_at
                    FROM {self.account_asset_table}
                    ORDER BY account_alias ASC, update_time DESC
                """)
            
            columns = ["account_alias", "total_initial_margin", "total_maint_margin", "total_wallet_balance",
                      "total_unrealized_profit", "total_margin_balance", "total_position_initial_margin",
                      "total_open_order_initial_margin", "total_cross_wallet_balance", "total_cross_un_pnl",
                      "available_balance", "max_withdraw_amount", "update_time", "created_at"]
            results = self._rows_to_dicts(rows, columns)
            
            # 转换为驼峰命名格式
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "accountAlias": result["account_alias"],
                    "totalInitialMargin": str(result["total_initial_margin"]),
                    "totalMaintMargin": str(result["total_maint_margin"]),
                    "totalWalletBalance": str(result["total_wallet_balance"]),
                    "totalUnrealizedProfit": str(result["total_unrealized_profit"]),
                    "totalMarginBalance": str(result["total_margin_balance"]),
                    "totalPositionInitialMargin": str(result["total_position_initial_margin"]),
                    "totalOpenOrderInitialMargin": str(result["total_open_order_initial_margin"]),
                    "totalCrossWalletBalance": str(result["total_cross_wallet_balance"]),
                    "totalCrossUnPnl": str(result["total_cross_un_pnl"]),
                    "availableBalance": str(result["available_balance"]),
                    "maxWithdrawAmount": str(result["max_withdraw_amount"]),
                    "updateTime": result["update_time"]
                })
            
            return formatted_results
        except Exception as e:
            logger.error(f"[Database] Failed to get all account assets: {e}")
            return []
    
    def update_account_asset(self, account_alias: str,
                            total_initial_margin: float = None,
                            total_maint_margin: float = None,
                            total_wallet_balance: float = None,
                            total_unrealized_profit: float = None,
                            total_margin_balance: float = None,
                            total_position_initial_margin: float = None,
                            total_open_order_initial_margin: float = None,
                            total_cross_wallet_balance: float = None,
                            total_cross_un_pnl: float = None,
                            available_balance: float = None,
                            max_withdraw_amount: float = None,
                            update_time: int = None) -> bool:
        """
        更新账户资产信息（部分字段）
        
        Args:
            account_alias: 账户唯一识别码
            total_initial_margin: 当前所需起始保证金总额（可选）
            total_maint_margin: 维持保证金总额（可选）
            total_wallet_balance: 账户总余额（可选）
            total_unrealized_profit: 持仓未实现盈亏总额（可选）
            total_margin_balance: 保证金总余额（可选）
            total_position_initial_margin: 持仓所需起始保证金（可选）
            total_open_order_initial_margin: 当前挂单所需起始保证金（可选）
            total_cross_wallet_balance: 全仓账户余额（可选）
            total_cross_un_pnl: 全仓持仓未实现盈亏总额（可选）
            available_balance: 可用余额（可选）
            max_withdraw_amount: 最大可转出余额（可选）
            update_time: 更新时间（可选，如果不提供则使用当前时间戳）
            
        Returns:
            操作是否成功
        """
        try:
            # 先获取现有账户资产信息
            existing = self.get_account_asset(account_alias)
            if not existing:
                logger.warning(f"[Database] Account asset {account_alias} not found for update")
                return False
            
            # 使用提供的值或保留现有值
            final_total_initial_margin = total_initial_margin if total_initial_margin is not None else float(existing["totalInitialMargin"])
            final_total_maint_margin = total_maint_margin if total_maint_margin is not None else float(existing["totalMaintMargin"])
            final_total_wallet_balance = total_wallet_balance if total_wallet_balance is not None else float(existing["totalWalletBalance"])
            final_total_unrealized_profit = total_unrealized_profit if total_unrealized_profit is not None else float(existing["totalUnrealizedProfit"])
            final_total_margin_balance = total_margin_balance if total_margin_balance is not None else float(existing["totalMarginBalance"])
            final_total_position_initial_margin = total_position_initial_margin if total_position_initial_margin is not None else float(existing["totalPositionInitialMargin"])
            final_total_open_order_initial_margin = total_open_order_initial_margin if total_open_order_initial_margin is not None else float(existing["totalOpenOrderInitialMargin"])
            final_total_cross_wallet_balance = total_cross_wallet_balance if total_cross_wallet_balance is not None else float(existing["totalCrossWalletBalance"])
            final_total_cross_un_pnl = total_cross_un_pnl if total_cross_un_pnl is not None else float(existing["totalCrossUnPnl"])
            final_available_balance = available_balance if available_balance is not None else float(existing["availableBalance"])
            final_max_withdraw_amount = max_withdraw_amount if max_withdraw_amount is not None else float(existing["maxWithdrawAmount"])
            final_update_time = update_time if update_time is not None else existing["updateTime"]
            
            # 使用 add_account_asset 方法（MySQL 使用 INSERT ... ON DUPLICATE KEY UPDATE 实现去重）
            return self.add_account_asset(
                account_alias=account_alias,
                total_initial_margin=final_total_initial_margin,
                total_maint_margin=final_total_maint_margin,
                total_wallet_balance=final_total_wallet_balance,
                total_unrealized_profit=final_total_unrealized_profit,
                total_margin_balance=final_total_margin_balance,
                total_position_initial_margin=final_total_position_initial_margin,
                total_open_order_initial_margin=final_total_open_order_initial_margin,
                total_cross_wallet_balance=final_total_cross_wallet_balance,
                total_cross_un_pnl=final_total_cross_un_pnl,
                available_balance=final_available_balance,
                max_withdraw_amount=final_max_withdraw_amount,
                update_time=final_update_time
            )
        except Exception as e:
            logger.error(f"[Database] Failed to update account asset {account_alias}: {e}")
            return False
    
    def delete_account_asset(self, account_alias: str) -> bool:
        """
        删除账户资产信息
        
        Args:
            account_alias: 账户唯一识别码
            
        Returns:
            操作是否成功
        """
        try:
            self.command(f"DELETE FROM {self.account_asset_table} WHERE account_alias = '{account_alias}'")
            logger.debug(f"[Database] Deleted account asset: {account_alias}")
            return True
        except Exception as e:
            logger.error(f"[Database] Failed to delete account asset {account_alias}: {e}")
            return False
    
    # ============ Asset（资产明细）管理方法 ============
    
    def add_asset(self, account_alias: str, asset: str,
                 wallet_balance: float = 0.0,
                 unrealized_profit: float = 0.0,
                 margin_balance: float = 0.0,
                 maint_margin: float = 0.0,
                 initial_margin: float = 0.0,
                 position_initial_margin: float = 0.0,
                 open_order_initial_margin: float = 0.0,
                 cross_wallet_balance: float = 0.0,
                 cross_un_pnl: float = 0.0,
                 available_balance: float = 0.0,
                 max_withdraw_amount: float = 0.0,
                 update_time: int = None) -> bool:
        """
        添加或更新资产信息
        
        Args:
            account_alias: 账户唯一识别码
            asset: 资产类型（如USDT）
            wallet_balance: 余额
            unrealized_profit: 未实现盈亏
            margin_balance: 保证金余额
            maint_margin: 维持保证金
            initial_margin: 当前所需起始保证金
            position_initial_margin: 持仓所需起始保证金（基于最新标记价格）
            open_order_initial_margin: 当前挂单所需起始保证金（基于最新标记价格）
            cross_wallet_balance: 全仓账户余额
            cross_un_pnl: 全仓持仓未实现盈亏
            available_balance: 可用余额
            max_withdraw_amount: 最大可转出余额
            update_time: 更新时间（毫秒时间戳，如果为None则使用当前时间戳）
            
        Returns:
            操作是否成功
        """
        try:
            if update_time is None:
                import time
                update_time = int(time.time() * 1000)
            
            self.insert_rows(
                self.asset_table,
                [[account_alias, asset, wallet_balance, unrealized_profit, margin_balance,
                  maint_margin, initial_margin, position_initial_margin, open_order_initial_margin,
                  cross_wallet_balance, cross_un_pnl, available_balance, max_withdraw_amount,
                  update_time, datetime.now(timezone.utc)]],
                ["account_alias", "asset", "wallet_balance", "unrealized_profit", "margin_balance",
                 "maint_margin", "initial_margin", "position_initial_margin", "open_order_initial_margin",
                 "cross_wallet_balance", "cross_un_pnl", "available_balance", "max_withdraw_amount",
                 "update_time", "created_at"]
            )
            logger.debug(f"[Database] Added/Updated asset: {account_alias}, {asset}")
            return True
        except Exception as e:
            logger.error(f"[Database] Failed to add asset {account_alias}/{asset}: {e}")
            raise
    
    def get_asset(self, account_alias: str, asset: str) -> Optional[Dict]:
        """
        获取资产信息（最新记录）
        
        Args:
            account_alias: 账户唯一识别码
            asset: 资产类型
            
        Returns:
            资产信息字典，如果不存在则返回None
        """
        try:
            rows = self.query(f"""
                SELECT account_alias, asset, wallet_balance, unrealized_profit, margin_balance,
                       maint_margin, initial_margin, position_initial_margin, open_order_initial_margin,
                       cross_wallet_balance, cross_un_pnl, available_balance, max_withdraw_amount,
                       update_time, created_at
                FROM {self.asset_table}
                WHERE account_alias = '{account_alias}' AND asset = '{asset}'
                ORDER BY update_time DESC
                LIMIT 1
            """)
            
            if not rows:
                return None
            
            columns = ["account_alias", "asset", "wallet_balance", "unrealized_profit", "margin_balance",
                      "maint_margin", "initial_margin", "position_initial_margin", "open_order_initial_margin",
                      "cross_wallet_balance", "cross_un_pnl", "available_balance", "max_withdraw_amount",
                      "update_time", "created_at"]
            result = self._row_to_dict(rows[0], columns)
            
            # 转换为驼峰命名格式
            return {
                "accountAlias": result["account_alias"],
                "asset": result["asset"],
                "walletBalance": str(result["wallet_balance"]),
                "unrealizedProfit": str(result["unrealized_profit"]),
                "marginBalance": str(result["margin_balance"]),
                "maintMargin": str(result["maint_margin"]),
                "initialMargin": str(result["initial_margin"]),
                "positionInitialMargin": str(result["position_initial_margin"]),
                "openOrderInitialMargin": str(result["open_order_initial_margin"]),
                "crossWalletBalance": str(result["cross_wallet_balance"]),
                "crossUnPnl": str(result["cross_un_pnl"]),
                "availableBalance": str(result["available_balance"]),
                "maxWithdrawAmount": str(result["max_withdraw_amount"]),
                "updateTime": result["update_time"]
            }
        except Exception as e:
            logger.error(f"[Database] Failed to get asset {account_alias}/{asset}: {e}")
            return None
    
    def get_all_assets(self, account_alias: str = None) -> List[Dict]:
        """
        获取所有资产信息或指定账户的所有资产
        
        Args:
            account_alias: 账户唯一识别码（可选，如果指定则只返回该账户的所有资产）
            
        Returns:
            资产信息列表
        """
        try:
            if account_alias:
                rows = self.query(f"""
                    SELECT account_alias, asset, wallet_balance, unrealized_profit, margin_balance,
                           maint_margin, initial_margin, position_initial_margin, open_order_initial_margin,
                           cross_wallet_balance, cross_un_pnl, available_balance, max_withdraw_amount,
                           update_time, created_at
                    FROM {self.asset_table}
                    WHERE account_alias = '{account_alias}'
                    ORDER BY asset ASC, update_time DESC
                """)
            else:
                rows = self.query(f"""
                    SELECT account_alias, asset, wallet_balance, unrealized_profit, margin_balance,
                           maint_margin, initial_margin, position_initial_margin, open_order_initial_margin,
                           cross_wallet_balance, cross_un_pnl, available_balance, max_withdraw_amount,
                           update_time, created_at
                    FROM {self.asset_table}
                    ORDER BY account_alias ASC, asset ASC, update_time DESC
                """)
            
            columns = ["account_alias", "asset", "wallet_balance", "unrealized_profit", "margin_balance",
                      "maint_margin", "initial_margin", "position_initial_margin", "open_order_initial_margin",
                      "cross_wallet_balance", "cross_un_pnl", "available_balance", "max_withdraw_amount",
                      "update_time", "created_at"]
            results = self._rows_to_dicts(rows, columns)
            
            # 转换为驼峰命名格式
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "accountAlias": result["account_alias"],
                    "asset": result["asset"],
                    "walletBalance": str(result["wallet_balance"]),
                    "unrealizedProfit": str(result["unrealized_profit"]),
                    "marginBalance": str(result["margin_balance"]),
                    "maintMargin": str(result["maint_margin"]),
                    "initialMargin": str(result["initial_margin"]),
                    "positionInitialMargin": str(result["position_initial_margin"]),
                    "openOrderInitialMargin": str(result["open_order_initial_margin"]),
                    "crossWalletBalance": str(result["cross_wallet_balance"]),
                    "crossUnPnl": str(result["cross_un_pnl"]),
                    "availableBalance": str(result["available_balance"]),
                    "maxWithdrawAmount": str(result["max_withdraw_amount"]),
                    "updateTime": result["update_time"]
                })
            
            return formatted_results
        except Exception as e:
            logger.error(f"[Database] Failed to get all assets: {e}")
            return []
    
    def update_asset(self, account_alias: str, asset: str,
                    wallet_balance: float = None,
                    unrealized_profit: float = None,
                    margin_balance: float = None,
                    maint_margin: float = None,
                    initial_margin: float = None,
                    position_initial_margin: float = None,
                    open_order_initial_margin: float = None,
                    cross_wallet_balance: float = None,
                    cross_un_pnl: float = None,
                    available_balance: float = None,
                    max_withdraw_amount: float = None,
                    update_time: int = None) -> bool:
        """
        更新资产信息（部分字段）
        
        Args:
            account_alias: 账户唯一识别码
            asset: 资产类型
            wallet_balance: 余额（可选）
            unrealized_profit: 未实现盈亏（可选）
            margin_balance: 保证金余额（可选）
            maint_margin: 维持保证金（可选）
            initial_margin: 当前所需起始保证金（可选）
            position_initial_margin: 持仓所需起始保证金（可选）
            open_order_initial_margin: 当前挂单所需起始保证金（可选）
            cross_wallet_balance: 全仓账户余额（可选）
            cross_un_pnl: 全仓持仓未实现盈亏（可选）
            available_balance: 可用余额（可选）
            max_withdraw_amount: 最大可转出余额（可选）
            update_time: 更新时间（可选，如果不提供则使用当前时间戳）
            
        Returns:
            操作是否成功
        """
        try:
            # 先获取现有资产信息
            existing = self.get_asset(account_alias, asset)
            if not existing:
                logger.warning(f"[Database] Asset {account_alias}/{asset} not found for update")
                return False
            
            # 使用提供的值或保留现有值
            final_wallet_balance = wallet_balance if wallet_balance is not None else float(existing["walletBalance"])
            final_unrealized_profit = unrealized_profit if unrealized_profit is not None else float(existing["unrealizedProfit"])
            final_margin_balance = margin_balance if margin_balance is not None else float(existing["marginBalance"])
            final_maint_margin = maint_margin if maint_margin is not None else float(existing["maintMargin"])
            final_initial_margin = initial_margin if initial_margin is not None else float(existing["initialMargin"])
            final_position_initial_margin = position_initial_margin if position_initial_margin is not None else float(existing["positionInitialMargin"])
            final_open_order_initial_margin = open_order_initial_margin if open_order_initial_margin is not None else float(existing["openOrderInitialMargin"])
            final_cross_wallet_balance = cross_wallet_balance if cross_wallet_balance is not None else float(existing["crossWalletBalance"])
            final_cross_un_pnl = cross_un_pnl if cross_un_pnl is not None else float(existing["crossUnPnl"])
            final_available_balance = available_balance if available_balance is not None else float(existing["availableBalance"])
            final_max_withdraw_amount = max_withdraw_amount if max_withdraw_amount is not None else float(existing["maxWithdrawAmount"])
            final_update_time = update_time if update_time is not None else existing["updateTime"]
            
            # 使用 add_asset 方法（MySQL 使用主键 (account_alias, asset) 和 INSERT 实现去重）
            return self.add_asset(
                account_alias=account_alias,
                asset=asset,
                wallet_balance=final_wallet_balance,
                unrealized_profit=final_unrealized_profit,
                margin_balance=final_margin_balance,
                maint_margin=final_maint_margin,
                initial_margin=final_initial_margin,
                position_initial_margin=final_position_initial_margin,
                open_order_initial_margin=final_open_order_initial_margin,
                cross_wallet_balance=final_cross_wallet_balance,
                cross_un_pnl=final_cross_un_pnl,
                available_balance=final_available_balance,
                max_withdraw_amount=final_max_withdraw_amount,
                update_time=final_update_time
            )
        except Exception as e:
            logger.error(f"[Database] Failed to update asset {account_alias}/{asset}: {e}")
            return False
    
    def delete_asset(self, account_alias: str, asset: str = None) -> bool:
        """
        删除资产信息
        
        Args:
            account_alias: 账户唯一识别码
            asset: 资产类型（可选，如果指定则只删除该资产的信息，否则删除该账户的所有资产信息）
            
        Returns:
            操作是否成功
        """
        try:
            if asset:
                self.command(f"DELETE FROM {self.asset_table} WHERE account_alias = '{account_alias}' AND asset = '{asset}'")
                logger.debug(f"[Database] Deleted asset: {account_alias}, {asset}")
            else:
                self.command(f"DELETE FROM {self.asset_table} WHERE account_alias = '{account_alias}'")
                logger.debug(f"[Database] Deleted all assets for: {account_alias}")
            return True
        except Exception as e:
            logger.error(f"[Database] Failed to delete asset {account_alias}/{asset}: {e}")
            return False

