"""
测试 data_agent 接收构建symbol监听命令请求后的代码执行逻辑

测试内容：
1. 模拟 HTTP POST /symbols/add 请求，批量添加symbol的所有interval K线流
2. 验证连接是否正常建立
3. 监听所有接收到的K线消息
4. 检查消息处理过程中是否有异常（包括 normalize_kline 和 insert_market_klines）
5. 记录详细的统计信息（成功、失败、异常等）
6. 测试所有interval（1m, 5m, 15m, 1h, 4h, 1d, 1w）

配置说明：
- TEST_SYMBOLS: 测试用的symbol列表，默认只测试2个symbol，便于快速验证
- 可以通过修改 TEST_SYMBOLS 列表来调整测试的symbol
"""
import asyncio
import json
import logging
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

# ============================================================================
# 测试配置
# ============================================================================

# 测试用的symbol列表（默认只测试2个symbol，便于快速验证）
# 可以通过修改此列表来调整测试的symbol
TEST_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT"
]

# 等待接收消息的时间（秒）
# 根据interval不同，消息频率也不同（1m最快，1w最慢）
MESSAGE_WAIT_TIME = 120

# 统计信息打印间隔（秒）
STATS_CHECK_INTERVAL = 10

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
# K线消息测试处理器
# ============================================================================

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
                    "[测试] ✅ [消息处理] 步骤1/2: 规范化完成 %s %s (耗时: %.3fs)",
                    symbol, interval, normalize_duration
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


# ============================================================================
# 模拟HTTP请求处理
# ============================================================================

async def simulate_add_symbols_request(
    kline_manager,
    symbols: List[str],
    per_symbol_timeout: int = 30
) -> Dict[str, Any]:
    """模拟 HTTP POST /symbols/add 请求的处理逻辑。
    
    该方法模拟 DataAgentCommandHandler._handle_add_symbols() 的核心逻辑，
    但不通过HTTP服务器，直接调用 kline_manager 的方法。
    
    Args:
        kline_manager: DataAgentKlineManager 实例
        symbols: 要添加的symbol列表
        per_symbol_timeout: 每个symbol的超时时间（秒）
    
    Returns:
        包含处理结果的字典，格式与HTTP响应相同
    """
    request_start_time = datetime.now(timezone.utc)
    
    logger.info(
        "[测试] 📥 [模拟请求] 模拟批量添加symbol请求 (时间: %s)",
        request_start_time.isoformat()
    )
    logger.info(
        "[测试] 📋 [模拟请求] 开始处理 %s 个symbol: %s",
        len(symbols), symbols
    )
    
    results = []
    failed_symbols = []
    
    for idx, symbol in enumerate(symbols):
        symbol_start_time = datetime.now(timezone.utc)
        symbol_clean = symbol.upper().strip()
        
        if not symbol_clean:
            logger.warning("[测试] ⚠️  [模拟请求] 跳过空symbol: %s", symbol)
            continue
        
        logger.info(
            "[测试] 🔨 [模拟请求] 开始处理 symbol %s (%s/%s) (时间: %s)",
            symbol_clean, idx + 1, len(symbols), symbol_start_time.isoformat()
        )
        
        try:
            # 直接调用 kline_manager.add_symbol_streams()，模拟HTTP请求中的逻辑
            result = await asyncio.wait_for(
                kline_manager.add_symbol_streams(symbol_clean),
                timeout=per_symbol_timeout
            )
            symbol_duration = (datetime.now(timezone.utc) - symbol_start_time).total_seconds()
            
            logger.info(
                "[测试] ✅ [模拟请求] symbol %s 处理完成 (耗时: %.3fs, 结果: %s)",
                symbol_clean, symbol_duration, result
            )
            
            results.append({
                "symbol": symbol_clean,
                **result
            })
        except asyncio.TimeoutError:
            symbol_duration = (datetime.now(timezone.utc) - symbol_start_time).total_seconds()
            logger.error(
                "[测试] ❌ [模拟请求] symbol %s 处理超时 (耗时: %.3fs, 超时设置: %ss)",
                symbol_clean, symbol_duration, per_symbol_timeout
            )
            failed_symbols.append(symbol_clean)
            results.append({
                "symbol": symbol_clean,
                "success_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "total_count": 7,
                "error": f"Timeout after {per_symbol_timeout}s"
            })
        except Exception as e:
            symbol_duration = (datetime.now(timezone.utc) - symbol_start_time).total_seconds()
            logger.error(
                "[测试] ❌ [模拟请求] symbol %s 处理失败 (耗时: %.3fs): %s",
                symbol_clean, symbol_duration, e, exc_info=True
            )
            failed_symbols.append(symbol_clean)
            results.append({
                "symbol": symbol_clean,
                "success_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "total_count": 7,
                "error": str(e)
            })
    
    # 获取当前连接状态
    logger.info("[测试] 📊 [模拟请求] 获取当前连接状态...")
    try:
        status = await kline_manager.get_connection_status()
        logger.info(
            "[测试] ✅ [模拟请求] 连接状态获取成功: %s",
            status
        )
    except Exception as e:
        logger.error(
            "[测试] ⚠️  [模拟请求] 获取连接状态失败: %s",
            e, exc_info=True
        )
        status = {
            "connection_count": 0,
            "symbols": []
        }
    
    request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
    
    response_data = {
        "status": "ok" if not failed_symbols else "partial",
        "results": results,
        "current_status": status,
        "summary": {
            "total_symbols": len(symbols),
            "success_count": len(results) - len(failed_symbols),
            "failed_count": len(failed_symbols),
            "failed_symbols": failed_symbols,
            "duration_seconds": round(request_duration, 3)
        }
    }
    
    logger.info(
        "[测试] 📤 [模拟请求] 请求处理完成 (总耗时: %.3fs, 状态: %s)",
        request_duration, response_data["status"]
    )
    
    return response_data


