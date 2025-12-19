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
from common.database.database_strategys import StrategysDatabase
from common.database.database_models import ModelsDatabase

logger = logging.getLogger(__name__)


class StrategyTrader(Trader):
    """
    基于策略代码的交易决策生成器
    
    通过执行model_strategy表中关联的策略代码来生成交易决策。
    策略按优先级顺序执行，直到找到有效的决策信号。
    
    使用示例：
        trader = StrategyTrader(db=db, model_id=1)
        result = trader.make_buy_decision(candidates, portfolio, account_info)
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
    
    def make_buy_decision(
        self,
        candidates: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        market_state: Dict,
        symbol_source: str = 'leaderboard',
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
            symbol_source: 数据源类型
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
        
        # 按优先级顺序执行策略
        for strategy in strategies:
            strategy_name = strategy.get('strategy_name', '未知策略')
            strategy_code = strategy.get('strategy_code', '')
            priority = strategy.get('priority', 0)
            
            if not strategy_code or not strategy_code.strip():
                logger.debug(f"[StrategyTrader] [Model {effective_model_id}] 策略 {strategy_name} (优先级: {priority}) 代码为空，跳过")
                continue
            
            logger.debug(f"[StrategyTrader] [Model {effective_model_id}] 执行策略: {strategy_name} (优先级: {priority})")
            
            try:
                # 执行策略代码（使用StrategyCodeExecutor，统一使用market_state）
                decision_result = self.code_executor.execute_strategy_code(
                    strategy_code=strategy_code,
                    strategy_name=strategy_name,
                    candidates=candidates,
                    portfolio=portfolio,
                    account_info=account_info,
                    market_state=market_state,  # 统一使用market_state
                    symbol_source=symbol_source,
                    decision_type='buy'
                )
                
                # 检查是否有有效的决策信号
                if decision_result and isinstance(decision_result, dict):
                    decisions = decision_result.get('decisions', {})
                    
                    # 检查是否有有效的买入/卖出信号
                    has_valid_signal = False
                    for symbol, decision in decisions.items():
                        signal = decision.get('signal', '').lower()
                        if signal in ['buy_to_enter', 'sell_to_enter']:
                            has_valid_signal = True
                            break
                    
                    if has_valid_signal:
                        logger.info(f"[StrategyTrader] [Model {effective_model_id}] 策略 {strategy_name} 返回有效决策信号")
                        return {
                            'decisions': decisions,
                            'prompt': None,
                            'raw_response': json.dumps(decision_result, ensure_ascii=False),
                            'cot_trace': strategy_name,
                            'skipped': False
                        }
                    else:
                        logger.debug(f"[StrategyTrader] [Model {effective_model_id}] 策略 {strategy_name} 未返回有效信号，继续下一个策略")
                else:
                    logger.debug(f"[StrategyTrader] [Model {effective_model_id}] 策略 {strategy_name} 返回结果无效，继续下一个策略")
            
            except Exception as e:
                logger.error(f"[StrategyTrader] [Model {effective_model_id}] 执行策略 {strategy_name} 失败: {e}")
                import traceback
                logger.debug(f"[StrategyTrader] 异常堆栈:\n{traceback.format_exc()}")
                continue
        
        # 所有策略都未返回有效信号，返回hold决策
        logger.info(f"[StrategyTrader] [Model {effective_model_id}] 所有策略都未返回有效信号，返回hold决策")
        return {
            'decisions': {},
            'prompt': None,
            'raw_response': None,
            'cot_trace': '所有策略未命中',
            'skipped': False  # 不是跳过，而是所有策略都未命中
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
        
        # 按优先级顺序执行策略
        for strategy in strategies:
            strategy_name = strategy.get('strategy_name', '未知策略')
            strategy_code = strategy.get('strategy_code', '')
            priority = strategy.get('priority', 0)
            
            if not strategy_code or not strategy_code.strip():
                logger.debug(f"[StrategyTrader] [Model {effective_model_id}] 策略 {strategy_name} (优先级: {priority}) 代码为空，跳过")
                continue
            
            logger.debug(f"[StrategyTrader] [Model {effective_model_id}] 执行策略: {strategy_name} (优先级: {priority})")
            
            try:
                # 执行策略代码（使用StrategyCodeExecutor）
                decision_result = self.code_executor.execute_strategy_code(
                    strategy_code=strategy_code,
                    strategy_name=strategy_name,
                    candidates=None,  # 卖出决策不需要candidates
                    portfolio=portfolio,
                    account_info=account_info,
                    constraints=None,  # 卖出决策不需要constraints
                    market_snapshot=None,  # 卖出决策不需要market_snapshot
                    market_state=market_state,
                    symbol_source=None,  # 卖出决策不需要symbol_source
                    decision_type='sell'
                )
                
                # 检查是否有有效的决策信号
                if decision_result and isinstance(decision_result, dict):
                    decisions = decision_result.get('decisions', {})
                    
                    # 检查是否有有效的卖出/平仓信号
                    has_valid_signal = False
                    for symbol, decision in decisions.items():
                        signal = decision.get('signal', '').lower()
                        if signal in ['close_position', 'stop_loss', 'take_profit']:
                            has_valid_signal = True
                            break
                    
                    if has_valid_signal:
                        logger.info(f"[StrategyTrader] [Model {effective_model_id}] 策略 {strategy_name} 返回有效决策信号")
                        return {
                            'decisions': decisions,
                            'prompt': None,
                            'raw_response': json.dumps(decision_result, ensure_ascii=False),
                            'cot_trace': strategy_name,
                            'skipped': False
                        }
                    else:
                        logger.debug(f"[StrategyTrader] [Model {effective_model_id}] 策略 {strategy_name} 未返回有效信号，继续下一个策略")
                else:
                    logger.debug(f"[StrategyTrader] [Model {effective_model_id}] 策略 {strategy_name} 返回结果无效，继续下一个策略")
            
            except Exception as e:
                logger.error(f"[StrategyTrader] [Model {effective_model_id}] 执行策略 {strategy_name} 失败: {e}")
                import traceback
                logger.debug(f"[StrategyTrader] 异常堆栈:\n{traceback.format_exc()}")
                continue
        
        # 所有策略都未返回有效信号，返回hold决策
        logger.info(f"[StrategyTrader] [Model {effective_model_id}] 所有策略都未返回有效信号，返回hold决策")
        return {
            'decisions': {},
            'prompt': None,
            'raw_response': None,
            'cot_trace': '所有策略未命中',
            'skipped': False  # 不是跳过，而是所有策略都未命中
        }

