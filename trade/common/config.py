"""
System configuration file module

This module provides all configuration items required for system operation, including database connections, API keys, service parameters, etc.
All configuration items support overriding default values through environment variables.

Configuration categories:
1. Database configuration: MySQL connection information
2. Binance API configuration: API keys, trading mode, market data configuration
3. Trading configuration: Auto trading, trading interval, fee rate and other configurations
4. AI decision configuration: Batch processing configurations related to AI trading decisions
5. Binance Service configuration: Binance Service microservice configuration
6. Logging configuration: Log level, format, date format configuration

Usage:
    import trade.common.config as app_config
    mysql_host = app_config.MYSQL_HOST
    api_key = app_config.BINANCE_API_KEY

Environment variables:
    All configuration items support overriding through environment variables, format: configuration item name (uppercase)
    For example: MYSQL_HOST, BINANCE_API_KEY, TRADING_INTERVAL, etc.

Notes:
    - Sensitive information (such as API keys, database passwords) should be set through environment variables, do not hardcode
    - Production environment configuration is recommended to be managed through docker-compose.yml or environment variable files
"""
import os

# ============ MySQL Database Configuration ============

# MySQL connection configuration
MYSQL_HOST = os.getenv('MYSQL_HOST', '154.89.148.172')  # MySQL server address (default: 154.89.148.172)
MYSQL_PORT = int(os.getenv('MYSQL_PORT', '32123'))  # MySQL server port
MYSQL_USER = os.getenv('MYSQL_USER', 'aifuturetrade')  # MySQL username
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', 'aifuturetrade123')  # MySQL password
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE', 'aifuturetrade')  # MySQL database name



# ============ Binance API Configuration ============

# Binance API key configuration
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', 'eric')  # Binance API key
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET', '55arJnwlytDflHv151UpHN1s32ACnJZEs86mbc79wGyeuSUJNHTDPN7jEgBbqO6I')  # Binance API secret
FUTURES_QUOTE_ASSET = 'USDT'  # Futures quote asset, fixed as USDT

# Binance trading mode configuration
BINANCE_TRADE_MODE = os.getenv('BINANCE_TRADE_MODE', 'test').lower()  # Trading mode: 'test' (test interface, default) or 'real' (real trading interface)
BINANCE_TESTNET = os.getenv('BINANCE_TESTNET', '0').lower() in {'1', 'true', 'yes'}  # Whether to use testnet

# Binance market data configuration
FUTURES_TOP_GAINERS_LIMIT = 5  # Limit on number of trading pairs returned in top gainers list
FUTURES_TOP_GAINERS_REFRESH = 30  # Top gainers list refresh interval (seconds), can be adjusted according to deployment needs
FUTURES_KLINE_LIMIT = 300  # Maximum limit for K-line data retrieval
FUTURES_LEADERBOARD_REFRESH = 5  # Frontend polling refresh interval for gain/loss leaderboard (seconds)

# ============ Trading Configuration ============

AUTO_TRADING = True  # Whether to enable auto trading (enabled by default)
TRADING_INTERVAL = 5  # Trading execution interval (seconds)
TRADE_FEE_RATE = 0.002  # Trading fee rate: 0.2% (bidirectional fee)

# Trading loop configuration
# Whether to start trading loops on service startup (default: False)
# Note: With the new model-based container architecture, trading loops are managed by individual model containers
# This flag controls whether the main trade service should also start trading loops
# Set to False by default to avoid conflicts with model containers
TRADING_LOOP_ENABLED = os.getenv('TRADING_LOOP_ENABLED', 'false').lower() in {'1', 'true', 'yes'}  # Default: False

# ============ AI Trading Decision Configuration ============

PROMPT_MARKET_SYMBOL_LIMIT = 5  # Number of market contracts processed each time AI model is called


# ============ Binance Service Configuration ============

# Binance Service microservice configuration (used for querying symbol-related data, such as real-time prices, K-line information, etc.)
# Supports configuring multiple services, system will automatically poll and use them
# Format: list, each element is a service configuration dictionary
# Note: Order placement and account query related interfaces do not use binance-service, only symbol-related data query interfaces use it
BINANCE_SERVICE_LIST = [
    # Example configuration (please modify according to actual situation):
    # {
    #     "base_url": "http://localhost:5004",  # Binance Service base URL
    #     "timeout": 30,  # Request timeout (seconds), default 30 seconds
    # },
     {
         "base_url": "http://109.206.245.131:5004",
         "timeout": 30,
     },
    {
         "base_url": "http://185.242.232.23:5004",
         "timeout": 30,
     },
]

# Read Binance Service configuration from environment variables (JSON format)
# Environment variable format: BINANCE_SERVICE_LIST='[{"base_url":"http://localhost:5004","timeout":30}]'
import json
_binance_service_list_env = os.getenv('BINANCE_SERVICE_LIST', '')
if _binance_service_list_env:
    try:
        BINANCE_SERVICE_LIST = json.loads(_binance_service_list_env)
    except json.JSONDecodeError:
        pass  # If parsing fails, use default value

# Whether to enable Binance Service (automatically disabled if BINANCE_SERVICE_LIST is empty)
BINANCE_SERVICE_ENABLED = len(BINANCE_SERVICE_LIST) > 0

# Binance Service request timeout (seconds), if not specified in service configuration, use this default value
BINANCE_SERVICE_DEFAULT_TIMEOUT = 30


# ============ Logging Configuration ============

# Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
# Default level is INFO
LOG_LEVEL = 'INFO'  # Optional values: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'  # Log format
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'  # Log date format
