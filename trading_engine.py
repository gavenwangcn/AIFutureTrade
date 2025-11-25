"""
Trading Engine - Core trading logic for executing AI trading decisions
"""
from datetime import datetime
from typing import Dict, List, Optional
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import config as app_config
from prompt_defaults import DEFAULT_BUY_CONSTRAINTS, DEFAULT_SELL_CONSTRAINTS

logger = logging.getLogger(__name__)

class TradingEngine:
    def __init__(self, model_id: int, db, market_fetcher, ai_trader, trade_fee_rate: float = 0.001):
        """Initialize trading engine for a model"""
        self.model_id = model_id
        self.db = db
        self.market_fetcher = market_fetcher
        self.ai_trader = ai_trader
        self.trade_fee_rate = trade_fee_rate
        self.max_positions = 3

    # ============ Main Trading Cycle ============

    def execute_trading_cycle(self) -> Dict:
        """
        执行一个完整的交易周期
        
        交易周期流程：
        1. 初始化阶段：获取市场状态、持仓信息、账户信息、提示词模板等
        2. 卖出决策阶段：优先处理卖出/平仓决策（风控优先）
        3. 买入决策阶段：分批处理买入决策（多线程并发，每批立即执行）
        4. 记录阶段：记录账户价值快照
        
        返回：
            Dict: {
                'success': bool,  # 是否成功
                'executions': List,  # 执行结果列表
                'portfolio': Dict,  # 最终持仓信息
                'conversations': List,  # 对话类型列表 ['sell', 'buy']
                'error': str  # 错误信息（如果失败）
            }
        """
        logger.debug(f"[Model {self.model_id}] ========== 开始执行交易周期 ==========")
        cycle_start_time = datetime.now()
        
        try:
            # ========== 阶段1: 初始化数据准备 ==========
            logger.debug(f"[Model {self.model_id}] [阶段1] 开始初始化数据准备")
            
            # 获取市场状态（包含价格和技术指标）
            logger.debug(f"[Model {self.model_id}] [阶段1.1] 获取市场状态...")
            market_state = self._get_market_state()
            logger.debug(f"[Model {self.model_id}] [阶段1.1] 市场状态获取完成, 跟踪合约数: {len(market_state)}")
            
            # 提取当前价格映射（用于计算持仓价值）
            current_prices = self._extract_price_map(market_state)
            logger.debug(f"[Model {self.model_id}] [阶段1.2] 价格映射提取完成, 价格数量: {len(current_prices)}")
            
            # 获取当前持仓信息
            portfolio = self.db.get_portfolio(self.model_id, current_prices)
            logger.debug(f"[Model {self.model_id}] [阶段1.3] 持仓信息获取完成: "
                        f"总价值=${portfolio.get('total_value', 0):.2f}, "
                        f"现金=${portfolio.get('cash', 0):.2f}, "
                        f"持仓数={len(portfolio.get('positions', []) or [])}")
            
            # 构建账户信息（用于AI决策）
            account_info = self._build_account_info(portfolio)
            logger.debug(f"[Model {self.model_id}] [阶段1.4] 账户信息构建完成: "
                        f"初始资金=${account_info.get('initial_capital', 0):.2f}, "
                        f"总收益率={account_info.get('total_return', 0):.2f}%")
            
            # 获取提示词模板（买入和卖出约束）
            prompt_templates = self._get_prompt_templates()
            logger.debug(f"[Model {self.model_id}] [阶段1.5] 提示词模板获取完成: "
                        f"买入提示词长度={len(prompt_templates.get('buy', ''))}, "
                        f"卖出提示词长度={len(prompt_templates.get('sell', ''))}")
            
            # 获取市场快照（涨跌幅榜，用于AI决策参考）
            market_snapshot = self._get_prompt_market_snapshot()
            logger.debug(f"[Model {self.model_id}] [阶段1.6] 市场快照获取完成, 快照数量: {len(market_snapshot)}")
            
            # 获取模型杠杆配置
            self.current_model_leverage = self._get_model_leverage()
            logger.debug(f"[Model {self.model_id}] [阶段1.7] 模型杠杆配置: {self.current_model_leverage}x")
            
            # 初始化执行结果和对话记录
            executions = []
            conversation_prompts = []
            logger.debug(f"[Model {self.model_id}] [阶段1] 初始化完成")

            # ========== 阶段2: 卖出/平仓决策处理（风控优先） ==========
            logger.debug(f"[Model {self.model_id}] [阶段2] 开始处理卖出/平仓决策")
            
            # 检查是否有持仓需要处理
            positions_count = len(portfolio.get('positions', []) or [])
            logger.debug(f"[Model {self.model_id}] [阶段2.1] 当前持仓数量: {positions_count}")
            
            if positions_count > 0:
                logger.debug(f"[Model {self.model_id}] [阶段2.2] 调用AI模型进行卖出决策...")
                sell_payload = self.ai_trader.make_sell_decision(
                    portfolio,
                    market_state,
                    account_info,
                    constraints_text=prompt_templates['sell'],
                    market_snapshot=market_snapshot
                )
                
                # 检查AI决策结果
                is_skipped = sell_payload.get('skipped', False)
                has_prompt = bool(sell_payload.get('prompt'))
                decisions = sell_payload.get('decisions') or {}
                logger.debug(f"[Model {self.model_id}] [阶段2.3] AI卖出决策完成: "
                            f"跳过={is_skipped}, 有提示词={has_prompt}, 决策数量={len(decisions)}")
                
                if not is_skipped and has_prompt:
                    # 记录AI对话到数据库
                    logger.debug(f"[Model {self.model_id}] [阶段2.4] 记录AI对话到数据库...")
                    self._record_ai_conversation(sell_payload)
                    
                    # 执行卖出决策
                    logger.debug(f"[Model {self.model_id}] [阶段2.5] 开始执行卖出决策, 决策详情: {list(decisions.keys())}")
                    sell_results = self._execute_decisions(
                        decisions,
                        market_state,
                        portfolio
                    )
                    logger.debug(f"[Model {self.model_id}] [阶段2.6] 卖出决策执行完成, 执行结果数: {len(sell_results)}")
                    for idx, result in enumerate(sell_results):
                        logger.debug(f"[Model {self.model_id}] [阶段2.6.{idx+1}] 执行结果: "
                                    f"合约={result.get('future')}, "
                                    f"信号={result.get('signal')}, "
                                    f"错误={result.get('error', '无')}")
                    
                    executions.extend(sell_results)
                    conversation_prompts.append('sell')
                    
                    # 更新持仓信息（卖出后持仓状态已改变）
                    logger.debug(f"[Model {self.model_id}] [阶段2.7] 更新持仓信息...")
                    portfolio = self.db.get_portfolio(self.model_id, current_prices)
                    account_info = self._build_account_info(portfolio)
                    logger.debug(f"[Model {self.model_id}] [阶段2.7] 持仓信息更新完成: "
                                f"总价值=${portfolio.get('total_value', 0):.2f}, "
                                f"现金=${portfolio.get('cash', 0):.2f}, "
                                f"持仓数={len(portfolio.get('positions', []) or [])}")
                else:
                    logger.debug(f"[Model {self.model_id}] [阶段2] 卖出决策被跳过或无有效决策")
            else:
                logger.debug(f"[Model {self.model_id}] [阶段2] 无持仓，跳过卖出决策处理")
            
            logger.debug(f"[Model {self.model_id}] [阶段2] 卖出/平仓决策处理完成")

            # ========== 阶段3: 买入决策处理（分批多线程） ==========
            logger.debug(f"[Model {self.model_id}] [阶段3] 开始处理买入决策")
            
            # 从涨跌幅榜选择买入候选
            logger.debug(f"[Model {self.model_id}] [阶段3.1] 从涨跌幅榜选择买入候选...")
            buy_candidates = self._select_buy_candidates(portfolio)
            logger.debug(f"[Model {self.model_id}] [阶段3.1] 买入候选选择完成, 候选数量: {len(buy_candidates)}")
            if buy_candidates:
                for idx, candidate in enumerate(buy_candidates[:5]):  # 只记录前5个
                    logger.debug(f"[Model {self.model_id}] [阶段3.1.{idx+1}] 候选: "
                                f"{candidate.get('symbol')}, "
                                f"价格=${candidate.get('price', 0):.4f}, "
                                f"涨跌幅={candidate.get('change_percent', 0):.2f}%")
            
            if buy_candidates:
                # 将候选合约添加到市场状态中
                logger.debug(f"[Model {self.model_id}] [阶段3.2] 将候选合约添加到市场状态...")
                market_state = self._augment_market_state_with_candidates(market_state, buy_candidates)
                current_prices = self._extract_price_map(market_state)
                logger.debug(f"[Model {self.model_id}] [阶段3.2] 市场状态更新完成, 总合约数: {len(market_state)}")
                
                # 构建约束条件（用于AI决策）
                constraints = {
                    'max_positions': self.max_positions,
                    'occupied': len(portfolio.get('positions', []) or []),
                    'available_cash': portfolio.get('cash', 0)
                }
                logger.debug(f"[Model {self.model_id}] [阶段3.3] 约束条件构建完成: "
                            f"最大持仓数={constraints['max_positions']}, "
                            f"已占用={constraints['occupied']}, "
                            f"可用现金=${constraints['available_cash']:.2f}")
                
                # 分批处理买入决策（多线程并发，每批立即执行）
                logger.debug(f"[Model {self.model_id}] [阶段3.4] 开始分批处理买入决策（多线程）...")
                self._make_batch_buy_decisions(
                    buy_candidates,
                    portfolio,
                    account_info,
                    constraints,
                    prompt_templates['buy'],
                    market_snapshot,
                    market_state,
                    executions,
                    conversation_prompts,
                    current_prices
                )
                logger.debug(f"[Model {self.model_id}] [阶段3.4] 分批买入决策处理完成")
                
                # 更新持仓信息（所有批次处理完成后）
                logger.debug(f"[Model {self.model_id}] [阶段3.5] 更新最终持仓信息...")
                portfolio = self.db.get_portfolio(self.model_id, current_prices)
                account_info = self._build_account_info(portfolio)
                logger.debug(f"[Model {self.model_id}] [阶段3.5] 最终持仓信息: "
                            f"总价值=${portfolio.get('total_value', 0):.2f}, "
                            f"现金=${portfolio.get('cash', 0):.2f}, "
                            f"持仓数={len(portfolio.get('positions', []) or [])}")
            else:
                logger.debug(f"[Model {self.model_id}] [阶段3] 无买入候选，跳过买入决策处理")
            
            logger.debug(f"[Model {self.model_id}] [阶段3] 买入决策处理完成")

            # ========== 阶段4: 记录账户价值快照 ==========
            logger.debug(f"[Model {self.model_id}] [阶段4] 开始记录账户价值快照")
            
            updated_portfolio = self.db.get_portfolio(self.model_id, current_prices)
            logger.debug(f"[Model {self.model_id}] [阶段4.1] 账户价值: "
                        f"总价值=${updated_portfolio.get('total_value', 0):.2f}, "
                        f"现金=${updated_portfolio.get('cash', 0):.2f}, "
                        f"持仓价值=${updated_portfolio.get('positions_value', 0):.2f}")
            
            self.db.record_account_value(
                self.model_id,
                updated_portfolio['total_value'],
                updated_portfolio['cash'],
                updated_portfolio['positions_value']
            )
            logger.debug(f"[Model {self.model_id}] [阶段4.2] 账户价值快照已记录到数据库")
            
            # ========== 交易周期完成 ==========
            cycle_end_time = datetime.now()
            cycle_duration = (cycle_end_time - cycle_start_time).total_seconds()
            logger.debug(f"[Model {self.model_id}] ========== 交易周期执行完成 ==========")
            logger.debug(f"[Model {self.model_id}] 执行统计: "
                        f"总耗时={cycle_duration:.2f}秒, "
                        f"执行操作数={len(executions)}, "
                        f"对话类型={conversation_prompts}")
            
            return {
                'success': True,
                'executions': executions,
                'portfolio': updated_portfolio,
                'conversations': conversation_prompts
            }

        except Exception as e:
            cycle_end_time = datetime.now()
            cycle_duration = (cycle_end_time - cycle_start_time).total_seconds()
            logger.error(f"[Model {self.model_id}] ========== 交易周期执行失败 ==========")
            logger.error(f"[Model {self.model_id}] 错误信息: {e}")
            logger.error(f"[Model {self.model_id}] 执行耗时: {cycle_duration:.2f}秒")
            import traceback
            logger.error(f"[Model {self.model_id}] 错误堆栈:\n{traceback.format_exc()}")
            return {
                'success': False,
                'error': str(e)
            }

    # ============ Market Data Methods ============

    def _get_tracked_symbols(self) -> List[str]:
        """Get list of tracked future symbols"""
        return [future['symbol'] for future in self.db.get_future_configs()]

    def _get_market_state(self) -> Dict:
        """Get current market state with prices and indicators"""
        market_state = {}
        symbols = self._get_tracked_symbols()
        prices = self.market_fetcher.get_prices(symbols)

        for symbol in symbols:
            price_info = prices.get(symbol)
            if price_info:
                market_state[symbol] = price_info.copy()
                indicators = self.market_fetcher.calculate_technical_indicators(symbol)
                market_state[symbol]['indicators'] = indicators

        return market_state

    def _extract_price_map(self, market_state: Dict) -> Dict[str, float]:
        """Extract price map from market state"""
        prices = {}
        for symbol, payload in (market_state or {}).items():
            price = payload.get('price') if isinstance(payload, dict) else None
            if price is not None:
                prices[symbol] = price
        return prices

    def _augment_market_state_with_candidates(self, market_state: Dict, candidates: list) -> Dict:
        """Augment market state with candidate symbols from leaderboard"""
        augmented = dict(market_state)
        for entry in candidates:
            symbol = entry.get('symbol')
            if not symbol:
                continue
            symbol = symbol.upper()
            if symbol in augmented and augmented[symbol].get('price'):
                continue
            augmented[symbol] = {
                'price': entry.get('price', 0),
                'name': entry.get('name', symbol),
                'exchange': entry.get('exchange', 'BINANCE_FUTURES'),
                'contract_symbol': entry.get('contract_symbol') or f"{symbol}USDT",
                'timeframes': entry.get('timeframes') or {},
                'source': 'leaderboard'
            }
        return augmented

    def _get_prompt_market_snapshot(self) -> List[Dict]:
        """Get market snapshot for prompt context"""
        limit = getattr(app_config, 'PROMPT_MARKET_SYMBOL_LIMIT', 5)
        limit = max(1, int(limit))

        try:
            leaderboard = self.market_fetcher.get_leaderboard(limit=limit)
        except Exception as exc:
            logger.warning(f"[Model {self.model_id}] 获取提示词市场快照失败: {exc}")
            return []

        entries = leaderboard.get('gainers') or []
        snapshot = []
        for entry in entries[:limit]:
            symbol = entry.get('symbol')
            if not symbol:
                continue
            snapshot.append({
                'symbol': symbol,
                'contract_symbol': entry.get('contract_symbol'),
                'price': entry.get('price'),
                'quote_volume': entry.get('quote_volume'),
                'timeframes': entry.get('timeframes') or {}
            })

        return snapshot

    # ============ Account Information Methods ============

    def _build_account_info(self, portfolio: Dict) -> Dict:
        """Build account information for AI decision making"""
        model = self.db.get_model(self.model_id)
        initial_capital = model['initial_capital']
        total_value = portfolio['total_value']
        total_return = ((total_value - initial_capital) / initial_capital) * 100

        return {
            'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_return': total_return,
            'initial_capital': initial_capital
        }

    # ============ Prompt Template Methods ============

    def _get_prompt_templates(self) -> Dict[str, str]:
        """Get prompt templates for buy and sell decisions"""
        prompt_config = self.db.get_model_prompt(self.model_id) or {}
        buy_prompt = prompt_config.get('buy_prompt') or DEFAULT_BUY_CONSTRAINTS
        sell_prompt = prompt_config.get('sell_prompt') or DEFAULT_SELL_CONSTRAINTS
        return {'buy': buy_prompt, 'sell': sell_prompt}

    def _record_ai_conversation(self, payload: Dict):
        """Record AI conversation to database"""
        prompt = payload.get('prompt')
        raw_response = payload.get('raw_response')
        cot_trace = payload.get('cot_trace') or ''
        if not isinstance(raw_response, str):
            raw_response = json.dumps(payload.get('decisions', {}), ensure_ascii=False)
        self.db.add_conversation(
            self.model_id,
            user_prompt=prompt,
            ai_response=raw_response,
            cot_trace=cot_trace
        )

    # ============ Buy Candidate Selection Methods ============

    def _make_batch_buy_decisions(
        self,
        candidates: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        constraints: Dict,
        constraints_text: str,
        market_snapshot: Optional[List[Dict]],
        market_state: Dict,
        executions: List,
        conversation_prompts: List,
        current_prices: Dict[str, float]
    ):
        """
        分批处理买入决策（多线程并发，每批立即执行）
        
        流程：
        1. 从配置获取批次大小和线程数
        2. 将候选列表分批
        3. 使用线程池并发处理各批次
        4. 每个批次完成后立即执行该批次的买入操作
        5. 使用锁保证线程安全
        """
        if not candidates:
            logger.debug(f"[Model {self.model_id}] [分批买入] 无候选合约，跳过处理")
            return

        # 从配置获取批次大小和线程数
        batch_size = getattr(app_config, 'PROMPT_MARKET_SYMBOL_LIMIT', 5)
        batch_size = max(1, int(batch_size))
        thread_count = getattr(app_config, 'BUY_DECISION_THREAD_COUNT', 2)
        thread_count = max(1, int(thread_count))
        logger.debug(f"[Model {self.model_id}] [分批买入] 配置参数: 批次大小={batch_size}, 线程数={thread_count}")

        # 将候选列表分批
        batches = []
        for i in range(0, len(candidates), batch_size):
            batches.append(candidates[i:i + batch_size])
        logger.debug(f"[Model {self.model_id}] [分批买入] 候选列表分批完成: "
                    f"总候选数={len(candidates)}, "
                    f"批次数={len(batches)}, "
                    f"每批大小={batch_size}")

        if not batches:
            logger.debug(f"[Model {self.model_id}] [分批买入] 批次列表为空，跳过处理")
            return

        logger.info(f"[Model {self.model_id}] 开始分批处理买入决策: 共 {len(candidates)} 个候选, 分为 {len(batches)} 批, 每批最多 {batch_size} 个, 使用 {thread_count} 个线程")

        # 创建线程安全锁（用于保护portfolio和executions的更新）
        portfolio_lock = threading.Lock()
        has_buy_decision = False
        batch_start_time = datetime.now()

        # 使用线程池并发处理各批次
        logger.debug(f"[Model {self.model_id}] [分批买入] 创建线程池，最大工作线程数: {thread_count}")
        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            # 提交所有批次任务到线程池
            futures = []
            for batch_idx, batch in enumerate(batches):
                batch_symbols = [c.get('symbol', 'N/A') for c in batch]
                logger.debug(f"[Model {self.model_id}] [分批买入] 提交批次 {batch_idx + 1}/{len(batches)} 到线程池: {batch_symbols}")
                future = executor.submit(
                    self._process_and_execute_batch,
                    batch,
                    portfolio,
                    account_info,
                    constraints,
                    constraints_text,
                    market_snapshot,
                    market_state,
                    current_prices,
                    portfolio_lock,
                    executions,
                    batch_idx + 1,
                    len(batches)
                )
                futures.append(future)
            logger.debug(f"[Model {self.model_id}] [分批买入] 所有批次任务已提交，等待执行完成...")

            # 等待所有批次完成并检查是否有决策
            completed_batches = 0
            for future_idx, future in enumerate(futures):
                try:
                    payload = future.result()
                    completed_batches += 1
                    if not payload.get('skipped') and payload.get('decisions'):
                        has_buy_decision = True
                    logger.debug(f"[Model {self.model_id}] [分批买入] 批次 {future_idx + 1}/{len(futures)} 完成: "
                                f"跳过={payload.get('skipped')}, "
                                f"决策数={len(payload.get('decisions') or {})}")
                except Exception as exc:
                    logger.error(f"[Model {self.model_id}] [分批买入] 批次 {future_idx + 1} 处理异常: {exc}")
                    import traceback
                    logger.debug(f"[Model {self.model_id}] [分批买入] 异常堆栈:\n{traceback.format_exc()}")

        batch_end_time = datetime.now()
        batch_duration = (batch_end_time - batch_start_time).total_seconds()
        logger.debug(f"[Model {self.model_id}] [分批买入] 所有批次处理完成: "
                    f"完成批次数={completed_batches}/{len(batches)}, "
                    f"总耗时={batch_duration:.2f}秒, "
                    f"平均每批耗时={batch_duration/len(batches):.2f}秒")

        # 如果有任何批次产生了买入决策，添加到对话提示中
        if has_buy_decision and 'buy' not in conversation_prompts:
            conversation_prompts.append('buy')
            logger.debug(f"[Model {self.model_id}] [分批买入] 已添加'buy'到对话提示列表")

    def _process_and_execute_batch(
        self,
        batch_candidates: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        constraints: Dict,
        constraints_text: str,
        market_snapshot: Optional[List[Dict]],
        market_state: Dict,
        current_prices: Dict[str, float],
        portfolio_lock: threading.Lock,
        executions: List,
        batch_num: int,
        total_batches: int
    ) -> Dict:
        """
        处理单个批次：调用AI决策并立即执行
        
        线程内部流程：
        1. 调用AI模型获取买入决策
        2. 记录AI对话到数据库
        3. 获取决策结果
        4. 获取锁，执行决策（线程安全）
        5. 更新portfolio和constraints（供后续批次使用）
        
        注意：此方法在独立线程中执行，需要线程安全处理
        """
        thread_id = threading.current_thread().ident
        batch_start_time = datetime.now()
        batch_symbols = [c.get('symbol', 'N/A') for c in batch_candidates]
        
        logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                    f"开始处理批次，候选合约: {batch_symbols}")
        
        try:
            # ========== 步骤1: 调用AI模型获取买入决策 ==========
            logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                        f"[步骤1] 调用AI模型获取买入决策...")
            logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                        f"[步骤1] 输入参数: 候选数={len(batch_candidates)}, "
                        f"当前持仓数={constraints.get('occupied', 0)}, "
                        f"可用现金=${constraints.get('available_cash', 0):.2f}")
            
            ai_call_start = datetime.now()
            buy_payload = self.ai_trader.make_buy_decision(
                batch_candidates,
                portfolio,
                account_info,
                constraints,
                constraints_text=constraints_text,
                market_snapshot=market_snapshot
            )
            ai_call_duration = (datetime.now() - ai_call_start).total_seconds()
            
            is_skipped = buy_payload.get('skipped', False)
            has_prompt = bool(buy_payload.get('prompt'))
            decisions = buy_payload.get('decisions') or {}
            logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                        f"[步骤1] AI调用完成: 耗时={ai_call_duration:.2f}秒, "
                        f"跳过={is_skipped}, 有提示词={has_prompt}, 决策数={len(decisions)}")

            # 检查是否需要跳过执行
            if is_skipped or not has_prompt:
                logger.info(f"[Model {self.model_id}] 批次 {batch_num}/{total_batches} 跳过执行")
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                            f"跳过原因: skipped={is_skipped}, has_prompt={has_prompt}")
                return buy_payload

            # ========== 步骤2: 记录AI对话到数据库 ==========
            logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                        f"[步骤2] 记录AI对话到数据库...")
            self._record_ai_conversation(buy_payload)
            logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                        f"[步骤2] AI对话已记录")

            # ========== 步骤3: 获取决策结果 ==========
            logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                        f"[步骤3] 解析决策结果...")
            if not decisions:
                logger.info(f"[Model {self.model_id}] 批次 {batch_num}/{total_batches} 无买入决策")
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                            f"[步骤3] 决策结果为空，返回")
                return buy_payload
            
            decision_symbols = list(decisions.keys())
            logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                        f"[步骤3] 决策结果解析完成: 决策合约={decision_symbols}")
            for symbol, decision in decisions.items():
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                            f"[步骤3] 决策详情 [{symbol}]: "
                            f"信号={decision.get('signal')}, "
                            f"数量={decision.get('quantity', 0)}, "
                            f"杠杆={decision.get('leverage', 1)}")

            # ========== 步骤4: 获取锁并执行决策（线程安全） ==========
            logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                        f"[步骤4] 等待获取锁以执行决策...")
            lock_acquire_start = datetime.now()
            
            with portfolio_lock:
                lock_acquire_duration = (datetime.now() - lock_acquire_start).total_seconds()
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                            f"[步骤4.1] 锁已获取，等待时间={lock_acquire_duration:.3f}秒")
                
                # 获取最新持仓状态（可能已被其他批次修改）
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                            f"[步骤4.2] 获取最新持仓状态...")
                latest_portfolio = self.db.get_portfolio(self.model_id, current_prices)
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                            f"[步骤4.2] 最新持仓状态: "
                            f"总价值=${latest_portfolio.get('total_value', 0):.2f}, "
                            f"现金=${latest_portfolio.get('cash', 0):.2f}, "
                            f"持仓数={len(latest_portfolio.get('positions', []) or [])}")
                
                # 执行决策
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                            f"[步骤4.3] 开始执行决策...")
                execution_start = datetime.now()
                batch_results = self._execute_decisions(
                    decisions,
                    market_state,
                    latest_portfolio
                )
                execution_duration = (datetime.now() - execution_start).total_seconds()
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                            f"[步骤4.3] 决策执行完成: 耗时={execution_duration:.2f}秒, 结果数={len(batch_results)}")
                
                # 记录每个执行结果
                for idx, result in enumerate(batch_results):
                    logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                                f"[步骤4.3.{idx+1}] 执行结果: "
                                f"合约={result.get('future')}, "
                                f"信号={result.get('signal')}, "
                                f"数量={result.get('quantity', 0)}, "
                                f"价格=${result.get('price', 0):.4f}, "
                                f"错误={result.get('error', '无')}")
                
                # 添加到执行结果列表（线程安全）
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                            f"[步骤4.4] 添加执行结果到列表（当前总数: {len(executions)}）...")
                executions.extend(batch_results)
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                            f"[步骤4.4] 执行结果已添加（新总数: {len(executions)}）")
                
                logger.info(f"[Model {self.model_id}] 批次 {batch_num}/{total_batches} 执行完成, 决策数: {len(decisions)}, 执行结果: {len(batch_results)}")
                
                # ========== 步骤5: 更新portfolio和constraints（供后续批次使用） ==========
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                            f"[步骤4.5] 更新portfolio和constraints供后续批次使用...")
                
                # 更新portfolio引用（字典更新，影响所有线程）
                old_cash = portfolio.get('cash', 0)
                old_positions = len(portfolio.get('positions', []) or [])
                portfolio.update(latest_portfolio)
                new_cash = portfolio.get('cash', 0)
                new_positions = len(portfolio.get('positions', []) or [])
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                            f"[步骤4.5.1] portfolio已更新: "
                            f"现金 ${old_cash:.2f} -> ${new_cash:.2f}, "
                            f"持仓数 {old_positions} -> {new_positions}")
                
                # 更新account_info
                updated_account_info = self._build_account_info(latest_portfolio)
                account_info.update(updated_account_info)
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                            f"[步骤4.5.2] account_info已更新: "
                            f"总收益率={updated_account_info.get('total_return', 0):.2f}%")
                
                # 更新constraints（供后续批次使用）
                old_occupied = constraints.get('occupied', 0)
                old_available_cash = constraints.get('available_cash', 0)
                constraints['occupied'] = len(latest_portfolio.get('positions', []) or [])
                constraints['available_cash'] = latest_portfolio.get('cash', 0)
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                            f"[步骤4.5.3] constraints已更新: "
                            f"已占用 {old_occupied} -> {constraints['occupied']}, "
                            f"可用现金 ${old_available_cash:.2f} -> ${constraints['available_cash']:.2f}")
                
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                            f"[步骤4.5] 状态更新完成，释放锁")

            # ========== 批次处理完成 ==========
            batch_end_time = datetime.now()
            batch_duration = (batch_end_time - batch_start_time).total_seconds()
            logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                        f"批次处理完成: 总耗时={batch_duration:.2f}秒")

            return buy_payload

        except Exception as exc:
            batch_end_time = datetime.now()
            batch_duration = (batch_end_time - batch_start_time).total_seconds()
            logger.error(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                        f"处理失败: {exc}, 耗时={batch_duration:.2f}秒")
            import traceback
            logger.error(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                        f"错误堆栈:\n{traceback.format_exc()}")
            return {
                'decisions': {},
                'prompt': None,
                'raw_response': None,
                'cot_trace': None,
                'skipped': True
            }

    def _select_buy_candidates(self, portfolio: Dict) -> list:
        """Select buy candidates from leaderboard"""
        try:
            leaderboard = self.market_fetcher.get_leaderboard()
        except Exception as exc:
            logger.warning(f"[Model {self.model_id}] 获取涨幅榜候选失败: {exc}")
            return []

        gainers = leaderboard.get('gainers') or []
        if not gainers:
            return []

        held = {pos['future'] for pos in (portfolio.get('positions') or [])}
        available_slots = max(0, self.max_positions - len(held))
        if available_slots <= 0:
            return []

        filtered = [item for item in gainers if item.get('symbol') not in held]
        return filtered[:available_slots]

    # ============ Decision Execution Methods ============

    def _execute_decisions(self, decisions: Dict, market_state: Dict, portfolio: Dict) -> list:
        """Execute AI trading decisions"""
        results = []

        tracked = set(self._get_tracked_symbols())
        positions_map = {pos['future']: pos for pos in portfolio.get('positions', [])}

        for symbol, decision in decisions.items():
            if symbol not in tracked:
                continue

            signal = decision.get('signal', '').lower()

            try:
                if signal == 'buy_to_enter':
                    result = self._execute_buy(symbol, decision, market_state, portfolio)
                elif signal == 'sell_to_enter':
                    result = {'future': symbol, 'error': '当前账户暂不支持做空'}
                elif signal == 'close_position':
                    if symbol not in positions_map:
                        result = {'future': symbol, 'error': 'No position to close'}
                    else:
                        result = self._execute_close(symbol, decision, market_state, portfolio)
                elif signal == 'hold':
                    result = {'future': symbol, 'signal': 'hold', 'message': '保持观望'}
                else:
                    result = {'future': symbol, 'error': f'Unknown signal: {signal}'}

                results.append(result)

            except Exception as e:
                results.append({'future': symbol, 'error': str(e)})

        return results

    # ============ Trade Execution Methods ============

    def _execute_buy(self, symbol: str, decision: Dict, market_state: Dict, portfolio: Dict) -> Dict:
        """Execute buy order"""
        quantity = decision.get('quantity', 0)
        leverage = self._resolve_leverage(decision)
        price = market_state[symbol]['price']

        positions = portfolio.get('positions', [])
        existing_symbols = {pos['future'] for pos in positions}
        if symbol not in existing_symbols and len(existing_symbols) >= self.max_positions:
            return {'future': symbol, 'error': '达到最大持仓数量，无法继续开仓'}

        max_affordable_qty = portfolio['cash'] / (price * (1 + self.trade_fee_rate))
        risk_pct = float(decision.get('risk_budget_pct', 3)) / 100
        risk_pct = min(max(risk_pct, 0.01), 0.05)
        risk_based_qty = (portfolio['cash'] * risk_pct) / (price * (1 + self.trade_fee_rate))

        quantity = float(quantity)
        if quantity <= 0 or quantity > max_affordable_qty:
            quantity = min(max_affordable_qty, risk_based_qty if risk_based_qty > 0 else max_affordable_qty)

        if quantity <= 0:
            return {'future': symbol, 'error': '现金不足，无法买入'}

        trade_amount = quantity * price
        trade_fee = trade_amount * self.trade_fee_rate
        required_margin = (quantity * price) / leverage
        total_required = required_margin + trade_fee

        if total_required > portfolio['cash']:
            return {'future': symbol, 'error': '可用资金不足（含手续费）'}

        # Update position
        try:
            self.db.update_position(
                self.model_id, symbol, quantity, price, leverage, 'long'
            )
        except Exception as db_err:
            logger.error(f"TRADE: Update position failed (BUY) model={self.model_id} future={symbol}: {db_err}")
            raise

        # Record trade
        logger.info(f"TRADE: PENDING - Model {self.model_id} BUY {symbol} qty={quantity} price={price} fee={trade_fee}")
        try:
            self.db.add_trade(
                self.model_id, symbol, 'buy_to_enter', quantity,
                price, leverage, 'long', pnl=0, fee=trade_fee
            )
        except Exception as db_err:
            logger.error(f"TRADE: Add trade failed (BUY) model={self.model_id} future={symbol}: {db_err}")
            raise
        logger.info(f"TRADE: RECORDED - Model {self.model_id} BUY {symbol}")

        return {
            'future': symbol,
            'signal': 'buy_to_enter',
            'quantity': quantity,
            'price': price,
            'leverage': leverage,
            'fee': trade_fee,
            'message': f'买入 {symbol} {quantity:.4f} @ ${price:.2f} (手续费: ${trade_fee:.2f})'
        }

    def _execute_close(self, symbol: str, decision: Dict, market_state: Dict, portfolio: Dict) -> Dict:
        """Execute close position order"""
        position = None
        for pos in portfolio['positions']:
            if pos['future'] == symbol:
                position = pos
                break

        if not position:
            return {'future': symbol, 'error': 'Position not found'}

        current_price = market_state[symbol]['price']
        entry_price = position['avg_price']
        quantity = position['quantity']
        side = position['side']

        # Calculate gross P&L (before fees)
        if side == 'long':
            gross_pnl = (current_price - entry_price) * quantity
        else:  # short
            gross_pnl = (entry_price - current_price) * quantity

        # Calculate closing trade fee
        trade_amount = quantity * current_price
        trade_fee = trade_amount * self.trade_fee_rate
        net_pnl = gross_pnl - trade_fee

        # Close position
        try:
            self.db.close_position(self.model_id, symbol, side)
        except Exception as db_err:
            logger.error(f"TRADE: Close position failed model={self.model_id} future={symbol}: {db_err}")
            raise

        # Record trade
        logger.info(f"TRADE: PENDING - Model {self.model_id} CLOSE {symbol} side={side} qty={quantity} price={current_price} fee={trade_fee} net_pnl={net_pnl}")
        try:
            self.db.add_trade(
                self.model_id, symbol, 'close_position', quantity,
                current_price, position['leverage'], side, pnl=net_pnl, fee=trade_fee
            )
        except Exception as db_err:
            logger.error(f"TRADE: Add trade failed (CLOSE) model={self.model_id} future={symbol}: {db_err}")
            raise
        logger.info(f"TRADE: RECORDED - Model {self.model_id} CLOSE {symbol}")

        return {
            'future': symbol,
            'signal': 'close_position',
            'quantity': quantity,
            'price': current_price,
            'pnl': net_pnl,
            'fee': trade_fee,
            'message': f'平仓 {symbol}, 毛收益 ${gross_pnl:.2f}, 手续费 ${trade_fee:.2f}, 净收益 ${net_pnl:.2f}'
        }

    # ============ Leverage Management Methods ============

    def _get_model_leverage(self) -> int:
        """Get model leverage configuration"""
        try:
            model = self.db.get_model(self.model_id)
        except Exception as exc:
            logger.warning(f"[Model {self.model_id}] 读取杠杆失败: {exc}")
            return 10

        if not model:
            return 10

        leverage = model.get('leverage', 10)
        try:
            leverage = int(leverage)
        except (TypeError, ValueError):
            leverage = 10
        return max(0, leverage)

    def _resolve_leverage(self, decision: Dict) -> int:
        """Resolve leverage from decision or model configuration"""
        configured = getattr(self, 'current_model_leverage', None)
        if configured is None:
            configured = self._get_model_leverage()

        ai_leverage = decision.get('leverage')
        try:
            ai_leverage = int(ai_leverage)
        except (TypeError, ValueError):
            ai_leverage = 1

        ai_leverage = max(1, ai_leverage)

        if configured == 0:
            return ai_leverage

        return max(1, configured)
