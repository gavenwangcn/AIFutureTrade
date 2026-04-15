"""
非虚拟真实交易：用币安 SDK 返回对象解析持仓与订单，供落库同步。
不手写 JSON 字段名猜测；优先 getattr/模型属性，与 binance_futures._flatten_to_dicts 互补。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _tz8_now_naive() -> datetime:
    return datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)


def _f(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _s(val: Any, default: str = "") -> str:
    if val is None:
        return default
    return str(val).strip()


def _i(val: Any) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def sdk_positions_iter(account_data: Any) -> List[Any]:
    """account_information_v3().data() 上的 positions 列表（元素为 SDK 仓位对象）。"""
    if account_data is None:
        return []
    raw = getattr(account_data, "positions", None)
    if raw is None:
        return []
    if not isinstance(raw, list):
        return [raw]
    return raw


def portfolio_row_from_sdk_position(pos_obj: Any, model_uuid: str) -> Optional[Dict[str, Any]]:
    """将 SDK 单条仓位转为 portfolios 表一行（仅非零仓位）。"""
    sym = _s(
        getattr(pos_obj, "symbol", None)
        or getattr(pos_obj, "Symbol", None)
    ).upper()
    if not sym:
        return None
    ps = _s(
        getattr(pos_obj, "position_side", None)
        or getattr(pos_obj, "positionSide", None)
        or "BOTH"
    ).upper()
    amt = _f(
        getattr(pos_obj, "position_amt", None)
        or getattr(pos_obj, "positionAmt", None)
    )
    if abs(amt) < 1e-12:
        return None
    entry = _f(
        getattr(pos_obj, "entry_price", None)
        or getattr(pos_obj, "entryPrice", None)
    )
    upnl = _f(
        getattr(pos_obj, "unrealized_profit", None)
        or getattr(pos_obj, "unrealizedProfit", None)
    )
    im = _f(
        getattr(pos_obj, "initial_margin", None)
        or getattr(pos_obj, "initialMargin", None)
    )
    lev = getattr(pos_obj, "leverage", None)
    try:
        leverage = int(lev) if lev is not None else 1
    except (TypeError, ValueError):
        leverage = 1
    abs_amt = abs(amt)
    return {
        "model_id": model_uuid,
        "symbol": sym,
        "position_amt": abs_amt,
        "position_init": abs_amt,
        "avg_price": entry,
        "leverage": max(1, leverage),
        "position_side": ps if ps in ("LONG", "SHORT", "BOTH") else "LONG",
        "initial_margin": im,
        "unrealized_profit": upnl,
    }


def merge_trade_row_from_query_order(
    order_obj: Any,
    *,
    trade_id: str,
    model_uuid: str,
    future: str,
    signal: str,
    leverage: int,
    side: str,
    position_side: str,
    pnl: float,
    fee: float,
    initial_margin: float,
    strategy_decision_id: Optional[str],
    portfolios_id: Optional[str],
) -> Tuple[List[str], List[Any]]:
    """
    用 SDK query_order 返回对象填充 trades 列；quantity/price/orderId/type 等以交易所为准。
    """
    ex_qty = _f(
        getattr(order_obj, "executed_qty", None)
        or getattr(order_obj, "executedQty", None)
    )
    avg_px = _f(
        getattr(order_obj, "avg_price", None)
        or getattr(order_obj, "avgPrice", None)
    )
    oid = _i(
        getattr(order_obj, "order_id", None)
        or getattr(order_obj, "orderId", None)
    )
    otype = _s(
        getattr(order_obj, "order_type", None)
        or getattr(order_obj, "type", None)
    ) or None
    orig_type = _s(
        getattr(order_obj, "orig_type", None)
        or getattr(order_obj, "origType", None)
    ) or None
    ps_sdk = _s(
        getattr(order_obj, "position_side", None)
        or getattr(order_obj, "positionSide", None)
    )
    if ps_sdk:
        position_side = ps_sdk.upper()
    columns = [
        "id",
        "model_id",
        "future",
        "signal",
        "quantity",
        "price",
        "leverage",
        "side",
        "position_side",
        "pnl",
        "fee",
        "initial_margin",
        "portfolios_id",
        "timestamp",
    ]
    values: List[Any] = [
        trade_id,
        model_uuid,
        future.upper(),
        signal,
        ex_qty,
        avg_px,
        leverage,
        side,
        position_side.upper() if position_side else "LONG",
        pnl,
        fee,
        initial_margin,
        portfolios_id,
        _tz8_now_naive(),
    ]
    if strategy_decision_id:
        columns.append("strategy_decision_id")
        values.append(strategy_decision_id)
    if oid is not None:
        columns.append("orderId")
        values.append(oid)
    if otype:
        columns.append("type")
        values.append(otype)
    if orig_type:
        columns.append("origType")
        values.append(orig_type)
    return columns, values
