"""
测试SDK的kline_candlestick_data方法是否支持startTime和endTime参数
"""
import os
import sys
import logging
from datetime import datetime, timezone

# 添加项目根目录到路径（tests现在在trade/tests下）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

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
    """测试不带时间参数的K线数据获取，验证limit=500是否返回500条数据"""
    logger.info("=" * 60)
    logger.info("测试1: 不带startTime和endTime参数（limit=500）")
    logger.info("=" * 60)
    try:
        response = client.rest_api.kline_candlestick_data(
            symbol="BTCUSDT",
            interval=KlineCandlestickDataIntervalEnum["INTERVAL_5m"].value,
            limit=500
        )
        data = response.data()
        count = len(data)
        logger.info(f"✅ 成功获取 {count} 条K线数据")
        
        if data:
            # 解析第一条和最后一条K线的时间戳
            first_kline = data[0]
            last_kline = data[-1]
            
            # 如果是列表格式，第一个元素是时间戳（毫秒）
            if isinstance(first_kline, (list, tuple)) and len(first_kline) > 0:
                first_timestamp = first_kline[0]
                last_timestamp = last_kline[0]
            else:
                # 如果是字典格式
                first_timestamp = first_kline.get('open_time', first_kline.get('t', 0))
                last_timestamp = last_kline.get('open_time', last_kline.get('t', 0))
            
            # 转换为datetime格式
            first_datetime = datetime.fromtimestamp(first_timestamp / 1000, tz=timezone.utc) if first_timestamp else None
            last_datetime = datetime.fromtimestamp(last_timestamp / 1000, tz=timezone.utc) if last_timestamp else None
            
            logger.info(f"第一条K线时间戳: {first_timestamp} -> {first_datetime.strftime('%Y-%m-%d %H:%M:%S UTC') if first_datetime else 'N/A'}")
            logger.info(f"最后一条K线时间戳: {last_timestamp} -> {last_datetime.strftime('%Y-%m-%d %H:%M:%S UTC') if last_datetime else 'N/A'}")
            
            # 验证数据条数
            if count == 500:
                logger.info(f"✅ 成功获取到500条数据（符合预期）")
            else:
                logger.warning(f"⚠️  获取到{count}条数据，不是500条（limit=500）")
            
            # 验证时间差（5分钟周期，500条应该是500*5=2500分钟≈41.67小时）
            if first_timestamp and last_timestamp:
                time_diff_ms = last_timestamp - first_timestamp
                time_diff_minutes = time_diff_ms / 1000 / 60
                expected_minutes = 500 * 5  # 500条 * 5分钟/条 = 2500分钟
                logger.info(f"时间差: {time_diff_minutes:.1f} 分钟 ({time_diff_minutes/60:.2f} 小时)")
                logger.info(f"预期时间差: {expected_minutes} 分钟 ({expected_minutes/60:.2f} 小时)")
                if abs(time_diff_minutes - expected_minutes) <= 5:  # 允许5分钟误差
                    logger.info(f"✅ 时间差验证通过（符合预期：500条 * 5分钟 = 2500分钟）")
                else:
                    logger.warning(f"⚠️  时间差不符合预期：实际{time_diff_minutes:.1f}分钟，预期{expected_minutes}分钟")
        
        return True
    except Exception as e:
        logger.error(f"❌ 失败: {e}")
        return False


