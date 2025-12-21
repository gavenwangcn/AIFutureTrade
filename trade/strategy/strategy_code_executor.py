"""
Strategy Code Executor - 策略代码执行器

本模块提供StrategyCodeExecutor类，用于安全地执行策略代码。
支持TA-Lib库和动态代码加载，提供安全的执行环境。

主要功能：
1. 安全执行策略代码：在受限环境中执行用户提供的策略代码
2. TA-Lib支持：预加载TA-Lib库，支持技术指标计算
3. 动态模块加载：使用importlib动态加载和执行代码
4. 上下文管理：提供candidates、portfolio、account_info等上下文数据
"""
import importlib.util
import sys
import types
import logging
from typing import Any, Dict, Optional, List, Tuple
from abc import ABC, abstractmethod
import traceback
import json
import datetime

logger = logging.getLogger(__name__)

# 尝试导入TA-Lib和numpy、pandas
try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    logger.warning("TA-Lib not available, strategy code using TA-Lib will fail")

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logger.warning("NumPy not available")

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    logger.warning("Pandas not available")


class StrategyCodeExecutor:
    """
    策略代码执行器
    
    提供安全的策略代码执行环境，支持TA-Lib、numpy、pandas等库。
    用于执行model_strategy表中的strategy_code字段内容。
    
    使用示例：
        executor = StrategyCodeExecutor()
        result = executor.execute_strategy_code(
            strategy_code="...",
            strategy_name="测试策略",
            candidates=[...],
            portfolio={...},
            account_info={...},
            market_state={...},
            decision_type='buy'
        )
    """
    
    def __init__(self, 
                 preload_talib: bool = True,
                 allow_imports: List[str] = None):
        """
        初始化执行器
        
        Args:
            preload_talib: 是否预加载TA-Lib库
            allow_imports: 允许导入的模块列表（额外允许的模块）
        """
        self.modules = {}
        self.module_counter = 0
        self.execution_history = []
        
        # 预加载允许的模块
        self.allowed_modules = {}
        
        # 加载TA-Lib
        if preload_talib and TALIB_AVAILABLE:
            try:
                self.allowed_modules['talib'] = talib
                self.allowed_modules['TA'] = talib  # 别名
                logger.debug("TA-Lib 库加载成功")
            except Exception as e:
                logger.warning(f"无法加载 TA-Lib: {e}")
        
        # 加载NumPy
        if NUMPY_AVAILABLE:
            self.allowed_modules['numpy'] = np
            self.allowed_modules['np'] = np
        
        # 加载Pandas
        if PANDAS_AVAILABLE:
            self.allowed_modules['pandas'] = pd
            self.allowed_modules['pd'] = pd
        
        # 默认允许的模块
        default_allowed = ['math', 'datetime', 'json', 'time', 'random']
        if allow_imports:
            default_allowed.extend(allow_imports)
        
        for module_name in default_allowed:
            try:
                module = __import__(module_name)
                self.allowed_modules[module_name] = module
            except ImportError:
                pass
        
        logger.info(f"[StrategyCodeExecutor] 初始化完成，已加载模块: {list(self.allowed_modules.keys())}")
    
    def _create_safe_globals(self, extra_globals: Dict = None) -> Dict:
        """
        创建安全的全局变量环境
        
        Args:
            extra_globals: 额外的全局变量字典
        
        Returns:
            Dict: 安全的全局变量字典
        """
        safe_globals = {
            '__builtins__': {
                'print': print,
                'len': len,
                'str': str,
                'int': int,
                'float': float,
                'list': list,
                'dict': dict,
                'tuple': tuple,
                'set': set,
                'range': range,
                'sum': sum,
                'min': min,
                'max': max,
                'abs': abs,
                'round': round,
                'sorted': sorted,
                'enumerate': enumerate,
                'zip': zip,
                'isinstance': isinstance,
                'type': type,
                'bool': bool,
                'True': True,
                'False': False,
                'None': None,
            },
            '__name__': '__main__',
            '__doc__': None,
        }
        
        # 添加允许的模块
        safe_globals.update(self.allowed_modules)
        
        # 添加额外的全局变量
        if extra_globals:
            safe_globals.update(extra_globals)
            
        return safe_globals
    
    def execute_strategy_code(
        self,
        strategy_code: str,
        strategy_name: str,
        candidates: Optional[List[Dict]] = None,
        portfolio: Optional[Dict] = None,
        account_info: Optional[Dict] = None,
        market_state: Optional[Dict] = None,
        decision_type: str = 'buy'
    ) -> Optional[Dict]:
        """
        执行策略代码
        
        在安全的执行环境中执行策略代码。策略代码必须是一个继承自 StrategyBase 的类。
        系统会实例化策略类并调用相应的方法。
        
        Args:
            strategy_code: 策略代码字符串（必须是一个继承 StrategyBase 的类定义）
            strategy_name: 策略名称（用于日志）
            candidates: 候选交易对列表（买入决策需要）
            portfolio: 持仓组合信息
            account_info: 账户信息
            market_state: 市场状态字典，key为交易对符号，value包含价格、技术指标等
            decision_type: 决策类型，'buy' 或 'sell'
        
        Returns:
            Optional[Dict]: 策略代码返回的决策结果，格式为：
                {
                    "decisions": {
                        "SYMBOL": {
                            "signal": "...",
                            ...
                        }
                    }
                }
                如果执行失败或返回None，则返回None
        
        Note:
            - 策略代码接口统一使用 market_state，不再使用 market_snapshot 和 constraints
            - market_state 格式：{"SYMBOL": {"price": float, "indicators": {"timeframes": {...}}}, ...}
        """
        try:
            # 构建执行上下文
            execution_context = self._create_safe_globals()
            
            # 根据决策类型导入对应的策略基类
            if decision_type == 'buy':
                from trade.strategy.strategy_template_buy import StrategyBaseBuy
                execution_context['StrategyBaseBuy'] = StrategyBaseBuy
                StrategyBase = StrategyBaseBuy
                base_class_name = 'StrategyBaseBuy'
            elif decision_type == 'sell':
                from trade.strategy.strategy_template_sell import StrategyBaseSell
                execution_context['StrategyBaseSell'] = StrategyBaseSell
                StrategyBase = StrategyBaseSell
                base_class_name = 'StrategyBaseSell'
            else:
                # 未知的决策类型，抛出错误
                raise ValueError(f"不支持的决策类型: {decision_type}，仅支持 'buy' 或 'sell'")
            
            execution_context['StrategyBase'] = StrategyBase
            execution_context['ABC'] = ABC
            execution_context['abstractmethod'] = abstractmethod
            
            # 添加 typing 模块（用于类型注解）
            try:
                from typing import Dict, List, Optional
                execution_context['Dict'] = Dict
                execution_context['List'] = List
                execution_context['Optional'] = Optional
            except ImportError:
                pass
            
            # 生成唯一的模块名
            self.module_counter += 1
            module_name = f"strategy_module_{self.module_counter}_{strategy_name.replace(' ', '_')}"
            
            # 创建模块
            module = types.ModuleType(module_name)
            
            # 执行策略代码（定义策略类）
            # 策略代码应该定义一个继承 StrategyBase 的类
            exec(strategy_code, execution_context, module.__dict__)
            
            # 存储模块引用
            self.modules[module_name] = module
            
            # 查找策略类（查找第一个继承自对应基类的类）
            strategy_class = None
            for name in dir(module):
                obj = getattr(module, name)
                if (isinstance(obj, type) and 
                    issubclass(obj, StrategyBase) and 
                    obj != StrategyBase):
                    strategy_class = obj
                    logger.debug(f"[StrategyCodeExecutor] 找到策略类: {name} (继承自 {base_class_name})")
                    break
            
            if strategy_class is None:
                raise ValueError(f"策略代码中未找到继承自 {base_class_name} 的类")
            
            # 实例化策略类
            strategy_instance = strategy_class()
            
            # 根据决策类型调用相应方法
            if decision_type == 'buy':
                # 调用买入决策方法（统一使用 market_state）
                decisions = strategy_instance.execute_buy_decision(
                    candidates=candidates or [],
                    portfolio=portfolio or {},
                    account_info=account_info or {},
                    market_state=market_state or {}
                )
            elif decision_type == 'sell':
                # 调用卖出决策方法
                decisions = strategy_instance.execute_sell_decision(
                    portfolio=portfolio or {},
                    market_state=market_state or {},
                    account_info=account_info or {}
                )
            else:
                raise ValueError(f"未知的决策类型: {decision_type}")
            
            # 验证返回结果格式
            if decisions is None:
                decisions = {}
            
            if not isinstance(decisions, dict):
                raise ValueError(f"策略方法返回结果格式不正确，期望 dict，实际 {type(decisions)}")
            
            # 包装成标准格式
            result = {
                "decisions": decisions
            }
            
            # 记录执行历史
            self.execution_history.append({
                'timestamp': datetime.datetime.now().isoformat(),
                'module': module_name,
                'strategy_name': strategy_name,
                'strategy_class': strategy_class.__name__,
                'decision_type': decision_type,
                'success': True,
                'decisions_count': len(decisions)
            })
            
            logger.info(f"[StrategyCodeExecutor] 策略 {strategy_name} 执行成功，返回决策数: {len(decisions)}")
            return result
        
        except Exception as e:
            error_info = {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc(),
                'code_snippet': strategy_code[:200] + "..." if len(strategy_code) > 200 else strategy_code
            }
            
            self.execution_history.append({
                'timestamp': datetime.datetime.now().isoformat(),
                'module': module_name if 'module_name' in locals() else 'unknown',
                'strategy_name': strategy_name,
                'decision_type': decision_type,
                'success': False,
                'error': str(e)
            })
            
            logger.error(f"[StrategyCodeExecutor] 执行策略代码失败 ({strategy_name}): {e}")
            logger.debug(f"[StrategyCodeExecutor] 异常堆栈:\n{traceback.format_exc()}")
            return None
    
    def get_execution_history(self) -> List[Dict]:
        """
        获取执行历史记录
        
        Returns:
            List[Dict]: 执行历史记录列表
        """
        return self.execution_history.copy()
    
    def clear_history(self):
        """清空执行历史记录"""
        self.execution_history.clear()
        logger.debug("[StrategyCodeExecutor] 执行历史已清空")

