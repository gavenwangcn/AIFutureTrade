"""测试运行辅助脚本

用于验证所有测试文件的导入是否正确，并运行测试。

用法:
    python tests/run_tests.py [test_name]

示例:
    python tests/run_tests.py test_database_mysql
    python tests/run_tests.py  # 运行所有测试
"""
import sys
import importlib
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def test_imports():
    """测试所有模块的导入"""
    print("=" * 80)
    print("测试模块导入...")
    print("=" * 80)
    
    modules_to_test = [
        ("common.config", "配置模块"),
        ("common.database_mysql", "MySQL数据库模块"),
        ("common.binance_futures", "币安期货客户端模块"),
        ("market.market_data", "市场数据模块"),
        ("market.market_streams", "市场数据流模块"),
        ("trade.ai_trader", "AI交易器模块"),
        ("trade.trading_engine", "交易引擎模块"),
        ("trade.prompt_defaults", "提示词默认值模块"),
        ("backend.app", "后端应用模块"),
        ("data.data_agent", "数据代理模块"),
        ("data.data_manager", "数据管理器模块"),
        ("async.async_agent", "异步代理模块"),
    ]
    
    failed_imports = []
    for module_name, description in modules_to_test:
        try:
            importlib.import_module(module_name)
            print(f"✅ {module_name:40s} - {description}")
        except Exception as e:
            print(f"❌ {module_name:40s} - {description}")
            print(f"   错误: {e}")
            failed_imports.append((module_name, str(e)))
    
    print("=" * 80)
    if failed_imports:
        print(f"❌ {len(failed_imports)} 个模块导入失败")
        return False
    else:
        print(f"✅ 所有 {len(modules_to_test)} 个模块导入成功")
        return True


def run_test(test_name: str = None):
    """运行指定的测试或所有测试"""
    if test_name:
        print(f"\n运行测试: {test_name}")
        print("=" * 80)
        try:
            test_module = importlib.import_module(f"tests.{test_name}")
            if hasattr(test_module, 'main'):
                result = test_module.main()
                return result == 0
            else:
                print(f"警告: {test_name} 没有 main() 函数")
                return True
        except Exception as e:
            print(f"❌ 运行测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    else:
        # 运行所有测试
        test_files = [
            "test_database_mysql",
            "test_binance_futures_client",
            "test_leaderboard_sync",
        ]
        
        results = []
        for test_file in test_files:
            print(f"\n{'=' * 80}")
            print(f"运行测试: {test_file}")
            print("=" * 80)
            try:
                test_module = importlib.import_module(f"tests.{test_file}")
                if hasattr(test_module, 'main'):
                    result = test_module.main()
                    results.append((test_file, result == 0))
                else:
                    print(f"⚠️  {test_file} 没有 main() 函数，跳过")
                    results.append((test_file, None))
            except Exception as e:
                print(f"❌ {test_file} 运行失败: {e}")
                results.append((test_file, False))
        
        print("\n" + "=" * 80)
        print("测试结果汇总:")
        print("=" * 80)
        for test_file, success in results:
            if success is True:
                print(f"✅ {test_file}")
            elif success is False:
                print(f"❌ {test_file}")
            else:
                print(f"⚠️  {test_file} (跳过)")
        
        all_passed = all(success for _, success in results if success is not None)
        return all_passed


if __name__ == "__main__":
    # 首先测试导入
    imports_ok = test_imports()
    
    if not imports_ok:
        print("\n❌ 模块导入失败，请检查错误信息")
        sys.exit(1)
    
    # 运行测试
    test_name = sys.argv[1] if len(sys.argv) > 1 else None
    tests_ok = run_test(test_name)
    
    if tests_ok:
        print("\n✅ 所有测试通过")
        sys.exit(0)
    else:
        print("\n❌ 部分测试失败")
        sys.exit(1)

