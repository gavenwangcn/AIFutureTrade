"""
Strategy Code Template - 买入策略代码模板基类

本模块定义了买入策略代码的抽象基类。
所有买入策略代码都应该继承 StrategyBaseBuy 类并实现其抽象方法。

使用方式：
1. AI 生成的买入策略代码应该继承 StrategyBaseBuy
2. 实现 execute_buy_decision() 方法
3. 系统会实例化策略类并调用相应方法
4. 使用 self.log.info() 输出关键执行日志
"""
from abc import ABC, abstractmethod
from typing import Dict, List
import logging


class StrategyBaseBuy(ABC):
    """
    买入策略代码抽象基类
    
    所有买入策略代码都必须继承此类并实现抽象方法。
    系统会在执行时实例化策略类并调用相应方法。
    
    使用示例：
        class MyBuyStrategy(StrategyBaseBuy):
            def execute_buy_decision(self, candidates, portfolio, account_info, 
                                    market_state):
                # 使用日志输出关键信息
                self.log.info("开始执行买入决策")
                # 实现买入决策逻辑
                self.log.info(f"处理候选交易对数量: {len(candidates)}")
                return {"SYMBOL": {...}}
    """
    
    def __init__(self):
        """初始化策略基类，设置日志记录器"""
        # 创建日志记录器，使用类名作为logger名称
        logger_name = f"{self.__class__.__module__}.{self.__class__.__name__}"
        self.log = logging.getLogger(logger_name)
        # 如果logger没有处理器，添加一个控制台处理器
        if not self.log.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s [%(levelname)s] %(name)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            self.log.addHandler(handler)
            self.log.setLevel(logging.INFO)
    
    @abstractmethod
    def execute_buy_decision(
        self,
        candidates: List[Dict],
        portfolio: Dict,
        account_info: Dict,
        market_state: Dict
    ) -> Dict[str, Dict]:
        """
        执行买入决策（抽象方法）
        
        子类必须实现此方法，根据候选交易对列表生成买入/开仓决策。
        
        Args:
            candidates: 候选交易对列表，每个元素包含：
                - symbol: 交易对符号（如 'BTC'）
                - contract_symbol: 合约符号（如 'BTCUSDT'）
                - price: 当前价格
                - quote_volume: 24小时成交额
            portfolio: 持仓组合信息，包含：
                - positions: 当前持仓列表
                - cash: 可用现金
                - total_value: 账户总值
            account_info: 账户信息，包含：
                - balance: 账户余额
                - available_balance: 可用余额
                - total_return: 累计收益率
            market_state: 市场状态字典，key为交易对符号，value包含：
                - price: 当前价格
                - contract_symbol: 合约符号
                - quote_volume: 24小时成交额
                - change_24h: 24小时涨跌幅
                - indicators: 技术指标数据
                    - timeframes: 多时间周期的技术指标
                    格式：{"1h": {"klines": [...]}, "4h": {...}, ...}
        
        Returns:
            Dict[str, Dict]: 决策字典，格式为：
                {
                    "SYMBOL": {
                        "signal": "buy_to_long" | "buy_to_short",
                        "quantity": 100,
                        "leverage": 10,
                        "justification": "理由说明"
                    }
                }
                如果没有决策，返回空字典 {}
        
        Note:
            - 从 market_state 中获取技术指标数据：market_state[symbol]['indicators']['timeframes']
            - 从 market_state 中获取当前价格：market_state[symbol]['price']
            - 约束条件可以从 portfolio 中获取（如 cash、positions 数量等）
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
            'datetime': 'Python 日期时间库（内置）',
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

