"""
盯盘引擎：每次只针对一个 symbol 拉取实时价、多周期 K 线与指标（逻辑与 TradingEngine 中单品种分支一致），
不通过 _build_market_state_for_candidates 批量接口。触发 notify 时：落库 SENDING、并入异步队列，由后台线程经 trade-monitor 推送后再写入 trade_notify 并置 ENDED。
"""

import copy
import json
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import numpy as np

import trade.common.config as app_config
from trade.common.wechat_markdown_limit import MAX_MARKDOWN_CHARS as _WECHAT_MD_MAX
from trade.common.database.database_market_look import (
    EXECUTION_ENDED,
    EXECUTION_SENDING,
    MarketLookDatabase,
)
from trade.common.database.database_strategys import StrategysDatabase
from trade.common.database.database_trade_notify import TradeNotifyDatabase
from trade.market.market_data import MarketDataFetcher
from trade.market.market_index import MarketIndexCalculator
from trade.market.indicator_rounding import round_indicator_4
from trade.strategy.strategy_trader import StrategyTrader

logger = logging.getLogger(__name__)

_TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _truncate_json_for_notify_line(obj: Any) -> str:
    """单行 market_date JSON，避免过大；整段 message 仍由 trade_monitor_client 按 4096 兜底。"""
    try:
        raw = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        raw = str(obj)
    cap = min(3500, max(512, _WECHAT_MD_MAX - 400))
    if len(raw) <= cap:
        return raw
    return raw[:cap] + f"...(truncated, total_len={len(raw)})"


def _now_shanghai_naive() -> datetime:
    """与 market_look.ended_at（DATETIME）对齐：上海墙钟时间的 naive datetime。"""
    return datetime.now(_TZ_SHANGHAI).replace(tzinfo=None)


