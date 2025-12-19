"""
AI Trader - 基于大语言模型的交易决策生成器

本模块提供AITrader类，用于通过LLM（大语言模型）生成交易决策。
支持多种LLM提供商：OpenAI、Anthropic、Gemini、DeepSeek等。

主要功能：
1. 买入决策生成：基于候选交易对列表生成买入/开仓决策
2. 卖出决策生成：基于当前持仓生成卖出/平仓决策
3. 多提供商支持：统一接口支持多种LLM API
4. 响应解析：自动解析LLM返回的JSON格式决策数据

使用流程：
1. 初始化AITrader实例（指定提供商、API密钥、模型等）
2. 调用make_buy_decision()或make_sell_decision()生成决策
3. 返回包含决策、提示词、原始响应等信息的字典
"""
import json
import logging
from typing import Dict, Optional, Tuple, List
from openai import OpenAI, APIConnectionError, APIError
from trade.trader import Trader
from common.database.database_model_prompts import ModelPromptsDatabase
from common.database.database_models import ModelsDatabase
from common.database.database_providers import ProvidersDatabase
from common.database.database_conversations import ConversationsDatabase

logger = logging.getLogger(__name__)

# 导入market_data模块用于计算指标
try:
    from market.market_data import MarketDataFetcher
    MARKET_DATA_AVAILABLE = True
except ImportError:
    MARKET_DATA_AVAILABLE = False
    logger.warning("market_data module not available, indicators calculation will be skipped")

# 尝试导入tiktoken用于token计算，如果不可用则使用简单估算
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken not available, will use simple token estimation")


