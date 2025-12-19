"""
策略模块 - Strategy Module

本模块包含所有策略相关的代码，包括：
1. strategy_template: 策略代码模板基类
2. strategy_code_executor: 策略代码执行器
3. strategy_code_tester: 策略代码测试器
4. strategy_trader: 基于策略代码的交易决策生成器
5. strategy_prompt_template: 策略代码生成 Prompt 模板
6. strategy_example: 策略代码示例
"""

from trade.strategy.strategy_template import StrategyBase
from trade.strategy.strategy_code_executor import StrategyCodeExecutor
from trade.strategy.strategy_code_tester import StrategyCodeTester, validate_strategy_code, validate_strategy_code_with_report
from trade.strategy.strategy_trader import StrategyTrader
from trade.strategy.strategy_prompt_template import STRATEGY_CODE_GENERATION_PROMPT, generate_strategy_code_prompt

__all__ = [
    'StrategyBase',
    'StrategyCodeExecutor',
    'StrategyCodeTester',
    'StrategyTrader',
    'STRATEGY_CODE_GENERATION_PROMPT',
    'generate_strategy_code_prompt',
    'validate_strategy_code',
    'validate_strategy_code_with_report',
]

