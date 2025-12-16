"""
交易引擎 - AI交易决策执行的核心逻辑模块

本模块提供完整的AI交易执行流程，包括：
- 买入/卖出决策周期的执行
- 市场数据获取和处理
- AI决策的批量处理和并发执行
- 订单执行（开仓、平仓、止损、止盈）
- 账户信息管理和记录

主要功能：
1. 主交易周期：execute_trading_cycle() - 统一入口，协调买入和卖出服务
2. 买入服务：execute_buy_cycle() - 从涨跌幅榜选择候选，调用AI决策并执行买入
3. 卖出服务：execute_sell_cycle() - 对持仓进行卖出/平仓决策并执行
4. 订单执行：支持开仓、平仓、止损、止盈等多种订单类型
5. 并发处理：使用多线程批量处理AI决策，提高执行效率
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import common.config as app_config
from trade.prompt_defaults import DEFAULT_BUY_CONSTRAINTS, DEFAULT_SELL_CONSTRAINTS, PROMPT_JSON_OUTPUT_SUFFIX
from common.binance_futures import BinanceFuturesOrderClient

logger = logging.getLogger(__name__)

class TradingEngine:
    """
    交易引擎类 - 负责执行AI交易决策的完整流程
    
    每个模型实例对应一个TradingEngine，独立管理该模型的交易逻辑。
    支持买入和卖出两个独立的服务线程，以不同的周期执行交易决策。
    """
    
    def __init__(self, model_id: int, db, market_fetcher, ai_trader, trade_fee_rate: float = 0.001,
                 buy_cycle_interval: int = 5, sell_cycle_interval: int = 5):
        """
        初始化交易引擎
        
        Args:
            model_id: 模型ID，用于标识和管理不同的交易模型
            db: 数据库实例，用于数据持久化
            market_fetcher: 市场数据获取器，用于获取实时价格和技术指标
            ai_trader: AI交易决策器，用于生成买入/卖出决策
            trade_fee_rate: 交易费率，默认0.001（0.1%）
            buy_cycle_interval: 买入周期间隔（秒），默认5秒
            sell_cycle_interval: 卖出周期间隔（秒），默认5秒
        
        Note:
            - Binance订单客户端不在初始化时创建，改为每次使用时新建实例
            - 确保每次交易都使用最新的 model 表中的 api_key 和 api_secret
        """
        self.model_id = model_id
        self.db = db
        self.market_fetcher = market_fetcher
        self.ai_trader = ai_trader
        self.trade_fee_rate = trade_fee_rate
        # 从数据库获取 max_positions（最大持仓数量），如果获取失败则使用默认值3
        try:
            model = self.db.get_model(model_id)
            self.max_positions = model.get('max_positions', 3) if model else 3
        except Exception as e:
            logger.warning(f"[TradingEngine] Failed to get max_positions for model {model_id}, using default 3: {e}")
            self.max_positions = 3
        # 配置执行周期（秒）
        self.buy_cycle_interval = buy_cycle_interval
        self.sell_cycle_interval = sell_cycle_interval
        # 线程控制标志
        self.running = False
        self.buy_thread = None
        self.sell_thread = None
        # 全局交易锁，用于协调买入和卖出服务线程之间的并发操作
        self.trading_lock = threading.Lock()
        
        # 【当前对话ID】用于关联交易日志和AI对话记录
        # 使用线程锁保护，确保多线程环境下的数据安全
        self.current_conversation_id_lock = threading.Lock()
        self.current_conversation_id = None
        
        # 【Binance订单客户端】不再在初始化时创建，改为每次使用时新建实例
        # 确保每次交易都使用最新的 model 表中的 api_key 和 api_secret
        # 这样每个model可以使用不同的API账户进行交易，且每次都是最新的凭证

    # ============ 主交易周期方法 ============
    # 提供完整的交易周期执行流程，包括买入和卖出决策

    def execute_sell_cycle(self) -> Dict:
        """
        执行卖出/平仓决策周期
        
        流程：
        1. 初始化数据准备：获取市场状态、持仓信息、账户信息、卖出提示词模板等
        2. 卖出决策处理：调用AI模型获取卖出决策并执行
        3. 记录账户价值快照
        
        返回：
            Dict: {
                'success': bool,  # 是否成功
                'executions': List,  # 执行结果列表
                'portfolio': Dict,  # 最终持仓信息
                'conversations': List,  # 对话类型列表 ['sell']
                'error': str  # 错误信息（如果失败）
            }
        """
        logger.info(f"[Model {self.model_id}] [卖出服务] ========== 开始执行卖出决策周期 ==========")
        cycle_start_time = datetime.now(timezone(timedelta(hours=8)))
        
        try:
            # 检查模型是否存在
            model = self._check_model_exists()
            if not model:
                return {
                    'success': False,
                    'executions': [],
                    'portfolio': {},
                    'conversations': [],
                    'error': f"Model {self.model_id} not found"
                }
                
            # ========== 阶段1: 初始化数据准备 ==========
            logger.debug(f"[Model {self.model_id}] [卖出服务] [阶段1] 开始初始化数据准备")
            
            # 获取市场状态（仅获取价格，不获取技术指标，指标将在批次处理时按需获取）
            logger.debug(f"[Model {self.model_id}] [卖出服务] [阶段1.1] 获取市场状态（仅价格）...")
            market_state = self._get_market_state(include_indicators=False)
            logger.debug(f"[Model {self.model_id}] [卖出服务] [阶段1.1] 市场状态获取完成, 跟踪合约数: {len(market_state)}")
            
            # 提取当前价格映射（用于计算持仓价值）
            current_prices = self._extract_price_map(market_state)
            logger.debug(f"[Model {self.model_id}] [卖出服务] [阶段1.2] 价格映射提取完成, 价格数量: {len(current_prices)}")
            
            # 获取当前持仓信息
            portfolio = self.db.get_portfolio(self.model_id, current_prices)
            logger.debug(f"[Model {self.model_id}] [卖出服务] [阶段1.3] 持仓信息获取完成: "
                        f"总价值=${portfolio.get('total_value', 0):.2f}, "
                        f"现金=${portfolio.get('cash', 0):.2f}, "
                        f"持仓数={len(portfolio.get('positions', []) or [])}")
            
            # 构建账户信息（用于AI决策）
            account_info = self._build_account_info(portfolio)
            logger.debug(f"[Model {self.model_id}] [卖出服务] [阶段1.4] 账户信息构建完成: "
                        f"初始资金=${account_info.get('initial_capital', 0):.2f}, "
                        f"总收益率={account_info.get('total_return', 0):.2f}%")
            
            # 获取提示词模板（仅卖出约束）
            prompt_templates = self._get_prompt_templates()
            logger.debug(f"[Model {self.model_id}] [卖出服务] [阶段1.5] 卖出提示词模板获取完成")
            
            # 初始化执行结果和对话记录
            executions = []
            conversation_prompts = []
            logger.debug(f"[Model {self.model_id}] [卖出服务] [阶段1] 初始化完成")

            # ========== 阶段2: 卖出/平仓决策处理 ==========
            logger.debug(f"[Model {self.model_id}] [卖出服务] [阶段2] 开始处理卖出/平仓决策")
            
            # 检查是否有持仓需要处理
            positions_count = len(portfolio.get('positions', []) or [])
            logger.debug(f"[Model {self.model_id}] [卖出服务] [阶段2.1] 当前持仓数量: {positions_count}")
            
            if positions_count > 0:
                # 获取持仓列表
                # 注意：market_state已在阶段1.1中获取了实时价格（不包含技术指标）
                # 技术指标将在批次处理时按需获取，以提高性能
                positions = portfolio.get('positions', []) or []
                
                # 分批处理卖出决策，每批处理指定数量的symbol
                logger.debug(f"[Model {self.model_id}] [卖出服务] [阶段2.2] 开始分批处理卖出决策...")
                
                # 从配置获取批次大小
                batch_size = getattr(app_config, 'AI_DECISION_SYMBOL_BATCH_SIZE', 1)
                batch_size = max(1, int(batch_size))
                
                # 将持仓分批
                batches = []
                for i in range(0, len(positions), batch_size):
                    batches.append(positions[i:i + batch_size])
                
                logger.debug(f"[Model {self.model_id}] [卖出服务] [阶段2.2] 持仓分批完成: "
                            f"总持仓数={len(positions)}, "
                            f"批次数={len(batches)}, "
                            f"每批大小={batch_size}")
                
                # 从配置获取线程数
                thread_count = getattr(app_config, 'SELL_DECISION_THREAD_COUNT', 2)
                thread_count = max(1, int(thread_count))
                
                logger.info(f"[Model {self.model_id}] 开始分批处理卖出决策: 共 {len(positions)} 个持仓, 分为 {len(batches)} 批, 每批最多 {batch_size} 个, 使用 {thread_count} 个线程")

                # 创建线程安全锁（用于保护portfolio和executions的更新）
                portfolio_lock = threading.Lock()
                has_sell_decision = False
                batch_start_time = datetime.now(timezone(timedelta(hours=8)))

                # 使用线程池并发处理各批次
                logger.info(f"[Model {self.model_id}] [卖出服务] 创建线程池，最大工作线程数: {thread_count}")
                with ThreadPoolExecutor(max_workers=thread_count) as executor:
                    # 提交所有批次任务到线程池
                    futures = []
                    for batch_idx, batch_positions in enumerate(batches):
                        # 提取当前批次的symbol列表
                        batch_symbols = [pos.get('symbol', 'N/A') for pos in batch_positions]
                        
                        # 为当前批次创建只包含对应symbol的market_state子集
                        # 此时才获取该批次symbols的技术指标数据（按需获取，提高性能）
                        batch_market_state = {}
                        for symbol in batch_symbols:
                            if symbol != 'N/A' and symbol in market_state:
                                # 复制基础价格信息
                                batch_market_state[symbol] = market_state[symbol].copy()
                                # 实时获取该symbol的技术指标数据
                                try:
                                    logger.debug(f"[Model {self.model_id}] [卖出服务] 批次 {batch_idx + 1} 正在获取 {symbol} 的技术指标...")
                                    merged_data = self._merge_timeframe_data(symbol)
                                    # 将合并后的数据格式调整为与原有格式兼容
                                    if symbol in merged_data:
                                        batch_market_state[symbol]['indicators'] = {'timeframes': merged_data[symbol]}
                                        logger.debug(f"[Model {self.model_id}] [卖出服务] 批次 {batch_idx + 1} {symbol} 技术指标获取完成")
                                    else:
                                        logger.warning(f"[Model {self.model_id}] [卖出服务] 批次 {batch_idx + 1} {symbol} 技术指标数据为空")
                                        batch_market_state[symbol]['indicators'] = {'timeframes': {}}
                                except Exception as e:
                                    logger.error(f"[Model {self.model_id}] [卖出服务] 批次 {batch_idx + 1} 获取 {symbol} 技术指标失败: {e}")
                                    # 即使指标获取失败，也保留价格信息，indicators设为空
                                    batch_market_state[symbol]['indicators'] = {'timeframes': {}}
                        
                        logger.info(f"[Model {self.model_id}] [卖出服务] 提交批次 {batch_idx + 1}/{len(batches)} 到线程池: "
                                    f"symbols={batch_symbols}, market_state包含{len(batch_market_state)}个symbol（已包含技术指标）")
                        
                        future = executor.submit(
                            self._process_and_execute_sell_batch,
                            batch_positions,
                            portfolio,
                            account_info,
                            batch_market_state,  # 只传递当前批次对应的market_state
                            prompt_templates['sell'],
                            portfolio_lock,
                            executions,
                            batch_idx + 1,
                            len(batches)
                        )
                        futures.append(future)
                    logger.info(f"[Model {self.model_id}] [卖出服务] 所有批次任务已提交，等待执行完成......")

                    # 等待所有批次完成并检查是否有决策
                    completed_batches = 0
                    for future_idx, future in enumerate(futures):
                        try:
                            payload = future.result()
                            completed_batches += 1
                            
                            # 检查是否有实际的卖出决策（排除 hold 操作）
                            # 卖出决策包括：close_position（平仓）、stop_loss（止损）、take_profit（止盈）
                            # hold（继续持有）不算作实际执行的操作
                            decisions = payload.get('decisions') or {}
                            has_actual_decision = False
                            if not payload.get('skipped') and decisions:
                                # 检查是否有非 hold 的决策
                                for symbol, decision in decisions.items():
                                    signal = decision.get('signal', '').lower()
                                    if signal in ['close_position', 'stop_loss', 'take_profit']:
                                        has_actual_decision = True
                                        break
                            
                            if has_actual_decision:
                                has_sell_decision = True
                            
                            # 统计决策类型
                            decision_types = {}
                            for symbol, decision in decisions.items():
                                signal = decision.get('signal', '').lower()
                                decision_types[signal] = decision_types.get(signal, 0) + 1
                            
                            logger.info(f"[Model {self.model_id}] [卖出服务] 批次 {future_idx + 1}/{len(futures)} 完成: "
                                        f"跳过={payload.get('skipped')}, "
                                        f"决策数={len(decisions)}, "
                                        f"决策类型={decision_types}, "
                                        f"有实际执行={has_actual_decision}")
                        except Exception as exc:
                            logger.error(f"[Model {self.model_id}] [卖出服务] 批次 {future_idx + 1} 处理异常: {exc}")
                            import traceback
                            logger.info(f"[Model {self.model_id}] [卖出服务] 异常堆栈:{traceback.format_exc()}")

                batch_end_time = datetime.now(timezone(timedelta(hours=8)))
                batch_duration = (batch_end_time - batch_start_time).total_seconds()
                logger.info(f"[Model {self.model_id}] [卖出服务] 所有批次处理完成: "
                            f"完成批次数={completed_batches}/{len(batches)}, "
                            f"总耗时={batch_duration:.2f}秒, "
                            f"平均每批耗时={batch_duration/len(batches):.2f}秒")
                
                # 如果有任何批次产生了实际的卖出决策（close_position/stop_loss/take_profit），添加到对话提示中
                # hold 操作不算作实际执行的操作，不添加到对话提示中
                if has_sell_decision and 'sell' not in conversation_prompts:
                    conversation_prompts.append('sell')
                    logger.info(f"[Model {self.model_id}] [卖出服务] [阶段2] 检测到实际卖出决策（close_position/stop_loss/take_profit），已添加到对话提示")
                else:
                    logger.info(f"[Model {self.model_id}] [卖出服务] [阶段2] 所有批次卖出决策被跳过、无有效决策或仅有hold操作（无实际执行）")
            else:
                logger.info(f"[Model {self.model_id}] [卖出服务] [阶段2] 无持仓，跳过卖出决策处理")
            
            logger.info(f"[Model {self.model_id}] [卖出服务] [阶段2] 卖出/平仓决策处理完成")

            # ========== 阶段3: 记录账户价值快照（仅在有实际交易时） ==========
            if self._has_actual_trades(executions):
                logger.info(f"[Model {self.model_id}] [卖出服务] [阶段3] 检测到实际交易，开始记录账户价值快照")
                self._record_account_snapshot(current_prices)
                logger.info(f"[Model {self.model_id}] [卖出服务] [阶段3] 账户价值快照已记录到数据库")
            else:
                logger.debug(f"[Model {self.model_id}] [卖出服务] [阶段3] 无实际交易，跳过账户价值快照记录")
            
            # ========== 同步model_futures表数据 ==========
            logger.debug(f"[Model {self.model_id}] [卖出服务] [阶段4] 同步model_futures表数据")
            self._sync_model_futures()
            
            # ========== 交易周期完成 ==========
            cycle_end_time = datetime.now(timezone(timedelta(hours=8)))
            cycle_duration = (cycle_end_time - cycle_start_time).total_seconds()
            logger.info(f"[Model {self.model_id}] [卖出服务] ========== 卖出决策周期执行完成 ==========")
            logger.info(f"[Model {self.model_id}] [卖出服务] 执行统计: "
                        f"总耗时={cycle_duration:.2f}秒, "
                        f"执行操作数={len(executions)}, "
                        f"对话类型={conversation_prompts}")
            
            # 获取最终持仓信息
            updated_portfolio = self.db.get_portfolio(self.model_id, current_prices)
            return {
                'success': True,
                'executions': executions,
                'portfolio': updated_portfolio,
                'conversations': conversation_prompts
            }

        except Exception as e:
            cycle_end_time = datetime.now(timezone(timedelta(hours=8)))
            cycle_duration = (cycle_end_time - cycle_start_time).total_seconds()
            logger.error(f"[Model {self.model_id}] [卖出服务] ========== 卖出决策周期执行失败 ==========")
            logger.error(f"[Model {self.model_id}] [卖出服务] 错误信息: {e}")
            logger.error(f"[Model {self.model_id}] [卖出服务] 执行耗时: {cycle_duration:.2f}秒")
            import traceback
            logger.error(f"[Model {self.model_id}] [卖出服务] 错误堆栈:\n{traceback.format_exc()}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def execute_buy_cycle(self) -> Dict:
        """
        执行买入决策周期
        
        优化后的流程：
        1. 初始化数据准备：获取模型配置、持仓信息、账户信息、买入提示词模板等
        2. 候选symbol选择与市场状态构建：
           - 根据模型的symbol_source字段获取候选symbol来源（leaderboard或future）
           - 过滤已持仓的symbol（可配置）
           - 基于候选symbol列表获取市场状态信息（价格、成交量、K线指标）
        3. 买入决策处理：调用AI模型获取买入决策并执行
        4. 记录账户价值快照
        
        主要优化：
        - 合并了market_snapshot和market_state，统一使用market_state
        - 根据symbol_source统一获取候选symbol，避免重复筛选
        - 基于候选symbol列表统一获取市场数据，逻辑更清晰
        
        返回：
            Dict: {
                'success': bool,  # 是否成功
                'executions': List,  # 执行结果列表
                'portfolio': Dict,  # 最终持仓信息
                'conversations': List,  # 对话类型列表 ['buy']
                'error': str  # 错误信息（如果失败）
            }
        """
        logger.info(f"[Model {self.model_id}] [买入服务] ========== 开始执行买入决策周期 ==========")
        cycle_start_time = datetime.now(timezone(timedelta(hours=8)))
        
        try:
            # 检查模型是否存在
            model = self.db.get_model(self.model_id)
            if not model:
                logger.warning(f"[Model {self.model_id}] [买入服务] 模型不存在，跳过买入决策周期")
                return {
                    'success': False,
                    'executions': [],
                    'portfolio': {},
                    'conversations': [],
                    'error': f"Model {self.model_id} not found"
                }
            # ========== 阶段1: 初始化数据准备 ==========
            logger.info(f"[Model {self.model_id}] [买入服务] [阶段1] 开始初始化数据准备")
            
            # 获取模型配置（包含symbol_source）
            symbol_source = model.get('symbol_source', 'leaderboard')
            logger.info(f"[Model {self.model_id}] [买入服务] [阶段1.1] 模型symbol_source配置: {symbol_source}")
            
            # 获取当前持仓信息（先使用空价格映射，后续会更新）
            portfolio = self.db.get_portfolio(self.model_id, {})
            logger.info(f"[Model {self.model_id}] [买入服务] [阶段1.2] 持仓信息获取完成: "
                        f"总价值=${portfolio.get('total_value', 0):.2f}, "
                        f"现金=${portfolio.get('cash', 0):.2f}, "
                        f"持仓数={len(portfolio.get('positions', []) or [])}")
            
            # 构建账户信息（用于AI决策）
            account_info = self._build_account_info(portfolio)
            logger.info(f"[Model {self.model_id}] [买入服务] [阶段1.3] 账户信息构建完成: "
                        f"初始资金=${account_info.get('initial_capital', 0):.2f}, "
                        f"总收益率={account_info.get('total_return', 0):.2f}%")
            
            # 获取提示词模板（仅买入约束）
            prompt_templates = self._get_prompt_templates()
            logger.info(f"[Model {self.model_id}] [买入服务] [阶段1.4] 买入提示词模板获取完成")
            
            # 初始化执行结果和对话记录
            executions = []
            conversation_prompts = []
            logger.info(f"[Model {self.model_id}] [买入服务] [阶段1] 初始化完成")

            # ========== 阶段2: 买入决策处理（分批多线程） ==========
            logger.info(f"[Model {self.model_id}] [买入服务] [阶段2] 开始处理买入决策")
            
            # 步骤1: 根据symbol_source获取候选symbol并构建市场状态（仅获取价格，不获取技术指标，指标将在批次处理时按需获取）
            logger.info(f"[Model {self.model_id}] [买入服务] [阶段2.1] 根据symbol_source获取候选symbol并构建市场状态（仅价格）...")
            buy_candidates, market_state = self._select_buy_candidates(portfolio, symbol_source, include_indicators=False)
            logger.info(f"[Model {self.model_id}] [买入服务] [阶段2.1] 候选symbol选择完成: "
                        f"候选数量={len(buy_candidates)}, "
                        f"市场状态symbol数={len(market_state)}")
            
            if buy_candidates:
                # 记录前几个候选的详细信息
                for idx, candidate in enumerate(buy_candidates[:5]):
                    symbol = candidate.get('symbol', 'N/A')
                    market_info = market_state.get(symbol.upper() if symbol != 'N/A' else symbol, {})
                    price = market_info.get('price', candidate.get('price', 0))
                    change = market_info.get('change_24h', candidate.get('change_percent', 0))
                    logger.debug(f"[Model {self.model_id}] [买入服务] [阶段2.1.{idx+1}] 候选: "
                                f"{symbol}, "
                                f"价格=${price:.4f}, "
                                f"涨跌幅={change:.2f}%")
                
                # 提取当前价格映射（用于计算持仓价值和后续处理）
                current_prices = self._extract_price_map(market_state)
                logger.debug(f"[Model {self.model_id}] [买入服务] [阶段2.2] 价格映射提取完成, 价格数量: {len(current_prices)}")
                
                # 更新持仓信息（使用最新价格）
                portfolio = self.db.get_portfolio(self.model_id, current_prices)
                logger.debug(f"[Model {self.model_id}] [买入服务] [阶段2.3] 持仓信息已更新: "
                            f"总价值=${portfolio.get('total_value', 0):.2f}, "
                            f"现金=${portfolio.get('cash', 0):.2f}")
                
                # 构建约束条件（用于AI决策）
                # 从数据库获取最新的 max_positions，确保使用最新配置
                try:
                    model = self.db.get_model(self.model_id)
                    current_max_positions = model.get('max_positions', self.max_positions) if model else self.max_positions
                    # 更新实例变量，供后续使用
                    self.max_positions = current_max_positions
                except Exception as e:
                    logger.warning(f"[Model {self.model_id}] [买入服务] Failed to get max_positions from database, using cached value: {e}")
                    current_max_positions = self.max_positions
                
                constraints = {
                    'max_positions': current_max_positions,
                    'occupied': len(portfolio.get('positions', []) or []),
                    'available_cash': portfolio.get('cash', 0)
                }
                logger.info(f"[Model {self.model_id}] [买入服务] [阶段2.4] 约束条件构建完成: "
                            f"最大持仓数={constraints['max_positions']}, "
                            f"已占用={constraints['occupied']}, "
                            f"可用现金=${constraints['available_cash']:.2f}")
                
                # 分批处理买入决策（多线程并发，每批立即执行）
                logger.info(f"[Model {self.model_id}] [买入服务] [阶段2.5] 开始分批处理买入决策（多线程）......")
                self._make_batch_buy_decisions(
                    buy_candidates,
                    portfolio,
                    account_info,
                    constraints,
                    prompt_templates['buy'],
                    market_state,
                    executions,
                    conversation_prompts,
                    current_prices,
                    symbol_source
                )
                logger.info(f"[Model {self.model_id}] [买入服务] [阶段2.5] 分批买入决策处理完成")
            else:
                logger.info(f"[Model {self.model_id}] [买入服务] [阶段2] 无买入候选，跳过买入决策处理")
                # 即使没有候选，也需要更新current_prices用于后续记录账户价值
                current_prices = {}
            
            logger.info(f"[Model {self.model_id}] [买入服务] [阶段2] 买入决策处理完成")

            # ========== 阶段3: 记录账户价值快照（仅在有实际交易时） ==========
            if self._has_actual_trades(executions):
                logger.info(f"[Model {self.model_id}] [买入服务] [阶段3] 检测到实际交易，开始记录账户价值快照")
                self._record_account_snapshot(current_prices)
                logger.info(f"[Model {self.model_id}] [买入服务] [阶段3] 账户价值快照已记录到数据库")
            else:
                logger.debug(f"[Model {self.model_id}] [买入服务] [阶段3] 无实际交易，跳过账户价值快照记录")
            
            # ========== 同步model_futures表数据 ==========
            logger.info(f"[Model {self.model_id}] [买入服务] [阶段4] 同步model_futures表数据")
            self._sync_model_futures()
            
            # ========== 交易周期完成 ==========
            cycle_end_time = datetime.now(timezone(timedelta(hours=8)))
            cycle_duration = (cycle_end_time - cycle_start_time).total_seconds()
            logger.info(f"[Model {self.model_id}] [买入服务] ========== 买入决策周期执行完成 ==========")
            logger.info(f"[Model {self.model_id}] [买入服务] 执行统计: "
                        f"总耗时={cycle_duration:.2f}秒, "
                        f"执行操作数={len(executions)}, "
                        f"对话类型={conversation_prompts}")
            
            # 获取最终持仓信息
            updated_portfolio = self.db.get_portfolio(self.model_id, current_prices)
            return {
                'success': True,
                'executions': executions,
                'portfolio': updated_portfolio,
                'conversations': conversation_prompts
            }

        except Exception as e:
            cycle_end_time = datetime.now(timezone(timedelta(hours=8)))
            cycle_duration = (cycle_end_time - cycle_start_time).total_seconds()
            logger.error(f"[Model {self.model_id}] [买入服务] ========== 买入决策周期执行失败 ==========")
            logger.error(f"[Model {self.model_id}] [买入服务] 错误信息: {e}")
            logger.error(f"[Model {self.model_id}] [买入服务] 执行耗时: {cycle_duration:.2f}秒")
            import traceback
            logger.error(f"[Model {self.model_id}] [买入服务] 错误堆栈:\n{traceback.format_exc()}")
            return {
                'success': False,
                'error': str(e)
            }
            
    # ============ 服务线程管理方法 ============
    # 管理买入和卖出服务的后台线程，实现周期性自动交易
    
    def _run_trading_service(self, service_name: str, cycle_method, cycle_interval: int):
        """
        运行交易服务的后台循环线程（通用方法）
        
        此方法在独立线程中运行，按照指定周期执行交易决策。
        当running标志为False时，循环退出。
        
        Args:
            service_name: 服务名称（用于日志），如 '买入服务' 或 '卖出服务'
            cycle_method: 周期执行的方法，如 self.execute_buy_cycle
            cycle_interval: 执行周期间隔（秒）
        """
        logger.info(f"[Model {self.model_id}] [{service_name}] 启动，执行周期: {cycle_interval}秒")
        import time
        import traceback
        while self.running:
            try:
                cycle_method()
            except Exception as e:
                logger.error(f"[Model {self.model_id}] [{service_name}] 循环执行出错: {e}")
                logger.error(f"[Model {self.model_id}] [{service_name}] 错误堆栈:\n{traceback.format_exc()}")
            
            # 等待下一个周期
            if self.running:
                logger.debug(f"[Model {self.model_id}] [{service_name}] 等待下一个周期，{cycle_interval}秒后继续")
                time.sleep(cycle_interval)
        logger.info(f"[Model {self.model_id}] [{service_name}] 已停止")
    
    def _run_buy_service(self):
        """运行买入服务的后台循环线程"""
        self._run_trading_service('买入服务', self.execute_buy_cycle, self.buy_cycle_interval)
        
    def _run_sell_service(self):
        """运行卖出服务的后台循环线程"""
        self._run_trading_service('卖出服务', self.execute_sell_cycle, self.sell_cycle_interval)
    
    def execute_trading_cycle(self):
        """
        执行完整的交易周期（主入口方法）
        
        此方法是交易引擎的主入口，被backend/app.py调用：
        - 自动交易循环：trading_loop() -> execute_trading_cycle()
        - 手动执行：/api/models/<id>/execute -> execute_trading_cycle()
        
        流程：
        1. 停止已有的服务线程（如果存在）
        2. 启动买入和卖出两个独立的服务线程
        3. 立即执行一次完整的买入和卖出周期（兼容原有调用方式）
        
        两个服务线程：
        - 买入服务：使用买入prompt配置，在buy_cycle_interval周期中执行
        - 卖出服务：使用卖出prompt配置，在sell_cycle_interval周期中执行
        
        返回：
            Dict: {
                'success': bool,  # 是否成功
                'executions': List,  # 执行结果列表
                'portfolio': Dict,  # 最终持仓信息
                'conversations': List,  # 对话类型列表 ['sell', 'buy']
                'message': str,  # 状态消息
                'error': str  # 错误信息（如果有）
            }
        """
        # 停止已有的服务
        self.stop_trading_services()
        
        # 启动新的服务
        self.running = True
        
        # 创建并启动买入和卖出服务线程
        self.buy_thread = threading.Thread(target=self._run_buy_service, daemon=True)
        self.sell_thread = threading.Thread(target=self._run_sell_service, daemon=True)
        self.buy_thread.start()
        self.sell_thread.start()
        
        logger.info(f"[Model {self.model_id}] 交易服务已启动: "
                   f"买入周期={self.buy_cycle_interval}秒, "
                   f"卖出周期={self.sell_cycle_interval}秒")
        
        # 立即执行一次卖出和买入周期，以兼容原有调用方式
        try:
            # 先执行卖出/平仓决策
            sell_result = self.execute_sell_cycle()
            logger.debug(f"[Model {self.model_id}] 立即执行卖出周期完成")
            
            # 再执行买入决策
            buy_result = self.execute_buy_cycle()
            logger.debug(f"[Model {self.model_id}] 立即执行买入周期完成")
            
            # 合并结果
            executions = []
            executions.extend(sell_result.get('executions', []))
            executions.extend(buy_result.get('executions', []))
            
            success = sell_result.get('success', False) and buy_result.get('success', False)
            
            return {
                'success': success,
                'executions': executions,
                'portfolio': buy_result.get('portfolio', sell_result.get('portfolio', {})),
                'conversations': ['sell', 'buy'],
                'message': f'交易服务已启动，买入周期{self.buy_cycle_interval}秒，卖出周期{self.sell_cycle_interval}秒',
                'error': sell_result.get('error') or buy_result.get('error') or None
            }
        except Exception as e:
            logger.error(f"[Model {self.model_id}] 立即执行交易周期失败: {e}")
            return {
                'success': True,  # 服务已启动，所以整体仍返回成功
                'executions': [],
                'conversations': [],
                'message': f'交易服务已启动，但立即执行交易周期失败: {str(e)}',
                'error': str(e)
            }
    
    def stop_trading_services(self):
        """
        停止买入和卖出交易服务线程
        
        此方法会：
        1. 设置running标志为False，通知服务线程退出
        2. 等待服务线程完成当前周期后退出
        3. 清理线程资源
        """
        logger.info(f"[Model {self.model_id}] 正在停止交易服务...")
        self.running = False
        
        # 等待线程结束
        if self.buy_thread and self.buy_thread.is_alive():
            self.buy_thread.join(timeout=5)
        if self.sell_thread and self.sell_thread.is_alive():
            self.sell_thread.join(timeout=5)
        
        self.buy_thread = None
        self.sell_thread = None
        logger.info(f"[Model {self.model_id}] 交易服务已停止")
        
        return {
            'success': True,
            'message': '交易服务已停止'
        }

    # ============ 工具方法：公共逻辑提取 ============
    
    def _check_model_exists(self) -> Optional[Dict]:
        """
        检查模型是否存在
        
        Returns:
            模型字典，如果不存在则返回None
        """
        try:
            model = self.db.get_model(self.model_id)
            if not model:
                logger.warning(f"[Model {self.model_id}] 模型不存在")
            return model
        except Exception as e:
            logger.error(f"[Model {self.model_id}] 检查模型失败: {e}")
            return None
    
    def _has_actual_trades(self, executions: List[Dict]) -> bool:
        """
        检查executions列表中是否有实际交易记录
        
        实际交易的定义：
        1. 没有error字段
        2. signal不是'hold'
        3. signal是有效的交易信号（buy_to_enter, sell_to_enter, close_position, stop_loss, take_profit）
        
        Args:
            executions: 执行结果列表
            
        Returns:
            bool: 如果有实际交易返回True，否则返回False
        """
        if not executions:
            return False
        
        valid_signals = {'buy_to_enter', 'sell_to_enter', 'close_position', 'stop_loss', 'take_profit'}
        
        for result in executions:
            # 跳过有错误的执行结果
            if result.get('error'):
                continue
            
            # 检查是否有有效的signal
            signal = result.get('signal', '').lower()
            if signal in valid_signals:
                logger.debug(f"[Model {self.model_id}] 检测到实际交易: signal={signal}, symbol={result.get('symbol', 'N/A')}")
                return True
        
        return False
    
    def _record_account_snapshot(self, current_prices: Dict) -> None:
        """
        记录账户价值快照（公共方法）
        
        Args:
            current_prices: 当前价格映射
        """
        updated_portfolio = self.db.get_portfolio(self.model_id, current_prices)
        balance = updated_portfolio.get('total_value', 0)
        available_balance = updated_portfolio.get('cash', 0)
        cross_wallet_balance = updated_portfolio.get('positions_value', 0)
        
        logger.info(f"[Model {self.model_id}] 账户价值: "
                   f"总余额(balance)=${balance:.2f}, "
                   f"可用余额(available_balance)=${available_balance:.2f}, "
                   f"全仓余额(cross_wallet_balance)=${cross_wallet_balance:.2f}")
        
        model = self.db.get_model(self.model_id)
        account_alias = model.get('account_alias', '') if model else ''
        
        self.db.record_account_value(
            self.model_id,
            balance=balance,
            available_balance=available_balance,
            cross_wallet_balance=cross_wallet_balance,
            account_alias=account_alias
        )
    
    def _sync_model_futures(self) -> None:
        """同步model_futures表数据"""
        sync_success = self.db.sync_model_futures_from_portfolio(self.model_id)
        if sync_success:
            logger.debug(f"[Model {self.model_id}] model_futures表同步成功")
        else:
            logger.debug(f"[Model {self.model_id}] model_futures表同步失败，但不影响交易流程")
    
    def _find_position(self, portfolio: Dict, symbol: str) -> Optional[Dict]:
        """
        查找持仓信息（公共方法）
        
        Args:
            portfolio: 持仓组合信息
            symbol: 交易对符号
            
        Returns:
            持仓信息字典，如果不存在则返回None
        """
        positions = portfolio.get('positions', []) or []
        for pos in positions:
            if pos.get('symbol') == symbol:
                return pos
        return None
    
    def _get_side_for_trade(self, position_side: str) -> str:
        """
        根据持仓方向确定交易方向（公共方法）
        
        Args:
            position_side: 持仓方向 ('LONG' 或 'SHORT')
            
        Returns:
            交易方向 ('SELL' 或 'BUY')
        """
        return 'SELL' if position_side == 'LONG' else 'BUY'
    
    def _get_trade_context(self) -> tuple[str, str]:
        """
        获取交易上下文信息（model_uuid和trade_id）
        
        Returns:
            (model_uuid, trade_id) 元组
        """
        model_mapping = self.db._get_model_id_mapping()
        model_uuid = model_mapping.get(self.model_id)
        trade_id = self.db._generate_id()
        return model_uuid, trade_id
    
    def _get_conversation_id(self) -> Optional[str]:
        """
        获取当前的conversation_id（线程安全）
        
        Returns:
            conversation_id字符串或None
        """
        with self.current_conversation_id_lock:
            return self.current_conversation_id
    
    def _handle_sdk_client_error(self, symbol: str, operation: str) -> tuple[bool, Optional[str]]:
        """
        处理SDK客户端创建失败的情况（公共方法）
        
        Args:
            symbol: 交易对符号
            operation: 操作名称（用于日志）
            
        Returns:
            (sdk_call_skipped, sdk_skip_reason) 元组
        """
        try:
            model = self.db.get_model(self.model_id)
            if not model:
                reason = "Model not found in database"
            else:
                api_key = model.get('api_key', '')
                api_secret = model.get('api_secret', '')
                if not api_key or not api_key.strip():
                    reason = "API key is empty or not configured in model table"
                elif not api_secret or not api_secret.strip():
                    reason = "API secret is empty or not configured in model table"
                else:
                    reason = "Failed to create Binance order client (unknown reason)"
        except Exception as check_err:
            reason = f"Failed to check model configuration: {check_err}"
        
        logger.error(f"@API@ [Model {self.model_id}] [{operation}] === 无法创建Binance订单客户端，跳过SDK调用 ==="
                   f" | symbol={symbol} | reason={reason} | "
                   f"⚠️ 警告：交易记录将保存到数据库，但实际交易未执行！请检查model表中的api_key和api_secret配置")
        return True, reason
    
    def _log_trade_record(self, signal: str, symbol: str, position_side: str, 
                         sdk_call_skipped: bool, sdk_skip_reason: Optional[str] = None) -> None:
        """
        记录交易日志（公共方法）
        
        Args:
            signal: 交易信号（如 'buy_to_enter', 'close_position'）
            symbol: 交易对符号
            position_side: 持仓方向
            sdk_call_skipped: SDK调用是否被跳过
            sdk_skip_reason: SDK跳过原因（可选）
        """
        if sdk_call_skipped:
            logger.warning(f"TRADE: ⚠️ SDK调用被跳过，但交易记录仍将保存到数据库 | symbol={symbol} | reason={sdk_skip_reason}")
        else:
            logger.info(f"TRADE: RECORDED - Model {self.model_id} {signal.upper()} {symbol}")
    
    # ============ Binance客户端管理方法 ============
    # 管理Binance订单客户端的创建，确保使用最新的API凭证
    
    def _create_binance_order_client(self) -> Optional[BinanceFuturesOrderClient]:
        """
        创建新的Binance期货订单客户端实例
        
        【重要说明】
        每次调用都创建一个新的BinanceFuturesOrderClient实例，使用model表中的api_key和api_secret进行初始化。
        这样确保每次交易都使用最新的凭证，避免凭证过期或变更导致的问题。
        
        【初始化流程】
        1. 从model表获取api_key和api_secret（每次都重新获取，确保使用最新值）
        2. 验证API密钥是否存在且不为空（严格验证）
        3. 使用API密钥创建新的BinanceFuturesOrderClient实例
        4. 如果创建失败，返回None，交易操作将跳过SDK调用（仅记录到数据库）
        
        【使用场景】
        - _execute_buy: 调用market_trade（市场价格交易）
        - _execute_close: 调用close_position_trade（平仓）
        - _execute_stop_loss: 调用stop_loss_trade（止损）
        - _execute_take_profit: 调用take_profit_trade（止盈）
        
        Returns:
            BinanceFuturesOrderClient实例，如果创建失败则返回None
        
        Note:
            如果返回None，交易操作仍会记录到数据库，但不会调用Binance SDK
        """
        try:
            # 【步骤1】从model表获取API密钥（每次都重新获取，确保使用最新值）
            model = self.db.get_model(self.model_id)
            if not model:
                logger.error(f"[Model {self.model_id}] Model not found, cannot create Binance order client")
                return None
            
            api_key = model.get('api_key', '')
            api_secret = model.get('api_secret', '')
            
            # 【步骤2】验证API密钥是否存在且不为空（严格验证）
            if not api_key or not api_key.strip():
                logger.error(f"[Model {self.model_id}] API key is empty or not configured in model table")
                logger.error(f"[Model {self.model_id}] SDK calls will be skipped, only database records will be created")
                return None
            
            if not api_secret or not api_secret.strip():
                logger.error(f"[Model {self.model_id}] API secret is empty or not configured in model table")
                logger.error(f"[Model {self.model_id}] SDK calls will be skipped, only database records will be created")
                return None
            
            # 【步骤3】使用model的API密钥创建新的Binance订单客户端实例
            # 每次调用都创建新实例，确保使用最新的凭证
            testnet = getattr(app_config, 'BINANCE_TESTNET', False)
            client = BinanceFuturesOrderClient(
                api_key=api_key.strip(),
                api_secret=api_secret.strip(),
                quote_asset='USDT',
                testnet=testnet
            )
            logger.info(f"[Model {self.model_id}] Created new Binance order client instance with model's API credentials")
            logger.info(f"[Model {self.model_id}] API key: {api_key[:8]}... (truncated for security)")
            return client
        except Exception as e:
            logger.error(f"[Model {self.model_id}] Failed to create Binance order client: {e}", exc_info=True)
            logger.error(f"[Model {self.model_id}] SDK calls will be skipped, only database records will be created")
            return None

    # ============ 市场数据获取方法 ============
    # 提供市场数据获取、处理和技术指标计算功能
    
    def _get_held_symbols(self) -> List[str]:
        """
        获取模型当前持仓的期货合约symbol列表（去重）
        
        从portfolios表中通过关联model_id获取当前有持仓的symbol（position_amt != 0），
        用于卖出服务获取市场状态。
        
        Returns:
            List[str]: 当前持仓的合约symbol列表（如 ['BTC', 'ETH']）
        """
        symbols = self.db.get_model_held_symbols(self.model_id)
        logger.debug(f"[Model {self.model_id}] Retrieved {len(symbols)} held symbols from portfolios table")
        return symbols
    
    def _get_market_state(self, include_indicators: bool = True) -> Dict:
        """
        获取当前市场状态（价格，可选技术指标）
        
        此方法用于AI交易决策（卖出服务），使用实时价格数据，不使用任何缓存。
        只获取当前有持仓的symbol的市场状态，确保AI决策基于最新市场数据。
        
        Args:
            include_indicators: 是否获取技术指标，默认True（向后兼容）
                              False时只获取价格信息，不获取指标（用于优化性能）
        
        Returns:
            Dict: 市场状态字典，格式为 {symbol: {价格信息, indicators: {...}}}
        """
        market_state = {}
        symbols = self._get_held_symbols()
        
        # 确保所有symbol都以USDT结尾，防止重复添加
        formatted_symbols = []
        symbol_mapping = {}  # formatted -> original
        for symbol in symbols:
            symbol_upper = symbol.upper()
            if not symbol_upper.endswith('USDT'):
                formatted_symbol = f"{symbol_upper}USDT"
            else:
                formatted_symbol = symbol_upper
            formatted_symbols.append(formatted_symbol)
            symbol_mapping[formatted_symbol] = symbol
        
        # 使用 get_current_prices 从API获取实时价格数据
        prices = self.market_fetcher.get_current_prices(formatted_symbols)

        for original_symbol in symbols:
            # 尝试用原始symbol和格式化后的symbol查询价格
            price_info = prices.get(original_symbol) or prices.get(symbol_mapping.get(original_symbol.upper(), original_symbol.upper()))
            if price_info:
                market_state[original_symbol] = price_info.copy()
                # 根据参数决定是否获取技术指标
                if include_indicators:
                    # 使用新方法获取所有时间周期的技术指标（无缓存）
                    # 确保传入的symbol以USDT结尾
                    query_symbol = original_symbol.upper()
                    if not query_symbol.endswith('USDT'):
                        query_symbol = f"{query_symbol}USDT"
                    merged_data = self._merge_timeframe_data(query_symbol)
                    # 将合并后的数据格式调整为与原有格式兼容
                    if query_symbol in merged_data:
                        market_state[original_symbol]['indicators'] = {'timeframes': merged_data[query_symbol]}
                    else:
                        market_state[original_symbol]['indicators'] = {'timeframes': {}}
                # 如果 include_indicators=False，则不获取指标，只保留价格信息

        return market_state

    def _validate_symbol_market_data(
        self,
        symbol: str,
        market_state: Dict,
        query_symbol: str = None,
        error_context: str = ""
    ) -> tuple[bool, str]:
        """
        验证symbol的市场数据是否有效
        
        Args:
            symbol: 交易对符号（如 'BTC'）
            market_state: 市场状态字典
            query_symbol: 查询用的symbol（用于技术指标）
            error_context: 错误上下文信息（用于日志）
            
        Returns:
            tuple[bool, str]: (是否有效, 错误信息)
        """
        symbol_upper = symbol.upper()
        market_info = market_state.get(symbol_upper, {})
        
        # 检查价格数据
        price = market_info.get('price') or market_info.get('last_price', 0)
        if not price or price == 0:
            error_msg = f"价格数据无效: price={price}, symbol={symbol_upper}"
            if error_context:
                error_msg += f", context={error_context}"
            return False, error_msg
        
        # 检查技术指标数据
        indicators = market_info.get('indicators', {})
        timeframes = indicators.get('timeframes', {}) if isinstance(indicators, dict) else {}
        
        # 检查是否有至少一个时间周期的数据
        if not timeframes or len(timeframes) == 0:
            error_msg = f"技术指标数据为空: symbol={symbol_upper}, query_symbol={query_symbol or symbol_upper}"
            if error_context:
                error_msg += f", context={error_context}"
            return False, error_msg
        
        # 检查每个时间周期的数据是否有效
        valid_timeframes = []
        invalid_timeframes = []
        for timeframe, data in timeframes.items():
            if data and isinstance(data, dict):
                # 检查是否有K线数据
                klines = data.get('klines', [])
                if klines and len(klines) > 0:
                    valid_timeframes.append(timeframe)
                else:
                    invalid_timeframes.append(timeframe)
            else:
                invalid_timeframes.append(timeframe)
        
        if not valid_timeframes:
            error_msg = f"所有时间周期的技术指标数据无效: symbol={symbol_upper}, query_symbol={query_symbol or symbol_upper}, invalid_timeframes={invalid_timeframes}"
            if error_context:
                error_msg += f", context={error_context}"
            return False, error_msg
        
        return True, ""
    
    def _merge_timeframe_data(self, symbol: str) -> Dict:
        """
        合并7个时间周期的市场数据和技术指标
        
        Args:
            symbol: 交易对符号（如 'BTC' 或 'BTCUSDT'）
            
        Returns:
            Dict: 合并后的数据格式 {symbol: {1m: {get_market_data_1m返回格式}, 5m: {get_market_data_5m返回格式}, ...}}
        """
        # 确保symbol以USDT结尾，防止重复添加
        symbol_upper = symbol.upper()
        if not symbol_upper.endswith('USDT'):
            formatted_symbol = f"{symbol_upper}USDT"
        else:
            formatted_symbol = symbol_upper
        
        # 获取7个时间周期的数据
        timeframe_methods = {
            '1m': self.market_fetcher.get_market_data_1m,
            '5m': self.market_fetcher.get_market_data_5m,
            '15m': self.market_fetcher.get_market_data_15m,
            '1h': self.market_fetcher.get_market_data_1h,
            '4h': self.market_fetcher.get_market_data_4h,
            '1d': self.market_fetcher.get_market_data_1d,
            '1w': self.market_fetcher.get_market_data_1w
        }
        
        merged_data = {formatted_symbol: {}}
        errors = []
        
        for timeframe, method in timeframe_methods.items():
            try:
                data = method(formatted_symbol)  # 使用格式化后的symbol
                if data:
                    # 直接使用get_market_data_*方法返回的完整数据格式
                    merged_data[formatted_symbol][timeframe] = data
                else:
                    errors.append(f"{timeframe}: 返回数据为空")
            except Exception as e:
                error_msg = str(e)
                errors.append(f"{timeframe}: {error_msg}")
                logger.warning(f"[Model {self.model_id}] 获取 {formatted_symbol} {timeframe} 数据失败: {e}")
                continue
        
        # 如果所有时间周期都失败，记录错误
        if not merged_data[formatted_symbol] and errors:
            logger.warning(f"[Model {self.model_id}] 获取 {formatted_symbol} 所有时间周期数据失败，错误详情: {errors}")
        
        return merged_data
        
    def _extract_price_map(self, market_state: Dict) -> Dict[str, float]:
        """
        从市场状态中提取价格映射
        
        Args:
            market_state: 市场状态字典，包含各交易对的价格和技术指标
        
        Returns:
            Dict[str, float]: 价格映射，key为交易对符号，value为价格
        """
        prices = {}
        for symbol, payload in (market_state or {}).items():
            price = payload.get('price') if isinstance(payload, dict) else None
            if price is not None:
                prices[symbol] = price
        return prices

    # ============ 账户信息管理方法 ============
    # 构建和管理账户信息，用于AI决策
    
    def _build_account_info(self, portfolio: Dict) -> Dict:
        """
        构建账户信息用于AI决策
        
        根据model的is_virtual值判断数据源：
        - 如果是virtual (True)：从account_values表获取最新记录
        - 如果不是virtual (False)：从account_asset表通过account_alias获取数据
        
        字段映射：
        - total_wallet_balance -> balance
        - total_cross_wallet_balance -> cross_wallet_balance
        - available_balance -> available_balance
        - total_cross_un_pnl -> cross_un_pnl
        """
        model = self.db.get_model(self.model_id)
        if not model:
            logger.error(f"[Model {self.model_id}] Model not found when building account info")
            return {
                'current_time': datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S'),
                'total_return': 0.0,
                'initial_capital': 0.0,
                'balance': 0.0,
                'available_balance': 0.0,
                'cross_wallet_balance': 0.0,
                'cross_un_pnl': 0.0
            }
        
        initial_capital = model.get('initial_capital', 0)
        is_virtual = model.get('is_virtual', False)
        account_alias = model.get('account_alias', '')
        
        # 根据is_virtual判断数据源
        if is_virtual:
            # 从account_values表获取最新记录
            account_data = self.db.get_latest_account_value(self.model_id)
            if account_data:
                balance = account_data.get('balance', 0.0)
                available_balance = account_data.get('available_balance', 0.0)
                cross_wallet_balance = account_data.get('cross_wallet_balance', 0.0)
                cross_un_pnl = account_data.get('cross_un_pnl', 0.0)
            else:
                # 如果没有记录，使用portfolio数据作为fallback
                balance = portfolio.get('total_value', 0)
                available_balance = portfolio.get('cash', 0)
                cross_wallet_balance = portfolio.get('positions_value', 0)
                cross_un_pnl = 0.0
                logger.warning(f"[Model {self.model_id}] No account_values record found for virtual model, using portfolio data")
        else:
            # 从account_asset表通过account_alias获取数据
            if not account_alias:
                logger.warning(f"[Model {self.model_id}] account_alias is empty for non-virtual model, using portfolio data")
                balance = portfolio.get('total_value', 0)
                available_balance = portfolio.get('cash', 0)
                cross_wallet_balance = portfolio.get('positions_value', 0)
                cross_un_pnl = 0.0
            else:
                account_data = self.db.get_account_asset(account_alias)
                if account_data:
                    balance = account_data.get('balance', 0.0)
                    available_balance = account_data.get('available_balance', 0.0)
                    cross_wallet_balance = account_data.get('cross_wallet_balance', 0.0)
                    cross_un_pnl = account_data.get('cross_un_pnl', 0.0)
                else:
                    # 如果account_asset表中没有数据，使用portfolio数据作为fallback
                    balance = portfolio.get('total_value', 0)
                    available_balance = portfolio.get('cash', 0)
                    cross_wallet_balance = portfolio.get('positions_value', 0)
                    cross_un_pnl = 0.0
                    logger.warning(f"[Model {self.model_id}] No account_asset record found for account_alias={account_alias}, using portfolio data")
        
        # 计算总收益率
        total_return = ((balance - initial_capital) / initial_capital) * 100 if initial_capital > 0 else 0

        return {
            'current_time': datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S'),
            'total_return': total_return,
            'initial_capital': initial_capital,
            'balance': balance,
            'available_balance': available_balance,
            'cross_wallet_balance': cross_wallet_balance,
            'cross_un_pnl': cross_un_pnl
        }

    # ============ 提示词管理方法 ============
    # 获取和管理AI决策的提示词模板
    
    def _get_prompt_templates(self) -> Dict[str, str]:
        """
        获取买入和卖出决策的提示词模板
        
        Returns:
            Dict[str, str]: {
                'buy': str,  # 买入决策提示词（已拼接JSON输出要求结尾句）
                'sell': str  # 卖出决策提示词（已拼接JSON输出要求结尾句）
            }
        
        Note:
            - 如果模型没有自定义提示词，则使用默认提示词（DEFAULT_BUY_CONSTRAINTS, DEFAULT_SELL_CONSTRAINTS）
            - 从数据库获取的prompt不包含JSON输出要求结尾句，这里会自动拼接上PROMPT_JSON_OUTPUT_SUFFIX
            - 结尾句永远作为传入给AI Prompt策略的结尾输入
        """
        prompt_config = self.db.get_model_prompt(self.model_id) or {}
        buy_prompt = prompt_config.get('buy_prompt') or DEFAULT_BUY_CONSTRAINTS
        sell_prompt = prompt_config.get('sell_prompt') or DEFAULT_SELL_CONSTRAINTS
        
        # 拼接JSON输出要求结尾句（确保数据库中的prompt不包含结尾句，这里统一拼接）
        # 移除可能已存在的结尾句，避免重复
        def _remove_suffix_if_exists(text: str) -> str:
            """移除结尾句（如果存在）"""
            if not text:
                return text
            text_stripped = text.rstrip()
            suffix = PROMPT_JSON_OUTPUT_SUFFIX.strip()
            if text_stripped.endswith(suffix):
                return text_stripped[:-len(suffix)].rstrip()
            return text_stripped
        
        buy_prompt_clean = _remove_suffix_if_exists(buy_prompt)
        sell_prompt_clean = _remove_suffix_if_exists(sell_prompt)
        
        buy_prompt_final = buy_prompt_clean + "\n" + PROMPT_JSON_OUTPUT_SUFFIX
        sell_prompt_final = sell_prompt_clean + "\n" + PROMPT_JSON_OUTPUT_SUFFIX
        
        return {'buy': buy_prompt_final, 'sell': sell_prompt_final}

    def _record_ai_conversation(self, payload: Dict) -> Optional[str]:
        """
        记录AI对话到数据库
        
        Args:
            payload: AI决策返回的完整数据，包含：
                - prompt: 发送给AI的提示词
                - raw_response: AI的原始响应
                - cot_trace: 思维链追踪（如果有）
                - decisions: AI的决策结果（如果raw_response不是字符串）
                - tokens: token使用数量（如果有）
        
        Returns:
            conversation_id (str): 对话记录的ID（UUID字符串），如果失败则返回None
        
        Note:
            对话记录用于后续分析和审计，帮助理解AI的决策过程
        """
        prompt = payload.get('prompt')
        raw_response = payload.get('raw_response')
        cot_trace = payload.get('cot_trace') or ''
        tokens = payload.get('tokens', 0)  # 获取tokens数量，默认为0
        if not isinstance(raw_response, str):
            raw_response = json.dumps(payload.get('decisions', {}), ensure_ascii=False)
        conversation_id = self.db.add_conversation(
            self.model_id,
            user_prompt=prompt,
            ai_response=raw_response,
            cot_trace=cot_trace,
            tokens=tokens
        )
        # 保存 conversation_id 到实例变量（线程安全）
        if conversation_id:
            with self.current_conversation_id_lock:
                self.current_conversation_id = conversation_id
        return conversation_id

    # ============ 批量决策处理方法 ============
    # 使用多线程批量处理AI决策，提高执行效率
    
    def _make_batch_buy_decisions(
        self,
        candidates: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        constraints: Dict,
        constraints_text: str,
        market_state: Dict,
        executions: List,
        conversation_prompts: List,
        current_prices: Dict[str, float],
        symbol_source: str = 'leaderboard'
    ):
        """
        分批处理买入决策（支持多线程并发，按单元分组统一处理）
        
        流程：
        1. 从配置获取批次大小、批次间隔、分组大小、线程数
        2. 将候选列表分批
        3. 如果线程数>1：使用多线程并发执行，每N个批次（N=线程数）作为一个单元
        4. 如果线程数=1：串行执行，每N个批次（N=AI_BATCH_EXECUTION_GROUP_SIZE）作为一个单元
        5. 每个批次只获取AI决策，不立即执行
        6. 每个单元的所有批次完成后，统一处理这些批次的决策（插入数据库和调用SDK）
        7. 单元之间有间隔（AI_BATCH_EXECUTION_INTERVAL）
        8. 使用锁保证线程安全
        """
        if not candidates:
            logger.debug(f"[Model {self.model_id}] [分批买入] 无候选合约，跳过处理")
            return

        # 从配置获取批次大小、批次间隔、分组大小、线程数
        batch_size = getattr(app_config, 'AI_DECISION_SYMBOL_BATCH_SIZE', 1)
        batch_size = max(1, int(batch_size))
        batch_interval = getattr(app_config, 'AI_BATCH_EXECUTION_INTERVAL', 5)
        batch_interval = max(0, int(batch_interval))
        group_size = getattr(app_config, 'AI_BATCH_EXECUTION_GROUP_SIZE', 1)
        group_size = max(1, int(group_size))
        thread_count = getattr(app_config, 'BUY_DECISION_THREAD_COUNT', 1)
        thread_count = max(1, int(thread_count))
        
        # 确定单元大小：如果线程数>1，使用线程数作为单元大小；否则使用配置的group_size
        unit_size = thread_count if thread_count > 1 else group_size
        
        logger.info(f"[Model {self.model_id}] [分批买入] 配置参数: 批次大小={batch_size}, 批次间隔={batch_interval}秒, 线程数={thread_count}, 单元大小={unit_size}")

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

        logger.info(f"[Model {self.model_id}] 开始分批处理买入决策: 共 {len(candidates)} 个候选, 分为 {len(batches)} 批, 每批最多 {batch_size} 个, 线程数={thread_count}, 单元大小={unit_size}, 单元间隔={batch_interval}秒")

        # 创建线程安全锁（用于保护portfolio和executions的更新）
        portfolio_lock = threading.Lock()
        has_buy_decision = False
        batch_start_time = datetime.now(timezone(timedelta(hours=8)))
        
        # 如果线程数>1，使用多线程并发执行
        if thread_count > 1:
            logger.info(f"[Model {self.model_id}] [分批买入] 使用多线程并发执行，线程数={thread_count}, 单元大小={unit_size}")
            
            # 使用线程池并发处理各批次
            with ThreadPoolExecutor(max_workers=thread_count) as executor:
                # 按单元处理批次
                for unit_start in range(0, len(batches), unit_size):
                    unit_end = min(unit_start + unit_size, len(batches))
                    unit_batches = batches[unit_start:unit_end]
                    unit_batch_nums = list(range(unit_start + 1, unit_end + 1))
                    
                    logger.info(f"[Model {self.model_id}] [分批买入] 开始处理单元 {unit_start+1}-{unit_end} (共{len(unit_batches)}个批次)...")
                    
                    # 准备批次任务
                    futures = []
                    batch_data_list = []
                    
                    for idx, batch in enumerate(unit_batches):
                        batch_num = unit_start + idx + 1
                        batch_symbols = [c.get('symbol', 'N/A') for c in batch]
                        
                        # 为当前批次创建只包含对应symbol的market_state子集
                        batch_market_state = {}
                        for symbol in batch_symbols:
                            if symbol != 'N/A':
                                symbol_upper = symbol.upper()
                                if symbol_upper in market_state:
                                    batch_market_state[symbol_upper] = market_state[symbol_upper].copy()
                                    
                                    market_info = market_state[symbol_upper]
                                    symbol_source_for_batch = market_info.get('source', 'leaderboard')
                                    
                                    if symbol_source_for_batch == 'future':
                                        query_symbol = market_info.get('contract_symbol') or f"{symbol}USDT"
                                    else:
                                        query_symbol = symbol_upper
                                    
                                    try:
                                        logger.debug(f"[Model {self.model_id}] [分批买入] 批次 {batch_num} 正在获取 {symbol_upper} ({query_symbol}) 的技术指标...")
                                        merged_data = self._merge_timeframe_data(query_symbol)
                                        timeframes_data = merged_data.get(query_symbol, {}) if merged_data else {}
                                        
                                        if timeframes_data:
                                            batch_market_state[symbol_upper]['indicators'] = {'timeframes': timeframes_data}
                                        else:
                                            batch_market_state[symbol_upper]['indicators'] = {'timeframes': {}}
                                    except Exception as e:
                                        logger.error(f"[Model {self.model_id}] [分批买入] 批次 {batch_num} 获取 {symbol_upper} 技术指标失败: {e}")
                                        batch_market_state[symbol_upper]['indicators'] = {'timeframes': {}}
                        
                        # 提交批次任务到线程池
                        future = executor.submit(
                            self._process_batch_decision_only,
                            batch,
                            portfolio,
                            account_info,
                            constraints,
                            constraints_text,
                            batch_market_state,
                            symbol_source,
                            batch_num,
                            len(batches)
                        )
                        futures.append((future, batch_num, batch_market_state, batch))
                    
                    # 等待当前单元的所有批次完成
                    unit_decisions = []
                    for future, batch_num, batch_market_state, batch in futures:
                        try:
                            payload = future.result()
                            unit_decisions.append({
                                'batch_num': batch_num,
                                'payload': payload,
                                'batch_market_state': batch_market_state,
                                'batch_candidates': batch
                            })
                            
                            if not payload.get('skipped') and payload.get('decisions'):
                                has_buy_decision = True
                                logger.info(f"[Model {self.model_id}] [分批买入] 批次 {batch_num}/{len(batches)} AI决策完成: 决策数={len(payload.get('decisions') or {})}")
                            else:
                                logger.info(f"[Model {self.model_id}] [分批买入] 批次 {batch_num}/{len(batches)} 跳过或无决策")
                        except Exception as exc:
                            logger.error(f"[Model {self.model_id}] [分批买入] 批次 {batch_num} 处理异常: {exc}")
                            import traceback
                            logger.debug(f"[Model {self.model_id}] [分批买入] 异常堆栈:\n{traceback.format_exc()}")
                    
                    logger.info(f"[Model {self.model_id}] [分批买入] 单元 {unit_start+1}-{unit_end} 所有批次完成，开始统一处理决策（插入数据库和调用SDK）...")
                    
                    # 统一处理当前单元的决策
                    self._execute_batch_group_decisions(
                        unit_decisions,
                        portfolio,
                        account_info,
                        constraints,
                        current_prices,
                        portfolio_lock,
                        executions
                    )
                    
                    logger.info(f"[Model {self.model_id}] [分批买入] 单元 {unit_start+1}-{unit_end} 处理完成")
                    
                    # 如果不是最后一个单元，等待间隔时间
                    if unit_end < len(batches) and batch_interval > 0:
                        logger.debug(f"[Model {self.model_id}] [分批买入] 单元 {unit_start+1}-{unit_end} 完成，等待 {batch_interval} 秒后处理下一单元...")
                        time.sleep(batch_interval)
        else:
            # 线程数=1，串行执行
            logger.info(f"[Model {self.model_id}] [分批买入] 使用串行执行，单元大小={unit_size}")
            
            # 存储所有批次的决策结果（用于分组处理）
            all_batch_decisions = []
            
            # 串行执行各批次
            for batch_idx, batch in enumerate(batches):
                batch_num = batch_idx + 1
                batch_symbols = [c.get('symbol', 'N/A') for c in batch]
                
                logger.info(f"[Model {self.model_id}] [分批买入] 开始处理批次 {batch_num}/{len(batches)}: symbols={batch_symbols}")
                
                # 为当前批次创建只包含对应symbol的market_state子集
                batch_market_state = {}
                for symbol in batch_symbols:
                    if symbol != 'N/A':
                        symbol_upper = symbol.upper()
                        if symbol_upper in market_state:
                            batch_market_state[symbol_upper] = market_state[symbol_upper].copy()
                            
                            market_info = market_state[symbol_upper]
                            symbol_source_for_batch = market_info.get('source', 'leaderboard')
                            
                            if symbol_source_for_batch == 'future':
                                query_symbol = market_info.get('contract_symbol') or f"{symbol}USDT"
                            else:
                                query_symbol = symbol_upper
                            
                            try:
                                logger.debug(f"[Model {self.model_id}] [分批买入] 批次 {batch_num} 正在获取 {symbol_upper} ({query_symbol}) 的技术指标...")
                                merged_data = self._merge_timeframe_data(query_symbol)
                                timeframes_data = merged_data.get(query_symbol, {}) if merged_data else {}
                                
                                if timeframes_data:
                                    batch_market_state[symbol_upper]['indicators'] = {'timeframes': timeframes_data}
                                else:
                                    batch_market_state[symbol_upper]['indicators'] = {'timeframes': {}}
                            except Exception as e:
                                logger.error(f"[Model {self.model_id}] [分批买入] 批次 {batch_num} 获取 {symbol_upper} 技术指标失败: {e}")
                                batch_market_state[symbol_upper]['indicators'] = {'timeframes': {}}
                
                # 调用AI决策（不立即执行）
                try:
                    payload = self._process_batch_decision_only(
                        batch,
                        portfolio,
                        account_info,
                        constraints,
                        constraints_text,
                        batch_market_state,
                        symbol_source,
                        batch_num,
                        len(batches)
                    )
                    
                    # 存储决策结果
                    all_batch_decisions.append({
                        'batch_num': batch_num,
                        'payload': payload,
                        'batch_market_state': batch_market_state,
                        'batch_candidates': batch
                    })
                    
                    if not payload.get('skipped') and payload.get('decisions'):
                        has_buy_decision = True
                        logger.info(f"[Model {self.model_id}] [分批买入] 批次 {batch_num}/{len(batches)} AI决策完成: 决策数={len(payload.get('decisions') or {})}")
                    else:
                        logger.info(f"[Model {self.model_id}] [分批买入] 批次 {batch_num}/{len(batches)} 跳过或无决策")
                        
                except Exception as exc:
                    logger.error(f"[Model {self.model_id}] [分批买入] 批次 {batch_num} 处理异常: {exc}")
                    import traceback
                    logger.debug(f"[Model {self.model_id}] [分批买入] 异常堆栈:\n{traceback.format_exc()}")
                
                # 每N个批次完成后，统一处理这些批次的决策
                if batch_num % unit_size == 0 or batch_num == len(batches):
                    group_start = ((batch_num - 1) // unit_size) * unit_size
                    group_end = batch_num
                    group_decisions = all_batch_decisions[group_start:group_end]
                    
                    logger.info(f"[Model {self.model_id}] [分批买入] 批次组 {group_start+1}-{group_end} 完成，开始统一处理决策（插入数据库和调用SDK）...")
                    
                    # 统一处理这组批次的决策
                    self._execute_batch_group_decisions(
                        group_decisions,
                        portfolio,
                        account_info,
                        constraints,
                        current_prices,
                        portfolio_lock,
                        executions
                    )
                    
                    logger.info(f"[Model {self.model_id}] [分批买入] 批次组 {group_start+1}-{group_end} 处理完成")
                
                # 如果不是最后一个批次，等待间隔时间
                if batch_num < len(batches) and batch_interval > 0:
                    logger.debug(f"[Model {self.model_id}] [分批买入] 批次 {batch_num} 完成，等待 {batch_interval} 秒后处理下一批次...")
                    time.sleep(batch_interval)

        batch_end_time = datetime.now(timezone(timedelta(hours=8)))
        batch_duration = (batch_end_time - batch_start_time).total_seconds()
        logger.info(f"[Model {self.model_id}] [分批买入] 所有批次处理完成: "
                    f"完成批次数={len(batches)}, "
                    f"总耗时={batch_duration:.2f}秒, "
                    f"平均每批耗时={batch_duration/len(batches):.2f}秒")

        # 如果有任何批次产生了买入决策，添加到对话提示中
        if has_buy_decision and 'buy' not in conversation_prompts:
            conversation_prompts.append('buy')
            logger.debug(f"[Model {self.model_id}] [分批买入] 已添加'buy'到对话提示列表")
    
    def _process_batch_decision_only(
        self,
        batch_candidates: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        constraints: Dict,
        constraints_text: str,
        market_state: Dict,
        symbol_source: str,
        batch_num: int,
        total_batches: int
    ) -> Dict:
        """
        处理单个批次：只获取AI决策，不执行
        
        流程：
        1. 验证所有symbol的市场数据是否有效
        2. 如果数据无效，记录醒目的warning日志并跳过
        3. 调用AI模型获取买入决策
        4. 返回决策结果（不记录对话，不执行）
        """
        batch_start_time = datetime.now(timezone(timedelta(hours=8)))
        batch_symbols = [c.get('symbol', 'N/A') for c in batch_candidates]
        
        logger.debug(f"[Model {self.model_id}] [批次 {batch_num}/{total_batches}] "
                    f"开始获取AI决策，候选合约: {batch_symbols}")
        
        try:
            # ========== 步骤0: 验证所有symbol的市场数据 ==========
            logger.debug(f"[Model {self.model_id}] [批次 {batch_num}/{total_batches}] "
                        f"[步骤0] 验证symbol市场数据...")
            
            valid_candidates = []
            invalid_symbols = []
            
            for candidate in batch_candidates:
                symbol = candidate.get('symbol', '')
                if not symbol or symbol == 'N/A':
                    continue
                
                symbol_upper = symbol.upper()
                market_info = market_state.get(symbol_upper, {})
                symbol_source_for_batch = market_info.get('source', 'leaderboard')
                
                if symbol_source_for_batch == 'future':
                    query_symbol = market_info.get('contract_symbol') or f"{symbol}USDT"
                else:
                    query_symbol = symbol_upper
                
                # 验证数据
                is_valid, error_msg = self._validate_symbol_market_data(
                    symbol,
                    market_state,
                    query_symbol,
                    error_context=f"批次{batch_num}/{total_batches}"
                )
                
                if is_valid:
                    valid_candidates.append(candidate)
                else:
                    invalid_symbols.append((symbol, error_msg))
                    # 打印醒目的warning日志
                    logger.warning(
                        f"@@@ [Model {self.model_id}] [批次 {batch_num}/{total_batches}] "
                        f"@@@ SYMBOL数据验证失败，跳过AI决策询问: {symbol_upper} @@@\n"
                        f"@@@ 错误信息: {error_msg} @@@\n"
                        f"@@@ 查询symbol: {query_symbol}, 数据源: {symbol_source_for_batch} @@@"
                    )
            
            # 如果所有symbol都无效，返回跳过结果
            if not valid_candidates:
                logger.warning(
                    f"@@@ [Model {self.model_id}] [批次 {batch_num}/{total_batches}] "
                    f"@@@ 批次中所有symbol数据验证失败，跳过AI决策询问 @@@\n"
                    f"@@@ 无效symbol详情: {[f'{s}: {e}' for s, e in invalid_symbols]} @@@"
                )
                return {
                    'skipped': True,
                    'decisions': {},
                    'error': f'所有symbol数据验证失败: {len(invalid_symbols)}个symbol无效'
                }
            
            # 如果有部分symbol无效，记录警告但继续处理有效的symbol
            if invalid_symbols:
                logger.warning(
                    f"@@@ [Model {self.model_id}] [批次 {batch_num}/{total_batches}] "
                    f"@@@ 批次中部分symbol数据验证失败，将只处理有效symbol @@@\n"
                    f"@@@ 有效symbol: {[c.get('symbol') for c in valid_candidates]} @@@\n"
                    f"@@@ 无效symbol详情: {[f'{s}: {e}' for s, e in invalid_symbols]} @@@"
                )
            
            # ========== 步骤1: 调用AI模型获取买入决策 ==========
            logger.debug(f"[Model {self.model_id}] [批次 {batch_num}/{total_batches}] "
                        f"[步骤1] 调用AI模型获取买入决策... (有效symbol数: {len(valid_candidates)})")
            
            # 将market_state转换为market_snapshot格式（用于AI决策），只包含有效的symbol
            market_snapshot = []
            for candidate in valid_candidates:
                symbol = candidate.get('symbol', '').upper()
                if symbol in market_state:
                    state_info = market_state[symbol]
                    snapshot_entry = {
                        'symbol': symbol,
                        'contract_symbol': state_info.get('contract_symbol', f"{symbol}USDT"),
                        'price': state_info.get('price', 0),
                        'quote_volume': state_info.get('quote_volume', state_info.get('daily_volume', 0)),
                        'change_percent': state_info.get('change_24h', 0),
                        'timeframes': state_info.get('indicators', {}).get('timeframes', {})
                    }
                    market_snapshot.append(snapshot_entry)
            
            ai_call_start = datetime.now(timezone(timedelta(hours=8)))
            buy_payload = self.ai_trader.make_buy_decision(
                valid_candidates,  # 只传递有效的candidates
                portfolio,
                account_info,
                constraints,
                constraints_text=constraints_text,
                market_snapshot=market_snapshot if market_snapshot else None,
                symbol_source=symbol_source,
                model_id=self.model_id
            )
            ai_call_duration = (datetime.now(timezone(timedelta(hours=8))) - ai_call_start).total_seconds()
            
            is_skipped = buy_payload.get('skipped', False)
            has_prompt = bool(buy_payload.get('prompt'))
            decisions = buy_payload.get('decisions') or {}
            logger.debug(f"[Model {self.model_id}] [批次 {batch_num}/{total_batches}] "
                        f"[步骤1] AI调用完成: 耗时={ai_call_duration:.2f}秒, "
                        f"跳过={is_skipped}, 有提示词={has_prompt}, 决策数={len(decisions)}")
            
            batch_end_time = datetime.now(timezone(timedelta(hours=8)))
            batch_duration = (batch_end_time - batch_start_time).total_seconds()
            logger.debug(f"[Model {self.model_id}] [批次 {batch_num}/{total_batches}] "
                        f"AI决策获取完成: 总耗时={batch_duration:.2f}秒")
            
            return buy_payload
            
        except Exception as e:
            logger.error(f"[Model {self.model_id}] [批次 {batch_num}/{total_batches}] 获取AI决策失败: {e}")
            import traceback
            logger.debug(f"[Model {self.model_id}] [批次 {batch_num}/{total_batches}] 异常堆栈:\n{traceback.format_exc()}")
            return {'skipped': True, 'decisions': {}, 'error': str(e)}
    
    def _execute_batch_group_decisions(
        self,
        group_decisions: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        constraints: Dict,
        current_prices: Dict[str, float],
        portfolio_lock: threading.Lock,
        executions: List
    ):
        """
        统一处理一组批次的决策（插入数据库和调用SDK）
        
        流程：
        1. 合并所有批次的决策
        2. 记录所有批次的AI对话到数据库
        3. 获取锁并执行所有决策（线程安全）
        4. 更新portfolio和constraints
        """
        if not group_decisions:
            logger.debug(f"[Model {self.model_id}] [批次组处理] 无决策数据，跳过")
            return
        
        logger.info(f"[Model {self.model_id}] [批次组处理] 开始处理 {len(group_decisions)} 个批次的决策...")
        
        # 合并所有批次的决策和对话
        all_decisions = {}
        all_payloads = []
        all_market_states = {}
        
        for batch_data in group_decisions:
            payload = batch_data.get('payload', {})
            decisions = payload.get('decisions') or {}
            batch_market_state = batch_data.get('batch_market_state', {})
            batch_num = batch_data.get('batch_num', 0)
            
            # 合并决策
            for symbol, decision in decisions.items():
                if symbol not in all_decisions:
                    all_decisions[symbol] = decision
                    logger.debug(f"[Model {self.model_id}] [批次组处理] 批次 {batch_num} 决策: {symbol} -> {decision.get('signal')}")
            
            # 合并market_state
            all_market_states.update(batch_market_state)
            
            # 保存payload用于记录对话
            if not payload.get('skipped') and payload.get('prompt'):
                all_payloads.append(payload)
        
        if not all_decisions:
            logger.info(f"[Model {self.model_id}] [批次组处理] 无有效决策，跳过执行")
            return
        
        logger.info(f"[Model {self.model_id}] [批次组处理] 合并完成: 决策数={len(all_decisions)}, 对话数={len(all_payloads)}")
        
        # ========== 步骤1: 记录所有批次的AI对话到数据库 ==========
        logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤1] 记录AI对话到数据库...")
        for payload in all_payloads:
            try:
                self._record_ai_conversation(payload)
            except Exception as e:
                logger.error(f"[Model {self.model_id}] [批次组处理] 记录AI对话失败: {e}")
        logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤1] AI对话已记录")
        
        # ========== 步骤2: 获取锁并执行所有决策（线程安全） ==========
        logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2] 等待获取锁以执行决策...")
        lock_acquire_start = datetime.now(timezone(timedelta(hours=8)))
        
        with portfolio_lock:
            lock_acquire_duration = (datetime.now(timezone(timedelta(hours=8))) - lock_acquire_start).total_seconds()
            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.1] 锁已获取，等待时间={lock_acquire_duration:.3f}秒")
            
            # 获取最新持仓状态
            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.2] 获取最新持仓状态...")
            latest_portfolio = self.db.get_portfolio(self.model_id, current_prices)
            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.2] 最新持仓状态: "
                        f"总价值=${latest_portfolio.get('total_value', 0):.2f}, "
                        f"现金=${latest_portfolio.get('cash', 0):.2f}, "
                        f"持仓数={len(latest_portfolio.get('positions', []) or [])}")
            
            # 执行所有决策
            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.3] 开始执行决策...")
            execution_start = datetime.now(timezone(timedelta(hours=8)))
            batch_results = self._execute_decisions(
                all_decisions,
                all_market_states,
                latest_portfolio
            )
            execution_duration = (datetime.now(timezone(timedelta(hours=8))) - execution_start).total_seconds()
            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.3] 决策执行完成: 耗时={execution_duration:.2f}秒, 结果数={len(batch_results)}")
            
            # 记录每个执行结果
            for idx, result in enumerate(batch_results):
                logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.3.{idx+1}] 执行结果: "
                            f"合约={result.get('symbol', 'N/A')}, "
                            f"信号={result.get('signal')}, "
                            f"数量={result.get('position_amt', 0)}, "
                            f"价格=${result.get('price', 0):.4f}, "
                            f"错误={result.get('error', '无')}")
            
            # 添加到执行结果列表（线程安全）
            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.4] 添加执行结果到列表（当前总数: {len(executions)}）...")
            executions.extend(batch_results)
            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.4] 执行结果已添加（新总数: {len(executions)}）")
            
            logger.info(f"[Model {self.model_id}] [批次组处理] 执行完成, 决策数: {len(all_decisions)}, 执行结果: {len(batch_results)}")
            
            # ========== 步骤3: 更新portfolio和constraints ==========
            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤3] 更新portfolio和constraints...")
            
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
            
            # 更新constraints
            old_occupied = constraints.get('occupied', 0)
            old_available_cash = constraints.get('available_cash', 0)
            constraints['occupied'] = len(latest_portfolio.get('positions', []) or [])
            constraints['available_cash'] = latest_portfolio.get('cash', 0)
            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤3.3] constraints已更新: "
                        f"已占用 {old_occupied} -> {constraints['occupied']}, "
                        f"可用现金 ${old_available_cash:.2f} -> ${constraints['available_cash']:.2f}")
            
            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤3] 状态更新完成，释放锁")

    def _process_and_execute_sell_batch(
        self,
        batch_positions: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        market_state: Dict,
        constraints_text: str,
        portfolio_lock: threading.Lock,
        executions: List,
        batch_num: int,
        total_batches: int
    ) -> Dict:
        """
        处理单个批次的卖出决策
        
        线程内部流程：
        1. 为当前批次创建临时portfolio
        2. 调用AI模型获取卖出决策
        3. 记录AI对话到数据库
        4. 获取决策结果
        5. 获取锁，执行决策（线程安全）
        6. 更新执行结果列表
        
        注意：此方法在独立线程中执行，需要线程安全处理
        """
        thread_id = threading.current_thread().ident
        batch_start_time = datetime.now(timezone(timedelta(hours=8)))
        batch_symbols = [pos.get('symbol', 'N/A') for pos in batch_positions]  # 【字段更新】使用新字段名symbol替代future
        
        logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                    f"开始处理批次，持仓合约: {batch_symbols}")
        
        try:
            # ========== 步骤0: 验证所有symbol的市场数据 ==========
            logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                        f"[步骤0] 验证symbol市场数据...")
            
            valid_positions = []
            invalid_symbols = []
            
            for position in batch_positions:
                symbol = position.get('symbol', '')
                if not symbol or symbol == 'N/A':
                    continue
                
                symbol_upper = symbol.upper()
                
                # 验证数据
                is_valid, error_msg = self._validate_symbol_market_data(
                    symbol,
                    market_state,
                    query_symbol=symbol_upper,
                    error_context=f"卖出批次{batch_num}/{total_batches}"
                )
                
                if is_valid:
                    valid_positions.append(position)
                else:
                    invalid_symbols.append((symbol, error_msg))
                    # 打印醒目的warning日志
                    logger.warning(
                        f"@@@ [Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                        f"@@@ SYMBOL数据验证失败，跳过AI决策询问: {symbol_upper} @@@\n"
                        f"@@@ 错误信息: {error_msg} @@@\n"
                        f"@@@ 查询symbol: {symbol_upper} @@@"
                    )
            
            # 如果所有symbol都无效，返回跳过结果
            if not valid_positions:
                logger.warning(
                    f"@@@ [Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                    f"@@@ 批次中所有symbol数据验证失败，跳过AI决策询问 @@@\n"
                    f"@@@ 无效symbol详情: {[f'{s}: {e}' for s, e in invalid_symbols]} @@@"
                )
                return {
                    'skipped': True,
                    'decisions': {},
                    'error': f'所有symbol数据验证失败: {len(invalid_symbols)}个symbol无效'
                }
            
            # 如果有部分symbol无效，记录警告但继续处理有效的symbol
            if invalid_symbols:
                logger.warning(
                    f"@@@ [Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                    f"@@@ 批次中部分symbol数据验证失败，将只处理有效symbol @@@\n"
                    f"@@@ 有效symbol: {[p.get('symbol') for p in valid_positions]} @@@\n"
                    f"@@@ 无效symbol详情: {[f'{s}: {e}' for s, e in invalid_symbols]} @@@"
                )
            
            # ========== 步骤1: 为当前批次创建临时portfolio ==========
            logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                        f"[步骤1] 创建临时portfolio，仅包含当前批次持仓... (有效symbol数: {len(valid_positions)})")
            batch_portfolio = portfolio.copy()
            batch_portfolio['positions'] = valid_positions  # 只使用有效的positions
            
            # ========== 步骤2: 调用AI模型获取卖出决策 ==========
            logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                        f"[步骤2] 调用AI模型进行卖出决策... (有效symbol数: {len(valid_positions)})")
            
            ai_call_start = datetime.now(timezone(timedelta(hours=8)))
            sell_payload = self.ai_trader.make_sell_decision(
                batch_portfolio,
                market_state,
                account_info,
                constraints_text=constraints_text,
                model_id=self.model_id
            )
            ai_call_duration = (datetime.now(timezone(timedelta(hours=8))) - ai_call_start).total_seconds()
            
            is_skipped = sell_payload.get('skipped', False)
            has_prompt = bool(sell_payload.get('prompt'))
            decisions = sell_payload.get('decisions') or {}
            logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                        f"[步骤2] AI调用完成: 耗时={ai_call_duration:.2f}秒, "
                        f"跳过={is_skipped}, 有提示词={has_prompt}, 决策数={len(decisions)}")

            # 检查是否需要跳过执行
            if is_skipped or not has_prompt:
                logger.info(f"[Model {self.model_id}] 卖出批次 {batch_num}/{total_batches} 跳过执行")
                return sell_payload

            # ========== 步骤3: 记录AI对话到数据库 ==========
            logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                        f"[步骤3] 记录AI对话到数据库...")
            self._record_ai_conversation(sell_payload)
            logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                        f"[步骤3] AI对话已记录")

            # ========== 步骤4: 获取决策结果 ==========
            logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                        f"[步骤4] 解析决策结果...")
            if not decisions:
                logger.info(f"[Model {self.model_id}] 卖出批次 {batch_num}/{total_batches} 无卖出决策")
                return sell_payload
            
            decision_symbols = list(decisions.keys())
            logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                        f"[步骤4] 决策结果解析完成: 决策合约={decision_symbols}")
            for symbol, decision in decisions.items():
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                            f"[步骤4] 决策详情 [{symbol}]: "
                            f"信号={decision.get('signal')}, "
                            f"数量={decision.get('quantity', 0)}")

            # ========== 步骤5: 获取锁并执行决策（线程安全） ==========
            logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                        f"[步骤5] 等待获取锁以执行决策...")
            lock_acquire_start = datetime.now(timezone(timedelta(hours=8)))
            
            with portfolio_lock:
                lock_acquire_duration = (datetime.now(timezone(timedelta(hours=8))) - lock_acquire_start).total_seconds()
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                            f"[步骤5.1] 锁已获取，等待时间={lock_acquire_duration:.3f}秒")
                
                # 获取最新持仓状态（可能已被其他批次修改）
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                            f"[步骤5.2] 获取最新持仓状态...")
                latest_portfolio = self.db.get_portfolio(self.model_id)
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                            f"[步骤5.2] 最新持仓状态: "
                            f"总价值=${latest_portfolio.get('total_value', 0):.2f}, "
                            f"现金=${latest_portfolio.get('cash', 0):.2f}, "
                            f"持仓数={len(latest_portfolio.get('positions', []) or [])}")
                
                # 执行决策
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                            f"[步骤5.3] 开始执行决策...")
                execution_start = datetime.now(timezone(timedelta(hours=8)))
                batch_results = self._execute_decisions(
                    decisions,
                    market_state,
                    latest_portfolio
                )
                execution_duration = (datetime.now(timezone(timedelta(hours=8))) - execution_start).total_seconds()
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                            f"[步骤5.3] 决策执行完成: 耗时={execution_duration:.2f}秒, 结果数={len(batch_results)}")
                
                # 记录每个执行结果
                for idx, result in enumerate(batch_results):
                    logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                                f"[步骤5.3.{idx+1}] 执行结果: "
                                f"合约={result.get('symbol', 'N/A')}, "
                                f"信号={result.get('signal')}, "
                                f"数量={result.get('position_amt', 0)}, "
                                f"价格=${result.get('price', 0):.4f}, "
                                f"错误={result.get('error', '无')}")
                
                # 添加到执行结果列表（线程安全）
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                            f"[步骤5.4] 添加执行结果到列表（当前总数: {len(executions)}）...")
                executions.extend(batch_results)
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                            f"[步骤5.4] 执行结果已添加（新总数: {len(executions)}）")
                
                logger.info(f"[Model {self.model_id}] 卖出批次 {batch_num}/{total_batches} 执行完成, 决策数: {len(decisions)}, 执行结果: {len(batch_results)}")
            
            # ========== 步骤6: 记录批次处理时间 ==========
            batch_duration = (datetime.now(timezone(timedelta(hours=8))) - batch_start_time).total_seconds()
            logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                        f"批次处理完成，耗时: {batch_duration:.2f}秒")
            
            return sell_payload
            
        except Exception as e:
            logger.error(f"[Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                        f"处理批次时发生异常: {str(e)}")
            import traceback
            logger.error(f"[Model {self.model_id}] [线程-{thread_id}] [卖出批次 {batch_num}/{total_batches}] "
                        f"异常堆栈: {traceback.format_exc()}")
            return {'skipped': True, 'decisions': {}}

    def _process_and_execute_batch(
        self,
        batch_candidates: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        constraints: Dict,
        constraints_text: str,
        market_state: Dict,
        current_prices: Dict[str, float],
        portfolio_lock: threading.Lock,
        executions: List,
        batch_num: int,
        total_batches: int,
        symbol_source: str = 'leaderboard'
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
        batch_start_time = datetime.now(timezone(timedelta(hours=8)))
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
            
            # 将market_state转换为market_snapshot格式（用于AI决策）
            # market_snapshot格式：List[Dict]，每个Dict包含symbol、price、timeframes等
            market_snapshot = []
            for candidate in batch_candidates:
                symbol = candidate.get('symbol', '').upper()
                if symbol in market_state:
                    state_info = market_state[symbol]
                    snapshot_entry = {
                        'symbol': symbol,
                        'contract_symbol': state_info.get('contract_symbol', f"{symbol}USDT"),
                        'price': state_info.get('price', 0),
                        'quote_volume': state_info.get('quote_volume', state_info.get('daily_volume', 0)),
                        'change_percent': state_info.get('change_24h', 0),
                        'timeframes': state_info.get('indicators', {}).get('timeframes', {})
                    }
                    market_snapshot.append(snapshot_entry)
            
            ai_call_start = datetime.now(timezone(timedelta(hours=8)))
            buy_payload = self.ai_trader.make_buy_decision(
                batch_candidates,
                portfolio,
                account_info,
                constraints,
                constraints_text=constraints_text,
                market_snapshot=market_snapshot if market_snapshot else None,
                symbol_source=symbol_source,
                model_id=self.model_id
            )
            ai_call_duration = (datetime.now(timezone(timedelta(hours=8))) - ai_call_start).total_seconds()
            
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
            lock_acquire_start = datetime.now(timezone(timedelta(hours=8)))
            
            with portfolio_lock:
                lock_acquire_duration = (datetime.now(timezone(timedelta(hours=8))) - lock_acquire_start).total_seconds()
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
                execution_start = datetime.now(timezone(timedelta(hours=8)))
                batch_results = self._execute_decisions(
                    decisions,
                    market_state,
                    latest_portfolio
                )
                execution_duration = (datetime.now(timezone(timedelta(hours=8))) - execution_start).total_seconds()
                logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                            f"[步骤4.3] 决策执行完成: 耗时={execution_duration:.2f}秒, 结果数={len(batch_results)}")
                
                # 记录每个执行结果
                for idx, result in enumerate(batch_results):
                    logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                                f"[步骤4.3.{idx+1}] 执行结果: "
                                f"合约={result.get('symbol', 'N/A')}, "
                                f"信号={result.get('signal')}, "
                                f"数量={result.get('position_amt', 0)}, "
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
            batch_end_time = datetime.now(timezone(timedelta(hours=8)))
            batch_duration = (batch_end_time - batch_start_time).total_seconds()
            logger.debug(f"[Model {self.model_id}] [线程-{thread_id}] [批次 {batch_num}/{total_batches}] "
                        f"批次处理完成: 总耗时={batch_duration:.2f}秒")

            return buy_payload

        except Exception as exc:
            batch_end_time = datetime.now(timezone(timedelta(hours=8)))
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

    # ============ 候选选择方法 ============
    # 根据模型配置选择买入候选交易对
    
    def _should_filter_held_symbols(self) -> bool:
        """
        配置方法：决定是否过滤已持仓的symbol
        
        此方法用于控制候选symbol选择逻辑，后期可以通过配置或模型设置来决定是否过滤已持仓的symbol。
        
        Returns:
            bool: True表示过滤已持仓的symbol，False表示不过滤
        """
        # 默认过滤已持仓的symbol，避免重复开仓
        # 后期可以通过配置或模型设置来调整此行为
        return True
    
    def _get_candidate_symbols_by_source(self, symbol_source: str, limit: int = None) -> List[Dict]:
        """
        根据模型的symbol_source字段获取候选symbol列表
        
        Args:
            symbol_source: 数据源类型，'leaderboard' 或 'future'
            limit: 可选的数量限制
            
        Returns:
            List[Dict]: 候选symbol列表，每个元素包含symbol等基本信息
        """
        if symbol_source == 'future':
            # 从futures表获取所有已配置的交易对
            try:
                entries = self.market_fetcher.get_configured_futures_symbols()
                if not entries:
                    logger.warning(f"[Model {self.model_id}] 未获取到futures表配置的交易对")
                    return []
                # 应用数量限制
                if limit:
                    entries = entries[:limit]
                return entries
            except Exception as exc:
                logger.warning(f"[Model {self.model_id}] 获取futures表候选symbol失败: {exc}")
                return []
        else:
            # 默认从涨跌榜获取（leaderboard）
            try:
                limit = limit or getattr(app_config, 'PROMPT_MARKET_SYMBOL_LIMIT', 5)
                limit = max(1, int(limit))
                leaderboard = self.market_fetcher.get_leaderboard(limit=limit)
                
                # 合并涨幅榜和跌幅榜
                gainers = leaderboard.get('gainers') or []
                losers = leaderboard.get('losers') or []
                entries = gainers[:limit] + losers[:limit]
                
                logger.info(f"[Model {self.model_id}] 从涨跌榜获取到 {len(entries)} 个候选symbol")
                return entries
            except Exception as exc:
                logger.warning(f"[Model {self.model_id}] 获取涨跌榜候选symbol失败: {exc}")
                return []
    
    def _filter_candidates_by_portfolio(self, candidates: List[Dict], portfolio: Dict) -> List[Dict]:
        """
        根据持仓信息过滤候选symbol列表
        
        Args:
            candidates: 候选symbol列表
            portfolio: 当前持仓组合信息
            
        Returns:
            List[Dict]: 过滤后的候选symbol列表
        """
        if not self._should_filter_held_symbols():
            return candidates
        
        # 计算已持仓的交易对
        held = {pos['symbol'] for pos in (portfolio.get('positions') or [])}
        
        # 过滤掉已持仓的交易对
        filtered = []
        for candidate in candidates:
            symbol = candidate.get('symbol')
            if symbol and symbol not in held:
                filtered.append(candidate)
        
        filtered_count = len(candidates) - len(filtered)
        if filtered_count > 0:
            logger.info(f"[Model {self.model_id}] 过滤掉 {filtered_count} 个已持仓的候选symbol")
        
        return filtered
    
    def _build_market_state_for_candidates(self, candidates: List[Dict], symbol_source: str, include_indicators: bool = True) -> Dict:
        """
        基于候选symbol列表构建市场状态信息（价格、成交量，可选K线指标）
        
        Args:
            candidates: 候选symbol列表
            symbol_source: 数据源类型，用于确定使用symbol还是contract_symbol
            include_indicators: 是否获取技术指标，默认True（向后兼容）
                              False时只获取价格信息，不获取指标（用于优化性能）
            
        Returns:
            Dict: 市场状态字典，key为symbol，value为包含价格、成交量、技术指标等信息
        """
        market_state = {}
        
        if not candidates:
            return market_state
        
        # 提取symbol列表（统一使用contract_symbol查询24_market_tickers表）
        # 注意：24_market_tickers表中的symbol字段是完整格式（如'BTCUSDT'），
        # 而futures表中的symbol是基础符号（如'BTC'），contract_symbol是完整格式（如'BTCUSDT'）
        # leaderboard返回的数据中，symbol字段已经是完整格式（如'BTCUSDT'）
        symbol_list = []
        symbol_to_contract = {}
        for candidate in candidates:
            symbol = candidate.get('symbol')
            if not symbol:
                continue
            
            # 优先使用contract_symbol字段（如果存在），确保与24_market_tickers表的格式一致
            # 如果不存在contract_symbol，则使用symbol并确保以USDT结尾
            contract_symbol = candidate.get('contract_symbol')
            if contract_symbol:
                # 如果提供了contract_symbol，直接使用（确保大写）
                contract_symbol = contract_symbol.upper()
            else:
                # 如果没有contract_symbol，使用symbol并确保以USDT结尾
                symbol_upper = symbol.upper()
                if not symbol_upper.endswith('USDT'):
                    contract_symbol = f"{symbol_upper}USDT"
                else:
                    contract_symbol = symbol_upper
            
            # 保存symbol到contract_symbol的映射
            symbol_to_contract[symbol] = contract_symbol
            symbol_list.append(contract_symbol)
        
        if not symbol_list:
            return market_state
        
        # 获取价格数据
        prices = self.market_fetcher.get_prices(symbol_list)
        
        # 为每个候选symbol构建市场状态
        for candidate in candidates:
            symbol = candidate.get('symbol')
            if not symbol:
                continue
            
            symbol_upper = symbol.upper()
            
            # 统一使用contract_symbol作为查询key（确保与24_market_tickers表的格式一致）
            # 从symbol_to_contract映射中获取contract_symbol，如果不存在则从candidate中获取或生成
            contract_symbol = symbol_to_contract.get(symbol)
            if not contract_symbol:
                # 如果映射中不存在，尝试从candidate中获取contract_symbol
                contract_symbol = candidate.get('contract_symbol')
                if contract_symbol:
                    contract_symbol = contract_symbol.upper()
                else:
                    # 如果candidate中也没有contract_symbol，使用symbol并确保以USDT结尾
                    if not symbol_upper.endswith('USDT'):
                        contract_symbol = f"{symbol_upper}USDT"
                    else:
                        contract_symbol = symbol_upper
            
            # 统一使用contract_symbol作为查询key和技术指标查询的symbol
            query_symbol = contract_symbol  # 用于获取技术指标
            price_key = contract_symbol  # 用于查询价格（与24_market_tickers表的symbol字段格式一致）
            
            # 获取价格信息
            price_info = prices.get(price_key, {})
            
            if not price_info:
                logger.warning(f"[Model {self.model_id}] 无法获取 {symbol} 的实时价格")
                continue
            
            # 根据参数决定是否获取技术指标
            timeframes_data = {}
            if include_indicators:
                # 获取技术指标（所有时间周期）
                merged_data = self._merge_timeframe_data(query_symbol)
                timeframes_data = merged_data.get(query_symbol, {}) if merged_data else {}
            
            # 构建市场状态条目
            market_state[symbol_upper] = {
                'price': price_info.get('price', candidate.get('price', candidate.get('last_price', 0))),
                'name': candidate.get('name', symbol),
                'exchange': candidate.get('exchange', 'BINANCE_FUTURES'),
                'contract_symbol': candidate.get('contract_symbol') or f"{symbol}USDT",
                'change_24h': price_info.get('change_24h', candidate.get('change_percent', 0)),
                'daily_volume': price_info.get('daily_volume', candidate.get('quote_volume', 0)),
                'quote_volume': price_info.get('daily_volume', candidate.get('quote_volume', 0)),
                'indicators': {'timeframes': timeframes_data} if timeframes_data else {},
                'source': symbol_source
            }
        
        logger.info(f"[Model {self.model_id}] 为 {len(market_state)} 个候选symbol构建了市场状态信息")
        return market_state
    
    def _select_buy_candidates(self, portfolio: Dict, symbol_source: str, include_indicators: bool = True) -> tuple[List[Dict], Dict]:
        """
        【重构方法】选择买入候选交易对并构建对应的市场状态
        
        新逻辑：
        1. 根据模型的symbol_source字段获取候选symbol来源
        2. 过滤已持仓的symbol（可配置）
        3. 基于候选symbol列表获取市场快照信息（价格、成交量，可选K线指标）
        
        Args:
            portfolio: 当前持仓组合信息
            symbol_source: 数据源类型，'leaderboard' 或 'future'
            include_indicators: 是否获取技术指标，默认True（向后兼容）
                              False时只获取价格信息，不获取指标（用于优化性能）
            
        Returns:
            tuple: (候选symbol列表, 市场状态字典)
        """
        # 步骤1: 根据symbol_source获取候选symbol列表
        limit = getattr(app_config, 'PROMPT_MARKET_SYMBOL_LIMIT', 5)
        candidates = self._get_candidate_symbols_by_source(symbol_source, limit=limit * 2)
        
        if not candidates:
            logger.info(f"[Model {self.model_id}] 未获取到候选symbol")
            return [], {}
        
        logger.info(f"[Model {self.model_id}] 从{symbol_source}数据源获取到 {len(candidates)} 个候选symbol")
        
        # 步骤2: 过滤已持仓的symbol（可配置）
        filtered_candidates = self._filter_candidates_by_portfolio(candidates, portfolio)
        
        if not filtered_candidates:
            logger.info(f"[Model {self.model_id}] 过滤后无可用候选symbol")
            return [], {}
        
        logger.info(f"[Model {self.model_id}] 过滤后剩余 {len(filtered_candidates)} 个候选symbol")
        
        # 步骤3: 基于候选symbol列表获取市场状态信息（价格、成交量，可选K线指标）
        market_state = self._build_market_state_for_candidates(filtered_candidates, symbol_source, include_indicators=include_indicators)
        
        return filtered_candidates, market_state
    
    # ============ 决策执行方法 ============
    # 统一执行AI交易决策，支持多种交易信号类型
    
    def _execute_decisions(self, decisions: Dict, market_state: Dict, portfolio: Dict) -> list:
        """
        执行AI交易决策（线程安全）
        
        根据AI返回的signal字段，调用相应的执行方法：
        - 'buy_to_enter' / 'sell_to_enter': 调用 _execute_buy（开仓）
        - 'close_position': 调用 _execute_close（平仓）
        - 'stop_loss': 调用 _execute_stop_loss（止损）
        - 'take_profit': 调用 _execute_take_profit（止盈）
        - 'hold': 保持观望，不执行任何操作
        
        Args:
            decisions: AI决策字典，key为交易对符号，value为决策详情
            market_state: 市场状态数据
            portfolio: 当前持仓组合信息
        
        Returns:
            List[Dict]: 执行结果列表，每个元素包含执行详情或错误信息
        
        Note:
            此方法使用trading_lock确保线程安全，避免买入和卖出服务同时执行交易操作
        """
        results = []

        positions_map = {pos['symbol']: pos for pos in portfolio.get('positions', [])}

        # 获取全局交易锁，确保买入和卖出服务线程不会同时执行交易操作
        with self.trading_lock:
            logger.info(f"[Model {self.model_id}] [交易执行] 获取到交易锁，=====开始执行SDK交易决策=====")
            
            for symbol, decision in decisions.items():
                signal = decision.get('signal', '').lower()

                try:
                    if signal == 'buy_to_enter' or signal == 'sell_to_enter':
                        # 【统一执行方法】buy_to_enter（开多）和sell_to_enter（开空）都调用_execute_buy方法
                        # _execute_buy方法会根据signal自动确定position_side：
                        # - buy_to_enter → position_side = 'LONG'
                        # - sell_to_enter → position_side = 'SHORT'
                        result = self._execute_buy(symbol, decision, market_state, portfolio)
                    elif signal == 'close_position':
                        if symbol not in positions_map:
                            result = {'symbol': symbol, 'error': 'No position to close'}
                        else:
                            result = self._execute_close(symbol, decision, market_state, portfolio)
                    elif signal == 'stop_loss':
                        if symbol not in positions_map:
                            result = {'symbol': symbol, 'error': 'No position for stop loss'}
                        else:
                            result = self._execute_stop_loss(symbol, decision, market_state, portfolio)
                    elif signal == 'take_profit':
                        if symbol not in positions_map:
                            result = {'symbol': symbol, 'error': 'No position for take profit'}
                        else:
                            result = self._execute_take_profit(symbol, decision, market_state, portfolio)
                    elif signal == 'hold':
                        result = {'symbol': symbol, 'signal': 'hold', 'message': '保持观望'}
                    else:
                        result = {'symbol': symbol, 'error': f'Unknown signal: {signal}'}

                    results.append(result)

                except Exception as e:
                    results.append({'symbol': symbol, 'error': str(e)})
            
            logger.debug(f"[Model {self.model_id}] [交易执行] 交易决策执行完成，释放交易锁")

        return results

    # ============ 订单执行方法 ============
    # 执行具体的交易订单操作：开仓、平仓、止损、止盈
    
    def _execute_buy(self, symbol: str, decision: Dict, market_state: Dict, portfolio: Dict) -> Dict:
        """
        执行开仓操作（统一方法，支持开多和开空）
        
        【signal与position_side的映射关系】
        根据AI模型返回的signal字段自动确定position_side：
        - signal='buy_to_enter'（开多）→ position_side='LONG'
        - signal='sell_to_enter'（开空）→ position_side='SHORT'
        
        【重要说明】
        - AI模型不再返回position_side字段，只需要返回signal字段
        - 系统会根据signal自动确定position_side
        - trades表中记录的signal字段：buy_to_enter 或 sell_to_enter
        
        【position_side的作用】
        根据position_side的值决定：
        - SDK调用的side参数：LONG持仓用SELL保护，SHORT持仓用BUY保护
        - 数据库记录的position_side：根据signal自动确定
        - trades表的side字段：LONG开仓用'buy'，SHORT开仓用'sell'
        """
        quantity = decision.get('quantity', 0)
        leverage = self._resolve_leverage(decision)
        price = market_state[symbol]['price']
        
        # 【根据signal自动确定position_side】不再从decision中获取position_side字段
        signal = decision.get('signal', '').lower()
        if signal == 'buy_to_enter':
            position_side = 'LONG'  # 开多仓
            trade_signal = 'buy_to_enter'  # trades表记录的signal
        elif signal == 'sell_to_enter':
            position_side = 'SHORT'  # 开空仓
            trade_signal = 'sell_to_enter'  # trades表记录的signal
        else:
            # 如果signal不是buy_to_enter或sell_to_enter，默认使用LONG（向后兼容）
            logger.warning(f"[Model {self.model_id}] Invalid signal '{signal}' for _execute_buy, defaulting to LONG")
            position_side = 'LONG'
            trade_signal = 'buy_to_enter'
        
        logger.info(f"[Model {self.model_id}] [开仓] {symbol} signal={signal} → position_side={position_side}")

        positions = portfolio.get('positions', [])
        existing_symbols = {pos['symbol'] for pos in positions}
        if symbol not in existing_symbols and len(existing_symbols) >= self.max_positions:
            return {'symbol': symbol, 'error': '达到最大持仓数量，无法继续开仓'}

        # 【获取可用现金】从portfolio中获取cash字段（计算值：初始资金 + 已实现盈亏 - 已用保证金）
        available_cash = portfolio.get('cash', 0)
        if available_cash <= 0:
            return {'symbol': symbol, 'error': '可用现金不足，无法买入'}
        
        max_affordable_qty = available_cash / (price * (1 + self.trade_fee_rate))
        risk_pct = float(decision.get('risk_budget_pct', 3)) / 100
        risk_pct = min(max(risk_pct, 0.01), 0.05)
        risk_based_qty = (available_cash * risk_pct) / (price * (1 + self.trade_fee_rate))

        quantity = float(quantity)
        if quantity <= 0 or quantity > max_affordable_qty:
            quantity = min(max_affordable_qty, risk_based_qty if risk_based_qty > 0 else max_affordable_qty)

        if quantity <= 0:
            return {'symbol': symbol, 'error': '现金不足，无法买入'}

        trade_amount = quantity * price
        trade_fee = trade_amount * self.trade_fee_rate
        required_margin = (quantity * price) / leverage
        total_required = required_margin + trade_fee

        if total_required > available_cash:
            return {'symbol': symbol, 'error': '可用资金不足（含手续费）'}

        # 【确定SDK调用的side参数】根据position_side决定trailing stop的保护方向
        # LONG持仓：用SELL方向来设置trailing stop（保护多仓，价格下跌时触发）
        # SHORT持仓：用BUY方向来设置trailing stop（保护空仓，价格上涨时触发）
        if position_side == 'LONG':
            trailing_stop_side = 'SELL'  # 保护LONG持仓使用SELL方向
        else:  # SHORT
            trailing_stop_side = 'BUY'  # 保护SHORT持仓使用BUY方向
        
        # 获取交易上下文
        model_uuid, trade_id = self._get_trade_context()
        
        # 调用SDK执行交易
        sdk_response = None
        sdk_call_skipped = False
        sdk_skip_reason = None
        binance_client = self._create_binance_order_client()
        if binance_client:
            try:
                logger.info(f"@API@ [Model {self.model_id}] [market_trade] === 准备调用接口 ===" 
                          f" | symbol={symbol} | side={trailing_stop_side} | position_side={position_side} | "
                          f"quantity={quantity} | price={price}")
                
                conversation_id = self._get_conversation_id()
                
                sdk_response = binance_client.market_trade(
                    symbol=symbol,
                    side=trailing_stop_side,
                    order_type='MARKET',
                    position_side=position_side,
                    quantity=quantity,
                    model_id=model_uuid,
                    conversation_id=conversation_id,
                    trade_id=trade_id,
                    db=self.db
                )
                
                logger.info(f"@API@ [Model {self.model_id}] [market_trade] === 接口调用成功 ==="
                          f" | symbol={symbol} | response={sdk_response}")
            except Exception as sdk_err:
                logger.error(f"@API@ [Model {self.model_id}] [market_trade] === 接口调用失败 ==="
                           f" | symbol={symbol} | error={sdk_err}", exc_info=True)
        else:
            sdk_call_skipped, sdk_skip_reason = self._handle_sdk_client_error(symbol, 'market_trade')

        # 【更新持仓】使用根据signal自动确定的position_side
        try:
            self.db.update_position(
                self.model_id, symbol=symbol, position_amt=quantity, avg_price=price, 
                leverage=leverage, position_side=position_side  # 使用根据signal自动确定的position_side
            )
        except Exception as db_err:
            logger.error(f"TRADE: Update position failed ({trade_signal.upper()}) model={self.model_id} future={symbol}: {db_err}")
            raise

        # 【确定trades表的side字段】开仓时的side字段
        # LONG开仓：side='buy'（开多仓）
        # SHORT开仓：side='sell'（开空仓）
        if position_side == 'LONG':
            trade_side = 'buy'  # 开多仓
        else:  # SHORT
            trade_side = 'sell'  # 开空仓
        
        # 记录交易
        logger.info(f"TRADE: PENDING - Model {self.model_id} {trade_signal.upper()} {symbol} position_side={position_side} qty={quantity} price={price} fee={trade_fee}")
        try:
            self.db.insert_rows(
                self.db.trades_table,
                [[trade_id, model_uuid, symbol.upper(), trade_signal, quantity, price, leverage, trade_side, 0, trade_fee, datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)]],
                ["id", "model_id", "future", "signal", "quantity", "price", "leverage", "side", "pnl", "fee", "timestamp"]
            )
        except Exception as db_err:
            logger.error(f"TRADE: Add trade failed ({trade_signal.upper()}) model={self.model_id} future={symbol}: {db_err}")
            raise
        self._log_trade_record(trade_signal, symbol, position_side, sdk_call_skipped, sdk_skip_reason)

        return {
            'symbol': symbol,
            'signal': trade_signal,  # 返回实际的signal（buy_to_enter或sell_to_enter）
            'position_amt': quantity,
            'position_side': position_side,  # 返回position_side信息
            'price': price,
            'leverage': leverage,
            'fee': trade_fee,
            'message': f'开仓 {symbol} {position_side} {quantity:.4f} @ ${price:.2f} (手续费: ${trade_fee:.2f})'
        }

    def _execute_close(self, symbol: str, decision: Dict, market_state: Dict, portfolio: Dict) -> Dict:
        """
        执行平仓操作
        
        根据持仓的position_side自动确定平仓方向：
        - LONG持仓：使用SELL方向平仓（平多仓）
        - SHORT持仓：使用BUY方向平仓（平空仓）
        
        Args:
            symbol: 交易对符号
            decision: AI决策详情，包含signal='close_position'
            market_state: 市场状态数据，包含当前价格
            portfolio: 当前持仓组合信息
        
        Returns:
            Dict: 执行结果，包含：
                - symbol: 交易对符号
                - signal: 'close_position'
                - position_amt: 平仓数量
                - price: 平仓价格
                - pnl: 净盈亏
                - fee: 手续费
                - message: 执行消息
        
        Note:
            - 使用STOP_MARKET订单类型，以当前价格作为触发价格（立即触发）
            - 计算毛盈亏和净盈亏（扣除手续费）
            - 平仓后更新数据库持仓记录
        """
        # 查找持仓信息
        position = self._find_position(portfolio, symbol)
        if not position:
            return {'symbol': symbol, 'error': 'Position not found'}

        current_price = market_state[symbol]['price']
        entry_price = position.get('avg_price', 0)
        position_amt = abs(position.get('position_amt', 0))
        position_side = position.get('position_side', 'LONG')

        # 计算毛盈亏和净盈亏
        if position_side == 'LONG':
            gross_pnl = (current_price - entry_price) * position_amt
        else:  # SHORT
            gross_pnl = (entry_price - current_price) * position_amt

        trade_amount = position_amt * current_price
        trade_fee = trade_amount * self.trade_fee_rate
        net_pnl = gross_pnl - trade_fee

        # 确定交易方向
        side_for_trade = self._get_side_for_trade(position_side)

        # 获取交易上下文
        model_uuid, trade_id = self._get_trade_context()
        
        # 【调用SDK执行交易】使用close_position_trade
        # 注意：close_position_trade只支持STOP_MARKET或TAKE_PROFIT_MARKET，不支持MARKET
        # 对于立即平仓，使用当前价格作为stop_price的STOP_MARKET订单
        sdk_response = None
        sdk_call_skipped = False
        sdk_skip_reason = None
        # 【每次创建新的Binance订单客户端】确保使用最新的model对应的api_key和api_secret
        binance_client = self._create_binance_order_client()
        if binance_client:
            try:
                # 【调用前日志】记录调用参数
                logger.info(f"@API@ [Model {self.model_id}] [close_position_trade] === 准备调用接口 ==="
                          f" | symbol={symbol} | side={side_for_trade} | order_type=STOP_MARKET | "
                          f"stop_price={current_price} | position_side={position_side} | "
                          f"position_amt={position_amt} | entry_price={entry_price}")
                
                conversation_id = self._get_conversation_id()
                
                sdk_response = binance_client.close_position_trade(
                    symbol=symbol,
                    side=side_for_trade,
                    order_type='STOP_MARKET',
                    stop_price=current_price,  # 使用当前价格作为触发价格，实现立即平仓
                    position_side=position_side,
                    quantity=position_amt,  # 传递持仓数量
                    model_id=model_uuid,
                    conversation_id=conversation_id,
                    trade_id=trade_id,
                    db=self.db
                )
                
                # 【调用后日志】记录接口返回内容
                logger.info(f"@API@ [Model {self.model_id}] [close_position_trade] === 接口调用成功 ==="
                          f" | symbol={symbol} | response={sdk_response}")
            except Exception as sdk_err:
                logger.error(f"@API@ [Model {self.model_id}] [close_position_trade] === 接口调用失败 ==="
                           f" | symbol={symbol} | error={sdk_err}", exc_info=True)
                # SDK调用失败不影响数据库记录，继续执行
        else:
            sdk_call_skipped, sdk_skip_reason = self._handle_sdk_client_error(symbol, 'close_position_trade')

        # Close position in database
        try:
            self.db.close_position(self.model_id, symbol=symbol, position_side=position_side)
        except Exception as db_err:
            logger.error(f"TRADE: Close position failed model={self.model_id} future={symbol}: {db_err}")
            raise
        
        # 记录交易
        logger.info(f"TRADE: PENDING - Model {self.model_id} CLOSE {symbol} position_side={position_side} position_amt={position_amt} price={current_price} fee={trade_fee} net_pnl={net_pnl}")
        try:
            self.db.insert_rows(
                self.db.trades_table,
                [[trade_id, model_uuid, symbol.upper(), 'close_position', position_amt, current_price, position.get('leverage', 1), side_for_trade.lower(), net_pnl, trade_fee, datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)]],
                ["id", "model_id", "future", "signal", "quantity", "price", "leverage", "side", "pnl", "fee", "timestamp"]
            )
        except Exception as db_err:
            logger.error(f"TRADE: Add trade failed (CLOSE) model={self.model_id} future={symbol}: {db_err}")
            raise
        self._log_trade_record('close_position', symbol, position_side, sdk_call_skipped, sdk_skip_reason)

        return {
            'symbol': symbol,
            'signal': 'close_position',
            'position_amt': position_amt,
            'price': current_price,
            'pnl': net_pnl,
            'fee': trade_fee,
            'message': f'平仓 {symbol}, 毛收益 ${gross_pnl:.2f}, 手续费 ${trade_fee:.2f}, 净收益 ${net_pnl:.2f}'
        }

    def _execute_stop_loss(self, symbol: str, decision: Dict, market_state: Dict, portfolio: Dict) -> Dict:
        """
        执行止损操作
        
        根据持仓的position_side自动确定止损方向：
        - LONG持仓：使用SELL方向止损（价格下跌时触发）
        - SHORT持仓：使用BUY方向止损（价格上涨时触发）
        
        Args:
            symbol: 交易对符号
            decision: AI决策详情，包含signal='stop_loss'和stop_price（止损价格）
            market_state: 市场状态数据
            portfolio: 当前持仓组合信息
        
        Returns:
            Dict: 执行结果，包含止损单详情
        
        Note:
            - 使用STOP_MARKET订单类型，只需要stop_price参数
            - 止损单可能不会立即成交，这里只是下单记录
        """
        # 查找持仓信息
        position = self._find_position(portfolio, symbol)
        if not position:
            return {'symbol': symbol, 'error': 'Position not found'}

        current_price = market_state[symbol]['price']
        position_amt = abs(position.get('position_amt', 0))
        position_side = position.get('position_side', 'LONG')
        
        # 获取止损价格
        stop_price = decision.get('stop_price')
        if not stop_price:
            return {'symbol': symbol, 'error': 'Stop price not provided'}
        stop_price = float(stop_price)
        
        # 确定交易方向
        side_for_trade = self._get_side_for_trade(position_side)

        # 获取交易上下文
        model_uuid, trade_id = self._get_trade_context()
        
        # 【调用SDK执行交易】使用stop_loss_trade
        sdk_response = None
        sdk_call_skipped = False
        sdk_skip_reason = None
        # 【每次创建新的Binance订单客户端】确保使用最新的model对应的api_key和api_secret
        binance_client = self._create_binance_order_client()
        if binance_client:
            try:
                # 【调用前日志】记录调用参数
                logger.info(f"@API@ [Model {self.model_id}] [stop_loss_trade] === 准备调用接口 ==="
                          f" | symbol={symbol} | side={side_for_trade} | order_type=STOP_MARKET | "
                          f"stop_price={stop_price} | position_side={position_side} | "
                          f"position_amt={position_amt} | current_price={current_price}")
                
                conversation_id = self._get_conversation_id()
                
                sdk_response = binance_client.stop_loss_trade(
                    symbol=symbol,
                    side=side_for_trade,
                    order_type='STOP_MARKET',  # 使用STOP_MARKET类型，只需要stop_price
                    stop_price=stop_price,
                    position_side=position_side,
                    quantity=position_amt,  # 添加quantity参数
                    model_id=model_uuid,
                    conversation_id=conversation_id,
                    trade_id=trade_id,
                    db=self.db
                )
                
                # 【调用后日志】记录接口返回内容
                logger.info(f"@API@ [Model {self.model_id}] [stop_loss_trade] === 接口调用成功 ==="
                          f" | symbol={symbol} | response={sdk_response}")
            except Exception as sdk_err:
                logger.error(f"@API@ [Model {self.model_id}] [stop_loss_trade] === 接口调用失败 ==="
                           f" | symbol={symbol} | error={sdk_err}", exc_info=True)
                # SDK调用失败不影响数据库记录，继续执行
        else:
            sdk_call_skipped, sdk_skip_reason = self._handle_sdk_client_error(symbol, 'stop_loss_trade')
        
        # 计算预估手续费（止损单可能不会立即成交，这里只是预估）
        trade_amount = position_amt * stop_price
        trade_fee = trade_amount * self.trade_fee_rate
        
        # 记录止损单到trades表（使用提前生成的trade_id）
        logger.info(f"TRADE: PENDING - Model {self.model_id} STOP_LOSS {symbol} position_side={position_side} position_amt={position_amt} stop_price={stop_price}")
        if sdk_call_skipped:
            logger.warning(f"TRADE: ⚠️ SDK调用被跳过，但交易记录仍将保存到数据库 | symbol={symbol} | reason={sdk_skip_reason}")
        try:
            # 【记录到trades表】side字段使用position_side的反向
            # 注意：这里需要修改add_trade方法支持传入trade_id，或者使用其他方式
            self.db.insert_rows(
                self.db.trades_table,
                [[trade_id, model_uuid, symbol.upper(), 'stop_loss', position_amt, stop_price, position.get('leverage', 1), side_for_trade.lower(), 0, trade_fee, datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)]],
                ["id", "model_id", "future", "signal", "quantity", "price", "leverage", "side", "pnl", "fee", "timestamp"]
            )
        except Exception as db_err:
            logger.error(f"TRADE: Add trade failed (STOP_LOSS) model={self.model_id} symbol={symbol}: {db_err}")
            raise
        if sdk_call_skipped:
            logger.warning(f"TRADE: RECORDED (但SDK未执行) - Model {self.model_id} STOP_LOSS {symbol} | "
                         f"⚠️ 此交易记录已保存，但实际交易未执行，请检查API密钥配置")
        else:
            logger.info(f"TRADE: RECORDED - Model {self.model_id} STOP_LOSS {symbol}")

        return {
            'symbol': symbol,
            'signal': 'stop_loss',
            'position_amt': position_amt,
            'stop_price': stop_price,
            'position_side': position_side,
            'side': side_for_trade.lower(),
            'fee': trade_fee,
            'message': f'止损单 {symbol}, 持仓方向: {position_side}, 止损价格: ${stop_price:.4f}, 数量: {position_amt:.4f}'
        }

    def _execute_take_profit(self, symbol: str, decision: Dict, market_state: Dict, portfolio: Dict) -> Dict:
        """
        执行止盈操作
        
        根据持仓的position_side自动确定止盈方向：
        - LONG持仓：使用SELL方向止盈（价格上涨到目标价时触发）
        - SHORT持仓：使用BUY方向止盈（价格下跌到目标价时触发）
        
        Args:
            symbol: 交易对符号
            decision: AI决策详情，包含signal='take_profit'和stop_price（止盈价格）
            market_state: 市场状态数据
            portfolio: 当前持仓组合信息
        
        Returns:
            Dict: 执行结果，包含止盈单详情
        
        Note:
            - 使用TAKE_PROFIT_MARKET订单类型，只需要stop_price参数
            - 止盈单可能不会立即成交，这里只是下单记录
        """
        # 查找持仓信息
        position = self._find_position(portfolio, symbol)
        if not position:
            return {'symbol': symbol, 'error': 'Position not found'}

        current_price = market_state[symbol]['price']
        position_amt = abs(position.get('position_amt', 0))
        position_side = position.get('position_side', 'LONG')
        
        # 获取止盈价格
        stop_price = decision.get('stop_price')
        if not stop_price:
            return {'symbol': symbol, 'error': 'Take profit price not provided'}
        stop_price = float(stop_price)
        
        # 确定交易方向
        side_for_trade = self._get_side_for_trade(position_side)

        # 获取交易上下文
        model_uuid, trade_id = self._get_trade_context()
        
        # 【调用SDK执行交易】使用take_profit_trade
        sdk_response = None
        sdk_call_skipped = False
        sdk_skip_reason = None
        # 【每次创建新的Binance订单客户端】确保使用最新的model对应的api_key和api_secret
        binance_client = self._create_binance_order_client()
        if binance_client:
            try:
                # 【调用前日志】记录调用参数
                logger.info(f"@API@ [Model {self.model_id}] [take_profit_trade] === 准备调用接口 ==="
                          f" | symbol={symbol} | side={side_for_trade} | order_type=TAKE_PROFIT_MARKET | "
                          f"stop_price={stop_price} | position_side={position_side} | "
                          f"position_amt={position_amt} | current_price={current_price}")
                
                conversation_id = self._get_conversation_id()
                
                sdk_response = binance_client.take_profit_trade(
                    symbol=symbol,
                    side=side_for_trade,
                    order_type='TAKE_PROFIT_MARKET',  # 使用TAKE_PROFIT_MARKET类型，只需要stop_price
                    stop_price=stop_price,
                    position_side=position_side,
                    quantity=position_amt,  # 添加quantity参数
                    model_id=model_uuid,
                    conversation_id=conversation_id,
                    trade_id=trade_id,
                    db=self.db
                )
                
                # 【调用后日志】记录接口返回内容
                logger.info(f"@API@ [Model {self.model_id}] [take_profit_trade] === 接口调用成功 ==="
                          f" | symbol={symbol} | response={sdk_response}")
            except Exception as sdk_err:
                logger.error(f"@API@ [Model {self.model_id}] [take_profit_trade] === 接口调用失败 ==="
                           f" | symbol={symbol} | error={sdk_err}", exc_info=True)
                # SDK调用失败不影响数据库记录，继续执行
        else:
            sdk_call_skipped, sdk_skip_reason = self._handle_sdk_client_error(symbol, 'take_profit_trade')
        
        # 计算预估手续费（止盈单可能不会立即成交，这里只是预估）
        trade_amount = position_amt * stop_price
        trade_fee = trade_amount * self.trade_fee_rate
        
        # 记录止盈单
        logger.info(f"TRADE: PENDING - Model {self.model_id} TAKE_PROFIT {symbol} position_side={position_side} position_amt={position_amt} stop_price={stop_price}")
        try:
            self.db.insert_rows(
                self.db.trades_table,
                [[trade_id, model_uuid, symbol.upper(), 'take_profit', position_amt, stop_price, position.get('leverage', 1), side_for_trade.lower(), 0, trade_fee, datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)]],
                ["id", "model_id", "future", "signal", "quantity", "price", "leverage", "side", "pnl", "fee", "timestamp"]
            )
        except Exception as db_err:
            logger.error(f"TRADE: Add trade failed (TAKE_PROFIT) model={self.model_id} symbol={symbol}: {db_err}")
            raise
        self._log_trade_record('take_profit', symbol, position_side, sdk_call_skipped, sdk_skip_reason)

        return {
            'symbol': symbol,
            'signal': 'take_profit',
            'position_amt': position_amt,
            'stop_price': stop_price,  # 在止盈场景下，stop_price就是止盈价格
            'position_side': position_side,
            'side': side_for_trade.lower(),
            'fee': trade_fee,
            'message': f'止盈单 {symbol}, 持仓方向: {position_side}, 止盈价格: ${stop_price:.4f}, 数量: {position_amt:.4f}'
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
        """
        解析杠杆倍数（优先使用AI决策中的杠杆，否则使用模型配置）
        
        Args:
            decision: AI决策字典，可能包含leverage字段
        
        Returns:
            int: 最终使用的杠杆倍数
        
        优先级：
        1. 如果模型配置的杠杆为0，则使用AI决策中的杠杆
        2. 否则使用模型配置的杠杆（忽略AI决策中的杠杆）
        
        Note:
            此方法确保杠杆倍数至少为1，避免无效配置
        """
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
