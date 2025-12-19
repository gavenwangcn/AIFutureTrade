"""
市场数据流模块 - 通过币安WebSocket将市场数据流式传输到MySQL

本模块提供以下功能：
1. Ticker流：实时接收所有交易对的24小时ticker数据，存储到24_market_tickers表

主要组件：
- MarketTickerStream: 管理全市场ticker的WebSocket流
- run_market_ticker_stream: 运行ticker流的主入口函数（支持自动重连）

使用场景：
- 后台服务：通过async_agent启动ticker流服务

注意：
- Ticker流每30分钟自动重连（币安WebSocket连接限制）
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import (
    DERIVATIVES_TRADING_USDS_FUTURES_WS_STREAMS_PROD_URL,
    ConfigurationWebSocketStreams,
    DerivativesTradingUsdsFutures,
)
from binance_common.constants import WebsocketMode

import common.config as app_config
from common.database.database_market_tickers import MarketTickersDatabase

logger = logging.getLogger(__name__)


# ============ 工具函数：数据类型转换 ============

def _to_float(value: Any) -> float:
    """
    将值转换为浮点数
    
    Args:
        value: 待转换的值（可能是字符串、数字等）
    
    Returns:
        float: 转换后的浮点数，转换失败时返回0.0
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    """
    将值转换为整数
    
    Args:
        value: 待转换的值（可能是字符串、数字等）
    
    Returns:
        int: 转换后的整数，转换失败时返回0
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


# ============ Ticker数据处理函数 ============

def _normalize_ticker(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    标准化ticker数据
    
    将币安WebSocket返回的原始ticker数据转换为标准格式，
    用于存储到24_market_tickers表。
    
    注意：不再从报文中解析以下字段，这些字段将在upsert_market_tickers中根据业务逻辑计算：
    - price_change: 价格变化
    - price_change_percent: 价格变化百分比
    - side: 涨跌方向（gainer/loser）
    - change_percent_text: 价格变化百分比文本
    - open_price: 开盘价
    
    Args:
        raw: 币安WebSocket返回的原始ticker数据字典
    
    Returns:
        Dict[str, Any]: 标准化后的ticker数据字典，包含以下字段：
            - event_time: 事件时间戳（毫秒）
            - symbol: 交易对符号
            - average_price: 加权平均价
            - last_price: 最新价格
            - last_trade_volume: 最新交易量
            - high_price: 24小时最高价
            - low_price: 24小时最低价
            - base_volume: 24小时基础资产成交量
            - quote_volume: 24小时计价资产成交量
            - stats_open_time: 统计开始时间（毫秒）
            - stats_close_time: 统计结束时间（毫秒）
            - first_trade_id: 首笔交易ID
            - last_trade_id: 末笔交易ID
            - trade_count: 24小时交易笔数
    """
    symbol = raw.get("s", "")
    logger.debug("[MarketStreams] Normalizing ticker data for symbol: %s", symbol)
    logger.debug("[MarketStreams] Raw ticker data: %s", raw)
    
    normalized = {
        "event_time": _to_int(raw.get("E")),
        "symbol": symbol,
        # 不再从报文中解析这些字段，将在 upsert_market_tickers 中计算
        # "price_change": _to_float(raw.get("p")),
        # "price_change_percent": _to_float(percent),
        # "side": "loser" if _to_float(percent) < 0 else "gainer",
        # "change_percent_text": f"{_to_float(percent):.2f}%",
        "average_price": _to_float(raw.get("w")),
        "last_price": _to_float(raw.get("c")),
        "last_trade_volume": _to_float(raw.get("Q")),
        # "open_price": _to_float(raw.get("o")),  # 不再从报文中解析
        "high_price": _to_float(raw.get("h")),
        "low_price": _to_float(raw.get("l")),
        "base_volume": _to_float(raw.get("v")),
        "quote_volume": _to_float(raw.get("q")),
        "stats_open_time": _to_int(raw.get("O")),
        "stats_close_time": _to_int(raw.get("C")),
        "first_trade_id": _to_int(raw.get("F")),
        "last_trade_id": _to_int(raw.get("L")),
        "trade_count": _to_int(raw.get("n")),
    }
    
    logger.debug("[MarketStreams] Normalized ticker data: %s", normalized)
    return normalized


