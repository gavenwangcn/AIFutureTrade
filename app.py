@app.route('/api/market/leaderboard', methods=['GET'])
def get_market_leaderboard():
    limit = request.args.get('limit', type=int)
    force = request.args.get('force', default=0, type=int)
    try:
        data = market_fetcher.sync_leaderboard(force=bool(force), limit=limit)
        return jsonify(data)
    except Exception as exc:
        logger.error(f"Failed to load leaderboard: {exc}")
        return jsonify({'error': str(exc)}), 500


@socketio.on('leaderboard:request')
def handle_leaderboard_request(payload=None):
    payload = payload or {}
    limit = payload.get('limit')
    try:
        data = market_fetcher.get_leaderboard(limit=limit)
        emit('leaderboard:update', data)
    except Exception as exc:
        emit('leaderboard:error', {'message': str(exc)})

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import os
import time
import threading
import json
import re
from datetime import datetime
from trading_engine import TradingEngine
from market_data import MarketDataFetcher
from ai_trader import AITrader
from database import Database
from version import __version__
from prompt_defaults import DEFAULT_BUY_CONSTRAINTS, DEFAULT_SELL_CONSTRAINTS

try:
    import config as app_config
except ImportError:  # pragma: no cover
    import config_example as app_config

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

import logging
import sys

# 从配置读取日志级别
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

