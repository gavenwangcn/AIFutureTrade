"""示例盯盘策略：仅用于场景测试脚本演示；返回空 decisions。"""
from trade.strategy.strategy_template_look import StrategyBaseLook
from typing import Dict, List


class DemoMinimalLook(StrategyBaseLook):
    def execute_look_decision(self, symbol: str, market_state: Dict) -> Dict[str, List[Dict]]:
        decisions = {}
        self.log.info("DemoMinimalLook symbol=%s", symbol)
        return decisions
