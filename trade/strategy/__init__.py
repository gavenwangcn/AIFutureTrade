"""
策略模块 - Strategy Module

本模块包含所有策略相关的代码，包括：
1. strategy_template_buy: 买入策略代码模板基类
2. strategy_template_sell: 卖出策略代码模板基类
3. strategy_code_executor: 策略代码执行器
4. strategy_code_tester_buy: 买入策略代码测试器
5. strategy_code_tester_sell: 卖出策略代码测试器
6. strategy_trader: 基于策略代码的交易决策生成器
7. strategy_prompt_template_buy: 买入策略代码生成 Prompt 模板
8. strategy_prompt_template_sell: 卖出策略代码生成 Prompt 模板
"""

# 核心模块
from trade.strategy.strategy_code_executor import StrategyCodeExecutor
from trade.strategy.strategy_trader import StrategyTrader

# 买入策略模块
from trade.strategy.strategy_template_buy import StrategyBaseBuy
from trade.strategy.strategy_code_tester_buy import StrategyCodeTesterBuy, validate_strategy_code as validate_buy_strategy_code, validate_strategy_code_with_report as validate_buy_strategy_code_with_report

# 卖出策略模块
from trade.strategy.strategy_template_sell import StrategyBaseSell
from trade.strategy.strategy_code_tester_sell import StrategyCodeTesterSell, validate_strategy_code as validate_sell_strategy_code, validate_strategy_code_with_report as validate_sell_strategy_code_with_report

__all__ = [
    # 核心模块
    'StrategyCodeExecutor',
    'StrategyTrader',
    # 买入策略模块
    'StrategyBaseBuy',
    'StrategyCodeTesterBuy',
    'validate_buy_strategy_code',
    'validate_buy_strategy_code_with_report',
    # 卖出策略模块
    'StrategyBaseSell',
    'StrategyCodeTesterSell',
    'validate_sell_strategy_code',
    'validate_sell_strategy_code_with_report',
]

