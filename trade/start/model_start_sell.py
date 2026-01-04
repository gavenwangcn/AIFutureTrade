"""
模型卖出循环启动脚本

用于在Docker容器中启动单个模型的卖出交易循环。
从环境变量 MODEL_ID 获取模型ID，初始化对应的交易引擎并启动卖出循环。

使用方法：
    MODEL_ID=1 python -m trade.start.model_start_sell

或通过Docker容器启动：
    docker run -e MODEL_ID=1 <image> python -m trade.start.model_start_sell
"""

import os
import sys
import time
import logging
from datetime import datetime, timezone, timedelta

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import trade.common.config as app_config
from trade.trading_engine import TradingEngine
from trade.market.market_data import MarketDataFetcher
from trade.ai.ai_trader import AITrader
from trade.strategy.strategy_trader import StrategyTrader
from trade.common.database.database_basic import Database
from trade.common.database.database_models import ModelsDatabase
from trade.common.database.database_providers import ProvidersDatabase
from trade.common.database.database_strategys import StrategysDatabase
from trade.common.database.database_settings import SettingsDatabase

# ============ 日志配置 ============

def get_log_level():
    """获取日志级别"""
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

logger = logging.getLogger(__name__)

# ============ 配置和初始化 ============

def get_model_id_from_env() -> int:
    """从环境变量获取模型ID"""
    model_id_str = os.getenv('MODEL_ID')
    if not model_id_str:
        logger.error("MODEL_ID environment variable is not set")
        sys.exit(1)
    
    try:
        model_id = int(model_id_str)
        if model_id <= 0:
            raise ValueError("MODEL_ID must be a positive integer")
        return model_id
    except ValueError as e:
        logger.error(f"Invalid MODEL_ID: {model_id_str}, {e}")
        sys.exit(1)

def get_sell_interval_seconds(db) -> int:
    """读取卖出交易频率设置（分钟）并返回秒数"""
    default_interval_seconds = getattr(app_config, 'TRADING_INTERVAL', 3600)
    default_minutes = max(1, int(default_interval_seconds / 60))
    try:
        settings_db = SettingsDatabase(pool=db._pool if hasattr(db, '_pool') else None)
        settings = settings_db.get_settings()
        minutes = int(settings.get('sell_frequency_minutes', default_minutes))
    except Exception as e:
        logger.warning(f"Unable to load sell trading frequency setting: {e}")
        minutes = default_minutes

    minutes = max(1, min(1440, minutes))
    return minutes * 60

def init_trading_engine_for_model(model_id: int, db, market_fetcher):
    """初始化指定模型的交易引擎"""
    logger.info(f"Initializing trading engine for model {model_id}...")
    
    models_db = ModelsDatabase(pool=db._pool if hasattr(db, '_pool') else None)
    providers_db = ProvidersDatabase(pool=db._pool if hasattr(db, '_pool') else None)
    strategys_db = StrategysDatabase(pool=db._pool if hasattr(db, '_pool') else None)
    
    model = models_db.get_model(model_id)
    if not model:
        logger.error(f"Model {model_id} not found, cannot initialize trading engine")
        return None
    
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
            logger.error(f"Provider not found for model {model_id}, cannot initialize AITrader")
            return None
        
        logger.info(f"Creating AITrader instance for model {model_id} with provider {provider.get('provider_type', 'openai')} and model {model['model_name']}")
        
        trader = AITrader(
            provider_type=provider.get('provider_type', 'openai'),
            api_key=provider['api_key'],
            api_url=provider['api_url'],
            model_name=model['model_name'],
            db=db,
            market_fetcher=market_fetcher
        )
    else:
        # 使用策略交易（默认）
        logger.info(f"Creating StrategyTrader instance for model {model_id}")
        
        trader = StrategyTrader(
            db=db,
            model_id=model_id
        )
    
    TRADE_FEE_RATE = getattr(app_config, 'TRADE_FEE_RATE', 0.002)
    
    engine = TradingEngine(
        model_id=model_id,
        db=db,
        market_fetcher=market_fetcher,
        trader=trader,
        trade_fee_rate=TRADE_FEE_RATE
    )
    
    logger.info(f"Successfully initialized trading engine for model {model_id} with trade_type={trade_type}")
    return engine

