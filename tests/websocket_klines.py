"""
WebSocket K线数据测试

测试 Binance WebSocket SDK 的 K线数据订阅功能。
支持配置多个 interval 进行测试。

配置说明：
- TEST_SYMBOL: 测试用的symbol，默认 BTCUSDT
- TEST_INTERVALS: 测试用的interval列表，默认只测试 1m 和 5m
- 可以通过修改 TEST_INTERVALS 列表来调整测试的interval
"""
import asyncio
import os
import logging
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import (
    DerivativesTradingUsdsFutures,
    DERIVATIVES_TRADING_USDS_FUTURES_WS_STREAMS_PROD_URL,
    ConfigurationWebSocketStreams,
)

# ============================================================================
# 测试配置
# ============================================================================

# 测试用的symbol
TEST_SYMBOL = "BTCUSDT"

# 测试用的interval列表（默认只测试2个interval，便于快速验证）
# 可以通过修改此列表来调整测试的interval
# 支持的interval: '1m', '5m', '15m', '1h', '4h', '1d', '1w'
TEST_INTERVALS = [
    "1m",
    "5m"
]

# 每个interval等待消息的超时时间（秒）
MESSAGE_WAIT_TIMEOUT = 60

# 每个interval需要接收的消息数量（收到指定数量后关闭）
MESSAGES_PER_INTERVAL = 2

# ============================================================================
# 日志配置
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# ============================================================================
# 辅助函数
# ============================================================================

