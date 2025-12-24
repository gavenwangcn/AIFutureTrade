"""
交易引擎 - AI交易决策执行的核心逻辑模块

本模块提供完整的AI交易执行流程，包括：
- 买入/卖出决策周期的执行
- 市场数据获取和处理
- AI决策的批量处理和并发执行
- 订单执行（开仓、平仓、止损、止盈）
- 账户信息管理和记录

主要功能：
1. 买入服务：execute_buy_cycle() - 从涨跌幅榜选择候选，调用AI决策并执行买入
2. 卖出服务：execute_sell_cycle() - 对持仓进行卖出/平仓决策并执行
3. 订单执行：支持开仓、平仓、止损、止盈等多种订单类型
4. 并发处理：使用多线程批量处理AI决策，提高执行效率

注意：
- 交易循环管理已移至 trade/app.py，不再在此模块中管理线程
- 买入和卖出循环在 trade/app.py 中分别独立运行
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import common.config as app_config
from trade.ai.prompt_defaults import DEFAULT_BUY_CONSTRAINTS, DEFAULT_SELL_CONSTRAINTS, PROMPT_JSON_OUTPUT_SUFFIX
from common.binance_futures import BinanceFuturesOrderClient
from common.database.database_model_prompts import ModelPromptsDatabase
from common.database.database_models import ModelsDatabase
from common.database.database_portfolios import PortfoliosDatabase
from common.database.database_conversations import ConversationsDatabase
from common.database.database_account_values import AccountValuesDatabase
from common.database.database_futures import FuturesDatabase
from common.database.database_account_asset import AccountAssetDatabase
from common.database.database_binance_trade_logs import BinanceTradeLogsDatabase

logger = logging.getLogger(__name__)

class TradingEngine:
    """
    交易引擎类 - 负责执行AI交易决策的完整流程
    
    每个模型实例对应一个TradingEngine，独立管理该模型的交易逻辑。
    支持买入和卖出两个独立的服务线程，以不同的周期执行交易决策。
    """
    
    def __init__(self, model_id: int, db, market_fetcher, trader, trade_fee_rate: float = 0.001,
                 buy_cycle_interval: int = 5, sell_cycle_interval: int = 5):
        """
        初始化交易引擎
        
        Args:
            model_id: 模型ID，用于标识和管理不同的交易模型
            db: 数据库实例，用于数据持久化
            market_fetcher: 市场数据获取器，用于获取实时价格和技术指标
            trader: 交易决策器，用于生成买入/卖出决策（可以是AITrader或StrategyTrader）
            trade_fee_rate: 交易费率，默认0.001（0.1%）
            buy_cycle_interval: 买入周期间隔（秒），默认5秒
            sell_cycle_interval: 卖出周期间隔（秒），默认5秒
        
        Note:
            - Binance订单客户端不在初始化时创建，改为每次使用时新建实例
            - 确保每次交易都使用最新的 model 表中的 api_key 和 api_secret
            - trader可以是AITrader或StrategyTrader的实例，都实现了Trader接口
        """
        self.model_id = model_id
        self.db = db
        self.market_fetcher = market_fetcher
        self.trader = trader
        self.trade_fee_rate = trade_fee_rate
        # 初始化 ModelPromptsDatabase、ModelsDatabase、PortfoliosDatabase、ConversationsDatabase、AccountValuesDatabase、FuturesDatabase、AccountAssetDatabase 和 BinanceTradeLogsDatabase 实例
        self.model_prompts_db = ModelPromptsDatabase(pool=db._pool if hasattr(db, '_pool') else None)
        self.models_db = ModelsDatabase(pool=db._pool if hasattr(db, '_pool') else None)
        self.portfolios_db = PortfoliosDatabase(pool=db._pool if hasattr(db, '_pool') else None)
        self.conversations_db = ConversationsDatabase(pool=db._pool if hasattr(db, '_pool') else None)
        self.account_values_db = AccountValuesDatabase(pool=db._pool if hasattr(db, '_pool') else None)
        self.futures_db = FuturesDatabase(pool=db._pool if hasattr(db, '_pool') else None)
        self.account_asset_db = AccountAssetDatabase(pool=db._pool if hasattr(db, '_pool') else None)
        self.binance_trade_logs_db = BinanceTradeLogsDatabase(pool=db._pool if hasattr(db, '_pool') else None)
        # 从数据库获取 max_positions（最大持仓数量），如果获取失败则使用默认值3
        try:
            model = self.models_db.get_model(model_id)
            self.max_positions = model.get('max_positions', 3) if model else 3
        except Exception as e:
            logger.warning(f"[TradingEngine] Failed to get max_positions for model {model_id}, using default 3: {e}")
            self.max_positions = 3
        # 配置执行周期（秒）（保留用于兼容性，实际循环管理在trade/app.py）
        self.buy_cycle_interval = buy_cycle_interval
        self.sell_cycle_interval = sell_cycle_interval
        # 全局交易锁，用于协调买入和卖出决策执行之间的并发操作
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
        logger.debug(f"[Model {self.model_id}] [卖出服务] ========== 开始执行卖出决策周期 ==========")
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
            portfolio = self._get_portfolio(self.model_id, current_prices)
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
                
                # 调用批次卖出决策处理方法（与买入决策使用相同的批次执行逻辑）
                self._make_batch_sell_decisions(
                    positions,
                    portfolio,
                    account_info,
                    prompt_templates['sell'],
                    market_state,
                    executions,
                    conversation_prompts,
                    current_prices
                )
            else:
                logger.debug(f"[Model {self.model_id}] [卖出服务] [阶段2] 无持仓，跳过卖出决策处理")
            
            logger.debug(f"[Model {self.model_id}] [卖出服务] [阶段2] 卖出/平仓决策处理完成")

            # ========== 阶段3: 账户价值快照记录说明 ==========
            # 注意：账户价值快照现在在每次交易执行时立即记录（在 _execute_close, _execute_stop_loss, _execute_take_profit 等方法中）
            # 不再在批次处理完成后统一记录，确保每次交易都有对应的账户价值快照
            logger.debug(f"[Model {self.model_id}] [卖出服务] [阶段3] 账户价值快照已在每次交易时记录，无需批次记录")
            
            # ========== 阶段4: 同步model_futures表数据 ==========
            logger.debug(f"[Model {self.model_id}] [卖出服务] [阶段4] 同步model_futures表数据")
            self._sync_model_futures()
            
            # ========== 交易周期完成 ==========
            cycle_end_time = datetime.now(timezone(timedelta(hours=8)))
            cycle_duration = (cycle_end_time - cycle_start_time).total_seconds()
            logger.debug(f"[Model {self.model_id}] [卖出服务] ========== 卖出决策周期执行完成 ==========")
            logger.debug(f"[Model {self.model_id}] [卖出服务] 执行统计: "
                        f"总耗时={cycle_duration:.2f}秒, "
                        f"执行操作数={len(executions)}, "
                        f"对话类型={conversation_prompts}")
            
            # 获取最终持仓信息
            updated_portfolio = self._get_portfolio(self.model_id, current_prices)
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
        - 优化了杠杆信息获取，避免重复查询数据库
        
        返回：
            Dict: {
                'success': bool,  # 是否成功
                'executions': List,  # 执行结果列表
                'portfolio': Dict,  # 最终持仓信息
                'conversations': List,  # 对话类型列表 ['buy']
                'error': str  # 错误信息（如果失败）
            }
        """
        logger.debug(f"[Model {self.model_id}] [买入服务] ========== 开始执行买入决策周期 ==========")
        cycle_start_time = datetime.now(timezone(timedelta(hours=8)))
        
        try:
            # 检查模型是否存在
            model = self.models_db.get_model(self.model_id)
            if not model:
                logger.warning(f"[Model {self.model_id}] [买入服务] 模型不存在，跳过买入决策周期")
                return {
                    'success': False,
                    'executions': [],
                    'portfolio': {},
                    'conversations': [],
                    'error': f"Model {self.model_id} not found"
                }
            
            # 记录模型的trade_type信息
            trade_type = model.get('trade_type', 'ai')
            logger.debug(f"[Model {self.model_id}] [买入服务] 模型trade_type: {trade_type}")
            logger.debug(f"[Model {self.model_id}] [买入服务] trader类型: {type(self.trader).__name__}")
            
            # 缓存模型的杠杆配置，避免后续重复查询数据库
            model_leverage = model.get('leverage', 10)
            try:
                model_leverage = int(model_leverage)
            except (TypeError, ValueError):
                model_leverage = 10
            # 确保缓存的杠杆值至少为1
            self.current_model_leverage = max(1, model_leverage)
            logger.debug(f"[Model {self.model_id}] [买入服务] 已缓存模型杠杆配置: {self.current_model_leverage}")
            
            # 缓存模型的max_positions配置，避免后续重复查询数据库
            current_max_positions = model.get('max_positions', self.max_positions)
            try:
                current_max_positions = int(current_max_positions) if current_max_positions is not None else self.max_positions
            except (TypeError, ValueError):
                current_max_positions = self.max_positions
            # 更新实例变量，供后续使用
            self.max_positions = current_max_positions
            logger.debug(f"[Model {self.model_id}] [买入服务] 已缓存模型max_positions配置: {self.max_positions}")
            
            # ========== 阶段1: 初始化数据准备 ==========
            logger.debug(f"[Model {self.model_id}] [买入服务] [阶段1] 开始初始化数据准备")
            
            # 获取模型配置（包含symbol_source）
            symbol_source = model.get('symbol_source', 'leaderboard')
            logger.debug(f"[Model {self.model_id}] [买入服务] [阶段1.1] 模型symbol_source配置: {symbol_source}")
            
            # 获取当前持仓信息（先使用空价格映射，后续会更新）
            portfolio = self._get_portfolio(self.model_id, {})
            current_positions_count = len(portfolio.get('positions', []) or [])
            logger.debug(f"[Model {self.model_id}] [买入服务] [阶段1.2] 持仓信息获取完成: "
                        f"总价值=${portfolio.get('total_value', 0):.2f}, "
                        f"现金=${portfolio.get('cash', 0):.2f}, "
                        f"持仓数={current_positions_count}")
            
            # 判断持仓数量是否已达到或超过max_positions限制
            if current_positions_count >= self.max_positions:
                logger.debug(f"[Model {self.model_id}] [买入服务] [阶段1.2] 持仓数量已达到上限: "
                            f"当前持仓数={current_positions_count}, "
                            f"最大持仓数={self.max_positions}, "
                            f"跳过后续买入决策处理，等待下一次循环")
                # 返回成功结果，但不执行买入决策
                cycle_end_time = datetime.now(timezone(timedelta(hours=8)))
                cycle_duration = (cycle_end_time - cycle_start_time).total_seconds()
                logger.debug(f"[Model {self.model_id}] [买入服务] ========== 买入决策周期执行完成（已跳过,已最大数量持仓，等待下一次循环） ==========")
                logger.debug(f"[Model {self.model_id}] [买入服务] 执行统计: "
                            f"总耗时={cycle_duration:.2f}秒, "
                            f"执行操作数=0, "
                            f"跳过原因=持仓数量已达上限")
                return {
                    'success': True,
                    'executions': [],
                    'portfolio': portfolio,
                    'conversations': [],
                    'skipped': True,
                    'skip_reason': f'持仓数量已达上限: {current_positions_count}/{self.max_positions}'
                }
            
            # 构建账户信息（用于AI决策）
            account_info = self._build_account_info(portfolio)
            logger.debug(f"[Model {self.model_id}] [买入服务] [阶段1.3] 账户信息构建完成: "
                        f"初始资金=${account_info.get('initial_capital', 0):.2f}, "
                        f"总收益率={account_info.get('total_return', 0):.2f}%")
            
            # 获取提示词模板（仅买入约束）
            prompt_templates = self._get_prompt_templates()
            logger.debug(f"[Model {self.model_id}] [买入服务] [阶段1.4] 买入提示词模板获取完成")
            
            # 初始化执行结果和对话记录
            executions = []
            conversation_prompts = []
            logger.debug(f"[Model {self.model_id}] [买入服务] [阶段1] 初始化完成")

            # ========== 阶段2: 买入决策处理（分批多线程） ==========
            logger.debug(f"[Model {self.model_id}] [买入服务] [阶段2] 开始处理买入决策")
            
            # 步骤1: 根据symbol_source获取候选symbol并构建市场状态（仅获取价格，不获取技术指标，指标将在批次处理时按需获取）
            logger.debug(f"[Model {self.model_id}] [买入服务] [阶段2.1] 根据symbol_source获取候选symbol并构建市场状态（仅价格）...")
            buy_candidates, market_state = self._select_buy_candidates(portfolio, symbol_source, include_indicators=False)
            logger.debug(f"[Model {self.model_id}] [买入服务] [阶段2.1] 候选symbol选择完成: "
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
                portfolio = self._get_portfolio(self.model_id, current_prices)
                logger.debug(f"[Model {self.model_id}] [买入服务] [阶段2.3] 持仓信息已更新: "
                            f"总价值=${portfolio.get('total_value', 0):.2f}, "
                            f"现金=${portfolio.get('cash', 0):.2f}")
                
                # 构建约束条件（用于AI决策）
                # 使用已缓存的max_positions，避免重复查询数据库
                constraints = {
                    'max_positions': self.max_positions,
                    'occupied': len(portfolio.get('positions', []) or []),
                    'available_cash': portfolio.get('cash', 0)
                }
                logger.debug(f"[Model {self.model_id}] [买入服务] [阶段2.4] 约束条件构建完成: "
                            f"最大持仓数={constraints['max_positions']}, "
                            f"已占用={constraints['occupied']}, "
                            f"可用现金=${constraints['available_cash']:.2f}")
                
                # 分批处理买入决策（顺序执行）
                logger.debug(f"[Model {self.model_id}] [买入服务] [阶段2.5] 开始分批处理买入决策（顺序执行）......")
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
                logger.debug(f"[Model {self.model_id}] [买入服务] [阶段2.5] 分批买入决策处理完成")
            else:
                logger.debug(f"[Model {self.model_id}] [买入服务] [阶段2] 无买入候选，跳过买入决策处理")
                # 即使没有候选，也需要更新current_prices用于后续记录账户价值
                current_prices = {}
            
            logger.debug(f"[Model {self.model_id}] [买入服务] [阶段2] 买入决策处理完成")

            # ========== 阶段3: 账户价值快照记录说明 ==========
            # 注意：账户价值快照现在在每次交易执行时立即记录（在 _execute_buy, _execute_sell, _execute_close 等方法中）
            # 不再在批次处理完成后统一记录，确保每次交易都有对应的账户价值快照
            logger.debug(f"[Model {self.model_id}] [买入服务] [阶段3] 账户价值快照已在每次交易时记录，无需批次记录")
            
            # ========== 阶段4: 同步model_futures表数据 ==========
            logger.debug(f"[Model {self.model_id}] [买入服务] [阶段4] 同步model_futures表数据")
            self._sync_model_futures()
            
            # ========== 交易周期完成 ==========
            cycle_end_time = datetime.now(timezone(timedelta(hours=8)))
            cycle_duration = (cycle_end_time - cycle_start_time).total_seconds()
            logger.debug(f"[Model {self.model_id}] [买入服务] ========== 买入决策周期执行完成 ==========")
            logger.debug(f"[Model {self.model_id}] [买入服务] 执行统计: "
                        f"总耗时={cycle_duration:.2f}秒, "
                        f"执行操作数={len(executions)}, "
                        f"对话类型={conversation_prompts}")
            
            # 清理缓存的杠杆配置
            if hasattr(self, 'current_model_leverage'):
                delattr(self, 'current_model_leverage')
            
            # 获取最终持仓信息
            updated_portfolio = self._get_portfolio(self.model_id, current_prices)
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
            

    # ============ 工具方法：公共逻辑提取 ============
    
    def _check_model_exists(self) -> Optional[Dict]:
        """
        检查模型是否存在
        
        Returns:
            模型字典，如果不存在则返回None
        """
        try:
            model = self.models_db.get_model(self.model_id)
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
        3. signal是有效的交易信号（buy_to_long, buy_to_short, sell_to_long, sell_to_short, close_position, stop_loss, take_profit）
        
        Args:
            executions: 执行结果列表
            
        Returns:
            bool: 如果有实际交易返回True，否则返回False
        """
        logger.info(f"[Model {self.model_id}] [交易检测] ========== 开始检查是否有实际交易 ==========")
        logger.info(f"[Model {self.model_id}] [交易检测] executions列表长度: {len(executions) if executions else 0}")
        
        if not executions:
            logger.info(f"[Model {self.model_id}] [交易检测] executions列表为空，返回False")
            return False
        
        valid_signals = {'buy_to_long', 'buy_to_short', 'sell_to_long', 'sell_to_short', 'close_position', 'stop_loss', 'take_profit'}
        
        logger.info(f"[Model {self.model_id}] [交易检测] 开始检查 {len(executions)} 个执行结果")
        logger.info(f"[Model {self.model_id}] [交易检测] 有效信号列表: {valid_signals}")
        
        for idx, result in enumerate(executions):
            logger.info(f"[Model {self.model_id}] [交易检测] 检查结果 {idx+1}/{len(executions)}:")
            logger.info(f"[Model {self.model_id}] [交易检测]   完整结果: {result}")
            logger.info(f"[Model {self.model_id}] [交易检测]   symbol: {result.get('symbol', 'N/A')}")
            logger.info(f"[Model {self.model_id}] [交易检测]   signal: {result.get('signal', 'N/A')}")
            logger.info(f"[Model {self.model_id}] [交易检测]   error: {result.get('error', '无')}")
            
            # 跳过有错误的执行结果
            if result.get('error'):
                logger.info(f"[Model {self.model_id}] [交易检测]   结果 {idx+1} 有错误，跳过: {result.get('error')}")
                continue
            
            # 检查是否有有效的signal
            signal = result.get('signal', '').lower()
            logger.info(f"[Model {self.model_id}] [交易检测]   规范化后的signal: '{signal}'")
            logger.info(f"[Model {self.model_id}] [交易检测]   signal是否在有效列表中: {signal in valid_signals}")
            
            if signal in valid_signals:
                logger.info(f"[Model {self.model_id}] [交易检测] ========== 检测到实际交易 ==========")
                logger.info(f"[Model {self.model_id}] [交易检测] 实际交易详情: signal={signal}, symbol={result.get('symbol', 'N/A')}")
                return True
            else:
                logger.info(f"[Model {self.model_id}] [交易检测]   结果 {idx+1} 的signal不在有效列表中")
        
        logger.info(f"[Model {self.model_id}] [交易检测] ========== 未检测到实际交易 ==========")
        logger.info(f"[Model {self.model_id}] [交易检测] 所有执行结果检查完毕，未找到有效交易信号")
        return False
    
    def _record_account_snapshot(self, current_prices: Dict) -> None:
        """
        记录账户价值快照（公共方法）
        
        Args:
            current_prices: 当前价格映射
        """
        try:
            logger.info(f"[Model {self.model_id}] [账户价值快照] 开始记录账户价值快照...")
            
            updated_portfolio = self._get_portfolio(self.model_id, current_prices)
            balance = updated_portfolio.get('total_value', 0)
            available_balance = updated_portfolio.get('cash', 0)
            cross_wallet_balance = updated_portfolio.get('positions_value', 0)
            
            logger.info(f"[Model {self.model_id}] [账户价值快照] 账户价值: "
                       f"总余额(balance)=${balance:.2f}, "
                       f"可用余额(available_balance)=${available_balance:.2f}, "
                       f"全仓余额(cross_wallet_balance)=${cross_wallet_balance:.2f}")
            
            model = self.models_db.get_model(self.model_id)
            account_alias = model.get('account_alias', '') if model else ''
            logger.debug(f"[Model {self.model_id}] [账户价值快照] account_alias={account_alias}")
            
            # 获取模型ID映射和账户价值历史表名
            model_mapping = self.models_db._get_model_id_mapping()
            from common.database.database_init import ACCOUNT_VALUE_HISTORYS_TABLE
            
            logger.info(f"[Model {self.model_id}] [账户价值快照] 准备调用record_account_value方法...")
            logger.info(f"[Model {self.model_id}] [账户价值快照] 调用参数: model_id={self.model_id}, balance=${balance:.2f}, "
                       f"available_balance=${available_balance:.2f}, cross_wallet_balance=${cross_wallet_balance:.2f}, "
                       f"account_alias={account_alias}")
            self.account_values_db.record_account_value(
                self.model_id,
                balance=balance,
                available_balance=available_balance,
                cross_wallet_balance=cross_wallet_balance,
                account_alias=account_alias,
                cross_un_pnl=0.0,
                model_id_mapping=model_mapping,
                get_model_func=self.models_db.get_model,
                account_value_historys_table=ACCOUNT_VALUE_HISTORYS_TABLE
            )
            logger.info(f"[Model {self.model_id}] [账户价值快照] record_account_value方法调用完成，账户价值快照记录完成")
        except Exception as e:
            logger.error(f"[Model {self.model_id}] [账户价值快照] 记录账户价值快照失败: {e}", exc_info=True)
            # 不抛出异常，避免影响主流程，但记录详细错误信息
            raise
    
    def _sync_model_futures(self) -> None:
        """同步model_futures表数据"""
        sync_success = self.futures_db.sync_model_futures_from_portfolio(self.model_id)
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
        model_mapping = self.models_db._get_model_id_mapping()
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
            model = self.models_db.get_model(self.model_id)
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
            signal: 交易信号（如 'buy_to_long', 'close_position'）
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
        - _execute_buy: 调用market_trade（市场价格买入）
        - _execute_sell: 调用market_trade（市场价格卖出/平仓）
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
            model = self.models_db.get_model(self.model_id)
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
        # 获取模型ID映射
        model_mapping = self.models_db._get_model_id_mapping()
        symbols = self.portfolios_db.get_model_held_symbols(self.model_id, model_mapping)
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
            # 获取K线数据（不计算指标）
            # 注意：include_indicators 参数已废弃，但保留以兼容旧代码
            # 现在只获取klines，指标由ai_trader内部按需计算
            query_symbol = original_symbol.upper()
            if not query_symbol.endswith('USDT'):
                query_symbol = f"{query_symbol}USDT"
            merged_data = self._merge_timeframe_data(query_symbol)
            # 将合并后的数据格式调整为与原有格式兼容（只包含klines）
            if query_symbol in merged_data:
                market_state[original_symbol]['indicators'] = {'timeframes': merged_data[query_symbol]}
            else:
                market_state[original_symbol]['indicators'] = {'timeframes': {}}

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
        合并7个时间周期的K线数据（不计算指标）
        
        Args:
            symbol: 交易对符号（如 'BTC' 或 'BTCUSDT'）
            
        Returns:
            Dict: 合并后的数据格式 {symbol: {1m: {klines: [...]}, 5m: {klines: [...]}, ...}}
            只包含klines数据，不包含indicators
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
                    # 只提取klines数据，不包含indicators
                    klines = data.get('klines', [])
                    if klines:
                        merged_data[formatted_symbol][timeframe] = {'klines': klines}
                    else:
                        errors.append(f"{timeframe}: K线数据为空")
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
        model = self.models_db.get_model(self.model_id)
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
            # 获取模型ID映射
            model_mapping = self.models_db._get_model_id_mapping()
            account_data = self.account_values_db.get_latest_account_value(self.model_id, model_mapping)
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
                account_data = self.account_asset_db.get_account_asset(account_alias)
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

    # ============ 投资组合管理辅助方法 ============
    # 封装对 PortfoliosDatabase 的调用
    
    def _get_portfolio(self, model_id: int, current_prices: Dict = None) -> Dict:
        """
        获取投资组合信息（委托给 PortfoliosDatabase）
        """
        try:
            model_mapping = self.models_db._get_model_id_mapping() if self.models_db else None
            return self.portfolios_db.get_portfolio(model_id, current_prices, model_mapping, 
                                                   self.models_db.get_model, self.db.trades_table)
        except Exception as e:
            logger.error(f"[TradingEngine] Failed to get portfolio for model {model_id}: {e}")
            raise
    
    def _update_position(self, model_id: int, symbol: str, position_amt: float,
                        avg_price: float, leverage: int = 1, position_side: str = 'LONG',
                        initial_margin: float = 0.0, unrealized_profit: float = 0.0):
        """
        更新持仓信息（委托给 PortfoliosDatabase）
        """
        try:
            model_mapping = self.models_db._get_model_id_mapping() if self.models_db else None
            self.portfolios_db.update_position(model_id, symbol, position_amt, avg_price, leverage,
                                            position_side, initial_margin, unrealized_profit, model_mapping)
        except Exception as e:
            logger.error(f"[TradingEngine] Failed to update position: {e}")
            raise
    
    def _close_position(self, model_id: int, symbol: str, position_side: str = 'LONG'):
        """
        平仓（委托给 PortfoliosDatabase）
        """
        try:
            model_mapping = self.models_db._get_model_id_mapping() if self.models_db else None
            self.portfolios_db.close_position(model_id, symbol, position_side, model_mapping)
        except Exception as e:
            logger.error(f"[TradingEngine] Failed to close position: {e}")
            raise
    
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
        # 使用 ModelPromptsDatabase 获取提示词配置
        model_mapping = self.models_db._get_model_id_mapping() if self.models_db else None
        prompt_config = self.model_prompts_db.get_model_prompt(self.model_id, model_mapping) or {}
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

    def _record_ai_conversation(self, payload: Dict, conversation_type: Optional[str] = None) -> Optional[str]:
        """
        记录AI对话到数据库
        
        Args:
            payload: AI决策返回的完整数据，包含：
                - prompt: 发送给AI的提示词
                - raw_response: AI的原始响应
                - cot_trace: 思维链追踪（如果有）
                - decisions: AI的决策结果（如果raw_response不是字符串）
                - tokens: token使用数量（如果有）
            conversation_type: 对话类型，'buy'（买入决策）或 'sell'（卖出决策），可选
        
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
        # 获取模型ID映射
        model_mapping = self.models_db._get_model_id_mapping()
        conversation_id = self.conversations_db.add_conversation(
            self.model_id,
            user_prompt='',
            ai_response=raw_response,
            cot_trace=cot_trace,
            tokens=tokens,
            conversation_type=conversation_type,
            model_id_mapping=model_mapping
        )
        # 保存 conversation_id 到实例变量（线程安全）
        if conversation_id:
            with self.current_conversation_id_lock:
                self.current_conversation_id = conversation_id
        return conversation_id

    # ============ 批量决策处理方法 ============
    # 使用顺序执行批量处理AI决策
    
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
        分批处理买入决策（顺序执行，按单元分组统一处理）
        
        流程：
        1. 从模型配置获取批次大小、批次间隔、分组大小
        2. 将候选列表分批
        3. 顺序执行各批次，每N个批次（N=模型配置的buy_batch_execution_group_size）作为一个单元
        4. 每个批次只获取AI决策，不立即执行
        5. 每个单元的所有批次完成后，统一处理这些批次的决策（插入数据库和调用SDK）
        6. 单元之间有间隔（模型配置的buy_batch_execution_interval）
        7. 顺序执行，不需要锁
        """
        if not candidates:
            logger.debug(f"[Model {self.model_id}] [分批买入] 无候选合约，跳过处理")
            return

        # 从模型配置获取批次大小、批次间隔、分组大小（买入配置）
        model = self.models_db.get_model(self.model_id)
        if model:
            batch_size = model.get('buy_batch_size', 1)
            batch_interval = model.get('buy_batch_execution_interval', 60)
            group_size = model.get('buy_batch_execution_group_size', 1)
        else:
            # 如果模型不存在，使用默认值
            batch_size = 1
            batch_interval = 60
            group_size = 1
        batch_size = max(1, int(batch_size))
        batch_interval = max(0, int(batch_interval))
        group_size = max(1, int(group_size))
        
        # 强制使用顺序执行，不使用多线程
        unit_size = group_size
        
        logger.debug(f"[Model {self.model_id}] [分批买入] 配置参数: 批次大小={batch_size}, 批次间隔={batch_interval}秒, 执行方式=顺序执行, 单元大小={unit_size}")

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

        logger.debug(f"[Model {self.model_id}] 开始分批处理买入决策: 共 {len(candidates)} 个候选, 分为 {len(batches)} 批, 每批最多 {batch_size} 个, 执行方式=顺序执行, 单元大小={unit_size}, 单元间隔={batch_interval}秒")

        has_buy_decision = False
        batch_start_time = datetime.now(timezone(timedelta(hours=8)))
        
        # 使用顺序执行（不使用多线程）
        logger.info(f"[Model {self.model_id}] [分批买入] 使用顺序执行，单元大小={unit_size}")
        
        # 存储所有批次的决策结果（用于分组处理）
        all_batch_decisions = []
        
        # 顺序执行各批次
        for batch_idx, batch in enumerate(batches):
            batch_num = batch_idx + 1
            batch_symbols = [c.get('symbol', 'N/A') for c in batch]
            
            logger.debug(f"[Model {self.model_id}] [分批买入] 开始处理批次 {batch_num}/{len(batches)}: symbols={batch_symbols}")
            
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
            
            # 调用决策（不立即执行）
            try:
                payload = self._process_batch_decision_only(
                    batch,
                    portfolio,
                    account_info,
                    constraints,
                    constraints_text,
                    batch_market_state,
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
                    logger.debug(f"[Model {self.model_id}] [分批买入] 批次 {batch_num}/{len(batches)} 跳过或无决策")
                    
            except Exception as exc:
                logger.error(f"[Model {self.model_id}] [分批买入] 批次 {batch_num} 处理异常: {exc}")
                import traceback
                logger.debug(f"[Model {self.model_id}] [分批买入] 异常堆栈:\n{traceback.format_exc()}")
            
            # 每N个批次完成后，统一处理这些批次的决策
            if batch_num % unit_size == 0 or batch_num == len(batches):
                group_start = ((batch_num - 1) // unit_size) * unit_size
                group_end = batch_num
                group_decisions = all_batch_decisions[group_start:group_end]
                
                logger.debug(f"[Model {self.model_id}] [分批买入] 批次组 {group_start+1}-{group_end} 完成，开始统一处理决策（插入数据库和调用SDK）...")
                
                # 统一处理这组批次的决策（顺序执行，不需要锁）
                try:
                    self._execute_batch_group_decisions_sequential(
                        group_decisions,
                        portfolio,
                        account_info,
                        constraints,
                        current_prices,
                        executions
                    )
                    logger.debug(f"[Model {self.model_id}] [分批买入] 批次组 {group_start+1}-{group_end} 处理完成")
                except Exception as e:
                    logger.error(f"[Model {self.model_id}] [分批买入] 批次组 {group_start+1}-{group_end} 处理异常: {e}", exc_info=True)
                    logger.error(f"[Model {self.model_id}] [分批买入] 批次组处理异常，但继续执行后续流程，executions当前数量: {len(executions)}")
                    # 即使批次组处理失败，也继续执行，确保阶段3能够检查executions
            
            # 如果不是最后一个批次，等待间隔时间
            if batch_num < len(batches) and batch_interval > 0:
                logger.debug(f"[Model {self.model_id}] [分批买入] 批次 {batch_num} 完成，等待 {batch_interval} 秒后处理下一批次...")
                time.sleep(batch_interval)

        batch_end_time = datetime.now(timezone(timedelta(hours=8)))
        batch_duration = (batch_end_time - batch_start_time).total_seconds()
        logger.debug(f"[Model {self.model_id}] [分批买入] 所有批次处理完成: "
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
        batch_num: int,
        total_batches: int
    ) -> Dict:
        """
        处理单个批次：只获取决策，不执行
        
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
            
            ai_call_start = datetime.now(timezone(timedelta(hours=8)))
            buy_payload = self.trader.make_buy_decision(
                valid_candidates,  # 只传递有效的candidates
                portfolio,
                account_info,
                market_state,  # 统一使用market_state，其中已包含source信息
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
    
    def _execute_batch_group_decisions_sequential(
        self,
        group_decisions: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        constraints: Dict,
        current_prices: Dict[str, float],
        executions: List
    ):
        """
        统一处理一组批次的决策（插入数据库和调用SDK）- 顺序执行版本
        
        流程：
        1. 合并所有批次的决策
        2. 记录所有批次的AI对话到数据库
        3. 顺序执行所有决策（不使用锁，因为已经是顺序执行）
        4. 更新portfolio和constraints
        """
        try:
            if not group_decisions:
                logger.debug(f"[Model {self.model_id}] [批次组处理] 无决策数据，跳过")
                return
            
            logger.debug(f"[Model {self.model_id}] [批次组处理] ========== 开始处理批次组决策 ==========")
            logger.debug(f"[Model {self.model_id}] [批次组处理] 批次数量: {len(group_decisions)}")
            
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
                logger.debug(f"[Model {self.model_id}] [批次组处理] 无有效决策，跳过执行")
                return
            
            logger.debug(f"[Model {self.model_id}] [批次组处理] 合并完成: 决策数={len(all_decisions)}, 对话数={len(all_payloads)}")
            
            # ========== 步骤1: 记录所有批次的AI对话到数据库 ==========
            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤1] 记录AI对话到数据库...")
            for payload in all_payloads:
                try:
                    self._record_ai_conversation(payload, conversation_type='buy')
                except Exception as e:
                    logger.error(f"[Model {self.model_id}] [批次组处理] 记录AI对话失败: {e}")
            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤1] AI对话已记录")
            
            # ========== 步骤2: 顺序执行所有决策 ==========
            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2] 开始顺序执行决策...")
            
            # 获取最新持仓状态
            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.1] 获取最新持仓状态...")
            latest_portfolio = self._get_portfolio(self.model_id, current_prices)
            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.1] 最新持仓状态: "
                        f"总价值=${latest_portfolio.get('total_value', 0):.2f}, "
                        f"现金=${latest_portfolio.get('cash', 0):.2f}, "
                        f"持仓数={len(latest_portfolio.get('positions', []) or [])}")
            
            # 执行所有决策（顺序执行）
            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.2] 开始执行决策...")
            execution_start = datetime.now(timezone(timedelta(hours=8)))
            batch_results = self._execute_decisions(
                all_decisions,
                all_market_states,
                latest_portfolio
            )
            execution_duration = (datetime.now(timezone(timedelta(hours=8))) - execution_start).total_seconds()
            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.2] 决策执行完成: 耗时={execution_duration:.2f}秒, 结果数={len(batch_results)}")
            
            # 记录每个执行结果
            for idx, result in enumerate(batch_results):
                logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.2.{idx+1}] 执行结果: "
                            f"合约={result.get('symbol', 'N/A')}, "
                            f"信号={result.get('signal')}, "
                            f"数量={result.get('position_amt', 0)}, "
                            f"价格=${result.get('price', 0):.4f}, "
                            f"错误={result.get('error', '无')}")
            
            # 添加到执行结果列表
            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.3] 添加执行结果到列表（当前总数: {len(executions)}）...")
            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.3] batch_results详情: 数量={len(batch_results)}")
            for idx, result in enumerate(batch_results):
                logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.3] batch_results[{idx}]: symbol={result.get('symbol')}, signal={result.get('signal')}, error={result.get('error', '无')}")
            executions.extend(batch_results)
            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.3] 执行结果已添加（新总数: {len(executions)}）")
            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.3] executions列表详情:")
            for idx, exec_result in enumerate(executions):
                logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤2.3] executions[{idx}]: symbol={exec_result.get('symbol')}, signal={exec_result.get('signal')}, error={exec_result.get('error', '无')}")
            
            logger.debug(f"[Model {self.model_id}] [批次组处理] 执行完成, 决策数: {len(all_decisions)}, 执行结果: {len(batch_results)}")
            
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
            
            logger.debug(f"[Model {self.model_id}] [批次组处理] [步骤3] 状态更新完成")
            logger.debug(f"[Model {self.model_id}] [批次组处理] ========== 批次组处理完成 ==========")
            
        except Exception as e:
            logger.error(f"[Model {self.model_id}] [批次组处理] ========== 批次组处理异常 ==========")
            logger.error(f"[Model {self.model_id}] [批次组处理] 异常信息: {e}", exc_info=True)
            logger.error(f"[Model {self.model_id}] [批次组处理] 即使发生异常，executions列表当前状态: {len(executions)} 条记录")
            # 即使发生异常，也不抛出，让主流程继续执行，确保阶段3的账户价值快照检查能够执行
            # 这样即使批次组处理失败，已经添加到executions的结果仍然可以被检查

    def _make_batch_sell_decisions(
        self,
        positions: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        constraints_text: str,
        market_state: Dict,
        executions: List,
        conversation_prompts: List,
        current_prices: Dict[str, float]
    ):
        """
        分批处理卖出决策（与买入决策使用相同的批次执行逻辑）
        
        流程：
        1. 从模型配置获取批次大小、批次间隔、分组大小、线程数
        2. 将持仓列表分批
        3. 如果线程数>1：使用多线程并发执行，每N个批次（N=线程数）作为一个单元
        4. 如果线程数=1：串行执行，每N个批次（N=模型配置的sell_batch_execution_group_size）作为一个单元
        5. 每个批次只获取AI决策，不立即执行
        6. 每个单元的所有批次完成后，统一处理这些批次的决策（插入数据库和调用SDK）
        7. 单元之间有间隔（模型配置的sell_batch_execution_interval）
        8. 使用锁保证线程安全
        """
        if not positions:
            logger.debug(f"[Model {self.model_id}] [分批卖出] 无持仓，跳过处理")
            return

        # 从模型配置获取批次大小、批次间隔、分组大小（卖出配置）
        model = self.models_db.get_model(self.model_id)
        if model:
            batch_size = model.get('sell_batch_size', 1)
            batch_interval = model.get('sell_batch_execution_interval', 60)
            group_size = model.get('sell_batch_execution_group_size', 1)
        else:
            # 如果模型不存在，使用默认值
            batch_size = 1
            batch_interval = 60
            group_size = 1
        batch_size = max(1, int(batch_size))
        batch_interval = max(0, int(batch_interval))
        group_size = max(1, int(group_size))
        
        # 强制使用顺序执行，不使用多线程
        unit_size = group_size
        
        logger.debug(f"[Model {self.model_id}] [分批卖出] 配置参数: 批次大小={batch_size}, 批次间隔={batch_interval}秒, 执行方式=顺序执行, 单元大小={unit_size}")

        # 将持仓列表分批
        batches = []
        for i in range(0, len(positions), batch_size):
            batches.append(positions[i:i + batch_size])
        logger.debug(f"[Model {self.model_id}] [分批卖出] 持仓列表分批完成: "
                    f"总持仓数={len(positions)}, "
                    f"批次数={len(batches)}, "
                    f"每批大小={batch_size}")

        if not batches:
            logger.debug(f"[Model {self.model_id}] [分批卖出] 批次列表为空，跳过处理")
            return

        logger.debug(f"[Model {self.model_id}] 开始分批处理卖出决策: 共 {len(positions)} 个持仓, 分为 {len(batches)} 批, 每批最多 {batch_size} 个, 执行方式=顺序执行, 单元大小={unit_size}, 单元间隔={batch_interval}秒")

        has_sell_decision = False
        batch_start_time = datetime.now(timezone(timedelta(hours=8)))
        
        # 使用顺序执行（不使用多线程）
        logger.info(f"[Model {self.model_id}] [分批卖出] 使用顺序执行，单元大小={unit_size}")
        
        # 存储所有批次的决策结果（用于分组处理）
        all_batch_decisions = []
        
        # 顺序执行各批次
        for batch_idx, batch in enumerate(batches):
            batch_num = batch_idx + 1
            batch_symbols = [pos.get('symbol', 'N/A') for pos in batch]
            
            logger.debug(f"[Model {self.model_id}] [分批卖出] 开始处理批次 {batch_num}/{len(batches)}: symbols={batch_symbols}")
            
            # 为当前批次创建只包含对应symbol的market_state子集
            batch_market_state = {}
            for symbol in batch_symbols:
                if symbol != 'N/A':
                    symbol_upper = symbol.upper()
                    if symbol_upper in market_state:
                        batch_market_state[symbol_upper] = market_state[symbol_upper].copy()
                        
                        try:
                            logger.debug(f"[Model {self.model_id}] [分批卖出] 批次 {batch_num} 正在获取 {symbol_upper} 的技术指标...")
                            merged_data = self._merge_timeframe_data(symbol_upper)
                            timeframes_data = merged_data.get(symbol_upper, {}) if merged_data else {}
                            
                            if timeframes_data:
                                batch_market_state[symbol_upper]['indicators'] = {'timeframes': timeframes_data}
                            else:
                                batch_market_state[symbol_upper]['indicators'] = {'timeframes': {}}
                        except Exception as e:
                            logger.error(f"[Model {self.model_id}] [分批卖出] 批次 {batch_num} 获取 {symbol_upper} 技术指标失败: {e}")
                            batch_market_state[symbol_upper]['indicators'] = {'timeframes': {}}
            
            # 调用AI决策（不立即执行）
            try:
                payload = self._process_sell_batch_decision_only(
                    batch,
                    portfolio,
                    account_info,
                    constraints_text,
                    batch_market_state,
                    batch_num,
                    len(batches)
                )
                
                # 存储决策结果
                all_batch_decisions.append({
                    'batch_num': batch_num,
                    'payload': payload,
                    'batch_market_state': batch_market_state,
                    'batch_positions': batch
                })
                
                if not payload.get('skipped') and payload.get('decisions'):
                    # 检查是否有实际的卖出决策（排除 hold 操作）
                    decisions = payload.get('decisions') or {}
                    has_actual_decision = False
                    for symbol, decision in decisions.items():
                        signal = decision.get('signal', '').lower()
                        if signal in ['close_position', 'stop_loss', 'take_profit']:
                            has_actual_decision = True
                            has_sell_decision = True
                            break
                    
                    if has_actual_decision:
                        logger.info(f"[Model {self.model_id}] [分批卖出] 批次 {batch_num}/{len(batches)} AI决策完成: 决策数={len(decisions)}, 有实际执行={has_actual_decision}")
                    else:
                        logger.debug(f"[Model {self.model_id}] [分批卖出] 批次 {batch_num}/{len(batches)} AI决策完成: 决策数={len(decisions)}, 但无实际执行（仅有hold）")
                else:
                    logger.debug(f"[Model {self.model_id}] [分批卖出] 批次 {batch_num}/{len(batches)} 跳过或无决策")
                    
            except Exception as exc:
                logger.error(f"[Model {self.model_id}] [分批卖出] 批次 {batch_num} 处理异常: {exc}")
                import traceback
                logger.debug(f"[Model {self.model_id}] [分批卖出] 异常堆栈:\n{traceback.format_exc()}")
            
            # 每N个批次完成后，统一处理这些批次的决策
            if batch_num % unit_size == 0 or batch_num == len(batches):
                group_start = ((batch_num - 1) // unit_size) * unit_size
                group_end = batch_num
                group_decisions = all_batch_decisions[group_start:group_end]
                
                logger.debug(f"[Model {self.model_id}] [分批卖出] 批次组 {group_start+1}-{group_end} 完成，开始统一处理决策（插入数据库和调用SDK）...")
                
                # 统一处理这组批次的决策（顺序执行，不需要锁）
                self._execute_batch_group_decisions_for_sell_sequential(
                    group_decisions,
                    portfolio,
                    account_info,
                    current_prices,
                    executions
                )
                
                logger.debug(f"[Model {self.model_id}] [分批卖出] 批次组 {group_start+1}-{group_end} 处理完成")
            
            # 如果不是最后一个批次，等待间隔时间
            if batch_num < len(batches) and batch_interval > 0:
                logger.debug(f"[Model {self.model_id}] [分批卖出] 批次 {batch_num} 完成，等待 {batch_interval} 秒后处理下一批次...")
                time.sleep(batch_interval)

        batch_end_time = datetime.now(timezone(timedelta(hours=8)))
        batch_duration = (batch_end_time - batch_start_time).total_seconds()
        logger.debug(f"[Model {self.model_id}] [分批卖出] 所有批次处理完成: "
                    f"完成批次数={len(batches)}, "
                    f"总耗时={batch_duration:.2f}秒, "
                    f"平均每批耗时={batch_duration/len(batches):.2f}秒")

        # 如果有任何批次产生了实际的卖出决策（close_position/stop_loss/take_profit），添加到对话提示中
        # hold 操作不算作实际执行的操作，不添加到对话提示中
        if has_sell_decision and 'sell' not in conversation_prompts:
            conversation_prompts.append('sell')
            logger.debug(f"[Model {self.model_id}] [分批卖出] 检测到实际卖出决策（close_position/stop_loss/take_profit），已添加到对话提示")
        else:
            logger.debug(f"[Model {self.model_id}] [分批卖出] 所有批次卖出决策被跳过、无有效决策或仅有hold操作（无实际执行）")

    def _execute_batch_group_decisions_for_sell_sequential(
        self,
        group_decisions: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        current_prices: Dict[str, float],
        executions: List
    ):
        """
        统一处理一组批次的卖出决策（插入数据库和调用SDK）- 顺序执行版本
        
        流程：
        1. 合并所有批次的卖出决策
        2. 记录所有批次的AI对话到数据库
        3. 顺序执行所有卖出决策（不使用锁，因为已经是顺序执行）
        4. 更新portfolio和account_info
        """
        if not group_decisions:
            logger.debug(f"[Model {self.model_id}] [卖出批次组处理] 无决策数据，跳过")
            return
        
        logger.debug(f"[Model {self.model_id}] [卖出批次组处理] 开始处理 {len(group_decisions)} 个批次的卖出决策...")
        
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
                    logger.debug(f"[Model {self.model_id}] [卖出批次组处理] 批次 {batch_num} 卖出决策: {symbol} -> {decision.get('signal')}")
            
            # 合并market_state
            all_market_states.update(batch_market_state)
            
            # 保存payload用于记录对话
            if not payload.get('skipped') and payload.get('prompt'):
                all_payloads.append(payload)
        
        if not all_decisions:
            logger.debug(f"[Model {self.model_id}] [卖出批次组处理] 无有效卖出决策，跳过执行")
            return
        
        logger.debug(f"[Model {self.model_id}] [卖出批次组处理] 合并完成: 卖出决策数={len(all_decisions)}, 对话数={len(all_payloads)}")
        
        # ========== 步骤1: 记录所有批次的AI对话到数据库 ==========
        logger.debug(f"[Model {self.model_id}] [卖出批次组处理] [步骤1] 记录AI对话到数据库...")
        for payload in all_payloads:
            try:
                self._record_ai_conversation(payload, conversation_type='sell')
            except Exception as e:
                logger.error(f"[Model {self.model_id}] [卖出批次组处理] 记录AI对话失败: {e}")
        logger.debug(f"[Model {self.model_id}] [卖出批次组处理] [步骤1] AI对话已记录")
        
        # ========== 步骤2: 顺序执行所有卖出决策 ==========
        logger.debug(f"[Model {self.model_id}] [卖出批次组处理] [步骤2] 开始顺序执行卖出决策...")
        
        # 获取最新持仓状态
        logger.debug(f"[Model {self.model_id}] [卖出批次组处理] [步骤2.1] 获取最新持仓状态...")
        latest_portfolio = self._get_portfolio(self.model_id, current_prices)
        logger.debug(f"[Model {self.model_id}] [卖出批次组处理] [步骤2.1] 最新持仓状态: "
                    f"总价值=${latest_portfolio.get('total_value', 0):.2f}, "
                    f"现金=${latest_portfolio.get('cash', 0):.2f}, "
                    f"持仓数={len(latest_portfolio.get('positions', []) or [])}")
        
        # 执行所有卖出决策（顺序执行）
        logger.debug(f"[Model {self.model_id}] [卖出批次组处理] [步骤2.2] 开始执行卖出决策...")
        execution_start = datetime.now(timezone(timedelta(hours=8)))
        batch_results = self._execute_decisions(
            all_decisions,
            all_market_states,
            latest_portfolio
        )
        execution_duration = (datetime.now(timezone(timedelta(hours=8))) - execution_start).total_seconds()
        logger.debug(f"[Model {self.model_id}] [卖出批次组处理] [步骤2.2] 卖出决策执行完成: 耗时={execution_duration:.2f}秒, 结果数={len(batch_results)}")
        
        # 记录每个执行结果
        for idx, result in enumerate(batch_results):
            logger.debug(f"[Model {self.model_id}] [卖出批次组处理] [步骤2.2.{idx+1}] 卖出执行结果: "
                        f"合约={result.get('symbol', 'N/A')}, "
                        f"信号={result.get('signal')}, "
                        f"数量={result.get('position_amt', 0)}, "
                        f"价格=${result.get('price', 0):.4f}, "
                        f"错误={result.get('error', '无')}")
        
        # 添加到执行结果列表
        logger.debug(f"[Model {self.model_id}] [卖出批次组处理] [步骤2.3] 添加执行结果到列表（当前总数: {len(executions)}）...")
        executions.extend(batch_results)
        logger.debug(f"[Model {self.model_id}] [卖出批次组处理] [步骤2.3] 执行结果已添加（新总数: {len(executions)}）")
        
        logger.debug(f"[Model {self.model_id}] [卖出批次组处理] 执行完成, 卖出决策数: {len(all_decisions)}, 执行结果: {len(batch_results)}")
        
        # ========== 步骤3: 更新portfolio和account_info ==========
        logger.debug(f"[Model {self.model_id}] [卖出批次组处理] [步骤3] 更新portfolio和account_info...")
        
        # 更新portfolio引用
        old_cash = portfolio.get('cash', 0)
        old_positions = len(portfolio.get('positions', []) or [])
        portfolio.update(latest_portfolio)
        new_cash = portfolio.get('cash', 0)
        new_positions = len(portfolio.get('positions', []) or [])
        logger.debug(f"[Model {self.model_id}] [卖出批次组处理] [步骤3.1] portfolio已更新: "
                    f"现金 ${old_cash:.2f} -> ${new_cash:.2f}, "
                    f"持仓数 {old_positions} -> {new_positions}")
        
        # 更新account_info
        updated_account_info = self._build_account_info(latest_portfolio)
        account_info.update(updated_account_info)
        logger.debug(f"[Model {self.model_id}] [卖出批次组处理] [步骤3.2] account_info已更新: "
                    f"总收益率={updated_account_info.get('total_return', 0):.2f}%")
        
        logger.debug(f"[Model {self.model_id}] [卖出批次组处理] [步骤3] 状态更新完成")

    def _process_sell_batch_decision_only(
        self,
        batch_positions: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        constraints_text: str,
        market_state: Dict,
        batch_num: int,
        total_batches: int
    ) -> Dict:
        """
        处理单个批次：只获取AI决策，不执行（用于卖出决策）
        
        流程：
        1. 验证所有symbol的市场数据是否有效
        2. 如果数据无效，记录醒目的warning日志并跳过
        3. 调用AI模型获取卖出决策
        4. 返回决策结果（不记录对话，不执行）
        """
        batch_start_time = datetime.now(timezone(timedelta(hours=8)))
        batch_symbols = [pos.get('symbol', 'N/A') for pos in batch_positions]
        
        logger.debug(f"[Model {self.model_id}] [卖出批次 {batch_num}/{total_batches}] "
                    f"开始获取AI决策，持仓合约: {batch_symbols}")
        
        try:
            # ========== 步骤0: 验证所有symbol的市场数据 ==========
            logger.debug(f"[Model {self.model_id}] [卖出批次 {batch_num}/{total_batches}] "
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
                        f"@@@ [Model {self.model_id}] [卖出批次 {batch_num}/{total_batches}] "
                        f"@@@ SYMBOL数据验证失败，跳过AI决策询问: {symbol_upper} @@@\n"
                        f"@@@ 错误信息: {error_msg} @@@\n"
                        f"@@@ 查询symbol: {symbol_upper} @@@"
                    )
            
            # 如果所有symbol都无效，返回跳过结果
            if not valid_positions:
                logger.warning(
                    f"@@@ [Model {self.model_id}] [卖出批次 {batch_num}/{total_batches}] "
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
                    f"@@@ [Model {self.model_id}] [卖出批次 {batch_num}/{total_batches}] "
                    f"@@@ 批次中部分symbol数据验证失败，将只处理有效symbol @@@\n"
                    f"@@@ 有效symbol: {[p.get('symbol') for p in valid_positions]} @@@\n"
                    f"@@@ 无效symbol详情: {[f'{s}: {e}' for s, e in invalid_symbols]} @@@"
                )
            
            # ========== 步骤1: 为当前批次创建临时portfolio ==========
            logger.debug(f"[Model {self.model_id}] [卖出批次 {batch_num}/{total_batches}] "
                        f"[步骤1] 创建临时portfolio，仅包含当前批次持仓... (有效symbol数: {len(valid_positions)})")
            batch_portfolio = portfolio.copy()
            batch_portfolio['positions'] = valid_positions  # 只使用有效的positions
            
            # ========== 步骤2: 调用AI模型获取卖出决策 ==========
            logger.debug(f"[Model {self.model_id}] [卖出批次 {batch_num}/{total_batches}] "
                        f"[步骤2] 调用AI模型进行卖出决策... (有效symbol数: {len(valid_positions)})")
            
            ai_call_start = datetime.now(timezone(timedelta(hours=8)))
            sell_payload = self.trader.make_sell_decision(
                batch_portfolio,
                market_state,
                account_info,
                model_id=self.model_id
            )
            ai_call_duration = (datetime.now(timezone(timedelta(hours=8))) - ai_call_start).total_seconds()
            
            is_skipped = sell_payload.get('skipped', False)
            has_prompt = bool(sell_payload.get('prompt'))
            decisions = sell_payload.get('decisions') or {}
            logger.debug(f"[Model {self.model_id}] [卖出批次 {batch_num}/{total_batches}] "
                        f"[步骤2] AI调用完成: 耗时={ai_call_duration:.2f}秒, "
                        f"跳过={is_skipped}, 有提示词={has_prompt}, 决策数={len(decisions)}")
            
            batch_end_time = datetime.now(timezone(timedelta(hours=8)))
            batch_duration = (batch_end_time - batch_start_time).total_seconds()
            logger.debug(f"[Model {self.model_id}] [卖出批次 {batch_num}/{total_batches}] "
                        f"AI决策获取完成: 总耗时={batch_duration:.2f}秒")
            
            return sell_payload
            
        except Exception as e:
            logger.error(f"[Model {self.model_id}] [卖出批次 {batch_num}/{total_batches}] 获取AI决策失败: {e}")
            import traceback
            logger.debug(f"[Model {self.model_id}] [卖出批次 {batch_num}/{total_batches}] 异常堆栈:\n{traceback.format_exc()}")
            return {'skipped': True, 'decisions': {}, 'error': str(e)}
    

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
            
            # 获取K线数据（不计算指标）
            # 注意：include_indicators 参数已废弃，但保留以兼容旧代码
            # 现在只获取klines，指标由ai_trader内部按需计算
            merged_data = self._merge_timeframe_data(query_symbol)
            timeframes_data = merged_data.get(query_symbol, {}) if merged_data else {}
            
            # 构建市场状态条目（只包含klines，不包含indicators）
            market_state[symbol_upper] = {
                'price': price_info.get('price', candidate.get('price', candidate.get('last_price', 0))),
                'name': candidate.get('name', symbol),
                'exchange': candidate.get('exchange', 'BINANCE_FUTURES'),
                'contract_symbol': candidate.get('contract_symbol') or f"{symbol}USDT",
                'change_24h': price_info.get('change_24h', candidate.get('change_percent', 0)),
                'daily_volume': price_info.get('daily_volume', candidate.get('quote_volume', 0)),
                'quote_volume': price_info.get('daily_volume', candidate.get('quote_volume', 0)),
                'indicators': {'timeframes': timeframes_data} if timeframes_data else {},  # 只包含klines
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
        - 'buy_to_long' / 'buy_to_short': 调用 _execute_buy（市场价买入）
        - 'sell_to_long' / 'sell_to_short': 调用 _execute_sell（市场价卖出/平仓）
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
            logger.debug(f"[Model {self.model_id}] [交易执行] 获取到交易锁，=====开始执行SDK交易决策=====")
            
            for symbol, decision in decisions.items():
                signal = decision.get('signal', '').lower()

                try:
                    if signal == 'buy_to_long' or signal == 'buy_to_short':
                        # 【市场价买入】buy_to_long（开多）和buy_to_short（开空）都调用_execute_buy方法
                        # _execute_buy方法会根据signal自动确定position_side：
                        # - buy_to_long → position_side = 'LONG'
                        # - buy_to_short → position_side = 'SHORT'
                        result = self._execute_buy(symbol, decision, market_state, portfolio)
                    elif signal == 'sell_to_long' or signal == 'sell_to_short':
                        # 【市场价卖出/平仓】sell_to_long（平多）和sell_to_short（平空）都调用_execute_sell方法
                        # _execute_sell方法会根据signal自动确定position_side：
                        # - sell_to_long → position_side = 'LONG'（平多仓）
                        # - sell_to_short → position_side = 'SHORT'（平空仓）
                        result = self._execute_sell(symbol, decision, market_state, portfolio)
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
                    # 记录异常，但继续执行其他交易决策
                    # 注意：所有数据库操作都通过 _with_connection 方法执行，连接会在异常时自动释放
                    logger.error(f"[Model {self.model_id}] [交易执行] 执行交易决策失败 (symbol={symbol}): {e}")
                    import traceback
                    logger.debug(f"[Model {self.model_id}] [交易执行] 异常堆栈:\n{traceback.format_exc()}")
                    results.append({'symbol': symbol, 'error': str(e)})
            
            logger.debug(f"[Model {self.model_id}] [交易执行] 交易决策执行完成，释放交易锁")

        return results

    # ============ 订单执行方法 ============
    # 执行具体的交易订单操作：开仓、平仓、止损、止盈
    
    def _execute_buy(self, symbol: str, decision: Dict, market_state: Dict, portfolio: Dict) -> Dict:
        """
        执行市场价买入（统一方法，支持开多和开空）
        
        【signal与position_side的映射关系】
        根据AI模型返回的signal字段自动确定position_side：
        - signal='buy_to_long'（开多）→ position_side='LONG'
        - signal='buy_to_short'（开空）→ position_side='SHORT'
        
        【重要说明】
        - AI模型不再返回position_side字段，只需要返回signal字段
        - 系统会根据signal自动确定position_side
        - trades表中记录的signal字段：buy_to_long 或 buy_to_short
        
        【SDK接口参数说明】
        - SDK调用的side参数：统一使用'BUY'（开多和开空都使用BUY）
        - SDK调用的positionSide参数：根据signal自动确定（LONG或SHORT）
        - 数据库记录的position_side：根据signal自动确定
        - trades表的side字段：统一使用'buy'（开多和开空都使用buy）
        """
        quantity = decision.get('quantity', 0)
        leverage = self._resolve_leverage(decision)
        price = market_state[symbol]['price']
        
        # 【根据signal自动确定position_side】不再从decision中获取position_side字段
        signal = decision.get('signal', '').lower()
        if signal == 'buy_to_long':
            position_side = 'LONG'  # 开多仓
            trade_signal = 'buy_to_long'  # trades表记录的signal
        elif signal == 'buy_to_short':
            position_side = 'SHORT'  # 开空仓
            trade_signal = 'buy_to_short'  # trades表记录的signal
        else:
            # 如果signal不是buy_to_long或buy_to_short，默认使用LONG（向后兼容）
            logger.warning(f"[Model {self.model_id}] Invalid signal '{signal}' for _execute_buy, defaulting to LONG")
            position_side = 'LONG'
            trade_signal = 'buy_to_long'
        
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

        # 确保quantity为整数（策略返回的quantity已经是整数，这里再次确保）
        quantity = int(float(quantity))
        if quantity <= 0 or quantity > max_affordable_qty:
            adjusted_qty = min(max_affordable_qty, risk_based_qty if risk_based_qty > 0 else max_affordable_qty)
            quantity = int(adjusted_qty)  # 确保调整后的数量也是整数
        
        if quantity <= 0:
            return {'symbol': symbol, 'error': '现金不足，无法买入'}

        trade_amount = quantity * price
        trade_fee = trade_amount * self.trade_fee_rate
        required_margin = (quantity * price) / leverage
        total_required = required_margin + trade_fee

        if total_required > available_cash:
            return {'symbol': symbol, 'error': '可用资金不足（含手续费）'}

        # 【确定SDK调用的side参数】统一使用BUY（开多和开空都使用BUY）
        # positionSide参数会根据signal自动确定（LONG或SHORT）
        sdk_side = 'BUY'  # 统一使用BUY
        
        # 获取交易上下文
        model_uuid, trade_id = self._get_trade_context()
        
        # 调用SDK执行交易
        sdk_response = None
        sdk_call_skipped = False
        sdk_skip_reason = None
        binance_client = self._create_binance_order_client()
        if binance_client:
            try:
                # 首先设置杠杆
                logger.info(f"@API@ [Model {self.model_id}] [change_initial_leverage] === 准备设置杠杆 ===" 
                          f" | symbol={symbol} | leverage={leverage}")
                
                binance_client.change_initial_leverage(
                    symbol=symbol,
                    leverage=leverage
                )
                
                logger.info(f"@API@ [Model {self.model_id}] [change_initial_leverage] === 杠杆设置成功 ===" 
                          f" | symbol={symbol} | leverage={leverage}")
                
                # 然后执行交易
                logger.info(f"@API@ [Model {self.model_id}] [market_trade] === 准备调用接口 ===" 
                          f" | symbol={symbol} | side={sdk_side} | position_side={position_side} | "
                          f"quantity={quantity} | price={price} | leverage={leverage}")
                
                conversation_id = self._get_conversation_id()
                
                sdk_response = binance_client.market_trade(
                    symbol=symbol,
                    side=sdk_side,
                    order_type='MARKET',
                    position_side=position_side,
                    quantity=quantity,
                    model_id=model_uuid,
                    conversation_id=conversation_id,
                    trade_id=trade_id,
                    db=self.binance_trade_logs_db
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
            self._update_position(
                self.model_id, symbol=symbol, position_amt=quantity, avg_price=price, 
                leverage=leverage, position_side=position_side  # 使用根据signal自动确定的position_side
            )
        except Exception as db_err:
            logger.error(f"TRADE: Update position failed ({trade_signal.upper()}) model={self.model_id} future={symbol}: {db_err}")
            raise

        # 【确定trades表的side字段】统一使用'buy'（开多和开空都使用buy）
        trade_side = 'buy'  # 统一使用buy
        
        # 记录交易
        logger.info(f"TRADE: PENDING - Model {self.model_id} {trade_signal.upper()} {symbol} position_side={position_side} qty={quantity} price={price} fee={trade_fee}")
        try:
            self.db.insert_rows(
                self.db.trades_table,
                [[trade_id, model_uuid, symbol.upper(), trade_signal, quantity, price, leverage, trade_side, 0, trade_fee, datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)]],
                ["id", "model_id", "future", "signal", "quantity", "price", "leverage", "side", "pnl", "fee", "timestamp"]
            )
            logger.info(f"TRADE: RECORDED - Model {self.model_id} {trade_signal.upper()} {symbol}")
        except Exception as db_err:
            logger.error(f"TRADE: Add trade failed ({trade_signal.upper()}) model={self.model_id} future={symbol}: {db_err}")
            raise
        
        self._log_trade_record(trade_signal, symbol, position_side, sdk_call_skipped, sdk_skip_reason)
        
        # 每次交易后立即记录账户价值快照
        try:
            # 从market_state中提取current_prices格式：{symbol: price_value}
            current_prices = {s: m.get('price', 0) for s, m in market_state.items()}
            logger.info(f"[Model {self.model_id}] [开仓交易] 交易已记录到trades表，立即记录账户价值快照")
            self._record_account_snapshot(current_prices)
            logger.info(f"[Model {self.model_id}] [开仓交易] 账户价值快照已记录")
        except Exception as snapshot_err:
            logger.error(f"[Model {self.model_id}] [开仓交易] 记录账户价值快照失败: {snapshot_err}", exc_info=True)
            # 不抛出异常，避免影响主流程

        return {
            'symbol': symbol,
            'signal': trade_signal,  # 返回实际的signal（buy_to_long或buy_to_short）
            'position_amt': quantity,
            'position_side': position_side,  # 返回position_side信息
            'price': price,
            'leverage': leverage,
            'fee': trade_fee,
            'message': f'开仓 {symbol} {position_side} {quantity:.4f} @ ${price:.2f} (手续费: ${trade_fee:.2f})'
        }

    def _execute_sell(self, symbol: str, decision: Dict, market_state: Dict, portfolio: Dict) -> Dict:
        """
        执行市场价卖出/平仓（统一方法，支持平多和平空）
        
        【signal与position_side的映射关系】
        根据AI模型返回的signal字段自动确定position_side：
        - signal='sell_to_long'（平多）→ position_side='LONG'
        - signal='sell_to_short'（平空）→ position_side='SHORT'
        
        【重要说明】
        - AI模型不再返回position_side字段，只需要返回signal字段
        - 系统会根据signal自动确定position_side
        - trades表中记录的signal字段：sell_to_long 或 sell_to_short
        
        【SDK接口参数说明】
        - SDK调用的side参数：统一使用'SELL'（平多和平空都使用SELL）
        - SDK调用的positionSide参数：根据signal自动确定（LONG或SHORT）
        - 数据库记录的position_side：根据signal自动确定
        - trades表的side字段：统一使用'sell'（平多和平空都使用sell）
        
        【持仓检查】
        - 必须检查是否有对应方向的持仓
        - 如果没有持仓，返回错误信息
        """
        # 查找持仓信息
        position = self._find_position(portfolio, symbol)
        if not position:
            return {'symbol': symbol, 'error': 'Position not found'}
        
        # 【根据signal自动确定position_side】不再从decision中获取position_side字段
        signal = decision.get('signal', '').lower()
        if signal == 'sell_to_long':
            position_side = 'LONG'  # 平多仓
            trade_signal = 'sell_to_long'  # trades表记录的signal
        elif signal == 'sell_to_short':
            position_side = 'SHORT'  # 平空仓
            trade_signal = 'sell_to_short'  # trades表记录的signal
        else:
            # 如果signal不是sell_to_long或sell_to_short，默认使用LONG（向后兼容）
            logger.warning(f"[Model {self.model_id}] Invalid signal '{signal}' for _execute_sell, defaulting to LONG")
            position_side = 'LONG'
            trade_signal = 'sell_to_long'
        
        # 检查持仓方向是否匹配
        actual_position_side = position.get('position_side', 'LONG')
        if actual_position_side != position_side:
            return {'symbol': symbol, 'error': f'持仓方向不匹配：期望{position_side}，实际{actual_position_side}'}
        
        current_price = market_state[symbol]['price']
        entry_price = position.get('avg_price', 0)
        # 确保position_amt为整数（去除小数部分）
        position_amt = int(abs(position.get('position_amt', 0)))
        
        if position_amt <= 0:
            return {'symbol': symbol, 'error': '持仓数量为0，无法平仓'}
        
        # 计算毛盈亏和净盈亏
        if position_side == 'LONG':
            gross_pnl = (current_price - entry_price) * position_amt
        else:  # SHORT
            gross_pnl = (entry_price - current_price) * position_amt
        
        trade_amount = position_amt * current_price
        trade_fee = trade_amount * self.trade_fee_rate
        net_pnl = gross_pnl - trade_fee
        
        # 【确定SDK调用的side参数】统一使用SELL（平多和平空都使用SELL）
        sdk_side = 'SELL'  # 统一使用SELL
        
        # 获取交易上下文
        model_uuid, trade_id = self._get_trade_context()
        
        # 调用SDK执行交易
        sdk_response = None
        sdk_call_skipped = False
        sdk_skip_reason = None
        binance_client = self._create_binance_order_client()
        if binance_client:
            try:
                # 首先设置杠杆（如果需要）
                leverage = self._resolve_leverage(decision)
                if not decision.get('leverage'):
                    leverage = position.get('leverage', leverage)
                
                logger.info(f"@API@ [Model {self.model_id}] [change_initial_leverage] === 准备设置杠杆 ===" 
                          f" | symbol={symbol} | leverage={leverage}")
                
                binance_client.change_initial_leverage(
                    symbol=symbol,
                    leverage=leverage
                )
                
                logger.info(f"@API@ [Model {self.model_id}] [change_initial_leverage] === 杠杆设置成功 ===" 
                          f" | symbol={symbol} | leverage={leverage}")
                
                # 然后执行交易
                logger.info(f"@API@ [Model {self.model_id}] [market_trade] === 准备调用接口 ===" 
                          f" | symbol={symbol} | side={sdk_side} | position_side={position_side} | "
                          f"quantity={position_amt} | price={current_price} | leverage={leverage}")
                
                conversation_id = self._get_conversation_id()
                
                sdk_response = binance_client.market_trade(
                    symbol=symbol,
                    side=sdk_side,
                    order_type='MARKET',
                    position_side=position_side,
                    quantity=position_amt,
                    model_id=model_uuid,
                    conversation_id=conversation_id,
                    trade_id=trade_id,
                    db=self.binance_trade_logs_db
                )
                
                logger.info(f"@API@ [Model {self.model_id}] [market_trade] === 接口调用成功 ==="
                          f" | symbol={symbol} | response={sdk_response}")
            except Exception as sdk_err:
                logger.error(f"@API@ [Model {self.model_id}] [market_trade] === 接口调用失败 ==="
                           f" | symbol={symbol} | error={sdk_err}", exc_info=True)
        else:
            sdk_call_skipped, sdk_skip_reason = self._handle_sdk_client_error(symbol, 'market_trade')
        
        # 平仓：更新数据库持仓记录（将持仓数量设为0）
        try:
            self._close_position(self.model_id, symbol=symbol, position_side=position_side)
        except Exception as db_err:
            logger.error(f"TRADE: Close position failed ({trade_signal.upper()}) model={self.model_id} future={symbol}: {db_err}")
            raise
        
        # 【确定trades表的side字段】统一使用'sell'（平多和平空都使用sell）
        trade_side = 'sell'  # 统一使用sell
        
        # 记录交易
        logger.info(f"TRADE: PENDING - Model {self.model_id} {trade_signal.upper()} {symbol} position_side={position_side} position_amt={position_amt} price={current_price} fee={trade_fee} net_pnl={net_pnl}")
        try:
            # 使用持仓中存储的杠杆值
            leverage = self._resolve_leverage(decision)
            if not decision.get('leverage'):
                leverage = position.get('leverage', leverage)
            
            self.db.insert_rows(
                self.db.trades_table,
                [[trade_id, model_uuid, symbol.upper(), trade_signal, position_amt, current_price, leverage, trade_side, net_pnl, trade_fee, datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)]],
                ["id", "model_id", "future", "signal", "quantity", "price", "leverage", "side", "pnl", "fee", "timestamp"]
            )
            logger.info(f"TRADE: RECORDED - Model {self.model_id} {trade_signal.upper()} {symbol}")
        except Exception as db_err:
            logger.error(f"TRADE: Add trade failed ({trade_signal.upper()}) model={self.model_id} future={symbol}: {db_err}")
            raise
        
        self._log_trade_record(trade_signal, symbol, position_side, sdk_call_skipped, sdk_skip_reason)
        
        # 每次交易后立即记录账户价值快照
        try:
            # 从market_state中提取current_prices格式：{symbol: price_value}
            current_prices = {s: m.get('price', 0) for s, m in market_state.items()}
            logger.info(f"[Model {self.model_id}] [平仓交易] 交易已记录到trades表，立即记录账户价值快照")
            self._record_account_snapshot(current_prices)
            logger.info(f"[Model {self.model_id}] [平仓交易] 账户价值快照已记录")
        except Exception as snapshot_err:
            logger.error(f"[Model {self.model_id}] [平仓交易] 记录账户价值快照失败: {snapshot_err}", exc_info=True)
            # 不抛出异常，避免影响主流程
        
        return {
            'symbol': symbol,
            'signal': trade_signal,  # 返回实际的signal（sell_to_long或sell_to_short）
            'position_amt': position_amt,
            'position_side': position_side,  # 返回position_side信息
            'price': current_price,
            'pnl': net_pnl,
            'fee': trade_fee,
            'message': f'平仓 {symbol} {position_side}, 毛收益 ${gross_pnl:.2f}, 手续费 ${trade_fee:.2f}, 净收益 ${net_pnl:.2f}'
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
        # 确保position_amt为整数（去除小数部分）
        position_amt = int(abs(position.get('position_amt', 0)))
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
                    db=self.binance_trade_logs_db
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
            self._close_position(self.model_id, symbol=symbol, position_side=position_side)
        except Exception as db_err:
            logger.error(f"TRADE: Close position failed model={self.model_id} future={symbol}: {db_err}")
            raise
        
        # 记录交易
        logger.info(f"TRADE: PENDING - Model {self.model_id} CLOSE {symbol} position_side={position_side} position_amt={position_amt} price={current_price} fee={trade_fee} net_pnl={net_pnl}")
        try:
            # 使用与开仓时一致的逻辑获取杠杆值
            leverage = self._resolve_leverage(decision)
            # 如果AI没有返回杠杆值，使用持仓中存储的杠杆值
            if not decision.get('leverage'):
                leverage = position.get('leverage', leverage)
                
            self.db.insert_rows(
                self.db.trades_table,
                [[trade_id, model_uuid, symbol.upper(), 'close_position', position_amt, current_price, leverage, side_for_trade.lower(), net_pnl, trade_fee, datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)]],
                ["id", "model_id", "future", "signal", "quantity", "price", "leverage", "side", "pnl", "fee", "timestamp"]
            )
            logger.info(f"TRADE: RECORDED - Model {self.model_id} CLOSE {symbol}")
        except Exception as db_err:
            logger.error(f"TRADE: Add trade failed (CLOSE) model={self.model_id} future={symbol}: {db_err}")
            raise
        self._log_trade_record('close_position', symbol, position_side, sdk_call_skipped, sdk_skip_reason)
        
        # 每次交易后立即记录账户价值快照
        try:
            # 从market_state中提取current_prices格式：{symbol: price_value}
            current_prices = {s: m.get('price', 0) for s, m in market_state.items()}
            logger.info(f"[Model {self.model_id}] [平仓交易] 交易已记录到trades表，立即记录账户价值快照")
            self._record_account_snapshot(current_prices)
            logger.info(f"[Model {self.model_id}] [平仓交易] 账户价值快照已记录")
        except Exception as snapshot_err:
            logger.error(f"[Model {self.model_id}] [平仓交易] 记录账户价值快照失败: {snapshot_err}", exc_info=True)
            # 不抛出异常，避免影响主流程

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
        # 确保position_amt为整数（去除小数部分）
        position_amt = int(abs(position.get('position_amt', 0)))
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
                    db=self.binance_trade_logs_db
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
            if sdk_call_skipped:
                logger.warning(f"TRADE: RECORDED (但SDK未执行) - Model {self.model_id} STOP_LOSS {symbol} | "
                             f"⚠️ 此交易记录已保存，但实际交易未执行，请检查API密钥配置")
            else:
                logger.info(f"TRADE: RECORDED - Model {self.model_id} STOP_LOSS {symbol}")
        except Exception as db_err:
            logger.error(f"TRADE: Add trade failed (STOP_LOSS) model={self.model_id} symbol={symbol}: {db_err}")
            raise
        
        # 每次交易后立即记录账户价值快照
        try:
            # 从market_state中提取current_prices格式：{symbol: price_value}
            current_prices = {s: m.get('price', 0) for s, m in market_state.items()}
            logger.info(f"[Model {self.model_id}] [止损交易] 交易已记录到trades表，立即记录账户价值快照")
            self._record_account_snapshot(current_prices)
            logger.info(f"[Model {self.model_id}] [止损交易] 账户价值快照已记录")
        except Exception as snapshot_err:
            logger.error(f"[Model {self.model_id}] [止损交易] 记录账户价值快照失败: {snapshot_err}", exc_info=True)
            # 不抛出异常，避免影响主流程

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
        # 确保position_amt为整数（去除小数部分）
        position_amt = int(abs(position.get('position_amt', 0)))
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
                    db=self.binance_trade_logs_db
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
            logger.info(f"TRADE: RECORDED - Model {self.model_id} TAKE_PROFIT {symbol}")
        except Exception as db_err:
            logger.error(f"TRADE: Add trade failed (TAKE_PROFIT) model={self.model_id} symbol={symbol}: {db_err}")
            raise
        self._log_trade_record('take_profit', symbol, position_side, sdk_call_skipped, sdk_skip_reason)
        
        # 每次交易后立即记录账户价值快照
        try:
            # 从market_state中提取current_prices格式：{symbol: price_value}
            current_prices = {s: m.get('price', 0) for s, m in market_state.items()}
            logger.info(f"[Model {self.model_id}] [止盈交易] 交易已记录到trades表，立即记录账户价值快照")
            self._record_account_snapshot(current_prices)
            logger.info(f"[Model {self.model_id}] [止盈交易] 账户价值快照已记录")
        except Exception as snapshot_err:
            logger.error(f"[Model {self.model_id}] [止盈交易] 记录账户价值快照失败: {snapshot_err}", exc_info=True)
            # 不抛出异常，避免影响主流程

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
        # 优先使用实例变量中缓存的杠杆值
        if hasattr(self, 'current_model_leverage') and self.current_model_leverage is not None:
            logger.debug(f"[Model {self.model_id}] 使用缓存的模型杠杆配置: {self.current_model_leverage}")
            return self.current_model_leverage
        
        # 如果没有缓存，则查询数据库
        try:
            model = self.models_db.get_model(self.model_id)
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
        # 确保返回的杠杆值至少为1
        return max(1, leverage)

    def _resolve_leverage(self, decision: Dict) -> int:
        """
        解析杠杆倍数（优先使用AI决策中的杠杆，否则使用模型配置）
        
        Args:
            decision: AI决策字典，可能包含leverage字段
        
        Returns:
            int: 最终使用的杠杆倍数
        
        优先级：
        1. 如果AI决策中包含有效的杠杆值，则使用该值
        2. 否则使用模型配置的杠杆值
        
        Note:
            此方法确保杠杆倍数至少为1，避免无效配置
        """
        configured = getattr(self, 'current_model_leverage', None)
        if configured is None:
            configured = self._get_model_leverage()

        ai_leverage = decision.get('leverage')
        leverage_valid = False
        
        # 检查AI决策中的杠杆是否有效
        if ai_leverage is not None:
            try:
                ai_leverage = int(ai_leverage)
                if ai_leverage >= 1:
                    leverage_valid = True
            except (TypeError, ValueError):
                leverage_valid = False

        # 如果AI决策中的杠杆有效，则使用该值
        if leverage_valid:
            return ai_leverage
        
        # 否则使用模型配置的杠杆值，确保至少为1
        return max(1, configured)