def _extract_tickers(message: Any) -> List[Dict[str, Any]]:
    """
    从WebSocket消息中提取ticker数据列表
    
    支持多种消息格式：
    - bytes/bytearray: 自动解码为字符串
    - JSON字符串: 自动解析为字典
    - SDK响应对象: 使用model_dump()或__dict__转换
    - 字典: 直接提取data/tickers/payload字段，或使用整个字典
    - 列表: 直接返回
    
    Args:
        message: WebSocket接收到的原始消息，可能是：
            - bytes/bytearray: 字节数据
            - str: JSON字符串
            - dict: 字典对象
            - list: 列表对象
            - SDK响应对象: 具有model_dump()或__dict__属性的对象
    
    Returns:
        List[Dict[str, Any]]: ticker数据字典列表
    
    Note:
        - 如果消息格式无法识别，返回空列表
        - 支持嵌套的SDK响应对象（列表中的元素也可能是SDK对象）
    """
    logger.debug("[MarketStreams] Received raw message: %s", message)
    
    if isinstance(message, (bytes, bytearray)):
        message = message.decode()
        logger.debug("[MarketStreams] Decoded bytes message to string: %s", message[:100] + "..." if len(message) > 100 else message)

    if isinstance(message, str):
        try:
            message = json.loads(message)
            logger.debug("[MarketStreams] Parsed JSON message: %s", type(message))
        except json.JSONDecodeError:
            logger.warning("[MarketStreams] Unable to decode message: %s", message)
            return []

    # SDK response objects (e.g., AllMarketTickersStreamsResponse)
    if hasattr(message, "model_dump"):
        try:
            message = message.model_dump()
            logger.debug("[MarketStreams] Used model_dump to convert message object")
        except Exception:
            message = message.__dict__
            logger.debug("[MarketStreams] Fallback to __dict__ for message object")

    if isinstance(message, dict):
        data = message.get("data") or message.get("tickers") or message.get("payload")
        if data is None:
            data = message
        logger.debug("[MarketStreams] Extracted data from message: %s (type: %s)", "list" if isinstance(data, list) else "dict", type(data))
    else:
        data = message
        logger.debug("[MarketStreams] Using raw message as data: %s (type: %s)", "list" if isinstance(data, list) else "dict", type(data))

    result: List[Dict[str, Any]] = []
    if isinstance(data, list):
        for item in data:
            if hasattr(item, "model_dump"):
                try:
                    item_dict = item.model_dump()
                    result.append(item_dict)
                    logger.debug("[MarketStreams] Added item from model_dump: %s", item_dict.get("s"))
                    continue
                except Exception:
                    logger.debug("[MarketStreams] model_dump failed for item, falling back")
            if isinstance(item, dict):
                result.append(item)
                logger.debug("[MarketStreams] Added item as dict: %s", item.get("s"))
            else:
                item_dict = vars(item)
                result.append(item_dict)
                logger.debug("[MarketStreams] Added item from __dict__: %s", item_dict.get("s"))
        logger.debug("[MarketStreams] Extracted %d tickers from message", len(result))
        return result
    if isinstance(data, dict):
        logger.debug("[MarketStreams] Extracted 1 ticker from message")
        return [data]
    logger.debug("[MarketStreams] No tickers extracted from message")
    return []


# ============ Ticker流管理类 ============

