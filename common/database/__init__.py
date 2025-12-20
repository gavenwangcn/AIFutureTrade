"""
数据库操作模块包

本包包含所有数据库相关的操作模块，包括：
- database_basic: 基础数据库操作和连接池
- database_init: 数据库表初始化
- database_account: 账户数据操作
- database_market_tickers: 市场行情数据操作
- database_model_prompts: 模型提示词数据操作
- database_settings: 系统设置数据操作
- database_strategys: 策略数据操作
"""

# 导出主要类和函数，保持向后兼容
from .database_basic import Database, create_pooled_db
from .database_init import (
    init_database_tables,
    init_market_tables,
    init_all_database_tables,
    DatabaseInitializer,
    # 表名常量
    PROVIDERS_TABLE,
    MODELS_TABLE,
    PORTFOLIOS_TABLE,
    TRADES_TABLE,
    CONVERSATIONS_TABLE,
    ACCOUNT_VALUES_TABLE,
    ACCOUNT_VALUE_HISTORYS_TABLE,
    SETTINGS_TABLE,
    MODEL_PROMPTS_TABLE,
    MODEL_FUTURES_TABLE,
    FUTURES_TABLE,
    ACCOUNT_ASSET_TABLE,
    ASSET_TABLE,
    BINANCE_TRADE_LOGS_TABLE,
    STRATEGYS_TABLE,
    MODEL_STRATEGY_TABLE,
    MARKET_TICKER_TABLE,
)

__all__ = [
    'Database',
    'create_pooled_db',
    'init_database_tables',
    'init_market_tables',
    'init_all_database_tables',
    'DatabaseInitializer',
    'PROVIDERS_TABLE',
    'MODELS_TABLE',
    'PORTFOLIOS_TABLE',
    'TRADES_TABLE',
    'CONVERSATIONS_TABLE',
    'ACCOUNT_VALUES_TABLE',
    'ACCOUNT_VALUE_HISTORYS_TABLE',
    'SETTINGS_TABLE',
    'MODEL_PROMPTS_TABLE',
    'MODEL_FUTURES_TABLE',
    'FUTURES_TABLE',
    'ACCOUNT_ASSET_TABLE',
    'ASSET_TABLE',
    'BINANCE_TRADE_LOGS_TABLE',
    'STRATEGYS_TABLE',
    'MODEL_STRATEGY_TABLE',
    'MARKET_TICKER_TABLE',
]

