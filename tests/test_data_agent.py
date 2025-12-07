"""
测试 data_agent 接收构建symbol监听命令请求后的代码执行逻辑

测试内容：
1. 模拟 HTTP POST /symbols/add 请求，批量添加symbol的所有interval K线流
2. 验证连接是否正常建立
3. 同时等待所有interval收到完结的K线消息（x=True）
4. 每个interval收到完结的K线消息后立即关闭该监听
5. 检查消息处理过程中是否有异常（包括 normalize_kline 和 insert_market_klines）
6. 记录详细的统计信息（成功、失败、异常等）
7. 测试所有interval（1m, 5m, 15m, 1h, 4h, 1d, 1w）

测试逻辑（与 websocket_klines.py 一致）：
- 同时构建所有interval的监听（使用 data_agent 封装的SDK）
- 每个interval持续等待直到收到完结的K线消息（x=True），无超时限制
- 收到完结的K线消息后立即关闭该interval的监听
- 所有interval都完成后测试结束

配置说明：
- TEST_SYMBOLS: 测试用的symbol列表，默认只测试1个symbol，便于快速验证
- 可以通过修改 TEST_SYMBOLS 列表来调整测试的symbol
"""
import asyncio
import json
import logging
import traceback
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set

# ============================================================================
# 测试配置
# ============================================================================

# 测试用的symbol列表（默认只测试2个symbol，便于快速验证）
# 可以通过修改此列表来调整测试的symbol
TEST_SYMBOLS = [
    "BTCUSDT"
]

# 等待接收消息的时间（秒）
# 注意：实际测试中会持续等待直到收到完结的K线消息（x=True），不设置超时
# 此配置仅用于其他场景
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
# 辅助函数
# ============================================================================

def print_kline_data(kline_data: Any, symbol: str, interval: str):
    """打印K线数据用于测试验证（参考 websocket_klines.py 的格式）
    
    Args:
        kline_data: K线数据对象或字典
        symbol: 交易对符号
        interval: 时间间隔
    """
    # 计算日期标签
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    
    # 提取K线数据
    k_data = None
    kline_date = None
    
    try:
        # 处理SDK返回的对象，而不是字典
        if hasattr(kline_data, 'k'):
            # 这是SDK返回的对象
            k_data = kline_data.k
            kline_date = datetime.fromtimestamp(k_data.t / 1000).date()
        elif isinstance(kline_data, dict) and 'k' in kline_data:
            # 字典格式
            k_data = kline_data['k']
            if isinstance(k_data, dict):
                kline_date = datetime.fromtimestamp(k_data['t'] / 1000).date()
            elif hasattr(k_data, 't'):
                kline_date = datetime.fromtimestamp(k_data.t / 1000).date()
        else:
            # 尝试从规范化后的数据中提取
            if isinstance(kline_data, dict) and 'kline_start_time' in kline_data:
                kline_date = datetime.fromisoformat(kline_data['kline_start_time'].replace('Z', '+00:00')).date()
        
        # 判断日期标签
        if kline_date:
            if kline_date == today.date():
                day_label = "今天"
            elif kline_date == yesterday.date():
                day_label = "昨天"
            else:
                day_label = str(kline_date)
        else:
            day_label = "未知日期"
        
        logger.info("=" * 80)
        logger.info("=== %s %s - %s K线数据 ===", symbol, interval, day_label)
        logger.info("=" * 80)
        
        # 打印K线数据
        if hasattr(k_data, 't'):
            # SDK对象格式
            logger.info("开盘时间: %s", datetime.fromtimestamp(k_data.t / 1000).strftime('%Y-%m-%d %H:%M:%S'))
            logger.info("收盘时间: %s", datetime.fromtimestamp(k_data.T / 1000).strftime('%Y-%m-%d %H:%M:%S'))
            logger.info("开盘价: %s", k_data.o)
            logger.info("最高价: %s", k_data.h)
            logger.info("最低价: %s", k_data.l)
            logger.info("收盘价: %s", k_data.c)
            logger.info("成交量: %s", k_data.v)
            logger.info("成交笔数: %s", k_data.n)
            logger.info("是否完结: %s", k_data.x)
        elif isinstance(k_data, dict):
            # 字典格式
            logger.info("开盘时间: %s", datetime.fromtimestamp(k_data['t'] / 1000).strftime('%Y-%m-%d %H:%M:%S'))
            logger.info("收盘时间: %s", datetime.fromtimestamp(k_data['T'] / 1000).strftime('%Y-%m-%d %H:%M:%S'))
            logger.info("开盘价: %s", k_data.get('o', 'N/A'))
            logger.info("最高价: %s", k_data.get('h', 'N/A'))
            logger.info("最低价: %s", k_data.get('l', 'N/A'))
            logger.info("收盘价: %s", k_data.get('c', 'N/A'))
            logger.info("成交量: %s", k_data.get('v', 'N/A'))
            logger.info("成交笔数: %s", k_data.get('n', 'N/A'))
            logger.info("是否完结: %s", k_data.get('x', 'N/A'))
        else:
            # 如果无法提取K线数据，打印原始数据
            logger.info("原始数据: %s", json.dumps(kline_data, indent=2, ensure_ascii=False, default=str))
        
        logger.info("=" * 80)
    except Exception as e:
        logger.warning("[测试] ⚠️  [打印K线数据] 无法解析K线数据: %s", e)
        logger.info("原始数据: %s", json.dumps(kline_data, indent=2, ensure_ascii=False, default=str))


