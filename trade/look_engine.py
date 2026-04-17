"""
盯盘引擎：每次只针对一个 symbol 拉取实时价、多周期 K 线与指标（逻辑与 TradingEngine 中单品种分支一致），
不通过 _build_market_state_for_candidates 批量接口。触发 notify 或超时结束时：落库 SENDING、并入 look_notify 异步队列，由后台线程经 trade-monitor 推送后再写入 trade_notify 并置 ENDED。
超时结束（无 notify 且已过 ended_at）：与 notify 相同，置 SENDING 并入 look_notify 队列，由后台线程 post_event_notify 后落库 trade_notify 并置 ENDED。
通知消息与 trade_notify.extra 不包含服务端拉取的市场 K 线快照，仅保留策略决策字段（如 justification、price、策略自定义 market_date）。
"""

import copy
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

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
    与 TradingEngine._merge_timeframe_data 相同：合并多周期 K 线（仅 klines），单合约。
    不包含周线 1w。
    """
    return market_fetcher.merge_timeframe_klines_for_contract(contract_symbol)


def build_single_symbol_market_state(
    market_fetcher: MarketDataFetcher,
    candidate: Dict,
    log_tag: str = "LookEngine",
) -> Dict:
    """
    仅构建一个 symbol 的 market_state 条目（与 TradingEngine 中单候选分支逻辑一致），
    不经过 _build_market_state_for_candidates。
    K 线指标（含 ADX）由 binance-service 带指标接口提供，不在此本地计算。
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
        indicators_data = {"timeframes": timeframes_data}
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


# 合并策略 market_date 时，从 indicators 顶层去掉的键（避免冗余大块）
_NOTIFY_DROP_INDICATOR_KEYS = frozenset({"adx", "vol"})


