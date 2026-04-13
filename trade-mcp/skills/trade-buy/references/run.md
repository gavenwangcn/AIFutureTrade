# trade-buy · references: RUN (spawn subagent, background watch, notify)

Goal: after you confirm workspace scripts, the main agent uses `sessions_spawn` to start a subagent that runs the script until signal or timeout, then `sessions_send` notifies the main agent → forwarded to your channel.

---

## 1) Main agent: `sessions_spawn` (force `lightContext`)

When calling `sessions_spawn` (runtime=subagent):

- `lightContext: true` (**required**, lightweight bootstrap)
- `runTimeoutSeconds: 86400` (default 24h; adjust as needed)
- `task` must cover: how to start the script, how to poll, how to `sessions_send`

Recommended parameter templates: see copy-paste blocks in `run.templates.md` (keeps this file short).

---

## 2) Subagent: start script (background + timeout)

The subagent must start with `exec` and background immediately:

- `background=true` (or `yieldMs=0`)
- **Must** set explicit `timeout=86400` (seconds)
- **Must** use conda:

  - `conda run -n trade-buy python trade_buy/watch_buy_signal.py ...`

---

## 3) Subagent: poll cadence (**30s**, required)

The subagent must:

- Drive status checks only with `process poll(timeout=30000)` (ms)
- After each poll, `process log` tail and parse the single JSON line
- **Do not** use `exec sleep ...` or exec as a timer
- On transient `process poll/log` failures: limited backoff/retry; after limit, `sessions_send` and stop

---

## 4) Subagent: notify main agent (`sessions_send` templates)

See copy-paste templates in `run.templates.md`.
