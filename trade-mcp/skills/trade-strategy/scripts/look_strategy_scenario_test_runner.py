#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
================================================================================
盯盘策略场景测试脚本 —— **纯仿真环境**（不依赖 AIFutureTrade 项目代码、不依赖 pip 包）
================================================================================

本文件是**独立可搬运**的 Python 脚本：仅用 **Python 标准库**，按线上
`StrategyCodeExecutor` 盯盘分支的语义**自行实现**「exec 策略 → 找类 →
`execute_look_decision` → 归一化 decisions」，并通过 **`sys.modules` 注入**
假的 `trade.strategy.strategy_template_look.StrategyBaseLook`，使 MCP 返回的
`from trade.strategy.strategy_template_look import StrategyBaseLook` 仍能执行。

**不是** import 仓库里的 `trade` 包；**不是**调用项目内 `strategy_code_executor.py`。

【何时使用】
用户要求核对「策略代码是否满足需求」时：将 MCP 取得的 `strategy_code` 与自建的
`market_state` JSON 传入本脚本，根据 **stdout / logging** 与返回的 `decisions`
判断逻辑是否符合规则。

【运行示例（任意目录，仅需 Python 3）】

    python look_strategy_scenario_test_runner.py --strategy-file s.py --market-state m.json --symbol BTC

    python look_strategy_scenario_test_runner.py --print-schema

【策略代码限制】
- 须继承仿真提供的 `StrategyBaseLook`，与线上一致；`self.log` 为 `logging.Logger`（与 `strategy_template_look` 相同，含 `info`/`warning`/`error`/`exception`），仿真在首次执行前会 `basicConfig` 以便 INFO 可见。
- 与 **`strategy_look_prompt.txt`** 及线上执行器对齐：`from trade.strategy.strategy_template_look import StrategyBaseLook` 由 `sys.modules` 注入；`execute_look_decision(self, symbol, market_state)` 两参签名；返回值 `dict` 经归一化（单条 dict 作 value 时包成 list，与线上一致）；顶层 `import talib`/`numpy` 等若环境未安装会失败（prompt 一般禁止用 talib 重算 K 线指标）。
- 执行命名空间与 `StrategyCodeExecutor` 盯盘分支对齐：`__name__` 为 `__main__`；`exec` 前 `datetime` 为**模块**，`exec` 后为 `datetime`/`timedelta`/`timezone`/`date` **类**（与 prompt 推荐 `from datetime import datetime, timedelta, timezone` 一致）；并预置 `collections`/`itertools`/`functools` 等常用标准库。
- 若策略**顶层** `import` 未安装的第三方库，会在 import 阶段失败——与「无预装 pip 包」场景一致；仅标准库与 `market_state` 时可在仿真中跑通。

【技能内渐进式披露】先读 **`scripts/README.md`** 与 **`../references/look-execution-and-testing.md` 第 11 节**。

================================================================================
"""

from __future__ import annotations

import argparse
import collections
import functools
import itertools
import json
import logging
import math
import random
import re
import sys
import time
import traceback
import types
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import datetime as datetime_module

# =============================================================================
# market_state 形状说明（与线上 build_single_symbol_market_state 语义对齐，供构造 JSON）
# =============================================================================

MARKET_STATE_SCHEMA_FOR_MODEL = """
盯盘路径下，execute_look_decision(symbol, market_state) 收到的 market_state 为：

  Dict[str, Any]
  └─ key: 基础合约符号 **大写**，无 USDT 后缀（如 "BTC"），必须与 --symbol 与 look_symbol 一致。
  └─ value: 单品种快照 dict，典型键如下（与线上 build_single_symbol_market_state 一致）：

    price              float     最新价
    contract_symbol    str       如 "BTCUSDT"
    name               str
    exchange           str       如 "BINANCE_FUTURES"
    change_24h         float
    base_volume        float     24h 基础资产成交量
    quote_volume       float     24h 计价成交额
    previous_close_prices  Dict[str, float]   key 为周期如 "1m","5m","15m","30m","1h","4h","1d"
    indicators         Dict
        └─ timeframes  Dict
            └─ "<interval>"  例如 "1m","5m","15m","30m","1h","4h","1d"
                └─ klines  List[Dict]   时间升序，最后一根常为「当前」；[-2] 用于上一根收盘等
                    每根 K 线 dict 常见键：
                      open, high, low, close, volume
                      open_time (int, 毫秒), time / open_time_dt_str 等（见 strategy_look_prompt 5.1）
                      indicators  Dict   预计算指标（禁止在策略里用 talib 重算）
                        ├─ ma    { ma5, ma20, ma60, ma99, ... }
                        ├─ ema   { ema5, ema20, ... }
                        ├─ rsi   { rsi6, rsi14, ... }
                        ├─ macd  { dif, dea, bar }
                        ├─ kdj   { k, d, j }
                        ├─ atr   { atr7, atr14, ... }
                        ├─ adx   { adx14, "+di14", "-di14" }   # 键名含 +/-
                        ├─ vol   { ... }
                        └─ supertrend { line, trend, upper, lower, ... }

