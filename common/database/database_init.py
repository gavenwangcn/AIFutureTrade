"""
数据库表初始化模块

本模块包含所有数据库表的创建逻辑，从 database_basic.py 中抽离出来。
统一管理所有表的 DDL 语句，便于维护和版本控制。

主要功能：
- 业务表初始化：providers, models, portfolios, trades 等
    - 市场数据表初始化：market_tickers 等
- 统一的初始化接口：init_database_tables() 和 init_market_tables()
- 表名定义：所有业务表的表名常量
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Callable, Any

logger = logging.getLogger(__name__)

# ============ 表名定义 ============
# 所有业务表的表名常量，统一管理
PROVIDERS_TABLE = "providers"
MODELS_TABLE = "models"
PORTFOLIOS_TABLE = "portfolios"
TRADES_TABLE = "trades"
CONVERSATIONS_TABLE = "conversations"
ACCOUNT_VALUES_TABLE = "account_values"
ACCOUNT_VALUE_HISTORYS_TABLE = "account_value_historys"
SETTINGS_TABLE = "settings"
MODEL_PROMPTS_TABLE = "model_prompts"
MODEL_FUTURES_TABLE = "model_futures"
FUTURES_TABLE = "futures"
ACCOUNT_ASSET_TABLE = "account_asset"
ASSET_TABLE = "asset"
BINANCE_TRADE_LOGS_TABLE = "binance_trade_logs"
STRATEGYS_TABLE = "strategys"
MODEL_STRATEGY_TABLE = "model_strategy"
STRATEGY_DECISIONS_TABLE = "strategy_decisions"
MARKET_TICKER_TABLE = "24_market_tickers"


class DatabaseInitializer:
    """
    数据库表初始化器
    
    封装所有表的创建逻辑，可以被 Database 和 MarketTickersDatabase 类使用。
    """
    
    def __init__(self, command_func: Callable[[str], Any]):
        """
        初始化数据库初始化器
        
        Args:
            command_func: 执行SQL命令的函数，接受SQL字符串作为参数
        """
        self.command = command_func
    
    # ============ 业务表初始化方法 ============
    
    def ensure_providers_table(self, table_name: str = "providers"):
        """Create providers table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
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
        logger.debug(f"[DatabaseInit] Ensured table {table_name} exists")
    
    def ensure_models_table(self, table_name: str = "models"):
        """Create models table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
            `id` VARCHAR(36) PRIMARY KEY,
            `name` VARCHAR(200) NOT NULL,
            `provider_id` VARCHAR(36) NOT NULL,
            `model_name` VARCHAR(200) NOT NULL,
            `initial_capital` DOUBLE DEFAULT 10000,
            `leverage` TINYINT UNSIGNED DEFAULT 10,
            `auto_buy_enabled` TINYINT UNSIGNED DEFAULT 1,
            `auto_sell_enabled` TINYINT UNSIGNED DEFAULT 1,
            `max_positions` TINYINT UNSIGNED DEFAULT 3,
            `buy_batch_size` INT UNSIGNED DEFAULT 1,
            `buy_batch_execution_interval` INT UNSIGNED DEFAULT 60,
            `buy_batch_execution_group_size` INT UNSIGNED DEFAULT 1,
            `sell_batch_size` INT UNSIGNED DEFAULT 1,
            `sell_batch_execution_interval` INT UNSIGNED DEFAULT 60,
            `sell_batch_execution_group_size` INT UNSIGNED DEFAULT 1,
            `api_key` VARCHAR(500),
            `api_secret` VARCHAR(500),
            `account_alias` VARCHAR(100),
            `is_virtual` TINYINT UNSIGNED DEFAULT 0,
            `symbol_source` VARCHAR(50) DEFAULT 'leaderboard',
            `trade_type` VARCHAR(20) DEFAULT 'strategy' COMMENT '交易类型：ai-使用AI交易，strategy-使用策略交易',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX `idx_provider_id` (`provider_id`),
            INDEX `idx_account_alias` (`account_alias`),
            INDEX `idx_trade_type` (`trade_type`),
            INDEX `idx_created_at` (`created_at`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.debug(f"[DatabaseInit] Ensured table {table_name} exists")
        
  
    def ensure_portfolios_table(self, table_name: str = "portfolios"):
        """Create portfolios table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
            `id` VARCHAR(36) PRIMARY KEY,
            `model_id` VARCHAR(36) NOT NULL,
            `symbol` VARCHAR(50) NOT NULL,
            `position_amt` DOUBLE DEFAULT 0.0,
            `avg_price` DOUBLE DEFAULT 0.0,
            `leverage` TINYINT UNSIGNED DEFAULT 1,
            `position_side` VARCHAR(10) DEFAULT 'LONG',
            `initial_margin` DOUBLE DEFAULT 0.0,
            `unrealized_profit` DOUBLE DEFAULT 0.0,
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY `uk_model_symbol_side` (`model_id`, `symbol`, `position_side`),
            INDEX `idx_model_id` (`model_id`),
            INDEX `idx_updated_at` (`updated_at`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.debug(f"[DatabaseInit] Ensured table {table_name} exists")
    
    def ensure_trades_table(self, table_name: str = "trades"):
        """Create trades table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
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
        logger.debug(f"[DatabaseInit] Ensured table {table_name} exists")
    
    def ensure_conversations_table(self, table_name: str = "conversations"):
        """Create conversations table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
            `id` VARCHAR(36) PRIMARY KEY,
            `model_id` VARCHAR(36) NOT NULL,
            `user_prompt` LONGTEXT,
            `ai_response` LONGTEXT,
            `cot_trace` LONGTEXT,
            `tokens` INT DEFAULT 0,
            `type` VARCHAR(10) DEFAULT NULL,
            `timestamp` DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX `idx_model_timestamp` (`model_id`, `timestamp`),
            INDEX `idx_type` (`type`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.debug(f"[DatabaseInit] Ensured table {table_name} exists with index for efficient timestamp DESC sorting")
    
    def ensure_account_values_table(self, table_name: str = "account_values"):
        """Create account_values table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
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
        logger.debug(f"[DatabaseInit] Ensured table {table_name} exists")
    
    def ensure_account_value_historys_table(self, table_name: str = "account_value_historys"):
        """Create account_value_historys table if not exists (用于账户价值历史图表)"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
            `id` VARCHAR(36) PRIMARY KEY,
            `model_id` VARCHAR(36) NOT NULL,
            `account_alias` VARCHAR(100) DEFAULT '',
            `balance` DOUBLE DEFAULT 0.0,
            `available_balance` DOUBLE DEFAULT 0.0,
            `cross_wallet_balance` DOUBLE DEFAULT 0.0,
            `cross_un_pnl` DOUBLE DEFAULT 0.0,
            `timestamp` DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX `idx_model_timestamp` (`model_id`, `timestamp`),
            INDEX `idx_timestamp` (`timestamp`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.debug(f"[DatabaseInit] Ensured table {table_name} exists")
    
    def ensure_settings_table(self, table_name: str = "settings"):
        """Create settings table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
            `id` VARCHAR(36) PRIMARY KEY,
            `buy_frequency_minutes` INT UNSIGNED DEFAULT 5,
            `sell_frequency_minutes` INT UNSIGNED DEFAULT 5,
            `trading_fee_rate` DOUBLE DEFAULT 0.002,
            `show_system_prompt` TINYINT UNSIGNED DEFAULT 0,
            `conversation_limit` INT UNSIGNED DEFAULT 5,
            `strategy_provider` VARCHAR(36) DEFAULT NULL,
            `strategy_model` VARCHAR(255) DEFAULT NULL,
            `strategy_temperature` DOUBLE DEFAULT 0.0,
            `strategy_max_tokens` INT UNSIGNED DEFAULT 8192,
            `strategy_top_p` DOUBLE DEFAULT 0.9,
            `strategy_top_k` INT UNSIGNED DEFAULT 50,
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.debug(f"[DatabaseInit] Ensured table {table_name} exists")
         
    def ensure_model_prompts_table(self, table_name: str = "model_prompts"):
        """Create model_prompts table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
            `id` VARCHAR(36) PRIMARY KEY,
            `model_id` VARCHAR(36) NOT NULL,
            `buy_prompt` TEXT,
            `sell_prompt` TEXT,
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY `uk_model_id` (`model_id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.debug(f"[DatabaseInit] Ensured table {table_name} exists")
    
    def ensure_model_futures_table(self, table_name: str = "model_futures"):
        """Create model_futures table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
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
        logger.debug(f"[DatabaseInit] Ensured table {table_name} exists")
    
    def ensure_futures_table(self, table_name: str = "futures"):
        """Create futures table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
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
        logger.debug(f"[DatabaseInit] Ensured table {table_name} exists")
    
    def ensure_account_asset_table(self, table_name: str = "account_asset"):
        """Create account_asset table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
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
        logger.debug(f"[DatabaseInit] Ensured table {table_name} exists")
    
    def ensure_asset_table(self, table_name: str = "asset", account_asset_table: str = "account_asset"):
        """Create asset table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
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
            FOREIGN KEY (`account_alias`) REFERENCES `{account_asset_table}`(`account_alias`) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.debug(f"[DatabaseInit] Ensured table {table_name} exists")
    
    def ensure_binance_trade_logs_table(self, table_name: str = "binance_trade_logs"):
        """Create binance_trade_logs table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
            `id` VARCHAR(36) PRIMARY KEY,
            `model_id` VARCHAR(36),
            `conversation_id` VARCHAR(36),
            `trade_id` VARCHAR(36),
            `type` VARCHAR(10) NOT NULL COMMENT 'test or real',
            `method_name` VARCHAR(50) NOT NULL COMMENT 'stop_loss_trade, take_profit_trade, market_trade, close_position_trade',
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
        logger.debug(f"[DatabaseInit] Ensured table {table_name} exists")
    
    def ensure_strategy_table(self, table_name: str = "strategys"):
        """Create strategys table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
            `id` VARCHAR(36) PRIMARY KEY,
            `name` VARCHAR(200) NOT NULL,
            `type` VARCHAR(10) DEFAULT 'buy' COMMENT '策略类型：buy-买，sell-卖',
            `strategy_context` TEXT,
            `strategy_code` TEXT,
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX `idx_name` (`name`),
            INDEX `idx_type` (`type`),
            INDEX `idx_created_at` (`created_at`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.debug(f"[DatabaseInit] Ensured table {table_name} exists")
    
    def ensure_model_strategy_table(self, table_name: str = "model_strategy"):
        """Create model_strategy table if not exists (用于模型关联策略信息管理)"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
            `id` VARCHAR(36) PRIMARY KEY,
            `model_id` VARCHAR(36) NOT NULL,
            `strategy_id` VARCHAR(36) NOT NULL,
            `type` VARCHAR(10) NOT NULL COMMENT '策略类型：buy-买，sell-卖',
            `priority` INT DEFAULT 0 COMMENT '策略优先级，数字越大优先级越高',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY `uk_model_strategy_type` (`model_id`, `strategy_id`, `type`),
            INDEX `idx_model_id` (`model_id`),
            INDEX `idx_strategy_id` (`strategy_id`),
            INDEX `idx_type` (`type`),
            INDEX `idx_priority` (`priority`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.debug(f"[DatabaseInit] Ensured table {table_name} exists")
    
    def ensure_strategy_decisions_table(self, table_name: str = "strategy_decisions"):
        """Create strategy_decisions table if not exists (用于存储策略执行决策)"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
            `id` VARCHAR(36) PRIMARY KEY,
            `model_id` VARCHAR(36) NOT NULL COMMENT '模型ID',
            `strategy_name` VARCHAR(200) NOT NULL COMMENT '策略名称',
            `strategy_type` VARCHAR(10) NOT NULL COMMENT '策略类型：buy-买，sell-卖',
            `signal` VARCHAR(50) NOT NULL COMMENT '交易信号',
            `quantity` DECIMAL(20, 8) COMMENT '数量',
            `leverage` INT COMMENT '杠杆',
            `price` DECIMAL(20, 8) COMMENT '期望价格（可空）',
            `stop_price` DECIMAL(20, 8) COMMENT '触发价格（可空）',
            `justification` TEXT COMMENT '触发理由（可空）',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX `idx_model_id` (`model_id`),
            INDEX `idx_strategy_name` (`strategy_name`),
            INDEX `idx_strategy_type` (`strategy_type`),
            INDEX `idx_signal` (`signal`),
            INDEX `idx_created_at` (`created_at`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.debug(f"[DatabaseInit] Ensured table {table_name} exists")
    
    # ============ 市场数据表初始化方法 ============
    
    def ensure_market_ticker_table(self, table_name: str = "24_market_tickers"):
        """Create the 24h market ticker table if it does not exist."""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
            `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            `event_time` DATETIME NOT NULL,
            `symbol` VARCHAR(50) NOT NULL UNIQUE,
            `price_change` DOUBLE DEFAULT 0.0,
            `price_change_percent` DOUBLE DEFAULT 0.0,
            `side` VARCHAR(10) DEFAULT '',
            `change_percent_text` VARCHAR(50) DEFAULT '',
            `average_price` DOUBLE DEFAULT 0.0,
            `last_price` DOUBLE DEFAULT 0.0,
            `last_trade_volume` DOUBLE DEFAULT 0.0,
            `open_price` DOUBLE DEFAULT 0.0,
            `high_price` DOUBLE DEFAULT 0.0,
            `low_price` DOUBLE DEFAULT 0.0,
            `base_volume` DOUBLE DEFAULT 0.0,
            `quote_volume` DOUBLE DEFAULT 0.0,
            `stats_open_time` DATETIME,
            `stats_close_time` DATETIME,
            `first_trade_id` BIGINT UNSIGNED DEFAULT 0,
            `last_trade_id` BIGINT UNSIGNED DEFAULT 0,
            `trade_count` BIGINT UNSIGNED DEFAULT 0,
            `ingestion_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
            `update_price_date` DATETIME NULL,
            INDEX `idx_symbol` (`symbol`),
            INDEX `idx_event_time` (`event_time`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.command(ddl)
        logger.info("[DatabaseInit] Ensured table %s exists", table_name)
    
    # ensure_market_klines_table 和 ensure_market_data_agent_table 方法已删除，相关表不再使用


def init_database_tables(command_func: Callable[[str], Any], table_names: dict):
    """
    初始化所有业务数据库表
    
    Args:
        command_func: 执行SQL命令的函数
        table_names: 表名字典，包含所有业务表的表名
    """
    logger.info("[DatabaseInit] Initializing MySQL business tables...")
    
    initializer = DatabaseInitializer(command_func)
    
    # Providers table (API提供方)
    initializer.ensure_providers_table(table_names.get('providers_table', 'providers'))
    
    # Models table
    initializer.ensure_models_table(table_names.get('models_table', 'models'))
    
    # Portfolios table
    initializer.ensure_portfolios_table(table_names.get('portfolios_table', 'portfolios'))
    
    # Trades table
    initializer.ensure_trades_table(table_names.get('trades_table', 'trades'))
    
    # Conversations table
    initializer.ensure_conversations_table(table_names.get('conversations_table', 'conversations'))
    
    # Account values table (用于当前值，支持UPDATE/INSERT)
    initializer.ensure_account_values_table(table_names.get('account_values_table', 'account_values'))
    
    # Account value historys table (用于历史记录，只INSERT)
    initializer.ensure_account_value_historys_table(table_names.get('account_value_historys_table', 'account_value_historys'))
    
    # Settings table
    initializer.ensure_settings_table(table_names.get('settings_table', 'settings'))
    
    # Model prompts table
    initializer.ensure_model_prompts_table(table_names.get('model_prompts_table', 'model_prompts'))
    
    # Model-specific futures configuration table
    initializer.ensure_model_futures_table(table_names.get('model_futures_table', 'model_futures'))
    
    # Futures table (USDS-M contract universe)
    initializer.ensure_futures_table(table_names.get('futures_table', 'futures'))
    
    # Account asset table
    initializer.ensure_account_asset_table(table_names.get('account_asset_table', 'account_asset'))
    
    # Asset table
    initializer.ensure_asset_table(
        table_names.get('asset_table', 'asset'),
        table_names.get('account_asset_table', 'account_asset')
    )
    
    # Binance trade logs table
    initializer.ensure_binance_trade_logs_table(table_names.get('binance_trade_logs_table', 'binance_trade_logs'))
    
    # Strategy table
    initializer.ensure_strategy_table(table_names.get('strategy_table', 'strategys'))
    
    # Model strategy table (模型关联策略)
    initializer.ensure_model_strategy_table(table_names.get('model_strategy_table', 'model_strategy'))
    
    # Strategy decisions table (策略执行决策)
    initializer.ensure_strategy_decisions_table(table_names.get('strategy_decisions_table', 'strategy_decisions'))
    
    logger.info("[DatabaseInit] MySQL business tables initialized")


def init_market_tables(command_func: Callable[[str], Any], table_config: dict):
    """
    初始化所有市场数据表
    
    Args:
        command_func: 执行SQL命令的函数
        table_config: 表配置字典，包含：
            - market_ticker_table: ticker表名
    """
    logger.info("[DatabaseInit] Initializing MySQL market tables...")
    
    initializer = DatabaseInitializer(command_func)
    
    # Market ticker table
    initializer.ensure_market_ticker_table(table_config.get('market_ticker_table', '24_market_tickers'))
    
    logger.info("[DatabaseInit] MySQL market tables initialized")


def init_all_database_tables(command_func: Callable[[str, tuple], Any]):
    """
    初始化所有数据库表（业务表 + 市场数据表）
    
    这是一个统一的初始化函数，用于系统启动时初始化所有表。
    
    Args:
        command_func: 执行SQL命令的函数，接受SQL字符串和参数元组
    """
    logger.info("[DatabaseInit] Initializing all database tables...")
    
    # 构建表名字典（使用常量）
    table_names = {
        'providers_table': PROVIDERS_TABLE,
        'models_table': MODELS_TABLE,
        'portfolios_table': PORTFOLIOS_TABLE,
        'trades_table': TRADES_TABLE,
        'conversations_table': CONVERSATIONS_TABLE,
        'account_values_table': ACCOUNT_VALUES_TABLE,
        'account_value_historys_table': ACCOUNT_VALUE_HISTORYS_TABLE,
        'settings_table': SETTINGS_TABLE,
        'model_prompts_table': MODEL_PROMPTS_TABLE,
        'model_futures_table': MODEL_FUTURES_TABLE,
        'futures_table': FUTURES_TABLE,
        'account_asset_table': ACCOUNT_ASSET_TABLE,
        'asset_table': ASSET_TABLE,
        'binance_trade_logs_table': BINANCE_TRADE_LOGS_TABLE,
        'strategy_table': STRATEGYS_TABLE,
        'model_strategy_table': MODEL_STRATEGY_TABLE,
    }
    
    # 初始化业务表
    init_database_tables(command_func, table_names)
    
    # 初始化市场数据表
    table_config = {
        'market_ticker_table': MARKET_TICKER_TABLE,
    }
    init_market_tables(command_func, table_config)
    
    logger.info("[DatabaseInit] All database tables initialized successfully")

