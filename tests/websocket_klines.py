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
    "5m",
    "15m"
]

# 注意：每个interval会持续等待直到收到消息，不设置超时时间

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
    yesterday: datetime,
    message_received_event: asyncio.Event
) -> Dict[str, Any]:
    """测试单个interval的K线数据订阅。
    
    Args:
        connection: WebSocket连接对象
        symbol: 交易对符号
        interval: 时间间隔
        today: 今天的日期
        yesterday: 昨天的日期
        message_received_event: 消息接收事件，收到消息后设置此事件
    
    Returns:
        包含测试结果的字典
    """
    logger.info("=" * 80)
    logger.info("[WebSocketTest] [%s %s] 📡 开始构建监听", symbol, interval)
    logger.info("=" * 80)
    
    stream = None
    received_kline = None
    
    try:
        # 订阅K线流
        logger.info("[WebSocketTest] [%s %s] 📡 正在订阅K线流...", symbol, interval)
        stream = await connection.kline_candlestick_streams(
            symbol=symbol,
            interval=interval,
        )
        logger.info("[WebSocketTest] [%s %s] ✅ 订阅成功", symbol, interval)
        
        def on_message(data: Any):
            """K线消息处理器"""
            nonlocal received_kline
            
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
                    received_kline = data
                    
                    # 判断这是今天的还是昨天的K线
                    if kline_date == today.date():
                        day_label = "今天"
                    elif kline_date == yesterday.date():
                        day_label = "昨天"
                    else:
                        day_label = str(kline_date)
                    
                    # 打印K线数据
                    logger.info("=" * 80)
                    logger.info("[WebSocketTest] [%s %s] 📨 收到K线消息", symbol, interval)
                    print_kline_data(data, symbol, interval, day_label)
                    
                    # 立即关闭订阅
                    logger.info("[WebSocketTest] [%s %s] 🔌 收到消息后立即关闭订阅...", symbol, interval)
                    asyncio.create_task(close_stream_async(stream, symbol, interval))
                    
                    # 设置事件，通知已收到消息
                    if not message_received_event.is_set():
                        message_received_event.set()
            except Exception as e:
                logger.error(
                    "[WebSocketTest] [%s %s] ❌ 处理消息时出错: %s",
                    symbol, interval, e, exc_info=True
                )
                # 打印数据的属性，便于调试
                if hasattr(data, '__dict__'):
                    logger.error("[WebSocketTest] [%s %s] Data attributes: %s", symbol, interval, data.__dict__)
                elif isinstance(data, dict):
                    logger.error("[WebSocketTest] [%s %s] Data keys: %s", symbol, interval, list(data.keys()))
        
        # 注册消息处理器
        stream.on("message", on_message)
        
        # 等待数据接收完成（不设置超时，一直等待）
        logger.info(
            "[WebSocketTest] [%s %s] ⏳ 等待接收K线数据（持续等待，直到收到消息）...",
            symbol, interval
        )
        
        # 等待消息接收事件（不设置超时）
        await message_received_event.wait()
        
        logger.info(
            "[WebSocketTest] [%s %s] ✅ 已收到消息，测试完成",
            symbol, interval
        )
        logger.info("=" * 80)
        
        return {
            "symbol": symbol,
            "interval": interval,
            "success": True,
            "kline": received_kline
        }
        
    except Exception as e:
        logger.error(
            "[WebSocketTest] [%s %s] ❌ 测试失败: %s",
            symbol, interval, e, exc_info=True
        )
        # 如果出错，尝试关闭订阅
        if stream:
            try:
                await close_stream_async(stream, symbol, interval)
            except Exception:
                pass
        
        return {
            "symbol": symbol,
            "interval": interval,
            "success": False,
            "error": str(e),
            "kline": None
        }


async def close_stream_async(stream: Any, symbol: str, interval: str):
    """异步关闭stream订阅。
    
    Args:
        stream: 流对象
        symbol: 交易对符号
        interval: 时间间隔
    """
    logger.info("[WebSocketTest] [%s %s] 🔌 开始关闭订阅...", symbol, interval)
    close_start = datetime.now()
    try:
        await stream.unsubscribe()
        close_duration = (datetime.now() - close_start).total_seconds()
        logger.info(
            "[WebSocketTest] [%s %s] ✅ 订阅已关闭 (耗时: %.3fs)",
            symbol, interval, close_duration
        )
    except Exception as e:
        close_duration = (datetime.now() - close_start).total_seconds()
        logger.error(
            "[WebSocketTest] [%s %s] ❌ 关闭订阅失败 (耗时: %.3fs): %s",
            symbol, interval, close_duration, e, exc_info=True
        )


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
        logger.info("[WebSocketTest]   - 等待模式: 持续等待直到收到消息（无超时）")
        logger.info("=" * 80)
        
        # 同时构建所有interval的监听
        logger.info("=" * 80)
        logger.info("[WebSocketTest] 🚀 开始同时构建 %s 个interval的监听", len(test_intervals))
        logger.info("[WebSocketTest] 📋 Interval列表: %s", test_intervals)
        logger.info("=" * 80)
        
        # 为每个interval创建独立的事件
        interval_events = {}
        for interval in test_intervals:
            interval_events[interval] = asyncio.Event()
        
        # 同时创建所有interval的订阅任务
        tasks = []
        for idx, interval in enumerate(test_intervals, 1):
            logger.info(
                "[WebSocketTest] 🔨 [%s/%s] 创建 %s %s 的订阅任务...",
                idx, len(test_intervals), test_symbol, interval
            )
            
            # 控制订阅频率，确保符合要求（每秒不超过10个订阅消息）
            if idx > 1:
                await asyncio.sleep(0.1)  # 每个订阅间隔0.1秒
            
            task = asyncio.create_task(
                test_interval(
                    connection,
                    test_symbol,
                    interval,
                    today,
                    yesterday,
                    interval_events[interval]
                )
            )
            tasks.append((interval, task))
        
        logger.info("=" * 80)
        logger.info("[WebSocketTest] ✅ 所有 %s 个interval的监听已同时构建完成", len(test_intervals))
        logger.info("[WebSocketTest] ⏳ 等待所有interval收到消息...")
        logger.info("=" * 80)
        
        # 等待所有interval都收到消息
        all_results = []
        for interval, task in tasks:
            try:
                result = await task
                all_results.append(result)
            except Exception as e:
                logger.error(
                    "[WebSocketTest] ❌ [%s %s] 任务执行失败: %s",
                    test_symbol, interval, e, exc_info=True
                )
                all_results.append({
                    "symbol": test_symbol,
                    "interval": interval,
                    "success": False,
                    "error": str(e),
                    "kline": None
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
            if result.get("success", False):
                logger.info(
                    "[WebSocketTest] %s [%s %s] 已收到消息并关闭",
                    status,
                    result["symbol"],
                    result["interval"]
                )
            else:
                logger.error(
                    "[WebSocketTest] %s [%s %s] 失败: %s",
                    status,
                    result["symbol"],
                    result["interval"],
                    result.get("error", "未知错误")
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
