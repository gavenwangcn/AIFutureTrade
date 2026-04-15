"""
Strategy Trader - 基于策略代码的交易决策生成器（门面类）

实现拆分为：
- strategy_trader_base: 共享初始化与数量归一化
- strategy_buy_trader: 买入决策
- strategy_sell_trader: 卖出决策
- strategy_look_trader: 盯盘决策
- strategy_trader_utils: 行情过滤、收盘价日志等工具函数

对外仍使用 ``StrategyTrader(db=db, model_id=...)``，行为与日志前缀 ``[StrategyTrader]`` 与拆分前一致。
"""

from trade.strategy.strategy_buy_trader import StrategyBuyTrader
from trade.strategy.strategy_sell_trader import StrategySellTrader
from trade.strategy.strategy_look_trader import StrategyLookTrader


class StrategyTrader(StrategyBuyTrader, StrategySellTrader, StrategyLookTrader):
    """
    基于策略代码的交易决策生成器。

    通过执行 strategys 表中关联的策略代码生成决策；买入/卖出按优先级执行，
    盯盘由调用方传入单条策略记录。

    使用示例::

        trader = StrategyTrader(db=db, model_id=1)
        result = trader.make_buy_decision(candidates, portfolio, account_info, market_state)
    """
    
    pass


__all__ = ["StrategyTrader"]