def print_kline_data(kline_data: Any, symbol: str, interval: str, day_label: str):
    """打印K线数据用于测试验证
    
    Args:
        kline_data: K线数据对象
        symbol: 交易对符号
        interval: 时间间隔
        day_label: 日期标签（今天/昨天/具体日期）
    """
    print(f"\n{'=' * 80}")
    print(f"=== {symbol} {interval} - {day_label} K线数据 ===")
    print(f"{'=' * 80}")
    
    # 处理SDK返回的对象，而不是字典
    if hasattr(kline_data, 'k'):
        # 这是SDK返回的对象
        k_data = kline_data.k
        print(f"开盘时间: {datetime.fromtimestamp(k_data.t / 1000).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"收盘时间: {datetime.fromtimestamp(k_data.T / 1000).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"开盘价: {k_data.o}")
        print(f"最高价: {k_data.h}")
        print(f"最低价: {k_data.l}")
        print(f"收盘价: {k_data.c}")
        print(f"成交量: {k_data.v}")
        print(f"成交笔数: {k_data.n}")
        print(f"是否完结: {k_data.x}")
    else:
        # 兼容旧版或字典格式
        print(f"开盘时间: {datetime.fromtimestamp(kline_data['k']['t'] / 1000).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"收盘时间: {datetime.fromtimestamp(kline_data['k']['T'] / 1000).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"开盘价: {kline_data['k']['o']}")
        print(f"最高价: {kline_data['k']['h']}")
        print(f"最低价: {kline_data['k']['l']}")
        print(f"收盘价: {kline_data['k']['c']}")
        print(f"成交量: {kline_data['k']['v']}")
        print(f"成交笔数: {kline_data['k']['n']}")
        print(f"是否完结: {kline_data['k']['x']}")
    
    print(f"{'=' * 80}\n")


# ============================================================================
# 主测试函数
# ============================================================================

async def test_interval(
    connection: Any,
    symbol: str,
    interval: str,
    today: datetime,
    yesterday: datetime
) -> Dict[str, Any]:
    """测试单个interval的K线数据订阅。
    
    Args:
        connection: WebSocket连接对象
        symbol: 交易对符号
        interval: 时间间隔
        today: 今天的日期
        yesterday: 昨天的日期
    
    Returns:
        包含测试结果的字典
    """
    logger.info("=" * 80)
    logger.info("[WebSocketTest] 📡 开始测试 %s %s", symbol, interval)
    logger.info("=" * 80)
    
    # 控制订阅频率，确保符合要求（每秒不超过10个订阅消息）
    logger.info("[WebSocketTest] ⏱️  订阅前等待1秒，确保不超过订阅频率限制...")
    await asyncio.sleep(1)
    
    # 订阅K线流
    logger.info("[WebSocketTest] 📡 正在订阅 %s %s 的K线流...", symbol, interval)
    stream = await connection.kline_candlestick_streams(
        symbol=symbol,
        interval=interval,
    )
    logger.info("[WebSocketTest] ✅ %s %s 订阅成功", symbol, interval)
    
    # 存储接收到的K线数据
    received_klines = []
    
    # 创建事件，用于等待数据接收完成
    data_received_event = asyncio.Event()
    
    def on_message(data: Any):
        """K线消息处理器"""
        # 只处理完结的K线数据
        is_final = False
        kline_date = None
        
        try:
            # 处理SDK返回的对象
            if hasattr(data, 'k'):
                # 这是SDK返回的对象
                is_final = data.k.x
                kline_date = datetime.fromtimestamp(data.k.t / 1000).date()
            else:
                # 兼容旧版或字典格式
                is_final = data['k']['x']
                kline_date = datetime.fromtimestamp(data['k']['t'] / 1000).date()
            
            if is_final:
                received_klines.append(data)
                
                # 判断这是今天的还是昨天的K线
                if kline_date == today.date():
                    day_label = "今天"
                elif kline_date == yesterday.date():
                    day_label = "昨天"
                else:
                    day_label = str(kline_date)
                
                # 打印K线数据
                print_kline_data(data, symbol, interval, day_label)
                
                logger.info(
                    "[WebSocketTest] ✅ [%s %s] 收到第 %s 条完结K线数据 (日期: %s)",
                    symbol, interval, len(received_klines), day_label
                )
                
                # 当收集到足够的数据后取消订阅并设置事件
                if len(received_klines) >= MESSAGES_PER_INTERVAL:
                    logger.info(
                        "[WebSocketTest] 📊 [%s %s] 已收到 %s 条消息，准备关闭订阅",
                        symbol, interval, len(received_klines)
                    )
                    asyncio.create_task(stream.unsubscribe())
                    data_received_event.set()
        except Exception as e:
            logger.error(
                "[WebSocketTest] ❌ [%s %s] 处理消息时出错: %s",
                symbol, interval, e, exc_info=True
            )
            # 打印数据的属性，便于调试
            if hasattr(data, '__dict__'):
                logger.error("[WebSocketTest] Data attributes: %s", data.__dict__)
            elif isinstance(data, dict):
                logger.error("[WebSocketTest] Data keys: %s", list(data.keys()))
    
    # 注册消息处理器
    stream.on("message", on_message)
    
    # 等待数据接收完成
    logger.info(
        "[WebSocketTest] ⏳ [%s %s] 等待接收K线数据（最多等待 %s 秒，需要 %s 条消息）...",
        symbol, interval, MESSAGE_WAIT_TIMEOUT, MESSAGES_PER_INTERVAL
    )
    
    try:
        # 等待数据接收完成，最多等待指定时间
        await asyncio.wait_for(data_received_event.wait(), timeout=MESSAGE_WAIT_TIMEOUT)
        logger.info(
            "[WebSocketTest] ✅ [%s %s] 数据接收完成，共收到 %s 条消息",
            symbol, interval, len(received_klines)
        )
    except asyncio.TimeoutError:
        logger.warning(
            "[WebSocketTest] ⚠️  [%s %s] 数据接收超时（已等待 %s 秒），当前收到 %s 条消息",
            symbol, interval, MESSAGE_WAIT_TIMEOUT, len(received_klines)
        )
    
    # 关闭该interval的订阅
    logger.info("[WebSocketTest] 🔌 [%s %s] 开始关闭订阅...", symbol, interval)
    close_start = datetime.now()
    try:
        await stream.unsubscribe()
        close_duration = (datetime.now() - close_start).total_seconds()
        logger.info(
            "[WebSocketTest] ✅ [%s %s] 订阅已关闭 (耗时: %.3fs)",
            symbol, interval, close_duration
        )
    except Exception as e:
        close_duration = (datetime.now() - close_start).total_seconds()
        logger.error(
            "[WebSocketTest] ❌ [%s %s] 关闭订阅失败 (耗时: %.3fs): %s",
            symbol, interval, close_duration, e, exc_info=True
        )
    
    logger.info("=" * 80)
    
    return {
        "symbol": symbol,
        "interval": interval,
        "received_count": len(received_klines),
        "expected_count": MESSAGES_PER_INTERVAL,
        "success": len(received_klines) >= MESSAGES_PER_INTERVAL,
        "klines": received_klines
    }


async def kline_candlestick_streams(
    symbol: Optional[str] = None,
    intervals: Optional[List[str]] = None
):
    """测试K线数据订阅功能。
    
    Args:
        symbol: 测试用的symbol，如果为None则使用默认配置 TEST_SYMBOL
        intervals: 测试用的interval列表，如果为None则使用默认配置 TEST_INTERVALS
    """
    # 使用配置参数或默认值
    test_symbol = symbol if symbol is not None else TEST_SYMBOL
    test_intervals = intervals if intervals is not None else TEST_INTERVALS
    
    connection = None
    try:
        # 确保在正确的事件循环中运行
        current_loop = asyncio.get_running_loop()
        logger.info(
            "[WebSocketTest] 当前事件循环: %s, 状态: %s",
            current_loop, '运行中' if current_loop.is_running() else '已关闭'
        )
        
        # 创建配置并初始化客户端（在函数内部，每次测试使用新实例）
        logger.info("[WebSocketTest] 正在初始化客户端...")
        configuration_ws_streams = ConfigurationWebSocketStreams(
            stream_url=os.getenv(
                "STREAM_URL", DERIVATIVES_TRADING_USDS_FUTURES_WS_STREAMS_PROD_URL
            )
        )
        client = DerivativesTradingUsdsFutures(
            config_ws_streams=configuration_ws_streams
        )
        logger.info("[WebSocketTest] ✅ 客户端初始化成功")
        
        # 创建WebSocket连接
        logger.info("[WebSocketTest] 正在创建WebSocket连接...")
        connection = await client.websocket_streams.create_connection()
        logger.info("[WebSocketTest] ✅ WebSocket连接创建成功: %s", connection)
        
        # 计算昨天和今天的日期
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        
        logger.info("=" * 80)
        logger.info("[WebSocketTest] 📋 测试配置:")
        logger.info("[WebSocketTest]   - Symbol: %s", test_symbol)
        logger.info("[WebSocketTest]   - Interval数量: %s", len(test_intervals))
        logger.info("[WebSocketTest]   - Interval列表: %s", test_intervals)
        logger.info("[WebSocketTest]   - 今天日期: %s", today.strftime('%Y-%m-%d'))
        logger.info("[WebSocketTest]   - 昨天日期: %s", yesterday.strftime('%Y-%m-%d'))
        logger.info("[WebSocketTest]   - 每个interval等待超时: %s秒", MESSAGE_WAIT_TIMEOUT)
        logger.info("[WebSocketTest]   - 每个interval需要消息数: %s", MESSAGES_PER_INTERVAL)
        logger.info("=" * 80)
        
        # 存储所有interval的测试结果
        all_results = []
        
        # 对每个interval进行测试
        for idx, interval in enumerate(test_intervals, 1):
            logger.info(
                "[WebSocketTest] 🔄 处理 interval %s (%s/%s)",
                interval, idx, len(test_intervals)
            )
            
            try:
                result = await test_interval(
                    connection,
                    test_symbol,
                    interval,
                    today,
                    yesterday
                )
                all_results.append(result)
            except Exception as e:
                logger.error(
                    "[WebSocketTest] ❌ [%s %s] 测试失败: %s",
                    test_symbol, interval, e, exc_info=True
                )
                all_results.append({
                    "symbol": test_symbol,
                    "interval": interval,
                    "received_count": 0,
                    "expected_count": MESSAGES_PER_INTERVAL,
                    "success": False,
                    "error": str(e),
                    "klines": []
                })
        
        # 打印测试结果汇总
        logger.info("=" * 80)
        logger.info("[WebSocketTest] 📊 测试结果汇总")
        logger.info("=" * 80)
        
        success_count = sum(1 for r in all_results if r.get("success", False))
        total_count = len(all_results)
        
        logger.info("[WebSocketTest] 总测试数: %s", total_count)
        logger.info("[WebSocketTest] 成功数: %s", success_count)
        logger.info("[WebSocketTest] 失败数: %s", total_count - success_count)
        
        for result in all_results:
            status = "✅" if result.get("success", False) else "❌"
            logger.info(
                "[WebSocketTest] %s [%s %s] 收到 %s/%s 条消息",
                status,
                result["symbol"],
                result["interval"],
                result["received_count"],
                result["expected_count"]
            )
        
        logger.info("=" * 80)
        
        # 检查连接有效期
        connection_created_at = datetime.now()
        connection_duration = datetime.now() - connection_created_at
        logger.info("[WebSocketTest] 连接持续时间: %s", connection_duration)
        if connection_duration > timedelta(hours=24):
            logger.warning("[WebSocketTest] ⚠️  连接已超过24小时有效期，应重新连接")
            
    except Exception as e:
        logger.error("[WebSocketTest] ❌ kline_candlestick_streams() 错误: %s", e, exc_info=True)
    finally:
        if connection:
            logger.info("[WebSocketTest] 🔌 开始关闭WebSocket连接...")
            close_start = datetime.now()
            try:
                await connection.close_connection(close_session=True)
                close_duration = (datetime.now() - close_start).total_seconds()
                logger.info(
                    "[WebSocketTest] ✅ 连接已关闭 (耗时: %.3fs)",
                    close_duration
                )
            except Exception as e:
                close_duration = (datetime.now() - close_start).total_seconds()
                logger.error(
                    "[WebSocketTest] ❌ 关闭连接失败 (耗时: %.3fs): %s",
                    close_duration, e, exc_info=True
                )


# ============================================================================
# 主入口
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='测试 Binance WebSocket K线数据订阅')
    parser.add_argument(
        '--symbol',
        type=str,
        default=None,
        help='测试用的symbol，例如: --symbol BTCUSDT'
    )
    parser.add_argument(
        '--intervals',
        type=str,
        nargs='+',
        default=None,
        help='测试用的interval列表，例如: --intervals 1m 5m 15m'
    )
    
    args = parser.parse_args()
    
    # 如果通过命令行参数指定了symbol和intervals，则使用命令行参数
    test_symbol = args.symbol if args.symbol else TEST_SYMBOL
    test_intervals = args.intervals if args.intervals else TEST_INTERVALS
    
    try:
        asyncio.run(kline_candlestick_streams(
            symbol=test_symbol,
            intervals=test_intervals
        ))
    except KeyboardInterrupt:
        logger.info("[WebSocketTest] ⚠️  测试被用户中断")
    except Exception as e:
        logger.error("[WebSocketTest] ❌ 测试执行失败: %s", e, exc_info=True)
