"""
测试SDK的kline_candlestick_data方法是否支持startTime和endTime参数
"""
import os
import sys
import logging
from datetime import datetime, timezone

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import (
    DerivativesTradingUsdsFutures,
    ConfigurationRestAPI,
    DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL,
)
from binance_sdk_derivatives_trading_usds_futures.rest_api.models import (
    KlineCandlestickDataIntervalEnum,
)

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 创建配置
configuration_rest_api = ConfigurationRestAPI(
    api_key=os.getenv("BINANCE_API_KEY", ""),
    api_secret=os.getenv("BINANCE_API_SECRET", ""),
    base_path=os.getenv(
        "BASE_PATH", DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL
    ),
)

# 初始化客户端
client = DerivativesTradingUsdsFutures(config_rest_api=configuration_rest_api)


def test_kline_without_time_params():
    """测试不带时间参数的K线数据获取"""
    logger.info("=" * 60)
    logger.info("测试1: 不带startTime和endTime参数")
    logger.info("=" * 60)
    try:
        response = client.rest_api.kline_candlestick_data(
            symbol="BTCUSDT",
            interval=KlineCandlestickDataIntervalEnum["INTERVAL_5m"].value,
            limit=300
        )
        data = response.data()
        logger.info(f"✅ 成功获取 {len(data)} 条K线数据")
        if data:
            logger.info(f"第一条K线时间: {data[0]}")
            logger.info(f"最后一条K线时间: {data[-1]}")
        return True
    except Exception as e:
        logger.error(f"❌ 失败: {e}")
        return False


def test_kline_with_endtime_only_short_intervals():
    """测试只带end_time参数（不传start_time）查询1m、5m、15m的K线数据，默认120条"""
    logger.info("=" * 60)
    logger.info("测试4: 只带end_time参数查询1m、5m、15m K线数据（limit=120）")
    logger.info("=" * 60)
    
    intervals = [
        ("INTERVAL_1m", "1分钟"),
        ("INTERVAL_5m", "5分钟"),
        ("INTERVAL_15m", "15分钟")
    ]
    
    # end_time使用当前时间
    end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    logger.info(f"end_time: {end_time} ({datetime.fromtimestamp(end_time/1000, tz=timezone.utc)})")
    logger.info(f"limit: 120")
    logger.info("")
    
    results = {}
    
    for interval_enum_key, interval_name in intervals:
        try:
            logger.info(f"--- 测试 {interval_name} ({interval_enum_key}) ---")
            
            response = client.rest_api.kline_candlestick_data(
                symbol="BTCUSDT",
                interval=KlineCandlestickDataIntervalEnum[interval_enum_key].value,
                limit=300,
                start_time=None,  # 不传入start_time
                end_time=end_time  # 只传入end_time
            )
            data = response.data()
            count = len(data)
            results[interval_name] = count
            
            logger.info(f"✅ {interval_name}: 成功获取 {count} 条K线数据")
            if data:
                # 解析第一条和最后一条K线的时间戳
                first_kline = data[0] if isinstance(data[0], (list, tuple)) else data[0]
                last_kline = data[-1] if isinstance(data[-1], (list, tuple)) else data[-1]
                
                # 如果是列表格式，第一个元素是时间戳
                first_timestamp = first_kline[0] if isinstance(first_kline, (list, tuple)) else first_kline.get('open_time', first_kline.get('t', 'N/A'))
                last_timestamp = last_kline[0] if isinstance(last_kline, (list, tuple)) else last_kline.get('open_time', last_kline.get('t', 'N/A'))
                
                logger.info(f"   第一条K线时间戳: {first_timestamp}")
                logger.info(f"   最后一条K线时间戳: {last_timestamp}")
                
                # 检查是否获取到120条
                if count == 120:
                    logger.info(f"   ✅ 成功获取到120条数据（符合预期）")
                else:
                    logger.warning(f"   ⚠️  获取到{count}条数据，不是120条")
            logger.info("")
            
        except TypeError as e:
            logger.warning(f"⚠️  {interval_name}: TypeError - SDK方法不支持end_time参数 - {e}")
            results[interval_name] = f"Error: {e}"
            logger.info("")
        except Exception as e:
            logger.error(f"❌ {interval_name}: 失败 - {e}")
            results[interval_name] = f"Error: {e}"
            logger.info("")
    
    # 汇总结果
    logger.info("=" * 60)
    logger.info("测试结果汇总:")
    logger.info("=" * 60)
    for interval_name, count in results.items():
        logger.info(f"  {interval_name}: {count} 条K线数据")
    logger.info("=" * 60)
    
    return True


