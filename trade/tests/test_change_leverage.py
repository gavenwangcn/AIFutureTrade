"""Manual test for common.binance_futures.BinanceFuturesOrderClient.change_initial_leverage.

Usage:
    export BINANCE_API_KEY=...
    export BINANCE_API_SECRET=...
    python trade/tests/test_change_leverage.py
    或
    python -m trade.tests.test_change_leverage

This script tests the change_initial_leverage method in BinanceFuturesOrderClient to ensure
it correctly modifies the initial leverage for a specified trading symbol.
"""

import logging
from math import fabs
import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径，以便导入项目模块（tests现在在trade/tests下）
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import trade.common.config as config
from trade.common.binance_futures import BinanceFuturesOrderClient

# 配置日志记录
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def test_change_initial_leverage(symbol: str = "MUSDT", leverage: int = 20) -> None:
    """测试修改初始杠杆方法
    
    Args:
        symbol: 要测试的交易对，默认MUSDT
        leverage: 要设置的杠杆倍数，默认20
    """
    # 创建客户端实例（使用测试网络）
    client = BinanceFuturesOrderClient(
        api_key='LBtjhBgX1RCksNJDdOoJPeDD30Z70YIGHHH9DrqjIDDkK7xcPRQcgydPxGRr6MN1',
        api_secret='55arJnwlytDflHv151UpHN1s32ACnJZEs86mbc79wGyeuSUJNHTDPN7jEgBbqO6I',
        testnet=False
    )
    
    logger.info(f"尝试修改 {symbol} 的初始杠杆为 {leverage} 倍...")
    result = client.change_initial_leverage(symbol=symbol, leverage=leverage)
    
    logger.info("修改成功！返回结果：")
    logger.info(result)
    
    # 验证返回结果
    assert result['symbol'] == symbol, f"返回的交易对不正确，期望 {symbol}，实际 {result['symbol']}"
    assert result['leverage'] == leverage, f"返回的杠杆倍数不正确，期望 {leverage}，实际 {result['leverage']}"
    
    logger.info("\n验证通过：返回的交易对和杠杆倍数正确")
    logger.info(f"交易对: {result['symbol']}")
    logger.info(f"新杠杆: {result['leverage']}")
    logger.info(f"最大名义价值: {result.get('max_notional_value', 'N/A')}")



if __name__ == "__main__":
    import argparse
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="测试修改Binance期货初始杠杆")
    parser.add_argument("-s", "--symbol", type=str, default="MUSDT", help="交易对，默认MUSDT")
    parser.add_argument("-l", "--leverage", type=int, default=20, help="杠杆倍数，默认20")
    args = parser.parse_args()
    
    try:
        # 加载API密钥
        #api_key, api_secret = _load_credentials()
        
        # 运行测试
        test_change_initial_leverage(
            symbol=args.symbol,
            leverage=args.leverage
        )
        
        logger.info("\n所有测试完成！")
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"测试失败：{e}")
        sys.exit(1)
