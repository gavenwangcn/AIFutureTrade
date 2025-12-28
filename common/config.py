"""
系统配置文件模块

本模块提供系统运行所需的所有配置项，包括数据库连接、API密钥、服务参数等。
所有配置项都支持通过环境变量覆盖默认值。

配置分类：
1. 数据库配置：MySQL连接信息
2. 币安API配置：API密钥、交易模式、市场数据配置
3. 异步服务配置：价格刷新、Symbol下线等定时任务配置
4. 交易配置：自动交易、交易间隔、费率等配置
5. AI决策配置：AI交易决策相关的并发和批处理配置
6. 日志配置：日志级别、格式、日期格式配置

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

# ============ 异步服务配置 ============

# 价格刷新服务配置
PRICE_REFRESH_CRON = os.getenv('PRICE_REFRESH_CRON', '*/5 * * * *')  # Cron表达式，默认每5分钟执行一次
PRICE_REFRESH_MAX_PER_MINUTE = int(os.getenv('PRICE_REFRESH_MAX_PER_MINUTE', '1000'))  # 每分钟最多刷新的symbol数量

# 市场Symbol下线服务配置
MARKET_SYMBOL_OFFLINE_CRON = os.getenv('MARKET_SYMBOL_OFFLINE_CRON', '*/30 * * * *')  # Cron表达式，默认每20分钟执行一次
MARKET_SYMBOL_RETENTION_MINUTES = int(os.getenv('MARKET_SYMBOL_RETENTION_MINUTES', '30'))  # Ticker数据保留分钟数，默认15分钟

# ============ 交易配置 ============

AUTO_TRADING = True  # 是否启用自动交易（默认启用）
TRADING_INTERVAL = 5  # 交易执行间隔（秒）
TRADE_FEE_RATE = 0.002  # 交易费率：0.2%（双向收费）

# 交易记录显示配置
TRADES_DISPLAY_COUNT = int(os.getenv('TRADES_DISPLAY_COUNT', '5'))  # 前端显示的交易记录数量，默认5条
TRADES_QUERY_LIMIT = int(os.getenv('TRADES_QUERY_LIMIT', '5'))  # 后端查询的交易记录数量，默认5条


# ============ AI交易决策配置 ============

PROMPT_MARKET_SYMBOL_LIMIT = 3  # 每次调用AI模型时处理的市场合约数量
BUY_DECISION_THREAD_COUNT = 1  # 买入决策API调用的并发线程数
SELL_DECISION_THREAD_COUNT = 1  # 卖出决策API调用的并发线程数


# ============ 代理配置 ============

# 币安API代理配置（用于REST API调用，减少IP限流）
# 支持配置多个代理，系统会自动轮询使用
# 格式：列表，每个元素是一个代理配置字典
# 注意：WebSocket连接不使用代理，只有REST API使用代理
BINANCE_PROXY_LIST = [
    # 示例配置（请根据实际情况修改）：
    # {
    #     "host": "127.0.0.1",
    #     "port": 8080,
    #     "protocol": "http",  # 或 'https'
    #     "auth": {  # 可选，如果代理需要认证
    #         "username": "proxy-user",
    #         "password": "proxy-password",
    #     },
    # },
]

# 从环境变量读取代理配置（JSON格式）
# 环境变量格式：BINANCE_PROXY_LIST='[{"host":"127.0.0.1","port":8080,"protocol":"http"}]'
import json
_proxy_list_env = os.getenv('BINANCE_PROXY_LIST', '')
if _proxy_list_env:
    try:
        BINANCE_PROXY_LIST = json.loads(_proxy_list_env)
    except json.JSONDecodeError:
        pass  # 如果解析失败，使用默认值

# 是否启用代理（如果BINANCE_PROXY_LIST为空，则自动禁用）
BINANCE_PROXY_ENABLED = len(BINANCE_PROXY_LIST) > 0


# ============ 日志配置 ============

# 日志级别: DEBUG, INFO, WARNING, ERROR, CRITICAL
# 默认级别为 INFO
LOG_LEVEL = 'INFO'  # 可选值: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'  # 日志格式
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'  # 日志日期格式
