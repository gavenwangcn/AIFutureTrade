import os

# ============ Server Configuration ============
# 注意：HOST和PORT通常在启动脚本或gunicorn配置中直接设置，这里保留作为参考
# HOST = '0.0.0.0'
# PORT = 5002
# DEBUG = False

# ============ Gunicorn Configuration ============
# Gunicorn配置（生产环境）
GUNICORN_WORKERS = int(os.getenv('GUNICORN_WORKERS', '5'))  # Worker进程数，建议为CPU核心数*2+1
GUNICORN_WORKER_CLASS = os.getenv('GUNICORN_WORKER_CLASS', 'eventlet')  # 使用eventlet异步worker
GUNICORN_WORKER_CONNECTIONS = int(os.getenv('GUNICORN_WORKER_CONNECTIONS', '1000'))  # 每个worker的最大连接数
GUNICORN_TIMEOUT = int(os.getenv('GUNICORN_TIMEOUT', '120'))  # Worker超时时间（秒）
GUNICORN_KEEPALIVE = int(os.getenv('GUNICORN_KEEPALIVE', '5'))  # Keep-alive时间（秒）
GUNICORN_MAX_REQUESTS = int(os.getenv('GUNICORN_MAX_REQUESTS', '1000'))  # 每个worker处理的最大请求数

# ============ Database Configuration ============
DATABASE_PATH = 'trading_bot.db'

# ============ ClickHouse Configuration ============
CLICKHOUSE_HOST = os.getenv('CLICKHOUSE_HOST', '193.134.209.95')
CLICKHOUSE_PORT = int(os.getenv('CLICKHOUSE_PORT', '32123'))
CLICKHOUSE_USER = os.getenv('CLICKHOUSE_USER', 'default')
CLICKHOUSE_PASSWORD = os.getenv('CLICKHOUSE_PASSWORD', 'di88fg2k')
CLICKHOUSE_DATABASE = os.getenv('CLICKHOUSE_DATABASE', 'default')
CLICKHOUSE_SECURE = os.getenv('CLICKHOUSE_SECURE', '0').lower() in {'1', 'true', 'yes'}

# ClickHouse表名配置
CLICKHOUSE_MARKET_TICKER_TABLE = os.getenv('CLICKHOUSE_MARKET_TICKER_TABLE', '24_market_tickers')
CLICKHOUSE_LEADERBOARD_TABLE = os.getenv('CLICKHOUSE_LEADERBOARD_TABLE', 'futures_leaderboard')
CLICKHOUSE_MARKET_KLINES_TABLE = os.getenv('CLICKHOUSE_MARKET_KLINES_TABLE', 'market_klines')

# ClickHouse涨幅榜同步配置
CLICKHOUSE_LEADERBOARD_SYNC_INTERVAL = int(os.getenv('CLICKHOUSE_LEADERBOARD_SYNC_INTERVAL', '2'))  # 秒
CLICKHOUSE_LEADERBOARD_TIME_WINDOW = int(os.getenv('CLICKHOUSE_LEADERBOARD_TIME_WINDOW', '2'))  # 秒，查询时间窗口
CLICKHOUSE_LEADERBOARD_TOP_N = int(os.getenv('CLICKHOUSE_LEADERBOARD_TOP_N', '10'))  # 涨幅/跌幅前N名
CLICKHOUSE_LEADERBOARD_CLEANUP_INTERVAL_MINUTES = int(os.getenv('CLICKHOUSE_LEADERBOARD_CLEANUP_INTERVAL_MINUTES', '2'))  # 涨跌榜清理执行频率（分钟）
CLICKHOUSE_LEADERBOARD_RETENTION_MINUTES = int(os.getenv('CLICKHOUSE_LEADERBOARD_RETENTION_MINUTES', '5'))  # 保留最近N分钟内的涨跌榜批次

# ============ K线同步配置 ============
KLINE_SYNC_CHECK_INTERVAL = int(os.getenv('KLINE_SYNC_CHECK_INTERVAL', '10'))  # 秒，K线WebSocket巡检间隔
KLINE_CLEANUP_CRON = os.getenv('KLINE_CLEANUP_CRON', '0 */1 * * *')  # Cron表达式，默认每1小时执行一次
KLINE_CLEANUP_RETENTION_DAYS = int(os.getenv('KLINE_CLEANUP_RETENTION_DAYS', '14'))  # 保留天数，默认14天

# ============ Data Agent配置 ============
DATA_AGENT_MAX_SYMBOL = int(os.getenv('DATA_AGENT_MAX_SYMBOL', '150'))  # 每个data_agent最多持有的symbol数量
DATA_AGENT_PORT = int(os.getenv('DATA_AGENT_PORT', '9999'))  # data_agent指令接口端口
DATA_AGENT_STATUS_PORT = int(os.getenv('DATA_AGENT_STATUS_PORT', '9988'))  # data_agent状态检查端口（独立端口，避免指令服务阻塞）

