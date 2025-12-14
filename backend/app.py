# This must be at the very top of the file, before any other imports
import eventlet
eventlet.monkey_patch()

"""
Flask application for AI Futures Trading System
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import os
import time
import threading
import json
from datetime import datetime, timedelta, timezone
from trade.trading_engine import TradingEngine
from market.market_data import MarketDataFetcher
from trade.ai_trader import AITrader
from common.database_basic import Database
from common.database_account import AccountDatabase
from common.binance_futures import BinanceFuturesAccountClient
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

# Database initialization (using MySQL configuration from app_config)
db = Database()

# Initialize database tables immediately when the application starts
# This ensures tables are created even when running with gunicorn or other WSGI servers
with app.app_context():
    db.init_db()
    logger.info("Database tables initialized")

# 应用启动时初始化后台服务（已移除MySQL涨跌幅榜同步服务）
def _init_background_services():
    """初始化后台服务（在应用启动时调用）"""
    logger.info("🚀 初始化后台服务...")
    logger.info("✅ 后台服务初始化完成（涨跌榜数据直接从24_market_tickers表查询，无需异步同步）")

market_fetcher = MarketDataFetcher(db)
trading_engines = {}
auto_trading = getattr(app_config, 'AUTO_TRADING', True)
TRADE_FEE_RATE = getattr(app_config, 'TRADE_FEE_RATE', 0.001)
LEADERBOARD_REFRESH_INTERVAL = getattr(app_config, 'FUTURES_LEADERBOARD_REFRESH', 10)

leaderboard_thread = None
leaderboard_stop_event = threading.Event()

# ============ Helper Functions ============

def init_trading_engine_for_model(model_id: int):
    """Initialize trading engine for a model if possible."""
    logger.info(f"Initializing trading engine for model {model_id}...")
    
    model = db.get_model(model_id)
    if not model:
        logger.warning(f"Model {model_id} not found, cannot initialize trading engine")
        return None, 'Model not found'

    provider = db.get_provider(model['provider_id'])
    if not provider:
        logger.warning(f"Provider not found for model {model_id}, cannot initialize trading engine")
        return None, 'Provider not found'

    logger.info(f"Creating AITrader instance for model {model_id} with provider {provider.get('provider_type', 'openai')} and model {model['model_name']}")
    
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
    
    logger.info(f"Successfully initialized trading engine for model {model_id}")
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
        cycle_start_time = datetime.now(timezone(timedelta(hours=8)))
        
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
            cycle_duration = (datetime.now(timezone(timedelta(hours=8))) - cycle_start_time).total_seconds()
            logger.error(f"[Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] 涨跌幅榜同步失败: {exc}, 耗时: {cycle_duration:.2f} 秒")
            import traceback
            logger.error(f"[Leaderboard Worker-{thread_id}] [循环 #{cycle_count}] 错误堆栈:\n{traceback.format_exc()}")
        
        # 等待指定间隔（可被停止事件中断）
        leaderboard_stop_event.wait(wait_seconds)
    
    logger.info(f"[Leaderboard Worker-{thread_id}] 涨跌幅榜同步循环停止，总循环次数: {cycle_count}")


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
                time.sleep(10)
                continue

            logger.info(f"\n{'='*60}")
            logger.info(f"CYCLE: {datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}")
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


# ============ Provider API Endpoints ============
# API提供方管理：用于配置和管理AI模型提供方（如OpenAI、DeepSeek等）

@app.route('/api/providers', methods=['GET'])
def get_providers():
    """
    获取所有API提供方列表
    
    Returns:
        JSON: 提供方列表，包含id、name、api_url、api_key等信息
    """
    providers = db.get_all_providers()
    return jsonify(providers)

@app.route('/api/providers', methods=['POST'])
def add_provider():
    """
    添加新的API提供方
    
    Request Body:
        name (str): 提供方名称
        api_url (str): API地址
        api_key (str): API密钥
        models (str, optional): 支持的模型列表（逗号分隔）
        provider_type (str, optional): 提供方类型，默认'openai'
    
    Returns:
        JSON: 包含新创建的提供方ID和成功消息
    """
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
    """
    删除API提供方
    
    Args:
        provider_id (int): 提供方ID
    
    Returns:
        JSON: 删除操作结果
    """
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
    """
    从提供方API获取可用的模型列表
    
    Request Body:
        api_url (str): API地址
        api_key (str): API密钥
    
    Returns:
        JSON: 包含可用模型列表
    """
    data = request.json
    api_url = data.get('api_url')
    api_key = data.get('api_key')

    if not api_url or not api_key:
        return jsonify({'error': 'API URL and key are required'}), 400

    try:
        models = []

        # 根据提供方类型调用相应的API
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
            # 默认返回常用模型名称
            models = ['gpt-3.5-turbo', 'gpt-4', 'gpt-4-turbo']

        return jsonify({'models': models})
    except Exception as e:
        logger.error(f"Fetch models failed: {e}")
        return jsonify({'error': f'Failed to fetch models: {str(e)}'}), 500

# ============ Futures Configuration API Endpoints ============
# 合约配置管理：用于配置和管理交易合约信息（如BTCUSDT、ETHUSDT等）

@app.route('/api/futures', methods=['GET'])
def list_futures():
    """
    获取所有合约配置列表
    
    Returns:
        JSON: 合约配置列表，包含symbol、contract_symbol、name等信息
    """
    try:
        futures = db.get_futures()
        return jsonify(futures)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/futures', methods=['POST'])
def add_future_config():
    """
    添加新的合约配置
    
    Request Body:
        symbol (str): 交易对符号（如BTC）
        contract_symbol (str): 合约符号（如BTCUSDT）
        name (str): 合约名称（如比特币永续合约）
        exchange (str, optional): 交易所，默认'BINANCE_FUTURES'
        link (str, optional): 相关链接
        sort_order (int, optional): 排序顺序，默认0
    
    Returns:
        JSON: 包含新创建的合约ID和成功消息
    """
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
    """
    删除合约配置
    
    Args:
        future_id (int): 合约ID
    
    Returns:
        JSON: 删除操作结果
    """
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
# 交易模型管理：用于创建、配置和管理AI交易模型

@app.route('/api/models', methods=['GET'])
def get_models():
    """
    获取所有交易模型列表
    
    Returns:
        JSON: 模型列表，包含id、name、provider_id、model_name等信息
    """
    models = db.get_all_models()
    return jsonify(models)

@app.route('/api/models/<int:model_id>', methods=['GET'])
def get_model_by_id(model_id):
    """Get a single model by ID"""
    try:
        model = db.get_model(model_id)
        if not model:
            return jsonify({'error': 'Model not found'}), 404
        return jsonify(model)
    except Exception as e:
        logger.error(f"Failed to get model {model_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/models', methods=['POST'])
def add_model():
    """
    Add new trading model
    
    【symbol_source参数说明】
    前端传递的symbol_source字段用于指定AI交易买入决策时的交易对数据源：
    - 'leaderboard'（默认）：从涨跌榜获取交易对，适用于关注市场热点的策略
    - 'future'：从futures表获取所有已配置的交易对，适用于全市场扫描策略
    
    该参数仅影响buy类型的AI交互，sell逻辑不受影响。
    相关调用：trading_engine._select_buy_candidates() 会根据此值选择不同的数据源
    """
    data = request.json or {}
    try:
        provider = db.get_provider(data['provider_id'])
        if not provider:
            return jsonify({'error': 'Provider not found'}), 404

        # 获取account_alias和is_virtual参数
        account_alias = data.get('account_alias', '').strip()
        is_virtual = data.get('is_virtual', True)  # 默认值为 True（虚拟账户）
        
        # 验证account_alias必填
        if not account_alias:
            return jsonify({'error': 'account_alias is required'}), 400
        
        # 兼容旧版本：如果没有account_alias，则使用api_key和api_secret
        api_key = data.get('api_key', '').strip()
        api_secret = data.get('api_secret', '').strip()
        
        # 获取max_positions参数，默认值为3
        max_positions = int(data.get('max_positions', 3))
        if max_positions < 1:
            return jsonify({'error': 'max_positions must be >= 1'}), 400
        
        model_id = db.add_model(
            name=data['name'],
            provider_id=data['provider_id'],
            model_name=data['model_name'],
            initial_capital=float(data.get('initial_capital', 100000)),
            leverage=int(data.get('leverage', 10)),
            api_key=api_key,
            api_secret=api_secret,
            account_alias=account_alias,
            is_virtual=bool(is_virtual),
            symbol_source=data.get('symbol_source', 'leaderboard'),  # 【新增参数】交易对数据源，默认'leaderboard'保持向后兼容
            max_positions=max_positions  # 【新增参数】最大持仓数量，默认3
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
        
        # 初始化模型的默认prompts（从prompt_defaults.py读取）
        try:
            from trade.prompt_defaults import DEFAULT_BUY_CONSTRAINTS, DEFAULT_SELL_CONSTRAINTS
            db.upsert_model_prompt(
                model_id=model_id,
                buy_prompt=DEFAULT_BUY_CONSTRAINTS,
                sell_prompt=DEFAULT_SELL_CONSTRAINTS
            )
            logger.info(f"Model {model_id} default prompts initialized")
        except Exception as prompt_err:
            logger.warning(f"Failed to initialize default prompts for model {model_id}: {prompt_err}")
            # 不阻止模型创建，prompts初始化失败不影响模型创建

        return jsonify({'id': model_id, 'message': 'Model added successfully'})

    except Exception as e:
        logger.error(f"Failed to add model: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<int:model_id>', methods=['DELETE', 'OPTIONS'])
def delete_model(model_id):
    """
    删除交易模型
    
    Args:
        model_id (int): 模型ID
    
    Returns:
        JSON: 删除操作结果
    """
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
    """
    获取模型的投资组合数据
    
    Args:
        model_id (int): 模型ID
    
    Returns:
        JSON: 包含投资组合、账户价值历史、自动交易状态等信息
    """
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

@app.route('/api/models/<int:model_id>/portfolio/symbols', methods=['GET'])
def get_model_portfolio_symbols(model_id):
    """
    获取模型的持仓合约symbol列表及其实时价格和当日成交额等市场数据
    
    Args:
        model_id (int): 模型ID
    
    Returns:
        JSON: 包含symbol列表及其实时价格、当日成交额、涨跌百分比等市场数据
    """
    model = db.get_model(model_id)
    if not model:
        return jsonify({'error': f'Model {model_id} not found'}), 404
    
    from common.database_mysql import MySQLDatabase
    mysql_db = MySQLDatabase(auto_init_tables=False)
    
    # 获取模型持有symbols列表
    symbols = mysql_db.get_model_portfolio_symbols(model_id)
    
    if not symbols:
        return jsonify({'data': []}), 200
    
    # 获取实时价格数据
    prices_data = market_fetcher.get_prices(symbols)
    
    # 构建响应数据
    result = []
    for symbol in symbols:
        symbol_data = {
            'symbol': symbol,
            'price': prices_data.get(symbol, {}).get('price', 0),
            'change': prices_data.get(symbol, {}).get('change', 0),
            'changePercent': prices_data.get(symbol, {}).get('changePercent', 0),
            'volume': prices_data.get(symbol, {}).get('volume', 0),
            'quoteVolume': prices_data.get(symbol, {}).get('quoteVolume', 0),
            'high': prices_data.get(symbol, {}).get('high', 0),
            'low': prices_data.get(symbol, {}).get('low', 0)
        }
        result.append(symbol_data)
    
    return jsonify({'data': result}), 200

@app.route('/api/models/<int:model_id>/trades', methods=['GET'])
def get_trades(model_id):
    """
    获取模型的交易历史记录
    
    Args:
        model_id (int): 模型ID
    
    Query Parameters:
        limit (int, optional): 返回记录数限制，默认50
    
    Returns:
        JSON: 交易记录列表
    """
    limit = request.args.get('limit', 50, type=int)
    trades = db.get_trades(model_id, limit=limit)
    return jsonify(trades)

@app.route('/api/models/<int:model_id>/conversations', methods=['GET'])
def get_conversations(model_id):
    """
    获取模型的对话历史记录
    
    Args:
        model_id (int): 模型ID
    
    Query Parameters:
        limit (int, optional): 返回记录数限制，默认20
    
    Returns:
        JSON: 对话记录列表
    """
    limit = request.args.get('limit', 20, type=int)
    conversations = db.get_conversations(model_id, limit=limit)
    return jsonify(conversations)

@app.route('/api/models/<int:model_id>/prompts', methods=['GET'])
def get_model_prompts(model_id):
    """
    获取模型的提示词配置（买入和卖出策略）
    
    Args:
        model_id (int): 模型ID
    
    Returns:
        JSON: 包含买入和卖出提示词配置
    """
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
    """
    更新模型的提示词配置
    
    Args:
        model_id (int): 模型ID
    
    Request Body:
        buy_prompt (str, optional): 买入策略提示词
        sell_prompt (str, optional): 卖出策略提示词
    
    Returns:
        JSON: 更新操作结果
    """
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

@app.route('/api/models/<int:model_id>/max_positions', methods=['POST'])
def update_model_max_positions(model_id):
    """
    更新模型的最大持仓数量
    
    Args:
        model_id (int): 模型ID
    
    Request Body:
        max_positions (int): 最大持仓数量，必须 >= 1
    
    Returns:
        JSON: 更新结果
    """
    try:
        data = request.get_json()
        if not data or 'max_positions' not in data:
            return jsonify({'error': 'max_positions is required'}), 400
        
        max_positions = data.get('max_positions')
        if not isinstance(max_positions, int) or max_positions < 1:
            return jsonify({'error': 'max_positions must be an integer >= 1'}), 400
        
        if not db.set_model_max_positions(model_id, max_positions):
            return jsonify({'error': 'Failed to update max_positions'}), 500
        
        return jsonify({'success': True, 'max_positions': max_positions})
    except Exception as e:
        logger.error(f"Failed to update max_positions for model {model_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<int:model_id>/leverage', methods=['POST'])
def update_model_leverage(model_id):
    """
    更新模型的杠杆倍数
    
    Args:
        model_id (int): 模型ID
    
    Request Body:
        leverage (int): 杠杆倍数（必须大于0）
    
    Returns:
        JSON: 更新后的杠杆倍数
    """
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
    """
    手动执行一次交易周期（用于测试或手动触发交易）
    
    Args:
        model_id (int): 模型ID
    
    Returns:
        JSON: 交易执行结果，包含成功状态和执行详情
    
    Note:
        手动执行会自动启用该模型的自动交易功能
    """
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
    """
    启用或禁用模型的自动交易功能
    
    Args:
        model_id (int): 模型ID
    
    Request Body:
        enabled (bool): 是否启用自动交易
    
    Returns:
        JSON: 更新后的自动交易状态
    """
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
    """
    获取所有模型的聚合投资组合数据
    
    Returns:
        JSON: 包含所有模型的汇总投资组合、图表数据等信息
    """
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

            # Aggregate positions by symbol and position_side
            for pos in portfolio.get('positions', []):
                symbol = pos.get('symbol', '')
                position_side = pos.get('position_side', 'LONG')
                position_amt = abs(pos.get('position_amt', 0.0))
                
                key = f"{symbol}_{position_side}"
                if key not in all_positions:
                    all_positions[key] = {
                        'symbol': symbol,
                        'position_side': position_side,
                        'position_amt': 0,
                        'avg_price': 0,
                        'total_cost': 0,
                        'leverage': pos.get('leverage', 1),
                        'current_price': pos.get('current_price'),
                        'pnl': pos.get('pnl', 0)
                    }

                # Weighted average calculation
                current_pos = all_positions[key]
                current_cost = current_pos['position_amt'] * current_pos['avg_price']
                new_cost = position_amt * pos.get('avg_price', 0)
                total_position_amt = current_pos['position_amt'] + position_amt

                if total_position_amt > 0:
                    current_pos['avg_price'] = (current_cost + new_cost) / total_position_amt
                    current_pos['position_amt'] = total_position_amt
                    current_pos['total_cost'] = current_cost + new_cost
                    current_pos['pnl'] = (pos.get('current_price', 0) - current_pos['avg_price']) * total_position_amt

    total_portfolio['positions'] = list(all_positions.values())
    chart_data = db.get_multi_model_chart_data(limit=100)

    return jsonify({
        'portfolio': total_portfolio,
        'chart_data': chart_data,
        'model_count': len(models)
    })

# ============ Market Data API Endpoints ============
# 市场数据接口：提供实时市场行情、涨跌幅榜、K线数据、技术指标等

@app.route('/api/market/prices', methods=['GET'])
def get_market_prices():
    """获取当前市场价格（仅返回配置的合约信息）
    
    Returns:
        JSON: 价格数据字典，key为交易对符号，value包含价格和来源信息
    """
    # 获取配置的合约
    configured_symbols = get_tracked_symbols()
    configured_prices = market_fetcher.get_prices(configured_symbols)
    
    # 为配置的合约添加来源标记
    for symbol in configured_prices:
        configured_prices[symbol]['source'] = 'configured'
    
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

@app.route('/api/market/leaderboard/gainers', methods=['GET'])
def get_market_leaderboard_gainers():
    """Get market gainers leaderboard data (涨幅榜)
    
    从 24_market_tickers 表直接查询涨幅榜数据：
    - 查询 side='gainer' 的记录
    - 按 price_change_percent 降序排序
    - 返回前N名
    
    前端通过轮询此接口获取涨幅榜数据
    """
    limit = request.args.get('limit', type=int) or 10  # 默认10条
    
    try:
        from common.database_mysql import MySQLDatabase
        db = MySQLDatabase(auto_init_tables=False)
        
        # 从 24_market_tickers 表直接查询涨幅榜
        gainers = db.get_gainers_from_tickers(limit=limit)
        
        result = {
            'gainers': gainers,
            'timestamp': int(datetime.now(timezone(timedelta(hours=8))).timestamp() * 1000)
        }
        
        logger.debug(f"[API] 涨幅榜数据返回: {len(gainers)} 条")
        return jsonify(result)
    except Exception as exc:
        logger.error(f"Failed to load gainers leaderboard: {exc}", exc_info=True)
        return jsonify({'error': str(exc), 'gainers': []}), 500

@app.route('/api/market/leaderboard/losers', methods=['GET'])
def get_market_leaderboard_losers():
    """Get market losers leaderboard data (跌幅榜)
    
    从 24_market_tickers 表直接查询跌幅榜数据：
    - 查询 side='loser' 的记录
    - 按 price_change_percent 绝对值降序排序（注意 price_change_percent 为负值）
    - 返回前N名
    
    前端通过轮询此接口获取跌幅榜数据
    """
    limit = request.args.get('limit', type=int) or 10  # 默认10条
    
    try:
        from common.database_mysql import MySQLDatabase
        db = MySQLDatabase(auto_init_tables=False)
        
        # 从 24_market_tickers 表直接查询跌幅榜
        losers = db.get_losers_from_tickers(limit=limit)
        
        result = {
            'losers': losers,
            'timestamp': int(datetime.now(timezone(timedelta(hours=8))).timestamp() * 1000)
        }
        
        logger.debug(f"[API] 跌幅榜数据返回: {len(losers)} 条")
        return jsonify(result)
    except Exception as exc:
        logger.error(f"Failed to load losers leaderboard: {exc}", exc_info=True)
        return jsonify({'error': str(exc), 'losers': []}), 500

@app.route('/api/market/leaderboard', methods=['GET'])
def get_market_leaderboard():
    """
    获取涨跌幅榜数据（已废弃，保留以兼容旧代码）
    
    注意：此接口已废弃，请使用 /api/market/leaderboard/gainers 和 /api/market/leaderboard/losers
    
    Query Parameters:
        limit (int, optional): 返回记录数限制，默认10
        force (int, optional): 是否强制刷新，默认0
    
    Returns:
        JSON: 包含涨幅榜和跌幅榜数据
    """
    limit = request.args.get('limit', type=int) or 10
    force = request.args.get('force', default=0, type=int)
    
    try:
        # 获取涨跌幅榜数据（涨10个，跌10个）
        data = market_fetcher.sync_leaderboard(force=bool(force), limit=limit)
        
        # 确保返回完整数据格式
        result = {
            'gainers': data.get('gainers', [])[:limit],
            'losers': data.get('losers', [])[:limit],
            'timestamp': int(datetime.now(timezone(timedelta(hours=8))).timestamp() * 1000)
        }
        
        gainers_count = len(result['gainers'])
        losers_count = len(result['losers'])
        logger.debug(f"[API] 涨跌幅榜数据返回: 涨幅榜 {gainers_count} 条, 跌幅榜 {losers_count} 条")
        
        return jsonify(result)
    except Exception as exc:
        logger.error(f"Failed to load leaderboard: {exc}", exc_info=True)
        return jsonify({'error': str(exc), 'gainers': [], 'losers': []}), 500

@app.route('/api/market/klines', methods=['GET'])
def get_market_klines():
    """获取K线历史数据
    
    参数:
        symbol: 交易对符号（如 'BTCUSDT'）
        interval: 时间间隔（'1m', '5m', '15m', '1h', '4h', '1d', '1w'）
        limit: 返回的最大记录数，默认值根据interval不同：
               - 1d（1天）：默认120条，最大120条
               - 1w（1周）：默认20条，最大20条
               - 其他interval：默认499条，最大499条
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
        # 其他interval：499条
        interval_default_limits = {
            '1d': 499,  # 1天周期，默认499条
            '1w': 99,   # 1周周期，默认99条
        }
        default_limit = interval_default_limits.get(interval, 499)  # 其他周期默认500条
        
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
            from common.database_mysql import MySQLDatabase
            logger.info(f"[API] 从数据库获取K线数据: symbol={symbol}, interval={interval}")
            mysql_db = MySQLDatabase(auto_init_tables=False)
            klines = mysql_db.get_market_klines(
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
            max_limit = interval_max_limits.get(interval, 499)  # 其他周期最大500条
            
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

# ============ WebSocket Handlers ============
# WebSocket事件处理：用于实时数据推送（K线数据等）

@socketio.on('klines:subscribe')
def handle_klines_subscribe(payload=None):
    """
    WebSocket处理：订阅K线实时数据推送
    
    Args:
        payload (dict): 订阅参数
            symbol (str): 交易对符号（如 'BTCUSDT'）
            interval (str): 时间间隔（'1m', '5m', '15m', '1h', '4h', '1d', '1w'）
    
    Note:
        订阅后，客户端将定期收到该交易对的K线更新数据
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
            'last_update_time': datetime.now(timezone(timedelta(hours=8)))
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
    """
    WebSocket处理：取消K线订阅
    
    Args:
        payload (dict): 取消订阅参数
            symbol (str): 交易对符号（如 'BTCUSDT'）
            interval (str): 时间间隔（'1m', '5m', '15m', '1h', '4h', '1d', '1w'）
    """
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
# 系统设置管理：用于配置交易频率、手续费率等系统参数

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """
    获取系统设置
    
    Returns:
        JSON: 系统设置信息，包括交易频率、手续费率等
    """
    try:
        settings = db.get_settings()
        return jsonify(settings)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/settings', methods=['PUT'])
def update_settings():
    """
    更新系统设置
    
    Request Body:
        trading_frequency_minutes (int, optional): 交易频率（分钟），默认60
        trading_fee_rate (float, optional): 手续费率，默认0.001
        show_system_prompt (bool, optional): 是否显示系统提示，默认False
    
    Returns:
        JSON: 更新操作结果
    """
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

# ============ Account Management API Endpoints ============
# 账户管理：用于添加、查询、删除交易账户（Binance API密钥管理）

@app.route('/api/accounts', methods=['GET'])
def get_all_accounts():
    """
    查询所有账户信息
    
    Returns:
        JSON: 账户列表，包含account_name、balance、crossWalletBalance等信息
    """
    try:
        account_db = AccountDatabase(auto_init_tables=False)
        accounts = account_db.get_all_accounts()
        return jsonify(accounts)
    except Exception as e:
        logger.error(f"Failed to get all accounts: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/accounts', methods=['POST'])
def add_account():
    """
    添加新账户（通过Binance API密钥验证并保存账户信息）
    
    Request Body:
        account_name (str): 账户名称（必填）
        api_key (str): Binance API密钥（必填）
        api_secret (str): Binance API密钥（必填）
    
    Returns:
        JSON: 包含account_alias和成功消息
    
    Note:
        此接口会调用Binance API验证密钥有效性，并获取账户资产信息
    """
    data = request.json or {}
    account_name = data.get('account_name', '').strip()
    api_key = data.get('api_key', '').strip()
    api_secret = data.get('api_secret', '').strip()
    
    if not account_name:
        return jsonify({'error': 'account_name is required'}), 400
    if not api_key or not api_secret:
        return jsonify({'error': 'api_key and api_secret are required'}), 400
    
    try:
        # 1. 创建BinanceFuturesAccountClient对象
        client = BinanceFuturesAccountClient(api_key=api_key, api_secret=api_secret)
        
        # 2. 调用get_account方法获取账户数据（包含汇总信息和assets数组）
        account_json = client.get_account()
        account_data = json.loads(account_json)
        
        # 3. 从account_data中提取汇总信息（直接使用返回的字段）
        account_asset_summary = {
            'totalInitialMargin': float(account_data.get('totalInitialMargin', 0)),
            'totalMaintMargin': float(account_data.get('totalMaintMargin', 0)),
            'totalWalletBalance': float(account_data.get('totalWalletBalance', 0)),
            'totalUnrealizedProfit': float(account_data.get('totalUnrealizedProfit', 0)),
            'totalMarginBalance': float(account_data.get('totalMarginBalance', 0)),
            'totalPositionInitialMargin': float(account_data.get('totalPositionInitialMargin', 0)),
            'totalOpenOrderInitialMargin': float(account_data.get('totalOpenOrderInitialMargin', 0)),
            'totalCrossWalletBalance': float(account_data.get('totalCrossWalletBalance', 0)),
            'totalCrossUnPnl': float(account_data.get('totalCrossUnPnl', 0)),
            'availableBalance': float(account_data.get('availableBalance', 0)),
            'maxWithdrawAmount': float(account_data.get('maxWithdrawAmount', 0))
        }
        
        # 4. 从account_data中提取assets数组（不包含positions）
        asset_list = []
        assets = account_data.get('assets', [])
        if isinstance(assets, list):
            for asset_item in assets:
                # 提取每个资产的详细信息（注意：SDK返回的字段名可能是驼峰命名）
                asset_info = {
                    'asset': asset_item.get('asset', ''),
                    'walletBalance': float(asset_item.get('walletBalance', 0)),
                    'unrealizedProfit': float(asset_item.get('unrealizedProfit', 0)),
                    'marginBalance': float(asset_item.get('marginBalance', 0)),
                    'maintMargin': float(asset_item.get('maintMargin', 0)),
                    'initialMargin': float(asset_item.get('initialMargin', 0)),
                    'positionInitialMargin': float(asset_item.get('positionInitialMargin', 0)),
                    'openOrderInitialMargin': float(asset_item.get('openOrderInitialMargin', 0)),
                    'crossWalletBalance': float(asset_item.get('crossWalletBalance', 0)),
                    'crossUnPnl': float(asset_item.get('crossUnPnl', 0)),
                    'availableBalance': float(asset_item.get('availableBalance', 0)),
                    'maxWithdrawAmount': float(asset_item.get('maxWithdrawAmount', 0))
                }
                asset_list.append(asset_info)
        
        # 5. 保存到数据库（account_alias由数据库方法自动生成）
        account_db = AccountDatabase(auto_init_tables=False)
        account_alias = account_db.add_account(
            account_name=account_name,
            api_key=api_key,
            api_secret=api_secret,
            account_asset_data=account_asset_summary,
            asset_list=asset_list
        )
        
        logger.info(f"Account added successfully: account_alias={account_alias}")
        return jsonify({
            'account_alias': account_alias,
            'message': 'Account added successfully'
        })
    except Exception as e:
        logger.error(f"Failed to add account: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/accounts/<account_alias>', methods=['DELETE', 'OPTIONS'])
def delete_account(account_alias):
    """
    删除账户
    
    Args:
        account_alias (str): 账户别名（账户唯一标识）
    
    Returns:
        JSON: 删除操作结果
    """
    # 处理 OPTIONS 预检请求
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Methods', 'DELETE, OPTIONS')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        return response
    
    try:
        account_db = AccountDatabase(auto_init_tables=False)
        account_db.delete_account(account_alias)
        logger.info(f"Account {account_alias} deleted successfully")
        return jsonify({'success': True, 'message': 'Account deleted successfully'})
    except Exception as e:
        logger.error(f"Failed to delete account {account_alias}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

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
    
    # 初始化后台服务（包括MySQL涨跌幅榜同步线程）
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
