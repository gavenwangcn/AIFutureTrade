"""
Strategy Code Template - 策略代码模板基类

本模块定义了策略代码的抽象基类。
所有策略代码都应该继承 StrategyBase 类并实现其抽象方法。

使用方式：
1. AI 生成的 strategy_code 应该继承 StrategyBase
2. 实现 execute_buy_decision() 和 execute_sell_decision() 方法
3. 系统会实例化策略类并调用相应方法
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class StrategyBase(ABC):
    """
    策略代码抽象基类
    
    所有策略代码都必须继承此类并实现抽象方法。
    系统会在执行时实例化策略类并调用相应方法。
    
    使用示例：
        class MyStrategy(StrategyBase):
            def execute_buy_decision(self, candidates, portfolio, account_info, 
                                    market_state, symbol_source):
                # 实现买入决策逻辑
                return {"decisions": {...}}
            
            def execute_sell_decision(self, portfolio, market_state, account_info):
                # 实现卖出决策逻辑
                return {"decisions": {...}}
    """
    
    @abstractmethod
    def execute_buy_decision(
        self,
        candidates: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        market_state: Dict,
        symbol_source: str
    ) -> Dict[str, Dict]:
        """
        执行买入决策（抽象方法）
        
        子类必须实现此方法，根据候选交易对列表生成买入/开仓决策。
        
        Args:
            candidates: 候选交易对列表，每个元素包含：
                - symbol: 交易对符号（如 'BTC'）
                - contract_symbol: 合约符号（如 'BTCUSDT'）
                - price: 当前价格
                - quote_volume: 24小时成交额
            portfolio: 持仓组合信息，包含：
                - positions: 当前持仓列表
                - cash: 可用现金
                - total_value: 账户总值
            account_info: 账户信息，包含：
                - balance: 账户余额
                - available_balance: 可用余额
                - total_return: 累计收益率
            market_state: 市场状态字典，key为交易对符号，value包含：
                - price: 当前价格
                - contract_symbol: 合约符号
                - quote_volume: 24小时成交额
                - change_24h: 24小时涨跌幅
                - indicators: 技术指标数据
                    - timeframes: 多时间周期的技术指标
                    格式：{"1h": {"klines": [...]}, "4h": {...}, ...}
            symbol_source: 数据源类型（'leaderboard' 或 'future'）
        
        Returns:
            Dict[str, Dict]: 决策字典，格式为：
                {
                    "SYMBOL": {
                        "signal": "buy_to_enter" | "sell_to_enter",
                        "quantity": 100,
                        "leverage": 10,
                        "justification": "理由说明"
                    }
                }
                如果没有决策，返回空字典 {}
        
        Note:
            - 从 market_state 中获取技术指标数据：market_state[symbol]['indicators']['timeframes']
            - 从 market_state 中获取当前价格：market_state[symbol]['price']
            - 约束条件可以从 portfolio 中获取（如 cash、positions 数量等）
        """
        pass
    
    @abstractmethod
    def execute_sell_decision(
        self,
        portfolio: Dict,
        market_state: Dict,
        account_info: Dict
    ) -> Dict[str, Dict]:
        """
        执行卖出决策（抽象方法）
        
        子类必须实现此方法，根据当前持仓生成卖出/平仓决策。
        
        Args:
            portfolio: 当前持仓组合信息，包含：
                - positions: 持仓列表，每个元素包含：
                    - symbol: 交易对符号
                    - position_amt: 持仓数量
                    - position_side: 持仓方向（LONG/SHORT）
                    - avg_price: 开仓均价
                    - unrealized_profit: 未实现盈亏
                - total_value: 账户总值
                - cash: 可用现金
            market_state: 市场状态字典，key为交易对符号，value包含：
                - price: 当前价格
                - indicators: 技术指标数据
                    - timeframes: 多时间周期的技术指标
                    格式：{"1h": {"klines": [...]}, "4h": {...}, ...}
            account_info: 账户信息，包含：
                - total_return: 累计收益率
        
        Returns:
            Dict[str, Dict]: 决策字典，格式为：
                {
                    "SYMBOL": {
                        "signal": "close_position" | "stop_loss" | "take_profit",
                        "quantity": 100,
                        "price": 0.0345,      # 期望价格（可选）
                        "stop_price": 0.0325, # 止损/止盈触发价格（必填）
                        "leverage": 10,
                        "justification": "理由说明"
                    }
                }
                如果没有决策，返回空字典 {}
        """
        pass
    
    def get_available_libraries(self) -> Dict:
        """
        获取可用的库（辅助方法）
        
        子类可以通过此方法了解可用的库和工具。
        
        Returns:
            Dict: 包含可用库的字典
        """
        return {
            'talib': 'TA-Lib 技术指标库（如果可用）',
            'numpy': 'NumPy 数值计算库（如果可用）',
            'pandas': 'Pandas 数据分析库（如果可用）',
            'math': 'Python 数学函数库',
            'datetime': 'Python 日期时间库',
            'json': 'Python JSON 处理库',
            'time': 'Python 时间库',
            'random': 'Python 随机数库'
        }