class MarketTickerStream:
    """
    全市场Ticker流管理器
    
    负责通过币安WebSocket接收所有交易对的24小时ticker数据，
    并将数据存储到MySQL的24_market_tickers表中。
    
    特性：
    - 自动重连：每30分钟自动重新建立连接（币安WebSocket连接限制）
    - 增量更新：使用upsert_market_tickers实现增量插入/更新
    - 异常处理：完善的错误处理和日志记录
    
    使用示例：
        streamer = MarketTickerStream(db)
        await streamer.stream()  # 无限运行，自动重连
        # 或
        await streamer.stream(run_seconds=60)  # 运行60秒后停止
    """

    def __init__(self, db: MarketTickersDatabase) -> None:
        """
        初始化Ticker流管理器
        
        Args:
            db: MySQL数据库实例，用于存储ticker数据
        """
        self._db = db
        configuration_ws_streams = ConfigurationWebSocketStreams(
            stream_url=os.getenv(
                "STREAM_URL",
                DERIVATIVES_TRADING_USDS_FUTURES_WS_STREAMS_PROD_URL,
            ),
            reconnect_delay=120,
            mode=WebsocketMode.POOL,
            pool_size=3
        )
        self._client = DerivativesTradingUsdsFutures(
            config_ws_streams=configuration_ws_streams
        )
        # 连接生命周期管理
        self._connection_creation_time: Optional[datetime] = None
        # 最大连接时长：30分钟
        self._MAX_CONNECTION_HOURS = 0.5

    async def _handle_message(self, message: Any) -> None:
        """
        处理WebSocket接收到的ticker消息
        
        流程：
        1. 从消息中提取ticker数据列表
        2. 标准化每个ticker数据
        3. 批量插入/更新到数据库（使用upsert_market_tickers）
        
        Args:
            message: WebSocket接收到的原始消息
        
        Note:
            - 如果消息中没有ticker数据，直接返回
            - 使用asyncio.to_thread在线程池中执行数据库操作，并设置超时限制
            - 异常会被记录但不会中断流处理
            - 消息处理有严格的超时限制，避免长时间卡住
        """
        logger.debug("[MarketStreams] Starting to handle message")
        
        # 为整个消息处理设置超时（Python 3.10兼容版本）
        async def process_message():
            tickers = _extract_tickers(message)
            logger.debug("[MarketStreams] Extracted %d tickers from message", len(tickers))
            
            if not tickers:
                logger.info("[MarketStreams] No tickers to process")
                return
                
            normalized = [_normalize_ticker(ticker) for ticker in tickers]
            logger.debug("[MarketStreams] Normalized %d tickers for database upsert", len(normalized))
            
            # 记录部分关键数据用于调试
            if normalized:
                sample = normalized[:3]  # 只记录前3个作为样本
                logger.debug("[MarketStreams] Normalized data sample: %s", sample)
            
            try:
                # 使用优化后的增量插入逻辑（在线程池中执行，避免阻塞），设置20秒超时
                logger.debug("[MarketStreams] Calling upsert_market_tickers for %d symbols", len(normalized))
                db_task = asyncio.create_task(asyncio.to_thread(self._db.upsert_market_tickers, normalized))
                await asyncio.wait_for(db_task, timeout=20)  # 数据库操作最多20秒
                logger.debug("[MarketStreams] Successfully completed upsert_market_tickers")
            except asyncio.TimeoutError:
                logger.error("[MarketStreams] Database operation timed out after 20 seconds")
            except Exception as e:
                logger.error("[MarketStreams] Error during upsert_market_tickers: %s", e, exc_info=True)
        
        try:
            # 使用asyncio.wait_for实现Python 3.10兼容的超时控制
            await asyncio.wait_for(process_message(), timeout=30)  # 整个消息处理最多30秒
        except asyncio.TimeoutError:
            logger.error("[MarketStreams] Message processing timed out after 30 seconds")
        except Exception as e:
            logger.error("[MarketStreams] Unexpected error in message handling: %s", e, exc_info=True)
        
        logger.debug("[MarketStreams] Finished handling message")



    async def _should_reconnect(self) -> bool:
        """
        检查是否需要重新连接
        
        币安WebSocket连接有30分钟的限制，超过30分钟需要重新建立连接。
        
        Returns:
            bool: 如果需要重新连接返回True，否则返回False
        
        Note:
            - 如果连接创建时间未记录，返回False（不重连）
            - 连接时长超过_MAX_CONNECTION_HOURS（0.5小时）时返回True
        """
        if not self._connection_creation_time:
            return False
        elapsed_hours = (datetime.now(timezone.utc) - self._connection_creation_time).total_seconds() / 3600
        return elapsed_hours >= self._MAX_CONNECTION_HOURS

    async def stream(self, run_seconds: Optional[int] = None) -> None:
        """
        启动ticker流并持续接收数据
        
        建立WebSocket连接，订阅全市场ticker流，并持续接收数据直到：
        - 连接达到30分钟限制（自动重连）
        - 指定运行时长到期（run_seconds参数）
        - 发生异常或取消
        
        Args:
            run_seconds: 可选，运行时长（秒）。如果指定，运行指定时长后停止；
                         如果为None，则无限运行直到连接达到30分钟限制或发生异常
        
        Note:
            - 连接创建时间会被记录，用于判断是否需要重连
            - 每0.5秒检查一次是否需要重连
            - 异常会被捕获并记录，但不会中断流处理
            - 退出时会自动取消订阅并关闭连接
        """
        connection = None
        stream = None
        try:
            # 记录连接创建时间
            self._connection_creation_time = datetime.now(timezone.utc)
            logger.debug("[MarketStreams] Creating new WebSocket connection")
            
            # 为连接创建添加超时保护
            connection = await asyncio.wait_for(
                self._client.websocket_streams.create_connection(),
                timeout=15.0  # 最多等待15秒建立连接
            )
            
            # 为流订阅添加超时保护
            stream = await asyncio.wait_for(
                connection.all_market_tickers_streams(),
                timeout=10.0  # 最多等待10秒订阅成功
            )
            
            stream.on(
                "message",
                lambda data: asyncio.create_task(self._handle_message(data)),
            )

            if run_seconds is not None:
                await asyncio.sleep(run_seconds)
                await stream.unsubscribe()
            else:
                while True:
                    # 检查是否需要重新连接（30分钟到期）
                    if await self._should_reconnect():
                        logger.debug("[MarketStreams] Connection reached 30-minute limit, reconnecting...")
                        break
                    await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("[MarketStreams] Streaming error: %s", exc)
        finally:
            # 使用超时处理确保关闭操作不会卡住
            if stream:
                try:
                    close_task = asyncio.create_task(stream.unsubscribe())
                    await asyncio.wait_for(close_task, timeout=5)
                except asyncio.TimeoutError:
                    logger.error("[MarketStreams] Stream unsubscribe timed out")
                except Exception:
                    logger.debug("[MarketStreams] Stream already unsubscribed or unsubscribe failed")
            if connection:
                try:
                    close_task = asyncio.create_task(connection.close_connection(close_session=True))
                    await asyncio.wait_for(close_task, timeout=5)
                except asyncio.TimeoutError:
                    logger.error("[MarketStreams] Connection close timed out")
                except Exception as e:
                    logger.debug("[MarketStreams] Error closing connection: %s", e)


