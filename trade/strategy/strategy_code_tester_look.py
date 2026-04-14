"""
盯盘策略代码测试：使用真实行情（symbol 由调用方传入）。
"""

import ast
import json
import logging
import os
import traceback
from typing import Dict, List, Optional, Tuple

import trade.common.config as app_config
from trade.strategy.strategy_code_executor import StrategyCodeExecutor, strip_markdown_code_block
logger = logging.getLogger(__name__)


class StrategyCodeTesterLook:
    def __init__(self, model_id: Optional[int] = None):
        self.code_executor = StrategyCodeExecutor(preload_talib=True)
        env_mid = os.getenv("LOOK_VALIDATE_MODEL_ID")
        self.model_id = model_id
        if self.model_id is None and env_mid:
            try:
                self.model_id = int(env_mid)
            except ValueError:
                self.model_id = 1
        if self.model_id is None:
            self.model_id = 1

    def test_strategy_code(
        self,
        strategy_code: str,
        strategy_name: str = "盯盘策略",
        symbol: str = "BTC",
    ) -> Dict:
        errors: List[str] = []
        warnings: List[str] = []
        test_results: Dict = {}

        strategy_code = strip_markdown_code_block(strategy_code)
        sym = (symbol or "BTC").strip().upper()
        if sym.endswith("USDT"):
            sym = sym.replace("USDT", "")

        logger.info("[StrategyCodeTesterLook] 测试盯盘策略: %s symbol=%s", strategy_name, sym)

        syn = self._test_syntax(strategy_code)
        test_results["syntax"] = syn
        if not syn["passed"]:
            errors.extend(syn["errors"])

        imp = self._test_imports(strategy_code)
        test_results["imports"] = imp
        if not imp["passed"]:
            errors.extend(imp["errors"])
        warnings.extend(imp.get("warnings", []))

        cls = self._test_class(strategy_code)
        test_results["class"] = cls
        if not cls["passed"]:
            errors.extend(cls["errors"])

        inh = self._test_inheritance(strategy_code)
        test_results["inheritance"] = inh
        if not inh["passed"]:
            errors.extend(inh["errors"])

        met = self._test_method(strategy_code)
        test_results["methods"] = met
        if not met["passed"]:
            errors.extend(met["errors"])

        exe = self._test_execution(strategy_code, strategy_name, sym)
        test_results["execution"] = exe
        if not exe["passed"]:
            errors.extend(exe["errors"])
        warnings.extend(exe.get("warnings", []))

        passed = len(errors) == 0
        return {
            "passed": passed,
            "errors": errors,
            "warnings": warnings,
            "test_results": test_results,
            "strategy_name": strategy_name,
            "symbol": sym,
        }

    def _test_syntax(self, code: str) -> Dict:
        try:
            ast.parse(code)
            return {"passed": True, "errors": []}
        except SyntaxError as e:
            return {"passed": False, "errors": [f"语法错误: {e}"]}

    def _test_imports(self, code: str) -> Dict:
        warnings = []
        if "import datetime" in code and "from datetime import" not in code:
            warnings.append("建议使用 from datetime import datetime, timedelta, timezone")
        return {"passed": True, "errors": [], "warnings": warnings}

    def _test_class(self, code: str) -> Dict:
        try:
            tree = ast.parse(code)
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    return {"passed": True, "errors": []}
            return {"passed": False, "errors": ["未找到类定义"]}
        except Exception as e:
            return {"passed": False, "errors": [str(e)]}

    def _test_inheritance(self, code: str) -> Dict:
        try:
            if "StrategyBaseLook" not in code:
                return {"passed": False, "errors": ["必须继承 StrategyBaseLook"]}
            return {"passed": True, "errors": []}
        except Exception as e:
            return {"passed": False, "errors": [str(e)]}

    def _test_method(self, code: str) -> Dict:
        if "execute_look_decision" not in code:
            return {"passed": False, "errors": ["必须实现 execute_look_decision 方法"]}
        return {"passed": True, "errors": []}

    def _test_execution(self, strategy_code: str, strategy_name: str, symbol: str) -> Dict:
        errors: List[str] = []
        warnings: List[str] = []

        try:
            from trade.common.database.database_basic import Database
            from trade.look_engine import LookEngine
            from trade.market.market_data import MarketDataFetcher

            db = Database()
            mf = MarketDataFetcher(db)
            look_eng = LookEngine(db=db, market_fetcher=mf, model_id=self.model_id)
            market_state = look_eng.build_market_state_for_symbol(symbol)
            if not market_state:
                warnings.append("真实行情为空，仅做语法/结构通过；请检查网络与交易对")
                return {"passed": True, "errors": [], "warnings": warnings}

            res = self.code_executor.execute_strategy_code(
                strategy_code=strategy_code,
                strategy_name=strategy_name,
                market_state=market_state,
                decision_type="look",
                look_symbol=symbol,
            )
            if res is None:
                errors.append("执行返回 None")
            elif not isinstance(res, dict) or "decisions" not in res:
                errors.append("执行返回格式缺少 decisions")
            else:
                dec = res.get("decisions") or {}
                if not isinstance(dec, dict):
                    errors.append("decisions 必须为 dict")
        except Exception as e:
            errors.append(f"执行异常: {e}")
            logger.debug(traceback.format_exc())

        return {"passed": len(errors) == 0, "errors": errors, "warnings": warnings}


def validate_look_strategy_code(
    strategy_code: str,
    symbol: str,
    strategy_name: str = "盯盘策略",
) -> Tuple[bool, Dict]:
    tester = StrategyCodeTesterLook()
    result = tester.test_strategy_code(strategy_code, strategy_name, symbol=symbol)
    return result["passed"], result


def validate_look_strategy_code_with_report(
    strategy_code: str,
    symbol: str,
    strategy_name: str = "盯盘策略",
) -> Tuple[bool, str]:
    tester = StrategyCodeTesterLook()
    result = tester.test_strategy_code(strategy_code, strategy_name, symbol=symbol)
    ok = result["passed"]
    report = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    return ok, report
