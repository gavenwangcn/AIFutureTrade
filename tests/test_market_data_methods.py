import sys
import os
import json

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from market.market_data import MarketDataFetcher
from common.database_basic import Database

def estimate_tokens(data):
    """
    估算JSON数据的token数量
    使用简单方法：字符数 / 4（粗略估算，实际token数量可能因模型而异）
    更准确的方法可以使用tiktoken库，但这里使用简单估算
    """
    json_str = json.dumps(data, ensure_ascii=False, default=str)
    # 粗略估算：1 token ≈ 4 字符（对于英文和数字）
    # 对于中文，可能需要更多token，这里使用保守估算
    char_count = len(json_str)
    # 使用更保守的估算：1 token ≈ 3.5 字符（考虑中文字符和标点）
    estimated_tokens = int(char_count / 3.5)
    return estimated_tokens, char_count, json_str

def test_market_data_methods():
    """测试7个时间周期的市场数据获取方法，并计算token数量"""
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
    
    # 存储所有时间周期的数据用于token计算
    all_interval_data = {}
    interval_stats = {}
    
    print(f"\n{'='*80}")
    print(f"测试 {symbol} 的7个时间周期市场数据")
    print(f"{'='*80}\n")
    
    for interval, method in methods:
        print(f"\n===== 测试 {interval} 时间周期 ====")
        
        try:
            # 调用方法获取数据
            data = method(symbol)
            
            if data:
                print(f"✓ 成功获取 {interval} 数据")
                
                # 计算token数量
                tokens, char_count, json_str = estimate_tokens(data)
                
                # 统计K线数量
                kline_count = len(data.get('klines', []))
                
                # 统计指标数组长度
                indicators = data.get('indicators', {})
                ma5_length = len(indicators.get('MA', {}).get('MA5', [])) if indicators.get('MA') else 0
                
                # 存储数据用于后续统计
                all_interval_data[interval] = data
                interval_stats[interval] = {
                    'tokens': tokens,
                    'char_count': char_count,
                    'kline_count': kline_count,
                    'ma5_length': ma5_length
                }
                
                print(f"  K线数量: {kline_count}")
                print(f"  MA5数组长度: {ma5_length}")
                print(f"  字符数: {char_count:,}")
                print(f"  估算Token数: {tokens:,}")
                print("=" * 80)
                # 打印整体数据（JSON格式，便于查看完整数据结构）
                print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
                print("=" * 80)
            else:
                print(f"✗ 获取 {interval} 数据失败（返回值为空）")
                interval_stats[interval] = {
                    'tokens': 0,
                    'char_count': 0,
                    'kline_count': 0,
                    'ma5_length': 0
                }
                
        except Exception as e:
            print(f"✗ 调用 {interval} 方法出错: {e}")
            import traceback
            traceback.print_exc()
            interval_stats[interval] = {
                'tokens': 0,
                'char_count': 0,
                'kline_count': 0,
                'ma5_length': 0
            }
    
    # 计算汇总统计
    print(f"\n{'='*80}")
    print(f"{symbol} 所有时间周期数据统计汇总")
    print(f"{'='*80}\n")
    
    total_tokens = 0
    total_char_count = 0
    total_kline_count = 0
    
    print(f"{'时间周期':<10} {'K线数量':<12} {'MA5长度':<12} {'字符数':<15} {'Token数':<15}")
    print("-" * 80)
    
    for interval in ["1m", "5m", "15m", "1h", "4h", "1d", "1w"]:
        stats = interval_stats.get(interval, {})
        kline_count = stats.get('kline_count', 0)
        ma5_length = stats.get('ma5_length', 0)
        char_count = stats.get('char_count', 0)
        tokens = stats.get('tokens', 0)
        
        total_tokens += tokens
        total_char_count += char_count
        total_kline_count += kline_count
        
        print(f"{interval:<10} {kline_count:<12} {ma5_length:<12} {char_count:<15,} {tokens:<15,}")
    
    print("-" * 80)
    print(f"{'总计':<10} {total_kline_count:<12} {'-':<12} {total_char_count:<15,} {total_tokens:<15,}")
    print(f"\n{'='*80}")
    print(f"📊 {symbol} 一次提交7个时间周期指标数据需要的Token数量: {total_tokens:,}")
    print(f"   总字符数: {total_char_count:,}")
    print(f"   总K线数量: {total_kline_count:,}")
    print(f"{'='*80}\n")
    
    # 如果所有数据都成功获取，计算合并后的token数量（模拟实际提交格式）
    if all_interval_data:
        print(f"\n{'='*80}")
        print(f"模拟实际提交格式（合并所有时间周期数据）")
        print(f"{'='*80}\n")
        
        # 构建合并数据格式（模拟实际提交给模型的数据结构）
        merged_data = {
            'symbol': symbol,
            'timeframes': all_interval_data
        }
        
        merged_tokens, merged_char_count, _ = estimate_tokens(merged_data)
        
        print(f"合并后数据统计:")
        print(f"  字符数: {merged_char_count:,}")
        print(f"  估算Token数: {merged_tokens:,}")
        print(f"\n注意: 实际提交时可能还需要额外的prompt文本，实际token消耗可能更高")
        print(f"{'='*80}\n")

if __name__ == "__main__":
    test_market_data_methods()