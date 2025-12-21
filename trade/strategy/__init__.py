"""
策略模块 - Strategy Module

本模块包含所有策略相关的代码，包括：
1. strategy_template: 策略代码模板基类（向后兼容）
2. strategy_template_buy: 买入策略代码模板基类
3. strategy_template_sell: 卖出策略代码模板基类
4. strategy_code_executor: 策略代码执行器
5. strategy_code_tester: 策略代码测试器（向后兼容）
6. strategy_code_tester_buy: 买入策略代码测试器
7. strategy_code_tester_sell: 卖出策略代码测试器
8. strategy_trader: 基于策略代码的交易决策生成器
9. strategy_prompt_template: 策略代码生成 Prompt 模板（向后兼容）
10. strategy_prompt_template_buy: 买入策略代码生成 Prompt 模板
11. strategy_prompt_template_sell: 卖出策略代码生成 Prompt 模板
12. strategy_example: 策略代码示例（向后兼容）
13. strategy_example_buy: 买入策略代码示例
14. strategy_example_sell: 卖出策略代码示例
"""

# 向后兼容的旧模块
from trade.strategy.strategy_template import StrategyBase
from trade.strategy.strategy_code_executor import StrategyCodeExecutor
from trade.strategy.strategy_code_tester import StrategyCodeTester, validate_strategy_code, validate_strategy_code_with_report
from trade.strategy.strategy_trader import StrategyTrader
from trade.strategy.strategy_prompt_template import STRATEGY_CODE_GENERATION_PROMPT, generate_strategy_code_prompt

# 新的买入策略模块
from trade.strategy.strategy_template_buy import StrategyBaseBuy
from trade.strategy.strategy_code_tester_buy import StrategyCodeTesterBuy, validate_strategy_code as validate_buy_strategy_code, validate_strategy_code_with_report as validate_buy_strategy_code_with_report
from trade.strategy.strategy_prompt_template_buy import STRATEGY_CODE_GENERATION_PROMPT_BUY, generate_strategy_code_prompt as generate_buy_strategy_code_prompt

# 新的卖出策略模块
from trade.strategy.strategy_template_sell import StrategyBaseSell
from trade.strategy.strategy_code_tester_sell import StrategyCodeTesterSell, validate_strategy_code as validate_sell_strategy_code, validate_strategy_code_with_report as validate_sell_strategy_code_with_report
from trade.strategy.strategy_prompt_template_sell import STRATEGY_CODE_GENERATION_PROMPT_SELL, generate_strategy_code_prompt as generate_sell_strategy_code_prompt

__all__ = [
    # 向后兼容
    'StrategyBase',
    'StrategyCodeExecutor',
    'StrategyCodeTester',
    'StrategyTrader',
    'STRATEGY_CODE_GENERATION_PROMPT',
    'generate_strategy_code_prompt',
    'validate_strategy_code',
    'validate_strategy_code_with_report',
    # 新的买入策略模块
    'StrategyBaseBuy',
    'StrategyCodeTesterBuy',
    'STRATEGY_CODE_GENERATION_PROMPT_BUY',
    'generate_buy_strategy_code_prompt',
    'validate_buy_strategy_code',
    'validate_buy_strategy_code_with_report',
    # 新的卖出策略模块
    'StrategyBaseSell',
    'StrategyCodeTesterSell',
    'STRATEGY_CODE_GENERATION_PROMPT_SELL',
    'generate_sell_strategy_code_prompt',
    'validate_sell_strategy_code',
    'validate_sell_strategy_code_with_report',
]

