# 策略代码验证一致性检查

本文档确保所有策略代码相关文件与Java Prompt模板保持一致。

## 方法签名要求

### execute_buy_decision 方法

**标准签名（必须严格遵循）：**
```python
def execute_buy_decision(
    self,
    candidates: List[Dict],
    portfolio: Dict,
    account_info: Dict,
    market_state: Dict
) -> Dict[str, Dict]:
```

**参数说明：**
- 总共 **5个参数**（包括 self）
- 参数顺序：`self`, `candidates`, `portfolio`, `account_info`, `market_state`
- 参数类型：`List[Dict]`, `Dict`, `Dict`, `Dict`
- 返回类型：`Dict[str, Dict]`

## 文件一致性检查清单

### ✅ 1. Java Prompt 模板
**文件：** `backend/src/main/resources/prompts/strategy_buy_prompt.txt`
- ✅ 要求5个参数（self + 4个）
- ✅ 参数名称：`self`, `candidates`, `portfolio`, `account_info`, `market_state`
- ✅ 参数类型：`List[Dict]`, `Dict`, `Dict`, `Dict`
- ✅ 返回类型：`Dict[str, Dict]`

### ✅ 2. Python 抽象基类
**文件：** `trade/strategy/strategy_template_buy.py`
- ✅ 定义5个参数（self + 4个）
- ✅ 参数名称：`self`, `candidates`, `portfolio`, `account_info`, `market_state`
- ✅ 参数类型：`List[Dict]`, `Dict`, `Dict`, `Dict`
- ✅ 返回类型：`Dict[str, Dict]`

### ✅ 3. 代码执行器
**文件：** `trade/strategy/strategy_code_executor.py`
- ✅ 调用时传递4个参数（不包括self）
- ✅ 参数：`candidates`, `portfolio`, `account_info`, `market_state`
- ✅ 不再传递 `symbol_source` 参数

### ✅ 4. 代码测试器
**文件：** `trade/strategy/strategy_code_tester_buy.py`
- ✅ 期望5个参数（self + 4个）
- ✅ 验证参数数量：`expected_args = 5`
- ✅ 验证参数名称和类型

### ✅ 5. 示例代码
**文件：** `trade/strategy/strategy_example_buy.py`
- ✅ 实现5个参数（self + 4个）
- ✅ 参数名称：`self`, `candidates`, `portfolio`, `account_info`, `market_state`
- ✅ 参数类型：`List[Dict]`, `Dict`, `Dict`, `Dict`
- ✅ 返回类型：`Dict[str, Dict]`

### ✅ 6. Python Prompt 模板
**文件：** `trade/strategy/strategy_prompt_template_buy.py`
- ✅ 模板包含5个参数（self + 4个）
- ✅ 参数名称：`self`, `candidates`, `portfolio`, `account_info`, `market_state`
- ✅ 参数类型：`List[Dict]`, `Dict`, `Dict`, `Dict`

## 已移除的参数

### ❌ symbol_source
- **已从所有trader接口移除**
- **已从策略方法签名移除**
- **仅在trading_engine内部使用**（用于决定数据来源）
- **market_state中已包含source信息**（如果需要）

## 验证测试

运行以下测试确保一致性：

```python
# 测试1: 验证抽象基类签名
from trade.strategy.strategy_template_buy import StrategyBaseBuy
import inspect
sig = inspect.signature(StrategyBaseBuy.execute_buy_decision)
assert len(sig.parameters) == 5, f"期望5个参数，实际{len(sig.parameters)}个"
params = list(sig.parameters.keys())
assert params == ['self', 'candidates', 'portfolio', 'account_info', 'market_state']

# 测试2: 验证测试器期望值
from trade.strategy.strategy_code_tester_buy import StrategyCodeTesterBuy
# 测试器内部期望值应为5

# 测试3: 验证示例代码
from trade.strategy.strategy_example_buy import ExampleBuyStrategy
sig = inspect.signature(ExampleBuyStrategy.execute_buy_decision)
assert len(sig.parameters) == 5, f"期望5个参数，实际{len(sig.parameters)}个"
```

## 注意事项

1. **参数顺序必须完全一致**：`self`, `candidates`, `portfolio`, `account_info`, `market_state`
2. **不能添加额外参数**：如 `symbol_source` 等
3. **不能删除任何参数**：所有5个参数都是必需的
4. **类型注解必须匹配**：`List[Dict]`, `Dict`, `Dict`, `Dict`
5. **返回类型必须匹配**：`Dict[str, Dict]`

## 更新历史

- 2025-12-21: 移除 `symbol_source` 参数，统一为5个参数（self + 4个）
- 2025-12-21: 修复测试器期望值，从4个参数更正为5个参数

