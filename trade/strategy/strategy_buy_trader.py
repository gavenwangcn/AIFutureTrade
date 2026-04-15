"""
买入策略交易器：按优先级执行 buy 类型策略代码，生成开仓决策。
"""

import json
import logging
import traceback
from typing import Dict, List, Optional

from trade.strategy.strategy_trader_base import StrategyTraderBase
from trade.strategy.strategy_trader_utils import (
    dedupe_candidates_by_symbol,
    filter_market_state,
    log_submit_close_prices,
    unique_ordered_symbols_from_strings,
)

logger = logging.getLogger(__name__)


class StrategyBuyTrader(StrategyTraderBase):
    """买入决策：候选去重、多策略优先级短路、quantity 按价精度归一。"""

    def make_buy_decision(
        self,
        candidates: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        market_state: Dict,
        model_id: Optional[int] = None,
        conditional_orders: Optional[Dict[str, List[Dict]]] = None,
    ) -> Dict:
        logger.info(f"[StrategyTrader] [Model {self.model_id}] 开始生成买入决策, 候选交易对数量: {len(candidates)}")

        if not candidates:
            return {"decisions": {}, "prompt": None, "raw_response": None, "cot_trace": None, "skipped": True}

        effective_model_id = model_id if model_id is not None else self.model_id
        if conditional_orders is None:
            conditional_orders = {}

        model_mapping = self.models_db._get_model_id_mapping()
        strategies = self.strategys_db.get_model_strategies_by_int_id(effective_model_id, "buy", model_mapping)

        if not strategies:
            logger.info(f"[StrategyTrader] [Model {effective_model_id}] 未找到买入类型策略，返回hold决策")
            return {
                "decisions": {},
                "prompt": None,
                "raw_response": None,
                "cot_trace": "无策略",
                "skipped": True,
            }

        logger.info(f"[StrategyTrader] [Model {effective_model_id}] 找到 {len(strategies)} 个买入类型策略，开始按优先级执行")

        remaining_candidates, remaining_symbol_set = dedupe_candidates_by_symbol(candidates)

        working_account_info: Dict = dict(account_info) if isinstance(account_info, dict) else {}
        working_portfolio: Dict = dict(portfolio) if isinstance(portfolio, dict) else {}

        final_decisions: Dict[str, List[Dict]] = {}
        used_strategy_names: List[str] = []

        valid_signals = {"buy_to_long", "buy_to_short"}

        for strategy in strategies:
            if not remaining_candidates or not remaining_symbol_set:
                break

            strategy_name = strategy.get("strategy_name", "未知策略")
            strategy_code = strategy.get("strategy_code", "")
            priority = strategy.get("priority", 0)

            if not strategy_code or not strategy_code.strip():
                logger.debug(
                    f"[StrategyTrader] [Model {effective_model_id}] 策略 {strategy_name} (优先级: {priority}) 代码为空，跳过"
                )
                continue

            filtered_market_state = filter_market_state(market_state, remaining_symbol_set)

            logger.debug(f"[StrategyTrader] [Model {effective_model_id}] 执行策略: {strategy_name} (优先级: {priority})")

            try:
                try:
                    symbols_for_log = []
                    for c in remaining_candidates:
                        sym_u = str(c.get("symbol") or c.get("contract_symbol") or "").upper()
                        if sym_u:
                            symbols_for_log.append(sym_u)
                    symbols_for_log = unique_ordered_symbols_from_strings(symbols_for_log)
                    log_submit_close_prices(
                        logger, effective_model_id, f"buy/{strategy_name}", symbols_for_log, filtered_market_state
                    )
                except Exception:
                    pass

                decision_result = self.code_executor.execute_strategy_code(
                    strategy_code=strategy_code,
                    strategy_name=strategy_name,
                    candidates=remaining_candidates,
                    portfolio=working_portfolio,
                    account_info=working_account_info,
                    market_state=filtered_market_state,
                    decision_type="buy",
                    conditional_orders=conditional_orders,
                )

                if not decision_result or not isinstance(decision_result, dict):
                    logger.info(
                        f"[StrategyTrader] [Model {effective_model_id}] [买入策略执行] 策略 {strategy_name} (优先级: {priority}) 返回结果无效或为空，继续下一个策略"
                    )
                    logger.debug(
                        f"[StrategyTrader] [Model {effective_model_id}] 策略 {strategy_name} 返回结果无效，继续下一个策略"
                    )
                    continue

                decisions = decision_result.get("decisions", {}) or {}
                if not isinstance(decisions, dict) or not decisions:
                    logger.info(
                        f"[StrategyTrader] [Model {effective_model_id}] [买入策略执行] 策略 {strategy_name} (优先级: {priority}) 返回的decisions为空或格式不正确，继续下一个策略"
                    )
                    continue

                list_per_symbol = self._decisions_to_list_per_symbol(decisions)
                total_decision_count = sum(len(lst) for lst in list_per_symbol.values())
                logger.info(
                    f"[StrategyTrader] [Model {effective_model_id}] [买入策略执行] ✓ 策略 {strategy_name} (优先级: {priority}) 执行成功，返回 {len(list_per_symbol)} 个 symbol、共 {total_decision_count} 个交易信号决策"
                )

                for symbol, dec_list in list_per_symbol.items():
                    for dec in dec_list:
                        if isinstance(dec, dict):
                            logger.info(
                                f"[StrategyTrader] [Model {effective_model_id}] [买入策略执行] [交易信号] "
                                f"策略={strategy_name}, Symbol={symbol}, Signal={dec.get('signal', 'N/A')}, "
                                f"Quantity={dec.get('quantity', 'N/A')}, Leverage={dec.get('leverage', 'N/A')}, Justification={dec.get('justification', 'N/A')}"
                            )

                normalized_decisions = self._normalize_quantity_by_price(decisions, filtered_market_state)

                decisions_by_symbol: Dict[str, List[Dict]] = {}
                for sym, dec_list in normalized_decisions.items():
                    sym_upper = str(sym).upper()
                    if not sym_upper:
                        continue
                    decisions_by_symbol[sym_upper] = dec_list

                selected_symbols_this_strategy: List[str] = []

                for c in remaining_candidates:
                    try:
                        sym_upper = str(c.get("symbol") or c.get("contract_symbol") or "").upper()
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
                        try:
                            qty = float(dec.get("quantity") or 0)
                        except (TypeError, ValueError):
                            qty = 0.0
                        if qty <= 0:
                            logger.warning(
                                f"[StrategyTrader] [Model {effective_model_id}] [买入策略筛选] 丢弃 {sym_upper} 一条决策: "
                                f"signal={sig} 但 quantity<=0 或非法"
                            )
                            continue
                        valid_dec_list.append(dec)
                    if not valid_dec_list:
                        try:
                            signals = [(d.get("signal") if isinstance(d, dict) else None) for d in dec_list]
                        except Exception:
                            signals = []
                        logger.warning(
                            f"[StrategyTrader] [Model {effective_model_id}] [买入策略筛选] 跳过 {sym_upper}: "
                            f"无有效买入信号（valid={sorted(list(valid_signals))} 且 quantity>0），策略返回signals={signals}"
                        )
                        continue

                    for dec in valid_dec_list:
                        logger.info(
                            f"[StrategyTrader] [Model {effective_model_id}] ✓ 接受有效买入信号: {sym_upper} -> "
                            f"{(dec.get('signal') or '').lower()} (quantity={dec.get('quantity')}, leverage={dec.get('leverage')})"
                        )
                        dec.setdefault("_strategy_name", strategy_name)
                        dec.setdefault("_strategy_type", "buy")

                    final_decisions[sym_upper] = valid_dec_list
                    selected_symbols_this_strategy.append(sym_upper)
                    logger.info(
                        f"[StrategyTrader] [Model {effective_model_id}] [买入策略筛选] 采纳 {sym_upper}: "
                        f"条数={len(valid_dec_list)}（不做余额预校验，由接口返回结果）"
                    )

                if selected_symbols_this_strategy:
                    used_strategy_names.append(strategy_name)
                    remaining_symbol_set = set(s for s in remaining_symbol_set if s not in set(selected_symbols_this_strategy))
                    remaining_candidates = [
                        c
                        for c in remaining_candidates
                        if str(c.get("symbol") or c.get("contract_symbol") or "").upper() in remaining_symbol_set
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
                        "remaining_candidate_count": len(remaining_candidates),
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
