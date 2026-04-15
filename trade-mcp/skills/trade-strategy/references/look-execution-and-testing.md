# 盯盘策略：运行上下文精简版（供无完整仓库的 Agent 使用）

本文档**自洽**：不依赖克隆整个 AIFutureTrade 即可理解盯盘策略代码如何被加载、调用、以及如何用**模拟数据**做逻辑验证。若需与线上一致，再以真实仓库中的模块名为准。

---

## 部署与环境：Docker、轮询周期、入口进程

- **典型部署**：盯盘循环跑在 **Docker 容器**中（仓库 `docker-compose.yml` 里 **`model-look`** 服务，镜像基于 `trade/Dockerfile` 构建）。容器内入口为：  
  `python -m trade.start.start_market_look`（见 `trade/start/start_market_look.py`）。  
  需配置 **`MODEL_ID`**（模型/租户上下文）、**MySQL**、以及 **Binance API**（拉行情）等环境变量；具体键名以 compose 与 `trade/common/config.py` 为准。
- **轮询周期**：主循环在 `trade/look_loop.py` 的 `market_look_loop`。每轮从 DB 取 **`execution_status=RUNNING`** 的 `market_look` 行，对**每一行**调用 `LookEngine.execute_look_row`，整轮结束后 **`time.sleep(interval)`**。  
  - `interval` 来自配置 **`MARKET_LOOK_POLL_INTERVAL_SECONDS`**（`trade/common/config.py` 默认 **60**，可通过环境变量覆盖）。  
  - 代码中将 interval **限制在 5～86400 秒**之间。  
  - **默认 60 秒 ≈ 每 1 分钟一轮**；若需约 **2 分钟**一轮，可在部署环境设 **`MARKET_LOOK_POLL_INTERVAL_SECONDS=120`**（属运维配置，**不是**用户策略 Python 里写的周期）。  
  - 循环异常时单次兜底 `sleep(60)` 后再继续。
- **策略代码本身**：仍以 **`execute_look_decision` 每次调用时收到的 `market_state`** 为准；上面周期只决定**多久重新拉一次行情并执行一次策略**，不改变 `market_state` 字段定义。

---

## 端到端主流程精简伪代码（与仓库逻辑等价）

下列片段为 **阅读用精简版**，便于在无全仓库时理解 **`look_loop.py` → `look_engine.py` → `strategy_look_trader.py` → `strategy_code_executor.py`** 的调用关系；行号与异常分支以源码为准。

### A. 轮询入口（`look_loop.py`）

```python
def market_look_loop(auto_run, look_engine, db):
    interval = int(getattr(app_config, "MARKET_LOOK_POLL_INTERVAL_SECONDS", 60))
    interval = max(5, min(86400, interval))   # 5s ~ 24h
    while auto_run:
        rows = market_look_db.list_running()   # RUNNING 的 market_look 行
        for row in rows:
            look_engine.execute_look_row(row)
        time.sleep(interval)
```

### B. 单行盯盘（`look_engine.py` → `strategy_look_trader.py`）

```python
def execute_look_row(self, row):   # LookEngine
    strategy = self.strategys_db.get_strategy_by_id(row["strategy_id"])
    sym_key = normalize_symbol(row["symbol"])   # 如 BTCUSDT -> BTC
    market_state = self.build_market_state_for_symbol(row["symbol"])  # 单品种，无全市场 market_indicators
    if not market_state:
        update_signal_result(...); return summary

    res = self.strategy_trader.make_look_decision(strategy, market_state, sym_key)
    decisions = res.get("decisions") or {}

    if extract_notify_decisions(decisions):
        trim_snapshot(...); enqueue_look_notify(...); status -> SENDING ...
    elif deadline_passed(row):
        emit_timeout_notify(...); status -> ENDED ...
    return summary
```

### C. 盯盘交易器（`strategy_look_trader.py`）

