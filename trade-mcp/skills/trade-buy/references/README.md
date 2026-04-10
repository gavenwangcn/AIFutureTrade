# trade-buy · references 索引

按需阅读，避免一次性加载全部细则与大段脚本内容。建议按下面“决策树”逐步打开。

**Agent 工作区（强制）**：所有本技能生成/运行的脚本与依赖必须放在 **`<workspace>/trade_buy/`** 下（无则新建）；勿放 workspace 根目录。详见 **`../SKILL.md`** 与 **`build.md` §1**。

## 决策树（只打开你需要的那个文件）

- **我要 BUILD（生成/迭代脚本）**：打开 `build.md`
  - **我需要确认策略入参/默认值/输出 JSON 单行协议**：再打开 `build.contract.md`
  - **我需要知道 trade-mcp 应该调用哪个行情/指标工具**：再打开 `build.market.md`
- **我已经人工确认脚本 OK，要 RUN（后台盯盘）**：打开 `run.md`
  - **我需要可复制的 sessions_spawn / sessions_send / 30s poll 模板**：再打开 `run.templates.md`

## 文件清单（按阶段分组）

- **BUILD**
  - `build.md`
  - `build.contract.md`
  - `build.market.md`
- **RUN**
  - `run.md`
  - `run.templates.md`

