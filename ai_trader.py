"""
AI Trader - LLM-based trading decision maker
Supports multiple LLM providers: OpenAI, Anthropic, Gemini, DeepSeek
"""
import json
import logging
import config as app_config
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
        market_snapshot: Optional[List[Dict]] = None
    ) -> Dict:
        """Make buy decision based on candidates from leaderboard"""
        if not candidates:
            return {'decisions': {}, 'prompt': None, 'raw_response': None, 'cot_trace': None, 'skipped': True}

        prompt = self._build_buy_prompt(candidates, portfolio, account_info, constraints or {}, constraints_text)
        return self._request_decisions(prompt)

    def make_sell_decision(
        self,
        portfolio: Dict,
        market_state: Dict,
        account_info: Dict,
        constraints_text: Optional[str] = None,
        market_snapshot: Optional[List[Dict]] = None
    ) -> Dict:
        """Make sell/close position decision based on current holdings"""
        if not portfolio.get('positions'):
            return {'decisions': {}, 'prompt': None, 'raw_response': None, 'cot_trace': None, 'skipped': True}

        prompt = self._build_sell_prompt(portfolio, market_state, account_info, constraints_text, market_snapshot)
        return self._request_decisions(prompt)

    # ============ Prompt Building Methods ============

    def _build_buy_prompt(
        self,
        candidates: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        constraints: Dict,
        constraints_text: Optional[str]
    ) -> str:
        """Build prompt for buy decision"""
        max_positions = constraints.get('max_positions')
        occupied = constraints.get('occupied', len(portfolio.get('positions') or []))
        available_cash = constraints.get('available_cash', portfolio.get('cash', 0))
        available_slots = max(0, max_positions - occupied) if isinstance(max_positions, int) else 'N/A'

        prompt = """你是USDS-M合约的AI买入策略模块，只能在给定的候选列表中挑选要买入的合约。"""
        prompt += f"\n\n候选合约（来自实时涨跌幅榜，共 {len(candidates)} 个）：\n"
        prompt += self._format_market_snapshot(candidates)

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
1. 仅按上述候选与约束做出 buy_to_enter 或 hold 决策。
2. 若需加仓或跳过，请写明理由与风险控制说明。
3. 严格按照下方 JSON 模板返回，仅包含需要动作的合约。

请返回：
```
{
  "cot_trace": ["推理步骤..."],
  "decisions": {
    "SYMBOL": {
      "signal": "buy_to_enter|hold",
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
                           constraints_text: Optional[str], market_snapshot: Optional[List[Dict]] = None) -> str:
        """Build prompt for sell/close position decision"""
        prompt = """你是USDS-M合约的AI卖出/风控模块，负责判断当前持仓是平仓还是继续持有。"""

        if market_snapshot:
            prompt += "\n\n市场行情（涨跌幅榜快照）：\n"
            prompt += self._format_market_snapshot(market_snapshot)

        prompt += "\n\n当前持仓：\n"
        positions = portfolio.get('positions', []) or []
        for pos in positions:
            symbol = pos['future']
            market_info = market_state.get(symbol, {}) if market_state else {}
            current_price = market_info.get('price')
            prompt += (
                f"- {symbol} {pos['side']} 数量 {pos['quantity']:.4f} @ ${pos['avg_price']:.4f}"
                f" | 现价: ${current_price:.4f if current_price else 0:.4f}"
            )
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
1. 仅针对现有持仓给出 close_position 或 hold。
2. 写明每个决策的依据与风控考量，必要时可保持观望。
3. 严格按照买入模块相同 JSON 结构输出，并包含 cot_trace。
"""

        return prompt

    def _format_market_snapshot(self, market_snapshot: Optional[List[Dict]]) -> str:
        """Format market snapshot data for prompt"""
        if not market_snapshot:
            return "暂无可用行情数据（涨跌幅榜为空）\n"

        timeframe_labels = [
            ('1w', '周线'),
            ('1d', '日线'),
            ('4h', '4小时'),
            ('1h', '1小时'),
            ('15m', '15分钟'),
            ('5m', '5分钟'),
            ('1m', '1分钟'),
        ]

        def fmt_number(value, precision=4, prefix='', suffix=''):
            try:
                if value is None:
                    return '--'
                return f"{prefix}{float(value):.{precision}f}{suffix}"
            except (TypeError, ValueError):
                return '--'

        lines = []
        for idx, entry in enumerate(market_snapshot, start=1):
            symbol = entry.get('symbol', 'N/A')
            contract_symbol = entry.get('contract_symbol') or f"{symbol}USDT"
            price = fmt_number(entry.get('price'))
            volume = fmt_number(entry.get('quote_volume'), precision=2)
            lines.append(f"{idx}. {symbol} / {contract_symbol}")
            lines.append(f"   实时价格: ${price} | 24H成交额: {volume} USDT")
            timeframes = entry.get('timeframes') or {}
            for key, label in timeframe_labels:
                tf = timeframes.get(key)
                if not tf:
                    continue
                
                # 新格式：{kline: {}, ma: {}, macd: {}, rsi: {}, vol: {}}
                kline = tf.get('kline', {})
                close = fmt_number(kline.get('close') or tf.get('close'))
                ma = tf.get('ma') or {}
                ma_text = ', '.join(
                    [f"MA{length}:{fmt_number(ma.get(f'ma{length}'))}" for length in (5, 20, 60, 99)]
                )
                
                # MACD 新格式：{dif: float, dea: float, bar: float}
                macd_data = tf.get('macd', {})
                if isinstance(macd_data, dict):
                    macd_text = f"DIF:{fmt_number(macd_data.get('dif'))}, DEA:{fmt_number(macd_data.get('dea'))}, BAR:{fmt_number(macd_data.get('bar'))}"
                else:
                    macd_text = fmt_number(macd_data)
                
                # RSI 新格式：{rsi6: float, rsi9: float}
                rsi_data = tf.get('rsi', {})
                if isinstance(rsi_data, dict):
                    rsi_text = f"RSI6:{fmt_number(rsi_data.get('rsi6'))}, RSI9:{fmt_number(rsi_data.get('rsi9'))}"
                else:
                    rsi_text = fmt_number(rsi_data)
                
                vol = fmt_number(tf.get('vol'), precision=2)
                lines.append(
                    f"   - {label}: close={close}, {ma_text}, MACD({macd_text}), RSI({rsi_text}), VOL={vol}"
                )

        return '\n'.join(lines) + '\n'

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
