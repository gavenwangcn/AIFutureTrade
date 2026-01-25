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
    
    def _normalize_quantity_to_int(self, decisions: Dict) -> Dict:
        """
        规范化decisions中的quantity为整数
        
        Args:
            decisions: 决策字典，key为交易对符号，value为决策详情
            
        Returns:
            规范化后的决策字典，所有quantity字段都转换为整数
        """
        normalized_decisions = {}
        for symbol, decision in decisions.items():
            normalized_decision = decision.copy()
            # 如果decision中有quantity字段，转换为整数
            if 'quantity' in normalized_decision and normalized_decision['quantity'] is not None:
                try:
                    quantity = normalized_decision['quantity']
                    # 转换为浮点数后再转换为整数（向下取整）
                    normalized_decision['quantity'] = int(float(quantity))
                    logger.debug(f"[StrategyTrader] 规范化 {symbol} 的quantity: {quantity} -> {normalized_decision['quantity']}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"[StrategyTrader] 无法转换 {symbol} 的quantity为整数: {normalized_decision.get('quantity')}, 错误: {e}")
                    # 如果转换失败，设置为0或保持原值（根据业务需求）
                    normalized_decision['quantity'] = 0
            normalized_decisions[symbol] = normalized_decision
        return normalized_decisions
    
    def make_buy_decision(
        self,
        candidates: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        market_state: Dict,
        model_id: Optional[int] = None
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

        # 语义要求：按优先级对“每个symbol”判定，某个symbol命中后不再继续判断后续策略；
        # 但对未命中的其他symbol仍继续执行后续策略。
        candidate_symbols = []
        try:
            candidate_symbols = [str(c.get('symbol') or c.get('contract_symbol') or '').upper() for c in candidates]
            candidate_symbols = [s for s in candidate_symbols if s]
        except Exception:
            candidate_symbols = []
        candidate_symbol_set = set(candidate_symbols)

        final_decisions: Dict[str, Dict] = {}
        used_strategy_names: List[str] = []

        valid_signals = {'buy_to_long', 'buy_to_short'}

        # 按优先级顺序执行策略（对每个symbol单独“短路”）
        for strategy in strategies:
            strategy_name = strategy.get('strategy_name', '未知策略')
            strategy_code = strategy.get('strategy_code', '')
            priority = strategy.get('priority', 0)

            if not strategy_code or not strategy_code.strip():
                logger.debug(f"[StrategyTrader] [Model {effective_model_id}] 策略 {strategy_name} (优先级: {priority}) 代码为空，跳过")
                continue

            # 如果已经对所有候选symbol产生了决策，提前结束
            if candidate_symbol_set and len(final_decisions) >= len(candidate_symbol_set):
                break

            logger.debug(f"[StrategyTrader] [Model {effective_model_id}] 执行策略: {strategy_name} (优先级: {priority})")

            try:
                decision_result = self.code_executor.execute_strategy_code(
                    strategy_code=strategy_code,
                    strategy_name=strategy_name,
                    candidates=candidates,
                    portfolio=portfolio,
                    account_info=account_info,
                    market_state=market_state,
                    decision_type='buy'
                )

                if not decision_result or not isinstance(decision_result, dict):
                    logger.debug(f"[StrategyTrader] [Model {effective_model_id}] 策略 {strategy_name} 返回结果无效，继续下一个策略")
                    continue

                decisions = decision_result.get('decisions', {}) or {}
                if not isinstance(decisions, dict) or not decisions:
                    continue

                # 规范化quantity为整数
                normalized_decisions = self._normalize_quantity_to_int(decisions)

                added_any = False
                for sym, dec in normalized_decisions.items():
                    if not isinstance(dec, dict):
                        continue

                    sym_upper = str(sym).upper()
                    if not sym_upper:
                        continue

                    # 如果给了候选列表，则只接受候选里的symbol
                    if candidate_symbol_set and sym_upper not in candidate_symbol_set:
                        continue

                    # per-symbol短路：已命中过就不再覆盖
                    if sym_upper in final_decisions:
                        continue

                    sig = (dec.get('signal') or '').lower()
                    if sig not in valid_signals:
                        continue

                    qty = dec.get('quantity')
                    try:
                        if qty is None or float(qty) <= 0:
                            continue
                    except Exception:
                        continue

                    # 回填策略追踪信息（供后续策略记录/落库使用）
                    dec.setdefault('_strategy_name', strategy_name)
                    dec.setdefault('_strategy_type', 'buy')

                    final_decisions[sym_upper] = dec
                    added_any = True

                if added_any:
                    used_strategy_names.append(strategy_name)

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
                'raw_response': json.dumps({'strategies': used_strategy_names, 'decisions': final_decisions}, ensure_ascii=False),
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
        model_id: Optional[int] = None
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

        position_symbols = []
        try:
            position_symbols = [str(p.get('symbol') or '').upper() for p in (portfolio.get('positions') or [])]
            position_symbols = [s for s in position_symbols if s]
        except Exception:
            position_symbols = []
        position_symbol_set = set(position_symbols)

        final_decisions: Dict[str, Dict] = {}
        used_strategy_names: List[str] = []
        valid_signals = {'sell_to_long', 'sell_to_short', 'close_position', 'stop_loss', 'take_profit'}

        for strategy in strategies:
            strategy_name = strategy.get('strategy_name', '未知策略')
            strategy_code = strategy.get('strategy_code', '')
            priority = strategy.get('priority', 0)

            if not strategy_code or not strategy_code.strip():
                logger.debug(f"[StrategyTrader] [Model {effective_model_id}] 策略 {strategy_name} (优先级: {priority}) 代码为空，跳过")
                continue

            if position_symbol_set and len(final_decisions) >= len(position_symbol_set):
                break

            logger.debug(f"[StrategyTrader] [Model {effective_model_id}] 执行策略: {strategy_name} (优先级: {priority})")

            try:
                decision_result = self.code_executor.execute_strategy_code(
                    strategy_code=strategy_code,
                    strategy_name=strategy_name,
                    candidates=None,
                    portfolio=portfolio,
                    account_info=account_info,
                    market_state=market_state,
                    decision_type='sell'
                )

                if not decision_result or not isinstance(decision_result, dict):
                    logger.debug(f"[StrategyTrader] [Model {effective_model_id}] 策略 {strategy_name} 返回结果无效，继续下一个策略")
                    continue

                decisions = decision_result.get('decisions', {}) or {}
                if not isinstance(decisions, dict) or not decisions:
                    continue

                normalized_decisions = self._normalize_quantity_to_int(decisions)

                added_any = False
                for sym, dec in normalized_decisions.items():
                    if not isinstance(dec, dict):
                        continue

                    sym_upper = str(sym).upper()
                    if not sym_upper:
                        continue

                    if position_symbol_set and sym_upper not in position_symbol_set:
                        continue

                    if sym_upper in final_decisions:
                        continue

                    sig = (dec.get('signal') or '').lower()
                    if sig not in valid_signals:
                        continue

                    dec.setdefault('_strategy_name', strategy_name)
                    dec.setdefault('_strategy_type', 'sell')

                    final_decisions[sym_upper] = dec
                    added_any = True

                if added_any:
                    used_strategy_names.append(strategy_name)

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
                'raw_response': json.dumps({'strategies': used_strategy_names, 'decisions': final_decisions}, ensure_ascii=False),
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

