"""
Account management database operations module
Provides account-related database operations, including add, delete, query and other functions
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from .database_basic import Database

logger = logging.getLogger(__name__)


class AccountDatabase:
    """Account management database operations class"""
    
    def __init__(self, auto_init_tables: bool = True):
        """
        Initialize account database operations
        
        Args:
            auto_init_tables: Whether to automatically initialize table structure, default True (Note: table structure is managed uniformly in database_basic.py)
        """
        self.db = Database()
        self.account_asset_table = "account_asset"
        self.asset_table = "asset"
    
    def add_account(
        self,
        account_name: str,
        api_key: str,
        api_secret: str,
        account_asset_data: Dict[str, Any],
        asset_list: List[Dict[str, Any]]
    ) -> str:
        """
        Add account information
        
        Args:
            account_name: Account Chinese name (required)
            api_key: API key
            api_secret: API secret
            account_asset_data: Account asset summary data returned by get_account (parsed, contains totalInitialMargin and other fields)
            asset_list: Assets array returned by get_account (parsed, does not include positions)
            
        Returns:
            account_alias string (auto-generated)
        """
        import hashlib
        import time
        
        if not account_name or not account_name.strip():
            raise ValueError("account_name is required and cannot be empty")
        
        # Generate account_alias: use first 8 characters of api_key hash + last 6 characters of timestamp
        api_key_hash = hashlib.md5(api_key.encode()).hexdigest()[:8]
        timestamp_suffix = str(int(time.time()))[-6:]
        account_alias = f"{api_key_hash}_{timestamp_suffix}"
        
        # Get current timestamp (milliseconds)
        update_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        
        # Insert into account_asset table (includes account_name, api_key and api_secret)
        account_asset_insert = f"""
        INSERT INTO `{self.account_asset_table}` 
        (`account_alias`, `account_name`, `api_key`, `api_secret`, `total_initial_margin`, `total_maint_margin`, `total_wallet_balance`, 
         `total_unrealized_profit`, `total_margin_balance`, `total_position_initial_margin`, 
         `total_open_order_initial_margin`, `total_cross_wallet_balance`, `total_cross_un_pnl`, 
         `available_balance`, `max_withdraw_amount`, `update_time`, `created_at`)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
        `account_name` = VALUES(`account_name`),
        `api_key` = VALUES(`api_key`),
        `api_secret` = VALUES(`api_secret`),
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
                account_name.strip(),
                api_key,
                api_secret,
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
        
        # First delete all asset records for this account, then insert new ones
        self.db.command(f"DELETE FROM `{self.asset_table}` WHERE `account_alias` = %s", (account_alias,))
        
        # Insert into asset table (one record per asset)
        if asset_list:
            # Use insert_rows method for batch insert
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
        Delete account information (cascade delete asset table data)
        
        Args:
            account_alias: Account unique identifier
            
        Returns:
            Whether deletion was successful
        """
        try:
            # First delete asset table data (due to foreign key CASCADE, deleting account_asset will automatically delete asset table data)
            self.db.command(f"DELETE FROM `{self.asset_table}` WHERE `account_alias` = %s", (account_alias,))
            # Delete account_asset table data
            self.db.command(f"DELETE FROM `{self.account_asset_table}` WHERE `account_alias` = %s", (account_alias,))
            logger.info(f"[AccountDatabase] Account deleted successfully: account_alias={account_alias}")
            return True
        except Exception as e:
            logger.error(f"[AccountDatabase] Failed to delete account {account_alias}: {e}")
            raise
    
    def get_all_accounts(self) -> List[Dict[str, Any]]:
        """
        Query all account information
        
        Returns:
            Account information list, contains total_wallet_balance (total balance), total_cross_wallet_balance (cross wallet balance), available_balance (order available balance) and other fields
        """
        try:
            query = f"""
            SELECT `account_alias`, `account_name`, `total_wallet_balance`, `total_cross_wallet_balance`, `available_balance`, `update_time`, `created_at`
            FROM `{self.account_asset_table}`
            ORDER BY `created_at` DESC
            """
            rows = self.db.query(query)
            
            accounts = []
            for row in rows:
                accounts.append({
                    'account_alias': row[0],
                    'account_name': row[1] if row[1] else '',  # account_name
                    'balance': float(row[2]) if row[2] is not None else 0.0,  # total_wallet_balance -> balance
                    'crossWalletBalance': float(row[3]) if row[3] is not None else 0.0,  # total_cross_wallet_balance -> crossWalletBalance
                    'availableBalance': float(row[4]) if row[4] is not None else 0.0,  # available_balance -> availableBalance
                    'update_time': row[5] if row[5] is not None else 0,
                    'created_at': row[6].isoformat() if row[6] else None
                })
            
            logger.debug(f"[AccountDatabase] Retrieved {len(accounts)} accounts")
            return accounts
        except Exception as e:
            logger.error(f"[AccountDatabase] Failed to get all accounts: {e}")
            raise
