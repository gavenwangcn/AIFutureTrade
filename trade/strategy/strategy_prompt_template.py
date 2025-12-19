"""
Strategy Prompt Template - 策略代码生成 Prompt 模板

本模板用于指导 AI 根据 strategy_context 生成符合标准的策略代码。
生成的代码必须继承 StrategyBase 类并实现其抽象方法。
"""

STRATEGY_CODE_GENERATION_PROMPT = """你是一个专业的量化交易策略代码生成专家。请根据提供的策略规则（strategy_context）生成符合标准的 Python 策略代码。

## 策略规则（strategy_context）：
{strategy_context}

## 重要要求：

### 1. 必须继承 StrategyBase 类

生成的代码必须是一个继承自 `StrategyBase` 的类，并实现其抽象方法：

```python
from trade.strategy.strategy_template import StrategyBase
from typing import Dict, List

class GeneratedStrategy(StrategyBase):
    def execute_buy_decision(
        self,
        candidates: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        market_state: Dict,
        symbol_source: str
    ) -> Dict[str, Dict]:
        # 实现买入决策逻辑
        decisions = {{}}
        
        # 遍历候选交易对
        for candidate in candidates:
            symbol = candidate.get('symbol', '').upper()
            if not symbol:
                continue
            
            # 获取当前价格（优先从candidate获取，如果没有则从market_state获取）
            current_price = candidate.get('price', 0)
            if current_price <= 0:
                # 从 market_state 获取价格
                symbol_state = market_state.get(symbol, {{}})
                current_price = symbol_state.get('price', 0)
            
            if current_price <= 0:
                continue
            
            # 从 market_state 中获取该交易对的技术指标数据
            symbol_state = market_state.get(symbol, {{}})
            if not symbol_state:
                continue
            
            # 获取技术指标数据
            indicators = symbol_state.get('indicators', {{}})
            timeframes = indicators.get('timeframes', {{}})
            
            # ============ 在这里实现策略逻辑 ============
            # 根据 strategy_context 中的买入策略规则编写代码
            # 1. 计算所需的技术指标（如 MA(99)）
            # 2. 判断是否满足开仓条件
            # 3. 如果满足条件，添加到 decisions 字典中
            
            # 示例：
            # if 满足开多条件:
            #     decisions[symbol] = {{
            #         "signal": "buy_to_enter",
            #         "quantity": 100,
            #         "leverage": 5,
            #         "justification": "理由"
            #     }}
            # elif 满足开空条件:
            #     decisions[symbol] = {{
            #         "signal": "sell_to_enter",
            #         "quantity": 100,
            #         "leverage": 5,
            #         "justification": "理由"
            #     }}
        
        return decisions
    
    def execute_sell_decision(
        self,
        portfolio: Dict,
        market_state: Dict,
        account_info: Dict
    ) -> Dict[str, Dict]:
        # 实现卖出决策逻辑
        decisions = {{}}
        
        # 获取当前持仓
        positions = portfolio.get('positions', []) or []
        
        # 遍历持仓
        for position in positions:
            symbol = position.get('symbol', '').upper()
            if not symbol:
                continue
            
            # 获取持仓信息
            position_amt = abs(position.get('position_amt', 0))
            position_side = position.get('position_side', 'LONG')
            avg_price = position.get('avg_price', 0)
            
            if position_amt <= 0:
                continue
            
            # 从 market_state 中获取该交易对的市场数据
            symbol_market_state = market_state.get(symbol, {{}})
            if not symbol_market_state:
                continue
            
            # 获取当前价格
            current_price = symbol_market_state.get('price', 0)
            if current_price <= 0:
                continue
            
            # 获取技术指标数据
            indicators = symbol_market_state.get('indicators', {{}})
            timeframes = indicators.get('timeframes', {{}})
            
            # ============ 在这里实现策略逻辑 ============
            # 根据 strategy_context 中的卖出策略规则编写代码
            # 1. 计算所需的技术指标（如 MA(99)）
            # 2. 根据持仓方向判断是否满足平仓条件
            # 3. 如果满足条件，添加到 decisions 字典中
            
            # 示例：
            # if position_side == 'LONG' and 满足多单平仓条件:
            #     decisions[symbol] = {{
            #         "signal": "close_position",  # 或 "stop_loss" 或 "take_profit"
            #         "quantity": position_amt,
            #         "price": current_price,
            #         "stop_price": trigger_price,
            #         "leverage": position.get('leverage', 5),
            #         "justification": "理由"
            #     }}
            # elif position_side == 'SHORT' and 满足空单平仓条件:
            #     decisions[symbol] = {{
            #         "signal": "close_position",  # 或 "stop_loss" 或 "take_profit"
            #         "quantity": position_amt,
            #         "price": current_price,
            #         "stop_price": trigger_price,
            #         "leverage": position.get('leverage', 5),
            #         "justification": "理由"
            #     }}
        
        return decisions
```

### 2. 必须使用 TA-Lib 库计算技术指标

- 使用 `talib.SMA()` 计算移动平均线
- 使用 `talib.RSI()` 计算 RSI 指标
- 使用 `talib.MACD()` 计算 MACD 指标
- 等等

### 3. 技术指标数据获取方式（统一使用 market_state）

**买入决策和卖出决策都使用 market_state：**
```python
# market_state 格式: {{"BTC": {{"price": float, "indicators": {{"timeframes": {{"1h": {{"klines": [...]}}, "4h": {{...}}, ...}}}}}}}}

# 买入决策中获取数据：
symbol_state = market_state.get(symbol, {{}})
current_price = symbol_state.get('price', 0)  # 或从 candidate.get('price') 获取
indicators = symbol_state.get('indicators', {{}})
timeframes = indicators.get('timeframes', {{}})
klines_1h = timeframes.get('1h', {{}}).get('klines', [])

# 卖出决策中获取数据：
symbol_market_state = market_state.get(symbol, {{}})
current_price = symbol_market_state.get('price', 0)
indicators = symbol_market_state.get('indicators', {{}})
timeframes = indicators.get('timeframes', {{}})
klines_1h = timeframes.get('1h', {{}}).get('klines', [])

# klines 格式: [{{'open': float, 'high': float, 'low': float, 'close': float, 'volume': float}}, ...]
```

**注意：**
- 买入决策中，当前价格可以从 `candidate.get('price')` 获取，也可以从 `market_state[symbol]['price']` 获取
- 约束条件（如可用现金、持仓数量）可以从 `portfolio` 中获取：
  - `portfolio.get('cash', 0)` - 可用现金
  - `len(portfolio.get('positions', []))` - 当前持仓数量

### 4. 决策格式要求

**买入决策返回值：**
```python
{{
    "SYMBOL": {{
        "signal": "buy_to_enter" | "sell_to_enter",  # 必须
        "quantity": 100,                              # 必须：数量
        "leverage": 5,                                # 必须：杠杆倍数
        "justification": "理由说明"                   # 必须：理由
    }}
}}
```

**卖出决策返回值：**
```python
{{
    "SYMBOL": {{
        "signal": "close_position" | "stop_loss" | "take_profit",  # 必须
        "quantity": 100,                                            # 必须：数量
        "price": 0.0345,                                            # 可选：期望价格
        "stop_price": 0.0325,                                       # 必须：止损/止盈触发价格
        "leverage": 5,                                              # 必须：杠杆倍数
        "justification": "理由说明"                                 # 必须：理由
    }}
}}
```

### 5. 代码质量要求

- 代码必须完整、可执行
- 必须处理边界情况（如数据为空、价格无效、K线数据不足等）
- 必须添加必要的注释说明
- 必须遵循 Python 代码规范
- 必须正确导入 StrategyBase：`from trade.strategy.strategy_template import StrategyBase`

### 6. 策略实现要求

- 严格按照 strategy_context 中的规则实现
- 正确计算技术指标（如 MA(99)）
- 正确判断开仓/平仓条件
- 正确设置仓位比例（如 50% 仓位）
- 正确处理多单和空单的不同逻辑

### 7. 示例策略规则解析

对于以下策略规则：
```
买入策略（5倍杠杆）：
(1) 开多单条件：当 即时价格 > 1.02 × MA(99)值，操作：买入50%仓位
(2) 多单平仓条件：
    条件A：即时价格 < 0.98 × MA(99)值，平仓100%
    条件B：即时价格 > 1.2 × MA(99)值，平仓100%

卖出策略（5倍杠杆）：
(3) 开空单条件：当 即时价格 ≤ 0.98 × MA(99)值，操作：买入50%仓位（做空）
(4) 空单平仓条件：
    条件A：即时价格 > 1.02 × MA(99)值，平仓100%
    条件B：即时价格 < 0.8 × MA(99)值，平仓100%
```

实现要点：
- **execute_buy_decision**: 检查开多单条件（价格 > 1.02 × MA(99)）和开空单条件（价格 ≤ 0.98 × MA(99)）
- **execute_sell_decision**: 根据持仓方向（LONG/SHORT）检查对应的平仓条件
- 使用 `talib.SMA()` 计算 MA(99)，需要至少 99 根 K 线数据
- 仓位计算：50% 仓位需要根据 `portfolio.get('cash', 0)` 和当前价格计算
- 杠杆：统一使用 5 倍杠杆
- **数据获取**：统一使用 `market_state` 获取技术指标数据，不再使用 `market_snapshot` 和 `constraints`

## 请根据提供的 strategy_context 生成完整的策略代码：

生成的代码必须：
1. 导入 StrategyBase：`from trade.strategy.strategy_template import StrategyBase`
2. 定义类继承 StrategyBase：`class GeneratedStrategy(StrategyBase):`
3. 实现 `execute_buy_decision()` 方法
4. 实现 `execute_sell_decision()` 方法
5. 代码必须完整、可执行，不需要额外的实例化代码（系统会自动实例化）

"""


def generate_strategy_code_prompt(strategy_context: str) -> str:
    """
    生成策略代码生成的 Prompt
    
    Args:
        strategy_context: 策略规则文本
    
    Returns:
        str: 完整的 Prompt 文本
    """
    return STRATEGY_CODE_GENERATION_PROMPT.format(strategy_context=strategy_context)


# ============ 示例：使用方式 ============
if __name__ == '__main__':
    # 示例策略内容
    example_strategy_context = """买入策略（5倍杠杆）：
(1) 开多单条件：
    当 即时价格 > 1.02 × MA(99)值
    操作：买入50%仓位

(2) 多单平仓条件：
    条件A：即时价格 < 0.98 × MA(99)值，平仓100%
    条件B：即时价格 > 1.2 × MA(99)值，平仓100%

卖出策略（5倍杠杆）：
(3) 开空单条件：
    当 即时价格 ≤ 0.98 × MA(99)值
    操作：买入50%仓位（做空）

(4) 空单平仓条件：
    条件A：即时价格 > 1.02 × MA(99)值，平仓100%
    条件B：即时价格 < 0.8 × MA(99)值，平仓100%"""
    
    prompt = generate_strategy_code_prompt(example_strategy_context)
    print(prompt)
