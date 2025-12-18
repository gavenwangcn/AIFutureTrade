"""
Trader - 交易决策生成器抽象基类

本模块提供Trader抽象基类，定义交易决策生成的标准接口。
子类需要实现make_buy_decision和make_sell_decision方法。

主要子类：
1. AITrader: 基于LLM的AI交易决策生成器
2. StrategyTrader: 基于策略代码的交易决策生成器
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class Trader(ABC):
    """
    交易决策生成器抽象基类
    
    定义交易决策生成的标准接口，所有具体的交易决策生成器都应该继承此类。
    
    使用示例：
        trader = AITrader(...)  # 或 StrategyTrader(...)
        result = trader.make_buy_decision(candidates, portfolio, account_info)
    """
    
    @abstractmethod
    def make_buy_decision(
        self,
        candidates: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        market_state: Dict,
        symbol_source: str = 'leaderboard',
        model_id: Optional[int] = None
    ) -> Dict:
        """
        生成买入/开仓决策（抽象方法）
        
        Args:
            candidates: 候选交易对列表
            portfolio: 持仓组合信息
            account_info: 账户信息
            market_state: 市场状态字典，key为交易对符号，value包含价格、技术指标等
            symbol_source: 数据源类型
            model_id: 模型ID
        
        Returns:
            Dict: 包含以下字段的字典：
                - decisions: 决策字典，key为交易对符号，value为决策详情
                - prompt: 提示词（可选）
                - raw_response: 原始响应（可选）
                - cot_trace: 推理过程（可选）
                - skipped: 是否跳过
        """
        pass
    
    @abstractmethod
    def make_sell_decision(
        self,
        portfolio: Dict,
        market_state: Dict,
        account_info: Dict,
        model_id: Optional[int] = None
    ) -> Dict:
        """
        生成卖出/平仓决策（抽象方法）
        
        Args:
            portfolio: 当前持仓组合信息
            market_state: 市场状态字典，key为交易对符号，value包含价格、技术指标等
            account_info: 账户信息
            model_id: 模型ID
        
        Returns:
            Dict: 包含以下字段的字典：
                - decisions: 决策字典，key为交易对符号，value为决策详情
                - prompt: 提示词（可选）
                - raw_response: 原始响应（可选）
                - cot_trace: 推理过程（可选）
                - skipped: 是否跳过
        """
        pass

