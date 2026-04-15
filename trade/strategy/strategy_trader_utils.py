"""
Strategy trader 共享工具：行情过滤、收盘价日志行、候选/持仓去重等。
日志前缀仍由调用方使用 [StrategyTrader]，与拆分前一致。
"""

import json
from typing import Dict, List, Set, Tuple


def filter_market_state(ms: Dict, allowed_symbols: Set[str]) -> Dict:
    """仅保留 allowed_symbols（大写）中出现的 key。"""
    if not ms or not isinstance(ms, dict) or not allowed_symbols:
        return {}
    filtered: Dict = {}
    for k, v in ms.items():
        try:
            if str(k).upper() in allowed_symbols:
                filtered[k] = v
        except Exception:
            continue
    return filtered


def market_state_by_upper(ms: Dict) -> Dict:
    """market_state key -> upper 映射，便于按 symbol 查找。"""
    out: Dict = {}
    for k, v in (ms or {}).items():
        try:
            out[str(k).upper()] = v
        except Exception:
            continue
    return out


def build_close_price_log_lines(symbols: List[str], ms: Dict) -> List[str]:
    """构造「收盘价信息」多行文本（与原先 StrategyTrader 逻辑一致）。"""
    if not symbols or not ms or not isinstance(ms, dict):
        return []
    ms_by_upper = market_state_by_upper(ms)
    lines: List[str] = []
    for sym in symbols:
        sym_u = str(sym).upper()
        payload = ms_by_upper.get(sym_u) or {}
        prev_close = payload.get("previous_close_prices") if isinstance(payload, dict) else None
        price = payload.get("price") if isinstance(payload, dict) else None
        prev_close_json = json.dumps(prev_close, ensure_ascii=False, default=str)
        lines.append(
            f"symbol={sym_u} | price实时价={price} | previous_close_prices收盘价={prev_close_json}"
        )
    return lines


def log_submit_close_prices(
    log,
    model_id: int,
    context: str,
    symbols: List[str],
    ms: Dict,
) -> None:
    try:
        lines = build_close_price_log_lines(symbols, ms)
        if lines:
            log.info(
                f"[StrategyTrader] [Model {model_id}] 提交到策略代码({context}) 收盘价信息:\n"
                + "\n".join(lines)
            )
    except Exception as e:
        log.debug(f"[StrategyTrader] 打印收盘价日志失败: {e}")


def dedupe_candidates_by_symbol(candidates: List[Dict]) -> Tuple[List[Dict], Set[str]]:
    """按 symbol 去重候选，保留顺序。"""
    remaining: List[Dict] = []
    sym_set: Set[str] = set()
    for c in candidates or []:
        try:
            sym = str(c.get("symbol") or c.get("contract_symbol") or "").upper()
        except Exception:
            sym = ""
        if not sym or sym in sym_set:
            continue
        sym_set.add(sym)
        remaining.append(c)
    return remaining, sym_set


def dedupe_positions_by_symbol(positions: List[Dict]) -> Tuple[List[Dict], Set[str]]:
    """按 symbol 去重持仓，保留顺序。"""
    remaining: List[Dict] = []
    sym_set: Set[str] = set()
    for p in positions or []:
        try:
            sym = str(p.get("symbol") or "").upper()
        except Exception:
            sym = ""
        if not sym or sym in sym_set:
            continue
        sym_set.add(sym)
        remaining.append(p)
    return remaining, sym_set


def unique_ordered_symbols_from_strings(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for s in items:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out
