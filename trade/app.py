# This must be at the very top of the file, before any other imports
import eventlet
eventlet.monkey_patch()

"""
Flask application for AI Futures Trading System - Trading Service
Trading service: Only retains trading loop execution functionality, other APIs have been migrated to Java backend
Load trading loop immediately on startup, do not wait for requests
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import threading
from trade.trading_engine import TradingEngine
from trade.market.market_data import MarketDataFetcher
from trade.ai.ai_trader import AITrader
from trade.strategy.strategy_trader import StrategyTrader
from trade.common.database.database_basic import Database
from trade.common.database.database_models import ModelsDatabase
from trade.common.database.database_providers import ProvidersDatabase
from trade.common.database.database_strategys import StrategysDatabase
from trade.common.version import __version__
from trade.trading_loop import trading_buy_loop, trading_sell_loop

import trade.common.config as app_config
import logging
import sys

# ============ Application Initialization ============

app = Flask(__name__)
# CORS configuration: Allow frontend service access
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
    """Get log level from configuration, default is INFO"""
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
# Use unified initialization function to ensure all tables are created correctly
with app.app_context():
    from trade.common.database.database_init import init_all_database_tables
    # Use Database's command method as initialization function
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
# Trading loop configuration: whether to start trading loops on service startup
TRADING_LOOP_ENABLED = getattr(app_config, 'TRADING_LOOP_ENABLED', False)

# ============ Helper Functions ============

def check_strategy_exists(model_id: int, strategy_type: str):
    """
    Check if model has strategy configuration of specified type
    
    Args:
        model_id: Model ID (integer)
        strategy_type: Strategy type, 'buy' or 'sell'
    
    Returns:
        tuple[bool, str]: (Whether strategy exists, error message)
    """
    try:
        model = models_db.get_model(model_id)
        if not model:
            return False, f"Model {model_id} not found"
        
        # Only check strategy for models with trade_type='strategy'
        trade_type = model.get('trade_type', 'strategy')
        if trade_type != 'strategy':
            # Non-strategy type models don't need strategy check
            return True, None
        
        # Get model ID mapping
        model_mapping = models_db._get_model_id_mapping()
        
        # Query strategy
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

    # Get trade_type, default is 'strategy'
    trade_type = model.get('trade_type', 'strategy')
    if trade_type not in ['ai', 'strategy']:
        logger.warning(f"Model {model_id} has invalid trade_type '{trade_type}', defaulting to 'strategy'")
        trade_type = 'strategy'
    
    # Create corresponding trader based on trade_type
    if trade_type == 'ai':
        # Use AI trading, need provider information
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
            market_fetcher=market_fetcher  # Pass market_fetcher for indicator calculation
        )
    else:
        # Use strategy trading (default)
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
    
    # 检查是否启用交易循环（默认不启动，由模型容器管理）
    if not TRADING_LOOP_ENABLED:
        logger.info("Trading loop is disabled (TRADING_LOOP_ENABLED=False), skipping trading loops startup")
        logger.info("Note: Trading loops are now managed by individual model containers (model-buy/model-sell)")
        return
    
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

@app.route('/api/strategy/validate-code', methods=['POST'])
def validate_strategy_code():
    """
    验证策略代码是否符合要求
    
    请求体:
        strategy_code: 策略代码字符串
        strategy_type: 策略类型（'buy' 或 'sell'）
        strategy_name: 策略名称（可选，用于日志）
    
    返回:
        JSON: 测试结果，包含passed、errors、warnings等字段
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': '请求体不能为空', 'passed': False}), 400
        
        strategy_code = data.get('strategy_code')
        strategy_type = data.get('strategy_type')
        strategy_name = data.get('strategy_name', '测试策略')
        
        if not strategy_code:
            return jsonify({'error': 'strategy_code参数不能为空', 'passed': False}), 400
        
        if not strategy_type or strategy_type not in ['buy', 'sell']:
            return jsonify({'error': 'strategy_type参数必须为"buy"或"sell"', 'passed': False}), 400
        
        # 导入对应的测试器
        if strategy_type == 'buy':
            from trade.strategy.strategy_code_tester_buy import StrategyCodeTesterBuy
            tester = StrategyCodeTesterBuy()
        else:
            from trade.strategy.strategy_code_tester_sell import StrategyCodeTesterSell
            tester = StrategyCodeTesterSell()
        
        # 执行测试
        result = tester.test_strategy_code(strategy_code, strategy_name)
        
        logger.info(f"策略代码验证完成: {strategy_name}, 类型: {strategy_type}, 通过: {result.get('passed', False)}")
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"验证策略代码时发生异常: {e}", exc_info=True)
        error_result = {
            "passed": False,
            "errors": [f"测试执行异常: {str(e)}"],
            "warnings": [],
            "test_results": {}
        }
        return jsonify(error_result), 500