# ============ Ticker流主入口函数 ============

async def run_market_ticker_stream(run_seconds: Optional[int] = None) -> None:
    """
    运行全市场ticker流服务（主入口函数）
    
    创建MarketTickerStream实例并启动流服务，支持自动重连。
    每30分钟自动重新建立连接（币安WebSocket连接限制）。
    
    使用场景：
    - 后台服务：通过async_agent启动，持续运行
    - 测试/调试：可以指定运行时长进行测试
    
    Args:
        run_seconds: 可选，运行时长（秒）。如果指定，运行指定时长后停止；
                     如果为None，则无限运行直到被取消
    
    Note:
        - 如果指定了run_seconds，只运行一次
        - 如果未指定run_seconds，会无限循环运行，每次连接30分钟后自动重连
        - 异常会被捕获并记录，然后等待5秒后重连（避免快速重连循环）
        - 可以通过asyncio.CancelledError取消任务
        - 所有资源都有严格的超时管理，避免长时间卡住
    """
    db = MarketTickersDatabase()
    
    try:
        if run_seconds is not None:
            # If a specific runtime is provided, run once
            streamer = MarketTickerStream(db)
            await streamer.stream(run_seconds=run_seconds)
        else:
            # Run indefinitely with automatic reconnection every 30 minutes
            start_time = datetime.now(timezone.utc)
            while True:
                streamer = MarketTickerStream(db)
                try:
                    # Stream until connection needs to be refreshed (30 minutes)
                    await streamer.stream()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.exception("[MarketStreams] Stream error, reconnecting...")
                    # Wait a short time before reconnecting to avoid rapid reconnection loops
                    await asyncio.sleep(5)
                
                # Check if we've been running for the requested duration
                if run_seconds and (datetime.now(timezone.utc) - start_time).total_seconds() >= run_seconds:
                    break
                
                logger.debug("[MarketStreams] Reconnecting to WebSocket...")
    finally:
        # 显式关闭数据库连接池
        try:
            db.close()
            logger.debug("[MarketStreams] Database connection pool closed")
        except Exception as e:
            logger.error("[MarketStreams] Error closing database: %s", e)


# ============ K线数据处理函数 ============
# _normalize_kline 和 run_kline_sync_agent 函数已删除，K线相关功能不再使用


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=getattr(logging, app_config.LOG_LEVEL, logging.INFO),
        format=app_config.LOG_FORMAT,
        datefmt=app_config.LOG_DATE_FORMAT,
    )

    parser = argparse.ArgumentParser(
        description="Stream Binance market data into MySQL"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Optional runtime in seconds before shutting down (runs forever when omitted)",
    )

    args = parser.parse_args()

    try:
        # kline-sync 模式已删除，K线同步功能不再使用
        asyncio.run(run_market_ticker_stream(run_seconds=args.duration))
    except KeyboardInterrupt:
        logger.debug("[MarketStreams] Interrupted by user")