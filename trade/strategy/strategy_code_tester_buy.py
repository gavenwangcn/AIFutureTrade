"""
Strategy Code Tester - 买入策略代码测试器

本模块提供 StrategyCodeTesterBuy 类，用于验证 AI 生成的买入策略代码是否符合要求。
主要用于在添加新买入策略时，验证生成的 strategy_code 是否正确。

主要功能：
1. 语法检查：验证策略代码的语法正确性
2. 继承检查：验证是否继承自 StrategyBaseBuy
3. 方法检查：验证是否实现了必要的方法
4. 签名检查：验证方法签名是否正确
5. 执行测试：使用模拟数据测试代码执行是否成功
6. 生成测试报告：返回详细的测试结果和错误信息

使用场景：
- 添加新买入策略时，验证 AI 生成的 strategy_code
- 确保策略代码可以被 StrategyCodeExecutor 正确执行
"""
import ast
import logging
from typing import Dict, List, Optional, Tuple
import traceback
from trade.strategy.strategy_template_buy import StrategyBaseBuy
from trade.strategy.strategy_code_executor import StrategyCodeExecutor, strip_markdown_code_block

logger = logging.getLogger(__name__)


class StrategyCodeTesterBuy:
    """
    买入策略代码测试器
    
    用于验证 AI 生成的买入策略代码是否符合要求，确保代码可以被 StrategyCodeExecutor 正确执行。
    
    测试内容：
    - 语法正确性：代码语法是否正确
    - 继承关系：是否继承自 StrategyBaseBuy
    - 方法实现：是否实现了必要的方法（execute_buy_decision）
    - 方法签名：方法参数数量是否正确
    - 执行能力：使用模拟数据测试代码是否能正常执行
    - 返回值格式：仅支持 Dict[str, List[Dict]]，每个 symbol 的 value 必须为决策列表（不兼容单条 dict）
    
    使用示例：
        # 在添加买入策略时验证 AI 生成的代码
        tester = StrategyCodeTesterBuy()
        result = tester.test_strategy_code(strategy_code, strategy_name="新买入策略")
        
        if result['passed']:
            # 测试通过，可以保存到数据库
            print("✓ 买入策略代码验证通过，可以保存")
        else:
            # 测试失败，需要重新生成或修复
            print("✗ 买入策略代码验证失败:")
            for error in result['errors']:
                print(f"  - {error}")
    """
    
    def __init__(self, use_real_data: bool = False):
        """
        初始化测试器

        Args:
            use_real_data: 是否使用真实数据进行测试（默认False使用mock数据）
                          True: 从币安API和数据库获取真实数据
                          False: 使用预定义的mock数据（更快，不依赖外部服务）
        """
        self.code_executor = StrategyCodeExecutor(preload_talib=True)
        self.use_real_data = use_real_data
    
    def test_strategy_code(
        self,
        strategy_code: str,
        strategy_name: str = "测试买入策略"
    ) -> Dict:
        """
        测试买入策略代码
        
        全面测试买入策略代码是否符合要求，包括语法、继承、方法实现和执行能力。
        
        Args:
            strategy_code: 策略代码字符串
            strategy_name: 策略名称（用于日志）
        
        Returns:
            Dict: 测试结果，包含：
                - passed: bool - 是否通过所有测试
                - errors: List[str] - 错误列表
                - warnings: List[str] - 警告列表
                - test_results: Dict - 各项测试结果详情
        """
        errors = []
        warnings = []
        test_results = {}
        
        # 剥离可能的 Markdown 代码块（AI 可能输出 ```python ... ```），确保语法/类/继承等检查使用纯代码
        strategy_code = strip_markdown_code_block(strategy_code)
        
        logger.info(f"[StrategyCodeTesterBuy] 开始测试买入策略代码: {strategy_name}")
        
        # ============ 测试1: 语法检查 ============
        logger.debug(f"[StrategyCodeTesterBuy] [测试1] 语法检查...")
        syntax_result = self._test_syntax(strategy_code)
        test_results['syntax'] = syntax_result
        if not syntax_result['passed']:
            errors.extend(syntax_result['errors'])
        else:
            logger.debug(f"[StrategyCodeTesterBuy] [测试1] ✓ 语法检查通过")
        
        # ============ 测试2: 导入检查 ============
        logger.debug(f"[StrategyCodeTesterBuy] [测试2] 导入检查...")
        import_result = self._test_imports(strategy_code)
        test_results['imports'] = import_result
        if not import_result['passed']:
            errors.extend(import_result['errors'])
        warnings.extend(import_result['warnings'])
        if import_result['passed']:
            logger.debug(f"[StrategyCodeTesterBuy] [测试2] ✓ 导入检查通过")
        
        # ============ 测试3: 类定义检查 ============
        logger.debug(f"[StrategyCodeTesterBuy] [测试3] 类定义检查...")
        class_result = self._test_class_definition(strategy_code)
        test_results['class_definition'] = class_result
        if not class_result['passed']:
            errors.extend(class_result['errors'])
        else:
            logger.debug(f"[StrategyCodeTesterBuy] [测试3] ✓ 类定义检查通过")
        
        # ============ 测试4: 继承检查 ============
        logger.debug(f"[StrategyCodeTesterBuy] [测试4] 继承检查...")
        inheritance_result = self._test_inheritance(strategy_code)
        test_results['inheritance'] = inheritance_result
        if not inheritance_result['passed']:
            errors.extend(inheritance_result['errors'])
        else:
            logger.debug(f"[StrategyCodeTesterBuy] [测试4] ✓ 继承检查通过")
        
        # ============ 测试5: 方法实现检查 ============
        logger.debug(f"[StrategyCodeTesterBuy] [测试5] 方法实现检查...")
        methods_result = self._test_methods(strategy_code)
        test_results['methods'] = methods_result
        if not methods_result['passed']:
            errors.extend(methods_result['errors'])
        warnings.extend(methods_result['warnings'])
        if methods_result['passed']:
            logger.debug(f"[StrategyCodeTesterBuy] [测试5] ✓ 方法实现检查通过")
        
        # ============ 测试6: 日志功能检查 ============
        logger.debug(f"[StrategyCodeTesterBuy] [测试6] 日志功能检查...")
        logging_result = self._test_logging(strategy_code)
        test_results['logging'] = logging_result
        if not logging_result['passed']:
            warnings.extend(logging_result['warnings'])  # 日志检查失败只产生警告，不阻止测试通过
        if logging_result['passed']:
            logger.debug(f"[StrategyCodeTesterBuy] [测试6] ✓ 日志功能检查通过")
        
        # ============ 测试7: 执行测试（使用模拟数据） ============
        logger.debug(f"[StrategyCodeTesterBuy] [测试7] 执行测试...")
        execution_result = self._test_execution(strategy_code, strategy_name)
        test_results['execution'] = execution_result
        if not execution_result['passed']:
            errors.extend(execution_result['errors'])
        warnings.extend(execution_result['warnings'])
        if execution_result['passed']:
            logger.debug(f"[StrategyCodeTesterBuy] [测试7] ✓ 执行测试通过")
        
        # ============ 汇总结果 ============
        passed = len(errors) == 0
        
        result = {
            'passed': passed,
            'errors': errors,
            'warnings': warnings,
            'test_results': test_results,
            'strategy_name': strategy_name
        }
        
        if passed:
            logger.info(f"[StrategyCodeTesterBuy] ✓ 买入策略代码测试通过: {strategy_name}")
        else:
            logger.warning(f"[StrategyCodeTesterBuy] ✗ 买入策略代码测试失败: {strategy_name}, 错误数: {len(errors)}")
        
        return result
    
    def _test_syntax(self, strategy_code: str) -> Dict:
        """测试语法正确性"""
        try:
            ast.parse(strategy_code)
            return {
                'passed': True,
                'errors': [],
                'message': '语法检查通过'
            }
        except SyntaxError as e:
            return {
                'passed': False,
                'errors': [f"语法错误: {e.msg} (行 {e.lineno})"],
                'message': f'语法检查失败: {e.msg}'
            }
        except Exception as e:
            return {
                'passed': False,
                'errors': [f"语法检查异常: {str(e)}"],
                'message': f'语法检查异常: {str(e)}'
            }
    
    def _test_imports(self, strategy_code: str) -> Dict:
        """测试导入语句"""
        warnings = []
        
        # 检查是否导入了 typing
        has_typing_import = 'from typing import' in strategy_code or 'import typing' in strategy_code
        if not has_typing_import:
            warnings.append("建议导入 typing 模块用于类型注解: from typing import Dict, List")
        
        return {
            'passed': True,  # 不限制导入语句，仅返回警告
            'errors': [],
            'warnings': warnings,
            'message': '导入检查完成'
        }
    
    def _test_class_definition(self, strategy_code: str) -> Dict:
        """测试类定义"""
        errors = []
        warnings = []
        
        try:
            tree = ast.parse(strategy_code)
            
            # 查找类定义
            classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            
            if len(classes) == 0:
                errors.append("未找到类定义，策略代码必须定义一个类")
            elif len(classes) > 1:
                warnings.append(f"找到 {len(classes)} 个类定义，建议只定义一个策略类")
            else:
                # 检查类名
                class_name = classes[0].name
                if not class_name or len(class_name) == 0:
                    errors.append("类名不能为空")
        
        except Exception as e:
            errors.append(f"类定义检查异常: {str(e)}")
        
        return {
            'passed': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'message': '类定义检查完成'
        }
    
    def _test_inheritance(self, strategy_code: str) -> Dict:
        """测试继承关系"""
        errors = []
        
        try:
            tree = ast.parse(strategy_code)
            
            # 查找类定义
            classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            
            if len(classes) == 0:
                errors.append("未找到类定义")
                return {
                    'passed': False,
                    'errors': errors,
                    'message': '继承检查失败：未找到类定义'
                }
            
            # 检查是否继承自 StrategyBaseBuy
            strategy_class = None
            for cls in classes:
                # 检查基类
                for base in cls.bases:
                    if isinstance(base, ast.Name):
                        if base.id == 'StrategyBaseBuy':
                            strategy_class = cls
                            break
                    elif isinstance(base, ast.Attribute):
                        # 处理 from module import Class 的情况
                        if isinstance(base.value, ast.Name) and base.value.id == 'StrategyBaseBuy':
                            strategy_class = cls
                            break
                        # 处理 from trade.strategy.strategy_template_buy import StrategyBaseBuy 的情况
                        if (isinstance(base.value, ast.Attribute) and 
                            isinstance(base.value.value, ast.Attribute) and
                            isinstance(base.value.value.value, ast.Name) and
                            base.value.value.value.id == 'trade' and
                            base.value.value.attr == 'strategy' and
                            base.value.attr == 'strategy_template_buy' and
                            base.attr == 'StrategyBaseBuy'):
                            strategy_class = cls
                            break
            
            if strategy_class is None:
                errors.append("未找到继承自 StrategyBaseBuy 的类，买入策略代码必须继承 StrategyBaseBuy")
            else:
                logger.debug(f"[StrategyCodeTesterBuy] 找到继承自 StrategyBaseBuy 的类: {strategy_class.name}")
        
        except Exception as e:
            errors.append(f"继承检查异常: {str(e)}")
        
        return {
            'passed': len(errors) == 0,
            'errors': errors,
            'message': '继承检查完成'
        }
    
    def _test_methods(self, strategy_code: str) -> Dict:
        """测试方法实现"""
        errors = []
        warnings = []
        
        try:
            tree = ast.parse(strategy_code)
            
            # 查找类定义
            classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            
            if len(classes) == 0:
                errors.append("未找到类定义")
                return {
                    'passed': False,
                    'errors': errors,
                    'warnings': warnings,
                    'message': '方法检查失败：未找到类定义'
                }
            
            # 查找继承自 StrategyBaseBuy 的类
            strategy_class = None
            for cls in classes:
                for base in cls.bases:
                    if isinstance(base, ast.Name) and base.id == 'StrategyBaseBuy':
                        strategy_class = cls
                        break
                    elif isinstance(base, ast.Attribute):
                        if base.attr == 'StrategyBaseBuy':
                            strategy_class = cls
                            break
            
            if strategy_class is None:
                errors.append("未找到继承自 StrategyBaseBuy 的类")
                return {
                    'passed': False,
                    'errors': errors,
                    'warnings': warnings,
                    'message': '方法检查失败：未找到继承自 StrategyBaseBuy 的类'
                }
            
            # 查找方法定义
            methods = [node for node in strategy_class.body if isinstance(node, ast.FunctionDef)]
            method_names = [m.name for m in methods]
            
            # 检查必要的方法
            required_methods = ['execute_buy_decision']
            missing_methods = [m for m in required_methods if m not in method_names]
            
            if missing_methods:
                errors.append(f"缺少必要的方法: {', '.join(missing_methods)}")
            
            # 检查方法签名（简单检查参数数量）
            for method_name in required_methods:
                if method_name in method_names:
                    method = next(m for m in methods if m.name == method_name)
                    # execute_buy_decision 应该有 6 个参数（self + 5个：candidates, portfolio, account_info, market_state, conditional_orders）
                    if method_name == 'execute_buy_decision':
                        expected_args = 6
                        actual_args = len(method.args.args)
                        if actual_args != expected_args:
                            warnings.append(f"{method_name} 方法参数数量不正确，期望 {expected_args} 个（包括self），实际 {actual_args} 个")
        
        except Exception as e:
            errors.append(f"方法检查异常: {str(e)}")
            import traceback
            logger.debug(f"[StrategyCodeTesterBuy] 方法检查异常堆栈:\n{traceback.format_exc()}")
        
        return {
            'passed': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'message': '方法检查完成'
        }
    
    def _test_logging(self, strategy_code: str) -> Dict:
        """测试日志功能使用情况"""
        warnings = []
        
        try:
            # 检查代码中是否使用了 self.log.info() 或 self.log.warning() 等日志方法
            has_log_info = 'self.log.info' in strategy_code
            has_log_warning = 'self.log.warning' in strategy_code
            has_log_error = 'self.log.error' in strategy_code
            has_log_debug = 'self.log.debug' in strategy_code
            
            # 检查是否使用了日志（至少使用一种日志级别）
            has_any_logging = has_log_info or has_log_warning or has_log_error or has_log_debug
            
            if not has_any_logging:
                warnings.append("建议在策略代码中使用 self.log.info() 输出关键执行日志，便于调试和监控")
            elif not has_log_info:
                warnings.append("建议在策略代码中使用 self.log.info() 输出关键执行信息（当前未使用 log.info）")
            else:
                # 统计日志使用次数
                log_info_count = strategy_code.count('self.log.info')
                if log_info_count < 2:
                    warnings.append(f"建议在策略代码中使用更多 self.log.info() 输出关键执行信息（当前仅使用 {log_info_count} 次）")
        
        except Exception as e:
            warnings.append(f"日志功能检查异常: {str(e)}")
        
        return {
            'passed': True,  # 日志检查不阻止测试通过，只产生警告
            'errors': [],
            'warnings': warnings,
            'message': '日志功能检查完成'
        }
    
    def _test_execution(self, strategy_code: str, strategy_name: str) -> Dict:
        """测试代码执行能力（使用模拟数据或真实数据）"""
        errors = []
        warnings = []

        # 根据配置选择使用mock数据还是真实数据
        if self.use_real_data:
            logger.info(f"[StrategyCodeTesterBuy] 使用真实数据进行测试")
            try:
                test_data = self._get_real_market_data()
                if test_data is None:
                    warnings.append("获取真实数据失败，回退到使用mock数据")
                    test_data = self._get_mock_market_data()
            except Exception as e:
                logger.warning(f"[StrategyCodeTesterBuy] 获取真实数据失败: {e}，回退到使用mock数据")
                warnings.append(f"获取真实数据失败: {str(e)}，回退到使用mock数据")
                test_data = self._get_mock_market_data()
        else:
            logger.debug(f"[StrategyCodeTesterBuy] 使用mock数据进行测试")
            test_data = self._get_mock_market_data()

        mock_candidates = test_data['candidates']
        mock_portfolio = test_data['portfolio']
        mock_account_info = test_data['account_info']
        mock_market_state = test_data['market_state']

        # 创建模拟条件单数据
        mock_conditional_orders = {
            'BTCUSDT': [
                {
                    'algoId': '123456789',
                    'orderType': 'STOP_MARKET',
                    'symbol': 'BTCUSDT',
                    'side': 'sell',
                    'positionSide': 'LONG',
                    'quantity': 0.05,
                    'algoStatus': 'NEW',
                    'triggerPrice': 48000.0
                },
                {
                    'algoId': '987654321',
                    'orderType': 'TAKE_PROFIT_MARKET',
                    'symbol': 'BTCUSDT',
                    'side': 'sell',
                    'positionSide': 'LONG',
                    'quantity': 0.05,
                    'algoStatus': 'NEW',
                    'triggerPrice': 52000.0
                }
            ]
        }

        # 测试买入决策执行
        try:
            logger.debug(f"[StrategyCodeTesterBuy] 测试买入决策执行...")
            buy_result = self.code_executor.execute_strategy_code(
                strategy_code=strategy_code,
                strategy_name=strategy_name,
                candidates=mock_candidates,
                portfolio=mock_portfolio,
                account_info=mock_account_info,
                market_state=mock_market_state,
                decision_type='buy',
                conditional_orders=mock_conditional_orders
            )
            
            if buy_result is None:
                errors.append("买入决策执行失败，返回 None")
            elif not isinstance(buy_result, dict):
                errors.append(f"买入决策返回格式不正确，期望 dict，实际 {type(buy_result)}")
            elif 'decisions' not in buy_result:
                errors.append("买入决策返回结果缺少 'decisions' 字段")
            else:
                decisions = buy_result.get('decisions', {})
                if not isinstance(decisions, dict):
                    errors.append(f"decisions 类型错误，期望 dict，实际 {type(decisions)}")
                else:
                    # 格式校验：仅支持 Dict[str, List[Dict]]，不兼容单条 dict 返回；每个 symbol 的 value 必须为列表
                    for sym, val in decisions.items():
                        if not isinstance(val, list):
                            errors.append(
                                f"返回值格式错误：decisions 的 value 必须为 List[Dict]（不兼容单条 dict）。"
                                f"当前 {sym!r} 的 value 类型为 {type(val).__name__}。"
                                f"正确示例: {{\"BTCUSDT\": [{{\"signal\": \"buy_to_long\", \"quantity\": 100, ...}}]}}"
                            )
                            break
                        for i, item in enumerate(val):
                            if not isinstance(item, dict):
                                errors.append(
                                    f"返回值格式错误：decisions[{sym!r}] 的第 {i+1} 项应为 dict，实际为 {type(item).__name__}"
                                )
                                break
                    if not errors:
                        total_count = sum(len(v) for v in decisions.values())
                        logger.debug(f"[StrategyCodeTesterBuy] ✓ 买入决策执行成功，格式 Dict[symbol, List[decision]] 正确，共 {len(decisions)} 个 symbol、{total_count} 条决策")
        except Exception as e:
            errors.append(f"买入决策执行异常: {str(e)}")
            import traceback
            logger.debug(f"[StrategyCodeTesterBuy] 买入决策执行异常堆栈:\n{traceback.format_exc()}")
        
        return {
            'passed': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'message': '执行测试完成'
        }

    def _get_mock_market_data(self) -> Dict:
        """
        获取mock测试数据

        Returns:
            Dict: 包含candidates, portfolio, account_info, market_state的测试数据
        """
        mock_candidates = [
            {
                'symbol': 'BTC',
                'contract_symbol': 'BTCUSDT',
                'price': 50000.0,
                'quote_volume': 1000000.0
            }
        ]

        mock_portfolio = {
            'positions': [],
            'cash': 10000.0,
            'total_value': 10000.0
        }

        mock_account_info = {
            'balance': 10000.0,
            'available_balance': 10000.0,
            'total_return': 0.0
        }

        mock_market_state = {
            'BTCUSDT': {
                'price': 50000.0,
                'contract_symbol': 'BTCUSDT',
                'quote_volume': 1000000.0,
                'base_volume': 20.0,
                'change_24h': 2.5,
                'source': 'future',
                'previous_close_prices': {
                    '1m': 49950.0,
                    '5m': 49900.0,
                    '15m': 49800.0,
                    '30m': 49700.0,
                    '1h': 49500.0,
                    '4h': 49000.0,
                    '1d': 48000.0,
                    '1w': 47000.0
                },
                'indicators': {
                    'timeframes': {
                        '1m': {
                            'klines': [
                                {'open': 49000.0, 'high': 51000.0, 'low': 48000.0, 'close': 50000.0, 'volume': 1000.0}
                            ] * 100  # 生成100根K线用于计算MA(99)
                        },
                        '5m': {
                            'klines': [
                                {'open': 49000.0, 'high': 51000.0, 'low': 48000.0, 'close': 50000.0, 'volume': 1000.0}
                            ] * 100
                        },
                        '15m': {
                            'klines': [
                                {'open': 49000.0, 'high': 51000.0, 'low': 48000.0, 'close': 50000.0, 'volume': 1000.0}
                            ] * 100
                        },
                        '30m': {
                            'klines': [
                                {'open': 49000.0, 'high': 51000.0, 'low': 48000.0, 'close': 50000.0, 'volume': 1000.0}
                            ] * 100
                        },
                        '1h': {
                            'klines': [
                                {'open': 49000.0, 'high': 51000.0, 'low': 48000.0, 'close': 50000.0, 'volume': 1000.0}
                            ] * 100  # 生成100根K线用于计算MA(99)
                        },
                        '4h': {
                            'klines': [
                                {'open': 49000.0, 'high': 51000.0, 'low': 48000.0, 'close': 50000.0, 'volume': 1000.0}
                            ] * 100
                        },
                        '1d': {
                            'klines': [
                                {'open': 49000.0, 'high': 51000.0, 'low': 48000.0, 'close': 50000.0, 'volume': 1000.0}
                            ] * 100
                        },
                        '1w': {
                            'klines': [
                                {'open': 49000.0, 'high': 51000.0, 'low': 48000.0, 'close': 50000.0, 'volume': 1000.0}
                            ] * 100
                        }
                    }
                }
            }
        }

        return {
            'candidates': mock_candidates,
            'portfolio': mock_portfolio,
            'account_info': mock_account_info,
            'market_state': mock_market_state
        }

    def _get_real_market_data(self) -> Optional[Dict]:
        """
        从币安API和数据库获取真实市场数据

        Returns:
            Dict: 包含candidates, portfolio, account_info, market_state的真实数据
            None: 获取失败时返回None
        """
        try:
            from trade.common.binance_futures_client import BinanceFuturesClient
            import trade.common.config as app_config

            # 从配置文件获取API配置（与trade服务保持一致）
            api_key = getattr(app_config, 'BINANCE_API_KEY', '')
            api_secret = getattr(app_config, 'BINANCE_API_SECRET', '')
            quote_asset = getattr(app_config, 'FUTURES_QUOTE_ASSET', 'USDT')
            testnet = getattr(app_config, 'BINANCE_TESTNET', False)

            if not api_key or not api_secret:
                logger.warning("[StrategyCodeTesterBuy] 未配置币安API密钥，无法获取真实数据")
                return None

            # 创建币安客户端（使用与trade服务一致的配置）
            client = BinanceFuturesClient(
                api_key=api_key,
                api_secret=api_secret,
                quote_asset=quote_asset,
                testnet=testnet
            )

            # 获取BTCUSDT的实时价格
            symbol = 'BTCUSDT'
            logger.info(f"[StrategyCodeTesterBuy] 获取 {symbol} 的真实市场数据...")

            # 获取当前价格
            try:
                price_data = client.get_symbol_price(symbol)
                current_price = float(price_data.get('price', 0))
                if current_price <= 0:
                    logger.warning(f"[StrategyCodeTesterBuy] 获取价格失败: {symbol}")
                    return None
            except Exception as e:
                logger.warning(f"[StrategyCodeTesterBuy] 获取价格失败: {e}")
                return None

            # 获取24小时统计数据
            try:
                ticker_data = client.get_24hr_ticker(symbol)
                quote_volume = float(ticker_data.get('quoteVolume', 0))
                base_volume = float(ticker_data.get('volume', 0))
                price_change_percent = float(ticker_data.get('priceChangePercent', 0))
            except Exception as e:
                logger.warning(f"[StrategyCodeTesterBuy] 获取24小时统计失败: {e}")
                quote_volume = 1000000.0
                base_volume = 20.0
                price_change_percent = 0.0

            # 获取K线数据（所有时间周期）
            intervals = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w']
            timeframes = {}
            previous_close_prices = {}

            for interval in intervals:
                try:
                    # 获取K线数据，limit=100以确保有足够数据计算MA(99)
                    klines_raw = client.get_klines(symbol, interval, limit=100)
                    if klines_raw and len(klines_raw) > 0:
                        # 转换K线数据格式
                        klines = []
                        for kline in klines_raw:
                            klines.append({
                                'open': float(kline.get('open', 0)),
                                'high': float(kline.get('high', 0)),
                                'low': float(kline.get('low', 0)),
                                'close': float(kline.get('close', 0)),
                                'volume': float(kline.get('volume', 0))
                            })
                        timeframes[interval] = {'klines': klines}

                        # 获取上一根K线的收盘价（倒数第二根，因为最后一根可能未完成）
                        if len(klines) >= 2:
                            previous_close_prices[interval] = klines[-2]['close']
                        else:
                            previous_close_prices[interval] = klines[-1]['close']

                        logger.debug(f"[StrategyCodeTesterBuy] 获取 {symbol} {interval} K线数据成功: {len(klines)} 根")
                    else:
                        logger.warning(f"[StrategyCodeTesterBuy] 获取 {symbol} {interval} K线数据为空")
                except Exception as e:
                    logger.warning(f"[StrategyCodeTesterBuy] 获取 {symbol} {interval} K线数据失败: {e}")

            # 检查是否至少获取到一个时间周期的数据
            if not timeframes:
                logger.warning("[StrategyCodeTesterBuy] 未能获取任何K线数据")
                return None

            # 构建测试数据
            real_candidates = [
                {
                    'symbol': 'BTC',
                    'contract_symbol': symbol,
                    'price': current_price,
                    'quote_volume': quote_volume
                }
            ]

            real_portfolio = {
                'positions': [],
                'cash': 10000.0,
                'total_value': 10000.0
            }

            real_account_info = {
                'balance': 10000.0,
                'available_balance': 10000.0,
                'total_return': 0.0
            }

            real_market_state = {
                symbol: {
                    'price': current_price,
                    'contract_symbol': symbol,
                    'quote_volume': quote_volume,
                    'base_volume': base_volume,
                    'change_24h': price_change_percent,
                    'source': 'future',
                    'previous_close_prices': previous_close_prices,
                    'indicators': {
                        'timeframes': timeframes
                    }
                }
            }

            logger.info(f"[StrategyCodeTesterBuy] 成功获取真实市场数据: {symbol}, 价格={current_price}, K线周期数={len(timeframes)}")

            return {
                'candidates': real_candidates,
                'portfolio': real_portfolio,
                'account_info': real_account_info,
                'market_state': real_market_state
            }

        except Exception as e:
            logger.error(f"[StrategyCodeTesterBuy] 获取真实市场数据失败: {e}")
            import traceback
            logger.debug(f"[StrategyCodeTesterBuy] 异常堆栈:\n{traceback.format_exc()}")
            return None

    def generate_test_report(self, test_result: Dict) -> str:
        """生成测试报告"""
        report_lines = []
        report_lines.append("=" * 60)
        report_lines.append(f"买入策略代码测试报告: {test_result.get('strategy_name', '未知策略')}")
        report_lines.append("=" * 60)
        report_lines.append("")
        
        # 总体结果
        if test_result['passed']:
            report_lines.append("✓ 测试状态: 通过")
        else:
            report_lines.append("✗ 测试状态: 失败")
        
        report_lines.append("")
        
        # 各项测试结果
        test_results = test_result.get('test_results', {})
        for test_name, result in test_results.items():
            status = "✓" if result.get('passed', False) else "✗"
            report_lines.append(f"{status} {test_name}: {result.get('message', '')}")
            
            if result.get('errors'):
                for error in result['errors']:
                    report_lines.append(f"  - 错误: {error}")
            
            if result.get('warnings'):
                for warning in result['warnings']:
                    report_lines.append(f"  - 警告: {warning}")
        
        report_lines.append("")
        
        # 错误汇总
        if test_result.get('errors'):
            report_lines.append("错误汇总:")
            for i, error in enumerate(test_result['errors'], 1):
                report_lines.append(f"  {i}. {error}")
            report_lines.append("")
        
        # 警告汇总
        if test_result.get('warnings'):
            report_lines.append("警告汇总:")
            for i, warning in enumerate(test_result['warnings'], 1):
                report_lines.append(f"  {i}. {warning}")
            report_lines.append("")
        
        report_lines.append("=" * 60)
        
        return "\n".join(report_lines)