class AITrader(Trader):
    """
    AI交易决策生成器
    
    负责通过LLM生成交易决策，包括买入和卖出决策。
    支持多种LLM提供商，提供统一的接口和响应格式。
    
    使用示例：
        trader = AITrader(
            provider_type='openai',
            api_key='sk-xxx',
            api_url='https://api.openai.com',
            model_name='gpt-4'
        )
        result = trader.make_buy_decision(candidates, portfolio, account_info)
    """
    
    # ============ 初始化方法 ============
    
    def __init__(self, provider_type: str, api_key: str, api_url: str, model_name: str, db=None, market_fetcher=None):
        """
        初始化AI交易决策生成器
        
        Args:
            provider_type: LLM提供商类型，支持：
                - 'openai': OpenAI API
                - 'azure_openai': Azure OpenAI
                - 'deepseek': DeepSeek API
                - 'anthropic': Anthropic Claude API
                - 'gemini': Google Gemini API
            api_key: LLM API密钥
            api_url: LLM API基础URL
            model_name: 使用的模型名称（如 'gpt-4', 'claude-3-opus' 等）
            db: 数据库实例（可选），用于记录API调用错误
            market_fetcher: MarketDataFetcher实例（可选），用于计算技术指标
        """
        self.provider_type = provider_type.lower()
        self.api_key = api_key
        self.api_url = api_url
        self.model_name = model_name
        self.db = db
        self.market_fetcher = market_fetcher
        # 初始化 ModelPromptsDatabase、ModelsDatabase、ProvidersDatabase 和 ConversationsDatabase 实例
        self.model_prompts_db = ModelPromptsDatabase(pool=db._pool if db and hasattr(db, '_pool') else None)
        self.models_db = ModelsDatabase(pool=db._pool if db and hasattr(db, '_pool') else None)
        self.providers_db = ProvidersDatabase(pool=db._pool if db and hasattr(db, '_pool') else None)
        self.conversations_db = ConversationsDatabase(pool=db._pool if db and hasattr(db, '_pool') else None)

    # ============ 公共决策方法 ============
    
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
        
        基于候选交易对列表，通过LLM生成买入或开仓决策。
        决策包括：buy_to_enter（开多）、sell_to_enter（开空）、hold（观望）。
        
        Args:
            candidates: 候选交易对列表，每个元素包含：
                - symbol: 交易对符号（如 'BTC'）
                - contract_symbol: 合约符号（如 'BTCUSDT'）
                - price: 当前价格
                - quote_volume: 24小时成交额
            portfolio: 持仓组合信息，包含：
                - positions: 当前持仓列表
                - cash: 可用现金
                - total_value: 账户总值
            account_info: 账户信息，包含：
                - balance: 账户余额
                - available_balance: 可用余额
                - total_return: 累计收益率
            market_state: 市场状态字典，key为交易对符号，value包含：
                - price: 当前价格
                - indicators: 技术指标数据
                    - timeframes: 多时间周期的技术指标
            symbol_source: 数据源类型，影响prompt构建：
                - 'leaderboard'（默认）：候选来自涨跌榜，说明"来自实时涨跌幅榜"
                - 'future'：候选来自合约配置信息表，说明"来自合约配置信息表"
            model_id: 模型ID（用于从数据库获取buy_prompt）
        
        Returns:
            Dict: 包含以下字段的字典：
                - decisions: 决策字典，key为交易对符号，value为决策详情
                - prompt: 发送给LLM的完整提示词
                - raw_response: LLM的原始响应文本
                - cot_trace: 推理过程（Chain of Thought）文本
                - skipped: 是否跳过（当candidates为空时为True）
        
        Note:
            - 如果candidates为空，返回skipped=True的结果
            - 决策格式：{"SYMBOL": {"signal": "buy_to_enter|sell_to_enter|hold", ...}}
            - 系统会根据signal自动设置position_side（LONG或SHORT）
            - constraints和constraints_text在内部从数据库获取和处理
            - market_snapshot在内部从market_state构建
        """
        logger.info(f"[{self.provider_type}] 开始生成买入决策, 候选交易对数量: {len(candidates)}, 模型: {self.model_name}")
        if not candidates:
            return {'decisions': {}, 'prompt': None, 'raw_response': None, 'cot_trace': None, 'skipped': True}

        # 内部处理：从数据库获取constraints_text（buy_prompt）
        constraints_text = None
        if self.model_prompts_db and model_id:
            try:
                model_mapping = self.models_db._get_model_id_mapping() if self.models_db else None
                model_prompt = self.model_prompts_db.get_model_prompt(model_id, model_mapping)
                if model_prompt:
                    constraints_text = model_prompt.get('buy_prompt')
            except Exception as e:
                logger.warning(f"[{self.provider_type}] [买入决策] 获取buy_prompt失败: {e}")
        
        # 内部处理：从market_state构建market_snapshot，并计算技术指标
        market_snapshot = []
        for candidate in candidates:
            symbol = candidate.get('symbol', '').upper()
            if symbol in market_state:
                state_info = market_state[symbol]
                timeframes_data = state_info.get('indicators', {}).get('timeframes', {})
                
                # 如果timeframes_data只包含klines，需要计算指标
                # 检查第一个时间框架是否有指标数据
                has_indicators = False
                if timeframes_data:
                    first_timeframe = next(iter(timeframes_data.values()), {})
                    if isinstance(first_timeframe, dict):
                        # 检查是否有ma、macd等指标字段
                        has_indicators = any(key in first_timeframe for key in ['ma', 'macd', 'rsi', 'vol'])
                
                # 如果没有指标且有market_fetcher，计算指标
                if not has_indicators and timeframes_data and self.market_fetcher:
                    try:
                        # 使用market_fetcher计算指标
                        timeframes_data = self.market_fetcher.calculate_indicators_for_timeframes(timeframes_data)
                        logger.debug(f"[{self.provider_type}] [买入决策] 为 {symbol} 计算了技术指标")
                    except Exception as e:
                        logger.warning(f"[{self.provider_type}] [买入决策] 计算指标失败: {e}")
                
                snapshot_entry = {
                    'symbol': symbol,
                    'contract_symbol': state_info.get('contract_symbol', f"{symbol}USDT"),
                    'price': state_info.get('price', 0),
                    'quote_volume': state_info.get('quote_volume', state_info.get('daily_volume', 0)),
                    'change_percent': state_info.get('change_24h', 0),
                    'timeframes': timeframes_data
                }
                market_snapshot.append(snapshot_entry)
        
        # 内部处理：构建constraints
        positions = portfolio.get('positions', []) or []
        constraints = {
            'max_positions': None,  # 可以从数据库获取，这里先设为None
            'occupied': len(positions),
            'available_cash': portfolio.get('cash', 0)
        }
        
        # 构建prompt
        prompt = self._build_buy_prompt(candidates, portfolio, account_info, constraints, constraints_text, market_snapshot, symbol_source)
        try:
            return self._request_decisions(prompt, decision_type='buy', model_id=model_id)
        except Exception as e:
            # 记录API调用错误到数据库
            error_msg = str(e)
            logger.error(f"[{self.provider_type}] [买入决策] LLM API调用失败: {error_msg}")
            
            # 如果提供了数据库实例和模型ID，记录错误信息
            if self.db and model_id:
                try:
                    # 获取模型信息以获取provider信息
                    model = self.models_db.get_model(model_id)
                    if model:
                        provider_id = model.get('provider_id')
                        if provider_id:
                            provider = self.providers_db.get_provider(provider_id)
                            if provider:
                                provider_name = provider.get('name', '')
                                model_name = model.get('model_name', self.model_name)
                                # 记录错误到数据库（不记录prompt字段）
                                model_mapping = self.models_db._get_model_id_mapping()
                                self.conversations_db.record_llm_api_error(
                                    model_id=model_id,
                                    provider_name=provider_name,
                                    model=model_name,
                                    error_msg=error_msg,
                                    model_id_mapping=model_mapping
                                )
                                logger.info(f"[{self.provider_type}] [买入决策] 已记录API错误到数据库: model_id={model_id}, provider={provider_name}, model={model_name}")
                except Exception as db_error:
                    logger.error(f"[{self.provider_type}] [买入决策] 记录API错误到数据库失败: {db_error}")
            
            # 重新抛出异常，让调用者处理
            raise

    def make_sell_decision(
        self,
        portfolio: Dict,
        market_state: Dict,
        account_info: Dict,
        model_id: Optional[int] = None
    ) -> Dict:
        """
        生成卖出/平仓决策
        
        基于当前持仓信息，通过LLM生成卖出或平仓决策。
        决策包括：close_position（平仓）、stop_loss（止损）、take_profit（止盈）、hold（继续持有）。
        
        注意：此方法只处理账户现有持仓，不涉及涨幅榜数据。
        决策基于持仓币种本身的价格表现、盈亏情况、风险控制等因素。
        
        Args:
            portfolio: 当前持仓组合信息，包含：
                - positions: 持仓列表，每个元素包含：
                    - symbol: 交易对符号
                    - position_amt: 持仓数量
                    - position_side: 持仓方向（LONG/SHORT）
                    - avg_price: 开仓均价
                    - unrealized_profit: 未实现盈亏
                - total_value: 账户总值
                - cash: 可用现金
            market_state: 市场状态字典，key为交易对符号，value包含：
                - price: 当前价格
                - indicators: 技术指标数据
                    - timeframes: 多时间周期的技术指标
            account_info: 账户信息，包含：
                - total_return: 累计收益率
            model_id: 模型ID（用于从数据库获取sell_prompt）
        
        Returns:
            Dict: 包含以下字段的字典：
                - decisions: 决策字典，key为交易对符号，value为决策详情
                - prompt: 发送给LLM的完整提示词
                - raw_response: LLM的原始响应文本
                - cot_trace: 推理过程（Chain of Thought）文本
                - skipped: 是否跳过（当portfolio中没有持仓时为True）
        
        Note:
            - 如果portfolio中没有持仓，返回skipped=True的结果
            - 决策格式：{"SYMBOL": {"signal": "close_position|stop_loss|take_profit|hold", ...}}
            - constraints_text在内部从数据库获取和处理
        """
        logger.info(f"[{self.provider_type}] 开始生成卖出决策, 持仓数量: {len(portfolio.get('positions') or [])}, 模型: {self.model_name}")
        if not portfolio.get('positions'):
            return {'decisions': {}, 'prompt': None, 'raw_response': None, 'cot_trace': None, 'skipped': True}

        # 内部处理：从数据库获取constraints_text（sell_prompt）
        constraints_text = None
        if self.model_prompts_db and model_id:
            try:
                model_mapping = self.models_db._get_model_id_mapping() if self.models_db else None
                model_prompt = self.model_prompts_db.get_model_prompt(model_id, model_mapping)
                if model_prompt:
                    constraints_text = model_prompt.get('sell_prompt')
            except Exception as e:
                logger.warning(f"[{self.provider_type}] [卖出决策] 获取sell_prompt失败: {e}")

        prompt = self._build_sell_prompt(portfolio, market_state, account_info, constraints_text)
        try:
            return self._request_decisions(prompt, decision_type='sell', model_id=model_id)
        except Exception as e:
            # 记录API调用错误到数据库
            error_msg = str(e)
            logger.error(f"[{self.provider_type}] [卖出决策] LLM API调用失败: {error_msg}")
            
            # 如果提供了数据库实例和模型ID，记录错误信息
            if self.db and model_id:
                try:
                    # 获取模型信息以获取provider信息
                    model = self.models_db.get_model(model_id)
                    if model:
                        provider_id = model.get('provider_id')
                        if provider_id:
                            provider = self.providers_db.get_provider(provider_id)
                            if provider:
                                provider_name = provider.get('name', '')
                                model_name = model.get('model_name', self.model_name)
                                # 记录错误到数据库（不记录prompt字段）
                                model_mapping = self.models_db._get_model_id_mapping()
                                self.conversations_db.record_llm_api_error(
                                    model_id=model_id,
                                    provider_name=provider_name,
                                    model=model_name,
                                    error_msg=error_msg,
                                    model_id_mapping=model_mapping
                                )
                                logger.info(f"[{self.provider_type}] [卖出决策] 已记录API错误到数据库: model_id={model_id}, provider={provider_name}, model={model_name}")
                except Exception as db_error:
                    logger.error(f"[{self.provider_type}] [卖出决策] 记录API错误到数据库失败: {db_error}")
            
            # 重新抛出异常，让调用者处理
            raise

    # ============ 提示词构建方法 ============
    
    def _build_buy_prompt(
        self,
        candidates: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        constraints: Dict,
        constraints_text: Optional[str],
        market_snapshot: Optional[List[Dict]] = None,
        symbol_source: str = 'leaderboard'
    ) -> str:
        """
        构建买入决策的提示词
        
        根据候选交易对、持仓信息、账户信息等构建完整的提示词，
        用于发送给LLM生成买入/开仓决策。
        
        Args:
            candidates: 候选交易对列表
            portfolio: 持仓组合信息
            account_info: 账户信息
            constraints: 约束条件字典
            constraints_text: 策略约束文本（buy_prompt）
            market_snapshot: 市场快照数据列表，包含每个交易对的技术指标
            symbol_source: 数据源类型：
                - 'future'：来自合约配置信息表（全市场扫描）
                - 'leaderboard'（默认）：来自实时涨跌幅榜（关注热点）
        
        Returns:
            str: 完整的提示词文本，包含：
                - 角色定义（USDS-M合约专业人士）
                - 候选交易对列表（价格、成交量、技术指标）
                - 账户约束（可用现金、持仓数、最大持仓上限）
                - 策略约束（用户自定义的buy_prompt）
                - 执行要求和JSON模板
        
        Note:
            - 根据symbol_source调整候选交易对来源的描述
            - 将market_snapshot中的技术指标数据以JSON格式嵌入prompt
            - 提示词要求LLM返回标准JSON格式的决策
        """
        max_positions = constraints.get('max_positions')
        occupied = constraints.get('occupied', len(portfolio.get('positions') or []))
        available_cash = constraints.get('available_cash', portfolio.get('cash', 0))
        available_slots = max(0, max_positions - occupied) if isinstance(max_positions, int) else 'N/A'

        prompt = """你是USDS-M合约的专业人士，请使用相关专业知识进行操作，只能在给定的候选列表中挑选要买入的合约。"""
        
        # 【根据数据源调整prompt文本】让AI模型知道交易对的来源，有助于理解数据特征
        # 涨跌榜的交易对通常具有较高的市场关注度和波动性
        # futures表的交易对则覆盖全市场，可能包含更多样化的选择
        if symbol_source == 'future':
            prompt += f"\n\n候选合约（来自合约配置信息表，共 {len(candidates)} 个），相关市场数据：\n"
        else:
            prompt += f"\n\n候选合约（来自实时涨跌幅榜，共 {len(candidates)} 个），相关市场数据：\n"
        
        # 创建一个symbol到timeframes的映射，用于快速查找
        symbol_timeframes_map = {}
        if market_snapshot:
            for snapshot_entry in market_snapshot:
                symbol = snapshot_entry.get('symbol')
                timeframes = snapshot_entry.get('timeframes')
                if symbol and timeframes:
                    symbol_timeframes_map[symbol] = timeframes
        
        # 直接将新的数据格式以JSON格式插入到prompt中，不再使用_format_market_snapshot
        for idx, entry in enumerate(candidates, start=1):
            symbol = entry.get('symbol', 'N/A')
            contract_symbol = entry.get('contract_symbol') or f"{symbol}USDT"
            price = entry.get('price')
            volume = entry.get('quote_volume')
            
            prompt += f"{idx}. {symbol} / {contract_symbol}\n"
            # 处理price和volume可能为0或None的情况
            price_str = f"${price:.4f}" if price and price > 0 else "价格获取中"
            volume_str = f"{volume:.2f} USDT" if volume and volume > 0 else "成交量获取中"
            prompt += f"   实时价格: {price_str} | 24H成交额: {volume_str}\n"
            
            # 获取时间框架数据（从market_snapshot中）
            timeframes = symbol_timeframes_map.get(symbol) or {}
            if timeframes:
                prompt += f"   {symbol}市场历史指标数据: {json.dumps(timeframes, indent=2, ensure_ascii=False, default=str)}\n"
            else:
                prompt += f"   {symbol}市场历史指标数据: 无\n"
            
            prompt += "\n"

        prompt += "\n账户约束：\n"
        prompt += f"- 可用现金: ${available_cash:.2f}\n"
        prompt += f"- 当前持仓数: {occupied}\n"
        prompt += f"- 最大持仓上限: {max_positions if max_positions is not None else '未限制'}\n"
        prompt += f"- 仍可开仓数量: {available_slots}\n"

        constraints_block = (constraints_text or '').strip()
        if constraints_block:
            prompt += "\n策略约束：\n" + constraints_block + "\n"

        prompt += """
