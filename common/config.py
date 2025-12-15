"""
系统配置文件模块

本模块提供系统运行所需的所有配置项，包括数据库连接、API密钥、服务参数等。
所有配置项都支持通过环境变量覆盖默认值。

配置分类：
1. 数据库配置：MySQL连接信息和表名配置
2. 币安API配置：API密钥、交易模式、市场数据配置
3. 异步服务配置：K线清理、价格刷新、Symbol下线等定时任务配置
4. Data Agent配置：K线数据同步代理的配置参数
5. 交易配置：自动交易、交易间隔、费率等配置
6. AI决策配置：AI交易决策相关的并发和批处理配置
7. 日志配置：日志级别、格式、日期格式配置

使用方式：
    import common.config as app_config
    mysql_host = app_config.MYSQL_HOST
    api_key = app_config.BINANCE_API_KEY

环境变量：
    所有配置项都支持通过环境变量覆盖，格式：配置项名称（大写）
    例如：MYSQL_HOST、BINANCE_API_KEY、PRICE_REFRESH_CRON 等

注意：
    - 敏感信息（如API密钥、数据库密码）建议通过环境变量设置，不要硬编码
    - 生产环境配置建议通过docker-compose.yml或环境变量文件管理
"""
import os

# ============ MySQL数据库配置 ============

# MySQL连接配置
MYSQL_HOST = os.getenv('MYSQL_HOST', 'localhost')  # MySQL服务器地址
MYSQL_PORT = int(os.getenv('MYSQL_PORT', '32123'))  # MySQL服务器端口
MYSQL_USER = os.getenv('MYSQL_USER', 'aifuturetrade')  # MySQL用户名
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', 'aifuturetrade123')  # MySQL密码
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE', 'aifuturetrade')  # MySQL数据库名

# MySQL表名配置
MYSQL_MARKET_KLINES_TABLE = os.getenv('MYSQL_MARKET_KLINES_TABLE', 'market_klines')  # K线数据表前缀
# 注意：MYSQL_MARKET_TICKER_TABLE已移除，表名在database_mysql.py中硬编码为'24_market_tickers'
# 注意：MySQL连接超时配置已移除，PyMySQL使用默认超时设置
# 如需自定义超时，可在创建连接时通过 pymysql.connect() 的 connect_timeout 参数设置


# ============ 币安API配置 ============

# 币安API密钥配置
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', 'eric')  # 币安API密钥
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET', '55arJnwlytDflHv151UpHN1s32ACnJZEs86mbc79wGyeuSUJNHTDPN7jEgBbqO6I')  # 币安API密钥
FUTURES_QUOTE_ASSET = 'USDT'  # 期货计价资产，固定为USDT

# 币安交易模式配置
BINANCE_TRADE_MODE = os.getenv('BINANCE_TRADE_MODE', 'test').lower()  # 交易模式：'test'（测试接口，默认）或 'real'（真实交易接口）
BINANCE_TESTNET = os.getenv('BINANCE_TESTNET', '0').lower() in {'1', 'true', 'yes'}  # 是否使用测试网络

# 币安市场数据配置
FUTURES_TOP_GAINERS_LIMIT = 5  # 涨幅榜返回的交易对数量限制
FUTURES_TOP_GAINERS_REFRESH = 30  # 涨幅榜刷新间隔（秒），可根据部署需求调整
FUTURES_KLINE_LIMIT = 300  # K线数据获取的最大数量限制
FUTURES_LEADERBOARD_REFRESH = 5  # 涨跌幅榜前端轮询刷新间隔（秒）
FUTURES_MARKET_PRICES_REFRESH = int(os.getenv('FUTURES_MARKET_PRICES_REFRESH', '10'))  # 市场行情价格前端轮询刷新间隔（秒），默认10秒

# K线数据获取配置
KLINE_DATA_SOURCE = os.getenv('KLINE_DATA_SOURCE', 'sdk').lower()  # 数据源：'sdk'（从币安SDK获取）或 'db'（从数据库获取）


# ============ 异步服务配置 ============

# K线同步配置
KLINE_SYNC_CHECK_INTERVAL = int(os.getenv('KLINE_SYNC_CHECK_INTERVAL', '10'))  # K线WebSocket巡检间隔（秒）

# K线清理服务配置
KLINE_CLEANUP_CRON = os.getenv('KLINE_CLEANUP_CRON', '0 */1 * * *')  # Cron表达式，默认每1小时执行一次
KLINE_CLEANUP_RETENTION_DAYS = int(os.getenv('KLINE_CLEANUP_RETENTION_DAYS', '14'))  # K线数据保留天数，默认14天

# 价格刷新服务配置
PRICE_REFRESH_CRON = os.getenv('PRICE_REFRESH_CRON', '*/5 * * * *')  # Cron表达式，默认每5分钟执行一次
PRICE_REFRESH_MAX_PER_MINUTE = int(os.getenv('PRICE_REFRESH_MAX_PER_MINUTE', '1000'))  # 每分钟最多刷新的symbol数量

# 市场Symbol下线服务配置
MARKET_SYMBOL_OFFLINE_CRON = os.getenv('MARKET_SYMBOL_OFFLINE_CRON', '*/20 * * * *')  # Cron表达式，默认每20分钟执行一次
MARKET_SYMBOL_RETENTION_MINUTES = int(os.getenv('MARKET_SYMBOL_RETENTION_MINUTES', '15'))  # Ticker数据保留分钟数，默认15分钟

# ============ Data Agent配置 ============

