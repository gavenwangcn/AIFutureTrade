"""
策略交易器基类：共享初始化、决策归一化、数量精度处理。
"""

import json
import logging
import math
from typing import Dict, List, Optional

from trade.trader import Trader
from trade.strategy.strategy_code_executor import StrategyCodeExecutor
from trade.common.database.database_strategys import StrategysDatabase
from trade.common.database.database_models import ModelsDatabase

logger = logging.getLogger(__name__)


class StrategyTraderBase(Trader):
    """
    基于策略代码的交易决策生成器基类。
    子类实现 make_buy_decision / make_sell_decision / make_look_decision 等。
    """

    def __init__(self, db, model_id: int):
        self.db = db
        self.model_id = model_id
        self.code_executor = StrategyCodeExecutor(preload_talib=True)
        self.strategys_db = StrategysDatabase(pool=db._pool if db and hasattr(db, "_pool") else None)
        self.models_db = ModelsDatabase(pool=db._pool if db and hasattr(db, "_pool") else None)

    def _decisions_to_list_per_symbol(self, decisions: Dict) -> Dict[str, List[Dict]]:
        """
        策略只返回 Dict[symbol, List[decision]]，value 必须为列表。
        非列表的 value 视为空列表并过滤掉非 dict 元素。
        """
        result: Dict[str, List[Dict]] = {}
        for symbol, val in (decisions or {}).items():
            if not symbol:
                continue
            if isinstance(val, list):
                result[symbol] = [d for d in val if isinstance(d, dict)]
            else:
                result[symbol] = []
        return result

    def _normalize_quantity_by_price(self, decisions: Dict, market_state: Dict) -> Dict[str, List[Dict]]:
        """
        根据 symbol 价格动态调整 decisions 中的 quantity 精度。
        decisions 格式为 Dict[symbol, List[decision]]，返回同格式。
        """
        from trade.trading.trading_utils import adjust_quantity_precision_by_price_ceil

        list_per_symbol = self._decisions_to_list_per_symbol(decisions)
        normalized_decisions: Dict[str, List[Dict]] = {}
        for symbol, decision_list in list_per_symbol.items():
            normalized_list = []
            for decision in decision_list:
                normalized_decision = decision.copy()
                if "quantity" in normalized_decision and normalized_decision["quantity"] is not None:
                    try:
                        quantity = float(normalized_decision["quantity"])
                        if quantity <= 0:
                            normalized_decision["quantity"] = 0.0
                        else:
                            price = None
                            symbol_upper = str(symbol).upper()
                            if isinstance(market_state, dict):
                                market_info = market_state.get(symbol_upper)
                                if market_info is None:
                                    for k, v in market_state.items():
                                        try:
                                            if str(k).upper() == symbol_upper:
                                                market_info = v
                                                break
                                        except Exception:
                                            continue
                                if isinstance(market_info, dict):
                                    price = market_info.get("price")
                            if price is not None:
                                try:
                                    price_float = float(price)
                                    if price_float > 0:
                                        adjusted_quantity = adjust_quantity_precision_by_price_ceil(quantity, price_float)
                                        normalized_decision["quantity"] = adjusted_quantity
                                        logger.debug(
                                            f"[StrategyTrader] 根据价格向后取整 {symbol} 的quantity: {quantity} -> {adjusted_quantity} (价格: {price_float})"
                                        )
                                    else:
                                        normalized_decision["quantity"] = float(math.ceil(quantity))
                                        logger.debug(
                                            f"[StrategyTrader] 价格无效，{symbol} 的quantity向后取整: {quantity} -> {normalized_decision['quantity']}"
                                        )
                                except (ValueError, TypeError):
                                    normalized_decision["quantity"] = float(math.ceil(quantity))
                                    logger.debug(
                                        f"[StrategyTrader] 价格转换失败，{symbol} 的quantity向后取整: {quantity} -> {normalized_decision['quantity']}"
                                    )
                            else:
                                normalized_decision["quantity"] = float(math.ceil(quantity))
                                logger.debug(
                                    f"[StrategyTrader] 无价格信息，{symbol} 的quantity向后取整: {quantity} -> {normalized_decision['quantity']}"
                                )
                    except (ValueError, TypeError) as e:
                        logger.warning(
                            f"[StrategyTrader] 无法转换 {symbol} 的quantity: {normalized_decision.get('quantity')}, 错误: {e}"
                        )
                        normalized_decision["quantity"] = 0.0
                normalized_list.append(normalized_decision)
            normalized_decisions[symbol] = normalized_list
        return normalized_decisions

    def _normalize_quantity_to_int(self, decisions: Dict) -> Dict[str, List[Dict]]:
        """
        将 decisions 中的 quantity 转为整数（向上取整），用于历史卖出路径兼容。
        """
        list_per_symbol = self._decisions_to_list_per_symbol(decisions)
        normalized_decisions: Dict[str, List[Dict]] = {}
        for symbol, decision_list in list_per_symbol.items():
            normalized_list = []
            for decision in decision_list:
                normalized_decision = decision.copy()
                if "quantity" in normalized_decision and normalized_decision["quantity"] is not None:
                    try:
                        quantity = float(normalized_decision["quantity"])
                        if quantity <= 0:
                            normalized_decision["quantity"] = 0
                        else:
                            normalized_decision["quantity"] = int(math.ceil(quantity))
                            logger.debug(
                                f"[StrategyTrader] 将 {symbol} 的quantity向后取整: {quantity} -> {normalized_decision['quantity']}"
                            )
                    except (ValueError, TypeError) as e:
                        logger.warning(
                            f"[StrategyTrader] 无法转换 {symbol} 的quantity: {normalized_decision.get('quantity')}, 错误: {e}"
                        )
                        normalized_decision["quantity"] = 0
                normalized_list.append(normalized_decision)
            normalized_decisions[symbol] = normalized_list
        return normalized_decisions

    # --- Trader 抽象接口：由子类 StrategyBuyTrader / StrategySellTrader 实现 ---
    def make_buy_decision(
        self,
        candidates: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        market_state: Dict,
        model_id: Optional[int] = None,
        conditional_orders: Optional[Dict[str, List[Dict]]] = None,
    ) -> Dict:
        raise NotImplementedError

    def make_sell_decision(
        self,
        portfolio: Dict,
        market_state: Dict,
        account_info: Dict,
        model_id: Optional[int] = None,
        conditional_orders: Optional[Dict[str, List[Dict]]] = None,
    ) -> Dict:
        raise NotImplementedError
