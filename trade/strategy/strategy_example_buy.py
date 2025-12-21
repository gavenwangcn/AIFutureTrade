"""
Strategy Code Example - 买入策略代码示例

基于提供的策略规则实现的完整示例代码。
此示例展示了如何继承 StrategyBaseBuy 并实现买入决策方法。
"""

from trade.strategy.strategy_template_buy import StrategyBaseBuy
from typing import Dict, List
import numpy as np

# 尝试导入 talib
try:
    import talib
except ImportError:
    talib = None


class ExampleBuyStrategy(StrategyBaseBuy):
    """
    示例买入策略类
    
    策略规则：
    买入策略（5倍杠杆）：
    (1) 开多单条件：当 即时价格 > 1.02 × MA(99)值，操作：买入50%仓位
    (3) 开空单条件：当 即时价格 ≤ 0.98 × MA(99)值，操作：买入50%仓位（做空）
    """
    
    # 杠杆倍数
    LEVERAGE = 5
    
    def execute_buy_decision(
        self,
        candidates: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        market_state: Dict,
        symbol_source: str
    ) -> Dict[str, Dict]:
        """
        执行买入决策
        """
        decisions = {}
        
        # 获取可用现金
        available_cash = portfolio.get('cash', 0)
        if available_cash <= 0:
            return decisions
        
        # 遍历候选交易对
        for candidate in candidates:
            symbol = candidate.get('symbol', '').upper()
            if not symbol:
                continue
            
            # 获取当前价格（优先从candidate获取，如果没有则从market_state获取）
            current_price = candidate.get('price', 0)
            if current_price <= 0:
                # 从 market_state 获取价格
                symbol_state = market_state.get(symbol, {})
                current_price = symbol_state.get('price', 0)
            
            if current_price <= 0:
                continue
            
            # 从 market_state 中获取该交易对的技术指标数据
            symbol_state = market_state.get(symbol, {})
            if not symbol_state:
                continue
            
            # 获取技术指标数据
            indicators = symbol_state.get('indicators', {})
            timeframes = indicators.get('timeframes', {})
            
            # 选择合适的时间周期（优先使用 1h）
            timeframe_data = timeframes.get('1h') or timeframes.get('4h') or timeframes.get('1d')
            if not timeframe_data:
                continue
            
            # 获取 K 线数据
            klines = timeframe_data.get('klines', [])
            if not klines or len(klines) < 99:
                # 数据不足，无法计算 MA(99)
                continue
            
            # 提取收盘价
            close_prices = []
            for k in klines:
                close = k.get('close', 0)
                if isinstance(close, (int, float)) and close > 0:
                    close_prices.append(float(close))
            
            if len(close_prices) < 99:
                continue
            
            # 转换为 numpy 数组
            close_array = np.array(close_prices)
            
            # 计算 MA(99) 指标
            if talib is None:
                # 如果 talib 不可用，使用简单移动平均
                if len(close_array) >= 99:
                    ma99_value = float(np.mean(close_array[-99:]))
                else:
                    continue
            else:
                try:
                    ma99 = talib.SMA(close_array, timeperiod=99)
                    if len(ma99) == 0 or np.isnan(ma99[-1]):
                        continue
                    ma99_value = float(ma99[-1])  # 获取最新的 MA(99) 值
                except Exception as e:
                    continue
            
            if ma99_value <= 0:
                continue
            
            # ============ 策略逻辑：买入决策 ============
            
            # (1) 开多单条件：当 即时价格 > 1.02 × MA(99)值
            if current_price > 1.02 * ma99_value:
                # 计算 50% 仓位的数量
                position_value = available_cash * 0.5
                quantity = position_value / current_price
                
                decisions[symbol] = {
                    "signal": "buy_to_enter",  # 开多单
                    "quantity": quantity,
                    "leverage": self.LEVERAGE,
                    "justification": f"价格 {current_price:.4f} > 1.02 × MA(99) {ma99_value:.4f}，满足开多条件"
                }
            
            # (3) 开空单条件：当 即时价格 ≤ 0.98 × MA(99)值
            elif current_price <= 0.98 * ma99_value:
                # 计算 50% 仓位的数量
                position_value = available_cash * 0.5
                quantity = position_value / current_price
                
                decisions[symbol] = {
                    "signal": "sell_to_enter",  # 开空单（做空）
                    "quantity": quantity,
                    "leverage": self.LEVERAGE,
                    "justification": f"价格 {current_price:.4f} ≤ 0.98 × MA(99) {ma99_value:.4f}，满足开空条件"
                }
            
            # 不满足开仓条件，保持观望（不添加到 decisions 中）
        
        return decisions

