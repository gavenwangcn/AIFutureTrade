# trade-buy · references: BUILD (generate/iterate scripts; confirm before RUN)

Goal: the main agent generates watch scripts under **workspace** (`trade_buy/`) and iterates until you manually approve, then RUN.

**This phase does not run a subagent.**

---

## 1) Output location (required: `<workspace>/trade_buy/`)

Same as top-level **`SKILL.md`**: scripts and deps must sit under the **current agent workspace** (relative to workspace root):

- `trade_buy/watch_buy_signal.py`
- `trade_buy/trade_mcp_client.py`
- `trade_buy/requirements.txt`
- `trade_buy/environment.yml` (conda env; name fixed: `trade-buy`)

Optional:

- `trade_buy/README.md`

Repo path `skills/trade-buy/trade-buy/` is **template only**; execution uses workspace outputs.

---

## 2) conda env (install deps first)

When the server uses conda, install deps into env **`trade-buy`** ahead of time.

From workspace root (recommended):

```bash
conda env create -f trade_buy/environment.yml -n trade-buy || \
conda env update -f trade_buy/environment.yml -n trade-buy
```

## 2.1 trade-mcp MCP URL (fixed)

This skill fixes the trade-mcp MCP URL:

- `TRADE_MCP_URL=http://154.89.148.172:8099/sse`

Set it before running/testing (e.g. subagent `exec` env or system env):

```bash
export TRADE_MCP_URL="http://154.89.148.172:8099/sse"
```

Or with conda (optional):

```bash
conda create -n trade-buy python=3.11 -y
conda run -n trade-buy python -m pip install -r trade_buy/requirements.txt
```

---

## 3) Script contract (must satisfy)

The script must:

- Loop until signal or timeout
- Default poll every **10** seconds (inside script)
- Default max **24** hours (inside script)
- Before exit, print **exactly one** JSON line (signal/timeout) to stdout for subagent parsing/notify

JSON line shape: see `build.contract.md`.

---

## 4) Manual checklist (before RUN)

- `TRADE_MCP_URL` is correct and reachable
- `conda run -n trade-buy python trade_buy/watch_buy_signal.py --help` works
- Short timeout path: `--max-seconds 30 --poll-interval-seconds 5` prints timeout JSON and exits ~30s
- If the strategy triggers easily, verify signal JSON prints once and exits
