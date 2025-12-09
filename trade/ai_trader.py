"""
AI Trader - LLM-based trading decision maker
Supports multiple LLM providers: OpenAI, Anthropic, Gemini, DeepSeek
"""
import json
import logging
import common.config as app_config
from typing import Dict, Optional, Tuple, List
from openai import OpenAI, APIConnectionError, APIError


logger = logging.getLogger(__name__)


class AITrader:
    def __init__(self, provider_type: str, api_key: str, api_url: str, model_name: str):
        """Initialize AI trader with provider configuration"""
        self.provider_type = provider_type.lower()
        self.api_key = api_key
        self.api_url = api_url
        self.model_name = model_name

    # ============ Public Decision Methods ============

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
        【改造方法】Make buy decision based on candidates
        
        【symbol_source参数说明】
        此参数用于标识候选交易对的数据来源，影响prompt的构建：
        - 'leaderboard'（默认）：候选来自涨跌榜，prompt会说明"来自实时涨跌幅榜"
        - 'future'：候选来自合约配置信息表，prompt会说明"来自合约配置信息表"
        
        这样AI模型可以理解交易对的来源，有助于做出更准确的决策。
        
        Args:
            candidates: 候选交易对列表（可能来自涨跌榜或futures表）
            portfolio: 持仓组合信息
            account_info: 账户信息
            constraints: 约束条件
            constraints_text: 约束文本
            market_snapshot: 市场快照数据
            symbol_source: 【新增参数】数据源类型，'future'（合约配置信息）或'leaderboard'（涨跌榜，默认）
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
        """Make sell/close position decision based on current holdings.
        
        此方法只处理账户本身现有持有的币，决定是持有还是平仓。
        不需要获取任何 market_snapshot 涨幅榜信息。
        
        Args:
            portfolio: 当前持仓组合信息
            market_state: 市场状态（包含持仓币种的实时价格等信息）
            account_info: 账户信息
            constraints_text: 策略约束文本
            
        Returns:
            包含决策结果的字典
        """
        if not portfolio.get('positions'):
            return {'decisions': {}, 'prompt': None, 'raw_response': None, 'cot_trace': None, 'skipped': True}

        prompt = self._build_sell_prompt(portfolio, market_state, account_info, constraints_text)
        return self._request_decisions(prompt)

    # ============ Prompt Building Methods ============

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
        【改造方法】Build prompt for buy decision
        
        【symbol_source参数说明】
        此参数用于调整prompt中关于候选交易对来源的描述：
        - 'future'：说明"来自合约配置信息表"，适用于全市场扫描策略
        - 'leaderboard'（默认）：说明"来自实时涨跌幅榜"，适用于关注市场热点的策略
        
        这样AI模型可以理解交易对的来源，有助于做出更准确的决策。
        
        Args:
            candidates: 候选交易对列表
            portfolio: 持仓组合信息
            account_info: 账户信息
            constraints: 约束条件
            constraints_text: 约束文本
            market_snapshot: 市场快照数据
            symbol_source: 【新增参数】数据源类型，'future'（合约配置信息）或'leaderboard'（涨跌榜，默认）
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
        """Build prompt for sell/close position decision.
        
        此方法只关注当前持仓信息，不包含涨幅榜数据。
        决策基于持仓币种本身的表现和账户状态。
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

    # ============ LLM API Call Methods ============

    def _call_llm(self, prompt: str) -> str:
        """Call LLM API based on provider type"""
        if self.provider_type in ['openai', 'azure_openai', 'deepseek']:
            return self._call_openai_api(prompt)
        elif self.provider_type == 'anthropic':
            return self._call_anthropic_api(prompt)
        elif self.provider_type == 'gemini':
            return self._call_gemini_api(prompt)
        else:
            # Default to OpenAI-compatible API
            return self._call_openai_api(prompt)

    def _call_openai_api(self, prompt: str) -> str:
        """Call OpenAI-compatible API"""
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
        """Call Anthropic Claude API"""
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
        """Call Google Gemini API"""
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

    # ============ Response Processing Methods ============

    def _request_decisions(self, prompt: str) -> Dict:
        """Request decisions from LLM and parse response"""
        response = self._call_llm(prompt)
        decisions, cot_trace = self._parse_response(response)
        return {
            'decisions': decisions,
            'prompt': prompt,
            'raw_response': response,
            'cot_trace': cot_trace
        }

    def _parse_response(self, response: str) -> Tuple[Dict, Optional[str]]:
        """Parse LLM response JSON and extract decisions"""
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
        """Convert CoT trace to string format"""
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