```python
def make_look_decision(self, strategy, market_state, symbol):
    return self.code_executor.execute_strategy_code(
        strategy_code=strategy["strategy_code"],
        strategy_name=strategy.get("name") or "盯盘",
        market_state=market_state,
        decision_type="look",
        look_symbol=symbol,          # 大写基础符号，与 market_state 的 key 一致
    )
    # 返回包装后 dict，含 "decisions"
```

### D. 执行器盯盘分支（`strategy_code_executor.py`）

```python
# execute_strategy_code(..., decision_type="look", look_symbol=...)
decisions = strategy_instance.execute_look_decision(
    symbol=look_symbol.strip().upper(),
    market_state=market_state or {},
)
# 将每个 symbol 下「单 dict」容错为 [dict]，再 {"decisions": decisions}
```

**据此编写「真实风格」测试**：最小化只需 **D + 伪造的 `market_state` + 策略代码字符串**（见第 6 节）；要验证 **enqueue/DB** 则需完整 **B** 与数据库（通常仅在集成环境）。

---

## 1. 执行链路（从代码字符串到决策）

```
策略 Python 字符串
    → StrategyCodeExecutor.execute_strategy_code(..., decision_type="look", look_symbol="BTC", market_state={...})
        → exec(代码) 定义类 → 找到第一个继承 StrategyBaseLook 的子类并实例化
        → strategy_instance.execute_look_decision(symbol=look_symbol, market_state=market_state)
        → 返回值归一化为 Dict[str, List[Dict]] 后包成 {"decisions": ...}
```

**调用盯盘的一方**（概念上）使用 `StrategyLookTrader.make_look_decision(strategy_row, market_state, symbol)`，内部同样走 `execute_strategy_code`，并传入 `strategy` 字典里的 `strategy_code`。

**你必须知道的约束**：

- `decision_type` 必须是字符串 **`"look"`**。
- **`look_symbol`**：合约**基础符号**大写，如 `BTC`（不要带 `USDT` 后缀；测试器里若传入 `BTCUSDT` 会剥成 `BTC`）。
- `market_state`：至少包含 key = `look_symbol` 的那一条合约状态（见下文结构）。

---

## 2. 策略代码契约（生成/审阅时必须满足）

### 2.1 固定导入与基类

- 第一行风格：`from trade.strategy.strategy_template_look import StrategyBaseLook`（真实环境类名固定）。
- 自定义类必须 **`class Xxx(StrategyBaseLook)`**。

### 2.2 必须实现的方法（签名不可改）

```python
def execute_look_decision(self, symbol: str, market_state: Dict) -> Dict[str, List[Dict]]:
    ...
```

- **`symbol`**：与 `market_state` 里使用的 key 一致，为大写基础符号（如 `BTC`）。
- **返回值**：
  - 规范类型：`Dict[str, List[Dict]]`，外层 key 为 **基础符号**（如 `"BTC"`），value 为**列表**（每条为一个决策 dict）。
  - **执行器容错**：若某 symbol 对应的是**单个 dict**（不是 list），会被**自动包成** `[dict]`；空或非法会变成 `[]`。但仍应直接写列表以通过测试器与规范。

### 2.3 企微通知类结果（业务上）

- 需要推送时，列表元素中应包含 **`"signal": "notify"`**（以及 `justification`、`price`、`market_date` 等，按产品约定）。
- **`signal` 为 `hold` 等不会当企微通知处理**（与策略生成 prompt 一致）；不需要通知时应 **`return {}`** 或对 decisions 不放无意义项。

### 2.4 基类能力（精简摘录，行为以真实模块为准）

```python
# 概念摘录 — StrategyBaseLook
class StrategyBaseLook(ABC):
    def __init__(self):
        self.log = logging.getLogger(...)  # self.log.info / warning / error

    @abstractmethod
    def execute_look_decision(self, symbol: str, market_state: Dict) -> Dict[str, List[Dict]]:
        pass

    def get_available_libraries(self) -> Dict:
        # 返回 talib/numpy/pandas 是否可用等说明字符串
        ...
```

