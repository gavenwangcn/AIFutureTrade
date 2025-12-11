"""Manual connectivity test harness for common.binance_futures.BinanceFuturesAccountClient.

Usage:
    export BINANCE_API_KEY=...
    export BINANCE_API_SECRET=...
    python tests/test_binance_futures_account_client.py

This script tests the BinanceFuturesAccountClient class and its methods to verify
that account information and asset balance can be retrieved correctly.
"""

import logging
import os
import sys
from pathlib import Path
import json

# 添加项目根目录到Python路径，以便导入项目模块
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from common.binance_futures import BinanceFuturesAccountClient
import common.config as config
BINANCE_API_KEY = getattr(config, 'BINANCE_API_KEY', None)
BINANCE_API_SECRET = getattr(config, 'BINANCE_API_SECRET', None)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


def _load_credentials() -> tuple[str, str]:
    api_key = BINANCE_API_KEY or os.getenv("BINANCE_API_KEY")
    api_secret = BINANCE_API_SECRET or os.getenv("BINANCE_API_SECRET")
    if not api_key or not api_secret:
        raise RuntimeError(
            "Please configure BINANCE_API_KEY and BINANCE_API_SECRET in config.py or env vars before running this test."
        )
    return api_key, api_secret


def test_get_account(api_key: str, api_secret: str) -> None:
    """
    测试 get_account() 方法
    
    Args:
        api_key: Binance API密钥
        api_secret: Binance API密钥
    """
    client = BinanceFuturesAccountClient(api_key=api_key, api_secret=api_secret)
    logging.info("Created BinanceFuturesAccountClient: quote_asset=%s", client.quote_asset)
    
    logging.info("Testing get_account()...")
    try:
        account_info_json = client.get_account()
        # 解析JSON以验证格式
        account_info = json.loads(account_info_json)
        logging.info("account json: %s", account_info_json)
        logging.info("get_account() returned valid JSON data")
        logging.info(f"Account info keys: {list(account_info.keys())[:10]}...")
        # 打印部分重要信息
        if 'accountType' in account_info:
            logging.info(f"Account type: {account_info['accountType']}")
        if 'positions' in account_info:
            logging.info(f"Number of positions: {len(account_info['positions'])}")
        logging.info("get_account() test passed")
    except Exception as e:
        logging.error(f"Error in get_account(): {e}", exc_info=True)
        raise


def test_get_account_asset(api_key: str, api_secret: str) -> None:
    """
    测试 get_account_asset() 方法
    
    Args:
        api_key: Binance API密钥
        api_secret: Binance API密钥
    """
    client = BinanceFuturesAccountClient(api_key=api_key, api_secret=api_secret)
    logging.info("Created BinanceFuturesAccountClient: quote_asset=%s", client.quote_asset)
    
    logging.info("Testing get_account_asset()...")
    try:
        account_asset_json = client.get_account_asset()
        # 解析JSON以验证格式
        account_asset = json.loads(account_asset_json)
        logging.info("account asset json: %s", account_asset_json)
        logging.info("get_account_asset() returned valid JSON data")
        if isinstance(account_asset, list):
            logging.info(f"Number of assets: {len(account_asset)}")
            # 打印部分资产信息
            for asset in account_asset[:3]:
                if isinstance(asset, dict) and 'asset' in asset:
                    asset_name = asset['asset']
                    balance = asset.get('balance', 'N/A')
                    wallet_balance = asset.get('walletBalance', 'N/A')
                    logging.info(f"Asset: {asset_name}, Balance: {balance}, Wallet Balance: {wallet_balance}")
        elif isinstance(account_asset, dict):
            logging.info(f"Asset info keys: {list(account_asset.keys())[:10]}...")
        logging.info("get_account_asset() test passed")
    except Exception as e:
        logging.error(f"Error in get_account_asset(): {e}", exc_info=True)
        raise


def exercise_binance_futures_account_client(api_key: str, api_secret: str) -> None:
    """
    执行所有测试方法
    
    Args:
        api_key: Binance API密钥
        api_secret: Binance API密钥
    """
    logging.info("=" * 60)
    logging.info("Starting BinanceFuturesAccountClient tests")
    logging.info("=" * 60)
    
    # 测试get_account方法
    test_get_account(api_key, api_secret)
    
    # 测试get_account_asset方法
    #test_get_account_asset(api_key, api_secret)
    
    logging.info("=" * 60)
    logging.info("All BinanceFuturesAccountClient method calls completed.")
    logging.info("=" * 60)


if __name__ == "__main__":
    api_key_value, api_secret_value = _load_credentials()
    exercise_binance_futures_account_client(api_key_value, api_secret_value)