# ============================================================================
# K线消息测试处理器
# ============================================================================

class KlineMessageTestHandler:
    """K线消息测试处理器，用于捕获和统计消息处理结果。"""
    
    def __init__(self):
        # 统计信息
        self.stats = {
            "total_messages": 0,  # 总消息数（包括所有类型的消息）
            "success_messages": 0,  # 成功处理的消息数（完结的K线）
            "failed_messages": 0,  # 处理失败的消息数（真正的错误）
            "skipped_messages": 0,  # 跳过的消息数（空消息、未完结K线等，不算错误）
            "normalize_errors": 0,  # normalize_kline 错误数（无效消息格式）
            "insert_errors": 0,  # insert_market_klines 错误数
            "other_errors": 0,  # 其他错误数
        }
        
        # 按symbol和interval统计
        self.by_symbol_interval: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        
        # 错误详情
        self.errors: List[Dict] = []
        
        # 成功处理的消息样本（每个symbol-interval组合保留最新的一条）
        self.sample_messages: Dict[str, Dict] = {}
        
        # 记录每个symbol-interval组合是否已收到消息
        # key: (symbol, interval), value: asyncio.Event
        self.message_received_events: Dict[tuple, asyncio.Event] = {}
        
        # 记录每个symbol-interval组合收到的第一条消息（用于打印）
        self.first_messages: Dict[tuple, Dict] = {}
        
        # 记录每个symbol的interval完成状态
        # key: symbol, value: set of completed intervals
        self.symbol_completed_intervals: Dict[str, Set[str]] = defaultdict(set)
        
        # 锁（用于线程安全）
        self._lock = asyncio.Lock()
    
    def register_symbol_interval(self, symbol: str, interval: str):
        """注册一个symbol-interval组合，创建等待事件。"""
        key = (symbol.upper(), interval)
        if key not in self.message_received_events:
            self.message_received_events[key] = asyncio.Event()
    
    async def wait_for_message(self, symbol: str, interval: str, timeout: Optional[int] = 60) -> bool:
        """等待指定symbol-interval组合收到消息。
        
        Args:
            symbol: 交易对符号
            interval: 时间间隔
            timeout: 超时时间（秒），如果为None则一直等待
        
        Returns:
            如果收到消息返回True，超时返回False
        """
        key = (symbol.upper(), interval)
        event = self.message_received_events.get(key)
        if event is None:
            return False
        
        try:
            if timeout is None:
                # 不设置超时，一直等待
                await event.wait()
                return True
            else:
                await asyncio.wait_for(event.wait(), timeout=timeout)
                return True
        except asyncio.TimeoutError:
            return False
    
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
        key_tuple = (symbol.upper(), interval)
        
        # 检查是否是第一条消息
        is_first_message = False
        async with self._lock:
            self.stats["total_messages"] += 1
            self.by_symbol_interval[symbol][interval] += 1
            if key_tuple not in self.first_messages:
                is_first_message = True
                self.first_messages[key_tuple] = {
                    "symbol": symbol,
                    "interval": interval,
                    "message": message,
                    "timestamp": message_start_time.isoformat()
                }
        
        try:
            # 步骤0: 检查消息类型（不打印，只用于内部判断）
            # 尝试将消息转换为可检查的格式
            message_dict = None
            try:
                if hasattr(message, "model_dump"):
                    message_dict = message.model_dump()
                elif hasattr(message, "__dict__"):
                    message_dict = message.__dict__
                elif isinstance(message, dict):
                    message_dict = message
                else:
                    message_dict = {"raw_message": str(message)}
            except Exception as e:
                # 如果序列化失败，创建一个基本的字典
                message_dict = {"raw_message": str(message)[:500], "serialization_error": str(e)}
            
            # 步骤0.1: 检查是否是订阅确认消息（如 {'result': None, 'id': '...'}）
            # 订阅确认消息不打印，直接跳过
            try:
                if message_dict is not None and isinstance(message_dict, dict):
                    # 检查是否是订阅确认消息格式
                    if "result" in message_dict and "id" in message_dict:
                        # 订阅确认消息不算在统计中，只是跳过（不打印）
                        logger.debug(
                            "[测试] ⏭️  [消息处理] 跳过订阅确认消息 %s %s (result=%s, id=%s)",
                            symbol, interval, message_dict.get("result"), message_dict.get("id")
                        )
                        return
            except Exception as e:
                logger.debug("[测试] ⚠️  [消息类型] 检查订阅确认消息时出错: %s", e)
            
            # 步骤0.2: 检查空消息
            if message is None:
                async with self._lock:
                    self.stats["skipped_messages"] += 1
                logger.debug(
                    "[测试] ⏭️  [消息处理] 跳过空消息 %s %s",
                    symbol, interval
                )
                # 空消息不算错误，只是跳过
                return
            
            # 步骤1: 测试 normalize_kline
            from market.market_streams import _normalize_kline
            
            try:
                normalized = _normalize_kline(message)
                
                if normalized is None:
                    # normalize_kline 返回 None 可能是以下情况：
                    # 1. 空消息（已在上方检查）
                    # 2. 未完结的K线（x=False）- 这是正常的，应该跳过
                    # 3. 无效的消息格式 - 这是错误
                    
                    # 检查是否是未完结的K线（正常情况）
                    is_incomplete_kline = False
                    try:
                        # 尝试提取 kline 对象检查 x 字段
                        if hasattr(message, "model_dump"):
                            data = message.model_dump()
                        elif hasattr(message, "__dict__"):
                            data = message.__dict__
                        elif isinstance(message, dict):
                            data = message
                        else:
                            data = {}
                        
                        kline_obj = data.get("k")
                        if kline_obj:
                            if hasattr(kline_obj, "model_dump"):
                                k = kline_obj.model_dump()
                            elif hasattr(kline_obj, "__dict__"):
                                k = kline_obj.__dict__
                            elif isinstance(kline_obj, dict):
                                k = kline_obj
                            else:
                                k = {}
                            
                            is_closed = k.get("x") or k.get("is_closed", False)
                            if not is_closed:
                                # 这是未完结的K线，正常跳过，不算错误（不打印）
                                is_incomplete_kline = True
                                async with self._lock:
                                    self.stats["skipped_messages"] += 1
                                logger.debug(
                                    "[测试] ⏭️  [消息处理] 跳过未完结K线 %s %s (x=False)",
                                    symbol, interval
                                )
                    except Exception:
                        # 如果无法检查，假设是无效消息格式
                        pass
                    
                    if not is_incomplete_kline:
                        # 这是真正的错误（无效消息格式）
                        async with self._lock:
                            self.stats["normalize_errors"] += 1
                            self.stats["failed_messages"] += 1
                            self.errors.append({
                                "symbol": symbol,
                                "interval": interval,
                                "step": "normalize_kline",
                                "error": "normalize_kline returned None (invalid message format)",
                                "message_preview": str(message)[:200] if message else None,
                                "timestamp": message_start_time.isoformat()
                            })
                        
                        logger.warning(
                            "[测试] ⚠️  [消息处理] normalize_kline 返回 None（无效消息格式） %s %s",
                            symbol, interval
                        )
                    # 无论是否未完结的K线，都不继续处理
                    return
            except Exception as e:
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
                    "[测试] ❌ [消息处理] normalize_kline 异常 %s %s: %s",
                    symbol, interval, e, exc_info=True
                )
                return
            
            # 步骤2: 测试 insert_market_klines
            try:
                # 调用原始处理器的数据库插入逻辑
                await original_handler(symbol, interval, message)
                
                async with self._lock:
                    self.stats["success_messages"] += 1
                    # 保存成功处理的消息样本
                    self.sample_messages[key] = {
                        "symbol": symbol,
                        "interval": interval,
                        "normalized_data": normalized,
                        "timestamp": message_start_time.isoformat()
                    }
                
                # 如果是第一条消息（完结的K线），打印K线数据（参考 websocket_klines.py 格式）
                if is_first_message:
                    logger.info("[测试] ✅ [收到完结K线] %s %s 收到第一条完结的K线消息 (x=True)", symbol, interval)
                    # 使用与 websocket_klines.py 相同的格式打印K线数据
                    print_kline_data(message, symbol, interval)
                    logger.info("[测试] ✅ [消息处理] 这是完结的K线")
                
                # 只有成功处理的完结K线才标记为已收到
                # 注意：不立即关闭监听，等待该symbol的所有interval都收到完结消息后再统一关闭
                event = self.message_received_events.get(key_tuple)
                if event and not event.is_set():
                    event.set()
                    # 记录该interval已完成
                    async with self._lock:
                        self.symbol_completed_intervals[symbol.upper()].add(interval)
                    logger.debug(
                        "[测试] ✅ [消息处理] %s %s 已收到完结的K线，标记为完成（等待所有interval完成后再关闭）",
                        symbol, interval
                    )
                
            except Exception as e:
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
                    "[测试] ❌ [消息处理] insert_market_klines 异常 %s %s: %s",
                    symbol, interval, e, exc_info=True
                )
        except Exception as e:
            # 捕获其他未预期的异常
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
                "[测试] ❌ [消息处理] 未预期的异常 %s %s: %s",
                symbol, interval, e, exc_info=True
            )
            # 错误情况下不设置事件，继续等待
    
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
        logger.info("[测试报告] 成功处理: %s (完结的K线)", self.stats["success_messages"])
        logger.info("[测试报告] 跳过消息: %s (空消息、未完结K线等，正常行为)", self.stats["skipped_messages"])
        logger.info("[测试报告] 处理失败: %s (真正的错误)", self.stats["failed_messages"])
        logger.info("[测试报告]   - normalize_kline 错误: %s (无效消息格式)", self.stats["normalize_errors"])
        logger.info("[测试报告]   - insert_market_klines 错误: %s", self.stats["insert_errors"])
        logger.info("[测试报告]   - 其他错误: %s", self.stats["other_errors"])
        logger.info("=" * 80)
        
        if self.stats["total_messages"] > 0:
            # 成功率 = 成功处理的消息数 / (总消息数 - 跳过的消息数)
            processable_messages = self.stats["total_messages"] - self.stats["skipped_messages"]
            if processable_messages > 0:
                success_rate = (self.stats["success_messages"] / processable_messages) * 100
                logger.info("[测试报告] 成功率: %.2f%% (基于可处理消息数: %s)", 
                           success_rate, processable_messages)
            else:
                logger.info("[测试报告] 成功率: N/A (所有消息都被跳过)")
        
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
    logger.info("[测试]   - 等待模式: 持续等待直到收到完结的K线（x=True），无超时限制")
    logger.info("[测试]   - 处理逻辑: 只处理完结的K线，未完结的K线会被跳过")
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
        
        # 步骤2: 同时等待所有symbol-interval组合收到完结的K线消息，所有interval都收到后再统一关闭
        logger.info("[测试] 📨 [步骤2] 开始同时监听所有K线数据消息...")
        
        # 注册所有symbol-interval组合
        for symbol in symbols:
            for interval in KLINE_INTERVALS:
                test_handler.register_symbol_interval(symbol, interval)
        
        total_combinations = len(symbols) * len(KLINE_INTERVALS)
        logger.info("[测试] 📨 [步骤2] 总共需要等待 %s 个symbol-interval组合收到完结的K线消息", total_combinations)
        logger.info("[测试] 📨 [步骤2] 等待模式: 持续等待直到收到完结的K线（x=True），无超时限制")
        logger.info("[测试] 📨 [步骤2] 关闭策略: 等待每个symbol的所有interval都收到完结消息后，统一关闭该symbol的所有订阅")
        logger.info("=" * 80)
        
        # 定义单个symbol-interval的等待任务（不关闭，只等待）
        async def wait_for_interval(symbol: str, interval: str) -> Dict[str, Any]:
            """等待指定symbol-interval收到完结的K线消息（不关闭监听）。
            
            Args:
                symbol: 交易对符号
                interval: 时间间隔
            
            Returns:
                包含处理结果的字典
            """
            logger.info(
                "[测试] 📨 [步骤2] [%s %s] 开始等待完结的K线消息（持续等待，无超时）...",
                symbol, interval
            )
            
            try:
                # 持续等待直到收到消息（不设置超时，一直等待）
                received = await test_handler.wait_for_message(symbol, interval, timeout=None)
                
                if received:
                    logger.info(
                        "[测试] ✅ [步骤2] [%s %s] 已收到完结的K线消息",
                        symbol, interval
                    )
                    return {
                        "symbol": symbol,
                        "interval": interval,
                        "success": True,
                        "message_received": True
                    }
                else:
                    logger.warning(
                        "[测试] ⚠️  [步骤2] [%s %s] 未收到消息（不应该发生，因为timeout=None）",
                        symbol, interval
                    )
                    return {
                        "symbol": symbol,
                        "interval": interval,
                        "success": False,
                        "message_received": False,
                        "error": "未收到消息"
                    }
            except Exception as e:
                logger.error(
                    "[测试] ❌ [步骤2] [%s %s] 等待消息时出错: %s",
                    symbol, interval, e, exc_info=True
                )
                return {
                    "symbol": symbol,
                    "interval": interval,
                    "success": False,
                    "message_received": False,
                    "error": str(e)
                }
        
        # 同时创建所有symbol-interval的等待任务
        logger.info("[测试] 🚀 [步骤2] 同时创建 %s 个等待任务...", total_combinations)
        tasks = []
        for symbol in symbols:
            for interval in KLINE_INTERVALS:
                task = asyncio.create_task(wait_for_interval(symbol, interval))
                tasks.append(task)
                # 控制任务创建频率，避免过快
                await asyncio.sleep(0.01)
        
        logger.info("[测试] ✅ [步骤2] 所有 %s 个等待任务已创建，开始并发等待...", len(tasks))
        logger.info("=" * 80)
        
        # 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 统计结果并检查每个symbol的所有interval是否都已完成
        completed_count = 0
        success_count = 0
        failed_count = 0
        
        for result in results:
            if isinstance(result, Exception):
                failed_count += 1
                logger.error(
                    "[测试] ❌ [步骤2] 任务执行异常: %s",
                    result, exc_info=True
                )
            elif isinstance(result, dict):
                completed_count += 1
                if result.get("success", False):
                    success_count += 1
                else:
                    failed_count += 1
        
        logger.info("=" * 80)
        logger.info("[测试] ✅ [步骤2] 所有interval都已收到完结消息")
        logger.info("[测试] 📊 [步骤2] 结果统计:")
        logger.info("[测试]   - 总任务数: %s", total_combinations)
        logger.info("[测试]   - 完成数: %s", completed_count)
        logger.info("[测试]   - 成功数: %s", success_count)
        logger.info("[测试]   - 失败数: %s", failed_count)
        logger.info("=" * 80)
        
        # 步骤2.1: 检查每个symbol的所有interval是否都已完成，完成后统一关闭该symbol的所有订阅
        logger.info("[测试] 🔌 [步骤2.1] 开始检查并关闭已完成的symbol订阅...")
        for symbol in symbols:
            symbol_upper = symbol.upper()
            completed_intervals = test_handler.symbol_completed_intervals.get(symbol_upper, set())
            expected_intervals = set(KLINE_INTERVALS)
            
            logger.info(
                "[测试] 📊 [步骤2.1] [%s] 已完成interval: %s/%s",
                symbol_upper, len(completed_intervals), len(expected_intervals)
            )
            
            # 检查是否所有interval都已完成
            if completed_intervals == expected_intervals:
                logger.info(
                    "[测试] ✅ [步骤2.1] [%s] 所有interval都已完成，开始关闭该symbol的所有订阅...",
                    symbol_upper
                )
                
                # 关闭该symbol的所有interval订阅
                close_start = datetime.now(timezone.utc)
                close_success_count = 0
                close_failed_count = 0
                
                for interval in KLINE_INTERVALS:
                    try:
                        success = await kline_manager.remove_stream(symbol_upper, interval)
                        if success:
                            close_success_count += 1
                            logger.debug(
                                "[测试] ✅ [步骤2.1] [%s %s] 订阅已关闭",
                                symbol_upper, interval
                            )
                        else:
                            close_failed_count += 1
                            logger.warning(
                                "[测试] ⚠️  [步骤2.1] [%s %s] 订阅关闭失败",
                                symbol_upper, interval
                            )
                    except Exception as e:
                        close_failed_count += 1
                        logger.error(
                            "[测试] ❌ [步骤2.1] [%s %s] 订阅关闭异常: %s",
                            symbol_upper, interval, e, exc_info=True
                        )
                
                close_duration = (datetime.now(timezone.utc) - close_start).total_seconds()
                logger.info(
                    "[测试] ✅ [步骤2.1] [%s] 所有订阅关闭完成 (耗时: %.3fs, 成功: %s, 失败: %s)",
                    symbol_upper, close_duration, close_success_count, close_failed_count
                )
            else:
                missing_intervals = expected_intervals - completed_intervals
                logger.warning(
                    "[测试] ⚠️  [步骤2.1] [%s] 还有 %s 个interval未完成: %s",
                    symbol_upper, len(missing_intervals), missing_intervals
                )
        
        logger.info("=" * 80)
        logger.info("[测试] ✅ [步骤2] 所有监听处理完成")
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