执行要求：
1. 仅按上述候选与约束做出buy_to_enter(开多)或sell_to_enter(开空)或hold决策。
2. 写明每个决策的依据与风控考量，必要时可保持观望。
3. 严格按照下方 JSON 模板返回，仅包含需要动作的合约。

【重要说明】
- buy_to_enter：开多仓（做多），系统会自动设置position_side为LONG
- sell_to_enter：开空仓（做空），系统会自动设置position_side为SHORT
- 不需要返回position_side字段，系统会根据signal自动确定

请返回：
```
{
  "cot_trace": ["推理步骤..."],
  "decisions": {
    "SYMBOL": {
      "signal": "buy_to_enter|sell_to_enter|hold",
      "quantity": 100,
      "leverage": 10,
      "confidence": 0.8,
      "risk_budget_pct": 3,
      "profit_target": 12345.0,
      "stop_loss": 12000.0,
      "justification": "理由"
    }
  }
}
```
"""

        return prompt

    def _build_sell_prompt(self, portfolio: Dict, market_state: Dict, account_info: Dict,
                           constraints_text: Optional[str]) -> str:
        """
        构建卖出决策的提示词
        
        根据当前持仓、市场状态、账户信息等构建完整的提示词，
        用于发送给LLM生成卖出/平仓决策。
        
        Args:
            portfolio: 持仓组合信息，包含positions列表
            market_state: 市场状态字典，key为交易对符号
            account_info: 账户信息
            constraints_text: 策略约束文本（sell_prompt）
        
        Returns:
            str: 完整的提示词文本，包含：
                - 角色定义（USDS-M合约专业人士）
                - 当前持仓详情（数量、方向、均价、当前价、盈亏）
                - 持仓币种的技术指标数据
                - 账户概况（总值、可用现金、累计收益率）
                - 策略约束（用户自定义的sell_prompt）
                - 执行要求和JSON模板
        
        Note:
            - 只关注当前持仓，不包含涨幅榜数据
            - 计算每个持仓的盈亏百分比和盈亏金额
            - 支持LONG和SHORT两种持仓方向的盈亏计算
            - 优先使用数据库中的unrealized_profit字段
        """
        prompt = """你是USDS-M合约的专业人士，请使用相关专业知识进行操作，负责判断当前持仓是平仓还是继续持有。
        
