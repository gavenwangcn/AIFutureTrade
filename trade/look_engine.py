"""
盯盘引擎：每次只针对一个 symbol 拉取实时价、多周期 K 线与指标（逻辑与 TradingEngine 中单品种分支一致），
不通过 _build_market_state_for_candidates 批量接口。触发 notify 时写入 trade_notify 表（不使用 alert_records）。
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import numpy as np

import trade.common.config as app_config
from trade.common.database.database_market_look import (
    EXECUTION_ENDED,
    MarketLookDatabase,
)
from trade.common.database.database_strategys import StrategysDatabase
from trade.common.database.database_trade_notify import TradeNotifyDatabase
from trade.market import calculate_market_indicators
from trade.market.market_data import MarketDataFetcher
from trade.market.market_index import MarketIndexCalculator
from trade.market.indicator_rounding import round_indicator_4
from trade.strategy.strategy_trader import StrategyTrader

logger = logging.getLogger(__name__)

_TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")


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

    try:
        klines_data_for_indicators: Dict[str, Any] = {}
        state_info = market_state[symbol_upper]
        indicators = state_info.get("indicators", {})
        timeframes = indicators.get("timeframes", {})
        klines = None
        for tf in ["1h", "4h", "30m", "15m"]:
            tf_data = timeframes.get(tf, {})
            tf_klines = tf_data.get("klines", [])
            if tf_klines and len(tf_klines) > 0:
                klines = tf_klines
                break
        if klines and len(klines) > 0:
            high_prices = []
            low_prices = []
            close_prices = []
            for kline in klines:
                if isinstance(kline, dict):
                    high_prices.append(float(kline.get("high", 0)))
                    low_prices.append(float(kline.get("low", 0)))
                    close_prices.append(float(kline.get("close", 0)))
            if high_prices and low_prices and close_prices:
                klines_data_for_indicators[symbol_upper] = {
                    "high": high_prices,
                    "low": low_prices,
                    "close": close_prices,
                }
        if klines_data_for_indicators:
            market_indicators = calculate_market_indicators(klines_data_for_indicators)
            market_state[symbol_upper]["market_indicators"] = market_indicators
        else:
            market_state[symbol_upper]["market_indicators"] = {}
    except Exception as e:
        logger.error("[%s] market_indicators 计算失败: %s", log_tag, e, exc_info=True)
        market_state[symbol_upper]["market_indicators"] = {}

    logger.info("[%s] 单品种 market_state 构建完成: %s", log_tag, symbol_upper)
    return market_state


def trim_market_snapshot_for_notify(market_state: Dict, symbol_key: str, max_klines: int = 5) -> Dict:
    """各周期仅保留最近 max_klines 根 K 线，用于 market_date 字段。"""
    sym_u = symbol_key.strip().upper()
    payload = market_state.get(sym_u) or market_state.get(symbol_key) or {}
    if not isinstance(payload, dict):
        return {}
    out = {
        "price": payload.get("price"),
        "contract_symbol": payload.get("contract_symbol"),
        "quote_volume": payload.get("quote_volume"),
        "base_volume": payload.get("base_volume"),
        "change_24h": payload.get("change_24h"),
        "previous_close_prices": payload.get("previous_close_prices"),
    }
    ind = payload.get("indicators") or {}
    tf = (ind.get("timeframes") or {}) if isinstance(ind, dict) else {}
    trimmed_tf = {}
    if isinstance(tf, dict):
        for interval, block in tf.items():
            if not isinstance(block, dict):
                continue
            kl = block.get("klines") or []
            if isinstance(kl, list) and kl:
                block = dict(block)
                block["klines"] = kl[:max_klines]
            trimmed_tf[interval] = block
    out["indicators"] = {"timeframes": trimmed_tf}
    out["market_indicators"] = payload.get("market_indicators")
    return out


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
        """仅请求当前 symbol 对应合约的行情（SDK 价格 + DB 成交额 + 8 周期 K 线 + ADX + market_indicators）。"""
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
            snap = trim_market_snapshot_for_notify(market_state, sym_key)

            trade_notify_ids: List[int] = []
            for dec in notify_payloads:
                if dec.get("market_date") is None:
                    dec["market_date"] = snap
                title = f"盯盘通知 [{sym_key}] {strategy.get('strategy_name') or ''}".strip()
                body_lines = [
                    f"盯盘任务ID (market_look.id): {row_id}",
                    f"策略ID (strategys.id): {strategy_id}",
                    f"策略名称: {strategy.get('strategy_name') or ''}",
                    f"交易对: {sym_key}",
                    f"合约: {dec.get('symbol') or sym_key}",
                    f"价格: {dec.get('price')}",
                    f"说明: {dec.get('justification')}",
                    f"market_date: {json.dumps(dec.get('market_date'), ensure_ascii=False, default=str)[:2000]}",
                ]
                message = "\n".join(body_lines)
                extra = {
                    "market_look_id": row_id,
                    "strategy_id": strategy_id,
                    "symbol": sym_key,
                    "decision": dec,
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
                trade_notify_ids.append(nid)
                summary["notify_sent"] = True

            summary["trade_notify_ids"] = trade_notify_ids

            self.market_look_db.update_signal_result(
                row_id,
                json.dumps(
                    {
                        "ts": _utc8_now_iso(),
                        "notify": True,
                        "decisions": decisions,
                        "snapshot_trimmed": snap,
                        "market_look_id": row_id,
                        "strategy_id": strategy_id,
                        "trade_notify_ids": trade_notify_ids,
                        "execution_ended": "notified",
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            )
            ended_ts = _now_shanghai_naive()
            self.market_look_db.update_status(row_id, EXECUTION_ENDED, ended_at=ended_ts)
            summary["execution_ended"] = "notified"
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
            self.market_look_db.update_status(row_id, EXECUTION_ENDED, ended_at=_now_shanghai_naive())
            summary["execution_ended"] = "timeout"
        return summary

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
        snap = trim_market_snapshot_for_notify(market_state, sym_key)
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