# 从配置读取日志格式
log_format = getattr(app_config, 'LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_date_format = getattr(app_config, 'LOG_DATE_FORMAT', '%Y-%m-%d %H:%M:%S')

# 配置日志系统
logging.basicConfig(
    level=get_log_level(),
    format=log_format,
    datefmt=log_date_format,
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# 设置 werkzeug 日志级别为 WARNING（减少 Flask 的请求日志）
logging.getLogger('werkzeug').setLevel(logging.WARNING)

# 创建应用日志器
logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = 'trading_bot.db'
env_db_path = os.getenv('DATABASE_PATH')
config_db_path = getattr(app_config, 'DATABASE_PATH', None)
db_path = env_db_path or config_db_path or DEFAULT_DB_PATH
db = Database(db_path)
market_fetcher = MarketDataFetcher(db)
trading_engines = {}
auto_trading = getattr(app_config, 'AUTO_TRADING', True)
TRADE_FEE_RATE = getattr(app_config, 'TRADE_FEE_RATE', 0.001)
LEADERBOARD_REFRESH_INTERVAL = getattr(app_config, 'FUTURES_LEADERBOARD_REFRESH', 180)

leaderboard_thread = None
leaderboard_stop_event = threading.Event()


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


def _leaderboard_loop():
    logger.info("Leaderboard loop started")
    wait_seconds = max(5, LEADERBOARD_REFRESH_INTERVAL)
    while not leaderboard_stop_event.is_set():
        try:
            data = market_fetcher.sync_leaderboard(force=False)
            if data:
                socketio.emit('leaderboard:update', data)
        except Exception as exc:
            logger.error(f"Leaderboard sync failed: {exc}")
        leaderboard_stop_event.wait(wait_seconds)
    logger.info("Leaderboard loop stopped")


def start_leaderboard_worker():
    global leaderboard_thread
    if leaderboard_thread and leaderboard_thread.is_alive():
        return
    leaderboard_stop_event.clear()
    leaderboard_thread = threading.Thread(target=_leaderboard_loop, daemon=True)
    leaderboard_thread.start()


def stop_leaderboard_worker():
    leaderboard_stop_event.set()

@app.route('/')
def index():
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
        # This is a placeholder - implement actual API call based on provider
        # For now, return empty list or common models
        models = []

        # Try to detect provider type and call appropriate API
        if 'openai.com' in api_url.lower():
            # OpenAI API call
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
            # DeepSeek API
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

# ============ Futures Configuration Endpoints ============

@app.route('/api/futures', methods=['GET'])
def list_futures():
    try:
        futures = db.get_futures()
        return jsonify(futures)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/futures', methods=['POST'])
def add_future_config():
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
    try:
        db.delete_future(future_id)
        return jsonify({'message': 'Future deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============ Model API Endpoints ============

@app.route('/api/models', methods=['GET'])
def get_models():
    models = db.get_all_models()
    return jsonify(models)

@app.route('/api/models', methods=['POST'])
def add_model():
    data = request.json
    try:
        # Get provider info
        provider = db.get_provider(data['provider_id'])
        if not provider:
            return jsonify({'error': 'Provider not found'}), 404

        model_id = db.add_model(
            name=data['name'],
            provider_id=data['provider_id'],
            model_name=data['model_name'],
            initial_capital=float(data.get('initial_capital', 100000))
        )

        model = db.get_model(model_id)
        
        # Get provider info
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
            trade_fee_rate=TRADE_FEE_RATE  # 新增：传入费率
        )
        logger.info(f"Model {model_id} ({data['name']}) initialized")

        return jsonify({'id': model_id, 'message': 'Model added successfully'})

    except Exception as e:
        logger.error(f"Failed to add model: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<int:model_id>', methods=['DELETE'])
def delete_model(model_id):
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
        'auto_trading_enabled': bool(model.get('auto_trading_enabled', 1))
    })

@app.route('/api/models/<int:model_id>/trades', methods=['GET'])
def get_trades(model_id):
    limit = request.args.get('limit', 50, type=int)
    trades = db.get_trades(model_id, limit=limit)
    return jsonify(trades)

@app.route('/api/models/<int:model_id>/conversations', methods=['GET'])
def get_conversations(model_id):
    limit = request.args.get('limit', 20, type=int)
    conversations = db.get_conversations(model_id, limit=limit)
    return jsonify(conversations)

@app.route('/api/models/<int:model_id>/prompts', methods=['GET'])
def get_model_prompts(model_id):
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

@app.route('/api/aggregated/portfolio', methods=['GET'])
def get_aggregated_portfolio():
    """Get aggregated portfolio data across all models"""
    symbols = get_tracked_symbols()
    prices_data = market_fetcher.get_current_prices(symbols)
    current_prices = {symbol: data['price'] for symbol, data in prices_data.items()}

    # Get aggregated data
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

    # Get multi-model chart data
    chart_data = db.get_multi_model_chart_data(limit=100)

    return jsonify({
        'portfolio': total_portfolio,
        'chart_data': chart_data,
        'model_count': len(models)
    })

@app.route('/api/models/chart-data', methods=['GET'])
def get_models_chart_data():
    """Get chart data for all models"""
    limit = request.args.get('limit', 100, type=int)
    chart_data = db.get_multi_model_chart_data(limit=limit)
    return jsonify(chart_data)

@app.route('/api/market/prices', methods=['GET'])
def get_market_prices():
    symbols = get_tracked_symbols()
    prices = market_fetcher.get_prices(symbols)
    return jsonify(prices)

@app.route('/api/models/<int:model_id>/execute', methods=['POST'])
def execute_trading(model_id):
    if model_id not in trading_engines:
        engine, error = init_trading_engine_for_model(model_id)
        if error:
            return jsonify({'error': error}), 404
    else:
        engine = trading_engines[model_id]

    # Manual执行视为重新开启自动交易
    db.set_model_auto_trading(model_id, True)

    try:
        result = engine.execute_trading_cycle()
        result['auto_trading_enabled'] = True
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/models/<int:model_id>/auto-trading', methods=['POST'])
def set_model_auto_trading(model_id):
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

def trading_loop():
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

@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    models = db.get_all_models()
    leaderboard = []
    
    symbols = get_tracked_symbols()
    prices_data = market_fetcher.get_prices(symbols)
    current_prices = {symbol: data['price'] for symbol, data in prices_data.items()}
    
    for model in models:
        portfolio = db.get_portfolio(model['id'], current_prices)
        account_value = portfolio.get('total_value', model['initial_capital'])
        returns = ((account_value - model['initial_capital']) / model['initial_capital']) * 100
        
        leaderboard.append({
            'model_id': model['id'],
            'model_name': model['name'],
            'account_value': account_value,
            'returns': returns,
            'initial_capital': model['initial_capital']
        })
    
    leaderboard.sort(key=lambda x: x['returns'], reverse=True)
    return jsonify(leaderboard)

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

@app.route('/api/version', methods=['GET'])
def get_version():
    """Get current version information"""
    return jsonify({
        'current_version': __version__
    })

def compare_versions(version1, version2):
    """Compare two version strings.

    Returns:
        1 if version1 > version2
        0 if version1 == version2
        -1 if version1 < version2
    """
    def normalize(v):
        # Extract numeric parts from version string
        parts = re.findall(r'\d+', v)
        # Pad with zeros to make them comparable
        return [int(p) for p in parts]

    v1_parts = normalize(version1)
    v2_parts = normalize(version2)

    # Pad shorter version with zeros
    max_len = max(len(v1_parts), len(v2_parts))
    v1_parts.extend([0] * (max_len - len(v1_parts)))
    v2_parts.extend([0] * (max_len - len(v2_parts)))

    # Compare
    if v1_parts > v2_parts:
        return 1
    elif v1_parts < v2_parts:
        return -1
    else:
        return 0

def init_trading_engines():
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
                # Get provider info
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

if __name__ == '__main__':
    import webbrowser
    import os
    
    logger.info("\n" + "=" * 60)
    logger.info("AICoinTrade - Starting...")
    logger.info("=" * 60)
    logger.info("Initializing database...")
    
    db.init_db()
    
    logger.info("Database initialized")
    logger.info("Initializing trading engines...")
    
    init_trading_engines()
    
    if auto_trading:
        trading_thread = threading.Thread(target=trading_loop, daemon=True)
        trading_thread.start()
        logger.info("Auto-trading enabled")

    start_leaderboard_worker()
    
    logger.info("\n" + "=" * 60)
    logger.info("AICoinTrade is running!")
    logger.info("Server: http://localhost:5002")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60 + "\n")
    
    # 自动打开浏览器
    def open_browser():
        time.sleep(1.5)  # 等待服务器启动
        url = "http://localhost:5002"
        try:
            webbrowser.open(url)
            logger.info(f"Browser opened: {url}")
        except Exception as e:
            logger.warning(f"Could not open browser: {e}")
    
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()
    
    socketio.run(app, debug=False, host='0.0.0.0', port=5002, use_reloader=False)
