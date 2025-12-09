# This must be at the very top of the file, before any other imports
import eventlet
eventlet.monkey_patch()

"""
Flask application for AI Futures Trading System
"""
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import os
import time
import threading
import json
from datetime import datetime
from trade.trading_engine import TradingEngine
from market.market_data import MarketDataFetcher
from trade.ai_trader import AITrader
from common.database_basic import Database
from common.version import __version__
from trade.prompt_defaults import DEFAULT_BUY_CONSTRAINTS, DEFAULT_SELL_CONSTRAINTS

import common.config as app_config
import logging
import sys

# ============ Application Initialization ============

app = Flask(__name__)
# CORS配置：允许前端服务访问
# 注意：在生产环境中，应该限制具体的域名，而不是使用通配符
CORS(app, resources={
    r"/api/*": {
        "origins": "*",  # 允许所有来源（生产环境应限制）
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # 明确支持所有HTTP方法
        "allow_headers": ["Content-Type", "Authorization"],  # 允许的请求头
        "expose_headers": ["Content-Type"],  # 暴露的响应头
        "supports_credentials": False  # 不支持凭证
    },
    r"/socket.io/*": {"origins": "*"}  # 允许所有来源（生产环境应限制）
})
# 使用eventlet作为异步模式以获得更好的性能
# async_mode='eventlet' 提供更好的并发性能
socketio = SocketIO(
    app, 
    cors_allowed_origins="*",  # Socket.IO允许所有来源
    async_mode='eventlet',  # 使用eventlet异步模式
    logger=False,  # 禁用SocketIO日志以减少开销
    engineio_logger=False,  # 禁用EngineIO日志
    ping_timeout=60,  # WebSocket ping超时时间
    ping_interval=25,  # WebSocket ping间隔
    max_http_buffer_size=1e6,  # 最大HTTP缓冲区大小
    allow_upgrades=True,  # 允许协议升级
    transports=['websocket', 'polling']  # 支持的传输方式
)

# ============ Logging Configuration ============

def get_log_level():
    """从配置获取日志级别，默认为 INFO"""
    log_level_str = getattr(app_config, 'LOG_LEVEL', 'INFO').upper()
    log_level_map = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }
    return log_level_map.get(log_level_str, logging.INFO)

