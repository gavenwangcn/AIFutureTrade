import json
import logging
from typing import Dict, Optional, Tuple, List
from openai import OpenAI, APIConnectionError, APIError

try:
    import config as app_config
except ImportError:  # pragma: no cover
    import config_example as app_config

logger = logging.getLogger(__name__)

class AITrader:
    def __init__(self, provider_type: str, api_key: str, api_url: str, model_name: str):
        self.provider_type = provider_type.lower()
        self.api_key = api_key
        self.api_url = api_url
        self.model_name = model_name
    
    def make_decision(self, market_state: Dict, portfolio: Dict, 
                     account_info: Dict, market_snapshot: Optional[List[Dict]] = None) -> Dict:
        prompt = self._build_prompt(market_state, portfolio, account_info, market_snapshot)
        return self._request_decisions(prompt)

    def make_buy_decision(
        self,
        candidates: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        constraints: Optional[Dict] = None,
        constraints_text: Optional[str] = None,
        market_snapshot: Optional[List[Dict]] = None
    ) -> Dict:
        if not candidates:
            return {'decisions': {}, 'prompt': None, 'raw_response': None, 'cot_trace': None, 'skipped': True}

        limit = getattr(app_config, 'PROMPT_MARKET_SYMBOL_LIMIT', 5)
        max_candidates = max(1, int(limit))
        limited_candidates = candidates[:max_candidates]

        prompt = self._build_buy_prompt(limited_candidates, portfolio, account_info, constraints or {}, constraints_text)
        return self._request_decisions(prompt)

    def make_sell_decision(
        self,
        portfolio: Dict,
        market_state: Dict,
        account_info: Dict,
        constraints_text: Optional[str] = None,
        market_snapshot: Optional[List[Dict]] = None
    ) -> Dict:
        if not portfolio.get('positions'):
            return {'decisions': {}, 'prompt': None, 'raw_response': None, 'cot_trace': None, 'skipped': True}

        prompt = self._build_sell_prompt(portfolio, market_state, account_info, constraints_text, market_snapshot)
        return self._request_decisions(prompt)
    
    def _build_prompt(self, market_state: Dict, portfolio: Dict, 
                     account_info: Dict, market_snapshot: Optional[List[Dict]] = None) -> str:
        prompt = """你是一名专业的加密货币量化交易员，负责在合规前提下为账户制定交易计划。

市场行情 (价格单位：美元)：
"""
        prompt += self._format_market_snapshot(market_snapshot)
        
        prompt += f"""
账户状态:
- 初始资金: ${account_info['initial_capital']:.2f}
- 账户总值: ${portfolio['total_value']:.2f}
- 可用现金: ${portfolio['cash']:.2f}
- 总收益率: {account_info['total_return']:.2f}%

当前持仓:
"""
        if portfolio['positions']:
            for pos in portfolio['positions']:
                prompt += f"- {pos['future']} {pos['side']} {pos['quantity']:.4f} @ ${pos['avg_price']:.2f}\n"
        else:
            prompt += "None\n"
        
        prompt += """
交易约束:
1. 仅允许 buy_to_enter (买入开仓)、close_position (卖出平仓)、hold (观望)。暂不支持做空。
2. 保持持仓数量≤3，只在具备明显优势时开新仓。
3. 单笔投入资金≤可用现金的5%，以合理数量下单；若模型给出的数量超出可承受范围，需要下调到最大可买数量。
4. 设置止盈/止损与理由，综合相关K线(周线、日线、四小时线、一小时线、15分钟线、5分钟线、一分钟线)以及这些K线的MA均线：(5、20、60、99)和相关K线的(MACD、RSI、VOL)指标、24小时成交额USDT、基本趋势等因素。
5. 优先考虑高流动性合约，避免频繁换手；加密货币市场24小时交易，可随时平仓。

仅输出以下 JSON 结构，不要添加额外文本:
```
{
  "cot_trace": [
    "步骤1：……",
    "步骤2：……"
  ],
  "decisions": {
    "BTC": {
      "signal": "buy_to_enter|close_position|hold",
      "quantity": 0.01,
      "leverage": 1,
      "confidence": 0.75,
      "risk_budget_pct": 3,
      "profit_target": 50000.0,
      "stop_loss": 45000.0,
      "justification": "理由"
    }
  }
}
```

说明:
- `cot_trace` 用于记录3-5步推理过程，可为字符串数组。
- `decisions` 字段同上，只列出需要动作的币种。
"""
        
        return prompt

    def _format_market_snapshot(self, market_snapshot: Optional[List[Dict]]) -> str:
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
                close = fmt_number(tf.get('close'))
                ma = tf.get('ma') or {}
                ma_text = ', '.join(
                    [f"MA{length}:{fmt_number(ma.get(f'ma{length}'))}" for length in (5, 20, 60, 99)]
                )
                macd = fmt_number(tf.get('macd'))
                rsi = fmt_number(tf.get('rsi'))
                vol = fmt_number(tf.get('vol'), precision=2)
                lines.append(
                    f"   - {label}: close={close}, {ma_text}, MACD={macd}, RSI={rsi}, VOL={vol}"
                )

        return '\n'.join(lines) + '\n'
    
    def _build_buy_prompt(
        self,
        candidates: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        constraints: Dict,
        constraints_text: Optional[str]
    ) -> str:
        max_positions = constraints.get('max_positions')
        occupied = constraints.get('occupied', len(portfolio.get('positions') or []))
        available_cash = constraints.get('available_cash', portfolio.get('cash', 0))
        available_slots = max(0, max_positions - occupied) if isinstance(max_positions, int) else 'N/A'

        prompt = """你是USDS-M合约的AI买入策略模块，只能在给定的候选列表中挑选要买入的合约。"""
        limit = getattr(app_config, 'PROMPT_MARKET_SYMBOL_LIMIT', 5)
        prompt += f"\n\n候选合约（来自实时涨跌幅榜，最多 {limit} 个）：\n"
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
            if market_info.get('indicators'):
                tf = market_info['indicators']
                prompt += f" | RSI14: {tf.get('rsi_14', 'N/A')}"
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
    
    def _call_llm(self, prompt: str) -> str:
        """Call LLM API based on provider type"""
        # OpenAI-compatible providers (same format)
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
    
    
    def _parse_response(self, response: str) -> Tuple[Dict, Optional[str]]:
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

    def _request_decisions(self, prompt: str) -> Dict:
        response = self._call_llm(prompt)
        decisions, cot_trace = self._parse_response(response)
        return {
            'decisions': decisions,
            'prompt': prompt,
            'raw_response': response,
            'cot_trace': cot_trace
        }

    def _stringify_cot_trace(self, cot_trace) -> Optional[str]:
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