def _parse_row_ended_at(row: Dict) -> Optional[datetime]:
    """解析 market_look.ended_at，返回 naive datetime（上海语义）。"""
    v = row.get("ended_at")
    if v is None:
        return None
    if isinstance(v, datetime):
        dt = v
    elif isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        if len(s) >= 19 and s[4] == "-" and s[10] in " T":
            dt = datetime.strptime(s[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S")
        else:
            try:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            except ValueError:
                return None
            if dt.tzinfo:
                dt = dt.astimezone(_TZ_SHANGHAI).replace(tzinfo=None)
            return dt
    else:
        return None
    if getattr(dt, "tzinfo", None):
        dt = dt.astimezone(_TZ_SHANGHAI).replace(tzinfo=None)
    return dt


def _is_deadline_passed(row: Dict) -> bool:
    deadline = _parse_row_ended_at(row)
    if deadline is None:
        return False
    return _now_shanghai_naive() >= deadline


def _normalize_symbol_key(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if s.endswith("USDT"):
        return s.replace("USDT", "")
    return s


def _contract_symbol(symbol: str) -> str:
    sym = _normalize_symbol_key(symbol)
    return sym if sym.endswith("USDT") else f"{sym}USDT"


def _candidate_for_symbol(symbol: str) -> Dict:
    sym = _normalize_symbol_key(symbol)
    contract = _contract_symbol(symbol)
    return {
        "symbol": sym,
        "contract_symbol": contract,
        "name": sym,
        "exchange": "BINANCE_FUTURES",
    }


def merge_timeframe_klines(market_fetcher: MarketDataFetcher, contract_symbol: str) -> Dict:
    """
    与 TradingEngine._merge_timeframe_data 相同：合并 8 周期 K 线（仅 klines），单合约。
    """
    symbol_upper = contract_symbol.upper()
    if not symbol_upper.endswith("USDT"):
        formatted_symbol = f"{symbol_upper}USDT"
    else:
        formatted_symbol = symbol_upper

    timeframe_methods = {
        "1m": market_fetcher.get_market_data_1m,
        "5m": market_fetcher.get_market_data_5m,
        "15m": market_fetcher.get_market_data_15m,
        "30m": market_fetcher.get_market_data_30m,
        "1h": market_fetcher.get_market_data_1h,
        "4h": market_fetcher.get_market_data_4h,
        "1d": market_fetcher.get_market_data_1d,
        "1w": market_fetcher.get_market_data_1w,
    }

    merged_data: Dict[str, Dict] = {formatted_symbol: {}}
    errors: List[str] = []

    for timeframe, method in timeframe_methods.items():
        try:
            data = method(formatted_symbol)
            if data:
                klines = data.get("klines", [])
                if klines:
                    merged_data[formatted_symbol][timeframe] = {"klines": klines}
                else:
                    errors.append(f"{timeframe}: K线数据为空")
            else:
                errors.append(f"{timeframe}: 返回数据为空")
        except Exception as e:
            errors.append(f"{timeframe}: {e}")
            logger.warning("LookEngine 获取 %s %s 失败: %s", formatted_symbol, timeframe, e)

    if not merged_data[formatted_symbol] and errors:
        logger.warning("LookEngine 获取 %s 全周期失败: %s", formatted_symbol, errors)

    return merged_data


def calculate_symbol_adx_timeframes(timeframes_data: Dict) -> Dict:
    """与 TradingEngine._calculate_symbol_adx 一致：为 1h/4h/1d K 线补充 ADX。"""
    calculator = MarketIndexCalculator()
    updated_timeframes: Dict = {}

    for timeframe in ["1h", "4h", "1d"]:
        tf_data = timeframes_data.get(timeframe, {})
        updated_timeframes[timeframe] = tf_data.copy() if tf_data else {}
        klines = tf_data.get("klines", [])

        if not klines or len(klines) < 14:
            updated_timeframes[timeframe]["klines"] = klines
            continue

        try:
            high = np.array([float(k.get("high", 0)) for k in klines if isinstance(k, dict)])
            low = np.array([float(k.get("low", 0)) for k in klines if isinstance(k, dict)])
            close = np.array([float(k.get("close", 0)) for k in klines if isinstance(k, dict)])

            if len(high) > 0 and len(low) > 0 and len(close) > 0:
                result = calculator.compute_adx(high, low, close)
                if result is not None:
                    adx_array, _, _ = result
                    updated_klines = []
                    for i, kline in enumerate(klines):
                        kline_copy = kline.copy() if isinstance(kline, dict) else {}
                        if "indicators" not in kline_copy:
                            kline_copy["indicators"] = {}
                        if i < len(adx_array) and not np.isnan(adx_array[i]):
                            adx_value = round_indicator_4(float(adx_array[i]))
                        else:
                            adx_value = None
                        if "adx" not in kline_copy["indicators"]:
                            kline_copy["indicators"]["adx"] = {}
                        kline_copy["indicators"]["adx"][f"adx_{timeframe}"] = adx_value
                        updated_klines.append(kline_copy)
                    updated_timeframes[timeframe]["klines"] = updated_klines
                else:
                    updated_timeframes[timeframe]["klines"] = klines
            else:
                updated_timeframes[timeframe]["klines"] = klines
        except Exception as e:
            logger.warning("LookEngine 计算 %s ADX 失败: %s", timeframe, e)
            updated_timeframes[timeframe]["klines"] = klines

    for tf in timeframes_data:
        if tf not in updated_timeframes:
            updated_timeframes[tf] = timeframes_data[tf]

    return updated_timeframes


def build_single_symbol_market_state(
    market_fetcher: MarketDataFetcher,
    candidate: Dict,
    log_tag: str = "LookEngine",
) -> Dict:
    """
    仅构建一个 symbol 的 market_state 条目（与 TradingEngine 中单候选分支逻辑一致），
    不经过 _build_market_state_for_candidates。
    """
    market_state: Dict[str, Any] = {}

    symbol = candidate.get("symbol")
    if not symbol:
        return market_state

    symbol_upper = symbol.upper()
    contract_symbol = candidate.get("contract_symbol")
    if contract_symbol:
        contract_symbol = contract_symbol.upper()
    else:
        su = symbol.upper()
        contract_symbol = su if su.endswith("USDT") else f"{su}USDT"

    query_symbol = contract_symbol
    price_key = contract_symbol
    symbol_list = [contract_symbol]

    prices: Dict = {}
    if market_fetcher:
        try:
            prices = market_fetcher.get_current_prices_by_contract(symbol_list)
            if not prices:
                prices = market_fetcher.get_current_prices(symbol_list)
            logger.info("[%s] SDK 实时价 %s 条", log_tag, len(prices))
        except Exception as e:
            logger.error("[%s] 获取实时价失败: %s", log_tag, e, exc_info=True)

    volume_data: Dict = {}
    if market_fetcher and getattr(market_fetcher, "_mysql_db", None):
        try:
            volume_data = market_fetcher._mysql_db.get_symbol_volumes(symbol_list)
        except Exception as e:
            logger.warning("[%s] 24h 成交额查询失败: %s", log_tag, e)

    price_info = prices.get(price_key, {}) if prices else {}
    if not price_info:
        logger.warning("[%s] 无实时价: %s", log_tag, contract_symbol)
        return market_state

    merged_data = merge_timeframe_klines(market_fetcher, query_symbol)
    timeframes_data = merged_data.get(query_symbol, {}) if merged_data else {}

    previous_close_prices: Dict[str, float] = {}
    for timeframe, timeframe_data in timeframes_data.items():
        klines = timeframe_data.get("klines", [])
        if klines and len(klines) >= 2:
            previous_kline = klines[-2]
            if isinstance(previous_kline, dict):
                previous_close = previous_kline.get("close")
                if previous_close is not None:
                    try:
                        previous_close_prices[timeframe] = float(previous_close)
                    except (ValueError, TypeError):
                        logger.warning(
                            "[%s] %s %s 上一根收盘转换失败", log_tag, symbol_upper, timeframe
                        )
        elif klines and len(klines) == 1:
            current_kline = klines[0]
            if isinstance(current_kline, dict):
                current_close = current_kline.get("close")
                if current_close is not None:
                    try:
                        previous_close_prices[timeframe] = float(current_close)
                    except (ValueError, TypeError):
                        pass

    volume_info = volume_data.get(contract_symbol, {})
    base_volume_value = volume_info.get("base_volume", 0.0) if volume_info else 0.0
    quote_volume_value = volume_info.get("quote_volume", 0.0) if volume_info else 0.0
    if quote_volume_value == 0.0:
        quote_volume_value = price_info.get("quote_volume", candidate.get("quote_volume", 0))

    if timeframes_data:
        timeframes_with_adx = calculate_symbol_adx_timeframes(timeframes_data)
        indicators_data = {"timeframes": timeframes_with_adx}
    else:
        indicators_data = {}

    market_state[symbol_upper] = {
        "price": price_info.get("price", candidate.get("price", candidate.get("last_price", 0))),
        "name": candidate.get("name", symbol),
        "exchange": candidate.get("exchange", "BINANCE_FUTURES"),
        "contract_symbol": candidate.get("contract_symbol") or f"{symbol_upper}USDT",
        "change_24h": price_info.get("change_24h", candidate.get("change_percent", 0)),
        "base_volume": base_volume_value,
        "quote_volume": quote_volume_value,
        "indicators": indicators_data,
        "previous_close_prices": previous_close_prices,
    }

    logger.info("[%s] 单品种 market_state 构建完成: %s", log_tag, symbol_upper)
    return market_state


# 盯盘通知用快照仅包含以下周期（与全量行情 8 周期解耦，减小 metadata / 合并后体积）
_NOTIFY_SNAPSHOT_TIMEFRAMES: Tuple[str, ...] = ("5m", "15m", "30m", "1h")
# 正文 filter：匹配不到时，群消息仅用以下周期各 1 根 K（不含 30m）
_NOTIFY_MSG_INTERVALS_UNMATCHED: Tuple[str, ...] = ("5m", "15m", "1h")

# 企微/正文用快照（snap）：每周期只取最近 N 根 K（当前为 1，减小 message 体积）
LOOK_NOTIFY_KLINE_BARS_MESSAGE = 1
# trade_notify 入库全量快照（snap_full）：每周期最近 N 根（保留多根便于复盘）
LOOK_NOTIFY_KLINE_BARS_STORAGE = 3
# 正文 filter 后再确保每周期至多 N 根（当前与 MESSAGE 均为 1）
LOOK_NOTIFY_KLINE_BARS_ALL_INTERVALS = 1

# 策略在 notify 信号里声明周期时使用的字段名（与行情 timeframes 的 key 语义一致，如 "5m"）
# Prompt 建议写在 key_date（如 pattern + timeframe）；顶层 / market_date 仍兼容。
_STRATEGY_INTERVAL_FIELD_NAMES = ("timeframe", "interval", "tf", "period")

# 与 merge_timeframe_klines / strategy_look_prompt 中 8 周期一致
_KNOWN_TIMEFRAME_KEYS = frozenset({"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"})

# 紧凑英文变体 -> canonical
_TF_COMPACT_ALIASES = {
    "5min": "5m",
    "5mins": "5m",
    "15min": "15m",
    "30min": "30m",
    "1min": "1m",
    "1hr": "1h",
    "4hr": "4h",
    "1day": "1d",
    "1week": "1w",
}

# 顺序敏感：先匹配 15m/30m 再 5m/1m，避免「15m」误命中「5m」
_TF_FUZZY_REGEX: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?:^|[^\d])15m(?:[^\d]|$)|15\s*分钟|15\s*分|15\s*min", re.I), "15m"),
    (re.compile(r"(?:^|[^\d])30m(?:[^\d]|$)|30\s*分钟|30\s*分|30\s*min", re.I), "30m"),
    (re.compile(r"(?:^|[^\d])5m(?:[^\d]|$)|5\s*分钟|五分钟|5\s*分|5\s*min", re.I), "5m"),
    (re.compile(r"(?:^|[^\d])1m(?:[^\d]|$)|1\s*分钟|一分钟|1\s*分|1\s*min", re.I), "1m"),
    (re.compile(r"(?:^|[^\d])4h(?:[^\d]|$)|4\s*小时|四\s*小时|4\s*hr", re.I), "4h"),
    (re.compile(r"(?:^|[^\d])1h(?:[^\d]|$)|1\s*小时|一小时|60\s*分钟|60\s*min", re.I), "1h"),
    (re.compile(r"(?:^|[^\d])1d(?:[^\d]|$)|1\s*天|一日|日线", re.I), "1d"),
    (re.compile(r"(?:^|[^\d])1w(?:[^\d]|$)|1\s*周|一周|周线", re.I), "1w"),
)


def _normalize_timeframe_label(raw: Optional[str]) -> str:
    """空白/大小写归一（用于与快照 key 直接比对）。"""
    if not raw or not isinstance(raw, str):
        return ""
    return raw.strip().lower().replace(" ", "").replace("　", "")


def _timeframe_raw_to_canonical(raw: Optional[str]) -> Optional[str]:
    """
    将策略/模型写的周期文案转为与行情 timeframes 一致的 canonical key（如 5m）。
    支持 5m、5分钟、五分钟、5min、1小时、60分钟 等模糊说法。
    """
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    compact = re.sub(r"[\s　]+", "", s.lower())
    if compact in _KNOWN_TIMEFRAME_KEYS:
        return compact
    if compact in _TF_COMPACT_ALIASES:
        return _TF_COMPACT_ALIASES[compact]
    sl = s.lower()
    for rx, canon in _TF_FUZZY_REGEX:
        if rx.search(sl):
            return canon
    return None


def _interval_field_from_mapping(m: Dict[str, Any]) -> Optional[str]:
    """从单层 dict 取 timeframe/interval/tf/period 中第一个非空字符串。"""
    for key in _STRATEGY_INTERVAL_FIELD_NAMES:
        v = m.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _resolve_timeframe_in_map(raw: Optional[str], timeframes: Dict[str, Any]) -> Optional[str]:
    """
    将策略给出的周期文案与快照 indicators.timeframes 的实际 key 对齐。
    先模糊归一成 canonical，再命中字典 key；否则再试与 key 的大小写不敏感相等。
    """
    if not raw or not isinstance(timeframes, dict) or not timeframes:
        return None
    canon = _timeframe_raw_to_canonical(raw)
    if canon and canon in timeframes:
        return canon
    needle = _normalize_timeframe_label(raw)
    if needle:
        for k in timeframes.keys():
            if _normalize_timeframe_label(str(k)) == needle:
                return str(k)
    return None


def interval_from_strategy_notify_signal(dec: Dict[str, Any]) -> Optional[str]:
    """
    从策略返回的 notify 条目中取出「信号相关周期」原始字符串，供 _resolve_timeframe_in_map 使用。

    读取顺序（与 strategy_look_prompt 一致，优先 key_date）：
    1. key_date 内：timeframe / interval / tf / period（Prompt 示例：key_date 含 pattern、timeframe）
    2. 本条决策顶层同名字段
    3. market_date 内同名字段

    取到第一个非空字符串即返回；均未设置则返回 None（通知带全周期 K 线）。
    """
    if not isinstance(dec, dict):
        return None
    kd = dec.get("key_date")
    if isinstance(kd, dict):
        hit = _interval_field_from_mapping(kd)
        if hit:
            return hit
    hit = _interval_field_from_mapping(dec)
    if hit:
        return hit
    md = dec.get("market_date")
    if isinstance(md, dict):
        hit = _interval_field_from_mapping(md)
        if hit:
            return hit
    return None


def infer_notify_focus_interval(dec: Dict[str, Any]) -> Optional[str]:
    """兼容旧名：等同 interval_from_strategy_notify_signal。"""
    return interval_from_strategy_notify_signal(dec)


# 通知正文不携带的 K 线 indicators 顶层键（与策略合并后也会从 indicators 顶层去掉）
_NOTIFY_DROP_INDICATOR_KEYS = frozenset({"adx", "vol"})


def _notify_indicators_drop_adx_vol(raw: Dict[str, Any]) -> Dict[str, Any]:
    """从单根 K 的 indicators 中去掉 adx、vol 指标块；其余指标原样保留。"""
    out = copy.deepcopy(raw)
    for k in _NOTIFY_DROP_INDICATOR_KEYS:
        out.pop(k, None)
    return out


def _trim_kline_bar_for_notify(bar: Dict[str, Any]) -> Dict[str, Any]:
    """单根 K 线（企微/正文）：时间、open、indicators（不含 adx/vol）；不含 high/low/close/volume 以缩小体积。"""
    if not isinstance(bar, dict):
        return {}
    t = bar.get("time")
    if t is None:
        t = bar.get("open_time_dt_str") or bar.get("open_time")
    out: Dict[str, Any] = {"time": t}
    if bar.get("open") is not None:
        out["open"] = bar.get("open")
    raw_ind = bar.get("indicators")
    if isinstance(raw_ind, dict) and raw_ind:
        out["indicators"] = _notify_indicators_drop_adx_vol(raw_ind)
    return out


def _kline_bar_for_storage(bar: Dict[str, Any]) -> Dict[str, Any]:
    """单根 K 线（trade_notify 落库）：保留行情侧完整字段（开高低收、量、时间戳及 indicators 等）。"""
    if not isinstance(bar, dict):
        return {}
    return copy.deepcopy(bar)


def _trim_market_snapshot(
    market_state: Dict,
    symbol_key: str,
    *,
    only_intervals: Optional[Tuple[str, ...]],
    full_kline_bars: bool = False,
) -> Dict:
    """
    构造盯盘用快照基座。
    - only_intervals 为 None：保留行情中的全部周期（落 trade_notify / 队列入库）。
    - only_intervals 为 _NOTIFY_SNAPSHOT_TIMEFRAMES：仅 5m/15m/30m/1h（企微正文与 filter 输入）。
    - full_kline_bars=True：每周期最多 LOOK_NOTIFY_KLINE_BARS_STORAGE 根，深拷贝原 bar（含 OHLCV）。
    - full_kline_bars=False：每周期最多 LOOK_NOTIFY_KLINE_BARS_MESSAGE 根，精简条（仅正文）。
    """
    sym_u = symbol_key.strip().upper()
    payload = market_state.get(sym_u) or market_state.get(symbol_key) or {}
    if not isinstance(payload, dict):
        return {}
    out: Dict[str, Any] = {
        "price": payload.get("price"),
        "contract_symbol": payload.get("contract_symbol"),
    }
    ind = payload.get("indicators") or {}
    tf = (ind.get("timeframes") or {}) if isinstance(ind, dict) else {}
    trimmed_tf: Dict[str, Any] = {}
    if not isinstance(tf, dict):
        out["indicators"] = {"timeframes": trimmed_tf}
        return out

    kline_fn = _kline_bar_for_storage if full_kline_bars else _trim_kline_bar_for_notify
    max_klines = LOOK_NOTIFY_KLINE_BARS_STORAGE if full_kline_bars else LOOK_NOTIFY_KLINE_BARS_MESSAGE

    def _one_interval(interval: str, block: Dict[str, Any], omit_empty: bool) -> None:
        kl = block.get("klines") or []
        if not isinstance(kl, list) or not kl:
            if not omit_empty:
                trimmed_tf[interval] = {"klines": []}
            return
        n = min(max_klines, len(kl))
        tail = kl[-n:]
        trimmed_tf[interval] = {"klines": [kline_fn(b) for b in tail if isinstance(b, dict)]}

    if only_intervals is None:
        for interval, block in tf.items():
            if not isinstance(block, dict):
                continue
            _one_interval(str(interval), block, omit_empty=False)
    else:
        for interval in only_intervals:
            block = tf.get(interval)
            if not isinstance(block, dict):
                continue
            _one_interval(interval, block, omit_empty=True)

    out["indicators"] = {"timeframes": trimmed_tf}
    return out


def trim_market_snapshot_full_for_storage(market_state: Dict, symbol_key: str) -> Dict:
    """trade_notify.extra / signal_result / 队列 snap_full：全周期；每周期最近 LOOK_NOTIFY_KLINE_BARS_STORAGE 根完整 K。"""
    return _trim_market_snapshot(
        market_state, symbol_key, only_intervals=None, full_kline_bars=True
    )


def trim_market_snapshot_for_message(market_state: Dict, symbol_key: str) -> Dict:
    """企微群消息正文与 filter_notify 输入：仅 5m / 15m / 30m / 1h；每周期最近 LOOK_NOTIFY_KLINE_BARS_MESSAGE 根 K。"""
    return _trim_market_snapshot(market_state, symbol_key, only_intervals=_NOTIFY_SNAPSHOT_TIMEFRAMES)


def trim_market_snapshot_for_notify(market_state: Dict, symbol_key: str) -> Dict:
    """兼容旧名，等同 trim_market_snapshot_for_message。"""
    return trim_market_snapshot_for_message(market_state, symbol_key)


def _subset_snap_timeframes(
    base_snap: Dict[str, Any], interval_keys: Tuple[str, ...]
) -> Dict[str, Any]:
    """从正文基座快照中只保留指定周期键（顺序与 interval_keys 一致），其余顶层字段保留。"""
    if not isinstance(base_snap, dict):
        return {}
    tf = ((base_snap.get("indicators") or {}).get("timeframes")) or {}
    trimmed: Dict[str, Any] = {}
    if isinstance(tf, dict):
        for k in interval_keys:
            if k in tf:
                trimmed[k] = tf[k]
    return {
        "price": base_snap.get("price"),
        "contract_symbol": base_snap.get("contract_symbol"),
        "indicators": {"timeframes": trimmed},
    }


def _snap_limit_klines_per_timeframe(snap: Dict[str, Any], max_bars: int) -> Dict[str, Any]:
    """复制 snap，并将各周期 klines 截为末尾最多 max_bars 根（用于匹配/未匹配不同根数）。"""
    if max_bars < 1 or not isinstance(snap, dict):
        return snap
    out = copy.deepcopy(snap)
    tfw = ((out.get("indicators") or {}).get("timeframes")) or {}
    if not isinstance(tfw, dict):
        return out
    for interval, block in tfw.items():
        if not isinstance(block, dict):
            continue
        kl = block.get("klines") or []
        if not isinstance(kl, list) or not kl:
            continue
        n = min(max_bars, len(kl))
        tfw[interval] = {**block, "klines": kl[-n:]}
    return out


def filter_notify_snapshot_for_decision(base_snap: Dict[str, Any], dec: Dict[str, Any]) -> Dict[str, Any]:
    """
    企微正文用快照子集（基座已为每周期 1 根精简 K：time + open + indicators）：

    - 策略声明的周期**能**在基座快照中匹配到：正文**只保留该 interval**，最近 **1** 根 K；
    - **匹配不到**：正文保留 **5m / 15m / 1h** 各 1 根。
    """
    if not isinstance(base_snap, dict):
        return {}
    tf = ((base_snap.get("indicators") or {}).get("timeframes")) or {}
    if not isinstance(tf, dict) or not tf:
        return dict(base_snap)
    raw_focus = interval_from_strategy_notify_signal(dec)
    key = _resolve_timeframe_in_map(raw_focus, tf) if raw_focus else None
    if key:
        block = tf.get(key)
        if isinstance(block, dict):
            out: Dict[str, Any] = {
                "price": base_snap.get("price"),
                "contract_symbol": base_snap.get("contract_symbol"),
                "indicators": {"timeframes": {key: block}},
                "focus_interval": key,
            }
        else:
            out = _subset_snap_timeframes(base_snap, _NOTIFY_MSG_INTERVALS_UNMATCHED)
    else:
        out = _subset_snap_timeframes(base_snap, _NOTIFY_MSG_INTERVALS_UNMATCHED)
    return _snap_limit_klines_per_timeframe(out, LOOK_NOTIFY_KLINE_BARS_ALL_INTERVALS)


def _merge_indicators_preserve_timeframes(base_i: Any, strat_i: Any) -> Any:
    """
    合并策略 market_date 中的 indicators：不得用策略侧 dict 覆盖快照里已带的
    indicators.timeframes（全量 K 线指标树）；策略多写的键（如单独汇总的 macd）并入同级。
    """
    if not isinstance(base_i, dict):
        base_i = {}
    out = copy.deepcopy(base_i)
    if not isinstance(strat_i, dict) or not strat_i:
        return out
    for k, v in strat_i.items():
        if k == "timeframes" and isinstance(out.get("timeframes"), dict):
            continue
        out[k] = copy.deepcopy(v)
    return out


def merge_market_date_for_notify_message(filtered_snap: Dict[str, Any], dec: Dict[str, Any]) -> Dict[str, Any]:
    """
    K 线快照与策略 market_date 合并：顶层标量（timeframe、current_macd_dif 等）叠加；
    若策略也提供 indicators，与快照 indicators 深度合并且保留 timeframes 全量指标。
    """
    base = dict(filtered_snap) if isinstance(filtered_snap, dict) else {}
    strat = dec.get("market_date") if isinstance(dec, dict) else None
    if not isinstance(strat, dict) or not strat:
        return base
    merged: Dict[str, Any] = {**base}
    for k, v in strat.items():
        if k == "indicators":
            continue
        merged[k] = v
    s_ind = strat.get("indicators")
    b_ind = base.get("indicators")
    if isinstance(s_ind, dict) and s_ind:
        merged["indicators"] = _merge_indicators_preserve_timeframes(b_ind, s_ind)
    elif isinstance(b_ind, dict):
        merged["indicators"] = copy.deepcopy(b_ind)
    mi = merged.get("indicators")
    if isinstance(mi, dict):
        for k in _NOTIFY_DROP_INDICATOR_KEYS:
            mi.pop(k, None)
    return merged


class LookEngine:
    """
    单 symbol 盯盘：使用 build_single_symbol_market_state 拉取行情，不调用 TradingEngine._build_market_state_for_candidates。
    """

    def __init__(
        self,
        db,
        market_fetcher: MarketDataFetcher,
        model_id: int,
    ):
        self.db = db
        self.market_fetcher = market_fetcher
        self.strategys_db = StrategysDatabase(pool=db._pool if hasattr(db, "_pool") else None)
        self.market_look_db = MarketLookDatabase(pool=db._pool if hasattr(db, "_pool") else None)
        self.trade_notify_db = TradeNotifyDatabase(pool=db._pool if hasattr(db, "_pool") else None)
        self.strategy_trader = StrategyTrader(db=db, model_id=model_id)

    def build_market_state_for_symbol(self, symbol: str) -> Dict:
        """仅请求当前 symbol 对应合约的行情（SDK 价格 + DB 成交额 + 8 周期 K 线 + ADX；不含全市场聚合 market_indicators）。"""
        c = _candidate_for_symbol(symbol)
        tag = f"LookEngine m={self.strategy_trader.model_id}"
        return build_single_symbol_market_state(
            self.market_fetcher,
            c,
            log_tag=tag,
        )

    def execute_look_row(self, row: Dict) -> Dict:
        """
        处理一条 market_look 记录（调用方应已筛选 RUNNING）。

        Returns:
            摘要 dict：notify_sent, decisions, error 等
        """
        row_id = row.get("id")
        symbol = row.get("symbol") or ""
        strategy_id = row.get("strategy_id")
        summary: Dict[str, Any] = {"row_id": row_id, "notify_sent": False}

        strategy = self.strategys_db.get_strategy_by_id(strategy_id)
        if not strategy:
            msg = f"策略不存在: {strategy_id}"
            logger.error(msg)
            self.market_look_db.update_signal_result(row_id, msg)
            summary["error"] = msg
            return summary

        sym_key = _normalize_symbol_key(symbol)
        try:
            market_state = self.build_market_state_for_symbol(symbol)
        except Exception as e:
            logger.error("构建 market_state 失败 %s: %s", symbol, e)
            self.market_look_db.update_signal_result(row_id, f"market_state error: {e}")
            summary["error"] = str(e)
            return summary

        if not market_state:
            w = f"无行情数据: {symbol}"
            logger.warning(w)
            self.market_look_db.update_signal_result(row_id, w)
            summary["warning"] = w
            return summary

        res = self.strategy_trader.make_look_decision(strategy, market_state, sym_key)
        decisions = res.get("decisions") or {}
        summary["decisions"] = decisions

        notify_payloads = self._extract_notify_decisions(decisions, sym_key)

        if notify_payloads:
            snap_message = trim_market_snapshot_for_message(market_state, sym_key)
            snap_full = trim_market_snapshot_full_for_storage(market_state, sym_key)
            queue_payload = {
                "strategy_id": strategy_id,
                "sym_key": sym_key,
                "snap": snap_message,
                "snap_full": snap_full,
                "decisions": decisions,
                "notify_payloads": notify_payloads,
            }
            stub = {
                "ts": _utc8_now_iso(),
                "notify": "queued",
                "notify_queue": True,
                "queue_payload": queue_payload,
                "decisions": decisions,
                "market_look_id": row_id,
                "strategy_id": strategy_id,
            }
            self.market_look_db.update_signal_result(
                row_id,
                json.dumps(stub, ensure_ascii=False, default=str),
            )
            self.market_look_db.update_status(row_id, EXECUTION_SENDING)
            from trade.look_notify_queue import JOB_KIND_LOOK_NOTIFY, enqueue_look_notify

            enqueue_look_notify(
                {
                    "kind": JOB_KIND_LOOK_NOTIFY,
                    "market_look_id": str(row_id),
                    "queue_payload": queue_payload,
                    "retries": 0,
                }
            )
            summary["notify_sent"] = True
            summary["notify_queued"] = True
            summary["execution_ended"] = "queued_notify"
            return summary

        # 无 notify：若已超过 ended_at（上海时区），落库超时通知并结束任务（仅一次）
        if _is_deadline_passed(row):
            timeout_ids = self._emit_look_timeout_notify(
                row, strategy, sym_key, decisions, market_state
            )
            summary["trade_notify_ids"] = timeout_ids
            summary["notify_sent"] = bool(timeout_ids)
            self.market_look_db.update_signal_result(
                row_id,
                json.dumps(
                    {
                        "ts": _utc8_now_iso(),
                        "notify": False,
                        "execution_ended": "timeout",
                        "reason": "deadline_passed",
                        "message": "策略已经执行超时，没有找到任何交易信号",
                        "decisions": decisions,
                        "trade_notify_ids": timeout_ids,
                        "market_look_id": row_id,
                        "strategy_id": strategy_id,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            )
            tn_ids = timeout_ids or []
            end_msg = (
                f"[超时结束] 当前时间已超过计划结束时间 ended_at，策略未返回 notify 信号。"
                f" 已写入 trade_notify 超时说明；trade_notify_ids={tn_ids}。"
            )
            self.market_look_db.update_status(
                row_id, EXECUTION_ENDED, ended_at=_now_shanghai_naive(), end_log=end_msg
            )
            summary["execution_ended"] = "timeout"
        return summary

    def process_notify_queue_payload(self, row_id: str, queue_payload: Dict[str, Any]) -> bool:
        """
        异步通知线程调用：先调 trade-monitor 推送，成功后再落 trade_notify 并置 ENDED。
        多条 notify 决策合并为一条消息，避免部分 HTTP 成功导致重试时重复推送。
        """
        from trade.common.trade_monitor_client import post_event_notify

        base = (getattr(app_config, "TRADE_MONITOR_BASE_URL", None) or "").strip()
        strategy_id = queue_payload.get("strategy_id")
        strategy = self.strategys_db.get_strategy_by_id(strategy_id)
        if not strategy:
            logger.error("queued notify: strategy not found id=%s", strategy_id)
            return False
        sym_key = queue_payload.get("sym_key") or ""
        snap = queue_payload.get("snap") or {}
        snap_full = queue_payload.get("snap_full") or snap
        notify_payloads = queue_payload.get("notify_payloads") or []
        decisions = queue_payload.get("decisions") or {}
        parts: List[str] = []
        for dec in notify_payloads:
            if not isinstance(dec, dict):
                continue
            dec_copy = dict(dec)
            # 正文与企微仅基于 5m/15m/30m/1h 快照
            filtered = filter_notify_snapshot_for_decision(snap, dec_copy)
            dec_copy["market_date"] = merge_market_date_for_notify_message(filtered, dec_copy)
            body_lines = [
                f"盯盘任务ID (market_look.id): {row_id}",
                f"策略ID (strategys.id): {strategy_id}",
                f"策略名称: {strategy.get('strategy_name') or ''}",
                f"交易对: {sym_key}",
                f"合约: {dec_copy.get('symbol') or sym_key}",
                f"价格: {dec_copy.get('price')}",
                f"说明: {dec_copy.get('justification')}",
                f"market_date: {_truncate_json_for_notify_line(dec_copy.get('market_date'))}",
            ]
            parts.append("\n".join(body_lines))
        if not parts:
            logger.warning("queued notify: empty payloads market_look_id=%s", row_id)
            return False

        title = f"盯盘通知 [{sym_key}] {strategy.get('strategy_name') or ''}".strip()
        message = "\n\n---\n\n".join(parts)
        extra = {
            "market_look_id": row_id,
            "strategy_id": strategy_id,
            "symbol": sym_key,
            "notify_payloads": notify_payloads,
            "market_snapshot": snap_full,
            "kind": "look_notify_queued",
        }
        try:
            snap_msg_json = json.dumps(snap, ensure_ascii=False, default=str)
            snap_full_json = json.dumps(snap_full, ensure_ascii=False, default=str)
            extra_json = json.dumps(extra, ensure_ascii=False, default=str)
            logger.info(
                "[look notify] 体积: 群消息用快照(4周期) JSON %s 字符 | 落库全量快照 JSON %s 字符 | "
                "metadata(extra) JSON %s 字符 | message 正文 %s 字符 | title %s 字符",
                len(snap_msg_json),
                len(snap_full_json),
                len(extra_json),
                len(message),
                len(title),
            )
        except Exception as sz_err:
            logger.debug("look notify size log skipped: %s", sz_err)

        alert_id_tm: Optional[int] = None
        if not base:
            logger.warning(
                "TRADE_MONITOR_BASE_URL 未配置，跳过 HTTP 推送，仅落库 trade_notify (market_look=%s)",
                row_id,
            )
            ok = True
        else:
            ok, alert_id_tm = post_event_notify(title, message, metadata=extra)
        if not ok:
            return False

        nid = self.trade_notify_db.insert_look_notify(
            market_look_id=str(row_id) if row_id is not None else None,
            strategy_id=str(strategy_id),
            strategy_name=strategy.get("strategy_name"),
            symbol=sym_key,
            title=title,
            message=message,
            extra=extra,
        )
        self.market_look_db.update_signal_result(
            row_id,
            json.dumps(
                {
                    "ts": _utc8_now_iso(),
                    "notify": True,
                    "decisions": decisions,
                    "market_snapshot": snap_full,
                    "market_look_id": row_id,
                    "strategy_id": strategy_id,
                    "trade_notify_ids": [nid],
                    "execution_ended": "notified",
                    "notify_channel": "trade_monitor",
                },
                ensure_ascii=False,
                default=str,
            ),
        )
        if not base:
            end_msg = (
                f"[正常结束] 未配置 TRADE_MONITOR_BASE_URL，已跳过 trade-monitor HTTP；"
                f"已落库 trade_notify id={nid}。"
            )
        else:
            tm_part = (
                f"trade-monitor 告警记录 alertId={alert_id_tm}" if alert_id_tm is not None else "trade-monitor 已接收"
            )
            end_msg = (
                f"[正常结束] 已通过 trade-monitor 推送事件并落库 trade_notify。"
                f" trade_notify.id={nid}；{tm_part}。"
            )
        self.market_look_db.update_status(
            row_id, EXECUTION_ENDED, ended_at=_now_shanghai_naive(), end_log=end_msg
        )
        return True

    def abandon_notify_queue(self, row_id: str, reason: str) -> None:
        """重试用尽：结束任务并记录原因。写入 engine 子对象，保留已有 decisions 等策略输出。"""
        row = self.market_look_db.get_by_id(str(row_id))
        prev: Dict[str, Any] = {}
        if row and row.get("signal_result"):
            try:
                raw = row["signal_result"]
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(parsed, dict):
                    prev = parsed
            except Exception:
                prev = {}
        engine_block = {
            "ts": _utc8_now_iso(),
            "notify": False,
            "notify_queue_aborted": True,
            "reason": reason,
            "execution_ended": reason,
        }
        merged = {**prev, "engine": engine_block}
        self.market_look_db.update_signal_result(
            row_id,
            json.dumps(merged, ensure_ascii=False, default=str),
        )
        end_msg = (
            f"[异常结束] 异步通知 trade-monitor 重试耗尽，任务终止。"
            f" reason={reason}（通常为推送失败或策略记录缺失）。"
        )
        self.market_look_db.update_status(
            row_id, EXECUTION_ENDED, ended_at=_now_shanghai_naive(), end_log=end_msg
        )

    def _emit_look_timeout_notify(
        self,
        row: Dict,
        strategy: Dict,
        sym_key: str,
        decisions: Dict,
        market_state: Dict,
    ) -> List[int]:
        """已超过 ended_at 时落库一条超时说明（trade_notify），返回 id 列表。"""
        row_id = row.get("id")
        strategy_id = row.get("strategy_id")
        snap = trim_market_snapshot_full_for_storage(market_state, sym_key)
        deadline = _parse_row_ended_at(row)
        now_s = _now_shanghai_naive()
        title = f"盯盘超时 [{sym_key}] {strategy.get('strategy_name') or ''}".strip()
        body_lines = [
            f"盯盘任务ID (market_look.id): {row_id}",
            f"策略ID (strategys.id): {strategy_id}",
            f"策略名称: {strategy.get('strategy_name') or ''}",
            f"交易对: {sym_key}",
            "说明: 策略已经执行超时，没有找到任何交易信号",
            f"ended_at(截止): {deadline}",
            f"当前时间: {now_s}",
        ]
        message = "\n".join(body_lines)
        extra = {
            "market_look_id": row_id,
            "strategy_id": strategy_id,
            "symbol": sym_key,
            "kind": "look_timeout",
            "decisions": decisions,
            "market_snapshot": snap,
        }
        nid = self.trade_notify_db.insert_look_notify(
            market_look_id=str(row_id) if row_id is not None else None,
            strategy_id=str(strategy_id),
            strategy_name=strategy.get("strategy_name"),
            symbol=sym_key,
            title=title,
            message=message,
            extra=extra,
        )
        return [nid]

    def _extract_notify_decisions(self, decisions: Dict, sym_key: str) -> List[Dict]:
        out: List[Dict] = []
        if not isinstance(decisions, dict):
            return out
        sym_u = sym_key.strip().upper()
        for k, val in decisions.items():
            if str(k).upper() != sym_u:
                continue
            items: List[Dict] = []
            if isinstance(val, list):
                items = [x for x in val if isinstance(x, dict)]
            elif isinstance(val, dict):
                items = [val]
            for d in items:
                sig = (d.get("signal") or "").lower()
                if sig == "notify":
                    out.append(d)
        return out


def _utc8_now_iso() -> str:
    dt = datetime.now(timezone(timedelta(hours=8)))
    return dt.strftime("%Y-%m-%d %H:%M:%S")
