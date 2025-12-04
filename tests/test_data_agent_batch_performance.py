"""
Data Agent 批量添加 Symbol 性能测试

测试 data_agent 接收批量添加 symbol 指令时的性能表现：
- 批量下发15个symbol一组
- 记录总共时长和详细日志
- 记录返回信息
- 使用 HTTP 请求（模拟 curl）方式测试

手动测试命令（curl）：
# 测试单个 symbol
curl -X POST http://localhost:9999/symbols/add \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["BTCUSDT"]}'

# 测试批量添加15个symbol
curl -X POST http://localhost:9999/symbols/add \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT", "XRPUSDT", "DOGEUSDT", "DOTUSDT", "MATICUSDT", "AVAXUSDT", "LINKUSDT", "UNIUSDT", "LTCUSDT", "ATOMUSDT", "ETCUSDT"]}'

# 测试获取连接状态
curl http://localhost:9999/status

# 测试获取连接列表
curl http://localhost:9999/connections/list

# 测试健康检查
curl http://localhost:9999/ping
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("[警告] requests 库未安装，将使用 subprocess 调用 curl")

logger = logging.getLogger(__name__)


class DataAgentBatchPerformanceTest:
    """Data Agent 批量添加 Symbol 性能测试类。"""
    
    def __init__(
        self,
        agent_host: str = 'localhost',
        agent_port: int = 9999,
        use_curl: bool = False
    ):
        """
        初始化测试类。
        
        Args:
            agent_host: agent 的主机地址
            agent_port: agent 的端口号
            use_curl: 是否使用 curl 命令（True）或 requests 库（False）
        """
        self.agent_host = agent_host
        self.agent_port = agent_port
        self.base_url = f"http://{agent_host}:{agent_port}"
        self.use_curl = use_curl or not HAS_REQUESTS
        
        # 测试结果记录
        self.test_results: List[Dict[str, Any]] = []
        
        logger.info("=" * 80)
        logger.info("[性能测试] Data Agent 批量添加 Symbol 性能测试")
        logger.info("=" * 80)
        logger.info("[性能测试] Agent 地址: %s:%s", agent_host, agent_port)
        logger.info("[性能测试] 使用方式: %s", "curl" if self.use_curl else "requests")
        logger.info("=" * 80)
    
    def _send_request_curl(self, method: str, path: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """使用 curl 命令发送 HTTP 请求。"""
        url = f"{self.base_url}{path}"
        
        cmd = ['curl', '-s', '-w', '\n%{http_code}\n%{time_total}', '-X', method]
        
        if method == 'POST' and data:
            cmd.extend(['-H', 'Content-Type: application/json'])
            cmd.extend(['-d', json.dumps(data)])
        
        cmd.append(url)
        
        logger.debug("[性能测试] 执行 curl 命令: %s", ' '.join(cmd))
        
        try:
            start_time = time.time()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5分钟超时
            )
            duration = time.time() - start_time
            
            if result.returncode != 0:
                logger.error("[性能测试] curl 命令执行失败: %s", result.stderr)
                return {
                    "success": False,
                    "error": f"curl failed: {result.stderr}",
                    "duration": duration
                }
            
            # 解析 curl 输出
            # curl -w 的输出格式：响应体\nHTTP状态码\n总时间
            output_lines = result.stdout.strip().split('\n')
            if len(output_lines) >= 3:
                response_body = '\n'.join(output_lines[:-2])
                http_code = output_lines[-2]
                curl_time = float(output_lines[-1])
            else:
                response_body = result.stdout
                http_code = "0"
                curl_time = duration
            
            try:
                response_data = json.loads(response_body) if response_body else {}
            except json.JSONDecodeError:
                response_data = {"raw_response": response_body}
            
            return {
                "success": int(http_code) == 200,
                "http_code": int(http_code) if http_code.isdigit() else 0,
                "response": response_data,
                "duration": curl_time,
                "raw_output": response_body
            }
        except subprocess.TimeoutExpired:
            logger.error("[性能测试] curl 命令超时")
            return {
                "success": False,
                "error": "Request timeout",
                "duration": 300.0
            }
        except Exception as e:
            logger.error("[性能测试] curl 命令执行异常: %s", e, exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "duration": 0.0
            }
    
    def _send_request_requests(self, method: str, path: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """使用 requests 库发送 HTTP 请求。"""
        url = f"{self.base_url}{path}"
        
        start_time = time.time()
        try:
            if method == 'GET':
                response = requests.get(url, timeout=300)
            elif method == 'POST':
                response = requests.post(
                    url,
                    json=data,
                    headers={'Content-Type': 'application/json'},
                    timeout=300
                )
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            duration = time.time() - start_time
            
            try:
                response_data = response.json()
            except json.JSONDecodeError:
                response_data = {"raw_response": response.text}
            
            return {
                "success": response.status_code == 200,
                "http_code": response.status_code,
                "response": response_data,
                "duration": duration,
                "raw_output": response.text
            }
        except requests.Timeout:
            duration = time.time() - start_time
            logger.error("[性能测试] 请求超时 (耗时: %.3fs)", duration)
            return {
                "success": False,
                "error": "Request timeout",
                "duration": duration
            }
        except Exception as e:
            duration = time.time() - start_time
            logger.error("[性能测试] 请求异常 (耗时: %.3fs): %s", duration, e, exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "duration": duration
            }
    
    def send_request(self, method: str, path: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """发送 HTTP 请求（统一接口）。"""
        if self.use_curl:
            return self._send_request_curl(method, path, data)
        else:
            return self._send_request_requests(method, path, data)
    
    def test_ping(self) -> Dict[str, Any]:
        """测试健康检查接口。"""
        logger.info("[性能测试] 🔍 [测试1] 健康检查 (ping)")
        test_start_time = datetime.now(timezone.utc)
        
        result = self.send_request('GET', '/ping')
        
        test_duration = (datetime.now(timezone.utc) - test_start_time).total_seconds()
        
        logger.info(
            "[性能测试] ✅ [测试1] 健康检查完成 (耗时: %.3fs, HTTP状态: %s, 成功: %s)",
            test_duration, result.get('http_code'), result.get('success')
        )
        
        if result.get('response'):
            logger.debug("[性能测试] 响应内容: %s", json.dumps(result['response'], ensure_ascii=False, indent=2))
        
        return {
            "test_name": "ping",
            "start_time": test_start_time.isoformat(),
            "duration": test_duration,
            "result": result
        }
    
    def test_get_status(self) -> Dict[str, Any]:
        """测试获取连接状态接口。"""
        logger.info("[性能测试] 🔍 [测试2] 获取连接状态")
        test_start_time = datetime.now(timezone.utc)
        
        result = self.send_request('GET', '/status')
        
        test_duration = (datetime.now(timezone.utc) - test_start_time).total_seconds()
        
        logger.info(
            "[性能测试] ✅ [测试2] 获取连接状态完成 (耗时: %.3fs, HTTP状态: %s, 成功: %s)",
            test_duration, result.get('http_code'), result.get('success')
        )
        
        if result.get('response'):
            status = result['response']
            logger.info(
                "[性能测试] 📊 [状态] 连接数: %s, Symbol数: %s",
                status.get('connection_count', 0),
                len(status.get('symbols', []))
            )
            logger.debug("[性能测试] 完整状态: %s", json.dumps(status, ensure_ascii=False, indent=2))
        
        return {
            "test_name": "get_status",
            "start_time": test_start_time.isoformat(),
            "duration": test_duration,
            "result": result
        }
    
    def test_batch_add_symbols(self, symbols: List[str], batch_name: str = "batch") -> Dict[str, Any]:
        """测试批量添加 symbol。
        
        Args:
            symbols: symbol 列表
            batch_name: 批次名称（用于日志标识）
        
        Returns:
            测试结果字典
        """
        logger.info("=" * 80)
        logger.info("[性能测试] 🔨 [批量测试] 开始批量添加 %s 个 symbol (批次: %s)", len(symbols), batch_name)
        logger.info("[性能测试] 📋 [批量测试] Symbol列表: %s", symbols)
        logger.info("=" * 80)
        
        test_start_time = datetime.now(timezone.utc)
        
        # 发送批量添加请求
        logger.info("[性能测试] 📤 [批量测试] 发送批量添加请求...")
        request_start_time = datetime.now(timezone.utc)
        
        result = self.send_request('POST', '/symbols/add', {"symbols": symbols})
        
        request_duration = (datetime.now(timezone.utc) - request_start_time).total_seconds()
        test_duration = (datetime.now(timezone.utc) - test_start_time).total_seconds()
        
        logger.info("=" * 80)
        logger.info("[性能测试] ✅ [批量测试] 批量添加请求完成")
        logger.info("[性能测试] ⏱️  [批量测试] 请求耗时: %.3fs", request_duration)
        logger.info("[性能测试] ⏱️  [批量测试] 总耗时: %.3fs", test_duration)
        logger.info("[性能测试] 📊 [批量测试] HTTP状态码: %s", result.get('http_code'))
        logger.info("[性能测试] 📊 [批量测试] 请求成功: %s", result.get('success'))
        
        if result.get('success'):
            response = result.get('response', {})
            
            # 解析响应数据
            status = response.get('status', 'unknown')
            results = response.get('results', [])
            current_status = response.get('current_status', {})
            summary = response.get('summary', {})
            
            logger.info("[性能测试] 📊 [批量测试] 响应状态: %s", status)
            logger.info(
                "[性能测试] 📊 [批量测试] 处理结果: 总数=%s, 成功=%s, 失败=%s, 跳过=%s",
                summary.get('total_symbols', 0),
                summary.get('success_count', 0),
                summary.get('failed_count', 0),
                len([r for r in results if r.get('skipped_count', 0) > 0])
            )
            
            # 详细统计每个 symbol 的处理结果
            success_symbols = []
            failed_symbols = []
            skipped_symbols = []
            
            for item in results:
                symbol = item.get('symbol', '')
                success_count = item.get('success_count', 0)
                failed_count = item.get('failed_count', 0)
                skipped_count = item.get('skipped_count', 0)
                error = item.get('error')
                
                if error:
                    failed_symbols.append({
                        "symbol": symbol,
                        "error": error
                    })
                elif skipped_count == 7:  # 所有 interval 都跳过
                    skipped_symbols.append(symbol)
                elif success_count > 0:
                    success_symbols.append({
                        "symbol": symbol,
                        "success_count": success_count,
                        "failed_count": failed_count,
                        "skipped_count": skipped_count
                    })
            
            logger.info("[性能测试] ✅ [批量测试] 成功处理的 Symbol (%s个):", len(success_symbols))
            for item in success_symbols[:10]:  # 只显示前10个
                logger.info(
                    "[性能测试]   - %s: 成功=%s, 失败=%s, 跳过=%s",
                    item['symbol'],
                    item['success_count'],
                    item['failed_count'],
                    item['skipped_count']
                )
            if len(success_symbols) > 10:
                logger.info("[性能测试]   ... 还有 %s 个成功处理的 symbol", len(success_symbols) - 10)
            
            if skipped_symbols:
                logger.info("[性能测试] ⏭️  [批量测试] 跳过的 Symbol (%s个): %s", len(skipped_symbols), skipped_symbols[:10])
            
            if failed_symbols:
                logger.info("[性能测试] ❌ [批量测试] 失败的 Symbol (%s个):", len(failed_symbols))
                for item in failed_symbols[:10]:  # 只显示前10个
                    logger.error(
                        "[性能测试]   - %s: %s",
                        item['symbol'],
                        item['error']
                    )
                if len(failed_symbols) > 10:
                    logger.error("[性能测试]   ... 还有 %s 个失败的 symbol", len(failed_symbols) - 10)
            
            # 显示当前连接状态
            if current_status:
                logger.info(
                    "[性能测试] 📊 [批量测试] 当前连接状态: 连接数=%s, Symbol数=%s",
                    current_status.get('connection_count', 0),
                    len(current_status.get('symbols', []))
                )
            
            # 显示每个 symbol 的详细处理时间
            logger.info("[性能测试] ⏱️  [批量测试] 每个 Symbol 的处理时间:")
            for item in results[:15]:  # 显示前15个
                symbol = item.get('symbol', '')
                # 注意：这里无法获取每个 symbol 的实际处理时间，因为响应中没有这个信息
                logger.debug(
                    "[性能测试]   - %s: 成功=%s, 失败=%s, 跳过=%s",
                    symbol,
                    item.get('success_count', 0),
                    item.get('failed_count', 0),
                    item.get('skipped_count', 0)
                )
            
            logger.info("=" * 80)
        else:
            error_msg = result.get('error', 'Unknown error')
            logger.error("[性能测试] ❌ [批量测试] 批量添加失败: %s", error_msg)
            if result.get('raw_output'):
                logger.error("[性能测试] ❌ [批量测试] 原始响应: %s", result['raw_output'])
            logger.info("=" * 80)
        
        return {
            "test_name": f"batch_add_symbols_{batch_name}",
            "symbols": symbols,
            "symbol_count": len(symbols),
            "start_time": test_start_time.isoformat(),
            "request_duration": request_duration,
            "total_duration": test_duration,
            "result": result
        }
    
    def test_get_connection_list(self) -> Dict[str, Any]:
        """测试获取连接列表接口。"""
        logger.info("[性能测试] 🔍 [测试3] 获取连接列表")
        test_start_time = datetime.now(timezone.utc)
        
        result = self.send_request('GET', '/connections/list')
        
        test_duration = (datetime.now(timezone.utc) - test_start_time).total_seconds()
        
        logger.info(
            "[性能测试] ✅ [测试3] 获取连接列表完成 (耗时: %.3fs, HTTP状态: %s, 成功: %s)",
            test_duration, result.get('http_code'), result.get('success')
        )
        
        if result.get('response'):
            response_data = result['response']
            connections = response_data.get('connections', [])
            count = response_data.get('count', 0)
            logger.info(
                "[性能测试] 📊 [连接列表] 连接总数: %s",
                count
            )
            logger.debug("[性能测试] 连接列表 (前10个): %s", json.dumps(connections[:10], ensure_ascii=False, indent=2))
        
        return {
            "test_name": "get_connection_list",
            "start_time": test_start_time.isoformat(),
            "duration": test_duration,
            "result": result
        }
    
    def run_full_test(self, test_symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """运行完整的性能测试套件。
        
        Args:
            test_symbols: 测试用的 symbol 列表，如果为 None 则使用默认列表
        
        Returns:
            完整的测试结果
        """
        if test_symbols is None:
            # 默认测试15个symbol
            test_symbols = [
                "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT",
                "XRPUSDT", "DOGEUSDT", "DOTUSDT", "MATICUSDT", "AVAXUSDT",
                "LINKUSDT", "UNIUSDT", "LTCUSDT", "ATOMUSDT", "ETCUSDT"
            ]
        
        full_test_start_time = datetime.now(timezone.utc)
        test_results = []
        
        logger.info("=" * 80)
        logger.info("[性能测试] 🚀 开始完整性能测试套件")
        logger.info("=" * 80)
        
        # 1. 健康检查
        ping_result = self.test_ping()
        test_results.append(ping_result)
        
        # 2. 获取初始状态
        initial_status_result = self.test_get_status()
        test_results.append(initial_status_result)
        
        # 3. 批量添加 symbol
        batch_result = self.test_batch_add_symbols(test_symbols, "main_batch")
        test_results.append(batch_result)
        
        # 4. 获取添加后的状态
        final_status_result = self.test_get_status()
        test_results.append(final_status_result)
        
        # 5. 获取连接列表
        connection_list_result = self.test_get_connection_list()
        test_results.append(connection_list_result)
        
        full_test_duration = (datetime.now(timezone.utc) - full_test_start_time).total_seconds()
        
        logger.info("=" * 80)
        logger.info("[性能测试] ✅ 完整性能测试套件完成")
        logger.info("[性能测试] ⏱️  总耗时: %.3fs", full_test_duration)
        logger.info("=" * 80)
        
        # 生成测试报告
        self._generate_report(test_results, full_test_duration)
        
        return {
            "full_test_start_time": full_test_start_time.isoformat(),
            "full_test_duration": full_test_duration,
            "test_results": test_results
        }
    
    def _generate_report(self, test_results: List[Dict[str, Any]], total_duration: float) -> None:
        """生成测试报告。"""
        logger.info("=" * 80)
        logger.info("[性能测试] 📊 测试报告")
        logger.info("=" * 80)
        
        for idx, result in enumerate(test_results, 1):
            test_name = result.get('test_name', 'unknown')
            duration = result.get('duration') or result.get('total_duration', 0)
            success = result.get('result', {}).get('success', False)
            
            logger.info(
                "[性能测试] [%s] %s: 耗时=%.3fs, 成功=%s",
                idx, test_name, duration, success
            )
            
            # 如果是批量添加测试，显示详细信息
            if 'batch_add_symbols' in test_name:
                symbol_count = result.get('symbol_count', 0)
                request_duration = result.get('request_duration', 0)
                logger.info(
                    "[性能测试]   - Symbol数量: %s",
                    symbol_count
                )
                logger.info(
                    "[性能测试]   - 请求耗时: %.3fs",
                    request_duration
                )
                logger.info(
                    "[性能测试]   - 平均每个Symbol耗时: %.3fs",
                    request_duration / symbol_count if symbol_count > 0 else 0
                )
        
        logger.info("=" * 80)
        logger.info("[性能测试] ⏱️  总测试耗时: %.3fs", total_duration)
        logger.info("=" * 80)


def main():
    """主函数：运行性能测试。"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Data Agent 批量添加 Symbol 性能测试')
    parser.add_argument('--host', default='localhost', help='Agent 主机地址 (默认: localhost)')
    parser.add_argument('--port', type=int, default=9999, help='Agent 端口号 (默认: 9999)')
    parser.add_argument('--use-curl', action='store_true', help='使用 curl 命令而不是 requests 库')
    parser.add_argument('--symbols', nargs='+', help='要测试的 symbol 列表（空格分隔）')
    parser.add_argument('--batch-size', type=int, default=15, help='每批测试的 symbol 数量 (默认: 15)')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='日志级别 (默认: INFO)')
    
    args = parser.parse_args()
    
    # 配置日志
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 创建测试实例
    tester = DataAgentBatchPerformanceTest(
        agent_host=args.host,
        agent_port=args.port,
        use_curl=args.use_curl
    )
    
    # 准备测试 symbol 列表
    if args.symbols:
        test_symbols = args.symbols
    else:
        # 默认测试15个symbol
        test_symbols = [
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT",
            "XRPUSDT", "DOGEUSDT", "DOTUSDT", "MATICUSDT", "AVAXUSDT",
            "LINKUSDT", "UNIUSDT", "LTCUSDT", "ATOMUSDT", "ETCUSDT"
        ]
    
    # 如果指定了 batch_size，分批测试
    if args.batch_size and len(test_symbols) > args.batch_size:
        logger.info("[性能测试] 📦 将 %s 个 symbol 分成 %s 批进行测试", len(test_symbols), args.batch_size)
        for i in range(0, len(test_symbols), args.batch_size):
            batch_symbols = test_symbols[i:i + args.batch_size]
            batch_num = i // args.batch_size + 1
            logger.info("[性能测试] 📦 测试批次 %s: %s 个 symbol", batch_num, len(batch_symbols))
            tester.test_batch_add_symbols(batch_symbols, f"batch_{batch_num}")
    else:
        # 运行完整测试套件
        tester.run_full_test(test_symbols)


if __name__ == "__main__":
    main()

