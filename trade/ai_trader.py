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


logger = logging.getLogger(__name__)


class AITrader:
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
    
    def __init__(self, provider_type: str, api_key: str, api_url: str, model_name: str):
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
        """
        self.provider_type = provider_type.lower()
        self.api_key = api_key
        self.api_url = api_url
        self.model_name = model_name

    # ============ 公共决策方法 ============
    
    def make_buy_decision(
        self,
        candidates: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        constraints: Optional[Dict] = None,
        constraints_text: Optional[str] = None,
        market_snapshot: Optional[List[Dict]] = None,
        symbol_source: str = 'leaderboard'
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
            constraints: 约束条件字典，包含：
                - max_positions: 最大持仓数量
                - occupied: 已占用持仓数
                - available_cash: 可用现金
            constraints_text: 策略约束文本（从model_prompts表获取的buy_prompt）
            market_snapshot: 市场快照数据列表，每个元素包含：
                - symbol: 交易对符号
                - timeframes: 多时间周期的技术指标数据
            symbol_source: 数据源类型，影响prompt构建：
                - 'leaderboard'（默认）：候选来自涨跌榜，说明"来自实时涨跌幅榜"
                - 'future'：候选来自合约配置信息表，说明"来自合约配置信息表"
        
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
        """
        if not candidates:
            return {'decisions': {}, 'prompt': None, 'raw_response': None, 'cot_trace': None, 'skipped': True}

        # 【传递symbol_source】将数据源类型传递给prompt构建方法，用于调整prompt文本
        prompt = self._build_buy_prompt(candidates, portfolio, account_info, constraints or {}, constraints_text, market_snapshot, symbol_source)
        return self._request_decisions(prompt)

    def make_sell_decision(
        self,
        portfolio: Dict,
        market_state: Dict,
        account_info: Dict,
        constraints_text: Optional[str] = None
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
            constraints_text: 策略约束文本（从model_prompts表获取的sell_prompt）
        
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
            - stop_loss和take_profit需要提供stop_price（触发价格）
        """
        if not portfolio.get('positions'):
            return {'decisions': {}, 'prompt': None, 'raw_response': None, 'cot_trace': None, 'skipped': True}

        prompt = self._build_sell_prompt(portfolio, market_state, account_info, constraints_text)
        return self._request_decisions(prompt)

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
      "quantity": 0.1,
      "leverage": 1,
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
            
            # 添加市场历史指标数据
            timeframes = market_info.get('indicators', {}).get('timeframes', {})
            if timeframes:
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
      "quantity": 1,
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
    
    def _call_llm(self, prompt: str) -> str:
        """
        根据提供商类型调用对应的LLM API
        
        这是一个路由方法，根据provider_type选择具体的API调用方法。
        
        Args:
            prompt: 发送给LLM的提示词文本
        
        Returns:
            str: LLM返回的原始响应文本
        
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

    def _call_openai_api(self, prompt: str) -> str:
        """
        调用OpenAI兼容的API
        
        支持OpenAI、Azure OpenAI、DeepSeek等兼容OpenAI API格式的提供商。
        使用OpenAI SDK进行调用。
        
        Args:
            prompt: 发送给LLM的提示词文本
        
        Returns:
            str: LLM返回的原始响应文本
        
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

            return response.choices[0].message.content

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

    def _call_anthropic_api(self, prompt: str) -> str:
        """
        调用Anthropic Claude API
        
        使用HTTP请求直接调用Anthropic的Claude API。
        
        Args:
            prompt: 发送给LLM的提示词文本
        
        Returns:
            str: LLM返回的原始响应文本
        
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
            return result['content'][0]['text']

        except Exception as e:
            error_msg = f"Anthropic API call failed: {str(e)}"
            logger.error(f"Anthropic API: {error_msg}")
            import traceback
            logger.error(traceback.format_exc())
            raise Exception(error_msg)

    def _call_gemini_api(self, prompt: str) -> str:
        """
        调用Google Gemini API
        
        使用HTTP请求直接调用Google的Gemini API。
        
        Args:
            prompt: 发送给LLM的提示词文本
        
        Returns:
            str: LLM返回的原始响应文本
        
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
            return result['candidates'][0]['content']['parts'][0]['text']

        except Exception as e:
            error_msg = f"Gemini API call failed: {str(e)}"
            logger.error(f"Gemini API: {error_msg}")
            import traceback
            logger.error(traceback.format_exc())
            raise Exception(error_msg)

    # ============ 响应处理方法 ============
    
    def _request_decisions(self, prompt: str) -> Dict:
        """
        请求LLM生成决策并解析响应
        
        这是决策生成的核心流程：
        1. 调用LLM API获取响应
        2. 解析响应中的决策和推理过程
        3. 返回标准格式的结果字典
        
        Args:
            prompt: 发送给LLM的提示词文本
        
        Returns:
            Dict: 包含以下字段的字典：
                - decisions: 解析后的决策字典
                - prompt: 原始提示词（用于记录）
                - raw_response: LLM的原始响应文本（用于调试）
                - cot_trace: 推理过程文本（Chain of Thought）
        
        Raises:
            Exception: LLM API调用失败时抛出异常
        """
        response = self._call_llm(prompt)
        decisions, cot_trace = self._parse_response(response)
        return {
            'decisions': decisions,
            'prompt': prompt,
            'raw_response': response,
            'cot_trace': cot_trace
        }

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
