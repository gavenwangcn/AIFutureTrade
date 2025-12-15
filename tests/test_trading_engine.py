import sys
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional
from unittest.mock import MagicMock, patch

# 设置日志级别以便查看详细信息
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 添加项目根目录到Python路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from trade.trading_engine import TradingEngine
from common.binance_futures import BinanceFuturesOrderClient

def test_buy_to_enter(engine, decisions, market_state, portfolio):
    """测试buy_to_enter信号是否调用_execute_buy"""
    logger.info("开始测试buy_to_enter场景...")
    
    # 调用被测试方法
    results = engine._execute_decisions(decisions, market_state, portfolio)
    
    # 验证结果
    logger.info(f"buy_to_enter测试结果: {results}")
    if len(results) == 1 and results[0]['symbol'] == 'BTCUSDT':
        logger.info("buy_to_enter测试通过")
    else:
        logger.error("buy_to_enter测试失败")
    
    return results

def test_sell_to_enter(engine, decisions, market_state, portfolio):
    """测试sell_to_enter信号是否调用_execute_buy"""
    logger.info("开始测试sell_to_enter场景...")
    
    # 调用被测试方法
    results = engine._execute_decisions(decisions, market_state, portfolio)
    
    # 验证结果
    logger.info(f"sell_to_enter测试结果: {results}")
    if len(results) == 1 and results[0]['symbol'] == 'BTCUSDT':
        logger.info("sell_to_enter测试通过")
    else:
        logger.error("sell_to_enter测试失败")
    
    return results

def test_close_position(engine, decisions, market_state, portfolio):
    """测试close_position信号是否调用_execute_close"""
    logger.info("开始测试close_position场景...")
    
    # 调用被测试方法
    results = engine._execute_decisions(decisions, market_state, portfolio)
    
    # 验证结果
    logger.info(f"close_position测试结果: {results}")
    if len(results) == 1 and results[0]['symbol'] == 'BTCUSDT':
        logger.info("close_position测试通过")
    else:
        logger.error("close_position测试失败")
    
    return results

def test_stop_loss(engine, decisions, market_state, portfolio):
    """测试stop_loss信号是否调用_execute_stop_loss"""
    logger.info("开始测试stop_loss场景...")
    
    # 调用被测试方法
    results = engine._execute_decisions(decisions, market_state, portfolio)
    
    # 验证结果
    logger.info(f"stop_loss测试结果: {results}")
    if len(results) == 1 and results[0]['symbol'] == 'BTCUSDT':
        logger.info("stop_loss测试通过")
    else:
        logger.error("stop_loss测试失败")
    
    return results

def test_take_profit(engine, decisions, market_state, portfolio):
    """测试take_profit信号是否调用_execute_take_profit"""
    logger.info("开始测试take_profit场景...")
    
    # 调用被测试方法
    results = engine._execute_decisions(decisions, market_state, portfolio)
    
    # 验证结果
    logger.info(f"take_profit测试结果: {results}")
    if len(results) == 1 and results[0]['symbol'] == 'BTCUSDT':
        logger.info("take_profit测试通过")
    else:
        logger.error("take_profit测试失败")
    
    return results

def test_binance_client_creation(engine, decisions, market_state, portfolio):
    """测试每次调用_execute_decisions时是否创建新的BinanceFuturesOrderClient"""
    logger.info("开始测试Binance客户端创建场景...")
    
    # 模拟BinanceFuturesOrderClient类
    with patch('trade.trading_engine.BinanceFuturesOrderClient') as mock_client_class:
        # 创建模拟客户端
        mock_client = MagicMock()
        
        # 模拟market_trade方法返回一个模拟结果
        mock_client.market_trade.return_value = {
            'orderId': 12345,
            'symbol': 'BTCUSDT',
            'status': 'NEW'
        }
        
        # 设置模拟类返回我们的模拟客户端
        mock_client_class.return_value = mock_client
        
        # 调用被测试方法
        results = engine._execute_decisions(decisions, market_state, portfolio)
        
        # 验证结果
        logger.info(f"Binance客户端创建测试结果: {results}")
        if len(results) == 1 and results[0]['symbol'] == 'BTCUSDT':
            logger.info("Binance客户端创建测试通过")
        else:
            logger.error("Binance客户端创建测试失败")
        
        # 验证BinanceFuturesOrderClient被创建
        logger.info(f"BinanceFuturesOrderClient创建次数: {mock_client_class.call_count}")
        
        # 验证market_trade方法被调用
        logger.info(f"market_trade调用次数: {mock_client.market_trade.call_count}")
    
    return results