# Data Agent K线时间间隔配置
# 支持的interval: '1m', '5m', '15m', '1h', '4h', '1d', '1w'
# 默认配置：7个interval（1m, 5m, 15m, 1h, 4h, 1d, 1w）
DATA_AGENT_KLINE_INTERVALS = os.getenv(
    'DATA_AGENT_KLINE_INTERVALS',
    '1m,5m,15m,1h,4h,1d,1w'  # 默认7个interval，用逗号分隔
).split(',') if os.getenv('DATA_AGENT_KLINE_INTERVALS') else ['1m', '5m', '15m', '1h', '4h', '1d', '1w']
# 清理空白字符
DATA_AGENT_KLINE_INTERVALS = [interval.strip() for interval in DATA_AGENT_KLINE_INTERVALS if interval.strip()]

# data_agent注册配置：在Docker Compose中使用服务名 'async-agent'，本地开发使用 '127.0.0.1'
DATA_AGENT_REGISTER_IP = os.getenv('DATA_AGENT_REGISTER_IP', '127.0.0.1')  # data_agent注册IP
DATA_AGENT_REGISTER_PORT = int(os.getenv('DATA_AGENT_REGISTER_PORT', '8888'))  # data_agent注册端口

# Data Agent心跳和超时配置
# DATA_AGENT_HEARTBEAT_INTERVAL - 已废弃，agent不再主动发送心跳，由manager主动探测
DATA_AGENT_HEARTBEAT_TIMEOUT = int(os.getenv('DATA_AGENT_HEARTBEAT_TIMEOUT', '60'))  # 心跳超时（秒）

# Data Agent任务执行配置
DATA_AGENT_BATCH_SYMBOL_SIZE = int(os.getenv('DATA_AGENT_BATCH_SYMBOL_SIZE', '20'))  # 批量添加symbol时每批最多处理的symbol数量
DATA_AGENT_COMMAND_TIMEOUT = int(os.getenv('DATA_AGENT_COMMAND_TIMEOUT', '90'))  # 命令执行超时（秒），防止agent不响应时阻塞队列

# Data Agent同步和检查配置
# DATA_AGENT_SYMBOL_CHECK_INTERVAL - 已废弃，使用DATA_AGENT_FULL_SYNC_INTERVAL替代
DATA_AGENT_STATUS_CHECK_INTERVAL = int(os.getenv('DATA_AGENT_STATUS_CHECK_INTERVAL', '60'))  # 检查data_agent状态间隔（秒）
DATA_AGENT_FULL_SYNC_INTERVAL = int(os.getenv('DATA_AGENT_FULL_SYNC_INTERVAL', '180'))  # 全量同步任务执行间隔（秒），默认3分钟
DATA_AGENT_SELF_UPDATE_INTERVAL = int(os.getenv('DATA_AGENT_SELF_UPDATE_INTERVAL', '60'))  # agent自己定时更新状态到数据库的间隔（秒），默认1分钟

# ============ 价格刷新服务配置 ============
PRICE_REFRESH_CRON = os.getenv('PRICE_REFRESH_CRON', '*/5 * * * *')  # Cron表达式，默认每5分钟执行一次
PRICE_REFRESH_MAX_PER_MINUTE = int(os.getenv('PRICE_REFRESH_MAX_PER_MINUTE', '1000'))  # 每分钟最多刷新的symbol数量

# ============ Trading配置 ============
AUTO_TRADING = True
TRADING_INTERVAL = 5  # seconds

# ============ 前端刷新配置 ============
MARKET_REFRESH = 2000  # ms - align with futures indicator frequency
PORTFOLIO_REFRESH = 10000  # ms
TRADE_FEE_RATE = 0.001  # 交易费率：0.1%（双向收费）

# ============ AI交易决策配置 ============
PROMPT_MARKET_SYMBOL_LIMIT = 5  # 每次调用AI模型时处理的合约数量
BUY_DECISION_THREAD_COUNT = 2  # 买入决策API调用的并发线程数

# ============ 日志配置 ============
# 日志级别: DEBUG, INFO, WARNING, ERROR, CRITICAL
# 默认级别为 INFO
LOG_LEVEL = 'INFO'  # 可选值: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# ============ Binance Futures Integration ============
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', 'Eric')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET', 'rg5CRfwMCbkFCZBQKatrnlM7ALOQQDDyfRyaLUs4TduxSRP8WQwk4PrcksHgWP4j')
FUTURES_QUOTE_ASSET = 'USDT'

# Binance期货市场数据配置
FUTURES_TOP_GAINERS_LIMIT = 10
FUTURES_TOP_GAINERS_REFRESH = 30  # seconds, can be adjusted per deployment needs
FUTURES_INDICATOR_REFRESH = 2  # seconds
FUTURES_KLINE_LIMIT = 120
FUTURES_LEADERBOARD_REFRESH = 5  # seconds - WebSocket实时推送间隔

# K线数据获取配置
KLINE_DATA_SOURCE = os.getenv('KLINE_DATA_SOURCE', 'sdk').lower()  # 数据源: 'sdk' 或 'db'
