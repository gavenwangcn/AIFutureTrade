"""
技术指标对外输出精度：与 trade-mcp KlineIndicatorCalculator 一致，最多保留小数点后 4 位（HALF_UP）。
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

import numpy as np


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
