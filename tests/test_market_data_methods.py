import sys
import os
import json

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from market.market_data import MarketDataFetcher
from common.database_basic import Database

def test_market_data_methods():
    """测试7个时间周期的市场数据获取方法"""
    # 初始化数据库和市场数据获取器
    db = Database(auto_init=True)
    market_data = MarketDataFetcher(db)
    
    # 测试的交易对
    symbol = "BTC"
    
    # 测试7个时间周期的方法
    methods = [
        ("1m", market_data.get_market_data_1m),
        ("5m", market_data.get_market_data_5m),
        ("15m", market_data.get_market_data_15m),
        ("1h", market_data.get_market_data_1h),
        ("4h", market_data.get_market_data_4h),
        ("1d", market_data.get_market_data_1d),
        ("1w", market_data.get_market_data_1w)
    ]
    
    for interval, method in methods:
        print(f"\n===== 测试 {interval} 时间周期 ====")
        
        try:
            # 调用方法获取数据
            data = method(symbol)
            
            if data:
                print(f"✓ 成功获取 {interval} 数据")
                print(f"  Symbol: {data.get('symbol')}")
                print(f"  Timeframe: {data.get('timeframe')}")
                print(f"  Kline count: {len(data.get('klines', []))}")
                print(f"  Indicators: {list(data.get('indicators', {}).keys())}")
                print(f"  Metadata: {data.get('metadata')}")
                
                # 验证数据结构
                if 'klines' in data and len(data['klines']) > 0:
                    print(f"  First kline: {data['klines'][0]}")
                    print(f"  Last kline: {data['klines'][-1]}")
                
                if 'indicators' in data:
                    indicators = data['indicators']
                    print(f"  MA: {indicators.get('MA')}")
                    print(f"  MACD: {indicators.get('MACD')}")
                    print(f"  RSI: {indicators.get('RSI')}")
                    print(f"  VOL: {indicators.get('VOL')}")
            else:
                print(f"✗ 获取 {interval} 数据失败")
                
        except Exception as e:
            print(f"✗ 调用 {interval} 方法出错: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_market_data_methods()