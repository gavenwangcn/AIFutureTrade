# trade-strategy 技能：`scripts/` 目录说明

本目录对应 **Agent Skills** 约定中的 **`scripts/`**（可执行脚本：`.py`、`.sh` 等）。与 **`SKILL.md`**（必需）、**`references/`**（参考文档）、**`assets/`**（可选资源）并列，见上级目录 **`SKILL.md` 中「目录结构」**。

为避免单次向模型注入过多 token，**默认只加载 `SKILL.md`**；其余材料按任务**按需读取**。

## 阅读层级（由浅到深）

| 层级 | 文件 | 何时读 |
|------|------|--------|
| L0 | `../SKILL.md` | 始终：流程、MCP 约束、耗时 |
| L1 | `../references/mcp-market-look-tools.md` | 要调 `trade_look_*` / `trade_strategy_*` 参数时 |
| L2 | `../references/strategy-context-and-look-prompt.md` | 撰写或审 `strategy_context`、对齐生成 Prompt 时 |
| L3 | `../references/look-execution-and-testing.md` | 理解 `market_state`、执行链、测试与**如何运行本目录脚本**时 |
| L4 | **不读脚本源码**：见 **`../references/look-execution-and-testing.md` 第 11.3 节**；**自造多场景 JSON** 见下文 **「模型如何构建模拟测试数据」** | 用户要求**严格核对代码与需求**、或要**本地跑仿真试跑**时；模型**不必**打开、修改 `look_strategy_scenario_test_runner.py`；须**按需求与策略分支自行设计**多份测试数据并尽量全覆盖 |

## 本目录脚本（可执行）

均在仓库根目录 `AIFutureTrade` 下运行；路径以 `trade-mcp/skills/trade-strategy/scripts/` 为前缀。

| 脚本 | 用途 |
|------|------|
| `look_strategy_scenario_test_runner.py` | MCP 拉取的 `strategy_code` 存成 `.py` + 多份 JSON 场景，批量跑 `decisions`；**标准库仿真**（不 import 仓库 `trade`），语义上与盯盘执行路径对齐，供审阅 stdout/返回结构 |

示例数据：本目录下 **`look_scenario_examples/`**（勿一次把大段 JSON 贴进 system prompt；按需打开单文件）。

详细命令、**`market_state` 形状**与 **prompt 固定语法 ↔ 仿真兼容性**见 **`../references/look-execution-and-testing.md` 第 11 节（含 11.3、11.4）**。

## 模型如何构建模拟测试数据（覆盖需求与策略条件）

**原则**：仿真只负责执行策略；**是否测全**取决于测试数据。**模型应主动**根据用户自然语言需求与已展示的 **`strategy_code`**，自行设计并说明（或指导用户写入）多份 **`market_state` JSON**，使审阅可追溯、可重复。

1. **按需求拆维度**  
   将规则拆成可独立检验的维度（示例）：多周期组合、价格与指标阈值、K 线根数是否充足、`None` 与边界值、应触发 `notify` 与应不触发的分支、仅满足部分条件 vs 全部条件等。**每个维度**都应有对应用意的场景，避免只测「一条 happy path」。

2. **按场景建不同 JSON**  
   **每一类场景单独一个 JSON 文件**（或等价地一次只构造一种情形），用 **`--scenarios-dir`** 批量跑；与「一次只打开一个场景文件」的渐进披露一致。不同场景应改 **`price`、`klines`、嵌套 `indicators`、根数、`quote_volume` 等** 中策略实际读取的字段，使结果在 `decisions` / 日志上可区分。

3. **覆盖策略内各条件（必做）**  
   阅读策略代码中的 **`if` / `elif` / 早退 / `notify` 分支**，列出「触发 notify」「明确不触发」「数据不足跳过」「指标为 None」等路径；**为每一条需要验证的路径至少准备一份测试数据**，并在说明中标注该 JSON 旨在覆盖哪条条件。目标：**策略里出现的每个业务条件，都至少被一组数据跑到一次**（含应告警的 warning 分支，若需求关心）。

4. **与输出对照**  
   跑完后根据每场景的 **`decisions`**（是否含 `"signal":"notify"`）和 **`self.log`** 是否与该场景预期一致，判断代码是否满足需求；缺场景则补 JSON 再跑，直至主要分支均有覆盖或用户接受剩余风险。

更细的 **`market_state` 契约与示例思路**见 **`../references/look-execution-and-testing.md`**（第 5～6 节及第 11 节）。需要键名清单时可在有 Python 的环境执行 **`python look_strategy_scenario_test_runner.py --print-schema`**（由用户或终端执行；模型只需知道存在该用法，**无需读 `.py` 文件**）。
