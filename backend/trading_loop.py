"""
交易循环模块 - 买入和卖出决策循环

本模块包含自动交易的买入和卖出决策循环逻辑，独立于主应用文件。
"""

import time
import logging
from datetime import datetime, timezone, timedelta
import common.config as app_config
from common.database.database_models import ModelsDatabase

logger = logging.getLogger(__name__)


def get_buy_interval_seconds(db) -> int:
    """读取买入交易频率设置（分钟）并返回秒数"""
    default_interval_seconds = getattr(app_config, 'TRADING_INTERVAL', 3600)
    default_minutes = max(1, int(default_interval_seconds / 60))
    try:
        settings = db.get_settings()
        minutes = int(settings.get('buy_frequency_minutes', default_minutes))
    except Exception as e:
        logger.warning(f"Unable to load buy trading frequency setting: {e}")
        minutes = default_minutes

    minutes = max(1, min(1440, minutes))
    return minutes * 60


def get_sell_interval_seconds(db) -> int:
    """读取卖出交易频率设置（分钟）并返回秒数"""
    default_interval_seconds = getattr(app_config, 'TRADING_INTERVAL', 3600)
    default_minutes = max(1, int(default_interval_seconds / 60))
    try:
        settings = db.get_settings()
        minutes = int(settings.get('sell_frequency_minutes', default_minutes))
    except Exception as e:
        logger.warning(f"Unable to load sell trading frequency setting: {e}")
        minutes = default_minutes

    minutes = max(1, min(1440, minutes))
    return minutes * 60


def trading_buy_loop(auto_trading, trading_engines, db):
    """买入交易循环 - 只执行买入决策"""
    logger.info("Trading buy loop started")
    
    # 创建 ModelsDatabase 实例用于模型操作
    models_db = ModelsDatabase(pool=db._pool if hasattr(db, '_pool') else None)

    while auto_trading:
        try:
            if not trading_engines:
                time.sleep(5)
                continue

            logger.info(f"\n{'='*60}")
            logger.info(f"BUY CYCLE: {datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"Active models: {len(trading_engines)}")
            logger.info(f"{'='*60}")

            for model_id, engine in list(trading_engines.items()):
                try:
                    # 检查模型的 auto_buy_enabled 字段
                    # 如果为 0（False），则跳过该模型的买入决策
                    if not models_db.is_model_auto_buy_enabled(model_id):
                        logger.info(f"SKIP: Model {model_id} - auto_buy_enabled=0, skipping AI buy decision")
                        continue

                    # 只有 auto_buy_enabled=1 的模型才会执行买入决策
                    logger.info(f"\nEXEC BUY: Model {model_id} - auto_buy_enabled=1, executing AI buy decision")
                    result = engine.execute_buy_cycle()

                    if result.get('success'):
                        logger.info(f"OK: Model {model_id} buy cycle completed")
                        if result.get('executions'):
                            for exec_result in result['executions']:
                                signal = exec_result.get('signal', 'unknown')
                                symbol = exec_result.get('future', exec_result.get('symbol', 'unknown'))
                                msg = exec_result.get('message', '')
                                if signal not in ['hold', 'close_position', 'stop_loss', 'take_profit']:
                                    logger.info(f"  BUY TRADE: {symbol}: {msg}")
                    else:
                        error = result.get('error', 'Unknown error')
                        logger.warning(f"Model {model_id} buy cycle failed: {error}")

                except Exception as e:
                    logger.error(f"Model {model_id} buy cycle exception: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    continue

            interval_seconds = get_buy_interval_seconds(db)
            interval_minutes = interval_seconds / 60
            logger.info(f"\n{'='*60}")
            logger.info(f"BUY SLEEP: Waiting {interval_minutes:.1f} minute(s) for next buy cycle")
            logger.info(f"{'='*60}\n")

            time.sleep(interval_seconds)

        except Exception as e:
            logger.critical(f"\nBuy trading loop error: {e}")
            import traceback
            logger.critical(traceback.format_exc())
            logger.info("RETRY: Retrying in 60 seconds\n")
            time.sleep(60)

    logger.info("Trading buy loop stopped")


def trading_sell_loop(auto_trading, trading_engines, db):
    """卖出交易循环 - 只执行卖出决策"""
    logger.info("Trading sell loop started")
    
    # 创建 ModelsDatabase 实例用于模型操作
    models_db = ModelsDatabase(pool=db._pool if hasattr(db, '_pool') else None)

    while auto_trading:
        try:
            if not trading_engines:
                time.sleep(5)
                continue

            logger.info(f"\n{'='*60}")
            logger.info(f"SELL CYCLE: {datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"Active models: {len(trading_engines)}")
            logger.info(f"{'='*60}")

            for model_id, engine in list(trading_engines.items()):
                try:
                    # 检查模型的 auto_sell_enabled 字段
                    # 如果为 0（False），则跳过该模型的 卖出决策
                    if not models_db.is_model_auto_sell_enabled(model_id):
                        logger.info(f"SKIP: Model {model_id} - auto_sell_enabled=0, skipping AI sell decision")
                        continue

                    # 只有 auto_sell_enabled=1 的模型才会执行 卖出决策
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

                except Exception as e:
                    logger.error(f"Model {model_id} sell cycle exception: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    continue

            interval_seconds = get_sell_interval_seconds(db)
            interval_minutes = interval_seconds / 60
            logger.info(f"\n{'='*60}")
            logger.info(f"SELL SLEEP: Waiting {interval_minutes:.1f} minute(s) for next sell cycle")
            logger.info(f"{'='*60}\n")

            time.sleep(interval_seconds)

        except Exception as e:
            logger.critical(f"\nSell trading loop error: {e}")
            import traceback
            logger.critical(traceback.format_exc())
            logger.info("RETRY: Retrying in 60 seconds\n")
            time.sleep(60)

    logger.info("Trading sell loop stopped")

