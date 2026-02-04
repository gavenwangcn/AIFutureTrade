"""
交易工具函数模块 - 提供交易相关的工具函数

本模块提供各种交易相关的工具函数，用于简化TradingEngine中的代码逻辑。
"""
from typing import Dict, Optional, Tuple
import logging
import math

logger = logging.getLogger(__name__)


def adjust_quantity_precision_by_price(quantity: float, price: float) -> float:
    """
    根据symbol价格动态调整quantity的精度
    
    规则：
    - 价格 < 1：取整数
    - 1 <= 价格 < 10：小数点后1位
    - 10 <= 价格 < 100：小数点后2位
    - 100 <= 价格 < 1000：小数点后3位
    - 1000 <= 价格 < 10000：小数点后4位
    - 10000 <= 价格 < 100000：小数点后5位
    - 价格 >= 100000：小数点后6位（最多）
    
    Args:
        quantity: 原始数量
        price: symbol的当前价格
        
    Returns:
        调整精度后的数量
    """
    if quantity <= 0:
        return 0.0
    
    if price <= 0:
        # 如果价格无效，默认取整数
        return float(int(quantity))
    
    # 根据价格范围确定精度
    if price < 1:
        precision = 0  # 取整数
    elif price < 10:
        precision = 1  # 小数点后1位
    elif price < 100:
        precision = 2  # 小数点后2位
    elif price < 1000:
        precision = 3  # 小数点后3位
    elif price < 10000:
        precision = 4  # 小数点后4位
    elif price < 100000:
        precision = 5  # 小数点后5位
    else:
        precision = 6  # 小数点后6位（最多）
    
    # 四舍五入到指定精度
    adjusted_quantity = round(quantity, precision)
    
    # 如果精度为0（整数），确保返回整数
    if precision == 0:
        adjusted_quantity = float(int(adjusted_quantity))
    
    return adjusted_quantity


def parse_signal_to_position_side(signal: str) -> Tuple[str, str]:
    """
    解析signal到position_side和trade_signal
    
    Args:
        signal: AI返回的signal（如 'buy_to_long', 'sell_to_short'）
    
    Returns:
        Tuple[str, str]: (position_side, trade_signal)
    """
    signal_lower = signal.lower()
    
    # ⚠️ 重要：buy_to_long 和 buy_to_short 是有效的买入信号
    if signal_lower == 'buy_to_long':
        return 'LONG', 'buy_to_long'
    elif signal_lower == 'buy_to_short':
        return 'SHORT', 'buy_to_short'
    elif signal_lower == 'sell_to_long':
        return 'LONG', 'sell_to_long'
    elif signal_lower == 'sell_to_short':
        return 'SHORT', 'sell_to_short'
    else:
        # 默认使用LONG
        logger.warning(f"Invalid signal '{signal}', defaulting to LONG")
        return 'LONG', 'buy_to_long'


def get_side_for_trade(position_side: str) -> str:
    """
    根据持仓方向获取交易方向

    Args:
        position_side: 持仓方向（LONG或SHORT）

    Returns:
        str: 交易方向（BUY或SELL）
    """
    if position_side == 'LONG':
        return 'SELL'  # 平多仓使用SELL
    else:  # SHORT
        return 'BUY'   # 平空仓使用BUY


def get_side_for_sell_cycle(position_side: str) -> str:
    """
    卖出循环专用：获取交易方向

    在卖出循环中，无论持仓方向如何，都统一使用SELL方向

    Args:
        position_side: 持仓方向（LONG或SHORT）

    Returns:
        str: 交易方向（始终返回SELL）
    """
    return 'SELL'  # 卖出循环统一使用SELL


def calculate_quantity_with_risk(
    available_cash: float,
    price: float,
    trade_fee_rate: float,
    requested_quantity_usdt: float,
    risk_budget_pct: float = 3.0,
    leverage: int = 1
) -> Tuple[float, Optional[str]]:
    """
    根据可用现金、风险预算和杠杆计算实际买入数量（合约数量）
    
    新的杠杆交易逻辑：
    1. requested_quantity_usdt 是USDT数量（账户可用资金），不是合约数量
    2. 杠杆放大可使用资金倍数
    3. 实际买入数量 = (可用资金 * 本金比例 * 杠杆) / symbol市价
    4. 本金 = 可用资金 * 本金比例
    
    Args:
        available_cash: 可用现金（交易账户中的可用资金，USDT）
        price: 当前价格（交易对的最新成交价格）
        trade_fee_rate: 交易费率（单边费率，如0.001表示0.1%）
        requested_quantity_usdt: 请求的USDT数量（模型建议的USDT数量，不是合约数量）
        risk_budget_pct: 风险预算百分比（默认3%，即最大风险暴露不超过可用现金的3%）
        leverage: 杠杆倍数（默认1倍）
    
    Returns:
        Tuple[float, Optional[str]]: (实际买入的合约数量, 错误信息)
    """
    # 基本检查：可用现金必须大于0
    if available_cash <= 0:
        return 0, '可用现金不足，无法买入'
    
    if price <= 0:
        return 0, '价格无效，无法买入'
    
    if leverage <= 0:
        return 0, '杠杆倍数无效'
    
    # 计算风险百分比：限制在1%~100%之间
    # 说明：将用户输入的百分比转换为小数，并确保在安全范围内
    risk_pct = min(max(risk_budget_pct / 100, 0.01), 1.0)
    
    # 如果请求的USDT数量有效，使用请求的数量；否则使用风险预算
    if requested_quantity_usdt > 0:
        # 使用请求的USDT数量，但不能超过可用现金
        capital_usdt = min(requested_quantity_usdt, available_cash)
    else:
        # 使用风险预算计算本金
        capital_usdt = available_cash * risk_pct
    
    # 确保本金不超过可用现金
    capital_usdt = min(capital_usdt, available_cash)
    
    if capital_usdt <= 0:
        return 0, '本金不足，无法买入'
    
    # 计算杠杆后的可使用资金
    leveraged_capital = capital_usdt * leverage
    
    # 计算实际买入的合约数量 = 杠杆后资金 / 价格
    actual_quantity = leveraged_capital / price
    
    # 转换为整数（合约数量必须是整数）
    quantity = int(actual_quantity)
    
    # 最终检查：调整后的数量必须大于0
    if quantity <= 0:
        return 0, '计算后的合约数量为0，无法买入'
    
    # 返回计算后的合约数量（整数）和无错误信息
    return quantity, None


