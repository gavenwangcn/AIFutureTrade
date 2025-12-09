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
    db = Database()
    db.init_db()  # 初始化数据库表
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
                print("=" * 80)
                # 打印整体数据（JSON格式，便于查看完整数据结构）
                print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
                print("=" * 80)
            else:
                print(f"✗ 获取 {interval} 数据失败（返回值为空）")
                
        except Exception as e:
            print(f"✗ 调用 {interval} 方法出错: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_market_data_methods()