def trading_sell_loop_for_model(model_id: int, engine: TradingEngine, db):
    """单个模型的卖出交易循环"""
    logger.info(f"Trading sell loop started for model {model_id}")
    
    # 创建 ModelsDatabase 和 StrategysDatabase 实例用于模型操作
    models_db = ModelsDatabase(pool=db._pool if hasattr(db, '_pool') else None)
    strategys_db = StrategysDatabase(pool=db._pool if hasattr(db, '_pool') else None)
    
    auto_trading = True
    
    while auto_trading:
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"SELL CYCLE: {datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"Model ID: {model_id}")
            logger.info(f"{'='*60}")
            
            # 检查模型的 auto_sell_enabled 字段
            if not models_db.is_model_auto_sell_enabled(model_id):
                logger.info(f"SKIP: Model {model_id} - auto_sell_enabled=0, skipping AI sell decision")
            else:
                # 对于 trade_type='strategy' 的模型，检查是否存在卖出策略
                model = models_db.get_model(model_id)
                if model:
                    trade_type = model.get('trade_type', 'strategy')
                    if trade_type == 'strategy':
                        # 获取模型ID映射
                        model_mapping = models_db._get_model_id_mapping()
                        # 查询卖出策略
                        sell_strategies = strategys_db.get_model_strategies_by_int_id(
                            model_id, 
                            'sell', 
                            model_mapping
                        )
                        if not sell_strategies:
                            logger.info(f"SKIP: Model {model_id} - trade_type=strategy but no sell strategy configured, skipping sell decision")
                        else:
                            # 执行卖出决策
                            logger.info(f"\nEXEC SELL: Model {model_id} - auto_sell_enabled=1, executing AI sell decision")
                            result = engine.execute_sell_cycle()
                            
                            if result.get('success'):
                                logger.info(f"OK: Model {model_id} sell cycle completed")
                                if result.get('executions'):
                                    for exec_result in result['executions']:
                                        signal = exec_result.get('signal', 'unknown')
                                        symbol = exec_result.get('future', exec_result.get('symbol', 'unknown'))
                                        msg = exec_result.get('message', '')
                                        if signal in ['close_position', 'stop_loss', 'take_profit']:
                                            logger.info(f"  SELL TRADE: {symbol}: {msg}")
                            else:
                                error = result.get('error', 'Unknown error')
                                logger.warning(f"Model {model_id} sell cycle failed: {error}")
                    else:
                        # AI交易类型，直接执行
                        logger.info(f"\nEXEC SELL: Model {model_id} - auto_sell_enabled=1, executing AI sell decision")
                        result = engine.execute_sell_cycle()
                        
                        if result.get('success'):
                            logger.info(f"OK: Model {model_id} sell cycle completed")
                            if result.get('executions'):
                                for exec_result in result['executions']:
                                    signal = exec_result.get('signal', 'unknown')
                                    symbol = exec_result.get('future', exec_result.get('symbol', 'unknown'))
                                    msg = exec_result.get('message', '')
                                    if signal in ['close_position', 'stop_loss', 'take_profit']:
                                        logger.info(f"  SELL TRADE: {symbol}: {msg}")
                        else:
                            error = result.get('error', 'Unknown error')
                            logger.warning(f"Model {model_id} sell cycle failed: {error}")
            
            interval_seconds = get_sell_interval_seconds(db)
            interval_minutes = interval_seconds / 60
            logger.info(f"\n{'='*60}")
            logger.info(f"SELL SLEEP: Waiting {interval_minutes:.1f} minute(s) for next sell cycle")
            logger.info(f"{'='*60}\n")
            
            time.sleep(interval_seconds)
            
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, stopping sell loop...")
            auto_trading = False
            break
        except Exception as e:
            logger.critical(f"\nSell trading loop error: {e}")
            import traceback
            logger.critical(traceback.format_exc())
            logger.info("RETRY: Retrying in 60 seconds\n")
            time.sleep(60)
    
    logger.info(f"Trading sell loop stopped for model {model_id}")

# ============ 主程序 ============

def main():
    """主函数"""
    # 从环境变量获取模型ID
    model_id = get_model_id_from_env()
    logger.info(f"Starting sell loop for model {model_id}")
    
    # 初始化数据库
    logger.info("Initializing database...")
    db = Database()
    
    # 初始化数据库表
    try:
        from trade.common.database.database_init import init_all_database_tables
        init_all_database_tables(db.command)
        logger.info("Database tables initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database tables: {e}")
        sys.exit(1)
    
    # 初始化市场数据获取器
    logger.info("Initializing market data fetcher...")
    market_fetcher = MarketDataFetcher(db)
    
    # 初始化交易引擎
    engine = init_trading_engine_for_model(model_id, db, market_fetcher)
    if not engine:
        logger.error(f"Failed to initialize trading engine for model {model_id}")
        sys.exit(1)
    
    # 启动卖出循环
    try:
        trading_sell_loop_for_model(model_id, engine, db)
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        import traceback
        logger.critical(traceback.format_exc())
        sys.exit(1)

if __name__ == '__main__':
    main()

