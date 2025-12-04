"""
测试 data_agent 接收K线数据消息后的处理逻辑

测试内容：
1. 批量添加多个symbol（15个一组）的所有interval K线流
2. 监听所有接收到的K线消息
3. 检查消息处理过程中是否有异常（包括 normalize_kline 和 insert_market_klines）
4. 记录详细的统计信息（成功、失败、异常等）
5. 测试所有interval（1m, 5m, 15m, 1h, 4h, 1d, 1w）
"""
import asyncio
import json
import logging
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class KlineMessageTestHandler:
    """K线消息测试处理器，用于捕获和统计消息处理结果。"""
    
    def __init__(self):
        # 统计信息
        self.stats = {
            "total_messages": 0,  # 总消息数
            "success_messages": 0,  # 成功处理的消息数
            "failed_messages": 0,  # 处理失败的消息数
            "normalize_errors": 0,  # normalize_kline 错误数
            "insert_errors": 0,  # insert_market_klines 错误数
            "other_errors": 0,  # 其他错误数
        }
        
        # 按symbol和interval统计
        self.by_symbol_interval: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        
        # 错误详情
        self.errors: List[Dict] = []
        
        # 成功处理的消息样本（每个symbol-interval组合保留最新的一条）
        self.sample_messages: Dict[str, Dict] = {}
        
        # 锁（用于线程安全）
        self._lock = asyncio.Lock()
    
    async def handle_message(self, symbol: str, interval: str, message: Any, 
                           original_handler, db) -> None:
        """处理K线消息，记录统计信息和错误。
        
        Args:
            symbol: 交易对符号
            interval: 时间间隔
            message: 原始消息数据
            original_handler: 原始的消息处理器
            db: 数据库实例（用于测试insert_market_klines）
        """
        message_start_time = datetime.now(timezone.utc)
        key = f"{symbol}_{interval}"
        
        async with self._lock:
            self.stats["total_messages"] += 1
            self.by_symbol_interval[symbol][interval] += 1
        
        logger.debug(
            "[测试] 📨 [消息处理] 收到K线消息 %s %s (消息序号: %s, 时间: %s)",
            symbol, interval, self.stats["total_messages"], message_start_time.isoformat()
        )
        
        try:
            # 步骤1: 测试 normalize_kline
            normalize_start_time = datetime.now(timezone.utc)
            logger.debug(
                "[测试] 🔧 [消息处理] 步骤1/2: 开始规范化K线数据 %s %s...",
                symbol, interval
            )
            
            from market.market_streams import _normalize_kline
            
            try:
                normalized = _normalize_kline(message)
                normalize_duration = (datetime.now(timezone.utc) - normalize_start_time).total_seconds()
                
                if normalized is None:
                    async with self._lock:
                        self.stats["normalize_errors"] += 1
                        self.stats["failed_messages"] += 1
                        self.errors.append({
                            "symbol": symbol,
                            "interval": interval,
                            "step": "normalize_kline",
                            "error": "normalize_kline returned None",
                            "message_preview": str(message)[:200] if message else None,
                            "timestamp": message_start_time.isoformat()
                        })
                    
                    logger.warning(
                        "[测试] ⚠️  [消息处理] normalize_kline 返回 None %s %s (耗时: %.3fs)",
                        symbol, interval, normalize_duration
                    )
                    return
                
                logger.debug(
                    "[测试] ✅ [消息处理] 步骤1/2: 规范化完成 %s %s (耗时: %.3fs, 规范化数据: %s)",
                    symbol, interval, normalize_duration,
                    {k: v for k, v in normalized.items() if k not in ['event_time', 'kline_start_time', 'kline_end_time']}
                )
            except Exception as e:
                normalize_duration = (datetime.now(timezone.utc) - normalize_start_time).total_seconds()
                error_info = {
                    "symbol": symbol,
                    "interval": interval,
                    "step": "normalize_kline",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc(),
                    "message_preview": str(message)[:200] if message else None,
                    "timestamp": message_start_time.isoformat()
                }
                
                async with self._lock:
                    self.stats["normalize_errors"] += 1
                    self.stats["failed_messages"] += 1
                    self.errors.append(error_info)
                
                logger.error(
                    "[测试] ❌ [消息处理] normalize_kline 异常 %s %s (耗时: %.3fs): %s",
                    symbol, interval, normalize_duration, e, exc_info=True
                )
                return
            
            # 步骤2: 测试 insert_market_klines
            insert_start_time = datetime.now(timezone.utc)
            logger.debug(
                "[测试] 💾 [消息处理] 步骤2/2: 开始插入数据库 %s %s...",
                symbol, interval
            )
            
            try:
                # 调用原始处理器的数据库插入逻辑
                await original_handler(symbol, interval, message)
                
                insert_duration = (datetime.now(timezone.utc) - insert_start_time).total_seconds()
                
                async with self._lock:
                    self.stats["success_messages"] += 1
                    # 保存成功处理的消息样本
                    self.sample_messages[key] = {
                        "symbol": symbol,
                        "interval": interval,
                        "normalized_data": normalized,
                        "timestamp": message_start_time.isoformat(),
                        "normalize_duration": normalize_duration,
                        "insert_duration": insert_duration,
                        "total_duration": (datetime.now(timezone.utc) - message_start_time).total_seconds()
                    }
                
                logger.info(
                    "[测试] ✅ [消息处理] 成功处理 %s %s (总耗时: %.3fs, normalize: %.3fs, insert: %.3fs)",
                    symbol, interval,
                    (datetime.now(timezone.utc) - message_start_time).total_seconds(),
                    normalize_duration, insert_duration
                )
            except Exception as e:
                insert_duration = (datetime.now(timezone.utc) - insert_start_time).total_seconds()
                error_info = {
                    "symbol": symbol,
                    "interval": interval,
                    "step": "insert_market_klines",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc(),
                    "normalized_data": normalized,
                    "timestamp": message_start_time.isoformat()
                }
                
                async with self._lock:
                    self.stats["insert_errors"] += 1
                    self.stats["failed_messages"] += 1
                    self.errors.append(error_info)
                
                logger.error(
                    "[测试] ❌ [消息处理] insert_market_klines 异常 %s %s (耗时: %.3fs): %s",
                    symbol, interval, insert_duration, e, exc_info=True
                )
        except Exception as e:
            # 捕获其他未预期的异常
            total_duration = (datetime.now(timezone.utc) - message_start_time).total_seconds()
            error_info = {
                "symbol": symbol,
                "interval": interval,
                "step": "other",
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
                "timestamp": message_start_time.isoformat()
            }
            
            async with self._lock:
                self.stats["other_errors"] += 1
                self.stats["failed_messages"] += 1
                self.errors.append(error_info)
            
            logger.error(
                "[测试] ❌ [消息处理] 未预期的异常 %s %s (耗时: %.3fs): %s",
                symbol, interval, total_duration, e, exc_info=True
            )
    
    def get_stats(self) -> Dict:
        """获取统计信息。"""
        return {
            **self.stats,
            "by_symbol_interval": dict(self.by_symbol_interval),
            "error_count": len(self.errors),
            "sample_message_count": len(self.sample_messages)
        }
    
    def print_report(self) -> None:
        """打印测试报告。"""
        logger.info("=" * 80)
        logger.info("[测试报告] 📊 K线消息处理测试统计")
        logger.info("=" * 80)
        logger.info("[测试报告] 总消息数: %s", self.stats["total_messages"])
        logger.info("[测试报告] 成功处理: %s", self.stats["success_messages"])
        logger.info("[测试报告] 处理失败: %s", self.stats["failed_messages"])
        logger.info("[测试报告]   - normalize_kline 错误: %s", self.stats["normalize_errors"])
        logger.info("[测试报告]   - insert_market_klines 错误: %s", self.stats["insert_errors"])
        logger.info("[测试报告]   - 其他错误: %s", self.stats["other_errors"])
        logger.info("=" * 80)
        
        if self.stats["total_messages"] > 0:
            success_rate = (self.stats["success_messages"] / self.stats["total_messages"]) * 100
            logger.info("[测试报告] 成功率: %.2f%%", success_rate)
        
        # 按symbol统计
        logger.info("[测试报告] 📊 按Symbol统计:")
        for symbol, intervals in sorted(self.by_symbol_interval.items()):
            total_for_symbol = sum(intervals.values())
            logger.info(
                "[测试报告]   - %s: 总消息数=%s, intervals=%s",
                symbol, total_for_symbol, dict(intervals)
            )
        
        # 错误详情
        if self.errors:
            logger.info("=" * 80)
            logger.info("[测试报告] ❌ 错误详情 (共 %s 个错误):", len(self.errors))
            for idx, error in enumerate(self.errors[:10], 1):  # 只显示前10个错误
                logger.error(
                    "[测试报告]   [错误 %s] %s %s - %s: %s",
                    idx, error["symbol"], error["interval"],
                    error["step"], error["error"]
                )
            if len(self.errors) > 10:
                logger.error("[测试报告]   ... 还有 %s 个错误未显示", len(self.errors) - 10)
        
        # 成功样本
        if self.sample_messages:
            logger.info("=" * 80)
            logger.info("[测试报告] ✅ 成功处理的消息样本 (共 %s 个):", len(self.sample_messages))
            for idx, (key, sample) in enumerate(list(self.sample_messages.items())[:5], 1):
                logger.info(
                    "[测试报告]   [样本 %s] %s %s (耗时: %.3fs)",
                    idx, sample["symbol"], sample["interval"], sample["total_duration"]
                )
        
        logger.info("=" * 80)


