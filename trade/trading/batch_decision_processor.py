"""
批量决策处理器模块 - 封装批量决策处理逻辑

本模块提供BatchDecisionProcessor类，用于处理批量决策的合并、执行和状态更新。
将批量决策处理相关的逻辑从TradingEngine中抽象出来，提高代码的可维护性。
"""
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)


class BatchDecisionProcessor:
    """
    批量决策处理器类
    
    负责处理批量决策的合并、执行和状态更新，包括：
    - 合并批次决策
    - 记录AI对话
    - 执行决策
    - 更新portfolio和account_info
    """
    
    def __init__(
        self,
        model_id: int,
        execute_decisions_func,
        record_ai_conversation_func,
        get_portfolio_func,
        build_account_info_func
    ):
        """
        初始化批量决策处理器
        
        Args:
            model_id: 模型ID
            execute_decisions_func: 执行决策的函数
            record_ai_conversation_func: 记录AI对话的函数
            get_portfolio_func: 获取portfolio的函数
            build_account_info_func: 构建account_info的函数
        """
        self.model_id = model_id
        self._execute_decisions = execute_decisions_func
        self._record_ai_conversation = record_ai_conversation_func
        self._get_portfolio = get_portfolio_func
        self._build_account_info = build_account_info_func
    
    def merge_group_decisions(self, group_decisions: List[Dict]) -> Dict:
        """
        合并批次组决策
        
        Args:
            group_decisions: 批次组决策列表
        
        Returns:
            Dict: 包含合并后的决策、对话和市场状态。其中 'decisions' 为 Dict[symbol, List[decision]]
        """
        all_decisions = {}
        all_payloads = []
        all_market_states = {}
        
        for batch_data in group_decisions:
            payload = batch_data.get('payload', {})
            decisions = payload.get('decisions') or {}
            batch_market_state = batch_data.get('batch_market_state', {})
            batch_num = batch_data.get('batch_num', 0)
            
            # 合并决策：格式为 Dict[symbol, List[decision]]，按 symbol 合并为 List
            for symbol, val in decisions.items():
                list_dec = val if isinstance(val, list) else []
                if not list_dec:
                    continue
                if symbol not in all_decisions:
                    all_decisions[symbol] = []
                all_decisions[symbol].extend(list_dec)
                for d in list_dec:
                    if isinstance(d, dict):
                        logger.debug(f"[Model {self.model_id}] [批次组处理] 批次 {batch_num} 决策: {symbol} -> {d.get('signal', 'N/A')}")
            
            # 合并market_state
            all_market_states.update(batch_market_state)
            
            # 保存payload用于记录对话
            if not payload.get('skipped') and payload.get('prompt'):
                all_payloads.append(payload)
        
        return {
            'decisions': all_decisions,
            'payloads': all_payloads,
            'market_states': all_market_states
        }
    
    def record_conversations(self, payloads: List[Dict], conversation_type: str = 'buy') -> None:
        """
        记录AI对话到数据库
        
        Args:
            payloads: 对话payload列表
            conversation_type: 对话类型（'buy'或'sell'）
        """
        logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤1] 记录AI对话到数据库...")
        for payload in payloads:
            try:
                self._record_ai_conversation(payload, conversation_type=conversation_type)
            except Exception as e:
                logger.error(f"[Model {self.model_id}] [批次组处理] 记录AI对话失败: {e}")
        logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤1] AI对话已记录")
    
    def execute_decisions(
        self,
        decisions: Dict,
        market_states: Dict,
        current_prices: Dict[str, float],
        executions: List
    ) -> List[Dict]:
        """
        执行决策
        
        Args:
            decisions: 决策字典，格式为 Dict[symbol, List[decision]]（每个 symbol 对应决策列表）
            market_states: 市场状态字典
            current_prices: 当前价格字典
            executions: 执行结果列表（会被更新）
        
        Returns:
            List[Dict]: 执行结果列表
        """
        logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2] 开始顺序执行决策...")
        
        # 获取最新持仓状态
        logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.1] 获取最新持仓状态...")
        latest_portfolio = self._get_portfolio(self.model_id, current_prices)
        logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.1] 最新持仓状态: "
                    f"总价值=${latest_portfolio.get('total_value', 0):.2f}, "
                    f"现金=${latest_portfolio.get('cash', 0):.2f}, "
                    f"持仓数={len(latest_portfolio.get('positions', []) or [])}")
        
        # 执行所有决策
        logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.2] 开始执行决策...")
        execution_start = datetime.now(timezone(timedelta(hours=8)))
        batch_results = self._execute_decisions(decisions, market_states, latest_portfolio)
        execution_duration = (datetime.now(timezone(timedelta(hours=8))) - execution_start).total_seconds()
        logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.2] 决策执行完成: 耗时={execution_duration:.2f}秒, 结果数={len(batch_results)}")
        
        # 记录每个执行结果
        for idx, result in enumerate(batch_results):
            # 安全获取字段值，避免None导致格式化错误
            symbol = result.get('symbol', 'N/A')
            signal = result.get('signal', 'N/A')
            position_amt = result.get('position_amt', 0)
            price = result.get('price')
            error = result.get('error', '无')

            # 格式化价格字段，处理None值
            price_str = f"${price:.4f}" if price is not None else "N/A"

            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.2.{idx+1}] 执行结果: "
                        f"合约={symbol}, "
                        f"信号={signal}, "
                        f"数量={position_amt}, "
                        f"价格={price_str}, "
                        f"错误={error}")
        
        # 添加到执行结果列表
        logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.3] 添加执行结果到列表（当前总数: {len(executions)}）...")
        executions.extend(batch_results)
        logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.3] 执行结果已添加（新总数: {len(executions)}）")
        
        return batch_results
    
    def update_portfolio_and_account_info(
        self,
        portfolio: Dict,
        account_info: Dict,
        constraints: Optional[Dict],
        current_prices: Dict[str, float]
    ) -> None:
        """
        更新portfolio和account_info
        
        Args:
            portfolio: 持仓组合信息（会被更新）
            account_info: 账户信息（会被更新）
            constraints: 约束条件（可选，会被更新）
            current_prices: 当前价格字典
        """
        logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤3] 更新portfolio和account_info...")
        
        latest_portfolio = self._get_portfolio(self.model_id, current_prices)
        
        # 更新portfolio引用
        old_cash = portfolio.get('cash', 0)
        old_positions = len(portfolio.get('positions', []) or [])
        portfolio.update(latest_portfolio)
        new_cash = portfolio.get('cash', 0)
        new_positions = len(portfolio.get('positions', []) or [])
        logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤3.1] portfolio已更新: "
                    f"现金 ${old_cash:.2f} -> ${new_cash:.2f}, "
                    f"持仓数 {old_positions} -> {new_positions}")
        
        # 更新account_info
        updated_account_info = self._build_account_info(latest_portfolio)
        account_info.update(updated_account_info)
        logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤3.2] account_info已更新: "
                    f"总收益率={updated_account_info.get('total_return', 0):.2f}%")
        
        # 更新constraints（如果提供）
        if constraints is not None:
            old_occupied = constraints.get('occupied', 0)
            old_available_cash = constraints.get('available_cash', 0)
            constraints['occupied'] = len(latest_portfolio.get('positions', []) or [])
            constraints['available_cash'] = latest_portfolio.get('cash', 0)
            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤3.3] constraints已更新: "
                        f"已占用 {old_occupied} -> {constraints['occupied']}, "
                        f"可用现金 ${old_available_cash:.2f} -> ${constraints['available_cash']:.2f}")
        
        logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤3] 状态更新完成")