log_format = getattr(app_config, 'LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_date_format = getattr(app_config, 'LOG_DATE_FORMAT', '%Y-%m-%d %H:%M:%S')

logging.basicConfig(
    level=get_log_level(),
    format=log_format,
    datefmt=log_date_format,
    handlers=[logging.StreamHandler(sys.stdout)]
)

logging.getLogger('werkzeug').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# ============ Global Configuration ============

DEFAULT_DB_PATH = 'trading_bot.db'
env_db_path = os.getenv('DATABASE_PATH')
config_db_path = getattr(app_config, 'DATABASE_PATH', None)
db_path = env_db_path or config_db_path or DEFAULT_DB_PATH

db = Database(db_path)

# Initialize database tables immediately when the application starts
# This ensures tables are created even when running with gunicorn or other WSGI servers
with app.app_context():
    db.init_db()
    logger.info("Database tables initialized")

# 应用启动时立即启动ClickHouse涨跌幅榜同步服务
# 这确保无论通过什么方式启动（直接运行、gunicorn等），都会自动启动服务
def _init_background_services():
    """初始化后台服务（在应用启动时调用）"""
    global clickhouse_leaderboard_running
    
    logger.info("🚀 初始化后台服务...")
    
    # 启动ClickHouse涨跌幅榜同步线程（默认运行状态）
    logger.info("📊 启动ClickHouse涨跌幅榜同步服务...")
    start_clickhouse_leaderboard_sync()
    logger.info("✅ ClickHouse涨跌幅榜同步服务已启动（默认运行状态）")
    
    logger.info("✅ 后台服务初始化完成")

market_fetcher = MarketDataFetcher(db)
trading_engines = {}
auto_trading = getattr(app_config, 'AUTO_TRADING', True)
TRADE_FEE_RATE = getattr(app_config, 'TRADE_FEE_RATE', 0.001)
LEADERBOARD_REFRESH_INTERVAL = getattr(app_config, 'FUTURES_LEADERBOARD_REFRESH', 10)

leaderboard_thread = None
leaderboard_stop_event = threading.Event()

# ClickHouse leaderboard sync
clickhouse_leaderboard_thread = None
clickhouse_leaderboard_stop_event = threading.Event()
clickhouse_leaderboard_running = True  # 默认状态为运行状态
# 添加线程锁以防止并发执行
clickhouse_leaderboard_lock = threading.Lock()
# 线程监控标志，用于自动重启
clickhouse_leaderboard_monitor_thread = None
clickhouse_leaderboard_monitor_stop_event = threading.Event()

# ============ Helper Functions ============

def init_trading_engine_for_model(model_id: int):
    """Initialize trading engine for a model if possible."""
    model = db.get_model(model_id)
    if not model:
        return None, 'Model not found'

    provider = db.get_provider(model['provider_id'])
    if not provider:
        return None, 'Provider not found'

    trading_engines[model_id] = TradingEngine(
        model_id=model_id,
        db=db,
        market_fetcher=market_fetcher,
        ai_trader=AITrader(
            provider_type=provider.get('provider_type', 'openai'),
            api_key=provider['api_key'],
            api_url=provider['api_url'],
            model_name=model['model_name'],
            market_fetcher=market_fetcher
        ),
        trade_fee_rate=TRADE_FEE_RATE
    )
    return trading_engines[model_id], None

def get_tracked_symbols():
    """Get list of tracked future symbols"""
    symbols = db.get_future_symbols()
    if not symbols:
        logger.warning('No futures configured. Please add futures via /api/futures.')
    return symbols

def get_trading_interval_seconds() -> int:
    """Read trading frequency from settings (minutes) and return seconds."""
    default_interval_seconds = getattr(app_config, 'TRADING_INTERVAL', 3600)
    default_minutes = max(1, int(default_interval_seconds / 60))
    try:
        settings = db.get_settings()
        minutes = int(settings.get('trading_frequency_minutes', default_minutes))
    except Exception as e:
        logger.warning(f"Unable to load trading frequency setting: {e}")
        minutes = default_minutes

    minutes = max(1, min(1440, minutes))
    return minutes * 60

def init_trading_engines():
    """Initialize trading engines for all models"""
    try:
        models = db.get_all_models()

        if not models:
            logger.warning("No trading models found")
            return

        logger.info(f"\nINIT: Initializing trading engines...")
        for model in models:
            model_id = model['id']
            model_name = model['name']

            try:
                provider = db.get_provider(model['provider_id'])
                if not provider:
                    logger.warning(f"  Model {model_id} ({model_name}): Provider not found")
                    continue

                trading_engines[model_id] = TradingEngine(
                    model_id=model_id,
                    db=db,
                    market_fetcher=market_fetcher,
                    ai_trader=AITrader(
                        provider_type=provider.get('provider_type', 'openai'),
                        api_key=provider['api_key'],
                        api_url=provider['api_url'],
                        model_name=model['model_name'],
                        market_fetcher=market_fetcher
                    ),
                    trade_fee_rate=TRADE_FEE_RATE
                )
                logger.info(f"  OK: Model {model_id} ({model_name})")
            except Exception as e:
                logger.error(f"  Model {model_id} ({model_name}): {e}")
                continue

        logger.info(f"Initialized {len(trading_engines)} engine(s)\n")

    except Exception as e:
        logger.error(f"Init engines failed: {e}\n")

# ============ Background Tasks ============

def _leaderboard_loop():
    """
    后台循环任务：定期同步涨跌幅榜数据到ClickHouse（不再通过WebSocket推送到前端）
    
    流程：
    1. 启动循环，记录启动信息
    2. 定期调用 sync_leaderboard 同步数据到ClickHouse
    3. 不再通过 WebSocket 推送到前端（前端改为轮询方式获取数据）
    4. 等待指定间隔后继续下一次循环
    5. 收到停止信号时退出循环
    
    注意：前端已改为轮询方式获取数据，不再使用WebSocket推送
    """
    thread_id = threading.current_thread().ident
    logger.info(f"[Leaderboard Worker-{thread_id}] 涨跌幅榜同步循环启动，刷新间隔: {LEADERBOARD_REFRESH_INTERVAL} 秒（仅同步到ClickHouse，不推送前端）")
    
    wait_seconds = max(5, LEADERBOARD_REFRESH_INTERVAL)
    cycle_count = 0
    
    while not leaderboard_stop_event.is_set():
        cycle_count += 1
        cycle_start_time = datetime.now()
        
        try:
            # 调用同步方法（不强制刷新，使用缓存机制）
            # 仅同步数据到ClickHouse，不再通过WebSocket推送
            data = market_fetcher.sync_leaderboard(force=False)
            
            # 检查同步结果（仅记录日志，不推送）
            if data:
                gainers_count = len(data.get('gainers', [])) if data.get('gainers') else 0
                losers_count = len(data.get('losers', [])) if data.get('losers') else 0
                logger.debug(
                    f"[Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] 同步完成: "
                    f"涨幅榜 {gainers_count} 条, 跌幅榜 {losers_count} 条 "
                    f"（已同步到ClickHouse，前端通过轮询获取）"
                )
            else:
                logger.warning(f"[Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] 同步返回空数据")
                
        except Exception as exc:
            cycle_duration = (datetime.now() - cycle_start_time).total_seconds()
            logger.error(f"[Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] 涨跌幅榜同步失败: {exc}, 耗时: {cycle_duration:.2f} 秒")
            import traceback
            logger.error(f"[Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] 错误堆栈:\n{traceback.format_exc()}")
        
        # 等待指定间隔（可被停止事件中断）
        leaderboard_stop_event.wait(wait_seconds)
    
    logger.info(f"[Leaderboard Worker-{thread_id}] 涨跌幅榜同步循环停止，总循环次数: {cycle_count}")

def _clickhouse_leaderboard_loop():
    """
    后台循环任务：定期从 ClickHouse 24_market_tickers 表同步涨跌幅榜数据到 futures_leaderboard 表
    
    核心功能：
    - 定期从24_market_tickers表获取最新的市场数据
    - 计算每个合约的涨跌幅
    - 筛选出涨幅前N名和跌幅前N名
    - 将结果保存到futures_leaderboard表中
    - 支持配置同步间隔、时间窗口和前N名数量
    
    执行流程：
    1. 初始化ClickHouse连接
    2. 获取配置参数
    3. 进入主循环：
       a. 查询最近时间窗口内的市场数据
       b. 计算涨跌幅并排序
       c. 筛选前N名涨幅和跌幅
       d. 原子更新futures_leaderboard表
       e. 等待指定间隔后重复循环
    4. 收到停止信号时退出循环
    
    配置参数：
    - CLICKHOUSE_LEADERBOARD_SYNC_INTERVAL: 同步间隔（秒）
    - CLICKHOUSE_LEADERBOARD_TIME_WINDOW: 查询时间窗口（秒）
    - CLICKHOUSE_LEADERBOARD_TOP_N: 涨跌幅前N名数量
    
    注意：
    - 此函数包含异常处理，确保即使发生异常也不会退出循环
    - 只有在收到明确的停止信号时才会退出
    """
    # 延迟导入，避免循环导入问题
    from common.database_clickhouse import ClickHouseDatabase
    
    # 获取当前线程ID，用于日志标识
    thread_id = threading.current_thread().ident
    
    # 获取配置参数，带默认值
    sync_interval = getattr(app_config, 'CLICKHOUSE_LEADERBOARD_SYNC_INTERVAL', 2)
    time_window = getattr(app_config, 'CLICKHOUSE_LEADERBOARD_TIME_WINDOW', 5)  # 已废弃，保留以兼容
    top_n = getattr(app_config, 'CLICKHOUSE_LEADERBOARD_TOP_N', 10)
    
    logger.info(f"[ClickHouse Leaderboard Worker-{thread_id}] ClickHouse 涨幅榜同步循环启动，同步间隔: {sync_interval} 秒，前N名数量: {top_n}")
    
    # 确保等待时间至少为1秒
    wait_seconds = max(1, sync_interval)
    cycle_count = 0
    db = None
    
    # 在循环外创建ClickHouseDatabase实例，避免频繁创建和销毁连接
    try:
        db = ClickHouseDatabase(auto_init_tables=True)
    except Exception as exc:
        logger.error(f"[ClickHouse Leaderboard Worker-{thread_id}] 初始化ClickHouse连接失败: {exc}，将在循环中重试初始化")
        # 不直接返回，而是在循环中重试
    
    # 立即执行第一次同步（启动时立即刷新数据）
    cycle_count += 1
    cycle_start_time = datetime.now()
    
    try:
        # 如果数据库连接未初始化，尝试重新初始化
        if db is None:
            db = ClickHouseDatabase(auto_init_tables=True)
        
        # 执行同步逻辑
        db.sync_leaderboard(
            time_window_seconds=time_window,
            top_n=top_n
        )
    except Exception as exc:
        # 处理同步失败的情况，但不退出循环
        cycle_duration = (datetime.now() - cycle_start_time).total_seconds()
        logger.error(f"[ClickHouse Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] 启动时首次同步失败: {exc}, 耗时: {cycle_duration:.3f} 秒")
        import traceback
        logger.error(f"[ClickHouse Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] 错误堆栈:\n{traceback.format_exc()}")
    
    # 主循环：定期执行同步任务（永不退出，除非收到停止信号）
    while not clickhouse_leaderboard_stop_event.is_set():
        cycle_count += 1
        cycle_start_time = datetime.now()
        
        try:
            # 如果数据库连接丢失，尝试重新初始化
            if db is None:
                db = ClickHouseDatabase(auto_init_tables=True)
            
            # 执行同步逻辑
            db.sync_leaderboard(
                time_window_seconds=time_window,
                top_n=top_n
            )
            
        except Exception as exc:
            # 处理同步失败的情况，但不退出循环，继续重试
            cycle_duration = (datetime.now() - cycle_start_time).total_seconds()
            logger.error(f"[ClickHouse Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] 同步失败: {exc}, 耗时: {cycle_duration:.3f} 秒")
            import traceback
            error_stack = traceback.format_exc()
            logger.error(f"[ClickHouse Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] 错误堆栈: {error_stack}")
            # 标记数据库连接可能已失效，下次循环时重新初始化
            db = None
        
        # 等待指定间隔后继续下一次循环
        # 使用wait()方法可以被停止事件中断
        # 如果等待期间收到停止信号，循环会退出
        if clickhouse_leaderboard_stop_event.wait(wait_seconds):
            # 如果wait返回True，说明在等待期间收到了停止信号
            break
    
    # 循环结束，记录停止信息
    logger.info(f"[ClickHouse Leaderboard Worker-{thread_id}] ClickHouse 涨幅榜同步循环停止，总循环次数: {cycle_count}")
    
    # 更新运行状态
    global clickhouse_leaderboard_running
    with clickhouse_leaderboard_lock:
        clickhouse_leaderboard_running = False


def _clickhouse_leaderboard_monitor():
    """
    监控线程：监控ClickHouse涨跌幅榜同步线程，如果线程意外退出则自动重启
    
    此监控线程确保同步服务持续运行，不会因为异常而停止
    """
    global clickhouse_leaderboard_thread, clickhouse_leaderboard_running
    
    logger.info("[ClickHouse Leaderboard Monitor] 🛡️  监控线程启动")
    
    while not clickhouse_leaderboard_monitor_stop_event.is_set():
        # 每10秒检查一次线程状态
        clickhouse_leaderboard_monitor_stop_event.wait(10)
        
        if clickhouse_leaderboard_monitor_stop_event.is_set():
            break
        
        with clickhouse_leaderboard_lock:
            # 检查线程是否还在运行
            if clickhouse_leaderboard_running:
                if clickhouse_leaderboard_thread and clickhouse_leaderboard_thread.is_alive():
                    # 线程正常运行，继续监控
                    continue
                else:
                    # 线程意外退出，需要重启
                    logger.warning("[ClickHouse Leaderboard Monitor] ⚠️  检测到同步线程意外退出，准备自动重启...")
                    clickhouse_leaderboard_running = False
            
            # 如果运行状态为False，但用户没有明确停止，则自动重启
            if not clickhouse_leaderboard_running and not clickhouse_leaderboard_stop_event.is_set():
                logger.info("[ClickHouse Leaderboard Monitor] 🔄 自动重启同步线程...")
                clickhouse_leaderboard_stop_event.clear()
                clickhouse_leaderboard_running = True
                
                clickhouse_leaderboard_thread = threading.Thread(
                    target=_clickhouse_leaderboard_loop,
                    daemon=True,
                    name="ClickHouseLeaderboardSync"
                )
                clickhouse_leaderboard_thread.start()
                logger.info("[ClickHouse Leaderboard Monitor] ✅ 同步线程已自动重启")
    
    logger.info("[ClickHouse Leaderboard Monitor] 🛡️  监控线程停止")


def start_clickhouse_leaderboard_sync():
    """
    启动 ClickHouse 涨幅榜同步线程
    
    功能：
    - 检查同步线程是否已在运行
    - 初始化停止事件
    - 创建并启动同步线程
    - 设置线程为守护线程，确保主程序退出时自动终止
    - 启动监控线程，确保线程意外退出时自动重启
    
    注意：
    - 该函数是线程安全的，可以多次调用
    - 多次调用时，只有第一次会真正启动线程
    - 默认状态为运行状态，应用启动时自动执行
    """
    global clickhouse_leaderboard_thread, clickhouse_leaderboard_running
    global clickhouse_leaderboard_monitor_thread, clickhouse_leaderboard_monitor_stop_event
    
    # 使用锁防止并发执行
    with clickhouse_leaderboard_lock:
        # 检查线程是否已在运行
        if clickhouse_leaderboard_thread and clickhouse_leaderboard_thread.is_alive():
            logger.warning("[ClickHouse Leaderboard] ⚠️  同步线程已在运行，无需重复启动")
            return
        
        logger.info("[ClickHouse Leaderboard] 🚀 准备启动涨跌幅榜同步线程...")
        
        # 重置停止事件和运行状态
        clickhouse_leaderboard_stop_event.clear()
        clickhouse_leaderboard_running = True
        
        # 创建同步线程
        clickhouse_leaderboard_thread = threading.Thread(
            target=_clickhouse_leaderboard_loop,
            daemon=True,  # 设置为守护线程
            name="ClickHouseLeaderboardSync"  # 设置线程名称，便于调试
        )
        
        # 启动线程
        clickhouse_leaderboard_thread.start()
        
        # 记录启动信息
        logger.info(f"[ClickHouse Leaderboard] ✅ 涨跌幅榜同步线程已启动")
        logger.info(f"[ClickHouse Leaderboard] 📋 线程ID: {clickhouse_leaderboard_thread.ident}")
        logger.info(f"[ClickHouse Leaderboard] 📋 线程名称: {clickhouse_leaderboard_thread.name}")
        
        # 启动监控线程（如果还没有启动）
        if not clickhouse_leaderboard_monitor_thread or not clickhouse_leaderboard_monitor_thread.is_alive():
            clickhouse_leaderboard_monitor_stop_event.clear()
            clickhouse_leaderboard_monitor_thread = threading.Thread(
                target=_clickhouse_leaderboard_monitor,
                daemon=True,
                name="ClickHouseLeaderboardMonitor"
            )
            clickhouse_leaderboard_monitor_thread.start()
            logger.info("[ClickHouse Leaderboard] 🛡️  监控线程已启动")


def stop_clickhouse_leaderboard_sync():
    """
    停止 ClickHouse 涨幅榜同步线程
    
    功能：
    - 检查同步线程是否在运行
    - 设置停止事件，通知线程退出
    - 等待线程终止（最多5秒）
    - 更新运行状态
    - 停止监控线程
    
    注意：
    - 该函数是线程安全的
    - 调用后会立即返回，不会阻塞等待线程终止
    - 只有用户明确调用此函数时才会停止，不会自动暂停
    """
    global clickhouse_leaderboard_running
    global clickhouse_leaderboard_monitor_thread, clickhouse_leaderboard_monitor_stop_event
    
    # 使用锁防止并发执行
    with clickhouse_leaderboard_lock:
        # 检查线程是否在运行
        if not clickhouse_leaderboard_running:
            logger.warning("[ClickHouse Leaderboard] ⚠️  同步线程未运行，无需停止")
            return
        
        logger.info("[ClickHouse Leaderboard] 🛑 准备停止涨跌幅榜同步线程（用户手动停止）...")
        
        # 设置停止状态和停止事件
        clickhouse_leaderboard_running = False
        clickhouse_leaderboard_stop_event.set()
        
        # 停止监控线程
        if clickhouse_leaderboard_monitor_thread and clickhouse_leaderboard_monitor_thread.is_alive():
            logger.info("[ClickHouse Leaderboard] 🛑 停止监控线程...")
            clickhouse_leaderboard_monitor_stop_event.set()
            clickhouse_leaderboard_monitor_thread.join(timeout=2)
        
        # 等待线程终止，最多5秒
        if clickhouse_leaderboard_thread and clickhouse_leaderboard_thread.is_alive():
            logger.info("[ClickHouse Leaderboard] ⏳ 等待线程终止...")
            clickhouse_leaderboard_thread.join(timeout=5)
            
            if clickhouse_leaderboard_thread.is_alive():
                logger.warning("[ClickHouse Leaderboard] ⚠️  线程未能在5秒内终止，可能已强制终止")
            else:
                logger.info("[ClickHouse Leaderboard] ✅ 线程已成功终止")
        else:
            logger.info("[ClickHouse Leaderboard] ✅ 线程已停止（未运行）")
        
        logger.info("[ClickHouse Leaderboard] 📋 涨跌幅榜同步线程停止完成")

def start_leaderboard_worker():
    """Start background worker for leaderboard updates"""
    global leaderboard_thread
    if leaderboard_thread and leaderboard_thread.is_alive():
        return
    leaderboard_stop_event.clear()
    leaderboard_thread = threading.Thread(target=_leaderboard_loop, daemon=True)
    leaderboard_thread.start()

def trading_loop():
    """Main trading loop for automatic trading"""
    logger.info("Trading loop started")

    while auto_trading:
        try:
            if not trading_engines:
                time.sleep(30)
                continue

            logger.info(f"\n{'='*60}")
            logger.info(f"CYCLE: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"Active models: {len(trading_engines)}")
            logger.info(f"{'='*60}")

            for model_id, engine in list(trading_engines.items()):
                try:
                    if not db.is_model_auto_trading_enabled(model_id):
                        logger.info(f"SKIP: Model {model_id} auto trading paused")
                        continue

                    logger.info(f"\nEXEC: Model {model_id}")
                    result = engine.execute_trading_cycle()

                    if result.get('success'):
                        logger.info(f"OK: Model {model_id} completed")
                        if result.get('executions'):
                            for exec_result in result['executions']:
                                signal = exec_result.get('signal', 'unknown')
                                symbol = exec_result.get('future', exec_result.get('symbol', 'unknown'))
                                msg = exec_result.get('message', '')
                                if signal != 'hold':
                                    logger.info(f"  TRADE: {symbol}: {msg}")
                    else:
                        error = result.get('error', 'Unknown error')
                        logger.warning(f"Model {model_id} failed: {error}")

                except Exception as e:
                    logger.error(f"Model {model_id} exception: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    continue

            interval_seconds = get_trading_interval_seconds()
            interval_minutes = interval_seconds / 60
            logger.info(f"\n{'='*60}")
            logger.info(f"SLEEP: Waiting {interval_minutes:.1f} minute(s) for next cycle")
            logger.info(f"{'='*60}\n")

            time.sleep(interval_seconds)

        except Exception as e:
            logger.critical(f"\nTrading loop error: {e}")
            import traceback
            logger.critical(traceback.format_exc())
            logger.info("RETRY: Retrying in 60 seconds\n")
            time.sleep(60)

    logger.info("Trading loop stopped")

# ============ Page Routes ============

# 后台服务初始化标志（延迟初始化，确保所有函数都已定义）
_background_services_initialized = False

@app.before_request
def _ensure_background_services():
    """确保后台服务已启动（在第一次请求时调用）"""
    global _background_services_initialized
    if not _background_services_initialized:
        _init_background_services()
        _background_services_initialized = True

@app.after_request
def after_request(response):
    """添加 CORS 响应头，确保所有请求都能正确处理"""
    # 对于所有 API 请求，添加 CORS 头
    if request.path.startswith('/api/'):
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        response.headers.add('Access-Control-Max-Age', '3600')
    return response

@app.route('/')
def index():
    """Main page route - 返回简单的状态信息，不渲染模板"""
    return jsonify({
        'status': 'running',
        'message': 'AI Future Trade Backend API',
        'version': __version__,
        'frontend_url': 'http://localhost:3000',
        'api_endpoint': '/api/'
    })

@app.route('/lib/<path:filename>')
def serve_lib_file(filename):
    """Serve files from static/lib/ directory"""
    from flask import send_from_directory
    import os
    lib_path = os.path.join(app.root_path, 'static', 'lib')
    return send_from_directory(lib_path, filename)

# ============ Provider API Endpoints ============

@app.route('/api/providers', methods=['GET'])
def get_providers():
    """Get all API providers"""
    providers = db.get_all_providers()
    return jsonify(providers)

@app.route('/api/providers', methods=['POST'])
def add_provider():
    """Add new API provider"""
    data = request.json
    try:
        provider_id = db.add_provider(
            name=data['name'],
            api_url=data['api_url'],
            api_key=data['api_key'],
            models=data.get('models', ''),
            provider_type=data.get('provider_type', 'openai')
        )
        return jsonify({'id': provider_id, 'message': 'Provider added successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/providers/<int:provider_id>', methods=['DELETE', 'OPTIONS'])
def delete_provider(provider_id):
    """Delete API provider"""
    # 处理 OPTIONS 预检请求
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Methods', 'DELETE, OPTIONS')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        return response
    
    try:
        db.delete_provider(provider_id)
        logger.info(f"Provider {provider_id} deleted successfully")
        return jsonify({'success': True, 'message': 'Provider deleted successfully'})
    except Exception as e:
        logger.error(f"Failed to delete provider {provider_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/providers/models', methods=['POST'])
def fetch_provider_models():
    """Fetch available models from provider's API"""
    data = request.json
    api_url = data.get('api_url')
    api_key = data.get('api_key')

    if not api_url or not api_key:
        return jsonify({'error': 'API URL and key are required'}), 400

    try:
        models = []

        # Try to detect provider type and call appropriate API
        if 'openai.com' in api_url.lower():
            import requests
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            response = requests.get(f'{api_url}/models', headers=headers, timeout=10)
            if response.status_code == 200:
                result = response.json()
                models = [m['id'] for m in result.get('data', []) if 'gpt' in m['id'].lower()]
        elif 'deepseek' in api_url.lower():
            import requests
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            response = requests.get(f'{api_url}/models', headers=headers, timeout=10)
            if response.status_code == 200:
                result = response.json()
                models = [m['id'] for m in result.get('data', [])]
        else:
            # Default: return common model names
            models = ['gpt-3.5-turbo', 'gpt-4', 'gpt-4-turbo']

        return jsonify({'models': models})
    except Exception as e:
        logger.error(f"Fetch models failed: {e}")
        return jsonify({'error': f'Failed to fetch models: {str(e)}'}), 500

# ============ Futures Configuration API Endpoints ============

@app.route('/api/futures', methods=['GET'])
def list_futures():
    """Get all futures configurations"""
    try:
        futures = db.get_futures()
        return jsonify(futures)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/futures', methods=['POST'])
def add_future_config():
    """Add new future configuration"""
    data = request.json or {}
    symbol = data.get('symbol', '').strip().upper()
    contract_symbol = data.get('contract_symbol', '').strip().upper()
    name = data.get('name', '').strip()
    exchange = data.get('exchange', 'BINANCE_FUTURES').strip().upper()
    link = (data.get('link') or '').strip()
    sort_order = data.get('sort_order')

    if not all([symbol, contract_symbol, name]):
        return jsonify({'error': 'symbol, contract_symbol, name are required'}), 400

    try:
        sort_order = int(sort_order)
    except (TypeError, ValueError):
        sort_order = 0

    try:
        future_id = db.add_future(
            symbol=symbol,
            contract_symbol=contract_symbol,
            name=name,
            exchange=exchange,
            link=link or None,
            sort_order=sort_order
        )
        return jsonify({'id': future_id, 'message': 'Future added successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/futures/<int:future_id>', methods=['DELETE', 'OPTIONS'])
def delete_future_config(future_id):
    """Delete future configuration"""
    # 处理 OPTIONS 预检请求
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Methods', 'DELETE, OPTIONS')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        return response
    
    try:
        db.delete_future(future_id)
        logger.info(f"Future {future_id} deleted successfully")
        return jsonify({'success': True, 'message': 'Future deleted successfully'})
    except Exception as e:
        logger.error(f"Failed to delete future {future_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ Model API Endpoints ============

@app.route('/api/models', methods=['GET'])
def get_models():
    """Get all trading models"""
    models = db.get_all_models()
    return jsonify(models)

@app.route('/api/models', methods=['POST'])
def add_model():
    """Add new trading model"""
    data = request.json or {}
    try:
        provider = db.get_provider(data['provider_id'])
        if not provider:
            return jsonify({'error': 'Provider not found'}), 404

        model_id = db.add_model(
            name=data['name'],
            provider_id=data['provider_id'],
            model_name=data['model_name'],
            initial_capital=float(data.get('initial_capital', 100000)),
            leverage=int(data.get('leverage', 10))
        )

        model = db.get_model(model_id)
        provider = db.get_provider(model['provider_id'])
        if not provider:
            return jsonify({'error': 'Provider not found'}), 404

        trading_engines[model_id] = TradingEngine(
            model_id=model_id,
            db=db,
            market_fetcher=market_fetcher,
            ai_trader=AITrader(
                provider_type=provider['provider_type'],
                api_key=provider['api_key'],
                api_url=provider['api_url'],
                model_name=model['model_name']
            ),
            trade_fee_rate=TRADE_FEE_RATE
        )
        logger.info(f"Model {model_id} ({data['name']}) initialized")

        return jsonify({'id': model_id, 'message': 'Model added successfully'})

    except Exception as e:
        logger.error(f"Failed to add model: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<int:model_id>', methods=['DELETE', 'OPTIONS'])
def delete_model(model_id):
    """Delete trading model"""
    # 处理 OPTIONS 预检请求
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Methods', 'DELETE, OPTIONS')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        return response
    
    try:
        model = db.get_model(model_id)
        model_name = model['name'] if model else f"ID-{model_id}"

        db.delete_model(model_id)
        if model_id in trading_engines:
            del trading_engines[model_id]

        logger.info(f"Model {model_id} ({model_name}) deleted")
        return jsonify({'success': True, 'message': 'Model deleted successfully'})
    except Exception as e:
        logger.error(f"Delete model {model_id} failed: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/models/<int:model_id>/portfolio', methods=['GET'])
def get_portfolio(model_id):
    """Get model portfolio data"""
    model = db.get_model(model_id)
    if not model:
        return jsonify({'error': f'Model {model_id} not found'}), 404

    symbols = get_tracked_symbols()
    prices_data = market_fetcher.get_prices(symbols)
    current_prices = {symbol: data['price'] for symbol, data in prices_data.items()}

    try:
        portfolio = db.get_portfolio(model_id, current_prices)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 404

    account_value = db.get_account_value_history(model_id, limit=100)

    return jsonify({
        'portfolio': portfolio,
        'account_value_history': account_value,
        'auto_trading_enabled': bool(model.get('auto_trading_enabled', 1)),
        'leverage': model.get('leverage', 10)
    })

@app.route('/api/models/<int:model_id>/trades', methods=['GET'])
def get_trades(model_id):
    """Get model trade history"""
    limit = request.args.get('limit', 50, type=int)
    trades = db.get_trades(model_id, limit=limit)
    return jsonify(trades)

@app.route('/api/models/<int:model_id>/conversations', methods=['GET'])
def get_conversations(model_id):
    """Get model conversation history"""
    limit = request.args.get('limit', 20, type=int)
    conversations = db.get_conversations(model_id, limit=limit)
    return jsonify(conversations)

@app.route('/api/models/<int:model_id>/prompts', methods=['GET'])
def get_model_prompts(model_id):
    """Get model prompt configuration"""
    model = db.get_model(model_id)
    if not model:
        return jsonify({'error': 'Model not found'}), 404

    prompt_config = db.get_model_prompt(model_id) or {}
    buy_prompt = prompt_config.get('buy_prompt') or DEFAULT_BUY_CONSTRAINTS
    sell_prompt = prompt_config.get('sell_prompt') or DEFAULT_SELL_CONSTRAINTS

    return jsonify({
        'model_id': model_id,
        'model_name': model.get('name'),
        'buy_prompt': buy_prompt,
        'sell_prompt': sell_prompt,
        'has_custom': bool(prompt_config),
        'updated_at': prompt_config.get('updated_at') if prompt_config else None
    })

@app.route('/api/models/<int:model_id>/prompts', methods=['PUT'])
def update_model_prompts(model_id):
    """Update model prompt configuration"""
    model = db.get_model(model_id)
    if not model:
        return jsonify({'error': 'Model not found'}), 404

    data = request.json or {}
    buy_prompt = data.get('buy_prompt')
    sell_prompt = data.get('sell_prompt')

    success = db.upsert_model_prompt(model_id, buy_prompt, sell_prompt)
    if not success:
        return jsonify({'error': 'Failed to update prompts'}), 500

    return jsonify({'success': True, 'message': 'Prompts updated successfully'})

@app.route('/api/models/<int:model_id>/leverage', methods=['POST'])
def update_model_leverage(model_id):
    """Update model leverage"""
    data = request.json or {}
    if 'leverage' not in data:
        return jsonify({'error': 'leverage is required'}), 400

    model = db.get_model(model_id)
    if not model:
        return jsonify({'error': 'Model not found'}), 404

    leverage = int(data.get('leverage', 0))
    leverage = max(0, leverage)
    if not db.set_model_leverage(model_id, leverage):
        return jsonify({'error': 'Failed to update leverage'}), 500

    return jsonify({'model_id': model_id, 'leverage': leverage})

@app.route('/api/models/<int:model_id>/execute', methods=['POST'])
def execute_trading(model_id):
    """Execute trading cycle for a model"""
    if model_id not in trading_engines:
        engine, error = init_trading_engine_for_model(model_id)
        if error:
            return jsonify({'error': error}), 404
    else:
        engine = trading_engines[model_id]

    # Manual execution enables auto trading
    db.set_model_auto_trading(model_id, True)

    try:
        result = engine.execute_trading_cycle()
        result['auto_trading_enabled'] = True
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<int:model_id>/auto-trading', methods=['POST'])
def set_model_auto_trading(model_id):
    """Enable or disable auto trading for a model"""
    data = request.json or {}
    if 'enabled' not in data:
        return jsonify({'error': 'enabled flag is required'}), 400

    model = db.get_model(model_id)
    if not model:
        return jsonify({'error': 'Model not found'}), 404

    enabled = bool(data.get('enabled'))
    success = db.set_model_auto_trading(model_id, enabled)
    if not success:
        return jsonify({'error': 'Failed to update model status'}), 500

    if enabled and model_id not in trading_engines:
        init_trading_engine_for_model(model_id)

    return jsonify({'model_id': model_id, 'auto_trading_enabled': enabled})

@app.route('/api/aggregated/portfolio', methods=['GET'])
def get_aggregated_portfolio():
    """Get aggregated portfolio data across all models"""
    symbols = get_tracked_symbols()
    prices_data = market_fetcher.get_current_prices(symbols)
    current_prices = {symbol: data['price'] for symbol, data in prices_data.items()}

    models = db.get_all_models()
    total_portfolio = {
        'total_value': 0,
        'cash': 0,
        'positions_value': 0,
        'realized_pnl': 0,
        'unrealized_pnl': 0,
        'initial_capital': 0,
        'positions': []
    }

    all_positions = {}

    for model in models:
        portfolio = db.get_portfolio(model['id'], current_prices)
        if portfolio:
            total_portfolio['total_value'] += portfolio.get('total_value', 0)
            total_portfolio['cash'] += portfolio.get('cash', 0)
            total_portfolio['positions_value'] += portfolio.get('positions_value', 0)
            total_portfolio['realized_pnl'] += portfolio.get('realized_pnl', 0)
            total_portfolio['unrealized_pnl'] += portfolio.get('unrealized_pnl', 0)
            total_portfolio['initial_capital'] += portfolio.get('initial_capital', 0)

            # Aggregate positions by future and side
            for pos in portfolio.get('positions', []):
                key = f"{pos['future']}_{pos['side']}"
                if key not in all_positions:
                    all_positions[key] = {
                        'future': pos['future'],
                        'side': pos['side'],
                        'quantity': 0,
                        'avg_price': 0,
                        'total_cost': 0,
                        'leverage': pos['leverage'],
                        'current_price': pos['current_price'],
                        'pnl': 0
                    }

                # Weighted average calculation
                current_pos = all_positions[key]
                current_cost = current_pos['quantity'] * current_pos['avg_price']
                new_cost = pos['quantity'] * pos['avg_price']
                total_quantity = current_pos['quantity'] + pos['quantity']

                if total_quantity > 0:
                    current_pos['avg_price'] = (current_cost + new_cost) / total_quantity
                    current_pos['quantity'] = total_quantity
                    current_pos['total_cost'] = current_cost + new_cost
                    current_pos['pnl'] = (pos['current_price'] - current_pos['avg_price']) * total_quantity

    total_portfolio['positions'] = list(all_positions.values())
    chart_data = db.get_multi_model_chart_data(limit=100)

    return jsonify({
        'portfolio': total_portfolio,
        'chart_data': chart_data,
        'model_count': len(models)
    })

# ============ Market Data API Endpoints ============

@app.route('/api/market/prices', methods=['GET'])
def get_market_prices():
    """Get current market prices for both configured futures and model positions"""
    # 获取配置的合约
    configured_symbols = get_tracked_symbols()
    configured_prices = market_fetcher.get_prices(configured_symbols)
    
    # 为配置的合约添加来源标记
    for symbol in configured_prices:
        configured_prices[symbol]['source'] = 'configured'
    
    # 获取所有模型的持仓合约
    models = db.get_all_models()
    position_symbols = set()
    for model in models:
        try:
            portfolio = db.get_portfolio(model['id'], {})
            for pos in portfolio.get('positions', []):
                if pos.get('future'):
                    position_symbols.add(pos['future'])
        except Exception:
            continue
    
    # 获取持仓合约的价格数据（排除已配置的合约，避免重复）
    position_symbols = [s for s in position_symbols if s not in configured_symbols]
    if position_symbols:
        position_prices = market_fetcher.get_prices(position_symbols)
        # 为持仓合约添加来源标记
        for symbol in position_prices:
            position_prices[symbol]['source'] = 'position'
        # 合并数据
        configured_prices.update(position_prices)
    
    return jsonify(configured_prices)

@app.route('/api/market/indicators/<symbol>', methods=['GET'])
def get_market_indicators(symbol):
    """Get technical indicators for a specific symbol
    
    从币安API实时获取并计算技术指标数据，包括：
    - K线数据（开高低收、成交量）
    - MA均线（5、20、60、99周期）
    - MACD指标（DIF、DEA、BAR）
    - RSI指标（RSI6、RSI9）
    - 成交量（VOL）
    
    时间框架：1周、1天、4小时、1小时、15分钟、5分钟、1分钟
    
    Args:
        symbol: 交易对符号（如 'BTC'）
        
    Returns:
        技术指标数据字典，格式：{'timeframes': {1w: {...}, 1d: {...}, ...}}
    """
    try:
        indicators = market_fetcher.calculate_technical_indicators(symbol)
        if not indicators:
            return jsonify({
                'symbol': symbol,
                'timeframes': {},
                'error': '无法获取技术指标数据'
            }), 200
        
        return jsonify({
            'symbol': symbol,
            **indicators
        })
    except Exception as e:
        logger.error(f"[API] Failed to get indicators for {symbol}: {e}", exc_info=True)
        return jsonify({
            'symbol': symbol,
            'timeframes': {},
            'error': str(e)
        }), 500

@app.route('/api/market/leaderboard', methods=['GET'])
def get_market_leaderboard():
    """Get market leaderboard data
    
    返回完整的涨跌幅榜数据：
    - gainers: 涨幅榜TOP 10（按涨幅从高到低排序）
    - losers: 跌幅榜TOP 10（按跌幅从低到高排序，跌幅为负值）
    
    前端通过轮询此接口获取数据，整体刷新渲染
    """
    limit = request.args.get('limit', type=int) or 10  # 默认10条，涨10个，跌10个
    force = request.args.get('force', default=0, type=int)
    
    try:
        # 获取涨跌幅榜数据（涨10个，跌10个）
        data = market_fetcher.sync_leaderboard(force=bool(force), limit=limit)
        
        # 确保返回完整数据格式
        result = {
            'gainers': data.get('gainers', [])[:limit],  # 确保最多返回limit条
            'losers': data.get('losers', [])[:limit],   # 确保最多返回limit条
            'timestamp': int(datetime.now().timestamp() * 1000)  # 添加时间戳，便于前端判断数据新鲜度
        }
        
        gainers_count = len(result['gainers'])
        losers_count = len(result['losers'])
        logger.debug(f"[API] 涨跌幅榜数据返回: 涨幅榜 {gainers_count} 条, 跌幅榜 {losers_count} 条")
        
        return jsonify(result)
    except Exception as exc:
        logger.error(f"Failed to load leaderboard: {exc}", exc_info=True)
        return jsonify({'error': str(exc), 'gainers': [], 'losers': []}), 500

@app.route('/api/clickhouse/leaderboard/status', methods=['GET'])
def get_clickhouse_leaderboard_status():
    """Get ClickHouse leaderboard sync status
    
    返回状态信息：
    - running: 运行状态（True表示运行中，False表示已停止）
    - thread_alive: 线程是否存活
    - 默认状态为运行状态（running=True）
    """
    global clickhouse_leaderboard_running, clickhouse_leaderboard_thread
    
    # 检查线程实际状态，如果线程不存在或已死亡，但用户没有明确停止，则认为是运行状态
    thread_alive = clickhouse_leaderboard_thread.is_alive() if clickhouse_leaderboard_thread else False
    
    # 如果线程已死亡但运行状态为True，说明线程意外退出，但用户期望运行
    # 这种情况下，返回running=True，让前端显示运行状态，监控线程会自动重启
    actual_running = clickhouse_leaderboard_running or (not clickhouse_leaderboard_stop_event.is_set() and thread_alive)
    
    return jsonify({
        'running': actual_running,
        'thread_alive': thread_alive
    })

@app.route('/api/clickhouse/leaderboard/control', methods=['POST'])
def control_clickhouse_leaderboard():
    """Control ClickHouse leaderboard sync (start/stop)"""
    data = request.json or {}
    action = data.get('action', '').lower()
    
    if action == 'start':
        start_clickhouse_leaderboard_sync()
        return jsonify({'message': 'ClickHouse leaderboard sync started', 'running': True})
    elif action == 'stop':
        stop_clickhouse_leaderboard_sync()
        return jsonify({'message': 'ClickHouse leaderboard sync stopped', 'running': False})

@app.route('/api/market/klines', methods=['GET'])
def get_market_klines():
    """获取K线历史数据
    
    参数:
        symbol: 交易对符号（如 'BTCUSDT'）
        interval: 时间间隔（'1m', '5m', '15m', '1h', '4h', '1d', '1w'）
        limit: 返回的最大记录数，默认值根据interval不同：
               - 1d（1天）：默认120条，最大120条
               - 1w（1周）：默认20条，最大20条
               - 其他interval：默认500条，最大500条
        start_time: 开始时间（可选，ISO格式字符串）
        end_time: 结束时间（可选，ISO格式字符串）
    """
    try:
        from datetime import datetime
        from common.config import KLINE_DATA_SOURCE
        
        symbol = request.args.get('symbol', '').upper()
        interval = request.args.get('interval', '5m')
        # 根据数据源设置不同的默认limit
        source = KLINE_DATA_SOURCE  # 从配置文件获取数据源，不再从请求参数获取
        
        # 根据不同的interval设置不同的默认limit
        # 1d（1天）：120条（约4个月历史数据）
        # 1w（1周）：20条（约5个月历史数据）
        # 其他interval：500条
        interval_default_limits = {
            '1d': 120,  # 1天周期，默认120条
            '1w': 20,   # 1周周期，默认20条
        }
        default_limit = interval_default_limits.get(interval, 500)  # 其他周期默认500条
        
        limit = request.args.get('limit', type=int) or default_limit
        start_time_str = request.args.get('start_time')
        end_time_str = request.args.get('end_time')
        
        if not symbol:
            return jsonify({'error': 'symbol parameter is required'}), 400
        
        # 验证interval
        valid_intervals = ['1m', '5m', '15m', '1h', '4h', '1d', '1w']
        if interval not in valid_intervals:
            return jsonify({'error': f'invalid interval. Must be one of: {valid_intervals}'}), 400
        
        # 解析时间参数
        start_time = None
        end_time = None
        start_timestamp = None
        end_timestamp = None
        
        if start_time_str:
            try:
                start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                start_timestamp = int(start_time.timestamp() * 1000)  # 转换为毫秒
            except ValueError:
                return jsonify({'error': 'invalid start_time format. Use ISO format'}), 400
        
        if end_time_str:
            try:
                end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
                end_timestamp = int(end_time.timestamp() * 1000)  # 转换为毫秒
            except ValueError:
                return jsonify({'error': 'invalid end_time format. Use ISO format'}), 400
        
        # 获取客户端IP地址
        client_ip = request.remote_addr
        
        # 查询K线数据，添加客户端IP信息
        logger.info(f"[API] 获取K线历史数据请求: symbol={symbol}, interval={interval}, limit={limit}, source={source}, start_time={start_time_str}, end_time={end_time_str}, client_ip={client_ip}")
        
        klines = []
        
        if source == 'db':
            # 从数据库获取数据
            from common.database_clickhouse import ClickHouseDatabase
            logger.info(f"[API] 从数据库获取K线数据: symbol={symbol}, interval={interval}")
            clickhouse_db = ClickHouseDatabase(auto_init_tables=False)
            klines = clickhouse_db.get_market_klines(
                symbol=symbol,
                interval=interval,
                limit=limit,
                start_time=start_time,
                end_time=end_time
            )
        else:
            # 从SDK获取数据（默认）
            # 使用全局market_fetcher变量，而非重新导入
            
            # SDK模式下根据不同的interval设置不同的最大limit
            # 1d（1天）：最大120条
            # 1w（1周）：最大20条
            # 其他interval：最大500条
            interval_max_limits = {
                '1d': 120,  # 1天周期，最大120条
                '1w': 20,   # 1周周期，最大20条
            }
            max_limit = interval_max_limits.get(interval, 500)  # 其他周期最大500条
            
            sdk_limit = limit
            if sdk_limit > max_limit:
                sdk_limit = max_limit
                logger.debug(f"[API] SDK模式下限制limit为{max_limit}（interval={interval}），原请求limit={limit}")
            
            logger.info(f"[API] 从SDK获取K线数据: symbol={symbol}, interval={interval}, limit={sdk_limit}")
            
            # 调用SDK获取K线数据（只传入endTime，不传入startTime）
            klines_raw = market_fetcher._futures_client.get_klines(
                symbol=symbol,
                interval=interval,
                limit=sdk_limit,
                startTime=start_timestamp,  # 如果提供了startTime，也传入
                endTime=end_timestamp  # 只传入endTime（或传入的endTime）
            )
            
            if not klines_raw or len(klines_raw) == 0:
                logger.warning(f"[API] SDK未返回K线数据: symbol={symbol}, interval={interval}")
                klines = []
            else:
                # SDK返回的数据是倒序的（从新到旧），数组[0]是最新的K线，数组[-1]是最旧的K线
                # 注意：K线页面已改为仅使用历史数据，不再订阅实时K线更新，因此保留所有数据（包括最新K线）
                logger.debug(f"[API] SDK返回{len(klines_raw)}条K线数据（倒序：最新→最旧），保留所有数据（包括最新K线）")
                
                # 转换SDK返回数据为统一格式，价格保留6位小数
                formatted_klines = []
                for kline in klines_raw:
                    # 获取原始价格数据（可能是字符串或数字）
                    raw_open = kline.get('open', 0)
                    raw_high = kline.get('high', 0)
                    raw_low = kline.get('low', 0)
                    raw_close = kline.get('close', 0)
                    
                    # 转换为浮点数并保留6位小数
                    formatted_open = round(float(raw_open) if raw_open else 0.0, 6)
                    formatted_high = round(float(raw_high) if raw_high else 0.0, 6)
                    formatted_low = round(float(raw_low) if raw_low else 0.0, 6)
                    formatted_close = round(float(raw_close) if raw_close else 0.0, 6)
                    
                    formatted_klines.append({
                        'timestamp': kline.get('open_time', 0),
                        'open': formatted_open,
                        'high': formatted_high,
                        'low': formatted_low,
                        'close': formatted_close,
                        'volume': float(kline.get('volume', 0)),
                        'turnover': float(kline.get('quote_asset_volume', 0))
                    })
                
                # 由于SDK返回的数据是倒序的（从新到旧），需要按timestamp升序排序（从旧到新）
                # 确保与数据库模式和前端期望的数据顺序一致
                # 前端K线图表从左到右显示，左边是最旧的数据，右边是最新的数据，所以需要从旧到新的顺序
                formatted_klines.sort(key=lambda x: x.get('timestamp', 0))
                klines = formatted_klines
                
                logger.info(f"[API] SDK查询完成，共获取 {len(klines)} 条K线数据（已排序为从旧到新，包含最新K线）")
                
                # 验证数据顺序：确保第一条时间戳小于最后一条时间戳（从旧到新，timestamp升序）
                # 前端K线图表从左到右显示，左边是最旧的数据（第一条），右边是最新的数据（最后一条）
                # 所以数据顺序应该是：第一条（最旧）< 最后一条（最新）
                if len(klines) > 1:
                    first_timestamp = klines[0].get('timestamp', 0)
                    last_timestamp = klines[-1].get('timestamp', 0)
                    
                    # 将时间戳转换为datetime格式便于排查
                    def format_timestamp_for_validation(ts):
                        """将timestamp（毫秒）转换为datetime字符串用于验证"""
                        if ts == 0 or ts is None:
                            return 'N/A'
                        try:
                            from datetime import timezone as tz
                            dt = datetime.fromtimestamp(ts / 1000, tz=tz.utc)
                            return dt.strftime('%Y-%m-%d %H:%M:%S UTC')
                        except (ValueError, TypeError, OSError) as e:
                            return f'{ts} (转换失败: {e})'
                    
                    first_timestamp_dt = format_timestamp_for_validation(first_timestamp)
                    last_timestamp_dt = format_timestamp_for_validation(last_timestamp)
                    
                    if first_timestamp >= last_timestamp:
                        logger.warning(
                            f"[API] ⚠️ 数据顺序异常：第一条时间戳({first_timestamp}, {first_timestamp_dt}) >= "
                            f"最后一条({last_timestamp}, {last_timestamp_dt})，"
                            f"重新排序以确保从旧到新的顺序（与前端K线图表从左到右的要求一致）"
                        )
                        klines.sort(key=lambda x: x.get('timestamp', 0))
                        # 重新验证
                        first_timestamp = klines[0].get('timestamp', 0)
                        last_timestamp = klines[-1].get('timestamp', 0)
                        first_timestamp_dt = format_timestamp_for_validation(first_timestamp)
                        last_timestamp_dt = format_timestamp_for_validation(last_timestamp)
                        logger.debug(
                            f"[API] ✓ 重新排序后：第一条时间戳={first_timestamp} ({first_timestamp_dt}), "
                            f"最后一条时间戳={last_timestamp} ({last_timestamp_dt})"
                        )
                    else:
                        logger.debug(
                            f"[API] ✓ 数据顺序验证通过：第一条时间戳={first_timestamp} ({first_timestamp_dt}) < "
                            f"最后一条时间戳={last_timestamp} ({last_timestamp_dt}) "
                            f"（从旧到新，符合前端K线图表从左到右的显示要求）"
                        )
        
        # 记录返回数据信息，添加客户端IP
        klines_count = len(klines) if klines else 0
        logger.info(f"[API] 获取K线历史数据查询完成: symbol={symbol}, interval={interval}, source={source}, 返回数据条数={klines_count}, client_ip={client_ip}")
        
        if klines_count > 0:
            # 记录第一条和最后一条数据的时间戳（用于调试）
            first_kline = klines[0]
            last_kline = klines[-1]
            first_timestamp = first_kline.get('timestamp', 'N/A')
            last_timestamp = last_kline.get('timestamp', 'N/A')
            
            # 将timestamp转换为datetime格式便于排查
            def format_timestamp(ts):
                """将timestamp（毫秒）转换为datetime字符串"""
                if ts == 'N/A' or ts is None:
                    return 'N/A'
                try:
                    # timestamp是毫秒时间戳，需要除以1000
                    from datetime import timezone as tz
                    dt = datetime.fromtimestamp(ts / 1000, tz=tz.utc)
                    return dt.strftime('%Y-%m-%d %H:%M:%S UTC')
                except (ValueError, TypeError, OSError) as e:
                    return f'{ts} (转换失败: {e})'
            
            first_timestamp_dt = format_timestamp(first_timestamp)
            last_timestamp_dt = format_timestamp(last_timestamp)
            
            logger.info(
                f"[API] 获取K线历史数据时间范围: "
                f"第一条timestamp={first_timestamp} ({first_timestamp_dt}), "
                f"最后一条timestamp={last_timestamp} ({last_timestamp_dt}), "
                f"共返回{klines_count}条数据, client_ip={client_ip}"
            )
            
            # 记录第一条数据的详细信息（用于调试数据格式）
            logger.debug(f"[API] 获取K线历史数据示例（第一条）: {first_kline}")
            logger.debug(f"[API] 获取K线历史数据示例（最后一条）: {last_kline}")
        else:
            logger.warning(f"[API]  未找到K线历史数据: symbol={symbol}, interval={interval}, client_ip={client_ip}")
        
        response_data = {
            'symbol': symbol,
            'interval': interval,
            'source': source,
            'data': klines,
            'count': klines_count  # 添加数据条数字段，便于前端调试
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"[API] 获取K线数据失败: symbol={symbol}, interval={interval}, source={source}, error={e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@socketio.on('leaderboard:request')
def handle_leaderboard_request(payload=None):
    """WebSocket handler for leaderboard requests (已废弃，前端已改为轮询方式)
    
    注意：涨跌幅榜已改为前端轮询方式获取数据，不再通过WebSocket推送。
    此handler保留以兼容旧版本前端，但建议前端使用 /api/market/leaderboard API接口。
    """
    payload = payload or {}
    limit = payload.get('limit', 10)
    
    logger.warning(f"[Leaderboard Request] WebSocket leaderboard:request 已废弃，建议使用 /api/market/leaderboard API接口（轮询方式）")
    
    try:
        # 获取涨跌榜数据
        data = market_fetcher.sync_leaderboard(force=False, limit=limit)
        
        # 发送数据更新事件（兼容旧版本前端）
        emit('leaderboard:update', data)
        logger.debug(f"[Leaderboard Request] Leaderboard update emitted to client (兼容模式)")
        
    except Exception as exc:
        logger.error(f"[Leaderboard Request] Failed to fetch leaderboard data: limit={limit}, error={str(exc)}", exc_info=True)
        emit('leaderboard:error', {'message': str(exc)})

@socketio.on('klines:subscribe')
def handle_klines_subscribe(payload=None):
    """WebSocket handler for K线订阅请求
    
    参数:
        symbol: 交易对符号（如 'BTCUSDT'）
        interval: 时间间隔（'1m', '5m', '15m', '1h', '4h', '1d', '1w'）
    """
    payload = payload or {}
    symbol = payload.get('symbol', '').upper()
    interval = payload.get('interval', '5m')
    
    # 记录函数调用信息
    logger.info(f"[KLine Subscribe] Received subscription request: payload={payload}, symbol={symbol}, interval={interval}")
    
    if not symbol:
        logger.warning(f"[KLine Subscribe] Subscription failed: symbol is required, payload={payload}")
        emit('klines:error', {'message': 'symbol is required'})
        return
    
    valid_intervals = ['1m', '5m', '15m', '1h', '4h', '1d', '1w']
    if interval not in valid_intervals:
        logger.warning(f"[KLine Subscribe] Subscription failed: invalid interval '{interval}', must be one of {valid_intervals}")
        emit('klines:error', {'message': f'invalid interval. Must be one of: {valid_intervals}'})
        return
    
    # 加入房间（按symbol和interval分组）
    room = f'klines:{symbol}:{interval}'
    from flask_socketio import join_room
    join_room(room)
    logger.debug(f"[KLine Subscribe] Client joined room: {room}")
    
    # 记录订阅前后的订阅数量
    with kline_push_lock:
        previous_count = len(kline_subscriptions)
        kline_subscriptions[room] = {
            'symbol': symbol,
            'interval': interval,
            'last_update_time': datetime.now()
        }
        current_count = len(kline_subscriptions)
    
    logger.info(f"[KLine Subscribe] Subscription added: room={room}, symbol={symbol}, interval={interval}, " \
                f"subscriptions_count: {previous_count} → {current_count}")
    
    # 启动推送工作线程（如果还没有启动）
    start_kline_push_worker()
    logger.debug(f"[KLine Subscribe] Push worker started/checked")
    
    # 发送订阅成功事件
    emit('klines:subscribed', {'symbol': symbol, 'interval': interval})
    logger.info(f"[KLine Subscribe] Subscription completed: symbol={symbol}, interval={interval}, room={room}, " \
                f"total_subscriptions={current_count}")

@socketio.on('klines:unsubscribe')
def handle_klines_unsubscribe(payload=None):
    """WebSocket handler for K线取消订阅"""
    payload = payload or {}
    symbol = payload.get('symbol', '').upper()
    interval = payload.get('interval', '5m')
    
    # 记录函数调用信息
    logger.info(f"[KLine Unsubscribe] Received unsubscribe request: payload={payload}, symbol={symbol}, interval={interval}")
    
    room = f'klines:{symbol}:{interval}'
    from flask_socketio import leave_room
    
    # 记录客户端离开房间信息
    logger.debug(f"[KLine Unsubscribe] Client leaving room: {room}")
    leave_room(room)
    
    # 移除订阅信息
    with kline_push_lock:
        previous_count = len(kline_subscriptions)
        was_subscribed = room in kline_subscriptions
        
        if was_subscribed:
            del kline_subscriptions[room]
            current_count = len(kline_subscriptions)
            logger.info(f"[KLine Unsubscribe] Subscription removed: room={room}, symbol={symbol}, interval={interval}, subscriptions_count: {previous_count} → {current_count}")
        else:
            current_count = previous_count
            logger.warning(f"[KLine Unsubscribe] Room not found in subscriptions: room={room}, symbol={symbol}, interval={interval}")
        
        # 检查是否还有活跃订阅，如果没有则关闭推送线程
        if not kline_subscriptions:
            kline_push_stop_event.set()
            logger.info("[KLine Unsubscribe] No active KLine subscriptions, stopping push thread")
    
    # 记录取消订阅完成信息
    logger.info(f"[KLine Unsubscribe] Client unsubscribed from klines: symbol={symbol}, interval={interval}, room={room}, was_subscribed={was_subscribed}")
    emit('klines:unsubscribed', {'symbol': symbol, 'interval': interval})

# K线实时推送相关变量
kline_subscriptions = {}  # 存储订阅信息: {room: {symbol, interval, last_update_time}}
kline_push_thread = None
kline_push_stop_event = threading.Event()
kline_push_lock = threading.Lock()

def push_realtime_kline(symbol: str, interval: str):
    """推送实时K线数据到订阅的客户端"""
    try:
        if not market_fetcher._futures_client:
            return
        
        # 获取最新K线数据
        contract_symbol = market_fetcher._futures_client.format_symbol(symbol)
        klines = market_fetcher._futures_client.get_klines(
            contract_symbol,
            interval,
            limit=1
        )
        
        if klines and len(klines) > 0:
            latest_kline = klines[-1]
            # 转换为标准格式
            kline_data = {
                'timestamp': int(latest_kline.get('close_time', latest_kline.get('open_time', 0))),
                'open': float(latest_kline.get('open', 0)),
                'high': float(latest_kline.get('high', 0)),
                'low': float(latest_kline.get('low', 0)),
                'close': float(latest_kline.get('close', 0)),
                'volume': float(latest_kline.get('volume', 0)),
                'turnover': float(latest_kline.get('quote_asset_volume', 0))
            }
            
            # 推送到订阅的房间
            room = f'klines:{contract_symbol}:{interval}'
            socketio.emit('klines:update', {
                'symbol': contract_symbol,
                'interval': interval,
                'kline': kline_data
            }, room=room)
            
    except Exception as e:
        logger.error(f"Failed to push realtime kline for {symbol} {interval}: {e}", exc_info=True)

def _kline_push_loop():
    """后台循环任务：定期推送实时K线数据到订阅的客户端"""
    global kline_push_thread
    thread_id = threading.current_thread().ident
    logger.info(f"[KLine Push Worker-{thread_id}] K线实时推送循环启动")
    
    # 根据最小周期（1m）设置推送间隔
    push_interval = 5  # 每5秒推送一次
    
    while not kline_push_stop_event.is_set():
        try:
            with kline_push_lock:
                # 获取所有活跃的订阅
                active_subscriptions = dict(kline_subscriptions)
            
            if not active_subscriptions:
                # 没有订阅，等待一段时间后重试
                kline_push_stop_event.wait(push_interval)
                continue
            
            # 遍历所有订阅并推送数据
            for room, subscription_info in active_subscriptions.items():
                try:
                    symbol = subscription_info.get('symbol')
                    interval = subscription_info.get('interval')
                    
                    if symbol and interval:
                        push_realtime_kline(symbol, interval)
                except Exception as e:
                    logger.error(f"[KLine Push Worker] Error pushing kline for {room}: {e}", exc_info=True)
            
            # 等待指定间隔
            kline_push_stop_event.wait(push_interval)
            
        except Exception as e:
            logger.error(f"[KLine Push Worker-{thread_id}] Error in push loop: {e}", exc_info=True)
            kline_push_stop_event.wait(push_interval)
    
    logger.info(f"[KLine Push Worker-{thread_id}] K线实时推送循环停止")
    
    # 线程退出时重置状态，确保下次能正确启动
    with kline_push_lock:
        kline_push_stop_event.clear()
        kline_push_thread = None

def start_kline_push_worker():
    """启动K线实时推送工作线程"""
    global kline_push_thread
    if kline_push_thread and kline_push_thread.is_alive():
        return
    kline_push_stop_event.clear()
    kline_push_thread = threading.Thread(target=_kline_push_loop, daemon=True, name="KLinePushWorker")
    kline_push_thread.start()
    logger.info("[KLine Push] K线实时推送工作线程已启动")

# ============ Settings API Endpoints ============

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Get system settings"""
    try:
        settings = db.get_settings()
        return jsonify(settings)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/settings', methods=['PUT'])
def update_settings():
    """Update system settings"""
    try:
        data = request.json or {}
        trading_frequency_minutes = int(data.get('trading_frequency_minutes', 60))
        trading_fee_rate = float(data.get('trading_fee_rate', 0.001))
        show_system_prompt = 1 if data.get('show_system_prompt') in (True, 1, '1', 'true', 'True') else 0

        success = db.update_settings(
            trading_frequency_minutes,
            trading_fee_rate,
            show_system_prompt
        )

        if success:
            return jsonify({'success': True, 'message': 'Settings updated successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to update settings'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============ Version API Endpoints ============

@app.route('/api/version', methods=['GET'])
def get_version():
    """Get current version information"""
    return jsonify({
        'current_version': __version__
    })

@app.route('/api/check-update', methods=['GET'])
def check_update():
    """Check for application updates"""
    try:
        return jsonify({
            'update_available': False,
            'current_version': __version__,
            'latest_version': __version__,
            'error': None
        })
    except Exception as e:
        logger.error(f"Check update failed: {e}")
        return jsonify({
            'update_available': False,
            'current_version': __version__,
            'latest_version': __version__,
            'error': str(e)
        }), 500

# ============ Main Entry Point ============

if __name__ == '__main__':
    logger.info("\n" + "=" * 60)
    logger.info("AIFutureTrade Backend Service - Starting...")
    logger.info("=" * 60)
    logger.info("Initializing database...")

    # Initialize database and trading engines within application context
    with app.app_context():
        db.init_db()
        logger.info("Database initialized")
        logger.info("Initializing trading engines...")
        init_trading_engines()
        logger.info("Trading engines initialized")

    # Start background threads
    if auto_trading:
        trading_thread = threading.Thread(target=trading_loop, daemon=True)
        trading_thread.start()
        logger.info("Auto-trading enabled")

    # Start leaderboard workers
    logger.info("🚀 准备启动涨跌幅榜相关工作线程...")
    
    # 启动前端推送工作线程
    logger.info("📡 启动涨跌幅榜前端推送线程...")
    start_leaderboard_worker()
    logger.info("✅ 涨跌幅榜前端推送线程已启动")
    
    # 初始化后台服务（包括ClickHouse涨跌幅榜同步线程）
    logger.info("📊 初始化后台服务...")
    _init_background_services()
    
    logger.info("✅ 所有涨跌幅榜相关工作线程已启动完成")

    logger.info("\n" + "=" * 60)
    logger.info("AIFutureTrade Backend Service is running!")
    logger.info("API Server: http://0.0.0.0:5002")
    logger.info("WebSocket Server: ws://0.0.0.0:5002")
    logger.info("=" * 60 + "\n")

    # 开发环境：使用Werkzeug服务器
    # 生产环境：使用gunicorn + eventlet（见Dockerfile和gunicorn_config.py）
    # 通过环境变量USE_GUNICORN=true来使用gunicorn启动
    if os.getenv('USE_GUNICORN') == 'true':
        logger.info("Production mode: Use 'gunicorn --config gunicorn_config.py app:app' to start")
        # 生产环境应该使用gunicorn启动，这里只是提示
        socketio.run(
            app, 
            debug=False, 
            host='0.0.0.0', 
            port=5002, 
            use_reloader=False,
            allow_unsafe_werkzeug=True
        )
    else:
        # 开发环境
        socketio.run(
            app, 
            debug=False, 
            host='0.0.0.0', 
            port=5002, 
            use_reloader=False,
            allow_unsafe_werkzeug=True
        )