@app.route('/api/market/klines', methods=['GET'])
def get_market_klines():
    """
    获取K线历史数据（仅使用SDK，不查询数据库）
    
    参数:
        symbol: 交易对符号（如 'BTCUSDT'）
        interval: 时间间隔（'1m', '5m', '15m', '1h', '4h', '1d', '1w'）
        limit: 返回的最大记录数，默认值根据interval不同：
               - 1d（1天）：默认499条，最大499条
               - 1w（1周）：默认99条，最大99条
               - 其他interval：默认499条，最大499条
        start_time: 开始时间（可选，ISO格式字符串）
        end_time: 结束时间（可选，ISO格式字符串）
    """
    try:
        from datetime import datetime
        
        symbol = request.args.get('symbol', '').upper()
        interval = request.args.get('interval', '5m')
        
        # 根据不同的interval设置不同的默认limit
        interval_default_limits = {
            '1d': 499,  # 1天周期，默认499条
            '1w': 99,   # 1周周期，默认99条
        }
        default_limit = interval_default_limits.get(interval, 499)  # 其他周期默认499条
        
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
        logger.info(f"[API] 获取K线历史数据请求: symbol={symbol}, interval={interval}, limit={limit}, start_time={start_time_str}, end_time={end_time_str}, client_ip={client_ip}")
        
        # 检查 market_fetcher 和 _futures_client 是否可用
        if not market_fetcher or not market_fetcher._futures_client:
            logger.error("[API] MarketDataFetcher or BinanceFuturesClient not initialized")
            return jsonify({'error': 'Market data service not available'}), 503
        
        # SDK模式下根据不同的interval设置不同的最大limit
        interval_max_limits = {
            '1d': 499,  # 1天周期，最大499条
            '1w': 99,   # 1周周期，最大99条
        }
        max_limit = interval_max_limits.get(interval, 499)  # 其他周期最大499条
        
        sdk_limit = limit
        if sdk_limit > max_limit:
            sdk_limit = max_limit
            logger.debug(f"[API] SDK模式下限制limit为{max_limit}（interval={interval}），原请求limit={limit}")
        
        logger.info(f"[API] 从SDK获取K线数据: symbol={symbol}, interval={interval}, limit={sdk_limit}")
        
        # 调用SDK获取K线数据
        klines_raw = market_fetcher._futures_client.get_klines(
            symbol=symbol,
            interval=interval,
            limit=sdk_limit,
            startTime=start_timestamp,  # 如果提供了startTime，也传入
            endTime=end_timestamp  # 如果提供了endTime，也传入
        )
        
        if not klines_raw or len(klines_raw) == 0:
            logger.warning(f"[API] SDK未返回K线数据: symbol={symbol}, interval={interval}")
            klines = []
        else:
            # SDK返回的数据是倒序的（从新到旧），数组[0]是最新的K线，数组[-1]是最旧的K线
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
            # 确保与前端期望的数据顺序一致
            # 前端K线图表从左到右显示，左边是最旧的数据，右边是最新的数据，所以需要从旧到新的顺序
            formatted_klines.sort(key=lambda x: x.get('timestamp', 0))
            klines = formatted_klines
            
            logger.info(f"[API] SDK查询完成，共获取 {len(klines)} 条K线数据（已排序为从旧到新，包含最新K线）")
        
        # 记录返回数据信息，添加客户端IP
        klines_count = len(klines) if klines else 0
        logger.info(f"[API] 获取K线历史数据查询完成: symbol={symbol}, interval={interval}, 返回数据条数={klines_count}, client_ip={client_ip}")
        
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
        else:
            logger.warning(f"[API] 未找到K线历史数据: symbol={symbol}, interval={interval}, client_ip={client_ip}")
        
        response_data = {
            'symbol': symbol,
            'interval': interval,
            'source': 'sdk',
            'data': klines,
            'count': klines_count  # 添加数据条数字段，便于前端调试
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"[API] 获取K线数据失败: symbol={symbol if 'symbol' in locals() else 'N/A'}, interval={interval if 'interval' in locals() else 'N/A'}, error={e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# ============ Main Entry Point ============

if __name__ == '__main__':
    logger.info("\n" + "=" * 60)
    logger.info("AIFutureTrade Trading application")
    logger.info("=" * 60)
    logger.info("Initializing database...")

    # Initialize database and trading engines within application context
    with app.app_context():
        db.init_db()
        logger.info("Database initialized")
    # 根据配置决定是否启动交易循环
    if TRADING_LOOP_ENABLED:
        logger.info("Initializing trading engines...")
        init_trading_engines()
        logger.info("Trading engines initialized")
        logger.info("Starting trading loops immediately...")
        _start_trading_loops()
    else:
        logger.info("Trading loops are disabled (TRADING_LOOP_ENABLED=False)")
        logger.info("Trading loops are now managed by individual model containers (model-buy/model-sell)")

    logger.info("\n" + "=" * 60)
    logger.info("AIFutureTrade Trading application is running!")
    logger.info("API Server: http://0.0.0.0:5000")
    logger.info("Available endpoints:")
    logger.info("  POST /api/strategy/validate-code")
    logger.info("  GET  /api/market/klines")
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

