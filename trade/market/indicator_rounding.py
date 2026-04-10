"""
技术指标对外输出精度：与 trade-mcp KlineIndicatorCalculator 一致，最多保留小数点后 4 位（HALF_UP）。
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

import numpy as np


def nested_dict_has_none(obj: Any) -> bool:
    """若嵌套 dict 中任一叶为 None，返回 True（用于判断整根 K 线是否应丢弃）。"""
    if obj is None:
        return True
    if isinstance(obj, dict):
        return any(
            v is None or (isinstance(v, dict) and nested_dict_has_none(v)) for v in obj.values()
        )
    return False


def compact_indicator_tree(obj: Any) -> Any:
    """
    去掉指标树中的 None 与空 dict，便于接口只返回有值的字段。
    """
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if v is None:
                continue
            if isinstance(v, dict):
                sub = compact_indicator_tree(v)
                if sub:
                    out[k] = sub
            else:
                out[k] = v
        return out
    return obj


def round_indicator_4(value: Any) -> Optional[float]:
    """
    将指标数值量化为最多 4 位小数；无法转换或非有限数时返回 None。
    """
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(f) or np.isinf(f):
        return None
    return float(Decimal(str(f)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