def validate_position_for_trade(
    portfolio: Dict,
    symbol: str,
    position_side: str
) -> Tuple[Optional[Dict], Optional[str]]:
    """
    验证持仓是否可用于交易
    
    Args:
        portfolio: 持仓组合信息
        symbol: 交易对符号
        position_side: 期望的持仓方向
    
    Returns:
        Tuple[Optional[Dict], Optional[str]]: (持仓信息, 错误信息)
    """
    positions = portfolio.get('positions', [])
    position = next((p for p in positions if p.get('symbol') == symbol), None)
    
    if not position:
        return None, 'Position not found'
    
    actual_position_side = position.get('position_side', 'LONG')
    if actual_position_side != position_side:
        return None, f'持仓方向不匹配：期望{position_side}，实际{actual_position_side}'
    
    position_amt = int(abs(position.get('position_amt', 0)))
    if position_amt <= 0:
        return None, '持仓数量为0，无法平仓'
    
    return position, None


def calculate_trade_requirements(
    quantity: float,
    price: float,
    leverage: int,
    trade_fee_rate: float,
    capital_usdt: float
) -> Tuple[float, float, float, float]:
    """
    计算交易所需资金（新的杠杆交易逻辑）
    
    新的逻辑：
    1. 交易金额 = 合约数量 * 价格（杠杆后的总价值）
    2. 手续费 = 交易金额 * 交易费率（双向收费，买入和卖出各收一次）
    3. initial_margin（本金）= capital_usdt（使用的本金USDT数量）
    4. 总消耗资金 = 本金 + 手续费（手续费只算到本金上，不算到杠杆后的总金额）
    
    Args:
        quantity: 实际买入的合约数量
        price: 价格
        leverage: 杠杆倍数
        trade_fee_rate: 交易费率（单边费率，如0.001表示0.1%）
        capital_usdt: 使用的本金USDT数量（不是杠杆后的金额）
    
    Returns:
        Tuple[float, float, float, float]: (交易金额, 买入手续费, 卖出手续费, initial_margin本金)
    """
    # 交易金额 = 合约数量 * 价格（这是杠杆后的总价值）
    trade_amount = quantity * price
    
    # 买入手续费 = 交易金额 * 交易费率
    buy_fee = trade_amount * trade_fee_rate
    
    # 卖出手续费 = 交易金额 * 交易费率（双向收费）
    sell_fee = trade_amount * trade_fee_rate
    
    # initial_margin（本金）= capital_usdt（使用的本金USDT数量）
    # 四舍五入保留两位小数
    initial_margin = round(capital_usdt, 2)
    
    return trade_amount, buy_fee, sell_fee, initial_margin


def calculate_pnl(
    entry_price: float,
    current_price: float,
    quantity: float,
    position_side: str,
    trade_fee_rate: float
) -> Tuple[float, float, float]:
    """
    计算盈亏（毛盈亏、手续费、净盈亏）
    
    Args:
        entry_price: 开仓价格
        current_price: 当前价格
        quantity: 数量
        position_side: 持仓方向（LONG或SHORT）
        trade_fee_rate: 交易费率
    
    Returns:
        Tuple[float, float, float]: (毛盈亏, 手续费, 净盈亏)
    """
    if position_side == 'LONG':
        gross_pnl = (current_price - entry_price) * quantity
    else:  # SHORT
        gross_pnl = (entry_price - current_price) * quantity
    
    trade_amount = quantity * current_price
    trade_fee = trade_amount * trade_fee_rate
    net_pnl = gross_pnl - trade_fee
    
    return gross_pnl, trade_fee, net_pnl


def extract_prices_from_market_state(market_state: Dict) -> Dict[str, float]:
    """
    从市场状态字典中提取价格字典
    
    Args:
        market_state: 市场状态字典，key为symbol，value包含price字段
    
    Returns:
        Dict[str, float]: {symbol: price_value}
    """
    return {s: m.get('price', 0) for s, m in market_state.items()}

