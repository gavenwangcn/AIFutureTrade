# This must be at the very top of the file, before any other imports
import eventlet
eventlet.monkey_patch()

"""
Flask application for AI Futures Trading System - Trading Service
交易服务：只保留交易循环执行功能，其他API已迁移到Java后端
启动时立即加载交易循环，不等待请求
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import threading
from trade.trading_engine import TradingEngine
from market.market_data import MarketDataFetcher
from trade.ai.ai_trader import AITrader
from trade.strategy.strategy_trader import StrategyTrader
from common.database.database_basic import Database
from common.database.database_models import ModelsDatabase
from common.database.database_providers import ProvidersDatabase
from common.database.database_strategys import StrategysDatabase
from common.version import __version__
from trade.trading_loop import trading_buy_loop, trading_sell_loop

import common.config as app_config
import logging
import sys

# ============ Application Initialization ============

app = Flask(__name__)
# CORS配置：允许前端服务访问
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "expose_headers": ["Content-Type"],
        "supports_credentials": False
    }
})

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
# 使用统一的初始化函数，确保所有表都被正确创建
with app.app_context():
    from common.database.database_init import init_all_database_tables
    # 使用 Database 的 command 方法作为初始化函数
    init_all_database_tables(db.command)
    logger.info("Database tables initialized")

# Initialize ModelsDatabase, ProvidersDatabase and StrategysDatabase for direct operations
models_db = ModelsDatabase(pool=db._pool)
providers_db = ProvidersDatabase(pool=db._pool)
strategys_db = StrategysDatabase(pool=db._pool)

market_fetcher = MarketDataFetcher(db)
trading_engines = {}
auto_trading = getattr(app_config, 'AUTO_TRADING', True)
TRADE_FEE_RATE = getattr(app_config, 'TRADE_FEE_RATE', 0.002)

# ============ Helper Functions ============

def check_strategy_exists(model_id: int, strategy_type: str):
    """
    检查模型是否存在指定类型的策略配置
    
    Args:
        model_id: 模型ID（整数）
        strategy_type: 策略类型，'buy' 或 'sell'
    
    Returns:
        tuple[bool, str]: (是否存在策略, 错误消息)
    """
    try:
        model = models_db.get_model(model_id)
        if not model:
            return False, f"Model {model_id} not found"
        
        # 只对 trade_type='strategy' 的模型进行策略检查
        trade_type = model.get('trade_type', 'strategy')
        if trade_type != 'strategy':
            # 非策略类型的模型不需要检查策略
            return True, None
        
        # 获取模型ID映射
        model_mapping = models_db._get_model_id_mapping()
        
        # 查询策略
        strategies = strategys_db.get_model_strategies_by_int_id(
            model_id, 
            strategy_type, 
            model_mapping
        )
        
        if not strategies:
            return False, f"Model {model_id} (trade_type=strategy) has no {strategy_type} strategy configured in model_strategy table"
        
        return True, None
    except Exception as e:
        logger.error(f"Failed to check strategy for model {model_id}, type {strategy_type}: {e}")
        return False, f"Error checking strategy: {str(e)}"

def init_trading_engine_for_model(model_id: int):
    """Initialize trading engine for a model if possible."""
    logger.info(f"Initializing trading engine for model {model_id}...")
    
    model = models_db.get_model(model_id)
    if not model:
        logger.warning(f"Model {model_id} not found, cannot initialize trading engine")
        return None, 'Model not found'

    # 获取trade_type，默认为'strategy'
    trade_type = model.get('trade_type', 'strategy')
    if trade_type not in ['ai', 'strategy']:
        logger.warning(f"Model {model_id} has invalid trade_type '{trade_type}', defaulting to 'strategy'")
        trade_type = 'strategy'
    
    # 根据trade_type创建对应的trader
    if trade_type == 'ai':
        # 使用AI交易，需要provider信息
        provider = providers_db.get_provider(model['provider_id'])
        if not provider:
            logger.warning(f"Provider not found for model {model_id}, cannot initialize AITrader")
            return None, 'Provider not found'
        
        logger.info(f"Creating AITrader instance for model {model_id} with provider {provider.get('provider_type', 'openai')} and model {model['model_name']}")
        
        trader = AITrader(
            provider_type=provider.get('provider_type', 'openai'),
            api_key=provider['api_key'],
            api_url=provider['api_url'],
            model_name=model['model_name'],
            db=db,
            market_fetcher=market_fetcher  # 传递market_fetcher用于计算指标
        )
    else:
        # 使用策略交易（默认）
        logger.info(f"Creating StrategyTrader instance for model {model_id}")
        
        trader = StrategyTrader(
            db=db,
            model_id=model_id
        )
    
    trading_engines[model_id] = TradingEngine(
        model_id=model_id,
        db=db,
        market_fetcher=market_fetcher,
        trader=trader,
        trade_fee_rate=TRADE_FEE_RATE
    )
    
    logger.info(f"Successfully initialized trading engine for model {model_id} with trade_type={trade_type}")
    return trading_engines[model_id], None

def init_trading_engines():
    """Initialize trading engines for all models"""
    try:
        models = models_db.get_all_models()

        if not models:
            logger.warning("No trading models found")
            return

        logger.info(f"\nINIT: Initializing trading engines...")
        for model in models:
            model_id = model['id']
            model_name = model['name']

            try:
                # 获取trade_type，默认为'strategy'
                trade_type = model.get('trade_type', 'strategy')
                if trade_type not in ['ai', 'strategy']:
                    logger.warning(f"  Model {model_id} ({model_name}): Invalid trade_type '{trade_type}', defaulting to 'strategy'")
                    trade_type = 'strategy'
                
                # 根据trade_type创建对应的trader
                if trade_type == 'ai':
                    # 使用AI交易，需要provider信息
                    provider = providers_db.get_provider(model['provider_id'])
                    if not provider:
                        logger.warning(f"  Model {model_id} ({model_name}): Provider not found")
                        continue
                    
                    trader = AITrader(
                        provider_type=provider.get('provider_type', 'openai'),
                        api_key=provider['api_key'],
                        api_url=provider['api_url'],
                        model_name=model['model_name'],
                        db=db,
                        market_fetcher=market_fetcher  # 传递market_fetcher用于计算指标
                    )
                    logger.info(f"  OK: Model {model_id} ({model_name}) - AITrader")
                else:
                    # 使用策略交易（默认）
                    trader = StrategyTrader(
                        db=db,
                        model_id=model_id
                    )
                    logger.info(f"  OK: Model {model_id} ({model_name}) - StrategyTrader")
                
                trading_engines[model_id] = TradingEngine(
                    model_id=model_id,
                    db=db,
                    market_fetcher=market_fetcher,
                    trader=trader,
                    trade_fee_rate=TRADE_FEE_RATE
                )
            except Exception as e:
                logger.error(f"  Model {model_id} ({model_name}): {e}")
                continue

        logger.info(f"Initialized {len(trading_engines)} engine(s)\n")

    except Exception as e:
        logger.error(f"Init engines failed: {e}\n")

# ============ Trading Loop Management ============

# 交易循环线程
_trading_buy_thread = None
_trading_sell_thread = None
_trading_loops_started = False

def _start_trading_loops():
    """启动买入和卖出交易循环"""
    global _trading_loops_started, _trading_buy_thread, _trading_sell_thread, auto_trading
    
    if _trading_loops_started:
        return
    
    if not auto_trading:
        logger.info("Auto-trading is disabled, skipping trading loops startup")
        return
    
    # 确保数据库和交易引擎已初始化
    if not trading_engines:
        logger.info("No trading engines found, initializing...")
        init_trading_engines()
    
    if trading_engines:
        # 启动买入循环线程
        _trading_buy_thread = threading.Thread(target=trading_buy_loop, args=(auto_trading, trading_engines, db), daemon=True, name="TradingBuyLoop")
        _trading_buy_thread.start()
        logger.info("✅ Auto-trading buy loop started")
        
        # 启动卖出循环线程
        _trading_sell_thread = threading.Thread(target=trading_sell_loop, args=(auto_trading, trading_engines, db), daemon=True, name="TradingSellLoop")
        _trading_sell_thread.start()
        logger.info("✅ Auto-trading sell loop started")
        
        _trading_loops_started = True
    else:
        logger.warning("⚠️ No trading engines available, trading loops not started")

@app.after_request
def after_request(response):
    """添加 CORS 响应头，确保所有请求都能正确处理"""
    if request.path.startswith('/api/'):
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        response.headers.add('Access-Control-Max-Age', '3600')
    return response

@app.route('/')
def index():
    """Main page route - 返回简单的状态信息"""
    return jsonify({
        'status': 'running',
        'message': 'AI Future Trade Trading Service',
        'version': __version__,
        'api_endpoint': '/api/'
    })

# ============ Trading API Endpoints ============

@app.route('/api/models/<int:model_id>/execute-buy', methods=['POST'])
def execute_buy_trading(model_id):
    """
    手动执行一次买入交易周期
    
    Args:
        model_id (int): 模型ID
    
    Returns:
        JSON: 买入交易执行结果
    """
    # 检查策略配置（仅对 trade_type='strategy' 的模型）
    has_strategy, error_msg = check_strategy_exists(model_id, 'buy')
    if not has_strategy:
        logger.warning(f"Model {model_id} buy execution blocked: {error_msg}")
        return jsonify({'error': error_msg, 'success': False}), 400
    
    if model_id not in trading_engines:
        engine, error = init_trading_engine_for_model(model_id)
        if error:
            return jsonify({'error': error}), 404
    else:
        engine = trading_engines[model_id]

    # 启用自动买入
    models_db.set_model_auto_buy_enabled(model_id, True)
    
    # 确保交易循环已启动
    _start_trading_loops()

    try:
        result = engine.execute_buy_cycle()
        result['auto_buy_enabled'] = True
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<int:model_id>/execute-sell', methods=['POST'])
def execute_sell_trading(model_id):
    """
    手动执行一次卖出交易周期
    
    Args:
        model_id (int): 模型ID
    
    Returns:
        JSON: 卖出交易执行结果
    """
    # 检查策略配置（仅对 trade_type='strategy' 的模型）
    has_strategy, error_msg = check_strategy_exists(model_id, 'sell')
    if not has_strategy:
        logger.warning(f"Model {model_id} sell execution blocked: {error_msg}")
        return jsonify({'error': error_msg, 'success': False}), 400
    
    if model_id not in trading_engines:
        engine, error = init_trading_engine_for_model(model_id)
        if error:
            return jsonify({'error': error}), 404
    else:
        engine = trading_engines[model_id]

    # 启用自动卖出
    models_db.set_model_auto_sell_enabled(model_id, True)
    
    # 确保交易循环已启动
    _start_trading_loops()

    try:
        result = engine.execute_sell_cycle()
        result['auto_sell_enabled'] = True
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<int:model_id>/disable-buy', methods=['POST'])
def disable_buy_trading(model_id):
    """
    禁用模型的自动买入功能
    
    Args:
        model_id (int): 模型ID
    
    Returns:
        JSON: 更新后的自动买入状态
    """
    model = models_db.get_model(model_id)
    if not model:
        return jsonify({'error': 'Model not found'}), 404

    success = models_db.set_model_auto_buy_enabled(model_id, False)
    if not success:
        return jsonify({'error': 'Failed to update auto buy status'}), 500

    logger.info(f"Auto buy disabled for model {model_id}")
    return jsonify({'model_id': model_id, 'auto_buy_enabled': False})

@app.route('/api/models/<int:model_id>/disable-sell', methods=['POST'])
def disable_sell_trading(model_id):
    """
    禁用模型的自动卖出功能
    
    Args:
        model_id (int): 模型ID
    
    Returns:
        JSON: 更新后的自动卖出状态
    """
    model = models_db.get_model(model_id)
    if not model:
        return jsonify({'error': 'Model not found'}), 404

    success = models_db.set_model_auto_sell_enabled(model_id, False)
    if not success:
        return jsonify({'error': 'Failed to update auto sell status'}), 500

    logger.info(f"Auto sell disabled for model {model_id}")
    return jsonify({'model_id': model_id, 'auto_sell_enabled': False})

# ============ Main Entry Point ============

if __name__ == '__main__':
    logger.info("\n" + "=" * 60)
    logger.info("AIFutureTrade Trading Service")
    logger.info("=" * 60)
    logger.info("Initializing database...")

    # Initialize database and trading engines within application context
    with app.app_context():
        db.init_db()
        logger.info("Database initialized")
        logger.info("Initializing trading engines...")
        init_trading_engines()
        logger.info("Trading engines initialized")
    
    # 启动时立即启动交易循环（不等待请求）
    logger.info("Starting trading loops immediately...")
    _start_trading_loops()

    logger.info("\n" + "=" * 60)
    logger.info("AIFutureTrade Trading Service is running!")
    logger.info("API Server: http://0.0.0.0:5000")
    logger.info("Available endpoints:")
    logger.info("  POST /api/models/<model_id>/execute-buy")
    logger.info("  POST /api/models/<model_id>/execute-sell")
    logger.info("  POST /api/models/<model_id>/disable-buy")
    logger.info("  POST /api/models/<model_id>/disable-sell")
    logger.info("=" * 60 + "\n")

    # 开发环境：使用Flask内置服务器
    # 生产环境：使用gunicorn + eventlet（见Dockerfile和gunicorn_config.py）
    # 通过环境变量USE_GUNICORN=true来使用gunicorn启动
    if os.getenv('USE_GUNICORN') == 'true':
        logger.info("Production mode: Use 'gunicorn --config gunicorn_config.py trade.app:app' to start")
        # 生产环境应该使用gunicorn启动，这里只是提示
        app.run(debug=False, host='0.0.0.0', port=5000, use_reloader=False)
    else:
        # 开发环境
        app.run(debug=False, host='0.0.0.0', port=5000, use_reloader=False)