注意：重点需要关注当前账户持有的币种。
决策应基于持仓币种本身的价格表现、盈亏情况、风险控制等因素。"""

        prompt += "\n\n当前持仓详情：\n"
        positions = portfolio.get('positions', []) or []
        for pos in positions:
            symbol = pos.get('symbol', '')  # 【字段更新】使用新字段名symbol替代future
            market_info = market_state.get(symbol, {}) if market_state else {}
            current_price = market_info.get('price') or 0.0
            avg_price = pos.get('avg_price', 0.0)
            position_amt = abs(pos.get('position_amt', 0.0))  # 【字段更新】使用新字段名position_amt替代quantity，使用绝对值
            position_side = pos.get('position_side', 'LONG')  # 【字段更新】使用新字段名position_side替代side
            
            # 计算盈亏
            if avg_price > 0 and current_price > 0:
                if position_side.upper() == 'LONG':
                    # 做多：盈亏 = (现价 - 均价) / 均价 * 100
                    pnl_pct = ((current_price - avg_price) / avg_price) * 100
                else:  # SHORT
                    # 做空：盈亏 = (均价 - 现价) / 均价 * 100
                    pnl_pct = ((avg_price - current_price) / avg_price) * 100
                
                # 计算盈亏金额（优先使用数据库中的unrealized_profit字段）
                unrealized_profit = pos.get('unrealized_profit', 0.0)
                if unrealized_profit != 0:
                    pnl_amount = unrealized_profit
                    pnl_pct = (unrealized_profit / (position_amt * avg_price)) * 100 if position_amt * avg_price > 0 else 0.0
                else:
                    # 如果没有，则使用计算值
                    position_value = position_amt * avg_price
                    pnl_amount = position_value * (pnl_pct / 100)
                
                pnl_status = "盈利" if pnl_pct > 0 else "亏损" if pnl_pct < 0 else "持平"
            else:
                # 使用数据库中的unrealized_profit字段
                unrealized_profit = pos.get('unrealized_profit', 0.0)
                pnl_amount = unrealized_profit
                pnl_pct = (unrealized_profit / (position_amt * avg_price)) * 100 if position_amt * avg_price > 0 else 0.0
                pnl_status = "未知"
            
            prompt += (
                f"- {symbol} ({position_side}) 数量: {position_amt:.4f} | "
                f"开仓均价: ${avg_price:.4f} | 当前价格: ${current_price:.4f} | "
                f"盈亏: {pnl_status} {pnl_pct:+.2f}% (约 ${pnl_amount:+.2f})"
            )
            prompt += "\n\n当前持仓的市场历史指标数据：\n"
            
            # 添加市场历史指标数据（如果只有klines，需要计算指标）
            timeframes = market_info.get('indicators', {}).get('timeframes', {})
            if timeframes:
                # 检查是否有指标数据
                has_indicators = False
                first_timeframe = next(iter(timeframes.values()), {})
                if isinstance(first_timeframe, dict):
                    has_indicators = any(key in first_timeframe for key in ['ma', 'macd', 'rsi', 'vol'])
                
                # 如果没有指标且有market_fetcher，计算指标
                if not has_indicators and self.market_fetcher:
                    try:
                        timeframes = self.market_fetcher.calculate_indicators_for_timeframes(timeframes)
                        logger.debug(f"[{self.provider_type}] [卖出决策] 为 {symbol} 计算了技术指标")
                    except Exception as e:
                        logger.warning(f"[{self.provider_type}] [卖出决策] 计算指标失败: {e}")
                
                prompt += f"   {symbol}市场历史指标数据: {json.dumps(timeframes, indent=2, ensure_ascii=False, default=str)}\n"
            else:
                prompt += f"   {symbol}市场历史指标数据: 无\n"
            
            prompt += "\n"

        prompt += "\n账户概况：\n"
        prompt += f"- 账户总值: ${portfolio.get('total_value', 0):.2f}\n"
        prompt += f"- 可用现金: ${portfolio.get('cash', 0):.2f}\n"
        prompt += f"- 累计收益率: {account_info.get('total_return', 0):.2f}%\n"

        constraints_block = (constraints_text or '').strip()
        if constraints_block:
            prompt += "\n策略约束：\n" + constraints_block + "\n"

        prompt += """