合并多周期时盯盘侧为 **7 档** interval（**不含 1w**）。

策略返回值：execute_look_decision 应返回 Dict[str, List[Dict]]，外层 key 为基础符号；
需要企微通知时列表元素含 "signal": "notify" 等（见 strategy_look_prompt）。
"""


def print_market_state_schema() -> None:
    print(MARKET_STATE_SCHEMA_FOR_MODEL.strip())


# =============================================================================
# 以下仿真逻辑参考线上 StrategyCodeExecutor（look 分支）行为，不 import 项目源码
# =============================================================================


def _strip_markdown_code_block(code: str) -> str:
    """与线上 strip_markdown_code_block 一致：去掉 ```python ... ``` 包装。"""
    if not code or not isinstance(code, str):
        return code
    stripped = code.strip()
    stripped = re.sub(r"^```(?:[pP]ython)?\s*\n?", "", stripped)
    stripped = re.sub(r"\n?```\s*$", "", stripped)
    return stripped.strip()


def _define_simulation_strategy_base_look() -> type:
    """内联定义 StrategyBaseLook，等价于线上 strategy_template_look 的契约（仅仿真用）。"""

    class StrategyBaseLook(ABC):
        def __init__(self) -> None:
            logger_name = f"{self.__class__.__module__}.{self.__class__.__name__}"
            self.log = logging.getLogger(logger_name)
            self.log.setLevel(logging.INFO)

        @abstractmethod
        def execute_look_decision(self, symbol: str, market_state: Dict) -> Dict[str, List[Dict]]:
            pass

        def get_available_libraries(self) -> Dict:
            try:
                import talib  # type: ignore

                ta = True
            except ImportError:
                ta = False
            try:
                import numpy  # type: ignore

                np_ok = True
            except ImportError:
                np_ok = False
            try:
                import pandas  # type: ignore

                pd_ok = True
            except ImportError:
                pd_ok = False
            return {
                "talib": "TA-Lib（可用）" if ta else "TA-Lib（不可用）",
                "numpy": "NumPy（可用）" if np_ok else "NumPy（不可用）",
                "pandas": "Pandas（可用）" if pd_ok else "Pandas（不可用）",
                "math": "math",
                "json": "json",
                "datetime": "使用 from datetime import datetime, timedelta, timezone",
            }

    return StrategyBaseLook


def _register_fake_trade_strategy_template(StrategyBaseLook: type) -> None:
    """注入 `from trade.strategy.strategy_template_look import StrategyBaseLook` 解析目标（无磁盘文件）。"""
    trade_m = types.ModuleType("trade")
    trade_m.__path__ = ["<sim_trade>"]
    strat_m = types.ModuleType("trade.strategy")
    strat_m.__path__ = ["<sim_trade.strategy>"]
    tpl_m = types.ModuleType("trade.strategy.strategy_template_look")
    tpl_m.StrategyBaseLook = StrategyBaseLook
    sys.modules["trade"] = trade_m
    sys.modules["trade.strategy"] = strat_m
    sys.modules["trade.strategy.strategy_template_look"] = tpl_m


def _find_look_strategy_class(module: types.ModuleType, base: type) -> Optional[type]:
    """
    在模块命名空间中取**最后一个**继承 base 的类（按定义顺序，与 Python 3.7+ __dict__ 插入序一致）。
    避免使用 dir() 的字母序误选到非主策略类。
    """
    found: Optional[type] = None
    for obj in module.__dict__.values():
        if not isinstance(obj, type):
            continue
        if obj is base or not issubclass(obj, base):
            continue
        found = obj
    return found


def _normalize_look_decisions(decisions: Any) -> Dict[str, List[Dict]]:
    """与线上 StrategyCodeExecutor 盯盘归一化一致：单 dict → 包成 list。"""
    if decisions is None:
        decisions = {}
    if not isinstance(decisions, dict):
        raise ValueError(f"execute_look_decision 应返回 dict，实际 {type(decisions)}")
    out: Dict[str, List[Dict]] = {}
    for k, v in decisions.items():
        if isinstance(v, dict):
            out[k] = [v]
        elif isinstance(v, list):
            out[k] = v
        else:
            out[k] = []
    return out


_SIM_MODULE_SEQ = 0


def _ensure_logging_configured() -> None:
    """与线上试跑类似：保证策略内 self.log.info 等能落到 stderr（未配置 root 时）。"""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(levelname)s %(name)s %(message)s",
        )


def run_look_strategy_simulation(
    strategy_code: str,
    market_state: Dict[str, Any],
    look_symbol: str,
    strategy_name: str = "scenario_test",
) -> Dict[str, Any]:
    """
    纯仿真执行：不读取 AIFutureTrade 仓库、不 import 项目内 strategy_code_executor。

    返回形状与旧版「加载项目执行器」兼容：成功时含 `decisions`；失败时含 `error`，并设 `simulation: true`。
    """
    global _SIM_MODULE_SEQ
    code = _strip_markdown_code_block(strategy_code)
    sym = (look_symbol or "").strip().upper()
    if sym.endswith("USDT"):
        sym = sym.replace("USDT", "").strip()
    if not sym:
        return {"error": "look_symbol 为空", "decisions": {}, "simulation": True}

    _ensure_logging_configured()

    StrategyBaseLook = _define_simulation_strategy_base_look()
    _register_fake_trade_strategy_template(StrategyBaseLook)

    _SIM_MODULE_SEQ += 1
    safe_name = re.sub(r"[^\w]", "_", strategy_name)[:80]
    mod_name = f"sim_look_strategy_{_SIM_MODULE_SEQ}_{safe_name}"
    module = types.ModuleType(mod_name)

    import typing as typing_mod

    g = module.__dict__
    g["__builtins__"] = __builtins__
    # 与 strategy_code_executor 盯盘分支一致，便于与线上行为对照
    g["__name__"] = "__main__"
    g["__doc__"] = None
    g["ABC"] = ABC
    g["abstractmethod"] = abstractmethod
    g["Dict"] = Dict
    g["List"] = List
    g["Optional"] = Optional
    g["Any"] = Any
    g["Tuple"] = Tuple
    g["Union"] = Union
    g["typing"] = typing_mod
    g["StrategyBaseLook"] = StrategyBaseLook
    g["StrategyBase"] = StrategyBaseLook
    g["math"] = math
    g["json"] = json
    g["logging"] = logging
    g["time"] = time
    g["random"] = random
    g["re"] = re
    g["collections"] = collections
    g["itertools"] = itertools
    g["functools"] = functools
    # exec 前为 datetime 模块（与执行器 allowed_modules['datetime'] 一致）
    g["datetime"] = datetime_module

    try:
        exec(code, g, g)
        # exec 后为常用类型，便于类体内/方法内与线上一致
        g["datetime"] = datetime_module.datetime
        g["timedelta"] = datetime_module.timedelta
        g["timezone"] = datetime_module.timezone
        g["date"] = datetime_module.date
    except Exception:
        return {
            "error": "策略代码 exec 失败",
            "decisions": {},
            "traceback": traceback.format_exc(),
            "simulation": True,
        }

    strategy_class = _find_look_strategy_class(module, StrategyBaseLook)

    if strategy_class is None:
        return {
            "error": "策略代码中未找到继承自 StrategyBaseLook 的类",
            "decisions": {},
            "simulation": True,
        }

    try:
        inst = strategy_class()
        raw = inst.execute_look_decision(sym, market_state or {})
        normalized = _normalize_look_decisions(raw)
        logging.getLogger(__name__).info(
            "[仿真] 策略 %s 执行完成，decisions=%s",
            strategy_name,
            json.dumps(normalized, ensure_ascii=False, default=str),
        )
        return {"decisions": normalized, "simulation": True}
    except Exception:
        return {
            "error": "execute_look_decision 执行异常",
            "decisions": {},
            "traceback": traceback.format_exc(),
            "simulation": True,
        }


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s %(message)s")


def run_look_strategy_once(
    strategy_code: str,
    market_state: Dict[str, Any],
    look_symbol: str,
    strategy_name: str = "scenario_test",
) -> Dict[str, Any]:
    """对外入口：与历史函数名兼容，内部仅走仿真。"""
    return run_look_strategy_simulation(
        strategy_code=strategy_code,
        market_state=market_state,
        look_symbol=look_symbol,
        strategy_name=strategy_name,
    )


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _validate_market_state_keys(market_state: Dict[str, Any], symbol: str) -> List[str]:
    warns: List[str] = []
    sym = symbol.strip().upper().replace("USDT", "")
    if sym not in market_state:
        warns.append(f"market_state 顶层缺少 key '{sym}'，与 --symbol 不一致")
    entry = market_state.get(sym) or {}
    if "indicators" in entry and "timeframes" not in (entry.get("indicators") or {}):
        warns.append("indicators 下建议包含 timeframes（与线上结构一致）")
    return warns


def run_test_mode(args: argparse.Namespace) -> int:
    strategy_code = _load_text(Path(args.strategy_file))
    sym = (args.symbol or "BTC").strip().upper().replace("USDT", "")

    scenarios: List[tuple[str, Dict[str, Any]]] = []

    if args.market_state:
        p = Path(args.market_state)
        scenarios.append((p.stem, _load_json(p)))
    if args.scenarios_dir:
        d = Path(args.scenarios_dir)
        for p in sorted(d.glob("*.json")):
            scenarios.append((p.stem, _load_json(p)))

    if not scenarios:
        logging.error("请提供 --market-state 或 --scenarios-dir")
        return 2

    results: List[Dict[str, Any]] = []
    for name, ms in scenarios:
        if not isinstance(ms, dict):
            logging.error("场景 %s: JSON 根须为 object", name)
            continue
        for w in _validate_market_state_keys(ms, sym):
            logging.warning("[%s] %s", name, w)
        out = run_look_strategy_once(
            strategy_code=strategy_code,
            market_state=ms,
            look_symbol=sym,
            strategy_name=f"{args.strategy_name or 'look'}::{name}",
        )
        decisions = out.get("decisions") if isinstance(out, dict) else {}
        results.append(
            {
                "scenario": name,
                "symbol": sym,
                "success": "error" not in out,
                "decisions": decisions,
                "simulation_output": out,
            }
        )

    if args.output_json:
        print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    else:
        for r in results:
            print("=== scenario:", r["scenario"], "===")
            print(json.dumps(r["simulation_output"], ensure_ascii=False, indent=2, default=str))
            print()

    print(
        "---\n"
        "模型审阅提示：本输出为**仿真环境**（无项目 trade 包）；请对照用户规则检查 decisions 是否应含 "
        '"signal":"notify" 或应返回空；若有 error/traceback 则策略未通过仿真执行。\n'
        "---",
        file=sys.stderr,
    )
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Look strategy scenario runner — pure simulation (stdlib only, no project imports)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="模型用法（无需读本文件源码）见 trade-mcp/skills/trade-strategy/references/look-execution-and-testing.md 第 11.3 节；技术说明见文件顶部与 scripts/README.md。",
    )
    p.add_argument(
        "--print-schema",
        action="store_true",
        help="打印 market_state 键说明后退出（无需策略文件）",
    )
    p.add_argument(
        "--strategy-file",
        help="盯盘策略 Python 源码路径（与 MCP 返回的 strategy_code 内容相同）",
    )
    p.add_argument(
        "--market-state",
        help="单个场景：market_state JSON 文件路径",
    )
    p.add_argument(
        "--scenarios-dir",
        help="多场景：目录下每个 *.json 运行一次",
    )
    p.add_argument(
        "--symbol",
        default="BTC",
        help="基础符号大写，如 BTC（须与 JSON 顶层 key 一致）",
    )
    p.add_argument(
        "--strategy-name",
        default="scenario_test",
        help="展示名前缀（用于日志）",
    )
    p.add_argument(
        "--output-json",
        action="store_true",
        help="输出为单一 JSON 数组（便于程序解析）",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    _configure_logging(args.verbose)

    if args.print_schema:
        print_market_state_schema()
        return 0

    if not args.strategy_file:
        logging.error("缺少 --strategy-file（或使用 --print-schema）")
        return 2

    return run_test_mode(args)


if __name__ == "__main__":
    sys.exit(main())
