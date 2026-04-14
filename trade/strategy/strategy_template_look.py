"""
Strategy Code Template - 盯盘策略（仅市场数据与通知信号，无交易/账户）
"""

from abc import ABC, abstractmethod
from typing import Dict, List
import logging


class StrategyBaseLook(ABC):
    """盯盘策略基类：根据单个 symbol 的 market_state 决定是否发出 notify。"""

    def __init__(self):
        logger_name = f"{self.__class__.__module__}.{self.__class__.__name__}"
        self.log = logging.getLogger(logger_name)
        self.log.setLevel(logging.INFO)

    @abstractmethod
    def execute_look_decision(self, symbol: str, market_state: Dict) -> Dict[str, List[Dict]]:
        """
        Args:
            symbol: 盯盘合约基础符号（大写，如 BTC；与 market_state 的 key 一致）
            market_state: 单 symbol 或多 symbol 字典；至少包含当前 symbol 的价格与 indicators.timeframes

        Returns:
            Dict[str, List[Dict]]: 例如 {"BTC": [{"signal": "notify", ...}]}
            无信号时返回 {} 或 {"BTC": [{"signal": "hold", ...}]}（hold 不触发企微）
        """
        pass

    def get_available_libraries(self) -> Dict:
        try:
            import talib
            TALIB_AVAILABLE = True
        except ImportError:
            TALIB_AVAILABLE = False
        try:
            import numpy
            NUMPY_AVAILABLE = True
        except ImportError:
            NUMPY_AVAILABLE = False
        try:
            import pandas
            PANDAS_AVAILABLE = True
        except ImportError:
            PANDAS_AVAILABLE = False
        return {
            "talib": "TA-Lib（可用）" if TALIB_AVAILABLE else "TA-Lib（不可用）",
            "numpy": "NumPy（可用）" if NUMPY_AVAILABLE else "NumPy（不可用）",
            "pandas": "Pandas（可用）" if PANDAS_AVAILABLE else "Pandas（不可用）",
            "math": "math",
            "json": "json",
            "datetime": "使用 from datetime import datetime, timedelta, timezone",
        }
