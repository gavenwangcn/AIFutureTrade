import sys
import os
import json

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market.market_data import MarketDataFetcher
from common.database_basic import Database

def test_market_data_format():
    """测试市场数据格式是否符合要求"""
    # 初始化数据库和市场数据获取器
    db = Database(auto_init=True)
    market_data = MarketDataFetcher(db)
    
    # 测试的交易对和时间周期
    symbol = "BTC"
    intervals = ["1m", "5m", "15m", "1h", "4h", "1d", "1w"]
    
    for interval in intervals:
        print(f"\n===== 测试 {interval} 时间周期 ====")
        
        # 获取市场数据
        try:
            if interval == "1m":
                data = market_data.get_market_data_1m(symbol)
            elif interval == "5m":
                data = market_data.get_market_data_5m(symbol)
            elif interval == "15m":
                data = market_data.get_market_data_15m(symbol)
            elif interval == "1h":
                data = market_data.get_market_data_1h(symbol)
            elif interval == "4h":
                data = market_data.get_market_data_4h(symbol)
            elif interval == "1d":
                data = market_data.get_market_data_1d(symbol)
            elif interval == "1w":
                data = market_data.get_market_data_1w(symbol)
            
            if not data:
                print(f"获取 {interval} 数据失败")
                continue
            
            # 验证数据格式
            assert "symbol" in data, "缺少 symbol 字段"
            assert "timeframe" in data, "缺少 timeframe 字段"
            assert "klines" in data, "缺少 klines 字段"
            assert "indicators" in data, "缺少 indicators 字段"
            assert "metadata" in data, "缺少 metadata 字段"
            
            # 验证时间周期
            assert data["timeframe"] == interval, f"时间周期不匹配，预期 {interval}，实际 {data['timeframe']}"
            
            # 验证 K 线数据
            assert isinstance(data["klines"], list), "klines 应该是列表"
            for kline in data["klines"]:
                assert "time" in kline, "K 线缺少 time 字段"
                assert "open" in kline, "K 线缺少 open 字段"
                assert "high" in kline, "K 线缺少 high 字段"
                assert "low" in kline, "K 线缺少 low 字段"
                assert "close" in kline, "K 线缺少 close 字段"
                assert "volume" in kline, "K 线缺少 volume 字段"
            
            # 验证指标数据
            assert "MA" in data["indicators"], "缺少 MA 指标"
            assert "MACD" in data["indicators"], "缺少 MACD 指标"
            assert "RSI" in data["indicators"], "缺少 RSI 指标"
            assert "VOL" in data["indicators"], "缺少 VOL 指标"
            
            # 验证 MA 指标
            ma_indicators = data["indicators"]["MA"]
            assert "MA5" in ma_indicators, "缺少 MA5 指标"
            assert "MA20" in ma_indicators, "缺少 MA20 指标"
            assert "MA50" in ma_indicators, "缺少 MA50 指标"
            assert "MA99" in ma_indicators, "缺少 MA99 指标"
            
            # 验证 MACD 指标
            macd_indicators = data["indicators"]["MACD"]
            assert "DIF" in macd_indicators, "缺少 MACD DIF 指标"
            assert "DEA" in macd_indicators, "缺少 MACD DEA 指标"
            assert "BAR" in macd_indicators, "缺少 MACD BAR 指标"
            
            # 验证 RSI 指标
            rsi_indicators = data["indicators"]["RSI"]
            assert "RSI6" in rsi_indicators, "缺少 RSI6 指标"
            assert "RSI9" in rsi_indicators, "缺少 RSI9 指标"
            
            # 验证 VOL 指标
            vol_indicators = data["indicators"]["VOL"]
            assert "volume" in vol_indicators, "缺少 volume 指标"
            assert "MAVOL5" in vol_indicators, "缺少 MAVOL5 指标"
            assert "MAVOL10" in vol_indicators, "缺少 MAVOL10 指标"
            
            # 验证指标数据长度与 K 线数据长度一致
            kline_count = len(data["klines"])
            assert len(ma_indicators["MA5"]) == kline_count, "MA5 指标长度与 K 线不一致"
            assert len(macd_indicators["DIF"]) == kline_count, "MACD DIF 指标长度与 K 线不一致"
            assert len(rsi_indicators["RSI6"]) == kline_count, "RSI6 指标长度与 K 线不一致"
            assert len(vol_indicators["volume"]) == kline_count, "volume 指标长度与 K 线不一致"
            
            # 验证 metadata
            assert "last_update" in data["metadata"], "缺少 last_update 字段"
            assert "total_bars" in data["metadata"], "缺少 total_bars 字段"
            assert "indicators_calculated" in data["metadata"], "缺少 indicators_calculated 字段"
            assert data["metadata"]["total_bars"] == kline_count, "total_bars 与 K 线数量不一致"
            
            # 打印数据摘要
            print(f"✓ 数据格式验证通过")
            print(f"✓ 交易对: {data['symbol']}")
            print(f"✓ 时间周期: {data['timeframe']}")
            print(f"✓ K 线数量: {len(data['klines'])}")
            print(f"✓ 最新更新时间: {data['metadata']['last_update']}")
            
            # 保存数据到文件（可选）
            # with open(f"market_data_{interval}.json", "w") as f:
            #     json.dump(data, f, indent=2, ensure_ascii=False)
            # print(f"✓ 数据已保存到 market_data_{interval}.json")
            
        except Exception as e:
            print(f"✗ 测试失败: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_market_data_format()
