import sys
import os
import json

# 添加项目根目录到Python路径（tests现在在trade/tests下）
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from trade.market.market_data import MarketDataFetcher
from trade.common.database.database_basic import Database

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    print("警告: tiktoken 库未安装，将使用简单估算方法")
    print("安装命令: pip install tiktoken")

def estimate_tokens(data, model="gpt-4"):
    """
    使用 tiktoken 库精确计算 JSON 数据的 token 数量
    
    Args:
        data: 要计算的数据（字典、列表等）
        model: 模型名称，默认为 "gpt-4"，可选值：
               - "gpt-4", "gpt-4-turbo-preview" (使用 cl100k_base 编码)
               - "gpt-3.5-turbo" (使用 cl100k_base 编码)
               - "gpt-4o" (使用 o200k_base 编码)
    
    Returns:
        tuple: (token_count, char_count, json_str)
    """
    json_str = json.dumps(data, ensure_ascii=False, default=str)
    char_count = len(json_str)
    
    if TIKTOKEN_AVAILABLE:
        try:
            # 根据模型选择编码器
            # GPT-4 和 GPT-3.5-turbo 使用 cl100k_base
            # GPT-4o 使用 o200k_base
            if "gpt-4o" in model.lower():
                encoding = tiktoken.get_encoding("o200k_base")
            else:
                # 默认使用 cl100k_base (GPT-4, GPT-3.5-turbo)
                encoding = tiktoken.get_encoding("cl100k_base")
            
            # 计算 token 数量
            token_count = len(encoding.encode(json_str))
            return token_count, char_count, json_str
        except Exception as e:
            print(f"警告: tiktoken 计算失败 ({e})，使用简单估算")
            # 降级到简单估算
            estimated_tokens = int(char_count / 3.5)
            return estimated_tokens, char_count, json_str
    else:
        # 如果没有 tiktoken，使用简单估算
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
    
    # 选择要使用的模型（用于 token 计算）
    # 可选: "gpt-4", "gpt-4-turbo-preview", "gpt-3.5-turbo", "gpt-4o"
    model_name = "gpt-4"  # 默认使用 GPT-4 的编码器
    print(f"使用模型编码器: {model_name}")
    if not TIKTOKEN_AVAILABLE:
        print("⚠️  注意: 未安装 tiktoken，将使用简单估算方法")
        print("   建议安装: pip install tiktoken\n")
    
    # 测试 7 个时间周期的方法（不含周线 1w）
    methods = [
        ("1m", market_data.get_market_data_1m),
        ("5m", market_data.get_market_data_5m),
        ("15m", market_data.get_market_data_15m),
        ("30m", market_data.get_market_data_30m),
        ("1h", market_data.get_market_data_1h),
        ("4h", market_data.get_market_data_4h),
        ("1d", market_data.get_market_data_1d),
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
                
                # 计算token数量（使用指定模型的编码器）
                tokens, char_count, json_str = estimate_tokens(data, model=model_name)
                
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
                print(f"  Token数 ({model_name}): {tokens:,}")
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
    
    for interval in ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]:
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
    print(f"📊 {symbol} 一次提交7个时间周期指标数据需要的Token数量 ({model_name}): {total_tokens:,}")
    print(f"   总字符数: {total_char_count:,}")
    print(f"   总K线数量: {total_kline_count:,}")
    if TIKTOKEN_AVAILABLE:
        print(f"   ✅ 使用 tiktoken 精确计算")
    else:
        print(f"   ⚠️  使用简单估算（建议安装 tiktoken: pip install tiktoken）")
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
        
        merged_tokens, merged_char_count, _ = estimate_tokens(merged_data, model=model_name)
        
        print(f"合并后数据统计:")
        print(f"  字符数: {merged_char_count:,}")
        print(f"  Token数 ({model_name}): {merged_tokens:,}")
        print(f"\n注意:")
        print(f"  - 实际提交时可能还需要额外的prompt文本，实际token消耗可能更高")
        print(f"  - 不同模型的token计算可能略有差异")
        print(f"  - 当前使用 {model_name} 的编码器计算")
        print(f"{'='*80}\n")

if __name__ == "__main__":
    test_market_data_methods()