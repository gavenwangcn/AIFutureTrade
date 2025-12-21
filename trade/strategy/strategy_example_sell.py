"""
Strategy Code Example - 卖出策略代码示例

基于提供的策略规则实现的完整示例代码。
此示例展示了如何继承 StrategyBaseSell 并实现卖出决策方法。
"""

from trade.strategy.strategy_template_sell import StrategyBaseSell
from typing import Dict
import numpy as np

# 尝试导入 talib
try:
    import talib
except ImportError:
    talib = None


class ExampleSellStrategy(StrategyBaseSell):
    """
    示例卖出策略类
    
    策略规则：
    卖出策略（5倍杠杆）：
    (2) 多单平仓条件：
        条件A：即时价格 < 0.98 × MA(99)值，平仓100%
        条件B：即时价格 > 1.2 × MA(99)值，平仓100%
    (4) 空单平仓条件：
        条件A：即时价格 > 1.02 × MA(99)值，平仓100%
        条件B：即时价格 < 0.8 × MA(99)值，平仓100%
    """
    
    # 杠杆倍数
    LEVERAGE = 5
    
    def execute_sell_decision(
        self,
        portfolio: Dict,
        market_state: Dict,
        account_info: Dict
    ) -> Dict[str, Dict]:
        """
        执行卖出决策
        """
        decisions = {}
        
        # 获取当前持仓
        positions = portfolio.get('positions', []) or []
        
        # 遍历持仓
        for position in positions:
            symbol = position.get('symbol', '').upper()
            if not symbol:
                continue
            
            # 获取持仓信息
            position_amt = abs(position.get('position_amt', 0))
            position_side = position.get('position_side', 'LONG')  # LONG 或 SHORT
            avg_price = position.get('avg_price', 0)
            
            if position_amt <= 0:
                continue
            
            # 从 market_state 中获取该交易对的市场数据
            symbol_market_state = market_state.get(symbol, {})
            if not symbol_market_state:
                continue
            
            # 获取当前价格
            current_price = symbol_market_state.get('price', 0)
            if current_price <= 0:
                continue
            
            # 获取技术指标数据
            indicators = symbol_market_state.get('indicators', {})
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
            
            # ============ 策略逻辑：卖出决策 ============
            
            if position_side == 'LONG':
                # (2) 多单平仓条件
                # 条件A：即时价格 < 0.98 × MA(99)值，平仓100%
                if current_price < 0.98 * ma99_value:
                    decisions[symbol] = {
                        "signal": "close_position",  # 平仓
                        "quantity": position_amt,
                        "price": current_price,
                        "stop_price": 0.98 * ma99_value,  # 触发价格
                        "leverage": position.get('leverage', self.LEVERAGE),
                        "justification": f"多单：价格 {current_price:.4f} < 0.98 × MA(99) {ma99_value:.4f}，满足平仓条件A"
                    }
                # 条件B：即时价格 > 1.2 × MA(99)值，平仓100%
                elif current_price > 1.2 * ma99_value:
                    decisions[symbol] = {
                        "signal": "take_profit",  # 止盈
                        "quantity": position_amt,
                        "price": current_price,
                        "stop_price": 1.2 * ma99_value,  # 触发价格
                        "leverage": position.get('leverage', self.LEVERAGE),
                        "justification": f"多单：价格 {current_price:.4f} > 1.2 × MA(99) {ma99_value:.4f}，满足平仓条件B（止盈）"
                    }
            
            elif position_side == 'SHORT':
                # (4) 空单平仓条件
                # 条件A：即时价格 > 1.02 × MA(99)值，平仓100%
                if current_price > 1.02 * ma99_value:
                    decisions[symbol] = {
                        "signal": "close_position",  # 平仓
                        "quantity": position_amt,
                        "price": current_price,
                        "stop_price": 1.02 * ma99_value,  # 触发价格
                        "leverage": position.get('leverage', self.LEVERAGE),
                        "justification": f"空单：价格 {current_price:.4f} > 1.02 × MA(99) {ma99_value:.4f}，满足平仓条件A"
                    }
                # 条件B：即时价格 < 0.8 × MA(99)值，平仓100%
                elif current_price < 0.8 * ma99_value:
                    decisions[symbol] = {
                        "signal": "take_profit",  # 止盈
                        "quantity": position_amt,
                        "price": current_price,
                        "stop_price": 0.8 * ma99_value,  # 触发价格
                        "leverage": position.get('leverage', self.LEVERAGE),
                        "justification": f"空单：价格 {current_price:.4f} < 0.8 × MA(99) {ma99_value:.4f}，满足平仓条件B（止盈）"
                    }
            
            # 不满足平仓条件，保持观望（不添加到 decisions 中）
        
        return decisions