---

## 3. `market_state` 形状（盯盘单品种，真实注入逻辑）

盯盘路径**不会**注入全市场聚合的 `market_indicators`。策略**只读**传入的 `market_state`。

对单个合约，**外层结构**为：

```text
market_state = {
  "BTC": {   # key = 基础符号大写，与参数 symbol 一致
    "price": float,
    "contract_symbol": "BTCUSDT",
    "name": str,
    "exchange": str,
    "change_24h": float,
    "base_volume": float,
    "quote_volume": float,
    "previous_close_prices": {
        "1m": float, "5m": float, ...   # 各周期「上一根已收盘」收盘价；可能部分缺失
    },
    "indicators": {
        "timeframes": {
            "1m": { "klines": [ ... ] },
            "5m": { ... },
            # 共 8 档：1m,5m,15m,30m,1h,4h,1d,1w（以实际有数据为准）
        }
    }
  }
}
```

**常用字段说明**：

- **`price`**：最新价优先。
- **`previous_close_prices`**：引擎由各周期 K 线推导，**避免**策略里再猜「倒数第几根是上一根收盘」；若与 `klines` 联用，须在日志中写明语义。
- **K 线列表**：每根通常含 `open/high/low/close/volume` 及时间字段（如 `open_time`）、以及预计算的 `indicators` 子结构；**排序以实际数据为准**——分析代码时务必看策略里取的是 `klines[-1]` 还是 `[-2]`，并与「已收盘」语义对齐。
- **不要假设**存在 `market_state[symbol]["source"]` 等买入全路径才有的字段（盯盘单品种组装通常不带 `source`）。

---

## 4. 执行器对返回值的处理（审代码时核对）

- `execute_look_decision` 若返回 **`None`**，会被当成 **`{}`**。
- 若返回 **`dict`**，则对每个 `(symbol -> value)`：
  - `value` 是 **`dict`** → 规范化为 **`[value]`**；
  - 是 **`list`** → 保持；
  - 其他 → 该 symbol 对应 **`[]`**。
- 最终包装为 **`{"decisions": normalized_dict}`** 交给上层。

因此：**策略应直接返回 `{"BTC": [{...}]}` 或 `{}`**，避免依赖执行器帮你「补 list」。

---

## 5. 无仓库时的「思维实验」与静态审阅

在**不能运行** `trade` 包时，仍可按下面步骤检查生成代码是否合理：

1. **签名**：是否仅有 `(self, symbol, market_state)`，返回 `Dict[str, List[Dict]]`。
2. **访问路径**：是否只用 `market_state.get(symbol)` 或 `market_state[symbol]`，且 key 与 `symbol` 一致。
3. **分支覆盖**：对用户描述的每一条规则，构造**一组虚构数值**（见第 6 节），推演是否返回 `notify` 或 `{}`。
4. **空数据**：`klines` 为空、指标为 `None` 时是否 **warning** 并早退，避免异常冒泡。
5. **日志**：关键分支是否有 `self.log.info/warning`（产品规范通常要求足够日志）。

---

## 6. 模拟 `market_state` 最小样例（纯 dict，可手写进测试说明）

下面**不依赖**任何项目 import，仅用于说明结构；数值可任意替换以覆盖「触发 / 不触发」场景。

```python
def minimal_mock_market_state_btc() -> dict:
    """仅用于离线推演；字段名与真实环境对齐。"""
    return {
        "BTC": {
            "price": 50000.0,
            "contract_symbol": "BTCUSDT",
            "name": "BTC",
            "exchange": "BINANCE_FUTURES",
            "change_24h": 1.5,
            "base_volume": 10000.0,
            "quote_volume": 5e8,
            "previous_close_prices": {"1h": 49800.0, "4h": 49000.0},
            "indicators": {
                "timeframes": {
                    "1h": {
                        "klines": [
                            {
                                "open": 49900.0,
                                "high": 50100.0,
                                "low": 49800.0,
                                "close": 50000.0,
                                "volume": 123.0,
                                "open_time": 1710000000000,
                                "indicators": {
                                    "rsi": {"rsi14": 55.0},
                                    "ma": {"ma20": 49800.0},
                                },
                            },
                            # 更多根…
                        ]
                    }
                }
            },
        }
    }
```

