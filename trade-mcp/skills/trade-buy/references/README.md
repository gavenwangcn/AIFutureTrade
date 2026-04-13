# trade-buy · references index

Read on demand; avoid loading every detail and large script blobs at once. Follow the decision tree below.

**Agent workspace (required)**: all scripts and dependencies this skill generates or runs must live under **`<workspace>/trade_buy/`** (create if missing); do not use the workspace root. See **`../SKILL.md`** (if present) and **`build.md` §1**.

## Decision tree (open only what you need)

- **BUILD (generate/iterate scripts)**: open `build.md`
  - **Strategy inputs / defaults / one-line JSON protocol**: open `build.contract.md`
  - **Which trade-mcp market/indicator tool to call**: open `build.market.md`
- **RUN (confirmed scripts; background watch)**: open `run.md`
  - **Copy-paste templates for `sessions_spawn` / `sessions_send` / 30s poll**: open `run.templates.md`

## Files by phase

- **BUILD**
  - `build.md`
  - `build.contract.md`
  - `build.market.md`
- **RUN**
  - `run.md`
  - `run.templates.md`
