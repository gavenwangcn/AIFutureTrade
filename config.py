import os

# Configuration Example

# Server
HOST = '0.0.0.0'
PORT = 5002
DEBUG = False

# Database
DATABASE_PATH = 'trading_bot.db'

# Trading
AUTO_TRADING = True
TRADING_INTERVAL = 180  # seconds

# Market Data
MARKET_API_CACHE = 5  # seconds

# Refresh Rates (frontend)
MARKET_REFRESH = 2000  # ms - align with futures indicator frequency
PORTFOLIO_REFRESH = 10000  # ms
TRADE_FEE_RATE = 0.001  # 交易费率：0.1%（双向收费）
PROMPT_MARKET_SYMBOL_LIMIT = 5  # AI提示中用于行情概览的最大合约数

# Logging Configuration
# 日志级别: DEBUG, INFO, WARNING, ERROR, CRITICAL
# 默认级别为 INFO
LOG_LEVEL = 'INFO'  # 可选值: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# Binance Futures Integration
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET', '')
FUTURES_TOP_GAINERS_LIMIT = 10
FUTURES_TOP_GAINERS_REFRESH = 3600  # seconds
FUTURES_INDICATOR_REFRESH = 2  # seconds
FUTURES_KLINE_LIMIT = 120
FUTURES_QUOTE_ASSET = 'USDT'
FUTURES_LEADERBOARD_REFRESH = 180  # seconds

