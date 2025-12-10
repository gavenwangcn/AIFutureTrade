"""
Data Agent 分步测试类

用于测试 data_agent 中每个步骤的独立功能，便于定位问题。
每个步骤都可以单独测试，支持单个 symbol 或 symbol 列表。
"""
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from data.data_agent import DataAgentKlineManager, KLINE_INTERVALS
from common.database_mysql import MySQLDatabase

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def make_json_serializable(obj: Any) -> Any:
    """将对象转换为可JSON序列化的格式。
    
    递归处理字典、列表等，将不可序列化的对象转换为字符串表示。
    特别处理 connection 和 stream 对象，移除它们但保留类型和ID信息。
    
    Args:
        obj: 要转换的对象
    
    Returns:
        可JSON序列化的对象
    """
    if obj is None:
        return None
    elif isinstance(obj, (str, int, float, bool)):
        return obj
    elif isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            # 跳过 connection 和 stream 对象，但保留类型和ID信息
            if k in ('connection', 'stream'):
                # 这些对象已经在结果中有 connection_type/stream_type 和 connection_id/stream_id
                # 所以可以跳过，或者转换为字符串表示
                try:
                    type_name = type(v).__name__ if v else None
                    obj_id = id(v) if v else None
                    result[k] = f"<{type_name} object at {hex(obj_id) if obj_id else 'None'}>" if v else None
                except Exception:
                    result[k] = None
            else:
                result[k] = make_json_serializable(v)
        return result
    elif isinstance(obj, (list, tuple)):
        return [make_json_serializable(item) for item in obj]
    elif isinstance(obj, set):
        return list(make_json_serializable(item) for item in obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    else:
        # 对于其他对象，尝试获取类型名和ID
        try:
            # 尝试获取对象的类型名
            type_name = type(obj).__name__
            obj_id = id(obj)
            return f"<{type_name} object at {hex(obj_id)}>"
        except Exception:
            return str(obj)


class DataAgentStepByStepTester:
    """Data Agent 分步测试类，每个步骤都可以单独测试。"""
    
    def __init__(self, max_symbols: int = 100):
        """初始化测试类。
        
        Args:
            max_symbols: 最大symbol数量
        """
        self.db = MySQLDatabase()
        self.kline_manager = DataAgentKlineManager(db=self.db, max_symbols=max_symbols)
        self.test_results: List[Dict[str, Any]] = []
        
        logger.info("=" * 80)
        logger.info("[分步测试] Data Agent 分步测试类已初始化")
        logger.info("=" * 80)
    
    async def test_step1_init_client(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """测试步骤1: 初始化客户端。
        
        Args:
            symbols: 可选的symbol列表（用于测试多个symbol时的客户端初始化）
        
        Returns:
            测试结果字典
        """
        logger.info("=" * 80)
        logger.info("[分步测试] 🔧 [步骤1测试] 初始化客户端")
        logger.info("=" * 80)
        
        test_start_time = datetime.now(timezone.utc)
        results = []
        
        # 如果提供了symbol列表，测试多次初始化（应该只初始化一次）
        if symbols:
            logger.info("[分步测试] 📋 [步骤1测试] 测试 %s 个symbol的客户端初始化", len(symbols))
            for idx, symbol in enumerate(symbols, 1):
                logger.info(
                    "[分步测试] 🔧 [步骤1测试] 测试 %s/%s: %s",
                    idx, len(symbols), symbol
                )
                result = await self.kline_manager.step1_init_client()
                results.append({
                    "symbol": symbol,
                    "result": result
                })
                logger.info(
                    "[分步测试] ✅ [步骤1测试] %s 完成: 成功=%s, 耗时=%.3fs, 客户端类型=%s",
                    symbol, result["success"], result["duration"], result.get("client_type")
                )
        else:
            # 单个测试
            logger.info("[分步测试] 🔧 [步骤1测试] 单个测试")
            result = await self.kline_manager.step1_init_client()
            results.append({
                "symbol": None,
                "result": result
            })
            logger.info(
                "[分步测试] ✅ [步骤1测试] 完成: 成功=%s, 耗时=%.3fs, 客户端类型=%s",
                result["success"], result["duration"], result.get("client_type")
            )
        
        test_duration = (datetime.now(timezone.utc) - test_start_time).total_seconds()
        
        success_count = sum(1 for r in results if r["result"]["success"])
        total_count = len(results)
        
        logger.info("=" * 80)
        logger.info("[分步测试] 📊 [步骤1测试] 测试完成: 成功=%s/%s, 总耗时=%.3fs", success_count, total_count, test_duration)
        logger.info("=" * 80)
        
        return {
            "step": "step1_init_client",
            "start_time": test_start_time.isoformat(),
            "duration": test_duration,
            "success_count": success_count,
            "total_count": total_count,
            "results": results
        }
    
    async def test_step2_rate_limit_check(
        self, symbols: Optional[List[str]] = None, intervals: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """测试步骤2: 检查订阅频率限制。
        
        Args:
            symbols: 可选的symbol列表
            intervals: 可选的interval列表
        
        Returns:
            测试结果字典
        """
        logger.info("=" * 80)
        logger.info("[分步测试] ⏱️  [步骤2测试] 检查订阅频率限制")
        logger.info("=" * 80)
        
        test_start_time = datetime.now(timezone.utc)
        results = []
        
        if symbols and intervals:
            # 测试多个symbol和interval的组合
            logger.info(
                "[分步测试] 📋 [步骤2测试] 测试 %s 个symbol × %s 个interval = %s 个组合",
                len(symbols), len(intervals), len(symbols) * len(intervals)
            )
            total_combinations = len(symbols) * len(intervals)
            for idx, symbol in enumerate(symbols, 1):
                for interval in intervals:
                    logger.info(
                        "[分步测试] ⏱️  [步骤2测试] 测试 %s/%s: %s %s",
                        (idx - 1) * len(intervals) + intervals.index(interval) + 1,
                        total_combinations, symbol, interval
                    )
                    result = await self.kline_manager.step2_rate_limit_check()
                    results.append({
                        "symbol": symbol,
                        "interval": interval,
                        "result": result
                    })
                    logger.info(
                        "[分步测试] ✅ [步骤2测试] %s %s 完成: 成功=%s, 耗时=%.3fs, 等待=%s, 等待时间=%.3fs",
                        symbol, interval, result["success"], result["duration"],
                        result.get("waited"), result.get("wait_time")
                    )
        else:
            # 单个测试
            logger.info("[分步测试] ⏱️  [步骤2测试] 单个测试")
            result = await self.kline_manager.step2_rate_limit_check()
            results.append({
                "symbol": None,
                "interval": None,
                "result": result
            })
            logger.info(
                "[分步测试] ✅ [步骤2测试] 完成: 成功=%s, 耗时=%.3fs, 等待=%s, 等待时间=%.3fs",
                result["success"], result["duration"], result.get("waited"), result.get("wait_time")
            )
        
        test_duration = (datetime.now(timezone.utc) - test_start_time).total_seconds()
        
        success_count = sum(1 for r in results if r["result"]["success"])
        total_count = len(results)
        waited_count = sum(1 for r in results if r["result"].get("waited", False))
        
        logger.info("=" * 80)
        logger.info(
            "[分步测试] 📊 [步骤2测试] 测试完成: 成功=%s/%s, 等待次数=%s, 总耗时=%.3fs",
            success_count, total_count, waited_count, test_duration
        )
        logger.info("=" * 80)
        
        return {
            "step": "step2_rate_limit_check",
            "start_time": test_start_time.isoformat(),
            "duration": test_duration,
            "success_count": success_count,
            "total_count": total_count,
            "waited_count": waited_count,
            "results": results
        }
    
    async def test_step3_create_connection(
        self, symbols: Optional[List[str]] = None, intervals: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """测试步骤3: 创建WebSocket连接。
        
        Args:
            symbols: 可选的symbol列表
            intervals: 可选的interval列表
        
        Returns:
            测试结果字典
        """
        logger.info("=" * 80)
        logger.info("[分步测试] 🔌 [步骤3测试] 创建WebSocket连接")
        logger.info("=" * 80)
        
        # 确保客户端已初始化
        await self.kline_manager.step1_init_client()
        
        test_start_time = datetime.now(timezone.utc)
        results = []
        connections = []
        
        if symbols and intervals:
            # 测试多个symbol和interval的组合
            logger.info(
                "[分步测试] 📋 [步骤3测试] 测试 %s 个symbol × %s 个interval = %s 个组合",
                len(symbols), len(intervals), len(symbols) * len(intervals)
            )
            total_combinations = len(symbols) * len(intervals)
            for idx, symbol in enumerate(symbols, 1):
                for interval in intervals:
                    logger.info(
                        "[分步测试] 🔌 [步骤3测试] 测试 %s/%s: %s %s",
                        (idx - 1) * len(intervals) + intervals.index(interval) + 1,
                        total_combinations, symbol, interval
                    )
                    result = await self.kline_manager.step3_create_connection()
                    results.append({
                        "symbol": symbol,
                        "interval": interval,
                        "result": result
                    })
                    if result["success"] and result.get("connection"):
                        connections.append(result["connection"])
                    logger.info(
                        "[分步测试] ✅ [步骤3测试] %s %s 完成: 成功=%s, 耗时=%.3fs, 连接类型=%s",
                        symbol, interval, result["success"], result["duration"],
                        result.get("connection_type")
                    )
        else:
            # 单个测试
            logger.info("[分步测试] 🔌 [步骤3测试] 单个测试")
            result = await self.kline_manager.step3_create_connection()
            results.append({
                "symbol": None,
                "interval": None,
                "result": result
            })
            if result["success"] and result.get("connection"):
                connections.append(result["connection"])
            logger.info(
                "[分步测试] ✅ [步骤3测试] 完成: 成功=%s, 耗时=%.3fs, 连接类型=%s",
                result["success"], result["duration"], result.get("connection_type")
            )
        
        # 清理连接
        logger.info("[分步测试] 🧹 [步骤3测试] 清理 %s 个连接...", len(connections))
        for conn in connections:
            try:
                await conn.close_connection()
            except Exception as e:
                logger.warning("[分步测试] ⚠️  [步骤3测试] 清理连接失败: %s", e)
        
        test_duration = (datetime.now(timezone.utc) - test_start_time).total_seconds()
        
        success_count = sum(1 for r in results if r["result"]["success"])
        total_count = len(results)
        
        logger.info("=" * 80)
        logger.info(
            "[分步测试] 📊 [步骤3测试] 测试完成: 成功=%s/%s, 总耗时=%.3fs",
            success_count, total_count, test_duration
        )
        logger.info("=" * 80)
        
        return {
            "step": "step3_create_connection",
            "start_time": test_start_time.isoformat(),
            "duration": test_duration,
            "success_count": success_count,
            "total_count": total_count,
            "results": results
        }
    
    async def test_step5_subscribe_kline_stream(
        self, symbols: Optional[List[str]] = None, intervals: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """测试步骤5: 订阅K线流（包含步骤3和步骤5）。
        
        Args:
            symbols: 可选的symbol列表
            intervals: 可选的interval列表
        
        Returns:
            测试结果字典
        """
        logger.info("=" * 80)
        logger.info("[分步测试] 📡 [步骤5测试] 订阅K线流")
        logger.info("=" * 80)
        
        # 确保客户端已初始化
        await self.kline_manager.step1_init_client()
        
        test_start_time = datetime.now(timezone.utc)
        results = []
        connections = []
        streams = []
        
        if symbols and intervals:
            # 测试多个symbol和interval的组合
            logger.info(
                "[分步测试] 📋 [步骤5测试] 测试 %s 个symbol × %s 个interval = %s 个组合",
                len(symbols), len(intervals), len(symbols) * len(intervals)
            )
            total_combinations = len(symbols) * len(intervals)
            for idx, symbol in enumerate(symbols, 1):
                for interval in intervals:
                    logger.info(
                        "[分步测试] 📡 [步骤5测试] 测试 %s/%s: %s %s",
                        (idx - 1) * len(intervals) + intervals.index(interval) + 1,
                        total_combinations, symbol, interval
                    )
                    
                    # 步骤2: 频率限制检查
                    await self.kline_manager.step2_rate_limit_check()
                    
                    # 步骤3: 创建连接
                    step3_result = await self.kline_manager.step3_create_connection()
                    if not step3_result["success"]:
                        results.append({
                            "symbol": symbol,
                            "interval": interval,
                            "step3_result": step3_result,
                            "step5_result": None,
                            "success": False
                        })
                        continue
                    
                    connection = step3_result["connection"]
                    if connection:
                        connections.append(connection)
                    
                    # 步骤5: 订阅流
                    step5_result = await self.kline_manager.step5_subscribe_kline_stream(
                        connection, symbol, interval
                    )
                    results.append({
                        "symbol": symbol,
                        "interval": interval,
                        "step3_result": step3_result,
                        "step5_result": step5_result,
                        "success": step5_result["success"]
                    })
                    
                    if step5_result["success"] and step5_result.get("stream"):
                        streams.append(step5_result["stream"])
                    
                    logger.info(
                        "[分步测试] ✅ [步骤5测试] %s %s 完成: 成功=%s, 步骤3耗时=%.3fs, 步骤5耗时=%.3fs",
                        symbol, interval, step5_result["success"],
                        step3_result["duration"], step5_result["duration"]
                    )
        else:
            # 单个测试
            logger.info("[分步测试] 📡 [步骤5测试] 单个测试")
            
            # 步骤2: 频率限制检查
            await self.kline_manager.step2_rate_limit_check()
            
            # 步骤3: 创建连接
            step3_result = await self.kline_manager.step3_create_connection()
            if step3_result["success"] and step3_result.get("connection"):
                connections.append(step3_result["connection"])
                connection = step3_result["connection"]
                
                # 步骤5: 订阅流
                step5_result = await self.kline_manager.step5_subscribe_kline_stream(
                    connection, "BTCUSDT", "1m"
                )
                results.append({
                    "symbol": "BTCUSDT",
                    "interval": "1m",
                    "step3_result": step3_result,
                    "step5_result": step5_result,
                    "success": step5_result["success"]
                })
                
                if step5_result["success"] and step5_result.get("stream"):
                    streams.append(step5_result["stream"])
        
        # 清理连接和流
        logger.info("[分步测试] 🧹 [步骤5测试] 清理 %s 个连接和 %s 个流...", len(connections), len(streams))
        for conn in connections:
            try:
                await conn.close_connection()
            except Exception as e:
                logger.warning("[分步测试] ⚠️  [步骤5测试] 清理连接失败: %s", e)
        
        test_duration = (datetime.now(timezone.utc) - test_start_time).total_seconds()
        
        success_count = sum(1 for r in results if r.get("success", False))
        total_count = len(results)
        
        logger.info("=" * 80)
        logger.info(
            "[分步测试] 📊 [步骤5测试] 测试完成: 成功=%s/%s, 总耗时=%.3fs",
            success_count, total_count, test_duration
        )
        logger.info("=" * 80)
        
        return {
            "step": "step5_subscribe_kline_stream",
            "start_time": test_start_time.isoformat(),
            "duration": test_duration,
            "success_count": success_count,
            "total_count": total_count,
            "results": results
        }
    
    async def test_full_flow_for_one_symbol(
        self, symbol: str, intervals: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """测试一个symbol的完整流程（所有7个interval）。
        
        Args:
            symbol: 交易对符号
            intervals: 可选的interval列表，如果为None则使用所有interval
        
        Returns:
            测试结果字典
        """
        if intervals is None:
            intervals = KLINE_INTERVALS
        
        logger.info("=" * 80)
        logger.info("[分步测试] 🔄 [完整流程测试] 测试 %s 的完整流程 (%s 个interval)", symbol, len(intervals))
        logger.info("=" * 80)
        
        test_start_time = datetime.now(timezone.utc)
        results = []
        
        for idx, interval in enumerate(intervals, 1):
            logger.info(
                "[分步测试] 🔄 [完整流程测试] 处理 %s %s (%s/%s)",
                symbol, interval, idx, len(intervals)
            )
            
            interval_start_time = datetime.now(timezone.utc)
            step_results = {}
            
            # 步骤1: 初始化客户端
            step1_result = await self.kline_manager.step1_init_client()
            step_results["step1"] = step1_result
            if not step1_result["success"]:
                results.append({
                    "symbol": symbol,
                    "interval": interval,
                    "step_results": step_results,
                    "success": False,
                    "error": "Step1 failed"
                })
                continue
            
            # 步骤2: 频率限制检查
            step2_result = await self.kline_manager.step2_rate_limit_check()
            step_results["step2"] = step2_result
            
            # 步骤3: 创建连接
            step3_result = await self.kline_manager.step3_create_connection()
            step_results["step3"] = step3_result
            if not step3_result["success"]:
                results.append({
                    "symbol": symbol,
                    "interval": interval,
                    "step_results": step_results,
                    "success": False,
                    "error": "Step3 failed"
                })
                continue
            
            connection = step3_result["connection"]
            
            # 步骤4: 注册连接错误处理器
            step4_result = await self.kline_manager.step4_register_connection_error_handler(
                connection, symbol, interval
            )
            step_results["step4"] = step4_result
            
            # 步骤5: 订阅流
            step5_result = await self.kline_manager.step5_subscribe_kline_stream(
                connection, symbol, interval
            )
            step_results["step5"] = step5_result
            if not step5_result["success"]:
                # 清理连接
                try:
                    await connection.close_connection()
                except Exception:
                    pass
                results.append({
                    "symbol": symbol,
                    "interval": interval,
                    "step_results": step_results,
                    "success": False,
                    "error": "Step5 failed"
                })
                continue
            
            stream = step5_result["stream"]
            
            # 步骤6: 注册消息处理器
            step6_result = await self.kline_manager.step6_register_message_handler(
                stream, symbol, interval
            )
            step_results["step6"] = step6_result
            
            # 步骤7: 保存连接
            step7_result = await self.kline_manager.step7_save_connection(
                symbol, interval, connection, stream
            )
            step_results["step7"] = step7_result
            
            interval_duration = (datetime.now(timezone.utc) - interval_start_time).total_seconds()
            
            success = all([
                step1_result["success"],
                step3_result["success"],
                step5_result["success"],
                step6_result["success"],
                step7_result["success"]
            ])
            
            results.append({
                "symbol": symbol,
                "interval": interval,
                "step_results": step_results,
                "success": success,
                "duration": interval_duration
            })
            
            logger.info(
                "[分步测试] ✅ [完整流程测试] %s %s 完成: 成功=%s, 耗时=%.3fs",
                symbol, interval, success, interval_duration
            )
        
        test_duration = (datetime.now(timezone.utc) - test_start_time).total_seconds()
        
        success_count = sum(1 for r in results if r.get("success", False))
        total_count = len(results)
        
        logger.info("=" * 80)
        logger.info(
            "[分步测试] 📊 [完整流程测试] 测试完成: 成功=%s/%s, 总耗时=%.3fs",
            success_count, total_count, test_duration
        )
        logger.info("=" * 80)
        
        return {
            "step": "full_flow_for_one_symbol",
            "symbol": symbol,
            "start_time": test_start_time.isoformat(),
            "duration": test_duration,
            "success_count": success_count,
            "total_count": total_count,
            "results": results
        }
    
    async def cleanup(self):
        """清理资源。"""
        logger.info("[分步测试] 🧹 清理资源...")
        await self.kline_manager.cleanup_all()
        logger.info("[分步测试] ✅ 资源清理完成")


# ============================================================================
# Main 函数 - 每个步骤都可以单独测试
# ============================================================================

async def main_step1():
    """测试步骤1: 初始化客户端。"""
    tester = DataAgentStepByStepTester()
    try:
        # 测试单个初始化
        result = await tester.test_step1_init_client()
        serializable_result = make_json_serializable(result)
        print(json.dumps(serializable_result, indent=2, ensure_ascii=False))
        
        # 测试多个symbol的初始化（应该只初始化一次）
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        result = await tester.test_step1_init_client(symbols=symbols)
        serializable_result = make_json_serializable(result)
        print(json.dumps(serializable_result, indent=2, ensure_ascii=False))
    finally:
        await tester.cleanup()


async def main_step2():
    """测试步骤2: 检查订阅频率限制。"""
    tester = DataAgentStepByStepTester()
    try:
        # 测试单个频率检查
        result = await tester.test_step2_rate_limit_check()
        serializable_result = make_json_serializable(result)
        print(json.dumps(serializable_result, indent=2, ensure_ascii=False))
        
        # 测试多个symbol和interval的组合（测试频率限制）
        symbols = ["BTCUSDT", "ETHUSDT"]
        intervals = ["1m", "5m"]
        result = await tester.test_step2_rate_limit_check(symbols=symbols, intervals=intervals)
        serializable_result = make_json_serializable(result)
        print(json.dumps(serializable_result, indent=2, ensure_ascii=False))
    finally:
        await tester.cleanup()


async def main_step3():
    """测试步骤3: 创建WebSocket连接。"""
    tester = DataAgentStepByStepTester()
    try:
        # 测试单个连接创建
        result = await tester.test_step3_create_connection()
        serializable_result = make_json_serializable(result)
        print(json.dumps(serializable_result, indent=2, ensure_ascii=False))
        
        # 测试多个连接创建
        symbols = ["BTCUSDT", "ETHUSDT"]
        intervals = ["1m", "5m"]
        result = await tester.test_step3_create_connection(symbols=symbols, intervals=intervals)
        serializable_result = make_json_serializable(result)
        print(json.dumps(serializable_result, indent=2, ensure_ascii=False))
    finally:
        await tester.cleanup()


async def main_step5():
    """测试步骤5: 订阅K线流。"""
    tester = DataAgentStepByStepTester()
    try:
        # 测试单个订阅
        result = await tester.test_step5_subscribe_kline_stream()
        serializable_result = make_json_serializable(result)
        print(json.dumps(serializable_result, indent=2, ensure_ascii=False))
        
        # 测试多个订阅
        symbols = ["BTCUSDT", "ETHUSDT"]
        intervals = ["1m", "5m"]
        result = await tester.test_step5_subscribe_kline_stream(symbols=symbols, intervals=intervals)
        serializable_result = make_json_serializable(result)
        print(json.dumps(serializable_result, indent=2, ensure_ascii=False))
    finally:
        await tester.cleanup()


async def main_full_flow():
    """测试完整流程: 一个symbol的所有interval。"""
    tester = DataAgentStepByStepTester()
    try:
        # 测试单个symbol的完整流程
        result = await tester.test_full_flow_for_one_symbol("BTCUSDT")
        serializable_result = make_json_serializable(result)
        print(json.dumps(serializable_result, indent=2, ensure_ascii=False))
    finally:
        await tester.cleanup()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Data Agent 分步测试')
    parser.add_argument(
        '--step',
        type=str,
        choices=['1', '2', '3', '5', 'full'],
        help='要测试的步骤: 1=初始化客户端, 2=频率限制检查, 3=创建连接, 5=订阅流, full=完整流程'
    )
    
    args = parser.parse_args()
    
    if args.step == '1':
        asyncio.run(main_step1())
    elif args.step == '2':
        asyncio.run(main_step2())
    elif args.step == '3':
        asyncio.run(main_step3())
    elif args.step == '5':
        asyncio.run(main_step5())
    elif args.step == 'full':
        asyncio.run(main_full_flow())
    else:
        print("请指定要测试的步骤: --step 1|2|3|5|full")
        print("示例: python tests/test_data_agent_step_by_step.py --step 1")
        print("示例: python tests/test_data_agent_step_by_step.py --step full")

