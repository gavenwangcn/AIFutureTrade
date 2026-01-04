"""
Basic database operation module - MySQL implementation

This module provides the Database class, which encapsulates all MySQL database operations for business data, including:
1. Provider management: CRUD operations for LLM providers
2. Model management: CRUD operations and configuration management for trading models
3. Portfolio management: Position tracking and account value recording
4. Trade records: Recording and querying trade history
5. Conversation records: Recording and querying AI conversation history
6. Contract configuration: Futures contract configuration management
7. Account assets: Account asset information management
8. Prompt management: Model buy/sell prompt configuration

Main components:
- Database: Basic database operation encapsulation class

Usage scenarios:
- Backend API: Provides data access for all business APIs
- Trading engine: The trading_engine module uses Database to manage models, positions, and trade records
- Frontend display: Uses Database indirectly through backend APIs to query data

Notes:
- Uses MySQL connection pool to manage database connections
- All table structures are automatically created in init_db()
- UUID and integer ID conversion for compatibility
"""
import logging
import time
import uuid
import trade.common.config as app_config
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any, Callable
from .database_init import (
    init_database_tables, 
    PROVIDERS_TABLE, MODELS_TABLE, PORTFOLIOS_TABLE, TRADES_TABLE,
    CONVERSATIONS_TABLE, ACCOUNT_VALUES_TABLE, ACCOUNT_VALUE_HISTORYS_TABLE,
    SETTINGS_TABLE, MODEL_PROMPTS_TABLE, MODEL_FUTURES_TABLE, FUTURES_TABLE,
    ACCOUNT_ASSET_TABLE, ASSET_TABLE, BINANCE_TRADE_LOGS_TABLE,
    STRATEGYS_TABLE, MODEL_STRATEGY_TABLE, STRATEGY_DECISIONS_TABLE
)
import pymysql
from pymysql import cursors
from dbutils.pooled_db import PooledDB

logger = logging.getLogger(__name__)


def create_pooled_db(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    charset: str = 'utf8mb4',
    mincached: int = 5,
    maxconnections: int = 50,
    blocking: bool = True
) -> PooledDB:
    """
    Create DBUtils connection pool
    
    Args:
        host: MySQL host
        port: MySQL port
        user: MySQL username
        password: MySQL password
        database: MySQL database name
        charset: Character set, default utf8mb4
        mincached: Minimum number of cached connections
        maxconnections: Maximum number of connections allowed
        blocking: Whether to block when pool is exhausted
        
    Returns:
        DBUtils PooledDB instance
    """
    def _create_connection():
        """Factory function to create a single connection"""
        return pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset=charset,
            cursorclass=cursors.DictCursor,
            autocommit=False
        )
    
    return PooledDB(
        creator=_create_connection,
        mincached=mincached,
        maxconnections=maxconnections,
        maxshared=maxconnections,  # Maximum number of shared connections
        maxcached=maxconnections,  # Maximum number of cached connections
        blocking=blocking,
        maxusage=None,  # Maximum usage count per connection, None means unlimited
        setsession=None,  # SQL statement list for session setup
        reset=True,  # Reset connection when returned
        failures=None,  # Number of retry attempts on failure
        ping=1,  # Ping database when acquiring connection (1=ping on every acquisition)
    )