执行要求：
1. 仅针对现有持仓给出 close_position 或 stop_loss 或 take_profit 或 hold。
2. 写明每个决策的依据与风控考量，必要时可保持观望。
3. 若决定止损/止盈请给出 quantity数量，price价格（期望价格），stop_price止损/止盈触发价格（必填）,
4. 严格按照下方 JSON 模板返回，仅包含需要动作的合约。

请返回：
```
{
  "cot_trace": ["推理步骤..."],
  "decisions": {
    "SYMBOL": {
      "signal": "close_position|stop_loss|take_profit|hold",
      "quantity": 100,
      "price": 0.0345,
      "stop_price": 0.0325,
      "confidence": 0.8,
      "risk_budget_pct": 3,
      "profit_target": 12345.0,
      "stop_loss": 12000.0,
      "justification": "理由"
    }
  }
}
```
"""

        return prompt

    # ============ LLM API调用方法 ============
    
    def _call_llm(self, prompt: str) -> tuple:
        """
        根据提供商类型调用对应的LLM API
        
        这是一个路由方法，根据provider_type选择具体的API调用方法。
        
        Args:
            prompt: 发送给LLM的提示词文本
        
        Returns:
            tuple: (响应文本, tokens数量)
        
        Raises:
            Exception: API调用失败时抛出异常
        
        Note:
            - 默认使用OpenAI兼容的API
            - 支持的提供商：openai, azure_openai, deepseek, anthropic, gemini
        """
        if self.provider_type in ['openai', 'azure_openai', 'deepseek']:
            return self._call_openai_api(prompt)
        elif self.provider_type == 'anthropic':
            return self._call_anthropic_api(prompt)
        elif self.provider_type == 'gemini':
            return self._call_gemini_api(prompt)
        else:
            # 默认使用OpenAI兼容的API
            return self._call_openai_api(prompt)

    def _call_openai_api(self, prompt: str) -> tuple:
        """
        调用OpenAI兼容的API
        
        支持OpenAI、Azure OpenAI、DeepSeek等兼容OpenAI API格式的提供商。
        使用OpenAI SDK进行调用。
        
        Args:
            prompt: 发送给LLM的提示词文本
        
        Returns:
            tuple: (响应文本, tokens数量)
        
        Raises:
            Exception: API调用失败时抛出异常，包含详细的错误信息
        
        Note:
            - 自动处理base_url，确保以/v1结尾
            - 使用temperature=0.7，max_tokens=2000
            - 系统提示词：专业加密货币交易员，只输出JSON格式
        """
        try:
            base_url = self.api_url.rstrip('/')
            if not base_url.endswith('/v1'):
                if '/v1' in base_url:
                    base_url = base_url.split('/v1')[0] + '/v1'
                else:
                    base_url = base_url + '/v1'

            client = OpenAI(
                api_key=self.api_key,
                base_url=base_url
            )

            response = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional cryptocurrency trader. Output JSON format only."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=2000
            )

            # 返回响应内容和tokens信息
            content = response.choices[0].message.content
            tokens = 0
            if hasattr(response, 'usage') and response.usage:
                tokens = response.usage.total_tokens if hasattr(response.usage, 'total_tokens') else 0
            return content, tokens

        except APIConnectionError as e:
            error_msg = f"API connection failed: {str(e)}"
            logger.error(f"OpenAI API: {error_msg}")
            raise Exception(error_msg)
        except APIError as e:
            error_msg = f"API error ({e.status_code}): {e.message}"
            logger.error(f"OpenAI API: {error_msg}")
            raise Exception(error_msg)
        except Exception as e:
            error_msg = f"OpenAI API call failed: {str(e)}"
            logger.error(f"OpenAI API: {error_msg}")
            import traceback
            logger.error(traceback.format_exc())
            raise Exception(error_msg)

    def _call_anthropic_api(self, prompt: str) -> tuple:
        """
        调用Anthropic Claude API
        
        使用HTTP请求直接调用Anthropic的Claude API。
        
        Args:
            prompt: 发送给LLM的提示词文本
        
        Returns:
            tuple: (响应文本, tokens数量)
        
        Raises:
            Exception: API调用失败时抛出异常，包含详细的错误信息
        
        Note:
            - 使用requests库发送POST请求
            - API版本：2023-06-01
            - 超时时间：60秒
            - 响应格式：result['content'][0]['text']
        """
        try:
            import requests

            base_url = self.api_url.rstrip('/')
            if not base_url.endswith('/v1'):
                base_url = base_url + '/v1'

            url = f"{base_url}/messages"
            headers = {
                'Content-Type': 'application/json',
                'x-api-key': self.api_key,
                'anthropic-version': '2023-06-01'
            }

            data = {
                "model": self.model_name,
                "max_tokens": 2000,
                "system": "You are a professional cryptocurrency trader. Output JSON format only.",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }

            response = requests.post(url, headers=headers, json=data, timeout=60)
            response.raise_for_status()

            result = response.json()
            content = result['content'][0]['text']
            # 提取tokens信息
            tokens = 0
            if 'usage' in result:
                usage = result['usage']
                tokens = usage.get('input_tokens', 0) + usage.get('output_tokens', 0)
            return content, tokens

        except Exception as e:
            error_msg = f"Anthropic API call failed: {str(e)}"
            logger.error(f"Anthropic API: {error_msg}")
            import traceback
            logger.error(traceback.format_exc())
            raise Exception(error_msg)

    def _call_gemini_api(self, prompt: str) -> tuple:
        """
        调用Google Gemini API
        
        使用HTTP请求直接调用Google的Gemini API。
        
        Args:
            prompt: 发送给LLM的提示词文本
        
        Returns:
            tuple: (响应文本, tokens数量)
        
        Raises:
            Exception: API调用失败时抛出异常，包含详细的错误信息
        
        Note:
            - 使用requests库发送POST请求
            - API密钥通过URL参数传递（key）
            - 超时时间：60秒
            - 响应格式：result['candidates'][0]['content']['parts'][0]['text']
        """
        try:
            import requests

            base_url = self.api_url.rstrip('/')
            if not base_url.endswith('/v1'):
                base_url = base_url + '/v1'

            url = f"{base_url}/{self.model_name}:generateContent"
            headers = {
                'Content-Type': 'application/json'
            }
            params = {'key': self.api_key}

            data = {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": f"You are a professional cryptocurrency trader. Output JSON format only.\n\n{prompt}"
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 2000
                }
            }

            response = requests.post(url, headers=headers, params=params, json=data, timeout=60)
            response.raise_for_status()

            result = response.json()
            content = result['candidates'][0]['content']['parts'][0]['text']
            # 提取tokens信息
            tokens = 0
            if 'usageMetadata' in result:
                usage = result['usageMetadata']
                tokens = usage.get('totalTokenCount', 0)
            return content, tokens

        except Exception as e:
            error_msg = f"Gemini API call failed: {str(e)}"
            logger.error(f"Gemini API: {error_msg}")
            import traceback
            logger.error(traceback.format_exc())
            raise Exception(error_msg)

    # ============ 响应处理方法 ============
    
    def _request_decisions(self, prompt: str, decision_type: str = 'unknown', model_id: Optional[int] = None) -> Dict:
        """
        请求LLM生成决策并解析响应
        
        这是决策生成的核心流程：
        1. 计算prompt的token数量
        2. 调用LLM API获取响应
        3. 解析响应中的决策和推理过程
        4. 返回标准格式的结果字典
        
        Args:
            prompt: 发送给LLM的提示词文本
            decision_type: 决策类型，'buy'（买入）或'sell'（卖出）
            model_id: 模型ID（可选），用于日志记录
        
        Returns:
            Dict: 包含以下字段的字典：
                - decisions: 解析后的决策字典
                - prompt: 原始提示词（用于记录）
                - raw_response: LLM的原始响应文本（用于调试）
                - cot_trace: 推理过程文本（Chain of Thought）
        
        Raises:
            Exception: LLM API调用失败时抛出异常
        """
        # 计算prompt的token数量
        token_count = self._count_tokens(prompt)
        decision_type_name = '买入' if decision_type == 'buy' else '卖出' if decision_type == 'sell' else '未知'
        model_info = f"Model ID: {model_id}" if model_id else "Model ID: 未知"
        
        logger.info(f"[{self.provider_type}] [{decision_type_name}决策] {model_info} | "
                   f"Prompt Token数量: {token_count} | 模型: {self.model_name}")
        
        logger.info(f"[{self.provider_type}] 开始调用LLM API请求决策，模型: {self.model_name}")
        response, tokens = self._call_llm(prompt)
        decisions, cot_trace = self._parse_response(response)
        logger.info(f"[{self.provider_type}] LLM决策生成完成，共生成 {len(decisions)} 个交易对的决策，使用tokens: {tokens}")
        return {
            'decisions': decisions,
            'prompt': prompt,
            'raw_response': response,
            'cot_trace': cot_trace,
            'tokens': tokens
        }
    
    def _count_tokens(self, text: str) -> int:
        """
        计算文本的token数量
        
        优先使用tiktoken库进行精确计算，如果不可用则使用简单估算。
        对于OpenAI模型，使用cl100k_base编码；对于其他模型，使用简单估算。
        
        Args:
            text: 要计算token数量的文本
        
        Returns:
            int: token数量
        """
        if not text:
            return 0
        
        if TIKTOKEN_AVAILABLE:
            try:
                # 根据模型类型选择编码器
                # OpenAI模型（gpt-3.5, gpt-4等）使用cl100k_base
                # 其他模型也尝试使用cl100k_base作为通用编码器
                if 'gpt' in self.model_name.lower() or 'o1' in self.model_name.lower():
                    encoding = tiktoken.get_encoding("cl100k_base")
                else:
                    # 对于其他模型，尝试使用cl100k_base，如果失败则使用简单估算
                    try:
                        encoding = tiktoken.get_encoding("cl100k_base")
                    except:
                        # 如果无法获取编码器，使用简单估算
                        return len(text) // 4
                
                return len(encoding.encode(text))
            except Exception as e:
                logger.warning(f"Token计算失败，使用简单估算: {e}")
                # 如果tiktoken计算失败，使用简单估算
                return len(text) // 4
        else:
            # 简单估算：平均每个token约4个字符
            return len(text) // 4

    def _parse_response(self, response: str) -> Tuple[Dict, Optional[str]]:
        """
        解析LLM响应并提取决策
        
        从LLM返回的文本中提取JSON格式的决策数据。
        支持多种格式：
        - 包含```json代码块
        - 包含```代码块
        - 纯JSON文本
        
        Args:
            response: LLM返回的原始响应文本
        
        Returns:
            Tuple[Dict, Optional[str]]: 
                - decisions: 决策字典，key为交易对符号，value为决策详情
                - cot_trace: 推理过程文本（如果存在）
        
        Note:
            - 如果响应格式不正确，返回空字典
            - 支持两种JSON格式：
                1. {"decisions": {...}, "cot_trace": [...]}
                2. 直接是决策字典 {...}
            - JSON解析失败时记录错误日志，返回空字典
        """
        response = response.strip()

        if '```json' in response:
            response = response.split('```json')[1].split('```')[0]
        elif '```' in response:
            response = response.split('```')[1].split('```')[0]

        cot_trace = None
        decisions: Dict = {}
        try:
            parsed = json.loads(response.strip())
            if isinstance(parsed, dict) and 'decisions' in parsed:
                cot_trace = parsed.get('cot_trace')
                decisions = parsed.get('decisions') or {}
            elif isinstance(parsed, dict):
                decisions = parsed
            else:
                decisions = {}
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse failed: {e}")
            logger.debug(f"Response data:\n{response}")
            decisions = {}

        if not isinstance(decisions, dict):
            decisions = {}

        return decisions, self._stringify_cot_trace(cot_trace)

    def _stringify_cot_trace(self, cot_trace) -> Optional[str]:
        """
        将推理过程（Chain of Thought）转换为字符串格式
        
        支持多种输入格式：
        - None: 返回None
        - str: 直接返回（去除首尾空白）
        - list/tuple: 将每个元素转换为字符串，用换行符连接
        - 其他类型: 尝试JSON序列化或转换为字符串
        
        Args:
            cot_trace: 推理过程数据，可能是None、字符串、列表、字典等
        
        Returns:
            Optional[str]: 格式化后的推理过程文本，如果输入为None或空则返回None
        
        Note:
            - 列表中的非字符串元素会被JSON序列化
            - 空字符串或空列表会返回None
        """
        if cot_trace is None:
            return None
        if isinstance(cot_trace, str):
            return cot_trace.strip() or None
        if isinstance(cot_trace, (list, tuple)):
            cleaned = []
            for item in cot_trace:
                if isinstance(item, str):
                    step = item.strip()
                    if step:
                        cleaned.append(step)
                else:
                    cleaned.append(json.dumps(item, ensure_ascii=False))
            return '\n'.join(cleaned) or None
        try:
            return json.dumps(cot_trace, ensure_ascii=False)
        except TypeError:
            return str(cot_trace)