# Data Agent基础配置
DATA_AGENT_MAX_SYMBOL = int(os.getenv('DATA_AGENT_MAX_SYMBOL', '150'))  # 每个data_agent最多持有的symbol数量
DATA_AGENT_PORT = int(os.getenv('DATA_AGENT_PORT', '9999'))  # data_agent指令接口端口
DATA_AGENT_STATUS_PORT = int(os.getenv('DATA_AGENT_STATUS_PORT', '9988'))  # data_agent状态检查端口（独立端口，避免指令服务阻塞）

# Data Agent注册配置
# 注意：在Docker Compose中使用服务名 'data-manager'，本地开发使用 '127.0.0.1'
DATA_AGENT_REGISTER_IP = os.getenv('DATA_AGENT_REGISTER_IP', '127.0.0.1')  # data_agent注册IP
DATA_AGENT_REGISTER_PORT = int(os.getenv('DATA_AGENT_REGISTER_PORT', '8888'))  # data_agent注册端口

# Data Agent K线时间间隔配置
# 支持的interval: '1m', '5m', '15m', '1h', '4h', '1d', '1w'
# 默认配置：7个interval（1m, 5m, 15m, 1h, 4h, 1d, 1w）
DATA_AGENT_KLINE_INTERVALS = os.getenv(
    'DATA_AGENT_KLINE_INTERVALS',
    '1m,5m,15m,1h,4h,1d,1w'  # 默认7个interval，用逗号分隔
).split(',') if os.getenv('DATA_AGENT_KLINE_INTERVALS') else ['1m', '5m', '15m', '1h', '4h', '1d', '1w']
# 清理空白字符
DATA_AGENT_KLINE_INTERVALS = [interval.strip() for interval in DATA_AGENT_KLINE_INTERVALS if interval.strip()]

# Data Agent心跳和超时配置
# 注意：DATA_AGENT_HEARTBEAT_INTERVAL已废弃，agent不再主动发送心跳，由manager主动探测
DATA_AGENT_HEARTBEAT_TIMEOUT = int(os.getenv('DATA_AGENT_HEARTBEAT_TIMEOUT', '60'))  # 心跳超时（秒）

# Data Agent任务执行配置
DATA_AGENT_BATCH_SYMBOL_SIZE = int(os.getenv('DATA_AGENT_BATCH_SYMBOL_SIZE', '20'))  # 批量添加symbol时每批最多处理的symbol数量
DATA_AGENT_COMMAND_TIMEOUT = int(os.getenv('DATA_AGENT_COMMAND_TIMEOUT', '90'))  # 命令执行超时（秒），防止agent不响应时阻塞队列

# Data Agent同步和检查配置
# 注意：DATA_AGENT_SYMBOL_CHECK_INTERVAL已废弃，使用DATA_AGENT_FULL_SYNC_INTERVAL替代
DATA_AGENT_STATUS_CHECK_INTERVAL = int(os.getenv('DATA_AGENT_STATUS_CHECK_INTERVAL', '60'))  # 检查data_agent状态间隔（秒）
DATA_AGENT_FULL_SYNC_INTERVAL = int(os.getenv('DATA_AGENT_FULL_SYNC_INTERVAL', '180'))  # 全量同步任务执行间隔（秒），默认3分钟
DATA_AGENT_SELF_UPDATE_INTERVAL = int(os.getenv('DATA_AGENT_SELF_UPDATE_INTERVAL', '60'))  # agent自己定时更新状态到数据库的间隔（秒），默认1分钟


# ============ 交易配置 ============

AUTO_TRADING = True  # 是否启用自动交易（默认启用）
TRADING_INTERVAL = 5  # 交易执行间隔（秒）
TRADE_FEE_RATE = 0.002 # 交易费率：0.1%（双向收费）
# 注意：MARKET_REFRESH 和 PORTFOLIO_REFRESH 已移除，前端刷新配置在前端代码中管理

# 交易记录显示配置
TRADES_DISPLAY_COUNT = int(os.getenv('TRADES_DISPLAY_COUNT', '5'))  # 前端显示的交易记录数量，默认5条
TRADES_QUERY_LIMIT = int(os.getenv('TRADES_QUERY_LIMIT', '5'))  # 后端查询的交易记录数量，默认5条


# ============ AI交易决策配置 ============

PROMPT_MARKET_SYMBOL_LIMIT = 5  # 每次调用AI模型时处理的合约数量
BUY_DECISION_THREAD_COUNT = 1  # 买入决策API调用的并发线程数
SELL_DECISION_THREAD_COUNT = 1  # 卖出决策API调用的并发线程数
AI_DECISION_SYMBOL_BATCH_SIZE = int(os.getenv('AI_DECISION_SYMBOL_BATCH_SIZE', '1'))  # 每次提交给AI模型的symbol数量，默认为1

# AI批次执行间隔配置
AI_BATCH_EXECUTION_INTERVAL = int(os.getenv('AI_BATCH_EXECUTION_INTERVAL', '30'))  # 批次执行间隔（秒），默认5秒
AI_BATCH_EXECUTION_GROUP_SIZE = int(os.getenv('AI_BATCH_EXECUTION_GROUP_SIZE', '1'))  # 每N个批次执行完成后统一处理（插入数据库和调用SDK），默认1


# ============ 日志配置 ============

# 日志级别: DEBUG, INFO, WARNING, ERROR, CRITICAL
# 默认级别为 INFO
LOG_LEVEL = 'INFO'  # 可选值: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'  # 日志格式
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'  # 日志日期格式