# ============================================================================
# 主测试函数
# ============================================================================

async def test_data_agent_kline_processing(
    test_symbols: Optional[List[str]] = None,
    message_wait_time: Optional[int] = None
):
    """测试 data_agent 接收构建symbol监听命令请求后的代码执行逻辑。
    
    Args:
        test_symbols: 测试用的symbol列表，如果为None则使用默认配置 TEST_SYMBOLS
        message_wait_time: 等待接收消息的时间（秒），如果为None则使用默认配置 MESSAGE_WAIT_TIME
    """
    from data.data_agent import DataAgentKlineManager, KLINE_INTERVALS
    from common.database_clickhouse import ClickHouseDatabase
    
    # 使用配置参数或默认值
    symbols = test_symbols if test_symbols is not None else TEST_SYMBOLS
    wait_time = message_wait_time if message_wait_time is not None else MESSAGE_WAIT_TIME
    
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
    
    logger.info("[测试] 📋 测试配置:")
    logger.info("[测试]   - Symbol数量: %s", len(symbols))
    logger.info("[测试]   - Symbol列表: %s", symbols)
    logger.info("[测试]   - Interval数量: %s", len(KLINE_INTERVALS))
    logger.info("[测试]   - Interval列表: %s", KLINE_INTERVALS)
    logger.info("[测试]   - 总连接数: %s", len(symbols) * len(KLINE_INTERVALS))
    logger.info("[测试]   - 等待消息时间: %s秒", wait_time)
    logger.info("=" * 80)
    
    try:
        # 步骤1: 模拟 HTTP POST /symbols/add 请求，批量添加所有symbol的所有interval
        logger.info("[测试] 🔨 [步骤1] 模拟批量添加symbol K线流请求...")
        logger.info("[测试] 🔨 [步骤1] 模拟 HTTP POST /symbols/add 请求")
        
        add_response = await simulate_add_symbols_request(
            kline_manager,
            symbols,
            per_symbol_timeout=30
        )
        
        logger.info("[测试] ✅ [步骤1] 批量添加完成")
        logger.info("[测试] 📊 [步骤1] 添加结果汇总:")
        logger.info("[测试]   - 状态: %s", add_response["status"])
        logger.info("[测试]   - 成功: %s 个", add_response["summary"]["success_count"])
        logger.info("[测试]   - 失败: %s 个", add_response["summary"]["failed_count"])
        logger.info("[测试]   - 总耗时: %.3fs", add_response["summary"]["duration_seconds"])
        logger.info("[测试]   - 当前连接数: %s", add_response["current_status"].get("connection_count", 0))
        logger.info("[测试]   - 当前symbol数: %s", len(add_response["current_status"].get("symbols", [])))
        
        if add_response["summary"]["failed_count"] > 0:
            logger.warning(
                "[测试] ⚠️  [步骤1] 有 %s 个symbol添加失败: %s",
                add_response["summary"]["failed_count"],
                add_response["summary"]["failed_symbols"]
            )
        
        logger.info("=" * 80)
        
        # 步骤2: 等待接收K线数据消息
        logger.info("[测试] 📨 [步骤2] 开始监听K线数据消息...")
        logger.info("[测试] 📨 [步骤2] 等待时间: %s秒（每个symbol-interval组合至少接收1条消息）", wait_time)
        
        # 每10秒打印一次统计信息
        elapsed = 0
        
        while elapsed < wait_time:
            await asyncio.sleep(STATS_CHECK_INTERVAL)
            elapsed += STATS_CHECK_INTERVAL
            
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
            for symbol in symbols[:5]:  # 只验证前5个symbol
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


# ============================================================================
# 主入口
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='测试 data_agent K线消息处理逻辑')
    parser.add_argument(
        '--symbols',
        type=str,
        nargs='+',
        default=None,
        help='测试用的symbol列表，例如: --symbols BTCUSDT ETHUSDT BNBUSDT'
    )
    parser.add_argument(
        '--wait-time',
        type=int,
        default=None,
        help='等待接收消息的时间（秒），默认使用配置中的 MESSAGE_WAIT_TIME'
    )
    
    args = parser.parse_args()
    
    # 如果通过命令行参数指定了symbols，则使用命令行参数
    test_symbols = args.symbols if args.symbols else TEST_SYMBOLS
    wait_time = args.wait_time if args.wait_time else MESSAGE_WAIT_TIME
    
    try:
        asyncio.run(test_data_agent_kline_processing(
            test_symbols=test_symbols,
            message_wait_time=wait_time
        ))
    except KeyboardInterrupt:
        logger.info("[测试] ⚠️  测试被用户中断")
    except Exception as e:
        logger.error("[测试] ❌ 测试执行失败: %s", e, exc_info=True)
