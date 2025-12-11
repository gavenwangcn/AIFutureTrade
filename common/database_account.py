"""
账户管理数据库操作模块
提供账户相关的数据库操作，包括添加、删除、查询等功能
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from common.database_mysql import MySQLDatabase

logger = logging.getLogger(__name__)


class AccountDatabase:
    """账户管理数据库操作类"""
    
    def __init__(self, auto_init_tables: bool = True):
        """
        初始化账户数据库操作类
        
        Args:
            auto_init_tables: 是否自动初始化表结构，默认True（注意：表结构在database_basic.py中统一管理）
        """
        self.db = MySQLDatabase(auto_init_tables=auto_init_tables)
        self.accounts_table = "accounts"
        self.account_asset_table = "account_asset"
        self.asset_table = "asset"
    
    def add_account(
        self,
        api_key: str,
        api_secret: str,
        account_data: Dict[str, Any],
        account_asset_data: Dict[str, Any],
        asset_list: List[Dict[str, Any]]
    ) -> str:
        """
        添加账户信息
        
        Args:
            api_key: API密钥
            api_secret: API密钥
            account_data: get_account返回的账户数据（已解析）
            account_asset_data: get_account_asset返回的账户资产汇总数据（已解析）
            asset_list: get_account_asset返回的资产列表（已解析，不包含positions）
            
        Returns:
            account_alias字符串
        """
        # 从account_data中提取account_alias（SDK返回的字段名可能是accountAlias或account_alias）
        account_alias = account_data.get('accountAlias') or account_data.get('account_alias')
        
        if not account_alias:
            logger.error(f"account_alias not found in account_data. Available keys: {list(account_data.keys())}")
            raise ValueError("account_alias not found in account_data. Please check SDK response structure.")
        
        # 获取当前时间戳（毫秒）
        update_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        
        # 从account_data中提取字段
        balance = float(account_data.get('totalWalletBalance', 0))
        cross_wallet_balance = float(account_data.get('totalCrossWalletBalance', 0))
        available_balance = float(account_data.get('availableBalance', 0))
        
        # 插入account表
        account_insert = f"""
        INSERT INTO `{self.accounts_table}` 
        (`account_alias`, `api_key`, `api_secret`, `balance`, `cross_wallet_balance`, `available_balance`, `update_time`, `created_at`)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
        `api_key` = VALUES(`api_key`),
        `api_secret` = VALUES(`api_secret`),
        `balance` = VALUES(`balance`),
        `cross_wallet_balance` = VALUES(`cross_wallet_balance`),
        `available_balance` = VALUES(`available_balance`),
        `update_time` = VALUES(`update_time`)
        """
        self.db.command(
            account_insert,
            (account_alias, api_key, api_secret, balance, cross_wallet_balance, available_balance, update_time, datetime.now(timezone.utc))
        )
        
        # 插入account_asset表
        account_asset_insert = f"""
        INSERT INTO `{self.account_asset_table}` 
        (`account_alias`, `total_initial_margin`, `total_maint_margin`, `total_wallet_balance`, 
         `total_unrealized_profit`, `total_margin_balance`, `total_position_initial_margin`, 
         `total_open_order_initial_margin`, `total_cross_wallet_balance`, `total_cross_un_pnl`, 
         `available_balance`, `max_withdraw_amount`, `update_time`, `created_at`)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
        `total_initial_margin` = VALUES(`total_initial_margin`),
        `total_maint_margin` = VALUES(`total_maint_margin`),
        `total_wallet_balance` = VALUES(`total_wallet_balance`),
        `total_unrealized_profit` = VALUES(`total_unrealized_profit`),
        `total_margin_balance` = VALUES(`total_margin_balance`),
        `total_position_initial_margin` = VALUES(`total_position_initial_margin`),
        `total_open_order_initial_margin` = VALUES(`total_open_order_initial_margin`),
        `total_cross_wallet_balance` = VALUES(`total_cross_wallet_balance`),
        `total_cross_un_pnl` = VALUES(`total_cross_un_pnl`),
        `available_balance` = VALUES(`available_balance`),
        `max_withdraw_amount` = VALUES(`max_withdraw_amount`),
        `update_time` = VALUES(`update_time`)
        """
        self.db.command(
            account_asset_insert,
            (
                account_alias,
                float(account_asset_data.get('totalInitialMargin', 0)),
                float(account_asset_data.get('totalMaintMargin', 0)),
                float(account_asset_data.get('totalWalletBalance', 0)),
                float(account_asset_data.get('totalUnrealizedProfit', 0)),
                float(account_asset_data.get('totalMarginBalance', 0)),
                float(account_asset_data.get('totalPositionInitialMargin', 0)),
                float(account_asset_data.get('totalOpenOrderInitialMargin', 0)),
                float(account_asset_data.get('totalCrossWalletBalance', 0)),
                float(account_asset_data.get('totalCrossUnPnl', 0)),
                float(account_asset_data.get('availableBalance', 0)),
                float(account_asset_data.get('maxWithdrawAmount', 0)),
                update_time,
                datetime.now(timezone.utc)
            )
        )
        
        # 先删除该账户的所有asset记录，再插入新的
        self.db.command(f"DELETE FROM `{self.asset_table}` WHERE `account_alias` = %s", (account_alias,))
        
        # 插入asset表（每个资产一条记录）
        if asset_list:
            # 使用insert_rows方法批量插入
            asset_rows = []
            for asset_item in asset_list:
                asset_rows.append([
                    account_alias,
                    asset_item.get('asset', ''),
                    float(asset_item.get('walletBalance', 0)),
                    float(asset_item.get('unrealizedProfit', 0)),
                    float(asset_item.get('marginBalance', 0)),
                    float(asset_item.get('maintMargin', 0)),
                    float(asset_item.get('initialMargin', 0)),
                    float(asset_item.get('positionInitialMargin', 0)),
                    float(asset_item.get('openOrderInitialMargin', 0)),
                    float(asset_item.get('crossWalletBalance', 0)),
                    float(asset_item.get('crossUnPnl', 0)),
                    float(asset_item.get('availableBalance', 0)),
                    float(asset_item.get('maxWithdrawAmount', 0)),
                    update_time,
                    datetime.now(timezone.utc)
                ])
            self.db.insert_rows(
                self.asset_table,
                asset_rows,
                ['account_alias', 'asset', 'wallet_balance', 'unrealized_profit', 'margin_balance',
                 'maint_margin', 'initial_margin', 'position_initial_margin', 'open_order_initial_margin',
                 'cross_wallet_balance', 'cross_un_pnl', 'available_balance', 'max_withdraw_amount', 'update_time', 'created_at']
            )
        
        logger.info(f"[AccountDatabase] Account added successfully: account_alias={account_alias}")
        return account_alias
    
    def delete_account(self, account_alias: str) -> bool:
        """
        删除账户信息（级联删除account_asset和asset表的数据）
        
        Args:
            account_alias: 账户唯一标识
            
        Returns:
            是否删除成功
        """
        try:
            # 由于设置了外键CASCADE，删除account表记录会自动删除account_asset和asset表的记录
            self.db.command(f"DELETE FROM `{self.accounts_table}` WHERE `account_alias` = %s", (account_alias,))
            logger.info(f"[AccountDatabase] Account deleted successfully: account_alias={account_alias}")
            return True
        except Exception as e:
            logger.error(f"[AccountDatabase] Failed to delete account {account_alias}: {e}")
            raise
    
    def get_all_accounts(self) -> List[Dict[str, Any]]:
        """
        查询所有账户信息
        
        Returns:
            账户信息列表，包含balance、crossWalletBalance、availableBalance等字段
        """
        try:
            query = f"""
            SELECT `account_alias`, `balance`, `cross_wallet_balance`, `available_balance`, `update_time`, `created_at`
            FROM `{self.accounts_table}`
            ORDER BY `created_at` DESC
            """
            rows = self.db.query(query)
            
            accounts = []
            for row in rows:
                accounts.append({
                    'account_alias': row[0],
                    'balance': float(row[1]) if row[1] is not None else 0.0,
                    'crossWalletBalance': float(row[2]) if row[2] is not None else 0.0,
                    'availableBalance': float(row[3]) if row[3] is not None else 0.0,
                    'update_time': row[4] if row[4] is not None else 0,
                    'created_at': row[5].isoformat() if row[5] else None
                })
            
            logger.debug(f"[AccountDatabase] Retrieved {len(accounts)} accounts")
            return accounts
        except Exception as e:
            logger.error(f"[AccountDatabase] Failed to get all accounts: {e}")
            raise

