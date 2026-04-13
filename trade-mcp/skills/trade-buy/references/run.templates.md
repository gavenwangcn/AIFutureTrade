# trade-buy · references: RUN templates (open only to copy-paste)

Large pasteable templates are isolated here so RUN does not load too much text at once.

---

## 1) Main agent: `sessions_spawn` template (`lightContext` required)

```json
{
  "runtime": "subagent",
  "lightContext": true,
  "runTimeoutSeconds": 86400,
  "cleanup": "keep",
  "task": "(paste subagent task text from sections 2/3/4 below)"
}
```

---

## 2) Subagent: start script (background + timeout + conda)

The subagent must start with `exec` and background immediately:

- `background=true` (or `yieldMs=0`)
- **Must** set explicit `timeout=86400` (seconds)
- **Must** use conda:

  - `conda run -n trade-buy python trade_buy/watch_buy_signal.py ...`

---

## 3) Subagent: poll cadence (**30s**, required)

- Status checks only via `process poll(timeout=30000)` (ms)
- After each poll, `process log` tail and parse the single JSON line
- **Do not** use `exec sleep ...` or exec as a timer
- On transient `process poll/log` failures: limited backoff/retry; after limit, `sessions_send` and stop

---

## 4) Subagent: `sessions_send` templates

**Signal**:

```json
{
  "sessionKey": "main",
  "timeoutSeconds": 0,
  "message": "[trade-buy] BUY signal triggered for ETHUSDT (5m RSI14>70)\nJSON: {...}"
}
```

**Timeout**:

```json
{
  "sessionKey": "main",
  "timeoutSeconds": 0,
  "message": "[trade-buy] No signal within 24h for ETHUSDT (5m RSI14>70)\nJSON: {...}"
}
```

Notes:

- `sessionKey` must target the **main** session (often `main`), not the subagent session.
- `timeoutSeconds: 0` avoids blocking the subagent on send; `sessions_send` still completes the announce flow.
