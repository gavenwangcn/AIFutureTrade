import asyncio
import os
import logging
from datetime import datetime, timedelta

from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import (
    DerivativesTradingUsdsFutures,
    DERIVATIVES_TRADING_USDS_FUTURES_WS_STREAMS_PROD_URL,
    ConfigurationWebSocketStreams,
)


# Configure logging
logging.basicConfig(level=logging.INFO)

# Create configuration for the WebSocket Streams
configuration_ws_streams = ConfigurationWebSocketStreams(
    stream_url=os.getenv(
        "STREAM_URL", DERIVATIVES_TRADING_USDS_FUTURES_WS_STREAMS_PROD_URL
    )
)

# Initialize DerivativesTradingUsdsFutures client
client = DerivativesTradingUsdsFutures(config_ws_streams=configuration_ws_streams)


def print_kline_data(kline_data, day_label):
    """打印K线数据用于测试验证"""
    print(f"\n=== {day_label} K线数据 ===")
    print(f"开盘时间: {datetime.fromtimestamp(kline_data['k']['t'] / 1000).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"收盘时间: {datetime.fromtimestamp(kline_data['k']['T'] / 1000).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"开盘价: {kline_data['k']['o']}")
    print(f"最高价: {kline_data['k']['h']}")
    print(f"最低价: {kline_data['k']['l']}")
    print(f"收盘价: {kline_data['k']['c']}")
    print(f"成交量: {kline_data['k']['v']}")
    print(f"成交笔数: {kline_data['k']['n']}")
    print(f"是否完结: {kline_data['k']['x']}")
    print("========================\n")

async def kline_candlestick_streams():
    connection = None
    try:
        connection = await client.websocket_streams.create_connection()

        # 计算昨天和今天的日期
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        
        print(f"正在获取BTCUSDT日K线数据...")
        print(f"今天日期: {today.strftime('%Y-%m-%d')}")
        print(f"昨天日期: {yesterday.strftime('%Y-%m-%d')}")

        stream = await connection.kline_candlestick_streams(
            symbol="btcusdt",
            interval="1d",
        )
        
        # 存储接收到的K线数据
        received_klines = []
        
        def on_message(data):
            # 只处理完结的K线数据
            if data['k']['x']:  # x表示K线是否完结
                received_klines.append(data)
                # 判断这是今天的还是昨天的K线
                kline_date = datetime.fromtimestamp(data['k']['t'] / 1000).date()
                if kline_date == today.date():
                    print_kline_data(data, "今天")
                elif kline_date == yesterday.date():
                    print_kline_data(data, "昨天")
                else:
                    print_kline_data(data, f"{kline_date}")
            
            # 当收集到足够的数据后取消订阅
            if len(received_klines) >= 2:
                asyncio.create_task(stream.unsubscribe())

        stream.on("message", on_message)

        # 等待足够长的时间以接收K线数据
        await asyncio.sleep(10)
        
        if received_klines:
            print(f"总共接收到 {len(received_klines)} 条K线数据")
        else:
            print("未接收到任何K线数据，请稍后重试")
            
    except Exception as e:
        logging.error(f"kline_candlestick_streams() error: {e}")
    finally:
        if connection:
            await connection.close_connection(close_session=True)


if __name__ == "__main__":
    asyncio.run(kline_candlestick_streams())
