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
            limit=10
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


def test_kline_with_starttime():
    """测试带start_time参数的K线数据获取"""
    logger.info("=" * 60)
    logger.info("测试2: 带start_time参数")
    logger.info("=" * 60)
    try:
        # 计算24小时前的时间戳（毫秒）
        start_time = int((datetime.now(timezone.utc).timestamp() - 24 * 3600) * 1000)
        logger.info(f"start_time: {start_time} ({datetime.fromtimestamp(start_time/1000, tz=timezone.utc)})")
        
        response = client.rest_api.kline_candlestick_data(
            symbol="BTCUSDT",
            interval=KlineCandlestickDataIntervalEnum["INTERVAL_5m"].value,
            limit=10,
            start_time=start_time  # 使用小写下划线格式
        )
        data = response.data()
        logger.info(f"✅ 成功获取 {len(data)} 条K线数据（带start_time）")
        if data:
            logger.info(f"第一条K线时间: {data[0]}")
            logger.info(f"最后一条K线时间: {data[-1]}")
        return True
    except TypeError as e:
        logger.warning(f"⚠️  TypeError: SDK方法不支持start_time参数 - {e}")
        return False
    except Exception as e:
        logger.error(f"❌ 失败: {e}")
        return False


def test_kline_with_starttime_endtime():
    """测试带start_time和end_time参数的K线数据获取"""
    logger.info("=" * 60)
    logger.info("测试3: 带start_time和end_time参数")
    logger.info("=" * 60)
    try:
        # 计算24小时前和12小时前的时间戳（毫秒）
        end_time = int((datetime.now(timezone.utc).timestamp() - 12 * 3600) * 1000)
        start_time = int((datetime.now(timezone.utc).timestamp() - 24 * 3600) * 1000)
        logger.info(f"start_time: {start_time} ({datetime.fromtimestamp(start_time/1000, tz=timezone.utc)})")
        logger.info(f"end_time: {end_time} ({datetime.fromtimestamp(end_time/1000, tz=timezone.utc)})")
        
        response = client.rest_api.kline_candlestick_data(
            symbol="BTCUSDT",
            interval=KlineCandlestickDataIntervalEnum["INTERVAL_5m"].value,
            limit=10,
            start_time=start_time,  # 使用小写下划线格式
            end_time=end_time      # 使用小写下划线格式
        )
        data = response.data()
        logger.info(f"✅ 成功获取 {len(data)} 条K线数据（带start_time和end_time）")
        if data:
            logger.info(f"第一条K线时间: {data[0]}")
            logger.info(f"最后一条K线时间: {data[-1]}")
        return True
    except TypeError as e:
        logger.warning(f"⚠️  TypeError: SDK方法不支持start_time/end_time参数 - {e}")
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
    
    # 测试2: 带startTime参数
    test_kline_with_starttime()
    logger.info("")
    
    # 测试3: 带startTime和endTime参数
    test_kline_with_starttime_endtime()
    logger.info("")
    
    logger.info("=" * 60)
    logger.info("测试完成")
    logger.info("=" * 60)

