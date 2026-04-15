"""
卖出策略交易器：按优先级执行 sell 类型策略代码，生成平仓/止盈止损等决策。
"""

import json
import logging
import traceback
from typing import Dict, List, Optional

from trade.strategy.strategy_trader_base import StrategyTraderBase
from trade.strategy.strategy_trader_utils import (
    build_close_price_log_lines,
    dedupe_positions_by_symbol,
    filter_market_state,
    unique_ordered_symbols_from_strings,
)

logger = logging.getLogger(__name__)


class StrategySellTrader(StrategyTraderBase):
    """卖出决策：持仓去重、多策略优先级短路、quantity 按价精度归一。"""

    def make_sell_decision(
        self,
        portfolio: Dict,
        market_state: Dict,
        account_info: Dict,
        model_id: Optional[int] = None,
        conditional_orders: Optional[Dict[str, List[Dict]]] = None,
    ) -> Dict:
        logger.info(
            f"[StrategyTrader] [Model {self.model_id}] 开始生成卖出决策, 持仓数量: {len(portfolio.get('positions') or [])}"
        )

        if not portfolio.get("positions"):
            return {"decisions": {}, "prompt": None, "raw_response": None, "cot_trace": None, "skipped": True}

        effective_model_id = model_id if model_id is not None else self.model_id
        if conditional_orders is None:
            conditional_orders = {}

        model_mapping = self.models_db._get_model_id_mapping()
        strategies = self.strategys_db.get_model_strategies_by_int_id(effective_model_id, "sell", model_mapping)

        if not strategies:
            logger.info(f"[StrategyTrader] [Model {effective_model_id}] 未找到卖出类型策略，返回hold决策")
            return {
                "decisions": {},
                "prompt": None,
                "raw_response": None,
                "cot_trace": "无策略",
                "skipped": True,
            }

        logger.info(f"[StrategyTrader] [Model {effective_model_id}] 找到 {len(strategies)} 个卖出类型策略，开始按优先级执行")

        positions = portfolio.get("positions") or []
        remaining_positions, remaining_symbol_set = dedupe_positions_by_symbol(positions)

        base_portfolio: Dict = dict(portfolio) if isinstance(portfolio, dict) else {}

        final_decisions: Dict[str, List[Dict]] = {}
        used_strategy_names: List[str] = []
        valid_signals = {"sell_to_long", "sell_to_short", "close_position", "stop_loss", "take_profit"}

        for strategy in strategies:
            if not remaining_positions or not remaining_symbol_set:
                break

            strategy_name = strategy.get("strategy_name", "未知策略")
            strategy_code = strategy.get("strategy_code", "")
            priority = strategy.get("priority", 0)

            if not strategy_code or not strategy_code.strip():
                logger.debug(
                    f"[StrategyTrader] [Model {effective_model_id}] 策略 {strategy_name} (优先级: {priority}) 代码为空，跳过"
                )
                continue

            working_portfolio = dict(base_portfolio)
            working_portfolio["positions"] = remaining_positions
            filtered_market_state = filter_market_state(market_state, remaining_symbol_set)

            logger.debug(f"[StrategyTrader] [Model {effective_model_id}] 执行策略: {strategy_name} (优先级: {priority})")

            try:
                try:
                    symbols_for_log = []
                    for p in remaining_positions:
                        sym_u = str(p.get("symbol") or "").upper()
                        if sym_u:
                            symbols_for_log.append(sym_u)
                    symbols_for_log = unique_ordered_symbols_from_strings(symbols_for_log)
                    lines = build_close_price_log_lines(symbols_for_log, filtered_market_state)
                    if lines:
                        logger.info(
                            f"[StrategyTrader] [Model {effective_model_id}] 提交到策略代码(sell/{strategy_name}) 收盘价信息:\n"
                            + "\n".join(lines)
                        )
                except Exception:
                    pass

                try:
                    co = conditional_orders or {}
                    total_co = sum(len(v) for v in (co.values() if isinstance(co, dict) else []))
                    symbols_to_log = [str(p.get("symbol") or "").upper() for p in remaining_positions if p.get("symbol")]
                    symbols_to_log = list(dict.fromkeys(symbols_to_log))
                    logger.info(
                        f"[StrategyTrader] [Model {effective_model_id}] 提交到策略代码(sell/{strategy_name}) 条件单信息: "
                        f"共 {total_co} 个条件单，涉及 {len(co)} 个symbol，keys={list(co.keys())}"
                    )
                    for sym_u in symbols_to_log:
                        orders = co.get(sym_u, []) if isinstance(co, dict) else []
                        if orders:
                            for i, o in enumerate(orders):
                                logger.info(
                                    f"[StrategyTrader] [Model {effective_model_id}] 条件单[{sym_u}][{i}]: "
                                    f"orderType={o.get('orderType')}, positionSide={o.get('positionSide')}, "
                                    f"triggerPrice={o.get('triggerPrice')}, quantity={o.get('quantity')}, algoId={o.get('algoId')}"
                                )
                        else:
                            logger.info(f"[StrategyTrader] [Model {effective_model_id}] 条件单[{sym_u}]: 无（空列表）")
                except Exception as e:
                    logger.debug(f"[StrategyTrader] 打印条件单信息异常: {e}")

                decision_result = self.code_executor.execute_strategy_code(
                    strategy_code=strategy_code,
                    strategy_name=strategy_name,
                    candidates=None,
                    portfolio=working_portfolio,
                    account_info=account_info,
                    market_state=filtered_market_state,
                    decision_type="sell",
                    conditional_orders=conditional_orders,
                )

                if not decision_result or not isinstance(decision_result, dict):
                    logger.info(
                        f"[StrategyTrader] [Model {effective_model_id}] [卖出策略执行] 策略 {strategy_name} (优先级: {priority}) 返回结果无效或为空，继续下一个策略"
                    )
                    logger.debug(
                        f"[StrategyTrader] [Model {effective_model_id}] 策略 {strategy_name} 返回结果无效，继续下一个策略"
                    )
                    continue

                decisions = decision_result.get("decisions", {}) or {}
                if not isinstance(decisions, dict) or not decisions:
                    logger.info(
                        f"[StrategyTrader] [Model {effective_model_id}] [卖出策略执行] 策略 {strategy_name} (优先级: {priority}) 返回的decisions为空或格式不正确，继续下一个策略"
                    )
                    continue

                list_per_symbol = self._decisions_to_list_per_symbol(decisions)
                total_decision_count = sum(len(lst) for lst in list_per_symbol.values())
                logger.info(
                    f"[StrategyTrader] [Model {effective_model_id}] [卖出策略执行] ✓ 策略 {strategy_name} (优先级: {priority}) 执行成功，返回 {len(list_per_symbol)} 个 symbol、共 {total_decision_count} 个交易信号决策"
                )

                for symbol, dec_list in list_per_symbol.items():
                    for dec in dec_list:
                        if isinstance(dec, dict):
                            logger.info(
                                f"[StrategyTrader] [Model {effective_model_id}] [卖出策略执行] [交易信号] "
                                f"策略={strategy_name}, Symbol={symbol}, Signal={dec.get('signal', 'N/A')}, "
                                f"Quantity={dec.get('quantity', 'N/A')}, Price={dec.get('price', 'N/A')}, Reason={dec.get('reason', dec.get('justification', 'N/A'))}"
                            )

                normalized_decisions = self._normalize_quantity_by_price(decisions, filtered_market_state)

                decisions_by_symbol: Dict[str, List[Dict]] = {}
                for sym, dec_list in normalized_decisions.items():
                    sym_upper = str(sym).upper()
                    if not sym_upper:
                        continue
                    decisions_by_symbol[sym_upper] = dec_list

                selected_symbols_this_strategy: List[str] = []

                for p in remaining_positions:
                    try:
                        sym_upper = str(p.get("symbol") or "").upper()
                    except Exception:
                        continue
                    if not sym_upper or sym_upper not in remaining_symbol_set:
                        continue
                    if sym_upper in final_decisions:
                        continue

                    dec_list = decisions_by_symbol.get(sym_upper) or []
                    if not dec_list:
                        continue

                    valid_dec_list = []
                    for dec in dec_list:
                        if not isinstance(dec, dict):
                            continue
                        sig = (dec.get("signal") or "").lower()
                        if sig not in valid_signals:
                            continue
                        dec.setdefault("_strategy_name", strategy_name)
                        dec.setdefault("_strategy_type", "sell")
                        valid_dec_list.append(dec)
                    if not valid_dec_list:
                        try:
                            signals = [(d.get("signal") if isinstance(d, dict) else None) for d in dec_list]
                        except Exception:
                            signals = []
                        logger.warning(
                            f"[StrategyTrader] [Model {effective_model_id}] [卖出策略筛选] 跳过 {sym_upper}: "
                            f"无有效卖出信号（valid={sorted(list(valid_signals))}），策略返回signals={signals}"
                        )
                        continue

                    final_decisions[sym_upper] = valid_dec_list
                    selected_symbols_this_strategy.append(sym_upper)
                    logger.warning(
                        f"[StrategyTrader] [Model {effective_model_id}] [卖出策略筛选] 采纳 {sym_upper}: "
                        f"decisions={[(d.get('signal'), d.get('quantity'), d.get('price'), d.get('stop_price')) for d in valid_dec_list]}"
                    )

                if selected_symbols_this_strategy:
                    used_strategy_names.append(strategy_name)
                    selected_set = set(selected_symbols_this_strategy)
                    remaining_symbol_set = set(s for s in remaining_symbol_set if s not in selected_set)
                    remaining_positions = [
                        p for p in remaining_positions if str(p.get("symbol") or "").upper() in remaining_symbol_set
                    ]

            except Exception as e:
                logger.error(f"[StrategyTrader] [Model {effective_model_id}] 执行策略 {strategy_name} 失败: {e}")
                logger.debug(f"[StrategyTrader] 异常堆栈:\n{traceback.format_exc()}")
                continue

        if final_decisions:
            trace = ",".join(used_strategy_names) if used_strategy_names else "策略命中"
            return {
                "decisions": final_decisions,
                "prompt": None,
                "raw_response": json.dumps(
                    {
                        "strategies": used_strategy_names,
                        "decisions": final_decisions,
                        "remaining_position_count": len(remaining_positions),
                    },
                    ensure_ascii=False,
                    default=str,
                ),
                "cot_trace": trace,
                "skipped": False,
            }

        logger.info(f"[StrategyTrader] [Model {effective_model_id}] 所有策略都未返回有效信号，返回hold决策")
        return {
            "decisions": {},
            "prompt": None,
            "raw_response": None,
            "cot_trace": "所有策略未命中",
            "skipped": False,
        }
