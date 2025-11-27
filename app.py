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
from trading_engine import TradingEngine
from market_data import MarketDataFetcher
from ai_trader import AITrader
from database import Database
from version import __version__
from prompt_defaults import DEFAULT_BUY_CONSTRAINTS, DEFAULT_SELL_CONSTRAINTS

import config as app_config
import logging
import sys

# ============ Application Initialization ============

app = Flask(__name__)
CORS(app)
# 使用eventlet作为异步模式以获得更好的性能
# async_mode='eventlet' 提供更好的并发性能
socketio = SocketIO(
    app, 
    cors_allowed_origins="*",
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
clickhouse_leaderboard_running = False

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
            model_name=model['model_name']
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
                        model_name=model['model_name']
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
    后台循环任务：定期同步涨跌幅榜数据并推送到前端
    
    流程：
    1. 启动循环，记录启动信息
    2. 定期调用 sync_leaderboard 同步数据
    3. 如果同步成功，通过 WebSocket 推送到前端
    4. 等待指定间隔后继续下一次循环
    5. 收到停止信号时退出循环
    """
    thread_id = threading.current_thread().ident
    logger.info(f"[Leaderboard Worker-{thread_id}] ========== 涨跌幅榜同步循环启动 ==========")
    logger.info(f"[Leaderboard Worker-{thread_id}] 刷新间隔: {LEADERBOARD_REFRESH_INTERVAL} 秒")
    
    wait_seconds = max(5, LEADERBOARD_REFRESH_INTERVAL)
    cycle_count = 0
    
    while not leaderboard_stop_event.is_set():
        cycle_count += 1
        cycle_start_time = datetime.now()
        
        logger.info(f"[Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] ========== 开始同步涨跌幅榜 ==========")
        logger.info(f"[Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] 同步时间: {cycle_start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            # 调用同步方法（不强制刷新，使用缓存机制）
            logger.info(f"[Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] [步骤1] 调用 sync_leaderboard 同步数据...")
            sync_start_time = datetime.now()
            
            data = market_fetcher.sync_leaderboard(force=False)
            
            sync_duration = (datetime.now() - sync_start_time).total_seconds()
            logger.info(f"[Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] [步骤1] 数据同步完成, 耗时: {sync_duration:.2f} 秒")
            
            # 检查同步结果
            if data:
                gainers = data.get('gainers', [])
                losers = data.get('losers', [])
                gainers_count = len(gainers) if gainers else 0
                losers_count = len(losers) if losers else 0
                
                logger.info(f"[Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] [步骤2] 同步数据统计: "
                           f"涨幅榜={gainers_count} 条, 跌幅榜={losers_count} 条")
                
                # 记录涨幅榜前3名（如果有）
                if gainers_count > 0:
                    top_gainers = gainers[:3]
                    for idx, entry in enumerate(top_gainers):
                        logger.info(f"[Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] [步骤2.1] 涨幅榜 #{idx+1}: "
                                   f"{entry.get('symbol', 'N/A')} "
                                   f"价格=${entry.get('price', 0):.4f} "
                                   f"涨跌幅={entry.get('change_percent', 0):.2f}% "
                                   f"成交量=${entry.get('quote_volume', 0):.2f}")
                
                # 记录跌幅榜前3名（如果有）
                if losers_count > 0:
                    top_losers = losers[:3]
                    for idx, entry in enumerate(top_losers):
                        logger.info(f"[Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] [步骤2.2] 跌幅榜 #{idx+1}: "
                                   f"{entry.get('symbol', 'N/A')} "
                                   f"价格=${entry.get('price', 0):.4f} "
                                   f"涨跌幅={entry.get('change_percent', 0):.2f}% "
                                   f"成交量=${entry.get('quote_volume', 0):.2f}")
                
                # 通过 WebSocket 推送到前端
                logger.info(f"[Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] [步骤3] 通过 WebSocket 推送数据到前端...")
                emit_start_time = datetime.now()
                
                socketio.emit('leaderboard:update', data)
                
                emit_duration = (datetime.now() - emit_start_time).total_seconds()
                logger.info(f"[Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] [步骤3] WebSocket 推送完成, 耗时: {emit_duration:.3f} 秒")
                
            else:
                logger.warning(f"[Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] [步骤2] 同步返回空数据，跳过推送")
                
        except Exception as exc:
            cycle_duration = (datetime.now() - cycle_start_time).total_seconds()
            logger.error(f"[Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] ========== 涨跌幅榜同步失败 ==========")
            logger.error(f"[Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] 错误信息: {exc}")
            logger.error(f"[Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] 失败耗时: {cycle_duration:.2f} 秒")
            import traceback
            logger.error(f"[Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] 错误堆栈:\n{traceback.format_exc()}")
        
        # 计算本次循环总耗时
        cycle_duration = (datetime.now() - cycle_start_time).total_seconds()
        logger.info(f"[Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] ========== 同步循环完成 ==========")
        logger.info(f"[Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] 本次循环耗时: {cycle_duration:.2f} 秒")
        logger.info(f"[Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] 等待 {wait_seconds} 秒后开始下一次循环...")
        
        # 等待指定间隔（可被停止事件中断）
        leaderboard_stop_event.wait(wait_seconds)
    
    logger.info(f"[Leaderboard Worker-{thread_id}] ========== 涨跌幅榜同步循环停止 ==========")
    logger.info(f"[Leaderboard Worker-{thread_id}] 总循环次数: {cycle_count}")

def _clickhouse_leaderboard_loop():
    """
    后台循环任务：定期从 ClickHouse 24_market_tickers 表同步涨跌幅榜数据到 futures_leaderboard 表
    
    流程：
    1. 查询 ingestion_time 大于当前时间-5秒的去重合约数据
    2. 按涨跌类型分别查询前N名
    3. 先删除再新增，保证表中只有前N涨幅和前N跌幅
    4. 循环执行，默认间隔2秒
    """
    from database_clickhouse import ClickHouseDatabase
    
    thread_id = threading.current_thread().ident
    logger.info(f"[ClickHouse Leaderboard Worker-{thread_id}] ========== ClickHouse 涨幅榜同步循环启动 ==========")
    
    # 获取配置
    sync_interval = getattr(app_config, 'CLICKHOUSE_LEADERBOARD_SYNC_INTERVAL', 2)
    time_window = getattr(app_config, 'CLICKHOUSE_LEADERBOARD_TIME_WINDOW', 5)
    top_n = getattr(app_config, 'CLICKHOUSE_LEADERBOARD_TOP_N', 10)
    
    logger.info(f"[ClickHouse Leaderboard Worker-{thread_id}] 同步间隔: {sync_interval} 秒")
    logger.info(f"[ClickHouse Leaderboard Worker-{thread_id}] 时间窗口: {time_window} 秒")
    logger.info(f"[ClickHouse Leaderboard Worker-{thread_id}] 前N名: {top_n}")
    
    wait_seconds = max(1, sync_interval)
    cycle_count = 0
    
    try:
        db = ClickHouseDatabase(auto_init_tables=True)
    except Exception as exc:
        logger.error(f"[ClickHouse Leaderboard Worker-{thread_id}] 初始化 ClickHouse 连接失败: {exc}")
        return
    
    while not clickhouse_leaderboard_stop_event.is_set():
        cycle_count += 1
        cycle_start_time = datetime.now()
        
        logger.debug(f"[ClickHouse Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] 开始同步...")
        
        try:
            db.sync_leaderboard(
                time_window_seconds=time_window,
                top_n=top_n
            )
            
            cycle_duration = (datetime.now() - cycle_start_time).total_seconds()
            logger.debug(
                f"[ClickHouse Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] "
                f"同步完成, 耗时: {cycle_duration:.3f} 秒"
            )
        except Exception as exc:
            cycle_duration = (datetime.now() - cycle_start_time).total_seconds()
            logger.error(
                f"[ClickHouse Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] "
                f"同步失败: {exc}, 耗时: {cycle_duration:.3f} 秒"
            )
        
        # 等待指定间隔（可被停止事件中断）
        clickhouse_leaderboard_stop_event.wait(wait_seconds)
    
    logger.info(f"[ClickHouse Leaderboard Worker-{thread_id}] ========== ClickHouse 涨幅榜同步循环停止 ==========")
    logger.info(f"[ClickHouse Leaderboard Worker-{thread_id}] 总循环次数: {cycle_count}")

def start_clickhouse_leaderboard_sync():
    """启动 ClickHouse 涨幅榜同步线程"""
    global clickhouse_leaderboard_thread, clickhouse_leaderboard_running
    
    if clickhouse_leaderboard_thread and clickhouse_leaderboard_thread.is_alive():
        logger.warning("[ClickHouse Leaderboard] 同步线程已在运行")
        return
    
    clickhouse_leaderboard_stop_event.clear()
    clickhouse_leaderboard_running = True
    clickhouse_leaderboard_thread = threading.Thread(
        target=_clickhouse_leaderboard_loop,
        daemon=True,
        name="ClickHouseLeaderboardSync"
    )
    clickhouse_leaderboard_thread.start()
    logger.info("[ClickHouse Leaderboard] 同步线程已启动")

def stop_clickhouse_leaderboard_sync():
    """停止 ClickHouse 涨幅榜同步线程"""
    global clickhouse_leaderboard_running
    
    if not clickhouse_leaderboard_running:
        logger.warning("[ClickHouse Leaderboard] 同步线程未运行")
        return
    
    clickhouse_leaderboard_running = False
    clickhouse_leaderboard_stop_event.set()
    
    if clickhouse_leaderboard_thread and clickhouse_leaderboard_thread.is_alive():
        clickhouse_leaderboard_thread.join(timeout=5)
        logger.info("[ClickHouse Leaderboard] 同步线程已停止")
    else:
        logger.info("[ClickHouse Leaderboard] 同步线程已停止（未运行）")

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

@app.route('/')
def index():
    """Main page route"""
    return render_template('index.html')

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

@app.route('/api/providers/<int:provider_id>', methods=['DELETE'])
def delete_provider(provider_id):
    """Delete API provider"""
    try:
        db.delete_provider(provider_id)
        return jsonify({'message': 'Provider deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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

@app.route('/api/futures/<int:future_id>', methods=['DELETE'])
def delete_future_config(future_id):
    """Delete future configuration"""
    try:
        db.delete_future(future_id)
        return jsonify({'message': 'Future deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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

@app.route('/api/models/<int:model_id>', methods=['DELETE'])
def delete_model(model_id):
    """Delete trading model"""
    try:
        model = db.get_model(model_id)
        model_name = model['name'] if model else f"ID-{model_id}"

        db.delete_model(model_id)
        if model_id in trading_engines:
            del trading_engines[model_id]

        logger.info(f"Model {model_id} ({model_name}) deleted")
        return jsonify({'message': 'Model deleted successfully'})
    except Exception as e:
        logger.error(f"Delete model {model_id} failed: {e}")
        return jsonify({'error': str(e)}), 500

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

@app.route('/api/market/leaderboard', methods=['GET'])
def get_market_leaderboard():
    """Get market leaderboard data"""
    limit = request.args.get('limit', type=int)
    force = request.args.get('force', default=0, type=int)
    try:
        data = market_fetcher.sync_leaderboard(force=bool(force), limit=limit)
        return jsonify(data)
    except Exception as exc:
        logger.error(f"Failed to load leaderboard: {exc}")
        return jsonify({'error': str(exc)}), 500

@app.route('/api/clickhouse/leaderboard/status', methods=['GET'])
def get_clickhouse_leaderboard_status():
    """Get ClickHouse leaderboard sync status"""
    global clickhouse_leaderboard_running
    return jsonify({
        'running': clickhouse_leaderboard_running,
        'thread_alive': clickhouse_leaderboard_thread.is_alive() if clickhouse_leaderboard_thread else False
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
    else:
        return jsonify({'error': 'Invalid action. Use "start" or "stop"'}), 400

@socketio.on('leaderboard:request')
def handle_leaderboard_request(payload=None):
    """WebSocket handler for leaderboard requests"""
    payload = payload or {}
    limit = payload.get('limit')
    try:
        data = market_fetcher.get_leaderboard(limit=limit)
        emit('leaderboard:update', data)
    except Exception as exc:
        emit('leaderboard:error', {'message': str(exc)})

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
    import webbrowser

    logger.info("\n" + "=" * 60)
    logger.info("AICoinTrade - Starting...")
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
    start_leaderboard_worker()
    logger.info("Leaderboard worker started")
    
    # Start ClickHouse leaderboard sync
    start_clickhouse_leaderboard_sync()
    logger.info("ClickHouse leaderboard sync started")

    logger.info("\n" + "=" * 60)
    logger.info("AICoinTrade is running!")
    logger.info("Server: http://localhost:5002")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60 + "\n")

    def open_browser():
        """Open browser after server starts"""
        time.sleep(1.5)
        url = "http://localhost:5002"
        try:
            webbrowser.open(url)
            logger.info(f"Browser opened: {url}")
        except Exception as e:
            logger.warning(f"Could not open browser: {e}")

    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()

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
