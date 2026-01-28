"""测试查询合约手续费接口

Usage:
    export BINANCE_API_KEY=...
    export BINANCE_API_SECRET=...
    python trade/tests/test_user_commission_rate.py
    或
    python -m trade.tests.test_user_commission_rate

该脚本测试币安期货合约的手续费查询接口，用于查看SDK接口状态和返回的详细信息。
"""

import logging
import os
import sys
from pathlib import Path
import json

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 导入币安SDK
from binance_common.configuration import ConfigurationRestAPI
from binance_common.constants import (
    DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL,
)
from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import (
    DerivativesTradingUsdsFutures,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


def _load_credentials() -> tuple[str, str]:
    """
    从环境变量或配置文件加载API凭证

    Returns:
        (api_key, api_secret) 元组
    """
    # 优先从环境变量读取
    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")

    # 如果环境变量未设置，尝试从配置文件读取
    if not api_key or not api_secret:
        try:
            import trade.common.config as config
            api_key = "LBtjhBgX1RCksNJDdOoJPeDD30Z70YIGHHH9DrqjIDDkK7xcPRQcgydPxGRr6MN1"
            api_secret = "55arJnwlytDflHv151UpHN1s32ACnJZEs86mbc79wGyeuSUJNHTDPN7jEgBbqO6I"
        except ImportError:
            pass

    if not api_key or not api_secret:
        raise RuntimeError(
            "请在环境变量中配置 BINANCE_API_KEY 和 BINANCE_API_SECRET，"
            "或在 trade/common/config.py 中配置这些参数"
        )

    return api_key, api_secret


def test_user_commission_rate(api_key: str, api_secret: str, symbol: str = "BTCUSDT") -> None:
    """
    测试查询用户手续费率接口

    Args:
        api_key: Binance API密钥
        api_secret: Binance API密钥
        symbol: 交易对符号，默认为BTCUSDT
    """
    logger.info("=" * 80)
    logger.info("开始测试用户手续费率查询接口")
    logger.info("=" * 80)

    try:
        # 创建SDK配置
        configuration_rest_api = ConfigurationRestAPI(
            api_key=api_key,
            api_secret=api_secret,
            base_path=DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL,
            timeout=10000,  # 10秒超时
        )

        # 初始化客户端
        client = DerivativesTradingUsdsFutures(config_rest_api=configuration_rest_api)
        logger.info(f"已创建 DerivativesTradingUsdsFutures 客户端")

        # 调用手续费率查询接口
        logger.info(f"正在查询交易对 {symbol} 的手续费率...")
        response = client.rest_api.user_commission_rate(symbol=symbol)

        # 获取速率限制信息
        rate_limits = response.rate_limits
        logger.info(f"API速率限制信息: {rate_limits}")

        # 获取响应数据
        data = response.data()
        logger.info(f"响应数据类型: {type(data)}")
        logger.info(f"响应数据: {data}")

        # 尝试将数据转换为字典格式以便更好地展示
        if hasattr(data, 'model_dump'):
            data_dict = data.model_dump()
            logger.info("=" * 80)
            logger.info("手续费率详细信息（字典格式）:")
            logger.info(json.dumps(data_dict, indent=2, ensure_ascii=False))
        elif hasattr(data, 'to_dict'):
            data_dict = data.to_dict()
            logger.info("=" * 80)
            logger.info("手续费率详细信息（字典格式）:")
            logger.info(json.dumps(data_dict, indent=2, ensure_ascii=False))
        elif isinstance(data, dict):
            logger.info("=" * 80)
            logger.info("手续费率详细信息（字典格式）:")
            logger.info(json.dumps(data, indent=2, ensure_ascii=False))

        # 打印关键字段
        logger.info("=" * 80)
        logger.info("关键字段提取:")
        if hasattr(data, 'symbol'):
            logger.info(f"  交易对: {data.symbol}")
        if hasattr(data, 'makerCommissionRate'):
            logger.info(f"  Maker手续费率: {data.makerCommissionRate}")
        if hasattr(data, 'takerCommissionRate'):
            logger.info(f"  Taker手续费率: {data.takerCommissionRate}")

        logger.info("=" * 80)
        logger.info("手续费率查询测试完成")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"查询手续费率失败: {e}", exc_info=True)
        raise


def test_multiple_symbols(api_key: str, api_secret: str) -> None:
    """
    测试查询多个交易对的手续费率

    Args:
        api_key: Binance API密钥
        api_secret: Binance API密钥
    """
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

    logger.info("=" * 80)
    logger.info(f"开始测试多个交易对的手续费率查询")
    logger.info(f"交易对列表: {symbols}")
    logger.info("=" * 80)

    try:
        # 创建SDK配置
        configuration_rest_api = ConfigurationRestAPI(
            api_key=api_key,
            api_secret=api_secret,
            base_path=DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL,
            timeout=10000,
        )

        # 初始化客户端
        client = DerivativesTradingUsdsFutures(config_rest_api=configuration_rest_api)

        # 查询每个交易对的手续费率
        for symbol in symbols:
            logger.info(f"\n查询 {symbol} 的手续费率...")
            try:
                response = client.rest_api.user_commission_rate(symbol=symbol)
                data = response.data()

                # 提取关键信息
                if hasattr(data, 'model_dump'):
                    data_dict = data.model_dump()
                elif hasattr(data, 'to_dict'):
                    data_dict = data.to_dict()
                elif isinstance(data, dict):
                    data_dict = data
                else:
                    data_dict = {}

                logger.info(f"  {symbol} 手续费率:")
                logger.info(f"    Maker: {data_dict.get('makerCommissionRate', 'N/A')}")
                logger.info(f"    Taker: {data_dict.get('takerCommissionRate', 'N/A')}")

            except Exception as e:
                logger.error(f"  查询 {symbol} 失败: {e}")

        logger.info("=" * 80)
        logger.info("多交易对手续费率查询测试完成")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"多交易对查询失败: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    # 加载API凭证
    api_key_value, api_secret_value = _load_credentials()

    # 测试单个交易对
    test_user_commission_rate(api_key_value, api_secret_value, symbol="BTCUSDT")

    # 测试多个交易对
    print("\n")
    test_multiple_symbols(api_key_value, api_secret_value)