# ============ 便捷函数 ============

def validate_strategy_code(strategy_code: str, strategy_name: str = "新买入策略") -> Tuple[bool, Dict]:
    """
    验证买入策略代码（推荐使用）
    
    用于在添加新买入策略时验证 AI 生成的 strategy_code 是否正确。
    
    Args:
        strategy_code: 策略代码字符串（AI 生成的代码）
        strategy_name: 策略名称（用于日志和报告）
    
    Returns:
        Tuple[bool, Dict]: (是否通过验证, 测试结果详情)
    """
    tester = StrategyCodeTesterBuy()
    result = tester.test_strategy_code(strategy_code, strategy_name)
    return result['passed'], result


def validate_strategy_code_with_report(strategy_code: str, strategy_name: str = "新买入策略") -> Tuple[bool, str]:
    """
    验证买入策略代码并生成报告（推荐使用）
    
    用于在添加新买入策略时验证 AI 生成的 strategy_code，并返回格式化的测试报告。
    
    Args:
        strategy_code: 策略代码字符串（AI 生成的代码）
        strategy_name: 策略名称（用于日志和报告）
    
    Returns:
        Tuple[bool, str]: (是否通过验证, 测试报告文本)
    """
    tester = StrategyCodeTesterBuy()
    result = tester.test_strategy_code(strategy_code, strategy_name)
    report = tester.generate_test_report(result)
    return result['passed'], report

