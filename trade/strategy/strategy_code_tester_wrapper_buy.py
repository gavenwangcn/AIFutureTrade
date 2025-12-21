#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
策略代码测试器包装脚本 - 买入策略
用于Java后端调用，接收策略代码文件路径，执行测试并返回JSON格式结果
"""

import sys
import json
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from trade.strategy.strategy_code_tester_buy import StrategyCodeTesterBuy

def main():
    if len(sys.argv) < 3:
        print(json.dumps({
            "passed": False,
            "errors": ["参数不足，需要策略代码文件路径和策略名称"],
            "warnings": [],
            "test_results": {}
        }), file=sys.stderr)
        sys.exit(1)
    
    strategy_code_file = sys.argv[1]
    strategy_name = sys.argv[2] if len(sys.argv) > 2 else "测试买入策略"
    
    try:
        # 读取策略代码文件
        with open(strategy_code_file, 'r', encoding='utf-8') as f:
            strategy_code = f.read()
        
        # 执行测试
        tester = StrategyCodeTesterBuy()
        result = tester.test_strategy_code(strategy_code, strategy_name)
        
        # 输出JSON结果
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
        # 根据测试结果设置退出码
        sys.exit(0 if result.get('passed', False) else 1)
        
    except Exception as e:
        error_result = {
            "passed": False,
            "errors": [f"测试执行异常: {str(e)}"],
            "warnings": [],
            "test_results": {}
        }
        print(json.dumps(error_result, ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