async def test_data_agent_kline_processing():
    """测试 data_agent 接收K线数据消息后的处理逻辑。"""
    from data.data_agent import DataAgentKlineManager, KLINE_INTERVALS
    from common.database_clickhouse import ClickHouseDatabase
    
    logger.info("=" * 80)
    logger.info("[测试] 🚀 开始测试 data_agent K线消息处理逻辑")
    logger.info("=" * 80)
    
    # 初始化数据库和kline_manager
    db = ClickHouseDatabase()
    kline_manager = DataAgentKlineManager(db, max_symbols=100)
    
    # 创建测试处理器
    test_handler = KlineMessageTestHandler()
    
    # 保存原有消息处理器
    original_handle_message = kline_manager._handle_kline_message
    
    # 定义新的消息处理器，用于测试
    async def test_handle_message(symbol: str, interval: str, message: Any) -> None:
        """测试用的消息处理器。"""
        await test_handler.handle_message(symbol, interval, message, original_handle_message, db)
    
    # 替换消息处理器
    kline_manager._handle_kline_message = test_handle_message
    logger.info("[测试] ✅ 消息处理器已替换为测试处理器")
    
    # 测试用的symbol列表（15个）
    test_symbols = [
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT",
        "XRPUSDT", "DOGEUSDT", "DOTUSDT", "MATICUSDT", "AVAXUSDT",
        "LINKUSDT", "UNIUSDT", "LTCUSDT", "ATOMUSDT", "ETCUSDT"
    ]
    
    logger.info("[测试] 📋 测试配置:")
    logger.info("[测试]   - Symbol数量: %s", len(test_symbols))
    logger.info("[测试]   - Interval数量: %s", len(KLINE_INTERVALS))
    logger.info("[测试]   - 总连接数: %s", len(test_symbols) * len(KLINE_INTERVALS))
    logger.info("[测试]   - Symbol列表: %s", test_symbols)
    logger.info("=" * 80)
    
    try:
        # 步骤1: 批量添加所有symbol的所有interval
        logger.info("[测试] 🔨 [步骤1] 开始批量添加symbol K线流...")
        add_start_time = datetime.now(timezone.utc)
        
        for idx, symbol in enumerate(test_symbols, 1):
            logger.info(
                "[测试] 🔨 [步骤1] 添加 symbol %s (%s/%s): %s",
                symbol, idx, len(test_symbols), symbol
            )
            
            try:
                result = await kline_manager.add_symbol_streams(symbol)
                logger.info(
                    "[测试] ✅ [步骤1] symbol %s 添加完成: 成功=%s, 失败=%s, 跳过=%s",
                    symbol, result["success_count"], result["failed_count"], result["skipped_count"]
                )
            except Exception as e:
                logger.error(
                    "[测试] ❌ [步骤1] symbol %s 添加失败: %s",
                    symbol, e, exc_info=True
                )
        
        add_duration = (datetime.now(timezone.utc) - add_start_time).total_seconds()
        logger.info(
            "[测试] ✅ [步骤1] 批量添加完成 (总耗时: %.3fs)",
            add_duration
        )
        logger.info("=" * 80)
        
        # 步骤2: 等待接收K线数据消息
        logger.info("[测试] 📨 [步骤2] 开始监听K线数据消息...")
        logger.info("[测试] 📨 [步骤2] 等待时间: 120秒（每个symbol-interval组合至少接收1条消息）")
        
        # 等待足够的时间让所有连接都接收到至少一条消息
        # 根据interval不同，消息频率也不同（1m最快，1w最慢）
        wait_time = 120  # 等待120秒
        
        # 每10秒打印一次统计信息
        check_interval = 10
        elapsed = 0
        
        while elapsed < wait_time:
            await asyncio.sleep(check_interval)
            elapsed += check_interval
            
            stats = test_handler.get_stats()
            logger.info(
                "[测试] 📊 [步骤2] 进度: 已等待 %s/%s秒, 总消息数=%s, 成功=%s, 失败=%s",
                elapsed, wait_time,
                stats["total_messages"],
                stats["success_messages"],
                stats["failed_messages"]
            )
        
        logger.info("[测试] ✅ [步骤2] 监听完成")
        logger.info("=" * 80)
        
        # 步骤3: 打印测试报告
        logger.info("[测试] 📊 [步骤3] 生成测试报告...")
        test_handler.print_report()
        
        # 步骤4: 检查是否有严重错误
        stats = test_handler.get_stats()
        if stats["failed_messages"] > 0:
            logger.warning(
                "[测试] ⚠️  发现 %s 个处理失败的消息，请检查错误详情",
                stats["failed_messages"]
            )
        else:
            logger.info("[测试] ✅ 所有消息处理成功，未发现错误")
        
        # 步骤5: 验证数据库中的数据
        logger.info("[测试] 🔍 [步骤4] 验证数据库中的数据...")
        try:
            for symbol in test_symbols[:5]:  # 只验证前5个symbol
                for interval in KLINE_INTERVALS[:3]:  # 只验证前3个interval
                    try:
                        klines = db.get_market_klines(symbol, interval, limit=1)
                        if klines:
                            logger.info(
                                "[测试] ✅ [验证] %s %s 数据库中有数据 (最新K线时间: %s)",
                                symbol, interval, klines[0].get('kline_start_time') if klines else None
                            )
                        else:
                            logger.warning(
                                "[测试] ⚠️  [验证] %s %s 数据库中暂无数据",
                                symbol, interval
                            )
                    except Exception as e:
                        logger.error(
                            "[测试] ❌ [验证] %s %s 查询数据库失败: %s",
                            symbol, interval, e
                        )
        except Exception as e:
            logger.error("[测试] ❌ [验证] 数据库验证失败: %s", e, exc_info=True)
        
        logger.info("=" * 80)
        logger.info("[测试] ✅ 测试完成")
        logger.info("=" * 80)
    
    finally:
        # 恢复原有消息处理器
        kline_manager._handle_kline_message = original_handle_message
        
        # 清理所有连接
        logger.info("[测试] 🧹 开始清理资源...")
        cleanup_start = datetime.now(timezone.utc)
        await kline_manager.cleanup_all()
        cleanup_duration = (datetime.now(timezone.utc) - cleanup_start).total_seconds()
        logger.info("[测试] ✅ 资源清理完成 (耗时: %.3fs)", cleanup_duration)
        logger.info("[测试] 🛑 测试已停止")


if __name__ == "__main__":
    try:
        asyncio.run(test_data_agent_kline_processing())
    except KeyboardInterrupt:
        logger.info("[测试] ⚠️  测试被用户中断")
    except Exception as e:
        logger.error("[测试] ❌ 测试执行失败: %s", e, exc_info=True)