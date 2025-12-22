"""
Strategy Code Tester - 卖出策略代码测试器

本模块提供 StrategyCodeTesterSell 类，用于验证 AI 生成的卖出策略代码是否符合要求。
主要用于在添加新卖出策略时，验证生成的 strategy_code 是否正确。

主要功能：
1. 语法检查：验证策略代码的语法正确性
2. 继承检查：验证是否继承自 StrategyBaseSell
3. 方法检查：验证是否实现了必要的方法
4. 签名检查：验证方法签名是否正确
5. 执行测试：使用模拟数据测试代码执行是否成功
6. 生成测试报告：返回详细的测试结果和错误信息

使用场景：
- 添加新卖出策略时，验证 AI 生成的 strategy_code
- 确保策略代码可以被 StrategyCodeExecutor 正确执行
"""
import ast
import logging
from typing import Dict, List, Optional, Tuple
import traceback
from trade.strategy.strategy_template_sell import StrategyBaseSell
from trade.strategy.strategy_code_executor import StrategyCodeExecutor

logger = logging.getLogger(__name__)


class StrategyCodeTesterSell:
    """
    卖出策略代码测试器
    
    用于验证 AI 生成的卖出策略代码是否符合要求，确保代码可以被 StrategyCodeExecutor 正确执行。
    
    测试内容：
    - 语法正确性：代码语法是否正确
    - 继承关系：是否继承自 StrategyBaseSell
    - 方法实现：是否实现了必要的方法（execute_sell_decision）
    - 方法签名：方法参数数量是否正确
    - 执行能力：使用模拟数据测试代码是否能正常执行
    
    使用示例：
        # 在添加卖出策略时验证 AI 生成的代码
        tester = StrategyCodeTesterSell()
        result = tester.test_strategy_code(strategy_code, strategy_name="新卖出策略")
        
        if result['passed']:
            # 测试通过，可以保存到数据库
            print("✓ 卖出策略代码验证通过，可以保存")
        else:
            # 测试失败，需要重新生成或修复
            print("✗ 卖出策略代码验证失败:")
            for error in result['errors']:
                print(f"  - {error}")
    """
    
    def __init__(self):
        """初始化测试器"""
        self.code_executor = StrategyCodeExecutor(preload_talib=True)
    
    def test_strategy_code(
        self,
        strategy_code: str,
        strategy_name: str = "测试卖出策略"
    ) -> Dict:
        """
        测试卖出策略代码
        
        全面测试卖出策略代码是否符合要求，包括语法、继承、方法实现和执行能力。
        
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
        
        logger.info(f"[StrategyCodeTesterSell] 开始测试卖出策略代码: {strategy_name}")
        
        # ============ 测试1: 语法检查 ============
        logger.debug(f"[StrategyCodeTesterSell] [测试1] 语法检查...")
        syntax_result = self._test_syntax(strategy_code)
        test_results['syntax'] = syntax_result
        if not syntax_result['passed']:
            errors.extend(syntax_result['errors'])
        else:
            logger.debug(f"[StrategyCodeTesterSell] [测试1] ✓ 语法检查通过")
        
        # ============ 测试2: 导入检查 ============
        logger.debug(f"[StrategyCodeTesterSell] [测试2] 导入检查...")
        import_result = self._test_imports(strategy_code)
        test_results['imports'] = import_result
        if not import_result['passed']:
            errors.extend(import_result['errors'])
        warnings.extend(import_result['warnings'])
        if import_result['passed']:
            logger.debug(f"[StrategyCodeTesterSell] [测试2] ✓ 导入检查通过")
        
        # ============ 测试3: 类定义检查 ============
        logger.debug(f"[StrategyCodeTesterSell] [测试3] 类定义检查...")
        class_result = self._test_class_definition(strategy_code)
        test_results['class_definition'] = class_result
        if not class_result['passed']:
            errors.extend(class_result['errors'])
        else:
            logger.debug(f"[StrategyCodeTesterSell] [测试3] ✓ 类定义检查通过")
        
        # ============ 测试4: 继承检查 ============
        logger.debug(f"[StrategyCodeTesterSell] [测试4] 继承检查...")
        inheritance_result = self._test_inheritance(strategy_code)
        test_results['inheritance'] = inheritance_result
        if not inheritance_result['passed']:
            errors.extend(inheritance_result['errors'])
        else:
            logger.debug(f"[StrategyCodeTesterSell] [测试4] ✓ 继承检查通过")
        
        # ============ 测试5: 方法实现检查 ============
        logger.debug(f"[StrategyCodeTesterSell] [测试5] 方法实现检查...")
        methods_result = self._test_methods(strategy_code)
        test_results['methods'] = methods_result
        if not methods_result['passed']:
            errors.extend(methods_result['errors'])
        warnings.extend(methods_result['warnings'])
        if methods_result['passed']:
            logger.debug(f"[StrategyCodeTesterSell] [测试5] ✓ 方法实现检查通过")
        
        # ============ 测试6: 执行测试（使用模拟数据） ============
        logger.debug(f"[StrategyCodeTesterSell] [测试6] 执行测试...")
        execution_result = self._test_execution(strategy_code, strategy_name)
        test_results['execution'] = execution_result
        if not execution_result['passed']:
            errors.extend(execution_result['errors'])
        warnings.extend(execution_result['warnings'])
        if execution_result['passed']:
            logger.debug(f"[StrategyCodeTesterSell] [测试6] ✓ 执行测试通过")
        
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
            logger.info(f"[StrategyCodeTesterSell] ✓ 卖出策略代码测试通过: {strategy_name}")
        else:
            logger.warning(f"[StrategyCodeTesterSell] ✗ 卖出策略代码测试失败: {strategy_name}, 错误数: {len(errors)}")
        
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
            warnings.append("建议导入 typing 模块用于类型注解: from typing import Dict")
        
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
            
            # 检查是否继承自 StrategyBaseSell
            strategy_class = None
            for cls in classes:
                # 检查基类
                for base in cls.bases:
                    if isinstance(base, ast.Name):
                        if base.id == 'StrategyBaseSell':
                            strategy_class = cls
                            break
                    elif isinstance(base, ast.Attribute):
                        # 处理 from module import Class 的情况
                        if isinstance(base.value, ast.Name) and base.value.id == 'StrategyBaseSell':
                            strategy_class = cls
                            break
                        # 处理 from trade.strategy.strategy_template_sell import StrategyBaseSell 的情况
                        if (isinstance(base.value, ast.Attribute) and 
                            isinstance(base.value.value, ast.Attribute) and
                            isinstance(base.value.value.value, ast.Name) and
                            base.value.value.value.id == 'trade' and
                            base.value.value.attr == 'strategy' and
                            base.value.attr == 'strategy_template_sell' and
                            base.attr == 'StrategyBaseSell'):
                            strategy_class = cls
                            break
            
            if strategy_class is None:
                errors.append("未找到继承自 StrategyBaseSell 的类，卖出策略代码必须继承 StrategyBaseSell")
            else:
                logger.debug(f"[StrategyCodeTesterSell] 找到继承自 StrategyBaseSell 的类: {strategy_class.name}")
        
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
            
            # 查找继承自 StrategyBaseSell 的类
            strategy_class = None
            for cls in classes:
                for base in cls.bases:
                    if isinstance(base, ast.Name) and base.id == 'StrategyBaseSell':
                        strategy_class = cls
                        break
                    elif isinstance(base, ast.Attribute):
                        if base.attr == 'StrategyBaseSell':
                            strategy_class = cls
                            break
            
            if strategy_class is None:
                errors.append("未找到继承自 StrategyBaseSell 的类")
                return {
                    'passed': False,
                    'errors': errors,
                    'warnings': warnings,
                    'message': '方法检查失败：未找到继承自 StrategyBaseSell 的类'
                }
            
            # 查找方法定义
            methods = [node for node in strategy_class.body if isinstance(node, ast.FunctionDef)]
            method_names = [m.name for m in methods]
            
            # 检查必要的方法
            required_methods = ['execute_sell_decision']
            missing_methods = [m for m in required_methods if m not in method_names]
            
            if missing_methods:
                errors.append(f"缺少必要的方法: {', '.join(missing_methods)}")
            
            # 检查方法签名（简单检查参数数量）
            for method_name in required_methods:
                if method_name in method_names:
                    method = next(m for m in methods if m.name == method_name)
                    # execute_sell_decision 应该有 4 个参数（self + 3个：portfolio, market_state, account_info）
                    if method_name == 'execute_sell_decision':
                        expected_args = 4
                        actual_args = len(method.args.args)
                        if actual_args != expected_args:
                            warnings.append(f"{method_name} 方法参数数量不正确，期望 {expected_args} 个（包括self），实际 {actual_args} 个")
        
        except Exception as e:
            errors.append(f"方法检查异常: {str(e)}")
            import traceback
            logger.debug(f"[StrategyCodeTesterSell] 方法检查异常堆栈:\n{traceback.format_exc()}")
        
        return {
            'passed': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'message': '方法检查完成'
        }
    
    def _test_execution(self, strategy_code: str, strategy_name: str) -> Dict:
        """测试代码执行能力（使用模拟数据）"""
        errors = []
        warnings = []
        
        # 创建模拟数据
        mock_portfolio = {
            'positions': [
                {
                    'symbol': 'BTC',
                    'position_amt': 0.1,
                    'position_side': 'LONG',
                    'avg_price': 49000.0,
                    'leverage': 5,
                    'unrealized_profit': 100.0
                }
            ],
            'cash': 10000.0,
            'total_value': 15000.0
        }
        
        mock_account_info = {
            'balance': 15000.0,
            'available_balance': 10000.0,
            'total_return': 50.0
        }
        
        mock_market_state = {
            'BTC': {
                'price': 50000.0,
                'contract_symbol': 'BTCUSDT',
                'quote_volume': 1000000.0,
                'change_24h': 2.5,
                'indicators': {
                    'timeframes': {
                        '1h': {
                            'klines': [
                                {'open': 49000.0, 'high': 51000.0, 'low': 48000.0, 'close': 50000.0, 'volume': 1000.0}
                            ] * 100  # 生成100根K线用于计算MA(99)
                        }
                    }
                }
            }
        }
        
        # 测试卖出决策执行
        try:
            logger.debug(f"[StrategyCodeTesterSell] 测试卖出决策执行...")
            sell_result = self.code_executor.execute_strategy_code(
                strategy_code=strategy_code,
                strategy_name=strategy_name,
                candidates=None,
                portfolio=mock_portfolio,
                account_info=mock_account_info,
                market_state=mock_market_state,
                decision_type='sell'
            )
            
            if sell_result is None:
                errors.append("卖出决策执行失败，返回 None")
            elif not isinstance(sell_result, dict):
                errors.append(f"卖出决策返回格式不正确，期望 dict，实际 {type(sell_result)}")
            elif 'decisions' not in sell_result:
                errors.append("卖出决策返回结果缺少 'decisions' 字段")
            else:
                logger.debug(f"[StrategyCodeTesterSell] ✓ 卖出决策执行成功，返回决策数: {len(sell_result.get('decisions', {}))}")
        except Exception as e:
            errors.append(f"卖出决策执行异常: {str(e)}")
            import traceback
            logger.debug(f"[StrategyCodeTesterSell] 卖出决策执行异常堆栈:\n{traceback.format_exc()}")
        
        return {
            'passed': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'message': '执行测试完成'
        }
    
    def generate_test_report(self, test_result: Dict) -> str:
        """生成测试报告"""
        report_lines = []
        report_lines.append("=" * 60)
        report_lines.append(f"卖出策略代码测试报告: {test_result.get('strategy_name', '未知策略')}")
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

def validate_strategy_code(strategy_code: str, strategy_name: str = "新卖出策略") -> Tuple[bool, Dict]:
    """
    验证卖出策略代码（推荐使用）
    
    用于在添加新卖出策略时验证 AI 生成的 strategy_code 是否正确。
    
    Args:
        strategy_code: 策略代码字符串（AI 生成的代码）
        strategy_name: 策略名称（用于日志和报告）
    
    Returns:
        Tuple[bool, Dict]: (是否通过验证, 测试结果详情)
    """
    tester = StrategyCodeTesterSell()
    result = tester.test_strategy_code(strategy_code, strategy_name)
    return result['passed'], result


def validate_strategy_code_with_report(strategy_code: str, strategy_name: str = "新卖出策略") -> Tuple[bool, str]:
    """
    验证卖出策略代码并生成报告（推荐使用）
    
    用于在添加新卖出策略时验证 AI 生成的 strategy_code，并返回格式化的测试报告。
    
    Args:
        strategy_code: 策略代码字符串（AI 生成的代码）
        strategy_name: 策略名称（用于日志和报告）
    
    Returns:
        Tuple[bool, str]: (是否通过验证, 测试报告文本)
    """
    tester = StrategyCodeTesterSell()
    result = tester.test_strategy_code(strategy_code, strategy_name)
    report = tester.generate_test_report(result)
    return result['passed'], report