def test_kline_with_endtime_only_1d():
    """测试只带end_time参数（不传start_time）查询1天K线数据，默认120条"""
    logger.info("=" * 60)
    logger.info("测试5: 只带end_time参数查询1天K线数据（limit=120）")
    logger.info("=" * 60)
    try:
        # end_time使用当前时间（或可以设置为过去某个时间点）
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        logger.info(f"end_time: {end_time} ({datetime.fromtimestamp(end_time/1000, tz=timezone.utc)})")
        logger.info(f"interval: 1d (1天)")
        logger.info(f"limit: 120")
        
        response = client.rest_api.kline_candlestick_data(
            symbol="BTCUSDT",
            interval=KlineCandlestickDataIntervalEnum["INTERVAL_1d"].value,
            limit=120,
            start_time=None,  # 不传入start_time
            end_time=end_time  # 只传入end_time
        )
        data = response.data()
        logger.info(f"✅ 成功获取 {len(data)} 条K线数据（1天周期，只带end_time）")
        if data:
            logger.info(f"第一条K线时间: {data[0]}")
            logger.info(f"最后一条K线时间: {data[-1]}")
            # 检查是否获取到120条
            if len(data) == 120:
                logger.info(f"✅ 成功获取到120条数据（符合预期）")
            else:
                logger.warning(f"⚠️  获取到{len(data)}条数据，不是120条（可能数据不足）")
        return True
    except TypeError as e:
        logger.warning(f"⚠️  TypeError: SDK方法不支持end_time参数 - {e}")
        return False
    except Exception as e:
        logger.error(f"❌ 失败: {e}")
        return False


def test_kline_with_endtime_only_1w():
    """测试只带end_time参数（不传start_time）查询1周K线数据，默认120条"""
    logger.info("=" * 60)
    logger.info("测试5: 只带end_time参数查询1周K线数据（limit=120）")
    logger.info("=" * 60)
    try:
        # end_time使用当前时间（或可以设置为过去某个时间点）
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        logger.info(f"end_time: {end_time} ({datetime.fromtimestamp(end_time/1000, tz=timezone.utc)})")
        logger.info(f"interval: 1w (1周)")
        logger.info(f"limit: 120")
        
        response = client.rest_api.kline_candlestick_data(
            symbol="BTCUSDT",
            interval=KlineCandlestickDataIntervalEnum["INTERVAL_1w"].value,
            limit=300,
            start_time=None,  # 不传入start_time
            end_time=end_time  # 只传入end_time
        )
        data = response.data()
        logger.info(f"✅ 成功获取 {len(data)} 条K线数据（1周周期，只带end_time）")
        if data:
            logger.info(f"第一条K线时间: {data[0]}")
            logger.info(f"最后一条K线时间: {data[-1]}")
            # 检查是否获取到120条
            if len(data) == 120:
                logger.info(f"✅ 成功获取到120条数据（符合预期）")
            else:
                logger.warning(f"⚠️  获取到{len(data)}条数据，不是120条（可能数据不足，120周=约2.3年历史数据）")
        return True
    except TypeError as e:
        logger.warning(f"⚠️  TypeError: SDK方法不支持end_time参数 - {e}")
        return False
    except Exception as e:
        logger.error(f"❌ 失败: {e}")
        return False


def inspect_method_signature():
    """检查方法签名"""
    logger.info("=" * 60)
    logger.info("检查kline_candlestick_data方法签名")
    logger.info("=" * 60)
    try:
        import inspect
        sig = inspect.signature(client.rest_api.kline_candlestick_data)
        logger.info(f"方法参数: {list(sig.parameters.keys())}")
        for param_name, param in sig.parameters.items():
            logger.info(f"  {param_name}: {param.annotation if param.annotation != inspect.Parameter.empty else 'Any'} = {param.default if param.default != inspect.Parameter.empty else '无默认值'}")
        return True
    except Exception as e:
        logger.error(f"❌ 检查方法签名失败: {e}")
        return False


if __name__ == "__main__":
    logger.info("开始测试SDK的kline_candlestick_data方法是否支持start_time和end_time参数")
    logger.info("")
    
    # 检查方法签名
    inspect_method_signature()
    logger.info("")
    
    # 测试1: 不带时间参数
    test_kline_without_time_params()
    logger.info("")
    
    # 测试4: 只带endTime参数查询1m、5m、15m K线数据（limit=120）
    test_kline_with_endtime_only_short_intervals()
    logger.info("")
    
    # 测试5: 只带endTime参数查询1天K线数据（limit=120）
    test_kline_with_endtime_only_1d()
    logger.info("")
    
    # 测试6: 只带endTime参数查询1周K线数据（limit=120）
    test_kline_with_endtime_only_1w()
    logger.info("")
    
    logger.info("=" * 60)
    logger.info("测试完成")
    logger.info("=" * 60)

