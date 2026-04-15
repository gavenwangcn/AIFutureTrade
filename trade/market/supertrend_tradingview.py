"""
Supertrend（TradingView ta.supertrend 对齐）

默认参数：ATR 周期 10、乘数 3（与 Pine `ta.supertrend(3, 10)` 一致）。
基础价 HL2 = (high + low) / 2；ATR 为 Wilder RMA（与 `_calculate_atr_tradingview` 相同）。

上轨/下轨为 HL2 ± multiplier×ATR，再经「只单向修正」的 trailing 得到 final_upper / final_lower；
趋势翻转：上涨趋势中收盘价跌破 final_lower → 空；下跌趋势中收盘价突破 final_upper → 多。
输出线：趋势为多(1)时取 final_lower，为空(-1)时取 final_upper。
"""
from __future__ import annotations

from typing import Tuple

import numpy as np


def calculate_supertrend_tradingview(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    atr: np.ndarray,
    multiplier: float = 3.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Args:
        high, low, close: 同长度
        atr: 与 ATR(period) 输出同长度，前段可为 nan
        multiplier: 通常为 3.0

    Returns:
        (line, trend, final_upper, final_lower, upper_basic)
        trend: 1.0 多头, -1.0 空头
    """
    n = len(close)
    hl2 = (high + low) * 0.5
    upper_basic = hl2 + multiplier * atr
    lower_basic = hl2 - multiplier * atr

    final_upper = np.full(n, np.nan, dtype=np.float64)
    final_lower = np.full(n, np.nan, dtype=np.float64)
    trend = np.zeros(n, dtype=np.float64)
    line = np.full(n, np.nan, dtype=np.float64)

    for i in range(n):
        if np.isnan(atr[i]):
            continue

        ub = upper_basic[i]
        lb = lower_basic[i]
        if i == 0:
            final_upper[i] = ub
            final_lower[i] = lb
            trend[i] = 1.0 if close[i] > final_upper[i] else -1.0
            line[i] = final_lower[i] if trend[i] == 1.0 else final_upper[i]
            continue

        fu_prev = final_upper[i - 1]
        fl_prev = final_lower[i - 1]

        # Trailing：下轨仅在 raw 更高或上一根收盘跌破旧下轨时取 raw；否则保持
        if not np.isnan(lb) and not np.isnan(fl_prev):
            if lb > fl_prev or close[i - 1] <= fl_prev:
                final_lower[i] = lb
            else:
                final_lower[i] = fl_prev
        else:
            final_lower[i] = lb

        if not np.isnan(ub) and not np.isnan(fu_prev):
            if ub < fu_prev or close[i - 1] >= fu_prev:
                final_upper[i] = ub
            else:
                final_upper[i] = fu_prev
        else:
            final_upper[i] = ub

        if trend[i - 1] == 1.0 and close[i] < final_lower[i]:
            trend[i] = -1.0
        elif trend[i - 1] == -1.0 and close[i] > final_upper[i]:
            trend[i] = 1.0
        else:
            trend[i] = trend[i - 1]

        line[i] = final_lower[i] if trend[i] == 1.0 else final_upper[i]

    return line, trend, final_upper, final_lower, upper_basic
