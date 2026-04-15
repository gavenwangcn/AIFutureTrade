"""
盯盘策略交易器：执行单条 look 类型策略（由 market_look 等调用方传入 strategys 行）。
"""

import json
import logging
import traceback
from typing import Dict

from trade.strategy.strategy_trader_base import StrategyTraderBase

logger = logging.getLogger(__name__)


class StrategyLookTrader(StrategyTraderBase):
    """盯盘决策：不依赖 model 下策略列表，单次执行传入的 strategy 代码。"""

    def make_look_decision(
        self,
        strategy: Dict,
        market_state: Dict,
        symbol: str,
    ) -> Dict:
        sym_u = str(symbol or "").strip().upper()
        if not sym_u:
            return {"decisions": {}, "prompt": None, "raw_response": None, "cot_trace": None, "skipped": True}

        strategy_name = strategy.get("strategy_name") or strategy.get("name") or "盯盘策略"
        strategy_code = strategy.get("strategy_code", "")
        if not strategy_code or not strategy_code.strip():
            logger.warning(f"[StrategyTrader] 盯盘策略代码为空: {strategy_name}")
            return {"decisions": {}, "prompt": None, "raw_response": None, "cot_trace": "无代码", "skipped": True}

        try:
            decision_result = self.code_executor.execute_strategy_code(
                strategy_code=strategy_code,
                strategy_name=strategy_name,
                market_state=market_state,
                decision_type="look",
                look_symbol=sym_u,
            )
            if not decision_result or not isinstance(decision_result, dict):
                return {
                    "decisions": {},
                    "prompt": None,
                    "raw_response": None,
                    "cot_trace": strategy_name,
                    "skipped": False,
                }
            decisions = decision_result.get("decisions") or {}
            return {
                "decisions": decisions if isinstance(decisions, dict) else {},
                "prompt": None,
                "raw_response": json.dumps(decision_result, ensure_ascii=False, default=str),
                "cot_trace": strategy_name,
                "skipped": False,
            }
        except Exception as e:
            logger.error(f"[StrategyTrader] 盯盘策略执行失败 {strategy_name}: {e}")
            logger.debug(traceback.format_exc())
            return {
                "decisions": {},
                "prompt": None,
                "raw_response": str(e),
                "cot_trace": strategy_name,
                "skipped": False,
            }