def _merge_indicators_preserve_timeframes(base_i: Any, strat_i: Any) -> Any:
    """
    合并策略 market_date 中的 indicators：若 base 已有 indicators.timeframes，则不被策略覆盖；
    策略多写的键（如单独汇总的 macd）并入同级。
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
    合并策略 notify 中的 market_date（可选与 base 叠加）。盯盘通知不再附带服务端 K 线快照，base 通常为空 {}。
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
        """仅请求当前 symbol 对应合约的行情（SDK 价格 + DB 成交额 + 7 周期带指标 K 线；不含全市场聚合 market_indicators）。"""
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
            queue_payload = {
                "strategy_id": strategy_id,
                "sym_key": sym_key,
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

        # 无 notify：若已超过 ended_at（上海时区），与 notify 相同：SENDING + 入队，由 look_notify worker 异步推送并落库
        if _is_deadline_passed(row):
            queue_payload = self._build_look_timeout_queue_payload(
                row, strategy, sym_key, decisions, market_state
            )
            stub = {
                "ts": _utc8_now_iso(),
                "notify": False,
                "notify_queue": True,
                "queue_kind": "look_timeout",
                "queue_payload": queue_payload,
                "reason": "deadline_passed",
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
            summary["execution_ended"] = "queued_look_timeout"
        return summary

    def process_notify_queue_payload(self, row_id: str, queue_payload: Dict[str, Any]) -> bool:
        """
        异步通知线程调用：先调 trade-monitor 推送，成功后再落 trade_notify 并置 ENDED。
        多条 notify 决策合并为一条消息，避免部分 HTTP 成功导致重试时重复推送。
        """
        if queue_payload.get("payload_kind") == "look_timeout":
            return self._process_look_timeout_queue_payload(row_id, queue_payload)

        from trade.common.trade_monitor_client import post_event_notify

        base = (getattr(app_config, "TRADE_MONITOR_BASE_URL", None) or "").strip()
        strategy_id = queue_payload.get("strategy_id")
        strategy = self.strategys_db.get_strategy_by_id(strategy_id)
        if not strategy:
            logger.error("queued notify: strategy not found id=%s", strategy_id)
            return False
        sym_key = queue_payload.get("sym_key") or ""
        notify_payloads = queue_payload.get("notify_payloads") or []
        decisions = queue_payload.get("decisions") or {}
        parts: List[str] = []
        for dec in notify_payloads:
            if not isinstance(dec, dict):
                continue
            dec_copy = dict(dec)
            merged_md = merge_market_date_for_notify_message({}, dec_copy)
            dec_copy["market_date"] = merged_md
            body_lines = [
                f"盯盘任务ID (market_look.id): {row_id}",
                f"策略ID (strategys.id): {strategy_id}",
                f"策略名称: {strategy.get('strategy_name') or ''}",
                f"交易对: {sym_key}",
                f"合约: {dec_copy.get('symbol') or sym_key}",
                f"价格: {dec_copy.get('price')}",
                f"说明: {dec_copy.get('justification')}",
            ]
            if merged_md:
                body_lines.append(f"market_date: {_truncate_json_for_notify_line(merged_md)}")
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
            "kind": "look_notify_queued",
        }
        logger.info(
            "[look notify] 推送 trade-monitor market_look_id=%s | title_len=%s message_len=%s",
            row_id,
            len(title),
            len(message),
        )

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

    def _build_look_timeout_queue_payload(
        self,
        row: Dict,
        strategy: Dict,
        sym_key: str,
        decisions: Dict,
        _market_state: Dict,
    ) -> Dict[str, Any]:
        """已超过 ended_at：构造入队 payload（由 look_notify worker 推送并落库）。超时通知不落库 K 线快照。"""
        row_id = row.get("id")
        strategy_id = row.get("strategy_id")
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
        }
        return {
            "payload_kind": "look_timeout",
            "strategy_id": strategy_id,
            "strategy_name": strategy.get("strategy_name"),
            "sym_key": sym_key,
            "title": title,
            "message": message,
            "extra": extra,
            "decisions": decisions,
        }

    def _process_look_timeout_queue_payload(self, row_id: str, qp: Dict[str, Any]) -> bool:
        """队列线程：盯盘超时 — post_event_notify → insert_look_notify → ENDED。"""
        from trade.common.trade_monitor_client import post_event_notify

        title = (qp.get("title") or "").strip()
        message = qp.get("message") or ""
        extra = qp.get("extra")
        if not isinstance(extra, dict):
            extra = {}
        strategy_id = qp.get("strategy_id")
        strategy_name = qp.get("strategy_name")
        sym_key = qp.get("sym_key") or ""

        base = (getattr(app_config, "TRADE_MONITOR_BASE_URL", None) or "").strip()
        if not base:
            logger.warning(
                "TRADE_MONITOR_BASE_URL 未配置，盯盘超时队列任务跳过 HTTP，仅落库 trade_notify | market_look=%s",
                row_id,
            )
            ok = True
        else:
            ok, _aid = post_event_notify(title, message, metadata=extra)
        if not ok:
            return False

        nid = self.trade_notify_db.insert_look_notify(
            market_look_id=str(row_id) if row_id is not None else None,
            strategy_id=str(strategy_id),
            strategy_name=strategy_name,
            symbol=sym_key,
            title=title,
            message=message,
            extra=extra if extra else None,
        )
        self.market_look_db.update_signal_result(
            row_id,
            json.dumps(
                {
                    "ts": _utc8_now_iso(),
                    "notify": False,
                    "execution_ended": "timeout",
                    "reason": "deadline_passed",
                    "message": "策略已经执行超时，没有找到任何交易信号",
                    "decisions": qp.get("decisions") or {},
                    "trade_notify_ids": [nid],
                    "market_look_id": row_id,
                    "strategy_id": strategy_id,
                    "notify_channel": "trade_monitor",
                },
                ensure_ascii=False,
                default=str,
            ),
        )
        end_msg = (
            f"[超时结束] 当前时间已超过计划结束时间 ended_at，策略未返回 notify 信号。"
            f" 已通过 trade-monitor 异步推送并写入 trade_notify；trade_notify_ids={[nid]}。"
        )
        self.market_look_db.update_status(
            row_id, EXECUTION_ENDED, ended_at=_now_shanghai_naive(), end_log=end_msg
        )
        return True

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