def test_kline_with_endtime_only_short_intervals():
    """测试只带end_time参数（不传start_time）查询1m、5m、15m的K线数据，验证limit=500是否返回500条数据"""
    logger.info("=" * 60)
    logger.info("测试2: 只带end_time参数查询1m、5m、15m K线数据（limit=500）")
    logger.info("=" * 60)
    
    intervals = [
        ("INTERVAL_1m", "1分钟", 1),   # interval名称, 显示名称, 分钟数
        ("INTERVAL_5m", "5分钟", 5),
        ("INTERVAL_15m", "15分钟", 15)
    ]
    
    # end_time使用当前时间
    end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    end_time_dt = datetime.fromtimestamp(end_time / 1000, tz=timezone.utc)
    logger.info(f"end_time: {end_time} -> {end_time_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info(f"limit: 500")
    logger.info("")
    
    results = {}
    
    for interval_enum_key, interval_name, minutes_per_kline in intervals:
        try:
            logger.info(f"--- 测试 {interval_name} ({interval_enum_key}) ---")
            
            response = client.rest_api.kline_candlestick_data(
                symbol="BTCUSDT",
                interval=KlineCandlestickDataIntervalEnum[interval_enum_key].value,
                limit=500,
                start_time=None,  # 不传入start_time
                end_time=end_time  # 只传入end_time
            )
            data = response.data()
            count = len(data)
            results[interval_name] = count
            
            logger.info(f"✅ {interval_name}: 成功获取 {count} 条K线数据")
            if data:
                # 解析第一条和最后一条K线的时间戳
                first_kline = data[0]
                last_kline = data[-1]
                
                # 如果是列表格式，第一个元素是时间戳（毫秒）
                if isinstance(first_kline, (list, tuple)) and len(first_kline) > 0:
                    first_timestamp = first_kline[0]
                    last_timestamp = last_kline[0]
                else:
                    # 如果是字典格式
                    first_timestamp = first_kline.get('open_time', first_kline.get('t', 0))
                    last_timestamp = last_kline.get('open_time', last_kline.get('t', 0))
                
                # 转换为datetime格式
                first_datetime = datetime.fromtimestamp(first_timestamp / 1000, tz=timezone.utc) if first_timestamp else None
                last_datetime = datetime.fromtimestamp(last_timestamp / 1000, tz=timezone.utc) if last_timestamp else None
                
                logger.info(f"   第一条K线时间戳: {first_timestamp} -> {first_datetime.strftime('%Y-%m-%d %H:%M:%S UTC') if first_datetime else 'N/A'}")
                logger.info(f"   最后一条K线时间戳: {last_timestamp} -> {last_datetime.strftime('%Y-%m-%d %H:%M:%S UTC') if last_datetime else 'N/A'}")
                
                # 验证数据条数
                if count == 500:
                    logger.info(f"   ✅ 成功获取到500条数据（符合预期）")
                else:
                    logger.warning(f"   ⚠️  获取到{count}条数据，不是500条（limit=500）")
            
            # 验证时间差
            if first_timestamp and last_timestamp:
                time_diff_ms = last_timestamp - first_timestamp
                time_diff_minutes = time_diff_ms / 1000 / 60
                expected_minutes = 500 * minutes_per_kline  # 500条 * 每条的分钟数
                expected_hours = expected_minutes / 60
                
                logger.info(f"   时间差: {time_diff_minutes:.1f} 分钟 ({time_diff_minutes/60:.2f} 小时)")
                logger.info(f"   预期时间差: {expected_minutes} 分钟 ({expected_hours:.2f} 小时)")
                
                # 允许一定误差（考虑到K线可能不完全连续）
                tolerance_minutes = minutes_per_kline  # 允许1个K线周期的误差
                if abs(time_diff_minutes - expected_minutes) <= tolerance_minutes:
                    logger.info(f"   ✅ 时间差验证通过（符合预期：500条 * {minutes_per_kline}分钟 = {expected_minutes}分钟）")
                else:
                    logger.warning(f"   ⚠️  时间差不符合预期：实际{time_diff_minutes:.1f}分钟，预期{expected_minutes}分钟（误差{abs(time_diff_minutes - expected_minutes):.1f}分钟）")
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
    """测试只带end_time参数（不传start_time）查询1天K线数据，验证limit=500是否返回500条数据"""
    logger.info("=" * 60)
    logger.info("测试3: 只带end_time参数查询1天K线数据（limit=500）")
    logger.info("=" * 60)
    try:
        # end_time使用当前时间（或可以设置为过去某个时间点）
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        end_time_dt = datetime.fromtimestamp(end_time / 1000, tz=timezone.utc)
        logger.info(f"end_time: {end_time} -> {end_time_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        logger.info(f"interval: 1d (1天)")
        logger.info(f"limit: 500")
        
        response = client.rest_api.kline_candlestick_data(
            symbol="BTCUSDT",
            interval=KlineCandlestickDataIntervalEnum["INTERVAL_1d"].value,
            limit=500,
            start_time=None,  # 不传入start_time
            end_time=end_time  # 只传入end_time
        )
        data = response.data()
        count = len(data)
        logger.info(f"✅ 成功获取 {count} 条K线数据（1天周期，只带end_time）")
        
        if data:
            # 解析第一条和最后一条K线的时间戳
            first_kline = data[0]
            last_kline = data[-1]
            
            # 如果是列表格式，第一个元素是时间戳（毫秒）
            if isinstance(first_kline, (list, tuple)) and len(first_kline) > 0:
                first_timestamp = first_kline[0]
                last_timestamp = last_kline[0]
            else:
                # 如果是字典格式
                first_timestamp = first_kline.get('open_time', first_kline.get('t', 0))
                last_timestamp = last_kline.get('open_time', last_kline.get('t', 0))
            
            # 转换为datetime格式
            first_datetime = datetime.fromtimestamp(first_timestamp / 1000, tz=timezone.utc) if first_timestamp else None
            last_datetime = datetime.fromtimestamp(last_timestamp / 1000, tz=timezone.utc) if last_timestamp else None
            
            logger.info(f"第一条K线时间戳: {first_timestamp} -> {first_datetime.strftime('%Y-%m-%d %H:%M:%S UTC') if first_datetime else 'N/A'}")
            logger.info(f"最后一条K线时间戳: {last_timestamp} -> {last_datetime.strftime('%Y-%m-%d %H:%M:%S UTC') if last_datetime else 'N/A'}")
            
            # 验证数据条数
            if count == 500:
                logger.info(f"✅ 成功获取到500条数据（符合预期）")
            else:
                logger.warning(f"⚠️  获取到{count}条数据，不是500条（可能数据不足，500天=约16.7个月历史数据）")
            
            # 验证时间差（1天周期，500条应该是500天）
            if first_timestamp and last_timestamp:
                time_diff_ms = last_timestamp - first_timestamp
                time_diff_days = time_diff_ms / 1000 / 60 / 60 / 24
                expected_days = 500  # 500条 * 1天/条 = 500天
                logger.info(f"时间差: {time_diff_days:.1f} 天 ({time_diff_days/30:.2f} 个月)")
                logger.info(f"预期时间差: {expected_days} 天 ({expected_days/30:.2f} 个月)")
                if abs(time_diff_days - expected_days) <= 1:  # 允许1天误差
                    logger.info(f"✅ 时间差验证通过（符合预期：500条 * 1天 = 500天）")
                else:
                    logger.warning(f"⚠️  时间差不符合预期：实际{time_diff_days:.1f}天，预期{expected_days}天")
        
        return True
    except TypeError as e:
        logger.warning(f"⚠️  TypeError: SDK方法不支持end_time参数 - {e}")
        return False
    except Exception as e:
        logger.error(f"❌ 失败: {e}")
        return False


def test_kline_with_endtime_only_1w():
    """测试只带end_time参数（不传start_time）查询1周K线数据，验证limit=500是否返回500条数据"""
    logger.info("=" * 60)
    logger.info("测试4: 只带end_time参数查询1周K线数据（limit=500）")
    logger.info("=" * 60)
    try:
        # end_time使用当前时间（或可以设置为过去某个时间点）
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        end_time_dt = datetime.fromtimestamp(end_time / 1000, tz=timezone.utc)
        logger.info(f"end_time: {end_time} -> {end_time_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        logger.info(f"interval: 1w (1周)")
        logger.info(f"limit: 500")
        
        response = client.rest_api.kline_candlestick_data(
            symbol="BTCUSDT",
            interval=KlineCandlestickDataIntervalEnum["INTERVAL_1w"].value,
            limit=500,
            start_time=None,  # 不传入start_time
            end_time=end_time  # 只传入end_time
        )
        data = response.data()
        count = len(data)
        logger.info(f"✅ 成功获取 {count} 条K线数据（1周周期，只带end_time）")
        
        if data:
            # 解析第一条和最后一条K线的时间戳
            first_kline = data[0]
            last_kline = data[-1]
            
            # 如果是列表格式，第一个元素是时间戳（毫秒）
            if isinstance(first_kline, (list, tuple)) and len(first_kline) > 0:
                first_timestamp = first_kline[0]
                last_timestamp = last_kline[0]
            else:
                # 如果是字典格式
                first_timestamp = first_kline.get('open_time', first_kline.get('t', 0))
                last_timestamp = last_kline.get('open_time', last_kline.get('t', 0))
            
            # 转换为datetime格式
            first_datetime = datetime.fromtimestamp(first_timestamp / 1000, tz=timezone.utc) if first_timestamp else None
            last_datetime = datetime.fromtimestamp(last_timestamp / 1000, tz=timezone.utc) if last_timestamp else None
            
            logger.info(f"第一条K线时间戳: {first_timestamp} -> {first_datetime.strftime('%Y-%m-%d %H:%M:%S UTC') if first_datetime else 'N/A'}")
            logger.info(f"最后一条K线时间戳: {last_timestamp} -> {last_datetime.strftime('%Y-%m-%d %H:%M:%S UTC') if last_datetime else 'N/A'}")
            
            # 验证数据条数
            if count == 500:
                logger.info(f"✅ 成功获取到500条数据（符合预期）")
            else:
                logger.warning(f"⚠️  获取到{count}条数据，不是500条（可能数据不足，500周=约9.6年历史数据）")
            
            # 验证时间差（1周周期，500条应该是500周）
            if first_timestamp and last_timestamp:
                time_diff_ms = last_timestamp - first_timestamp
                time_diff_weeks = time_diff_ms / 1000 / 60 / 60 / 24 / 7
                expected_weeks = 500  # 500条 * 1周/条 = 500周
                logger.info(f"时间差: {time_diff_weeks:.1f} 周 ({time_diff_weeks/52:.2f} 年)")
                logger.info(f"预期时间差: {expected_weeks} 周 ({expected_weeks/52:.2f} 年)")
                if abs(time_diff_weeks - expected_weeks) <= 1:  # 允许1周误差
                    logger.info(f"✅ 时间差验证通过（符合预期：500条 * 1周 = 500周）")
                else:
                    logger.warning(f"⚠️  时间差不符合预期：实际{time_diff_weeks:.1f}周，预期{expected_weeks}周")
        
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