**如何做场景覆盖**：为同一策略复制多份 mock，只改 `price`、`rsi14`、均线交叉相关字段，检查策略代码是否在「应对应 notify」的场景里返回含 `"signal": "notify"` 的列表，在「不应触发」时返回 `{}`。

### 6.1 与生产链等价的单测骨架（伪代码，需已安装 `trade` 包）

下列调用链与 **`strategy_look_trader` → `execute_strategy_code`** 一致，**不包含** DB 轮询与 Docker；用于在开发机/CI 验证策略逻辑是否与 `market_state` 匹配。

```python
from trade.strategy.strategy_code_executor import StrategyCodeExecutor

def run_look_strategy_once(strategy_code: str, symbol_base: str, market_state: dict):
    """symbol_base 如 'BTC'，须与 market_state 顶层 key 一致。"""
    executor = StrategyCodeExecutor(preload_talib=True)
    return executor.execute_strategy_code(
        strategy_code=strategy_code,
        strategy_name="look_test",
        market_state=market_state,
        decision_type="look",
        look_symbol=symbol_base,
    )
    # 返回 {"decisions": {...}}，结构与线上执行器相同

# 使用第 6 节 minimal_mock_market_state_btc() 作为 market_state，即可做一次完整试跑。
```

**更贴近生产的试跑**（拉真实行情而非手写 dict）：使用 `StrategyCodeTesterLook` / `LookEngine.build_market_state_for_symbol`，见第 7 节。

---

## 7. 在有完整仓库时的真实校验（可选）

若运行环境包含本仓库 `trade` 包：

- **`StrategyCodeTesterLook.test_strategy_code`**：语法、import、继承 `StrategyBaseLook`、`execute_look_decision` 存在性、并用 **`LookEngine.build_market_state_for_symbol(symbol)`** 拉**真实行情**试跑（行情为空时可能仅结构通过）。
- **`validate_symbol`**（MCP/后端创建策略时）：与试跑用的合约一致，通常为 **`BTCUSDT` 形式**用于校验。

Agent **若无仓库**：不要假装已运行 tester；应明确说明「需在部署环境中用 `StrategyCodeTesterLook` 或集成测试确认」。

---

## 8. 常见错误（改代码时优先排查）

| 现象 | 可能原因 |
|------|----------|
| KeyError / 取不到行情 | `market_state` 的 key 用了 `BTCUSDT`，实际 key 是基础符号 `BTC` |
| 永远不 notify | 条件写反、`signal` 不是 `notify`、或 price/指标为 None 未处理 |
| 误判「上一根收盘」 | 未使用 `previous_close_prices` 且 K 线索引与排序假设错误 |
| 执行通过但业务不对 | 规则与用户自然语言不一致，需用第 5、6 节与用户逐项确认 |

---

## 9. 与 MCP / 后端的衔接（提醒）

- 创建策略时提交的 **`strategy_code`** 会按上述契约在校验服务中执行；**`validate_symbol`** 须与试跑/盯盘合约一致。
- 本文档**不替代** MCP 工具参数说明；创建任务前仍需先有 **look 策略 `id`**，见 `mcp-market-look-tools.md`。

---

## 10. 与「策略描述 / 生成 Prompt」的关系

AI 生成盯盘代码时，后端使用 **`strategy_look_prompt.txt` 作为 system**、**用户策略正文作为 user**（见 `strategy-context-and-look-prompt.md`）。若需**调整自然语言表述**以便生成代码更贴合业务，应优先阅读该文档中的撰写要点与 system 约束摘要，再与本文件的运行时契约对照。
