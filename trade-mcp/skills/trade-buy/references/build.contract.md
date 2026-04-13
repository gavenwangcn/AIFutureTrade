# trade-buy · references: BUILD contract (open when editing strategy/script)

Use during **BUILD**: defaults, hit conditions, and stdout protocol the main agent must follow when generating/updating the watch script.
RUN only executes; do not “redesign” this contract during RUN.

## 1) Defaults

- `symbol`: `ETHUSDT`
- `interval`: `5m`
- `poll_interval_seconds`: `10`
- `max_seconds`: `86400` (24h)
- `strategy`: default `rsi_gt`
- `rsi_period`: `14`
- `rsi_threshold`: `70`

## 2) Hit condition (default strategy)

On the **latest** bar that has full indicators:

- `RSI(rsi_period) > rsi_threshold`

counts as a **buy signal** (example only; real trading needs separate authorization and risk controls).

## 3) Script output protocol (required)

The script may log multiple lines to **stdout**, but **before exit it must print exactly one** of these JSON lines (for stable subagent parsing):

### Signal

```json
{"status":"signal","symbol":"ETHUSDT","interval":"5m","strategy":"rsi14_gt_70","timestamp_ms":1710000000000,"details":{"rsi14":72.3,"close":1850.12}}
```

### Timeout

```json
{"status":"timeout","symbol":"ETHUSDT","interval":"5m","strategy":"rsi14_gt_70","timestamp_ms":1710000000000,"details":{"elapsed_seconds":86400}}
```