def main():
    """主函数，用于执行测试"""
    logger.info("开始运行TradingEngine测试...")
    
    # 创建实例
    logger.info("创建必要的实例...")
    
    # 创建模拟数据库
    mock_db = MagicMock()
    
    # 模拟模型配置
    mock_model = {
        'max_positions': 5,
        'api_key': 'LBtjhBgX1RCksNJDdOoJPeDD30Z70YIGHHH9DrqjIDDkK7xcPRQcgydPxGRr6MN1',
        'api_secret': '55arJnwlytDflHv151UpHN1s32ACnJZEs86mbc79wGyeuSUJNHTDPN7jEgBbqO6I'
    }
    mock_db.get_model.return_value = mock_model
    
    # 模拟模型ID映射
    mock_db._get_model_id_mapping.return_value = {1: 'model_1_uuid'}
    
    # 模拟生成ID
    mock_db._generate_id.return_value = 'test_trade_id'
    
    # 模拟数据库表名
    mock_db.trades_table = 'trades'
    
    # 创建模拟市场数据获取器
    mock_market_fetcher = MagicMock()
    
    # 创建模拟AI交易者
    mock_ai_trader = MagicMock()
    
    # 创建TradingEngine实例
    engine = TradingEngine(
        model_id=1,
        db=mock_db,
        market_fetcher=mock_market_fetcher,
        ai_trader=mock_ai_trader,
        trade_fee_rate=0.001
    )
    
    # 提前设置好各个场景的输入数据
    logger.info("准备测试数据...")
    
    # buy_to_enter测试数据
    buy_to_enter_decisions = {
        'BTCUSDT': {
            'signal': 'buy_to_enter',
            'quantity': 100,
            'leverage': 10,
            'callback_rate': 1.0
        }
    }
    
    # sell_to_enter测试数据
    sell_to_enter_decisions = {
        'BTCUSDT': {
            'signal': 'sell_to_enter',
            'quantity': 100,
            'leverage': 10,
            'callback_rate': 1.0
        }
    }
    
    # close_position测试数据
    close_position_decisions = {
        'BTCUSDT': {
            'signal': 'close_position'
        }
    }
    
    # stop_loss测试数据
    stop_loss_decisions = {
        'BTCUSDT': {
            'signal': 'stop_loss',
            'stop_price': 43000.0
        }
    }
    
    # take_profit测试数据
    take_profit_decisions = {
        'BTCUSDT': {
            'signal': 'take_profit',
            'stop_price': 46000.0
        }
    }
    
    # 市场状态数据
    market_state = {
        'BTCUSDT': {
            'price': 45000.0
        }
    }
    
    # 空持仓投资组合
    empty_portfolio = {
        'cash': 10000.0,
        'positions': []
    }
    
    # 有持仓投资组合（多头）
    long_portfolio = {
        'cash': 10000.0,
        'positions': [
            {
                'symbol': 'BTCUSDT',
                'position_amt': 100,
                'position_side': 'LONG',
                'entry_price': 44000.0
            }
        ]
    }
    
    # 执行各个场景的测试
    logger.info("=" * 50)
    test_buy_to_enter(engine, buy_to_enter_decisions, market_state, empty_portfolio)
    
    logger.info("=" * 50)
    test_sell_to_enter(engine, sell_to_enter_decisions, market_state, empty_portfolio)
    
    logger.info("=" * 50)
    test_close_position(engine, close_position_decisions, market_state, long_portfolio)
    
    logger.info("=" * 50)
    test_stop_loss(engine, stop_loss_decisions, market_state, long_portfolio)
    
    logger.info("=" * 50)
    test_take_profit(engine, take_profit_decisions, market_state, long_portfolio)
    
    logger.info("=" * 50)
    test_binance_client_creation(engine, buy_to_enter_decisions, market_state, empty_portfolio)
    
    logger.info("=" * 50)
    logger.info("所有测试场景执行完成")

if __name__ == '__main__':
    main()