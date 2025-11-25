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
PROMPT_MARKET_SYMBOL_LIMIT = 5  # 每次调用AI模型时处理的合约数量
BUY_DECISION_THREAD_COUNT = 2  # 买入决策API调用的并发线程数

# Logging Configuration
# 日志级别: DEBUG, INFO, WARNING, ERROR, CRITICAL
# 默认级别为 INFO
LOG_LEVEL = 'INFO'  # 可选值: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# Binance Futures Integration
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', 'Eric')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET', 'rg5CRfwMCbkFCZBQKatrnlM7ALOQQDDyfRyaLUs4TduxSRP8WQwk4PrcksHgWP4j')
FUTURES_TOP_GAINERS_LIMIT = 10
FUTURES_TOP_GAINERS_REFRESH = 5  # seconds, can be adjusted per deployment needs
FUTURES_INDICATOR_REFRESH = 2  # seconds
FUTURES_KLINE_LIMIT = 120
FUTURES_QUOTE_ASSET = 'USDT'
FUTURES_LEADERBOARD_REFRESH = 180  # seconds