class Database:
    """
    Basic database operation encapsulation class
    
    Encapsulates all MySQL database operations for business data, including providers, models, portfolios, trade records, etc.
    Uses connection pool to manage database connections, supporting high concurrency access.
    
    Main features:
    - Provider management: Query LLM providers (CRUD operations migrated to Java backend)
    - Model management: Query and configure trading models (CRUD operations migrated to Java backend)
    - Portfolio management: Position updates, account value recording, portfolio queries (account value recording migrated to database_account_values.AccountValuesDatabase)
    - Trade records: Recording and querying trade history (migrated to database_trades.TradesDatabase)
    - Conversation records: Recording and querying AI conversation history (migrated to database_conversations.ConversationsDatabase)
    - Account value history: Query account value history (migrated to database_account_value_historys.AccountValueHistorysDatabase)
    - Contract configuration: Query futures contract configuration (CRUD operations migrated to Java backend)
    - Account assets: Query account asset information (CRUD operations migrated to Java backend)
    - Prompt management: Model buy/sell prompt configuration
    
    Usage example:
        db = Database()
        db.init_db()  # Initialize all tables
        from trade.common.database.database_models import ModelsDatabase
        from trade.common.database.database_portfolios import PortfoliosDatabase
        from trade.common.database.database_trades import TradesDatabase
        from trade.common.database.database_conversations import ConversationsDatabase
        from trade.common.database.database_account_values import AccountValuesDatabase
        from trade.common.database.database_account_value_historys import AccountValueHistorysDatabase
        models_db = ModelsDatabase(pool=db._pool)
        portfolios_db = PortfoliosDatabase(pool=db._pool)
        trades_db = TradesDatabase(pool=db._pool)
        conversations_db = ConversationsDatabase(pool=db._pool)
        account_values_db = AccountValuesDatabase(pool=db._pool)
        account_value_historys_db = AccountValueHistorysDatabase(pool=db._pool)
        model = models_db.get_model(model_id)
        portfolio = portfolios_db.get_portfolio(model_id, current_prices, ...)
        trades_db.add_trade(model_id, symbol, signal, quantity, price)
        conversations_db.add_conversation(model_id, user_prompt, ai_response)
        account_values_db.record_account_value(model_id, balance, available_balance, cross_wallet_balance)
        history = account_value_historys_db.get_account_value_history(model_id, limit=100)
        db.close()  # Explicitly close connection pool, release resources
    
    Notes:
        - Migrated from ClickHouse to MySQL, maintaining method signatures and return value format compatibility
    """
    
    def __init__(self):
        """
        Initialize database connection
        
        Note:
            - Create MySQL connection pool (minimum 15 connections, maximum 100 connections)
            - Define table names for all business tables
            - Does not automatically initialize table structure, need to call init_db() method
            - Uses MySQL connection information from configuration file
        """
        # 打印数据库连接配置（详细日志）
        import logging
        db_logger = logging.getLogger(__name__)
        db_logger.info("=" * 60)
        db_logger.info("Database Connection Configuration:")
        db_logger.info(f"  Host: {app_config.MYSQL_HOST}")
        db_logger.info(f"  Port: {app_config.MYSQL_PORT}")
        db_logger.info(f"  User: {app_config.MYSQL_USER}")
        db_logger.info(f"  Database: {app_config.MYSQL_DATABASE}")
        db_logger.info(f"  Connection String: mysql://{app_config.MYSQL_USER}@{app_config.MYSQL_HOST}:{app_config.MYSQL_PORT}/{app_config.MYSQL_DATABASE}")
        db_logger.info("=" * 60)
        
        # Use DBUtils connection pool
        self._pool = create_pooled_db(
            host=app_config.MYSQL_HOST,
            port=app_config.MYSQL_PORT,
            user=app_config.MYSQL_USER,
            password=app_config.MYSQL_PASSWORD,
            database=app_config.MYSQL_DATABASE,
            charset='utf8mb4',
            mincached=15,
            maxconnections=100,
            blocking=True
        )
        
        # Table name definitions (import constants from database_init.py)
        self.providers_table = PROVIDERS_TABLE
        self.models_table = MODELS_TABLE
        self.portfolios_table = PORTFOLIOS_TABLE
        self.trades_table = TRADES_TABLE
        self.conversations_table = CONVERSATIONS_TABLE
        self.account_values_table = ACCOUNT_VALUES_TABLE
        self.account_value_historys_table = ACCOUNT_VALUE_HISTORYS_TABLE
        self.settings_table = SETTINGS_TABLE
        self.model_prompts_table = MODEL_PROMPTS_TABLE
        self.model_futures_table = MODEL_FUTURES_TABLE
        self.futures_table = FUTURES_TABLE
        self.account_asset_table = ACCOUNT_ASSET_TABLE
        self.asset_table = ASSET_TABLE
        self.binance_trade_logs_table = BINANCE_TRADE_LOGS_TABLE
        self.strategys_table = STRATEGYS_TABLE
        self.model_strategy_table = MODEL_STRATEGY_TABLE
        self.strategy_decisions_table = STRATEGY_DECISIONS_TABLE
    
    def close(self) -> None:
        """
        Close database connection pool, release all resources
        
        Calling this method will close all active connections in the pool, ensuring resources are properly released.
        Should explicitly call this method when database connections are no longer needed.
        """
        if hasattr(self, '_pool') and self._pool:
            try:
                # DBUtils connection pool automatically manages connections, here we just need to close the pool
                # Note: DBUtils PooledDB does not have close_all method, connections will be automatically closed when object is destroyed
                # But we can trigger cleanup by deleting the reference
                self._pool = None
                logger.info("[Database] Connection pool closed successfully")
            except Exception as e:
                logger.warning(f"[Database] Error closing connection pool: {e}")
    
    def __del__(self) -> None:
        """
        Destructor method, ensures connection pool resources are released
        
        When Database instance is garbage collected, this method will be automatically called to close the connection pool.
        To ensure resources are released in time, it is recommended to explicitly call close() method.
        """
        self.close()
    
    def _with_connection(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function with a MySQL connection from the pool.
        
        Supports automatic retry mechanism, will automatically retry when encountering network errors (up to 3 times).
        
        Args:
            func: Function to execute
            *args: Positional arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function
        
        Returns:
            Function execution result
        
        Raises:
            Exception: If still fails after 3 retries, raises the last exception
        """
        max_retries = 3
        retry_delay = 0.5  # Initial retry delay (seconds)
        
        for attempt in range(max_retries):
            conn = None
            connection_acquired = False
            try:
                # Use DBUtils connection pool to acquire connection
                conn = self._pool.connection()
                if not conn:
                    raise Exception("Failed to acquire MySQL connection")
                connection_acquired = True
                
                # Execute function
                result = func(conn, *args, **kwargs)
                
                # Successfully executed, commit transaction
                conn.commit()
                # DBUtils automatically manages connections, will automatically return after use, no need to manually release
                conn = None  # Mark as processed, avoid duplicate handling in finally block
                return result
                
            except Exception as e:
                # Record error information
                error_type = type(e).__name__
                error_msg = str(e)
                
                # Determine if it is a network/protocol error or deadlock error, needs retry
                # Includes "Packet sequence number wrong" error, which usually indicates connection state inconsistency
                # Includes MySQL deadlock error (1213), which is a resource contention error that needs retry
                # Includes "read of closed file" error, which usually indicates underlying connection is closed
                is_network_error = any(keyword in error_msg.lower() for keyword in [
                    'connection', 'broken', 'lost', 'timeout', 'reset', 'gone away',
                    'operationalerror', 'interfaceerror', 'packet sequence', 'internalerror',
                    'deadlock found', 'read of closed file'
                ]) or any(keyword in error_type.lower() for keyword in [
                    'connection', 'timeout', 'operationalerror', 'interfaceerror', 'internalerror',
                    'valueerror'
                ]) or (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213)
                
                # If connection has been acquired, need to handle connection (close it)
                # Regardless of exception type, ensure connection is properly released to prevent connection leak
                if connection_acquired and conn:
                    try:
                        # Rollback transaction
                        try:
                            conn.rollback()
                        except Exception as rollback_error:
                            logger.debug(f"[Database] Error rolling back transaction: {rollback_error}")
                        
                        # For all errors, close connection, DBUtils will automatically handle damaged connections
                        try:
                            conn.close()
                        except Exception as close_error:
                            logger.debug(f"[Database] Error closing connection: {close_error}")
                        finally:
                            # Ensure connection reference is cleared, mark as processed even if close fails
                            conn = None
                    except Exception as close_error:
                        logger.error(f"[Database] Critical error closing failed connection: {close_error}")
                        # Even if exception occurs, clear connection reference
                        conn = None
                
                # Determine if retry is needed
                if attempt < max_retries - 1:
                    # Only retry for network errors
                    if not is_network_error:
                        # Non-network errors don't retry, raise directly
                        raise
                    
                    # Calculate wait time
                    # Use special retry strategy for deadlock errors (longer initial delay and slower growth)
                    is_deadlock = (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213) or 'deadlock' in error_msg.lower()
                    if is_deadlock:
                        # Deadlock error: initial delay 1 second, growth factor 1.5 (slower growth)
                        wait_time = 1.0 * (1.5 ** attempt)
                        logger.warning(
                            f"[Database] Deadlock error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    else:
                        # Other network errors use exponential backoff strategy
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(
                            f"[Database] Network error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    
                    # Wait then retry
                    time.sleep(wait_time)
                    continue
                else:
                    # Maximum retry count reached, raise exception
                    logger.error(
                        f"[Database] Failed after {max_retries} attempts: "
                        f"{error_type}: {error_msg}"
                    )
                    raise
            finally:
                # Ensure connection is properly handled (double insurance)
                if connection_acquired and conn:
                    try:
                        # If connection hasn't been handled, try to close it
                        logger.warning(
                            f"[Database] Connection not closed in finally block, closing it"
                        )
                        try:
                            conn.rollback()
                            conn.close()
                        except Exception:
                            pass
                        # DBUtils automatically handles connections, no need to manually manage connection count
                    except Exception as final_error:
                        logger.debug(f"[Database] Error in finally block: {final_error}")
    
    def command(self, sql: str, params: tuple = None) -> None:
        """Execute a raw SQL command."""
        def _execute_command(conn):
            cursor = conn.cursor()
            try:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
            finally:
                cursor.close()
        self._with_connection(_execute_command)
    
    def query(self, sql: str, params: tuple = None, as_dict: bool = False) -> List:
        """Execute a query and return results.
        
        Note: MySQL supports parameterized queries, use %s as placeholder.
        
        Args:
            sql: SQL query statement
            params: Query parameter tuple
            as_dict: Whether to return dictionary format (default False, returns tuple list for compatibility)
        
        Returns:
            List: Query result list, returns dictionary list if as_dict=True, otherwise returns tuple list
        """
        def _execute_query(conn):
            if as_dict:
                cursor = conn.cursor(cursors.DictCursor)
            else:
                cursor = conn.cursor()
            try:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                rows = cursor.fetchall()
                # If using dictionary cursor, directly return dictionary list
                if as_dict:
                    return [dict(row) for row in rows] if rows else []
                # Otherwise convert to tuple list for compatibility
                if rows and isinstance(rows[0], dict):
                    return [tuple(row.values()) for row in rows]
                return rows
            finally:
                cursor.close()
        return self._with_connection(_execute_query)
    
    def insert_rows(self, table: str, rows: List[List[Any]], column_names: List[str]) -> None:
        """Insert rows into a table."""
        if not rows:
            return
        
        def _execute_insert(conn):
            cursor = conn.cursor()
            try:
                # Build INSERT statement
                columns_str = ', '.join([f"`{col}`" for col in column_names])
                placeholders = ', '.join(['%s'] * len(column_names))
                sql = f"INSERT INTO `{table}` ({columns_str}) VALUES ({placeholders})"
                
                # Batch insert
                cursor.executemany(sql, rows)
            finally:
                cursor.close()
        
        self._with_connection(_execute_insert)
    
    # ============ Initialization methods ============
    
    def init_db(self):
        """Initialize database tables - only CREATE TABLE IF NOT EXISTS, no migration logic"""
        logger.info("[Database] Initializing MySQL tables...")
        
        # Use unified table initialization module
        table_names = {
            'providers_table': self.providers_table,
            'models_table': self.models_table,
            'portfolios_table': self.portfolios_table,
            'trades_table': self.trades_table,
            'conversations_table': self.conversations_table,
            'account_values_table': self.account_values_table,
            'account_value_historys_table': self.account_value_historys_table,
            'settings_table': self.settings_table,
            'model_prompts_table': self.model_prompts_table,
            'model_futures_table': self.model_futures_table,
            'futures_table': self.futures_table,
            'account_asset_table': self.account_asset_table,
            'asset_table': self.asset_table,
            'binance_trade_logs_table': self.binance_trade_logs_table,
            'strategy_table': self.strategys_table,
            'model_strategy_table': self.model_strategy_table,
            'strategy_decisions_table': self.strategy_decisions_table,
        }
        init_database_tables(self.command, table_names)
        
        # Insert default settings if no settings exist
        self._init_default_settings()
        
        logger.info("[Database] MySQL tables initialized")
    
    # Table initialization methods have been moved to common/database/database_init.py
    
    # Table initialization methods have been moved to common/database/database_init.py
    
    def _init_default_settings(self):
        """Initialize default settings if none exist"""
        try:
            # Check if settings records exist
            result = self.query(f"SELECT COUNT(*) as cnt FROM `{self.settings_table}`")
            if result and result[0][0] == 0:
                # Use UTC+8 timezone (Beijing time), convert to naive datetime for storage
                beijing_tz = timezone(timedelta(hours=8))
                current_time = datetime.now(beijing_tz).replace(tzinfo=None)
                
                # Insert default settings
                settings_id = str(uuid.uuid4())
                self.insert_rows(
                    self.settings_table,
                    [[settings_id, 5, 5, 0.002, 0, 5, None, None, 0.0, 8192, 0.9, 50, current_time, current_time]],
                    ["id", "buy_frequency_minutes", "sell_frequency_minutes", "trading_fee_rate", "show_system_prompt", "conversation_limit", "strategy_provider", "strategy_model", "strategy_temperature", "strategy_max_tokens", "strategy_top_p", "strategy_top_k", "created_at", "updated_at"]
                )
                logger.info("[Database] Default settings initialized")
        except Exception as e:
            logger.warning(f"[Database] Failed to initialize default settings: {e}")
    
    def _generate_id(self) -> str:
        """Generate a unique ID (UUID)"""
        return str(uuid.uuid4())


