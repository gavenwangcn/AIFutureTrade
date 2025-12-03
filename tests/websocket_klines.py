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
    print("========================\n")

async def kline_candlestick_streams():
    connection = None
    try:
        connection = await client.websocket_streams.create_connection()
        
        # 计算昨天和今天的日期
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        
        print(f"正在获取A2ZUSDT日K线数据...")
        print(f"今天日期: {today.strftime('%Y-%m-%d')}")
        print(f"昨天日期: {yesterday.strftime('%Y-%m-%d')}")
        
        # 控制订阅频率，确保符合要求（每秒不超过10个订阅消息）
        print(f"[WebSocketTest] 订阅前等待1秒，确保不超过订阅频率限制...")
        await asyncio.sleep(1)
        
        # 订阅K线流
        stream = await connection.kline_candlestick_streams(
            symbol="A2ZUSDT",
            interval="1m",
        )
        
        # 存储接收到的K线数据
        received_klines = []
        
        # 连接创建时间，用于检查连接有效期
        connection_created_at = datetime.now()
        
        def on_message(data):
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
                        print_kline_data(data, "今天")
                    elif kline_date == yesterday.date():
                        print_kline_data(data, "昨天")
                    else:
                        print_kline_data(data, f"{kline_date}")
                
                # 当收集到足够的数据后取消订阅
                if len(received_klines) >= 2:
                    asyncio.create_task(stream.unsubscribe())
            except Exception as e:
                logging.error(f"Error in on_message: {e}, data: {type(data)}")
                # 打印数据的属性，便于调试
                if hasattr(data, '__dict__'):
                    logging.error(f"Data attributes: {data.__dict__}")
                elif isinstance(data, dict):
                    logging.error(f"Data keys: {data.keys()}")

        stream.on("message", on_message)
        
        # 定期发送ping请求，保持连接活跃
        # 注意：根据SDK错误信息，WebSocketCommon.ping()需要connection参数，不是实例方法
        # 暂时注释掉ping发送，避免测试错误
        # async def send_ping():
        #     while len(received_klines) < 2:
        #         try:
        #             if connection and hasattr(connection, 'ping'):
        #                 await connection.ping()
        #                 print(f"[WebSocketTest] 发送ping请求")
        #             await asyncio.sleep(5)  # 每5秒发送一次ping
        #         except Exception as e:
        #             logging.error(f"Error sending ping: {e}")
        #             break
        # 
        # ping_task = asyncio.create_task(send_ping())
        
        # 创建事件，用于等待数据接收完成
        data_received_event = asyncio.Event()
        
        # 修改消息处理器，当收到足够数据时设置事件
        original_on_message = on_message
        
        def enhanced_on_message(data):
            original_on_message(data)
            # 当收集到足够的数据后取消订阅并设置事件
            if len(received_klines) >= 2:
                asyncio.create_task(stream.unsubscribe())
                data_received_event.set()
        
        # 替换消息处理器
        stream.on("message", enhanced_on_message)
        
        # 等待数据接收完成，最多等待60秒
        print("[WebSocketTest] 等待接收K线数据，最多等待60秒...")
        try:
            # 等待数据接收完成，最多等待60秒
            await asyncio.wait_for(data_received_event.wait(), timeout=60)
            print("[WebSocketTest] 数据接收完成，正在处理...")
        except asyncio.TimeoutError:
            print("[WebSocketTest] 数据接收超时，可能没有新的K线数据生成")
        
        if received_klines:
            print(f"总共接收到 {len(received_klines)} 条K线数据")
        else:
            print("未接收到任何K线数据，请稍后重试")
            
        # 检查连接有效期
        connection_duration = datetime.now() - connection_created_at
        print(f"[WebSocketTest] 连接持续时间: {connection_duration}")
        if connection_duration > timedelta(hours=24):
            print(f"[WebSocketTest] 连接已超过24小时有效期，应重新连接")
            
    except Exception as e:
        logging.error(f"kline_candlestick_streams() error: {e}")
    finally:
        if connection:
            await connection.close_connection(close_session=True)
            print(f"[WebSocketTest] 连接已关闭")


if __name__ == "__main__":
    asyncio.run(kline_candlestick_streams())
