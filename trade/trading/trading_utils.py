"""
交易工具函数模块 - 提供交易相关的工具函数

本模块提供各种交易相关的工具函数，用于简化TradingEngine中的代码逻辑。
"""
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


def parse_signal_to_position_side(signal: str) -> Tuple[str, str]:
    """
    解析signal到position_side和trade_signal
    
    Args:
        signal: AI返回的signal（如 'buy_to_long', 'sell_to_short'）
    
    Returns:
        Tuple[str, str]: (position_side, trade_signal)
    """
    signal_lower = signal.lower()
    
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


def calculate_quantity_with_risk(
    available_cash: float,
    price: float,
    trade_fee_rate: float,
    requested_quantity: float,
    risk_budget_pct: float = 3.0
) -> Tuple[float, Optional[str]]:
    """
    根据可用现金和风险预算计算交易数量
    
    该函数实现了基于风险控制的交易数量计算逻辑，确保：
    1. 不超过可用现金限制
    2. 符合风险预算要求（默认最大3%风险暴露）
    3. 考虑交易费用的影响
    4. 对无效请求数量进行合理调整
    
    Args:
        available_cash: 可用现金（交易账户中的可用资金）
        price: 当前价格（交易对的最新成交价格）
        trade_fee_rate: 交易费率（单边费率，如0.001表示0.1%）
        requested_quantity: 请求的数量（模型建议的交易数量）
        risk_budget_pct: 风险预算百分比（默认3%，即最大风险暴露不超过可用现金的3%）
    
    Returns:
        Tuple[float, Optional[str]]: (计算后的数量, 错误信息)
    """
    # 基本检查：可用现金必须大于0
    if available_cash <= 0:
        return 0, '可用现金不足，无法买入'
    
    # 计算最大可承受数量（考虑交易费用）
    # 公式：可用现金 ÷ (价格 × (1 + 交易费率))
    # 说明：购买数量需要考虑手续费，确保总支出（数量×价格×(1+费率)）不超过可用现金
    max_affordable_qty = available_cash / (price * (1 + trade_fee_rate))
    
    # 计算风险百分比：限制在1%~5%之间
    # 说明：将用户输入的百分比转换为小数，并确保在安全范围内
    # - 最低1%：避免过度保守的交易
    # - 最高5%：控制单笔交易的最大风险暴露
    risk_pct = min(max(risk_budget_pct / 100, 0.01), 0.05)
    
    # 计算基于风险的数量
    # 公式：(可用现金 × 风险百分比) ÷ (价格 × (1 + 交易费率))
    # 说明：根据风险预算计算的最大允许交易数量，确保单笔交易风险可控
    risk_based_qty = (available_cash * risk_pct) / (price * (1 + trade_fee_rate))
    
    # 处理请求数量：转换为整数
    # 说明：加密货币交易通常要求整数数量，小数部分会被截断
    quantity = int(float(requested_quantity))
    
    # 检查请求数量是否有效：
    # 1. 必须大于0
    # 2. 不能超过最大可承受数量
    if quantity <= 0 or quantity > max_affordable_qty:
        # 调整数量：取最大可承受数量和风险基数量中的较小值
        # 说明：确保交易既符合资金限制，又符合风险控制要求
        adjusted_qty = min(max_affordable_qty, risk_based_qty if risk_based_qty > 0 else max_affordable_qty)
        quantity = int(adjusted_qty)
    
    # 最终检查：调整后的数量必须大于0
    if quantity <= 0:
        return 0, '现金不足，无法买入'
    
    # 返回计算后的数量（整数）和无错误信息
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
    trade_fee_rate: float
) -> Tuple[float, float, float]:
    """
    计算交易所需资金
    
    Args:
        quantity: 数量
        price: 价格
        leverage: 杠杆
        trade_fee_rate: 交易费率
    
    Returns:
        Tuple[float, float, float]: (交易金额, 手续费, 所需保证金)
    """
    trade_amount = quantity * price
    trade_fee = trade_amount * trade_fee_rate
    required_margin = trade_amount / leverage
    total_required = required_margin + trade_fee
    
    return trade_amount, trade_fee, total_required


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

