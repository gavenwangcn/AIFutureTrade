"""
Database management module - ClickHouse implementation
基础配置数据库操作模块，使用 ClickHouse 作为存储引擎
"""
import json
import logging
import uuid
import common.config as app_config
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any, Callable, Tuple
from common.database_clickhouse import ClickHouseConnectionPool

logger = logging.getLogger(__name__)


class Database:
    """Database management class using ClickHouse as storage backend.
    
    注意：此模块已从 SQLite 迁移到 ClickHouse，保持与原 SQLite 版本的方法签名和返回值格式兼容。
    """
    
    def __init__(self, db_path: str = 'trading_bot.db'):
        """Initialize database connection.
        
        Args:
            db_path: 保留此参数以保持兼容性，但不再使用（ClickHouse 使用配置中的连接信息）
        """
        # 使用 ClickHouse 连接池，参考 database_clickhouse.py 的模式
        self._pool = ClickHouseConnectionPool(
            host=app_config.CLICKHOUSE_HOST,
            port=app_config.CLICKHOUSE_PORT,
            username=app_config.CLICKHOUSE_USER,
            password=app_config.CLICKHOUSE_PASSWORD,
            database=app_config.CLICKHOUSE_DATABASE,
            secure=app_config.CLICKHOUSE_SECURE,
            min_connections=5,
            max_connections=50,
            connection_timeout=30
        )
        
        # 表名定义
        self.providers_table = "providers"
        self.models_table = "models"
        self.portfolios_table = "portfolios"
        self.trades_table = "trades"
        self.conversations_table = "conversations"
        self.account_values_table = "account_values"
        self.settings_table = "settings"
        self.model_prompts_table = "model_prompts"
        self.model_futures_table = "model_futures"
        self.futures_table = "futures"
        self.futures_leaderboard_table = "futures_leaderboard"
    
    def _with_connection(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function with a ClickHouse connection from the pool."""
        client = self._pool.acquire()
        if not client:
            raise Exception("Failed to acquire ClickHouse connection")
        
        try:
            return func(client, *args, **kwargs)
        finally:
            self._pool.release(client)
    
    def command(self, sql: str) -> None:
        """Execute a raw SQL command."""
        def _execute_command(client):
            client.command(sql)
        self._with_connection(_execute_command)
    
    def query(self, sql: str) -> List[Tuple]:
        """Execute a query and return results.
        
        注意：ClickHouse 的参数化查询支持有限，这里直接执行 SQL 字符串。
        所有参数都应该在调用前通过字符串格式化安全地嵌入到 SQL 中。
        """
        def _execute_query(client):
            result = client.query(sql)
            return result.result_rows
        return self._with_connection(_execute_query)
    
    def insert_rows(self, table: str, rows: List[List[Any]], column_names: List[str]) -> None:
        """Insert rows into a table."""
        if not rows:
            return
        
        def _execute_insert(client):
            client.insert(table, rows, column_names=column_names)
        
        self._with_connection(_execute_insert)
    
    # ==================================================================
    # 数据库初始化
    # ==================================================================
    
    def init_db(self):
        """Initialize database tables - only CREATE TABLE IF NOT EXISTS, no migration logic"""
        logger.info("[Database] Initializing ClickHouse tables...")
        
        # Providers table (API提供方)
        self._ensure_providers_table()
        
        # Models table
        self._ensure_models_table()
        
        # Portfolios table
        self._ensure_portfolios_table()
        
        # Trades table
        self._ensure_trades_table()
        
        # Conversations table
        self._ensure_conversations_table()
        
        # Account values history table
        self._ensure_account_values_table()
        
        # Settings table
        self._ensure_settings_table()
        
        # Model prompts table
        self._ensure_model_prompts_table()
        
        # Model-specific futures configuration table
        self._ensure_model_futures_table()
        
        # Futures table (USDS-M contract universe)
        self._ensure_futures_table()
        
        # Futures leaderboard table
        self._ensure_futures_leaderboard_table()
        
        # Insert default settings if no settings exist
        self._init_default_settings()
        
        logger.info("[Database] ClickHouse tables initialized")
    
    def _ensure_providers_table(self):
        """Create providers table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {self.providers_table} (
            id String,
            name String,
            api_url String,
            api_key String,
            models String,
            provider_type String DEFAULT 'openai',
            created_at DateTime DEFAULT now()
        )
        ENGINE = MergeTree
        ORDER BY (id, created_at)
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.providers_table} exists")
    
    def _ensure_models_table(self):
        """Create models table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {self.models_table} (
            id String,
            name String,
            provider_id String,
            model_name String,
            initial_capital Float64 DEFAULT 10000,
            leverage UInt8 DEFAULT 10,
            auto_trading_enabled UInt8 DEFAULT 1,
            created_at DateTime DEFAULT now()
        )
        ENGINE = MergeTree
        ORDER BY (id, created_at)
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.models_table} exists")
    
    def _ensure_portfolios_table(self):
        """Create portfolios table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {self.portfolios_table} (
            id String,
            model_id String,
            future String,
            quantity Float64,
            avg_price Float64,
            leverage UInt8 DEFAULT 1,
            side String DEFAULT 'long',
            updated_at DateTime DEFAULT now()
        )
        ENGINE = ReplacingMergeTree(updated_at)
        ORDER BY (model_id, future, side)
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.portfolios_table} exists")
    
    def _ensure_trades_table(self):
        """Create trades table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {self.trades_table} (
            id String,
            model_id String,
            future String,
            signal String,
            quantity Float64,
            price Float64,
            leverage UInt8 DEFAULT 1,
            side String DEFAULT 'long',
            pnl Float64 DEFAULT 0,
            fee Float64 DEFAULT 0,
            timestamp DateTime DEFAULT now()
        )
        ENGINE = MergeTree
        ORDER BY (model_id, timestamp, future)
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.trades_table} exists")
    
    def _ensure_conversations_table(self):
        """Create conversations table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {self.conversations_table} (
            id String,
            model_id String,
            user_prompt String,
            ai_response String,
            cot_trace String,
            timestamp DateTime DEFAULT now()
        )
        ENGINE = MergeTree
        ORDER BY (model_id, timestamp)
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.conversations_table} exists")
    
    def _ensure_account_values_table(self):
        """Create account_values table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {self.account_values_table} (
            id String,
            model_id String,
            total_value Float64,
            cash Float64,
            positions_value Float64,
            timestamp DateTime DEFAULT now()
        )
        ENGINE = MergeTree
        ORDER BY (model_id, timestamp)
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.account_values_table} exists")
    
    def _ensure_settings_table(self):
        """Create settings table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {self.settings_table} (
            id String,
            trading_frequency_minutes UInt32 DEFAULT 60,
            trading_fee_rate Float64 DEFAULT 0.001,
            show_system_prompt UInt8 DEFAULT 0,
            created_at DateTime DEFAULT now(),
            updated_at DateTime DEFAULT now()
        )
        ENGINE = ReplacingMergeTree(updated_at)
        ORDER BY id
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.settings_table} exists")
    
    def _ensure_model_prompts_table(self):
        """Create model_prompts table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {self.model_prompts_table} (
            id String,
            model_id String,
            buy_prompt String,
            sell_prompt String,
            updated_at DateTime DEFAULT now()
        )
        ENGINE = ReplacingMergeTree(updated_at)
        ORDER BY model_id
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.model_prompts_table} exists")
    
    def _ensure_model_futures_table(self):
        """Create model_futures table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {self.model_futures_table} (
            id String,
            model_id String,
            symbol String,
            contract_symbol String,
            name String,
            exchange String DEFAULT 'BINANCE_FUTURES',
            link String,
            sort_order Int32 DEFAULT 0
        )
        ENGINE = ReplacingMergeTree(sort_order)
        ORDER BY (model_id, symbol)
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.model_futures_table} exists")
    
    def _ensure_futures_table(self):
        """Create futures table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {self.futures_table} (
            id String,
            symbol String,
            contract_symbol String,
            name String,
            exchange String DEFAULT 'BINANCE_FUTURES',
            link String,
            sort_order Int32 DEFAULT 0,
            created_at DateTime DEFAULT now()
        )
        ENGINE = ReplacingMergeTree(created_at)
        ORDER BY symbol
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.futures_table} exists")
    
    def _ensure_futures_leaderboard_table(self):
        """Create futures_leaderboard table if not exists"""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {self.futures_leaderboard_table} (
            id String,
            symbol String,
            contract_symbol String,
            name String,
            exchange String DEFAULT 'BINANCE_FUTURES',
            side String,
            rank UInt8,
            price Float64,
            change_percent Float64,
            quote_volume Float64,
            timeframes String,
            updated_at DateTime DEFAULT now()
        )
        ENGINE = ReplacingMergeTree(updated_at)
        ORDER BY (symbol, side)
        """
        self.command(ddl)
        logger.debug(f"[Database] Ensured table {self.futures_leaderboard_table} exists")
    
    def _init_default_settings(self):
        """Initialize default settings if none exist"""
        try:
            # 检查是否有设置记录
            result = self.query(f"SELECT count() as cnt FROM {self.settings_table}")
            if result and result[0][0] == 0:
                # 插入默认设置
                settings_id = str(uuid.uuid4())
                self.insert_rows(
                    self.settings_table,
                    [[settings_id, 60, 0.001, 0, datetime.now(timezone.utc), datetime.now(timezone.utc)]],
                    ["id", "trading_frequency_minutes", "trading_fee_rate", "show_system_prompt", "created_at", "updated_at"]
                )
                logger.info("[Database] Default settings initialized")
        except Exception as e:
            logger.warning(f"[Database] Failed to initialize default settings: {e}")
    
    def _generate_id(self) -> str:
        """Generate a unique ID (UUID)"""
        return str(uuid.uuid4())
    
    def _uuid_to_int(self, uuid_str: str) -> int:
        """Convert UUID string to int ID for compatibility"""
        # 使用 UUID 的前 8 个字符的 hash 来生成稳定的 int ID
        return abs(hash(uuid_str)) % (10 ** 9)
    
    def _int_to_uuid(self, int_id: int, table: str) -> Optional[str]:
        """Find UUID string by int ID (for compatibility)"""
        try:
            rows = self.query(f"SELECT id FROM {table}")
            for row in rows:
                uuid_str = row[0]
                if self._uuid_to_int(uuid_str) == int_id:
                    return uuid_str
            return None
        except Exception as e:
            logger.error(f"[Database] Failed to find UUID for int ID {int_id} in table {table}: {e}")
            return None
    
    def _row_to_dict(self, row: Tuple, columns: List[str]) -> Dict:
        """Convert a row tuple to a dictionary"""
        return dict(zip(columns, row))
    
    def _rows_to_dicts(self, rows: List[Tuple], columns: List[str]) -> List[Dict]:
        """Convert rows to list of dictionaries"""
        return [self._row_to_dict(row, columns) for row in rows]
    
    # ==================================================================
    # Provider Management
    # ==================================================================
    
    def add_provider(self, name: str, api_url: str, api_key: str, models: str = '', provider_type: str = 'openai') -> int:
        """Add new API provider
        
        注意：返回类型保持为 int 以兼容原接口，但实际存储的是 String (UUID)
        """
        provider_id = self._generate_id()
        try:
            self.insert_rows(
                self.providers_table,
                [[provider_id, name, api_url, api_key, models or '', provider_type.lower(), datetime.now(timezone.utc)]],
                ["id", "name", "api_url", "api_key", "models", "provider_type", "created_at"]
            )
            # 为了兼容性，返回一个数字 ID（使用 UUID 的 hash）
            return self._uuid_to_int(provider_id)
        except Exception as e:
            logger.error(f"[Database] Failed to add provider: {e}")
            raise
    
    def get_provider(self, provider_id: int) -> Optional[Dict]:
        """Get provider information
        
        注意：provider_id 参数类型为 int（兼容性），但实际查询时需要使用 String
        这里需要先查找匹配的 provider
        """
        try:
            # 由于原接口使用 int ID，我们需要查找所有 providers 并匹配
            # 这是一个兼容性处理，实际应该使用 UUID
            rows = self.query(f"SELECT * FROM {self.providers_table} ORDER BY created_at DESC")
            columns = ["id", "name", "api_url", "api_key", "models", "provider_type", "created_at"]
            
            for row in rows:
                row_dict = self._row_to_dict(row, columns)
                # 检查 hash 是否匹配
                if self._uuid_to_int(row_dict['id']) == provider_id:
                    # 转换 ID 为 int 以保持兼容性
                    row_dict['id'] = provider_id
                    return row_dict
            return None
        except Exception as e:
            logger.error(f"[Database] Failed to get provider {provider_id}: {e}")
            return None
    
    def get_all_providers(self) -> List[Dict]:
        """Get all API providers"""
        try:
            rows = self.query(f"SELECT * FROM {self.providers_table} ORDER BY created_at DESC")
            columns = ["id", "name", "api_url", "api_key", "models", "provider_type", "created_at"]
            results = self._rows_to_dicts(rows, columns)
            # 转换 ID 为 int 以保持兼容性
            for result in results:
                result['id'] = self._uuid_to_int(result['id'])
            return results
        except Exception as e:
            logger.error(f"[Database] Failed to get all providers: {e}")
            return []
    
    def update_provider(self, provider_id: int, name: str, api_url: str, api_key: str, models: str, provider_type: str = 'openai'):
        """Update provider information"""
        try:
            # 查找匹配的 provider
            provider = self.get_provider(provider_id)
            if not provider:
                logger.warning(f"[Database] Provider {provider_id} not found for update")
                return
            
            actual_id = provider['id']
            # ClickHouse 使用 DELETE + INSERT 来实现 UPDATE
            self.command(f"ALTER TABLE {self.providers_table} DELETE WHERE id = '{actual_id}'")
            self.insert_rows(
                self.providers_table,
                [[actual_id, name, api_url, api_key, models or '', provider_type.lower(), provider.get('created_at', datetime.now(timezone.utc))]],
                ["id", "name", "api_url", "api_key", "models", "provider_type", "created_at"]
            )
        except Exception as e:
            logger.error(f"[Database] Failed to update provider {provider_id}: {e}")
            raise
    
    def delete_provider(self, provider_id: int):
        """Delete provider"""
        try:
            provider = self.get_provider(provider_id)
            if not provider:
                logger.warning(f"[Database] Provider {provider_id} not found for deletion")
                return
            
            actual_id = provider['id']
            self.command(f"ALTER TABLE {self.providers_table} DELETE WHERE id = '{actual_id}'")
        except Exception as e:
            logger.error(f"[Database] Failed to delete provider {provider_id}: {e}")
            raise
    
    # ==================================================================
    # Model Management
    # ==================================================================
    
    def _get_model_id_mapping(self) -> Dict[int, str]:
        """Get mapping from int ID to UUID string ID for models"""
        try:
            rows = self.query(f"SELECT id FROM {self.models_table}")
            mapping = {}
            for row in rows:
                uuid_str = row[0]
                int_id = self._uuid_to_int(uuid_str)
                mapping[int_id] = uuid_str
            return mapping
        except Exception as e:
            logger.error(f"[Database] Failed to get model ID mapping: {e}")
            return {}
    
    def _get_provider_id_mapping(self) -> Dict[int, str]:
        """Get mapping from int ID to UUID string ID for providers"""
        try:
            rows = self.query(f"SELECT id FROM {self.providers_table}")
            mapping = {}
            for row in rows:
                uuid_str = row[0]
                int_id = self._uuid_to_int(uuid_str)
                mapping[int_id] = uuid_str
            return mapping
        except Exception as e:
            logger.error(f"[Database] Failed to get provider ID mapping: {e}")
            return {}
    
    def add_model(self, name: str, provider_id: int, model_name: str,
                 initial_capital: float = 10000, leverage: int = 10) -> int:
        """Add new trading model"""
        model_id = self._generate_id()
        provider_mapping = self._get_provider_id_mapping()
        provider_uuid = provider_mapping.get(provider_id, '')
        
        try:
            self.insert_rows(
                self.models_table,
                [[model_id, name, provider_uuid, model_name, initial_capital, leverage, 1, datetime.now(timezone.utc)]],
                ["id", "name", "provider_id", "model_name", "initial_capital", "leverage", "auto_trading_enabled", "created_at"]
            )
            return self._uuid_to_int(model_id)
        except Exception as e:
            logger.error(f"[Database] Failed to add model: {e}")
            raise
    
    def get_model(self, model_id: int) -> Optional[Dict]:
        """Get model information"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return None
            
            # 查询 model 和关联的 provider
            rows = self.query(f"""
                SELECT m.id, m.name, m.provider_id, m.model_name, m.initial_capital, 
                       m.leverage, m.auto_trading_enabled, m.created_at,
                       p.api_key, p.api_url, p.provider_type
                FROM {self.models_table} m
                LEFT JOIN {self.providers_table} p ON m.provider_id = p.id
                WHERE m.id = '{model_uuid}'
            """)
            
            if not rows:
                return None
            
            columns = ["id", "name", "provider_id", "model_name", "initial_capital", 
                      "leverage", "auto_trading_enabled", "created_at",
                      "api_key", "api_url", "provider_type"]
            result = self._row_to_dict(rows[0], columns)
            # 转换 ID 为 int 以保持兼容性
            result['id'] = model_id
            if result.get('provider_id'):
                provider_mapping = self._get_provider_id_mapping()
                for pid, puuid in provider_mapping.items():
                    if puuid == result['provider_id']:
                        result['provider_id'] = pid
                        break
            return result
        except Exception as e:
            logger.error(f"[Database] Failed to get model {model_id}: {e}")
            return None
    
    def get_all_models(self) -> List[Dict]:
        """Get all trading models"""
        try:
            rows = self.query(f"""
                SELECT m.id, m.name, m.provider_id, m.model_name, m.initial_capital,
                       m.leverage, m.auto_trading_enabled, m.created_at,
                       p.name as provider_name
                FROM {self.models_table} m
                LEFT JOIN {self.providers_table} p ON m.provider_id = p.id
                ORDER BY m.created_at DESC
            """)
            columns = ["id", "name", "provider_id", "model_name", "initial_capital",
                      "leverage", "auto_trading_enabled", "created_at", "provider_name"]
            results = self._rows_to_dicts(rows, columns)
            
            # 转换 ID 为 int 以保持兼容性
            provider_mapping = self._get_provider_id_mapping()
            for result in results:
                result['id'] = self._uuid_to_int(result['id'])
                if result.get('provider_id'):
                    for pid, puuid in provider_mapping.items():
                        if puuid == result['provider_id']:
                            result['provider_id'] = pid
                            break
            return results
        except Exception as e:
            logger.error(f"[Database] Failed to get all models: {e}")
            return []
    
    def delete_model(self, model_id: int):
        """Delete model and related data"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                logger.warning(f"[Database] Model {model_id} not found for deletion")
                return
            
            # 删除相关数据
            self.command(f"ALTER TABLE {self.portfolios_table} DELETE WHERE model_id = '{model_uuid}'")
            self.command(f"ALTER TABLE {self.trades_table} DELETE WHERE model_id = '{model_uuid}'")
            self.command(f"ALTER TABLE {self.conversations_table} DELETE WHERE model_id = '{model_uuid}'")
            self.command(f"ALTER TABLE {self.account_values_table} DELETE WHERE model_id = '{model_uuid}'")
            self.command(f"ALTER TABLE {self.model_futures_table} DELETE WHERE model_id = '{model_uuid}'")
            self.command(f"ALTER TABLE {self.models_table} DELETE WHERE id = '{model_uuid}'")
        except Exception as e:
            logger.error(f"[Database] Failed to delete model {model_id}: {e}")
            raise
    
    def set_model_auto_trading(self, model_id: int, enabled: bool) -> bool:
        """Enable or disable auto trading for a model"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return False
            
            # 获取当前 model 数据
            model = self.get_model(model_id)
            if not model:
                return False
            
            # 获取 provider UUID
            provider_id_int = model.get('provider_id')
            provider_uuid = ''
            if provider_id_int:
                provider_mapping = self._get_provider_id_mapping()
                provider_uuid = provider_mapping.get(provider_id_int, '')
            
            # 使用 DELETE + INSERT 实现 UPDATE
            self.command(f"ALTER TABLE {self.models_table} DELETE WHERE id = '{model_uuid}'")
            self.insert_rows(
                self.models_table,
                [[model_uuid, model['name'], provider_uuid, model['model_name'],
                  model['initial_capital'], model['leverage'], 1 if enabled else 0, model.get('created_at', datetime.now(timezone.utc))]],
                ["id", "name", "provider_id", "model_name", "initial_capital", "leverage", "auto_trading_enabled", "created_at"]
            )
            return True
        except Exception as e:
            logger.error(f"[Database] Failed to update auto trading flag for model {model_id}: {e}")
            return False
    
    def is_model_auto_trading_enabled(self, model_id: int) -> bool:
        """Check auto trading flag for a model"""
        try:
            model = self.get_model(model_id)
            if not model:
                return False
            return bool(model.get('auto_trading_enabled', 0))
        except Exception as e:
            logger.error(f"[Database] Failed to check auto trading flag for model {model_id}: {e}")
            return False
    
    def set_model_leverage(self, model_id: int, leverage: int) -> bool:
        """Update model leverage"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return False
            
            model = self.get_model(model_id)
            if not model:
                return False
            
            # 获取 provider UUID
            provider_id_int = model.get('provider_id')
            provider_uuid = ''
            if provider_id_int:
                provider_mapping = self._get_provider_id_mapping()
                provider_uuid = provider_mapping.get(provider_id_int, '')
            
            # 使用 DELETE + INSERT 实现 UPDATE
            self.command(f"ALTER TABLE {self.models_table} DELETE WHERE id = '{model_uuid}'")
            self.insert_rows(
                self.models_table,
                [[model_uuid, model['name'], provider_uuid, model['model_name'],
                  model['initial_capital'], leverage, model.get('auto_trading_enabled', 1), model.get('created_at', datetime.now(timezone.utc))]],
                ["id", "name", "provider_id", "model_name", "initial_capital", "leverage", "auto_trading_enabled", "created_at"]
            )
            return True
        except Exception as e:
            logger.error(f"[Database] Failed to update leverage for model {model_id}: {e}")
            return False
    
    # ==================================================================
    # Portfolio Management
    # ==================================================================
    
    def update_position(self, model_id: int, future: str, quantity: float,
                       avg_price: float, leverage: int = 1, side: str = 'long'):
        """Update position"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                logger.warning(f"[Database] Model {model_id} not found for position update")
                return
            
            # 使用 ReplacingMergeTree，直接插入即可（会自动去重）
            position_id = self._generate_id()
            self.insert_rows(
                self.portfolios_table,
                [[position_id, model_uuid, future.upper(), quantity, avg_price, leverage, side, datetime.now(timezone.utc)]],
                ["id", "model_id", "future", "quantity", "avg_price", "leverage", "side", "updated_at"]
            )
        except Exception as e:
            logger.error(f"[Database] Failed to update position: {e}")
            raise
    
    def get_portfolio(self, model_id: int, current_prices: Dict = None) -> Dict:
        """Get portfolio with positions and P&L"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                raise ValueError(f"Model {model_id} not found")
            
            # 获取持仓（使用 FINAL 确保 ReplacingMergeTree 去重）
            rows = self.query(f"""
                SELECT * FROM {self.portfolios_table} FINAL
                WHERE model_id = '{model_uuid}' AND quantity > 0
            """)
            columns = ["id", "model_id", "future", "quantity", "avg_price", "leverage", "side", "updated_at"]
            positions = self._rows_to_dicts(rows, columns)
            
            # 获取初始资金
            model = self.get_model(model_id)
            if not model:
                raise ValueError(f"Model {model_id} not found")
            initial_capital = model['initial_capital']
            
            # 计算已实现盈亏
            pnl_rows = self.query(f"""
                SELECT COALESCE(SUM(pnl), 0) as total_pnl 
                FROM {self.trades_table}
                WHERE model_id = '{model_uuid}'
            """)
            realized_pnl = float(pnl_rows[0][0]) if pnl_rows and pnl_rows[0][0] is not None else 0.0
            
            # 计算已用保证金
            margin_used = sum([p['quantity'] * p['avg_price'] / p['leverage'] for p in positions])
            
            # 计算未实现盈亏
            unrealized_pnl = 0
            if current_prices:
                for pos in positions:
                    symbol = pos['future']
                    if symbol in current_prices:
                        current_price = current_prices[symbol]
                        entry_price = pos['avg_price']
                        qty = pos['quantity']
                        pos['current_price'] = current_price
                        if pos['side'] == 'long':
                            pos_pnl = (current_price - entry_price) * qty
                        else:
                            pos_pnl = (entry_price - current_price) * qty
                        pos['pnl'] = pos_pnl
                        unrealized_pnl += pos_pnl
                    else:
                        pos['current_price'] = None
                        pos['pnl'] = 0
            else:
                for pos in positions:
                    pos['current_price'] = None
                    pos['pnl'] = 0
            
            cash = initial_capital + realized_pnl - margin_used
            positions_value = sum([p['quantity'] * p['avg_price'] for p in positions])
            total_value = initial_capital + realized_pnl + unrealized_pnl
            
            return {
                'model_id': model_id,
                'initial_capital': initial_capital,
                'cash': cash,
                'positions': positions,
                'positions_value': positions_value,
                'margin_used': margin_used,
                'total_value': total_value,
                'realized_pnl': realized_pnl,
                'unrealized_pnl': unrealized_pnl
            }
        except Exception as e:
            logger.error(f"[Database] Failed to get portfolio for model {model_id}: {e}")
            raise
    
    def close_position(self, model_id: int, future: str, side: str = 'long'):
        """Close position and clean up futures universe if unused"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return
            
            normalized_symbol = future.upper()
            self.command(f"ALTER TABLE {self.portfolios_table} DELETE WHERE model_id = '{model_uuid}' AND future = '{normalized_symbol}' AND side = '{side}'")
            
            # 检查是否还有其他持仓
            remaining_rows = self.query(f"""
                SELECT count() as cnt FROM {self.portfolios_table} FINAL
                WHERE future = '{normalized_symbol}' AND quantity > 0
            """)
            if remaining_rows and remaining_rows[0][0] == 0:
                # 删除 futures 表中的记录
                self.command(f"ALTER TABLE {self.futures_table} DELETE WHERE symbol = '{normalized_symbol}'")
        except Exception as e:
            logger.error(f"[Database] Failed to close position: {e}")
            raise
    
    # ==================================================================
    # Trade Records
    # ==================================================================
    
    def add_trade(self, model_id: int, future: str, signal: str, quantity: float,
              price: float, leverage: int = 1, side: str = 'long', pnl: float = 0, fee: float = 0):
        """Add trade record with fee"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                logger.warning(f"[Database] Model {model_id} not found for trade record")
                return
            
            trade_id = self._generate_id()
            self.insert_rows(
                self.trades_table,
                [[trade_id, model_uuid, future.upper(), signal, quantity, price, leverage, side, pnl, fee, datetime.now(timezone.utc)]],
                ["id", "model_id", "future", "signal", "quantity", "price", "leverage", "side", "pnl", "fee", "timestamp"]
            )
        except Exception as e:
            logger.error(f"[Database] Failed to add trade: {e}")
            raise
    
    def get_trades(self, model_id: int, limit: int = 50) -> List[Dict]:
        """Get trade history"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return []
            
            rows = self.query(f"""
                SELECT * FROM {self.trades_table}
                WHERE model_id = '{model_uuid}'
                ORDER BY timestamp DESC
                LIMIT {limit}
            """)
            columns = ["id", "model_id", "future", "signal", "quantity", "price", "leverage", "side", "pnl", "fee", "timestamp"]
            return self._rows_to_dicts(rows, columns)
        except Exception as e:
            logger.error(f"[Database] Failed to get trades for model {model_id}: {e}")
            return []
    
    # ==================================================================
    # Conversation History
    # ==================================================================
    
    def add_conversation(self, model_id: int, user_prompt: str,
                        ai_response: str, cot_trace: str = ''):
        """Add conversation record"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                logger.warning(f"[Database] Model {model_id} not found for conversation record")
                return
            
            conv_id = self._generate_id()
            self.insert_rows(
                self.conversations_table,
                [[conv_id, model_uuid, user_prompt, ai_response, cot_trace or '', datetime.now(timezone.utc)]],
                ["id", "model_id", "user_prompt", "ai_response", "cot_trace", "timestamp"]
            )
        except Exception as e:
            logger.error(f"[Database] Failed to add conversation: {e}")
            raise
    
    def get_conversations(self, model_id: int, limit: int = 20) -> List[Dict]:
        """Get conversation history"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return []
            
            rows = self.query(f"""
                SELECT * FROM {self.conversations_table}
                WHERE model_id = '{model_uuid}'
                ORDER BY timestamp DESC
                LIMIT {limit}
            """)
            columns = ["id", "model_id", "user_prompt", "ai_response", "cot_trace", "timestamp"]
            return self._rows_to_dicts(rows, columns)
        except Exception as e:
            logger.error(f"[Database] Failed to get conversations for model {model_id}: {e}")
            return []
    
    # ==================================================================
    # Account Value History
    # ==================================================================
    
    def record_account_value(self, model_id: int, total_value: float,
                            cash: float, positions_value: float):
        """Record account value snapshot"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                logger.warning(f"[Database] Model {model_id} not found for account value record")
                return
            
            av_id = self._generate_id()
            self.insert_rows(
                self.account_values_table,
                [[av_id, model_uuid, total_value, cash, positions_value, datetime.now(timezone.utc)]],
                ["id", "model_id", "total_value", "cash", "positions_value", "timestamp"]
            )
        except Exception as e:
            logger.error(f"[Database] Failed to record account value: {e}")
            raise
    
    def get_account_value_history(self, model_id: int, limit: int = 100) -> List[Dict]:
        """Get account value history"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return []
            
            rows = self.query(f"""
                SELECT * FROM {self.account_values_table}
                WHERE model_id = '{model_uuid}'
                ORDER BY timestamp DESC
                LIMIT {limit}
            """)
            columns = ["id", "model_id", "total_value", "cash", "positions_value", "timestamp"]
            return self._rows_to_dicts(rows, columns)
        except Exception as e:
            logger.error(f"[Database] Failed to get account value history for model {model_id}: {e}")
            return []
    
    def get_aggregated_account_value_history(self, limit: int = 100) -> List[Dict]:
        """Get aggregated account value history across all models"""
        try:
            # ClickHouse 的日期函数略有不同
            rows = self.query(f"""
                SELECT 
                    timestamp,
                    SUM(total_value) as total_value,
                    SUM(cash) as cash,
                    SUM(positions_value) as positions_value,
                    COUNT(DISTINCT model_id) as model_count
                FROM (
                    SELECT 
                        timestamp,
                        total_value,
                        cash,
                        positions_value,
                        model_id,
                        ROW_NUMBER() OVER (PARTITION BY model_id, toDate(timestamp) ORDER BY timestamp DESC) as rn
                    FROM {self.account_values_table}
                ) grouped
                WHERE rn <= 10
                GROUP BY toDate(timestamp), toHour(timestamp), timestamp
                ORDER BY timestamp DESC
                LIMIT {limit}
            """)
            columns = ["timestamp", "total_value", "cash", "positions_value", "model_count"]
            return self._rows_to_dicts(rows, columns)
        except Exception as e:
            logger.error(f"[Database] Failed to get aggregated account value history: {e}")
            return []
    
    def get_multi_model_chart_data(self, limit: int = 100) -> List[Dict]:
        """Get chart data for all models to display in multi-line chart"""
        try:
            # 获取所有 models
            models = self.get_all_models()
            chart_data = []
            
            for model in models:
                model_id = model['id']
                model_name = model['name']
                history = self.get_account_value_history(model_id, limit)
                
                if history:
                    model_data = {
                        'model_id': model_id,
                        'model_name': model_name,
                        'data': [
                            {
                                'timestamp': row['timestamp'],
                                'value': row['total_value']
                            } for row in history
                        ]
                    }
                    chart_data.append(model_data)
            
            return chart_data
        except Exception as e:
            logger.error(f"[Database] Failed to get multi-model chart data: {e}")
            return []
    
    # ==================================================================
    # Prompt Configuration
    # ==================================================================
    
    def get_model_prompt(self, model_id: int) -> Optional[Dict]:
        """Get model prompt configuration"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return None
            
            rows = self.query(f"""
                SELECT * FROM {self.model_prompts_table} FINAL
                WHERE model_id = '{model_uuid}'
            """)
            if not rows:
                return None
            
            columns = ["id", "model_id", "buy_prompt", "sell_prompt", "updated_at"]
            result = self._row_to_dict(rows[0], columns)
            result['model_id'] = model_id  # 转换为 int ID
            return result
        except Exception as e:
            logger.error(f"[Database] Failed to get model prompt for model {model_id}: {e}")
            return None
    
    def upsert_model_prompt(self, model_id: int, buy_prompt: Optional[str], sell_prompt: Optional[str]) -> bool:
        """Insert or update model prompt configuration"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return False
            
            if (not buy_prompt or not buy_prompt.strip()) and (not sell_prompt or not sell_prompt.strip()):
                # 删除记录
                self.command(f"ALTER TABLE {self.model_prompts_table} DELETE WHERE model_id = '{model_uuid}'")
                return True
            
            # 使用 ReplacingMergeTree，直接插入即可
            prompt_id = self._generate_id()
            self.insert_rows(
                self.model_prompts_table,
                [[prompt_id, model_uuid, buy_prompt or '', sell_prompt or '', datetime.now(timezone.utc)]],
                ["id", "model_id", "buy_prompt", "sell_prompt", "updated_at"]
            )
            return True
        except Exception as e:
            logger.error(f"[Database] Failed to upsert model prompt for model {model_id}: {e}")
            return False
    
    # ==================================================================
    # Futures Universe Management
    # ==================================================================
    
    def get_futures(self) -> List[Dict]:
        """Get all futures configurations"""
        try:
            rows = self.query(f"""
                SELECT * FROM {self.futures_table} FINAL
                ORDER BY sort_order DESC, created_at DESC, symbol ASC
            """)
            columns = ["id", "symbol", "contract_symbol", "name", "exchange", "link", "sort_order", "created_at"]
            results = self._rows_to_dicts(rows, columns)
            # 转换 ID 为 int 以保持与前端兼容性（类似 get_all_providers 和 get_all_models）
            for result in results:
                if result.get('id'):
                    result['id'] = self._uuid_to_int(result['id'])
            return results
        except Exception as e:
            logger.error(f"[Database] Failed to get futures: {e}")
            return []
    
    def add_future(self, symbol: str, contract_symbol: str, name: str,
                   exchange: str = 'BINANCE_FUTURES', link: Optional[str] = None, sort_order: int = 0) -> int:
        """Add new future configuration"""
        future_id = self._generate_id()
        try:
            self.insert_rows(
                self.futures_table,
                [[future_id, symbol.upper(), contract_symbol.upper(), name, exchange.upper(), (link or '').strip() or '', sort_order, datetime.now(timezone.utc)]],
                ["id", "symbol", "contract_symbol", "name", "exchange", "link", "sort_order", "created_at"]
            )
            return self._uuid_to_int(future_id)
        except Exception as e:
            logger.error(f"[Database] Failed to add future: {e}")
            raise
    
    def upsert_future(self, symbol: str, contract_symbol: str, name: str,
                     exchange: str = 'BINANCE_FUTURES', link: Optional[str] = None, sort_order: int = 0):
        """Insert or update a futures configuration identified by symbol"""
        try:
            # 使用 ReplacingMergeTree，直接插入即可
            future_id = self._generate_id()
            self.insert_rows(
                self.futures_table,
                [[future_id, symbol.upper(), contract_symbol.upper(), name, exchange.upper(), (link or '').strip() or '', sort_order, datetime.now(timezone.utc)]],
                ["id", "symbol", "contract_symbol", "name", "exchange", "link", "sort_order", "created_at"]
            )
        except Exception as e:
            logger.error(f"[Database] Failed to upsert future: {e}")
            raise
    
    def delete_future(self, future_id: int):
        """Delete future configuration"""
        try:
            # 查找匹配的 future
            futures = self.get_futures()
            for future in futures:
                if self._uuid_to_int(future['id']) == future_id:
                    actual_id = future['id']
                    self.command(f"ALTER TABLE {self.futures_table} DELETE WHERE id = '{actual_id}'")
                    return
            logger.warning(f"[Database] Future {future_id} not found for deletion")
        except Exception as e:
            logger.error(f"[Database] Failed to delete future {future_id}: {e}")
            raise
    
    def get_future_configs(self) -> List[Dict]:
        """Get future configurations"""
        try:
            rows = self.query(f"""
                SELECT symbol, contract_symbol, name, exchange, link, sort_order
                FROM {self.futures_table} FINAL
                ORDER BY sort_order DESC, symbol ASC
            """)
            columns = ["symbol", "contract_symbol", "name", "exchange", "link", "sort_order"]
            return self._rows_to_dicts(rows, columns)
        except Exception as e:
            logger.error(f"[Database] Failed to get future configs: {e}")
            return []
    
    def get_future_symbols(self) -> List[str]:
        """Get list of future symbols"""
        return [future['symbol'] for future in self.get_future_configs()]
    
    # ==================================================================
    # Model Futures Configuration
    # ==================================================================
    
    def add_model_future(self, model_id: int, symbol: str, contract_symbol: str,
                         name: str, exchange: str = 'BINANCE_FUTURES',
                         link: Optional[str] = None, sort_order: int = 0) -> int:
        """Add model-specific future configuration"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                raise ValueError(f"Model {model_id} not found")
            
            mf_id = self._generate_id()
            self.insert_rows(
                self.model_futures_table,
                [[mf_id, model_uuid, symbol.upper(), contract_symbol.upper(), name, exchange.upper(), (link or '').strip() or '', sort_order]],
                ["id", "model_id", "symbol", "contract_symbol", "name", "exchange", "link", "sort_order"]
            )
            return self._uuid_to_int(mf_id)
        except Exception as e:
            logger.error(f"[Database] Failed to add model future: {e}")
            raise
    
    def delete_model_future(self, model_id: int, symbol: str):
        """Delete model-specific future configuration"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return
            
            self.command(f"ALTER TABLE {self.model_futures_table} DELETE WHERE model_id = '{model_uuid}' AND symbol = '{symbol.upper()}'")
        except Exception as e:
            logger.error(f"[Database] Failed to delete model future: {e}")
            raise
    
    def get_model_futures(self, model_id: int) -> List[Dict]:
        """
        获取模型关联的期货合约配置，按symbol去重
        
        Args:
            model_id: 模型ID
            
        Returns:
            List[Dict]: 期货合约配置列表，每个字典包含id, model_id, symbol等字段
        """
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return []
            
            # 在查询中添加DISTINCT关键字，确保按symbol去重
            rows = self.query(f"""
                SELECT DISTINCT id, model_id, symbol, contract_symbol, name, exchange, link, sort_order
                FROM {self.model_futures_table} FINAL
                WHERE model_id = '{model_uuid}'
                ORDER BY sort_order DESC, symbol ASC
            """)
            columns = ["id", "model_id", "symbol", "contract_symbol", "name", "exchange", "link", "sort_order"]
            results = self._rows_to_dicts(rows, columns)
            # 转换 model_id 为 int
            for result in results:
                result['model_id'] = model_id
            return results
        except Exception as e:
            logger.error(f"[Database] Failed to get model futures for model {model_id}: {e}")
            return []
            
    def sync_model_futures_from_portfolio(self, model_id: int) -> bool:
        """
        从portfolios表同步去重的future信息到model_future表
        
        此方法会：
        1. 从portfolios表获取当前模型所有交易过的去重future合约
        2. 将这些合约信息同步到model_futures表
        3. 对于新增的合约，从全局futures表获取完整信息
        4. 对于不再在portfolios表中出现的合约，从model_futures表移除
        
        Args:
            model_id: 模型ID
        
        Returns:
            bool: 是否同步成功
        """
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                logger.error(f"[Database] Model {model_id} not found in mapping")
                return False
            
            # 1. 从portfolios表获取当前模型所有交易过的去重future合约
            rows = self.query(f"""
                SELECT DISTINCT future as symbol
                FROM {self.portfolios_table} FINAL
                WHERE model_id = '{model_uuid}'
                ORDER BY symbol ASC
            """)
            portfolio_symbols = [row[0] for row in rows]
            
            # 2. 获取当前model_futures表中的合约列表
            current_model_futures = self.get_model_futures(model_id)
            current_symbols = {future['symbol']: future for future in current_model_futures}
            
            # 3. 确定需要添加和删除的合约
            symbols_to_add = set(portfolio_symbols) - set(current_symbols.keys())
            symbols_to_delete = set(current_symbols.keys()) - set(portfolio_symbols)
            
            # 4. 添加新合约到model_futures表
            if symbols_to_add:
                # 从全局futures表获取合约的完整信息
                futures_info = self.query(f"""
                    SELECT symbol, contract_symbol, name, exchange, link
                    FROM {self.futures_table} FINAL
                    WHERE symbol IN {tuple(symbols_to_add)}
                """)
                
                # 如果某些合约在全局表中不存在，创建默认信息
                futures_dict = {row[0]: {
                    'symbol': row[0],
                    'contract_symbol': row[1] or row[0],
                    'name': row[2] or row[0],
                    'exchange': row[3] or 'BINANCE_FUTURES',
                    'link': row[4] or ''
                } for row in futures_info}
                
                # 为每个需要添加的合约生成记录
                for symbol in symbols_to_add:
                    # 如果全局表中没有该合约信息，创建默认信息
                    if symbol not in futures_dict:
                        futures_dict[symbol] = {
                            'symbol': symbol,
                            'contract_symbol': symbol,
                            'name': symbol,
                            'exchange': 'BINANCE_FUTURES',
                            'link': ''
                        }
                    
                    # 生成唯一ID
                    future_id = str(uuid.uuid4())
                    
                    # 插入到model_futures表
                    self.insert_rows(
                        self.model_futures_table,
                        [future_id, model_uuid, futures_dict[symbol]['symbol'], 
                         futures_dict[symbol]['contract_symbol'], futures_dict[symbol]['name'],
                         futures_dict[symbol]['exchange'], futures_dict[symbol]['link'], 0]
                    )
                    logger.debug(f"[Database] Added future {symbol} to model {model_id} in model_futures table")
            
            # 5. 从model_futures表删除不再交易的合约
            if symbols_to_delete:
                # 构建删除条件
                delete_conditions = " OR ".join([f"symbol = '{symbol}'" for symbol in symbols_to_delete])
                
                # 执行删除操作
                self.command(f"""
                    ALTER TABLE {self.model_futures_table}
                    DELETE WHERE model_id = '{model_uuid}' AND ({delete_conditions})
                """)
                logger.debug(f"[Database] Deleted {len(symbols_to_delete)} futures from model {model_id} in model_futures table")
            
            logger.info(f"[Database] Successfully synced model_futures for model {model_id}: "
                        f"added {len(symbols_to_add)}, deleted {len(symbols_to_delete)}")
            return True
            
        except Exception as e:
            logger.error(f"[Database] Failed to sync model_futures from portfolio for model {model_id}: {e}")
            import traceback
            logger.error(f"[Database] Error stack: {traceback.format_exc()}")
            return False
    
    def clear_model_futures(self, model_id: int):
        """Clear all model-specific future configurations"""
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return
            
            self.command(f"ALTER TABLE {self.model_futures_table} DELETE WHERE model_id = '{model_uuid}'")
        except Exception as e:
            logger.error(f"[Database] Failed to clear model futures for model {model_id}: {e}")
            raise
    
    # ==================================================================
    # Settings Management
    # ==================================================================
    
    def get_settings(self) -> Dict:
        """Get system settings"""
        try:
            rows = self.query(f"""
                SELECT trading_frequency_minutes, trading_fee_rate, show_system_prompt
                FROM {self.settings_table} FINAL
                ORDER BY updated_at DESC
                LIMIT 1
            """)
            
            if rows:
                columns = ["trading_frequency_minutes", "trading_fee_rate", "show_system_prompt"]
                result = self._row_to_dict(rows[0], columns)
                return {
                    'trading_frequency_minutes': int(result['trading_frequency_minutes']),
                    'trading_fee_rate': float(result['trading_fee_rate']),
                    'show_system_prompt': int(result.get('show_system_prompt', 0))
                }
            else:
                # 返回默认设置
                return {
                    'trading_frequency_minutes': 60,
                    'trading_fee_rate': 0.001,
                    'show_system_prompt': 1
                }
        except Exception as e:
            logger.error(f"[Database] Failed to get settings: {e}")
            return {
                'trading_frequency_minutes': 60,
                'trading_fee_rate': 0.001,
                'show_system_prompt': 1
            }
    
    def update_settings(self, trading_frequency_minutes: int, trading_fee_rate: float,
                        show_system_prompt: int) -> bool:
        """Update system settings"""
        try:
            # 使用 ReplacingMergeTree，直接插入新记录即可
            settings_id = self._generate_id()
            self.insert_rows(
                self.settings_table,
                [[settings_id, trading_frequency_minutes, trading_fee_rate, show_system_prompt, datetime.now(timezone.utc), datetime.now(timezone.utc)]],
                ["id", "trading_frequency_minutes", "trading_fee_rate", "show_system_prompt", "created_at", "updated_at"]
            )
            return True
        except Exception as e:
            logger.error(f"[Database] Failed to update settings: {e}")
            return False
    
    # ==================================================================
    # Leaderboard Management
    # ==================================================================
    
    def upsert_leaderboard_entries(self, entries: List[Dict]):
        """Insert or update leaderboard entries"""
        if not entries:
            return
        
        try:
            rows_to_insert = []
            for entry in entries:
                try:
                    entry_id = self._generate_id()
                    rows_to_insert.append([
                        entry_id,
                        entry['symbol'],
                        entry['contract_symbol'],
                        entry.get('name', ''),
                        entry.get('exchange', 'BINANCE_FUTURES'),
                        entry['side'],
                        entry['rank'],
                        entry.get('price', 0.0),
                        entry.get('change_percent', 0.0),
                        entry.get('quote_volume', 0.0),
                        json.dumps(entry.get('timeframes', {}), ensure_ascii=False),
                        datetime.now(timezone.utc)
                    ])
                except KeyError as exc:
                    logger.warning(f"[Database] 无法写入涨跌幅榜：缺少字段 {exc}")
            
            if rows_to_insert:
                self.insert_rows(
                    self.futures_leaderboard_table,
                    rows_to_insert,
                    ["id", "symbol", "contract_symbol", "name", "exchange", "side", "rank", "price", "change_percent", "quote_volume", "timeframes", "updated_at"]
                )
        except Exception as e:
            logger.error(f"[Database] Failed to upsert leaderboard entries: {e}")
            raise
    
    def get_futures_leaderboard(self, side: Optional[str] = None, limit: int = 10) -> Dict[str, List[Dict]]:
        """Get futures leaderboard data"""
        try:
            def fetch(side_key: str) -> List[Dict]:
                rows = self.query(f"""
                    SELECT symbol, contract_symbol, name, exchange, side,
                           rank, price, change_percent, quote_volume, timeframes, updated_at
                    FROM {self.futures_leaderboard_table} FINAL
                    WHERE side = '{side_key}'
                    ORDER BY rank ASC
                    LIMIT {limit}
                """)
                columns = ["symbol", "contract_symbol", "name", "exchange", "side", "rank", "price", "change_percent", "quote_volume", "timeframes", "updated_at"]
                results = self._rows_to_dicts(rows, columns)
                for result in results:
                    try:
                        result['timeframes'] = json.loads(result['timeframes']) if result['timeframes'] else {}
                    except json.JSONDecodeError:
                        result['timeframes'] = {}
                return results
            
            result: Dict[str, List[Dict]] = {'gainers': [], 'losers': []}
            side_map = {'gainer': 'gainers', 'loser': 'losers'}
            
            if side:
                normalized = side_map.get(side, side)
                result[normalized] = fetch(side)
            else:
                for raw_key, target_key in side_map.items():
                    result[target_key] = fetch(raw_key)
            
            return result
        except Exception as e:
            logger.error(f"[Database] Failed to get futures leaderboard: {e}")
            return {'gainers': [], 'losers': []}

