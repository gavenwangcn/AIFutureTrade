"""
Database operation module package

This package contains all database-related operation modules, including:
- database_basic: Basic database operations and connection management
- database_init: Database table initialization
- database_account: Account data operations
- database_market_tickers: Market ticker data operations
- database_model_prompts: Model prompt data operations
- database_settings: System settings data operations
- database_strategys: Strategy data operations
"""

# Export main classes and functions, maintain backward compatibility
from .database_basic import Database, create_pooled_db
from .database_init import (
    init_database_tables,
    init_market_tables,
    init_all_database_tables,
    DatabaseInitializer,
    # Table name constants
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
