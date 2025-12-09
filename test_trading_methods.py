#!/usr/bin/env python3
"""
测试Binance Futures客户端的交易方法

需要在环境变量中设置：
- BINANCE_API_KEY: 币安API密钥
- BINANCE_API_SECRET: 币安API密钥
"""
import os
import logging
from common.binance_futures import BinanceFuturesClient

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_trading_methods():
    """测试交易方法"""
    # 从环境变量获取API密钥
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')
    
    if not api_key or not api_secret:
        logger.error("请在环境变量中设置BINANCE_API_KEY和BINANCE_API_SECRET")
        return
    
    try:
        # 初始化客户端
        client = BinanceFuturesClient(
            api_key=api_key,
            api_secret=api_secret,
            testnet=True,  # 使用测试网络
        )
        
        logger.info("Binance Futures客户端初始化成功")
        
        # 示例交易参数
        symbol = "BTC"
        quantity = 0.001
        price = 40000.0
        stop_price = 39500.0
        callback_rate = 0.5
        
        # 1. 测试止损交易 (STOP_MARKET)
        logger.info("\n=== 测试止损交易 (STOP_MARKET) ===")
        try:
            # 注意：这只是演示，实际运行会下单
            # response = client.stop_loss_trade(
            #     symbol=symbol,
            #     side="SELL",
            #     order_type="STOP_MARKET",
            #     stop_price=stop_price,
            # )
            logger.info("止损交易 (STOP_MARKET) 示例代码：")
            logger.info(f"client.stop_loss_trade(\n    symbol='{symbol}',\n    side='SELL',\n    order_type='STOP_MARKET',\n    stop_price={stop_price},\n)")
        except Exception as e:
            logger.error(f"止损交易测试失败: {e}")
        
        # 2. 测试止损交易 (STOP)
        logger.info("\n=== 测试止损交易 (STOP) ===")
        try:
            # 注意：这只是演示，实际运行会下单
            # response = client.stop_loss_trade(
            #     symbol=symbol,
            #     side="SELL",
            #     order_type="STOP",
            #     quantity=quantity,
            #     price=price,
            #     stop_price=stop_price,
            # )
            logger.info("止损交易 (STOP) 示例代码：")
            logger.info(f"client.stop_loss_trade(\n    symbol='{symbol}',\n    side='SELL',\n    order_type='STOP',\n    quantity={quantity},\n    price={price},\n    stop_price={stop_price},\n)")
        except Exception as e:
            logger.error(f"止损交易测试失败: {e}")
        
        # 3. 测试止盈交易 (TAKE_PROFIT_MARKET)
        logger.info("\n=== 测试止盈交易 (TAKE_PROFIT_MARKET) ===")
        try:
            # 注意：这只是演示，实际运行会下单
            # response = client.take_profit_trade(
            #     symbol=symbol,
            #     side="SELL",
            #     order_type="TAKE_PROFIT_MARKET",
            #     stop_price=40500.0,
            # )
            logger.info("止盈交易 (TAKE_PROFIT_MARKET) 示例代码：")
            logger.info(f"client.take_profit_trade(\n    symbol='{symbol}',\n    side='SELL',\n    order_type='TAKE_PROFIT_MARKET',\n    stop_price=40500.0,\n)")
        except Exception as e:
            logger.error(f"止盈交易测试失败: {e}")
        
        # 4. 测试跟踪止损交易
        logger.info("\n=== 测试跟踪止损交易 ===")
        try:
            # 注意：这只是演示，实际运行会下单
            # response = client.trailing_stop_market_trade(
            #     symbol=symbol,
            #     side="SELL",
            #     callback_rate=callback_rate,
            # )
            logger.info("跟踪止损交易示例代码：")
            logger.info(f"client.trailing_stop_market_trade(\n    symbol='{symbol}',\n    side='SELL',\n    callback_rate={callback_rate},\n)")
        except Exception as e:
            logger.error(f"跟踪止损交易测试失败: {e}")
        
        # 5. 测试平仓交易
        logger.info("\n=== 测试平仓交易 ===")
        try:
            # 注意：这只是演示，实际运行会下单
            # response = client.close_position_trade(
            #     symbol=symbol,
            #     side="BUY",
            #     order_type="STOP_MARKET",
            #     stop_price=39500.0,
            # )
            logger.info("平仓交易示例代码：")
            logger.info(f"client.close_position_trade(\n    symbol='{symbol}',\n    side='BUY',\n    order_type='STOP_MARKET',\n    stop_price=39500.0,\n)")
        except Exception as e:
            logger.error(f"平仓交易测试失败: {e}")
        
    except Exception as e:
        logger.error(f"初始化客户端失败: {e}")


if __name__ == "__main__":
    test_trading_methods()
