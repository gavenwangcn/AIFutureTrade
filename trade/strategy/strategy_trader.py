"""
Strategy Trader - 基于策略代码的交易决策生成器

本模块提供StrategyTrader类，用于通过执行策略代码生成交易决策。
策略代码从model_strategy表中获取，按优先级顺序执行。

主要功能：
1. 买入决策生成：基于候选交易对列表，执行买入类型策略代码生成决策
2. 卖出决策生成：基于当前持仓，执行卖出类型策略代码生成决策
3. 策略优先级：按priority降序、created_at升序执行策略
4. 决策合并：多个策略的决策结果合并处理
5. 代码执行：使用StrategyCodeExecutor安全执行策略代码，支持TA-Lib等库
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


class StrategyTrader(Trader):
    """
    基于策略代码的交易决策生成器
    
    通过执行model_strategy表中关联的策略代码来生成交易决策。
    策略按优先级顺序执行，直到找到有效的决策信号。
    
    使用示例：
        trader = StrategyTrader(db=db, model_id=1)
        result = trader.make_buy_decision(candidates, portfolio, account_info, market_state)
    """
    
    def __init__(self, db, model_id: int):
        """
        初始化策略交易决策生成器
        
        Args:
            db: 数据库实例，用于查询策略信息
            model_id: 模型ID，用于查询该模型关联的策略
        """
        self.db = db
        self.model_id = model_id
        # 初始化策略代码执行器
        self.code_executor = StrategyCodeExecutor(preload_talib=True)
        # 初始化 StrategysDatabase 和 ModelsDatabase 实例
        self.strategys_db = StrategysDatabase(pool=db._pool if db and hasattr(db, '_pool') else None)
        self.models_db = ModelsDatabase(pool=db._pool if db and hasattr(db, '_pool') else None)
    
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
                # 如果decision中有quantity字段，根据价格调整精度
                if 'quantity' in normalized_decision and normalized_decision['quantity'] is not None:
                    try:
                        quantity = float(normalized_decision['quantity'])
                        if quantity <= 0:
                            normalized_decision['quantity'] = 0.0
                        else:
                            # 从market_state中获取symbol的价格
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
                                    price = market_info.get('price')
                            if price is not None:
                                try:
                                    price_float = float(price)
                                    if price_float > 0:
                                        adjusted_quantity = adjust_quantity_precision_by_price_ceil(quantity, price_float)
                                        normalized_decision['quantity'] = adjusted_quantity
                                        logger.debug(f"[StrategyTrader] 根据价格向后取整 {symbol} 的quantity: {quantity} -> {adjusted_quantity} (价格: {price_float})")
                                    else:
                                        normalized_decision['quantity'] = float(math.ceil(quantity))
                                        logger.debug(f"[StrategyTrader] 价格无效，{symbol} 的quantity向后取整: {quantity} -> {normalized_decision['quantity']}")
                                except (ValueError, TypeError):
                                    normalized_decision['quantity'] = float(math.ceil(quantity))
                                    logger.debug(f"[StrategyTrader] 价格转换失败，{symbol} 的quantity向后取整: {quantity} -> {normalized_decision['quantity']}")
                            else:
                                normalized_decision['quantity'] = float(math.ceil(quantity))
                                logger.debug(f"[StrategyTrader] 无价格信息，{symbol} 的quantity向后取整: {quantity} -> {normalized_decision['quantity']}")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"[StrategyTrader] 无法转换 {symbol} 的quantity: {normalized_decision.get('quantity')}, 错误: {e}")
                        normalized_decision['quantity'] = 0.0
                normalized_list.append(normalized_decision)
            normalized_decisions[symbol] = normalized_list
        return normalized_decisions
    
    def _normalize_quantity_to_int(self, decisions: Dict) -> Dict[str, List[Dict]]:
        """
        将decisions中的quantity字段转换为整数（用于卖出策略）。
        使用向后取整（向上取整），例如 20.5 -> 21。
        decisions 可为 Dict[symbol, decision] 或 Dict[symbol, List[decision]]，返回 Dict[symbol, List[decision]]。
        """
        list_per_symbol = self._decisions_to_list_per_symbol(decisions)
        normalized_decisions: Dict[str, List[Dict]] = {}
        for symbol, decision_list in list_per_symbol.items():
            normalized_list = []
            for decision in decision_list:
                normalized_decision = decision.copy()
                if 'quantity' in normalized_decision and normalized_decision['quantity'] is not None:
                    try:
                        quantity = float(normalized_decision['quantity'])
                        if quantity <= 0:
                            normalized_decision['quantity'] = 0
                        else:
                            normalized_decision['quantity'] = int(math.ceil(quantity))
                            logger.debug(f"[StrategyTrader] 将 {symbol} 的quantity向后取整: {quantity} -> {normalized_decision['quantity']}")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"[StrategyTrader] 无法转换 {symbol} 的quantity: {normalized_decision.get('quantity')}, 错误: {e}")
                        normalized_decision['quantity'] = 0
                normalized_list.append(normalized_decision)
            normalized_decisions[symbol] = normalized_list
        return normalized_decisions
    
    def make_buy_decision(
        self,
        candidates: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        market_state: Dict,
        model_id: Optional[int] = None,
        conditional_orders: Optional[Dict[str, List[Dict]]] = None
    ) -> Dict:
        """
        生成买入/开仓决策

        通过执行模型关联的买入类型策略代码生成决策。
        按优先级顺序执行策略，直到找到有效的决策信号。

        Args:
            candidates: 候选交易对列表
            portfolio: 持仓组合信息
            account_info: 账户信息
            market_state: 市场状态字典，key为交易对符号，value包含价格、技术指标等
            model_id: 模型ID（可选，优先使用实例变量中的model_id）
            conditional_orders: 条件单信息字典（可选），按symbol分组的条件单列表

        Returns:
            Dict: 包含以下字段的字典：
                - decisions: 决策字典，key为交易对符号，value为决策详情
                - prompt: None（策略交易不使用prompt）
                - raw_response: 策略代码执行结果
                - cot_trace: 策略名称（用于追踪）
                - skipped: 是否跳过（当candidates为空或没有策略时为True）
        """
        logger.info(f"[StrategyTrader] [Model {self.model_id}] 开始生成买入决策, 候选交易对数量: {len(candidates)}")

        if not candidates:
            return {'decisions': {}, 'prompt': None, 'raw_response': None, 'cot_trace': None, 'skipped': True}

        # 使用实例变量中的model_id，如果提供了参数则使用参数
        effective_model_id = model_id if model_id is not None else self.model_id

        # 如果没有提供conditional_orders，设置为空字典
        if conditional_orders is None:
            conditional_orders = {}

        # 获取模型关联的买入类型策略（按优先级排序）
        model_mapping = self.models_db._get_model_id_mapping()
        strategies = self.strategys_db.get_model_strategies_by_int_id(effective_model_id, 'buy', model_mapping)

        if not strategies:
            logger.info(f"[StrategyTrader] [Model {effective_model_id}] 未找到买入类型策略，返回hold决策")
            return {
                'decisions': {},
                'prompt': None,
                'raw_response': None,
                'cot_trace': '无策略',
                'skipped': True
            }

        logger.info(f"[StrategyTrader] [Model {effective_model_id}] 找到 {len(strategies)} 个买入类型策略，开始按优先级执行")

        # 语义要求：
        # - 按优先级逐个执行策略
        # - 一旦某个symbol在较高优先级策略中命中（产生买入决策），该symbol需要从后续策略的 candidates/market_state 中扣除
        # - account_info.available_balance（以及portfolio.cash）需要按已命中的买入决策预扣资金，避免后续策略重复/超额决策
        #
        # 注意：这里是“决策生成阶段”的预扣，用于策略间约束；真实下单阶段仍以交易执行模块的风控/资金校验为准。
        #
        # 规范化 & 去重 candidates（按symbol去重，保留顺序）
        remaining_candidates: List[Dict] = []
        remaining_symbol_set: set = set()
        for c in candidates:
            try:
                sym = str(c.get('symbol') or c.get('contract_symbol') or '').upper()
            except Exception:
                sym = ''
            if not sym or sym in remaining_symbol_set:
                continue
            remaining_symbol_set.add(sym)
            remaining_candidates.append(c)

        # market_state 过滤将基于 remaining_symbol_set 进行（key 可能是任意大小写）
        def _filter_market_state(ms: Dict, allowed_symbols: set) -> Dict:
            if not ms or not isinstance(ms, dict) or not allowed_symbols:
                return {}
            filtered = {}
            for k, v in ms.items():
                try:
                    if str(k).upper() in allowed_symbols:
                        filtered[k] = v
                except Exception:
                    continue
            return filtered

        def _log_close_prices_for_symbols(
            context: str, symbols: List[str], ms: Dict
        ) -> None:
            """
            在提交给策略代码前，打印每个symbol的收盘价信息。
            目前收盘价使用 TradingEngine 注入的 previous_close_prices（上一根K线收盘价，按 timeframe 映射）。
            """
            try:
                if not symbols or not ms or not isinstance(ms, dict):
                    return
                # 将 market_state key 归一化为 upper，便于按 symbol 查找
                ms_by_upper = {}
                for k, v in ms.items():
                    try:
                        ms_by_upper[str(k).upper()] = v
                    except Exception:
                        continue

                lines: List[str] = []
                for sym in symbols:
                    sym_u = str(sym).upper()
                    payload = ms_by_upper.get(sym_u) or {}
                    prev_close = payload.get('previous_close_prices') if isinstance(payload, dict) else None
                    price = payload.get('price') if isinstance(payload, dict) else None
                    prev_close_json = json.dumps(prev_close, ensure_ascii=False, default=str)
                    lines.append(
                        f"symbol={sym_u} | price实时价={price} | previous_close_prices收盘价={prev_close_json}"
                    )

                if lines:
                    logger.info(
                        f"[StrategyTrader] [Model {effective_model_id}] 提交到策略代码({context}) 收盘价信息:\n"
                        + "\n".join(lines)
                    )
            except Exception as e:
                logger.debug(f"[StrategyTrader] 打印收盘价日志失败: {e}")

        # 使用工作副本（避免污染外部对象）
        working_account_info: Dict = dict(account_info) if isinstance(account_info, dict) else {}
        working_portfolio: Dict = dict(portfolio) if isinstance(portfolio, dict) else {}

        def _get_available_balance() -> float:
            # account_info 主字段：available_balance
            # 若缺失，fallback 到 portfolio.cash（策略模板也会使用该字段）
            candidates_keys = [
                ('available_balance', working_account_info),
                ('availableBalance', working_account_info),
                ('available_cash', working_account_info),
                ('cash', working_portfolio),
            ]
            for key, obj in candidates_keys:
                try:
                    if isinstance(obj, dict) and obj.get(key) is not None:
                        return float(obj.get(key))
                except Exception:
                    continue
            return 0.0

        def _set_available_balance(v: float) -> None:
            # 同步写回 account_info.available_balance 与 portfolio.cash（仅工作副本）
            try:
                working_account_info['available_balance'] = float(v)
            except Exception:
                pass
            try:
                if 'cash' in working_portfolio:
                    working_portfolio['cash'] = float(v)
            except Exception:
                pass

        def _estimate_required_capital(sym_upper: str, dec: Dict, ms: Dict) -> float:
            """
            预估需要占用的本金（USDT），与交易执行模块一致采用：
            required_capital_usdt = (position_amt * price) / leverage
            
            注意：期货 quantity 可为小数（如 0.0146 ETH），需使用 float 而非 int。
            """
            try:
                qty = float(dec.get('quantity') or 0)
                if qty <= 0:
                    return 0.0
            except (ValueError, TypeError):
                return 0.0

            # leverage：优先取决策字段，其次fallback为1
            try:
                lev = int(float(dec.get('leverage') or 0))
                if lev <= 0:
                    lev = 1
            except Exception:
                lev = 1

            # price：优先从 market_state[symbol].price 取（注意 key 可能不是大写）
            price = None
            if isinstance(ms, dict):
                # 先直接按大写找
                payload = ms.get(sym_upper)
                if payload is None:
                    # 再遍历找 key 大小写不同的情况
                    for k, v in ms.items():
                        try:
                            if str(k).upper() == sym_upper:
                                payload = v
                                break
                        except Exception:
                            continue
                if isinstance(payload, dict):
                    price = payload.get('price')
            try:
                price_f = float(price) if price is not None else 0.0
            except Exception:
                price_f = 0.0
            if price_f <= 0:
                return 0.0

            return (qty * price_f) / lev

        final_decisions: Dict[str, List[Dict]] = {}
        used_strategy_names: List[str] = []

        valid_signals = {'buy_to_long', 'buy_to_short'}

        # 按优先级顺序执行策略（对每个symbol单独“短路”）
        for strategy in strategies:
            # 没有剩余候选时直接结束
            if not remaining_candidates or not remaining_symbol_set:
                break

            # 可用余额耗尽时，停止继续生成买入决策
            if _get_available_balance() <= 0:
                break

            strategy_name = strategy.get('strategy_name', '未知策略')
            strategy_code = strategy.get('strategy_code', '')
            priority = strategy.get('priority', 0)

            if not strategy_code or not strategy_code.strip():
                logger.debug(f"[StrategyTrader] [Model {effective_model_id}] 策略 {strategy_name} (优先级: {priority}) 代码为空，跳过")
                continue

            # 为下一策略准备扣除后的 candidates & market_state
            filtered_market_state = _filter_market_state(market_state, remaining_symbol_set)

            logger.debug(f"[StrategyTrader] [Model {effective_model_id}] 执行策略: {strategy_name} (优先级: {priority})")

            try:
                # 在提交给策略代码前打印候选symbol的收盘价信息（上一根K线收盘价）
                try:
                    symbols_for_log = []
                    for c in remaining_candidates:
                        sym_u = str(c.get('symbol') or c.get('contract_symbol') or '').upper()
                        if sym_u:
                            symbols_for_log.append(sym_u)
                    # 去重保序
                    seen = set()
                    symbols_for_log = [s for s in symbols_for_log if not (s in seen or seen.add(s))]
                    _log_close_prices_for_symbols(f"buy/{strategy_name}", symbols_for_log, filtered_market_state)
                except Exception:
                    pass

                decision_result = self.code_executor.execute_strategy_code(
                    strategy_code=strategy_code,
                    strategy_name=strategy_name,
                    candidates=remaining_candidates,
                    portfolio=working_portfolio,
                    account_info=working_account_info,
                    market_state=filtered_market_state,
                    decision_type='buy',
                    conditional_orders=conditional_orders
                )

                # ⚠️ 重要：记录策略代码执行后的返回结果（info级别日志，便于排查问题）
                if not decision_result or not isinstance(decision_result, dict):
                    logger.info(f"[StrategyTrader] [Model {effective_model_id}] [买入策略执行] 策略 {strategy_name} (优先级: {priority}) 返回结果无效或为空，继续下一个策略")
                    logger.debug(f"[StrategyTrader] [Model {effective_model_id}] 策略 {strategy_name} 返回结果无效，继续下一个策略")
                    continue

                decisions = decision_result.get('decisions', {}) or {}
                if not isinstance(decisions, dict) or not decisions:
                    logger.info(f"[StrategyTrader] [Model {effective_model_id}] [买入策略执行] 策略 {strategy_name} (优先级: {priority}) 返回的decisions为空或格式不正确，继续下一个策略")
                    continue
                
                # 归一化为 symbol -> List[decision]（同一 symbol 可多条信号）
                list_per_symbol = self._decisions_to_list_per_symbol(decisions)
                total_decision_count = sum(len(lst) for lst in list_per_symbol.values())
                logger.info(f"[StrategyTrader] [Model {effective_model_id}] [买入策略执行] ✓ 策略 {strategy_name} (优先级: {priority}) 执行成功，返回 {len(list_per_symbol)} 个 symbol、共 {total_decision_count} 个交易信号决策")

                for symbol, dec_list in list_per_symbol.items():
                    for dec in dec_list:
                        if isinstance(dec, dict):
                            logger.info(
                                f"[StrategyTrader] [Model {effective_model_id}] [买入策略执行] [交易信号] "
                                f"策略={strategy_name}, Symbol={symbol}, Signal={dec.get('signal', 'N/A')}, "
                                f"Quantity={dec.get('quantity', 'N/A')}, Leverage={dec.get('leverage', 'N/A')}, Justification={dec.get('justification', 'N/A')}"
                            )

                # 根据价格动态调整quantity精度（返回 Dict[symbol, List[decision]]）
                normalized_decisions = self._normalize_quantity_by_price(decisions, filtered_market_state)

                # 按 symbol 归一化为 upper key，value 为 List[decision]
                decisions_by_symbol: Dict[str, List[Dict]] = {}
                for sym, dec_list in normalized_decisions.items():
                    sym_upper = str(sym).upper()
                    if not sym_upper:
                        continue
                    decisions_by_symbol[sym_upper] = dec_list

                selected_symbols_this_strategy: List[str] = []
                spent_this_strategy = 0.0
                available_before = _get_available_balance()

                # 按 remaining_candidates 顺序挑选（同一 symbol 可有多条决策，合并资金预估）
                for c in remaining_candidates:
                    try:
                        sym_upper = str(c.get('symbol') or c.get('contract_symbol') or '').upper()
                    except Exception:
                        continue
                    if not sym_upper or sym_upper not in remaining_symbol_set:
                        continue
                    if sym_upper in final_decisions:
                        continue

                    dec_list = decisions_by_symbol.get(sym_upper) or []
                    if not dec_list:
                        continue

                    # 只保留有效买入信号的决策，并汇总所需资金
                    valid_dec_list = []
                    total_required_capital = 0.0
                    for dec in dec_list:
                        if not isinstance(dec, dict):
                            continue
                        sig = (dec.get('signal') or '').lower()
                        if sig not in valid_signals:
                            continue
                        valid_dec_list.append(dec)
                        cap = _estimate_required_capital(sym_upper, dec, filtered_market_state)
                        if cap > 0:
                            total_required_capital += cap
                    if not valid_dec_list:
                        continue
                    if total_required_capital <= 0:
                        continue
                    if available_before - spent_this_strategy < total_required_capital:
                        continue

                    for dec in valid_dec_list:
                        logger.info(f"[StrategyTrader] [Model {effective_model_id}] ✓ 接受有效买入信号: {sym_upper} -> {(dec.get('signal') or '').lower()} (quantity={dec.get('quantity')}, leverage={dec.get('leverage')})")
                        dec.setdefault('_strategy_name', strategy_name)
                        dec.setdefault('_strategy_type', 'buy')

                    final_decisions[sym_upper] = valid_dec_list
                    selected_symbols_this_strategy.append(sym_upper)
                    spent_this_strategy += total_required_capital

                # 若本策略命中，则扣除 candidates/market_state，并预扣余额（供后续策略使用）
                if selected_symbols_this_strategy:
                    used_strategy_names.append(strategy_name)

                    remaining_symbol_set = set(s for s in remaining_symbol_set if s not in set(selected_symbols_this_strategy))
                    remaining_candidates = [
                        c for c in remaining_candidates
                        if str(c.get('symbol') or c.get('contract_symbol') or '').upper() in remaining_symbol_set
                    ]

                    # 预扣余额并写回工作副本
                    new_available = max(0.0, available_before - spent_this_strategy)
                    _set_available_balance(new_available)

            except Exception as e:
                logger.error(f"[StrategyTrader] [Model {effective_model_id}] 执行策略 {strategy_name} 失败: {e}")
                import traceback
                logger.debug(f"[StrategyTrader] 异常堆栈:\n{traceback.format_exc()}")
                continue

        if final_decisions:
            trace = ','.join(used_strategy_names) if used_strategy_names else '策略命中'
            return {
                'decisions': final_decisions,
                'prompt': None,
                'raw_response': json.dumps({
                    'strategies': used_strategy_names,
                    'decisions': final_decisions,
                    'remaining_candidate_count': len(remaining_candidates),
                    'remaining_available_balance': _get_available_balance()
                }, ensure_ascii=False, default=str),
                'cot_trace': trace,
                'skipped': False
            }

        logger.info(f"[StrategyTrader] [Model {effective_model_id}] 所有策略都未返回有效信号，返回hold决策")
        return {
            'decisions': {},
            'prompt': None,
            'raw_response': None,
            'cot_trace': '所有策略未命中',
            'skipped': False
        }
    
    def make_sell_decision(
        self,
        portfolio: Dict,
        market_state: Dict,
        account_info: Dict,
        model_id: Optional[int] = None,
        conditional_orders: Optional[Dict[str, List[Dict]]] = None
    ) -> Dict:
        """
        生成卖出/平仓决策

        通过执行模型关联的卖出类型策略代码生成决策。
        按优先级顺序执行策略，直到找到有效的决策信号。

        Args:
            portfolio: 当前持仓组合信息
            market_state: 市场状态字典，key为交易对符号，value包含价格、技术指标等
            account_info: 账户信息
            model_id: 模型ID（可选，优先使用实例变量中的model_id）
            conditional_orders: 条件单信息字典（可选），按symbol分组的条件单列表

        Returns:
            Dict: 包含以下字段的字典：
                - decisions: 决策字典，key为交易对符号，value为决策详情
                - prompt: None（策略交易不使用prompt）
                - raw_response: 策略代码执行结果
                - cot_trace: 策略名称（用于追踪）
                - skipped: 是否跳过（当portfolio中没有持仓或没有策略时为True）
        """
        logger.info(f"[StrategyTrader] [Model {self.model_id}] 开始生成卖出决策, 持仓数量: {len(portfolio.get('positions') or [])}")

        if not portfolio.get('positions'):
            return {'decisions': {}, 'prompt': None, 'raw_response': None, 'cot_trace': None, 'skipped': True}

        # 使用实例变量中的model_id，如果提供了参数则使用参数
        effective_model_id = model_id if model_id is not None else self.model_id

        # 如果没有提供conditional_orders，设置为空字典
        if conditional_orders is None:
            conditional_orders = {}

        # 获取模型关联的卖出类型策略（按优先级排序）
        model_mapping = self.models_db._get_model_id_mapping()
        strategies = self.strategys_db.get_model_strategies_by_int_id(effective_model_id, 'sell', model_mapping)

        if not strategies:
            logger.info(f"[StrategyTrader] [Model {effective_model_id}] 未找到卖出类型策略，返回hold决策")
            return {
                'decisions': {},
                'prompt': None,
                'raw_response': None,
                'cot_trace': '无策略',
                'skipped': True
            }

        logger.info(f"[StrategyTrader] [Model {effective_model_id}] 找到 {len(strategies)} 个卖出类型策略，开始按优先级执行")

        # 语义要求（卖出）：
        # - 按优先级逐个执行策略
        # - 一旦某个symbol在较高优先级策略中命中（产生卖出/平仓/止损/止盈决策），该symbol需要从后续策略的 portfolio.positions 和 market_state 中扣除
        # - account_info 不需要更新（卖出不做预扣资金）
        positions = portfolio.get('positions') or []

        # 规范化 & 去重 positions（按symbol去重，保留顺序）
        remaining_positions: List[Dict] = []
        remaining_symbol_set: set = set()
        for p in positions:
            try:
                sym = str(p.get('symbol') or '').upper()
            except Exception:
                sym = ''
            if not sym or sym in remaining_symbol_set:
                continue
            remaining_symbol_set.add(sym)
            remaining_positions.append(p)

        # market_state 过滤将基于 remaining_symbol_set 进行（key 可能是任意大小写）
        def _filter_market_state(ms: Dict, allowed_symbols: set) -> Dict:
            if not ms or not isinstance(ms, dict) or not allowed_symbols:
                return {}
            filtered = {}
            for k, v in ms.items():
                try:
                    if str(k).upper() in allowed_symbols:
                        filtered[k] = v
                except Exception:
                    continue
            return filtered

        # portfolio 工作副本（仅用于策略间扣除）
        base_portfolio: Dict = dict(portfolio) if isinstance(portfolio, dict) else {}

        final_decisions: Dict[str, List[Dict]] = {}
        used_strategy_names: List[str] = []
        valid_signals = {'sell_to_long', 'sell_to_short', 'close_position', 'stop_loss', 'take_profit'}

        for strategy in strategies:
            if not remaining_positions or not remaining_symbol_set:
                break

            strategy_name = strategy.get('strategy_name', '未知策略')
            strategy_code = strategy.get('strategy_code', '')
            priority = strategy.get('priority', 0)

            if not strategy_code or not strategy_code.strip():
                logger.debug(f"[StrategyTrader] [Model {effective_model_id}] 策略 {strategy_name} (优先级: {priority}) 代码为空，跳过")
                continue

            # 为下一策略准备扣除后的 portfolio.positions & market_state
            working_portfolio = dict(base_portfolio)
            working_portfolio['positions'] = remaining_positions
            filtered_market_state = _filter_market_state(market_state, remaining_symbol_set)

            logger.debug(f"[StrategyTrader] [Model {effective_model_id}] 执行策略: {strategy_name} (优先级: {priority})")

            try:
                # 在提交给策略代码前打印持仓symbol的收盘价信息（上一根K线收盘价）
                try:
                    symbols_for_log = []
                    for p in remaining_positions:
                        sym_u = str(p.get('symbol') or '').upper()
                        if sym_u:
                            symbols_for_log.append(sym_u)
                    # 去重保序
                    seen = set()
                    symbols_for_log = [s for s in symbols_for_log if not (s in seen or seen.add(s))]

                    # 将 market_state key 归一化为 upper，便于按 symbol 查找
                    ms_by_upper = {}
                    for k, v in (filtered_market_state or {}).items():
                        try:
                            ms_by_upper[str(k).upper()] = v
                        except Exception:
                            continue

                    lines = []
                    for sym_u in symbols_for_log:
                        payload = ms_by_upper.get(sym_u) or {}
                        prev_close = payload.get('previous_close_prices') if isinstance(payload, dict) else None
                        price = payload.get('price') if isinstance(payload, dict) else None
                        prev_close_json = json.dumps(prev_close, ensure_ascii=False, default=str)
                        lines.append(
                            f"symbol={sym_u} | price实时价={price} | previous_close_prices收盘价={prev_close_json}"
                        )

                    if lines:
                        logger.info(
                            f"[StrategyTrader] [Model {effective_model_id}] 提交到策略代码(sell/{strategy_name}) 收盘价信息:\n"
                            + "\n".join(lines)
                        )
                except Exception:
                    pass

                # 打印传递给策略代码的条件单信息（便于排查条件单未正确传递的问题）
                try:
                    co = conditional_orders or {}
                    total_co = sum(len(v) for v in (co.values() if isinstance(co, dict) else []))
                    symbols_to_log = [str(p.get('symbol') or '').upper() for p in remaining_positions if p.get('symbol')]
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
                    decision_type='sell',
                    conditional_orders=conditional_orders
                )

                # ⚠️ 重要：记录策略代码执行后的返回结果（info级别日志，便于排查问题）
                if not decision_result or not isinstance(decision_result, dict):
                    logger.info(f"[StrategyTrader] [Model {effective_model_id}] [卖出策略执行] 策略 {strategy_name} (优先级: {priority}) 返回结果无效或为空，继续下一个策略")
                    logger.debug(f"[StrategyTrader] [Model {effective_model_id}] 策略 {strategy_name} 返回结果无效，继续下一个策略")
                    continue

                decisions = decision_result.get('decisions', {}) or {}
                if not isinstance(decisions, dict) or not decisions:
                    logger.info(f"[StrategyTrader] [Model {effective_model_id}] [卖出策略执行] 策略 {strategy_name} (优先级: {priority}) 返回的decisions为空或格式不正确，继续下一个策略")
                    continue
                
                # 归一化为 symbol -> List[decision]（同一 symbol 可多条信号：卖出/止损/止盈等）
                list_per_symbol = self._decisions_to_list_per_symbol(decisions)
                total_decision_count = sum(len(lst) for lst in list_per_symbol.values())
                logger.info(f"[StrategyTrader] [Model {effective_model_id}] [卖出策略执行] ✓ 策略 {strategy_name} (优先级: {priority}) 执行成功，返回 {len(list_per_symbol)} 个 symbol、共 {total_decision_count} 个交易信号决策")

                for symbol, dec_list in list_per_symbol.items():
                    for dec in dec_list:
                        if isinstance(dec, dict):
                            logger.info(
                                f"[StrategyTrader] [Model {effective_model_id}] [卖出策略执行] [交易信号] "
                                f"策略={strategy_name}, Symbol={symbol}, Signal={dec.get('signal', 'N/A')}, "
                                f"Quantity={dec.get('quantity', 'N/A')}, Price={dec.get('price', 'N/A')}, Reason={dec.get('reason', dec.get('justification', 'N/A'))}"
                            )

                # 使用 _normalize_quantity_by_price 而非 _normalize_quantity_to_int：
                # 期货 quantity 可为小数（如 0.0146 ETH），int(ceil(0.0146))=1 会错误放大数量
                normalized_decisions = self._normalize_quantity_by_price(decisions, filtered_market_state)

                # 按 symbol 归一化为 upper key，value 为 List[decision]
                decisions_by_symbol: Dict[str, List[Dict]] = {}
                for sym, dec_list in normalized_decisions.items():
                    sym_upper = str(sym).upper()
                    if not sym_upper:
                        continue
                    decisions_by_symbol[sym_upper] = dec_list

                selected_symbols_this_strategy: List[str] = []

                # 按 remaining_positions 顺序挑选（同一 symbol 可有多条决策：close_position/stop_loss/take_profit 等）
                for p in remaining_positions:
                    try:
                        sym_upper = str(p.get('symbol') or '').upper()
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
                        sig = (dec.get('signal') or '').lower()
                        if sig not in valid_signals:
                            continue
                        dec.setdefault('_strategy_name', strategy_name)
                        dec.setdefault('_strategy_type', 'sell')
                        valid_dec_list.append(dec)
                    if not valid_dec_list:
                        continue

                    final_decisions[sym_upper] = valid_dec_list
                    selected_symbols_this_strategy.append(sym_upper)

                # 若本策略命中，则扣除 portfolio.positions & market_state（通过 remaining_symbol_set 实现）
                if selected_symbols_this_strategy:
                    used_strategy_names.append(strategy_name)

                    selected_set = set(selected_symbols_this_strategy)
                    remaining_symbol_set = set(s for s in remaining_symbol_set if s not in selected_set)
                    remaining_positions = [
                        p for p in remaining_positions
                        if str(p.get('symbol') or '').upper() in remaining_symbol_set
                    ]

            except Exception as e:
                logger.error(f"[StrategyTrader] [Model {effective_model_id}] 执行策略 {strategy_name} 失败: {e}")
                import traceback
                logger.debug(f"[StrategyTrader] 异常堆栈:\n{traceback.format_exc()}")
                continue

        if final_decisions:
            trace = ','.join(used_strategy_names) if used_strategy_names else '策略命中'
            return {
                'decisions': final_decisions,
                'prompt': None,
                'raw_response': json.dumps({
                    'strategies': used_strategy_names,
                    'decisions': final_decisions,
                    'remaining_position_count': len(remaining_positions)
                }, ensure_ascii=False, default=str),
                'cot_trace': trace,
                'skipped': False
            }

        logger.info(f"[StrategyTrader] [Model {effective_model_id}] 所有策略都未返回有效信号，返回hold决策")
        return {
            'decisions': {},
            'prompt': None,
            'raw_response': None,
            'cot_trace': '所有策略未命中',
            'skipped': False
        }

