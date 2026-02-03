"""
Strategy Code Template - 卖出策略代码模板基类

本模块定义了卖出策略代码的抽象基类。
所有卖出策略代码都应该继承 StrategyBaseSell 类并实现其抽象方法。

使用方式：
1. AI 生成的卖出策略代码应该继承 StrategyBaseSell
2. 实现 execute_sell_decision() 方法
3. 系统会实例化策略类并调用相应方法
4. 使用 self.log.info() 输出关键执行日志

时间相关库使用（供生成代码参考）：
- 必须使用：from datetime import datetime, timedelta
- 然后使用：datetime.now()、datetime.strptime(s, '%Y-%m-%d')、timedelta(days=1)
- 禁止使用：import datetime 后调用 datetime.now() 或 datetime.strptime()（会报错 AttributeError）
"""
from abc import ABC, abstractmethod
from typing import Dict
import logging
from datetime import datetime, timedelta  # 时间处理：推荐在生成代码中也写 from datetime import datetime, timedelta


class StrategyBaseSell(ABC):
    """
    卖出策略代码抽象基类
    
    所有卖出策略代码都必须继承此类并实现抽象方法。
    系统会在执行时实例化策略类并调用相应方法。
    
    使用示例：
        class MySellStrategy(StrategyBaseSell):
            def execute_sell_decision(self, portfolio, market_state, account_info):
                # 使用日志输出关键信息
                self.log.info("开始执行卖出决策")
                # 实现卖出决策逻辑
                positions = portfolio.get('positions', [])
                self.log.info(f"当前持仓数量: {len(positions)}")
                return {"SYMBOL": {...}}
    """
    
    def __init__(self):
        """初始化策略基类，设置日志记录器"""
        # 创建日志记录器，使用类名作为logger名称
        logger_name = f"{self.__class__.__module__}.{self.__class__.__name__}"
        self.log = logging.getLogger(logger_name)
        # 使用父级logger（root logger），确保使用UTC+8时区
        # propagate默认为True，日志会传播到父级logger
        self.log.setLevel(logging.INFO)
    
    @abstractmethod
    def execute_sell_decision(
        self,
        portfolio: Dict,
        market_state: Dict,
        account_info: Dict
    ) -> Dict[str, Dict]:
        """
        执行卖出决策（抽象方法）
        
        子类必须实现此方法，根据当前持仓生成卖出/平仓决策。
        
        Args:
            portfolio: 当前持仓组合信息，包含：
                - positions: 持仓列表，每个元素包含：
                    - symbol: 交易对符号
                    - position_amt: 持仓数量
                    - position_side: 持仓方向（LONG/SHORT）
                    - avg_price: 开仓均价
                    - unrealized_profit: 未实现盈亏
                - total_value: 账户总值
                - cash: 可用现金
            market_state: 市场状态字典，key为交易对符号，value包含：
                - price: 当前价格
                - indicators: 技术指标数据
                    - timeframes: 多时间周期的技术指标
                    格式：{"1h": {"klines": [...]}, "4h": {...}, ...}
            account_info: 账户信息，包含：
                - total_return: 累计收益率
        
        Returns:
            Dict[str, Dict]: 决策字典，格式为：
                {
                    "SYMBOL": {
                        "signal": "close_position" | "stop_loss" | "take_profit",
                        "quantity": 100,
                        "price": 0.0345,      # 期望价格（可选）
                        "stop_price": 0.0325, # 止损/止盈触发价格（必填）
                        "leverage": 10,
                        "justification": "理由说明"
                    }
                }
                如果没有决策，返回空字典 {}
        """
        pass
    
    def get_available_libraries(self) -> Dict:
        """
        获取可用的Python库信息
        
        Returns:
            Dict: 包含可用库的字典，格式为{库名: 描述}
        """
        # 尝试导入TA-Lib、numpy、pandas
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
            
        libraries = {
            'talib': 'TA-Lib 技术指标库（可用）' if TALIB_AVAILABLE else 'TA-Lib 技术指标库（不可用）',
            'numpy': 'NumPy 数值计算库（可用）' if NUMPY_AVAILABLE else 'NumPy 数值计算库（不可用）',
            'pandas': 'Pandas 数据分析库（可用）' if PANDAS_AVAILABLE else 'Pandas 数据分析库（不可用）',
            'math': 'Python 数学函数库（内置）',
            'datetime': 'Python 日期时间库（内置）。必须用 from datetime import datetime, timedelta 再使用 datetime.now()/datetime.strptime()/timedelta()；禁止 import datetime 后直接用 datetime.now()（会报错）',
            'json': 'Python JSON 处理库（内置）',
            'time': 'Python 时间库（内置）',
            'random': 'Python 随机数库（内置）',
            'sys': 'Python 系统库（内置）',
            'os': 'Python 操作系统接口（内置）',
            're': 'Python 正则表达式库（内置）',
            'collections': 'Python 集合工具库（内置）',
            'itertools': 'Python 迭代工具库（内置）',
            'functools': 'Python 函数工具库（内置）',
            'typing': 'Python 类型注解库（内置）',
            'ast': 'Python 抽象语法树库（内置）',
            'logging': 'Python 日志库（内置）',
            'traceback': 'Python 异常追踪库（内置）',
        }
        
        # 检查并添加其他常用第三方库
        try:
            import requests
            libraries['requests'] = 'HTTP 请求库（可用）'
        except ImportError:
            libraries['requests'] = 'HTTP 请求库（不可用）'
        
        try:
            import matplotlib
            libraries['matplotlib'] = '绘图库（可用）'
        except ImportError:
            libraries['matplotlib'] = '绘图库（不可用）'
        
        try:
            import scipy
            libraries['scipy'] = '科学计算库（可用）'
        except ImportError:
            libraries['scipy'] = '科学计算库（不可用）'
        
        return libraries

