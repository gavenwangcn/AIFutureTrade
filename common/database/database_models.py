"""
模型数据表操作模块 - models 表

本模块提供模型数据的增删改查操作。

主要组件：
- ModelsDatabase: 模型数据操作类
"""

import logging
from typing import Dict, List, Optional, Any, Callable
import pymysql
from .database_basic import create_pooled_db
import common.config as app_config
from .database_init import MODELS_TABLE, PROVIDERS_TABLE

logger = logging.getLogger(__name__)


class ModelsDatabase:
    """
    模型数据操作类
    
    封装models表的所有数据库操作。
    """
    
    def __init__(self, pool=None):
        """
        初始化模型数据库操作类
        
        Args:
            pool: 可选的数据库连接池，如果不提供则创建新的连接池
        """
        if pool is None:
            self._pool = create_pooled_db(
                host=app_config.MYSQL_HOST,
                port=app_config.MYSQL_PORT,
                user=app_config.MYSQL_USER,
                password=app_config.MYSQL_PASSWORD,
                database=app_config.MYSQL_DATABASE,
                charset='utf8mb4',
                mincached=5,
                maxconnections=50,
                blocking=True
            )
        else:
            self._pool = pool
        
        self.models_table = MODELS_TABLE
        self.providers_table = PROVIDERS_TABLE
    
    def _with_connection(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function with a MySQL connection from the pool."""
        max_retries = 3
        retry_delay = 0.5
        
        for attempt in range(max_retries):
            conn = None
            connection_acquired = False
            try:
                conn = self._pool.connection()
                if not conn:
                    raise Exception("Failed to acquire MySQL connection")
                connection_acquired = True
                
                result = func(conn, *args, **kwargs)
                conn.commit()
                conn = None
                return result
                
            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                
                is_network_error = any(keyword in error_msg.lower() for keyword in [
                    'connection', 'broken', 'lost', 'timeout', 'reset', 'gone away',
                    'operationalerror', 'interfaceerror', 'packet sequence', 'internalerror',
                    'deadlock found', 'read of closed file'
                ]) or any(keyword in error_type.lower() for keyword in [
                    'connection', 'timeout', 'operationalerror', 'interfaceerror', 'internalerror',
                    'valueerror'
                ]) or (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213)
                
                # 如果已获取连接，需要处理连接（关闭）
                # 无论什么异常，都要确保连接被正确释放，防止连接泄露
                if connection_acquired and conn:
                    try:
                        # 回滚事务
                        try:
                            conn.rollback()
                        except Exception as rollback_error:
                            logger.debug(f"[Models] Error rolling back transaction: {rollback_error}")
                        
                        # 对于所有错误，关闭连接，DBUtils会自动处理损坏的连接
                        try:
                            conn.close()
                        except Exception as close_error:
                            logger.debug(f"[Models] Error closing connection: {close_error}")
                        finally:
                            # 确保连接引用被清除，即使关闭失败也要标记为已处理
                            conn = None
                    except Exception as close_error:
                        logger.error(f"[Models] Critical error closing failed connection: {close_error}")
                        # 即使发生异常，也要清除连接引用
                        conn = None
                
                if attempt < max_retries - 1:
                    if not is_network_error:
                        raise
                    
                    is_deadlock = (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213) or 'deadlock' in error_msg.lower()
                    if is_deadlock:
                        wait_time = 1.0 * (1.5 ** attempt)
                        logger.warning(
                            f"[Models] Deadlock error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    else:
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(
                            f"[Models] Network error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    
                    import time
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"[Models] Failed after {max_retries} attempts: "
                        f"{error_type}: {error_msg}"
                    )
                    raise
            finally:
                if connection_acquired and conn:
                    try:
                        logger.warning(
                            f"[Models] Connection not closed in finally block, closing it"
                        )
                        try:
                            conn.rollback()
                            conn.close()
                        except Exception:
                            pass
                    except Exception as final_error:
                        logger.debug(f"[Models] Error in finally block: {final_error}")
    
    def _uuid_to_int(self, uuid_str: str) -> int:
        """Convert UUID string to int ID for compatibility"""
        return abs(hash(uuid_str)) % (10 ** 9)
    
    def _row_to_dict(self, row: tuple, columns: list) -> Dict:
        """Convert a row tuple to a dictionary"""
        return dict(zip(columns, row))
    
    def _rows_to_dicts(self, rows: List[tuple], columns: list) -> List[Dict]:
        """Convert rows to list of dictionaries"""
        return [self._row_to_dict(row, columns) for row in rows]
    
    def query(self, sql: str, params: tuple = None, as_dict: bool = False):
        """Execute a query and return results."""
        def _execute_query(conn):
            from pymysql import cursors
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
                if as_dict:
                    return [dict(row) for row in rows] if rows else []
                if rows and isinstance(rows[0], dict):
                    return [tuple(row.values()) for row in rows]
                return rows
            finally:
                cursor.close()
        return self._with_connection(_execute_query)
    
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
            logger.error(f"[Models] Failed to get model ID mapping: {e}")
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
            logger.error(f"[Models] Failed to get provider ID mapping: {e}")
            return {}
    
    def get_model(self, model_id: int) -> Optional[Dict]:
        """
        Get model information
        
        Args:
            model_id: 模型ID（整数）
        
        Returns:
            模型信息字典，如果不存在则返回None
        """
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return None
            
            # 查询 model 和关联的 provider
            rows = self.query(f"""
                SELECT m.id, m.name, m.provider_id, m.model_name, m.initial_capital, 
                       m.leverage, m.auto_buy_enabled, m.auto_sell_enabled, m.max_positions, 
                       m.buy_batch_size, m.buy_batch_execution_interval, m.buy_batch_execution_group_size,
                       m.sell_batch_size, m.sell_batch_execution_interval, m.sell_batch_execution_group_size,
                       m.account_alias, m.is_virtual, m.symbol_source, m.created_at,
                       m.api_key, m.api_secret, p.api_url, p.provider_type
                FROM {self.models_table} m
                LEFT JOIN {self.providers_table} p ON m.provider_id = p.id
                WHERE m.id = '{model_uuid}'
            """)
            
            if not rows:
                return None
            
            columns = ["id", "name", "provider_id", "model_name", "initial_capital", 
                      "leverage", "auto_buy_enabled", "auto_sell_enabled", "max_positions",
                      "buy_batch_size", "buy_batch_execution_interval", "buy_batch_execution_group_size",
                      "sell_batch_size", "sell_batch_execution_interval", "sell_batch_execution_group_size",
                      "account_alias", "is_virtual", "symbol_source", "created_at",
                      "api_key", "api_secret", "api_url", "provider_type"]
            result = self._row_to_dict(rows[0], columns)
            # 转换 ID 为 int 以保持兼容性
            result['id'] = model_id
            if result.get('provider_id'):
                provider_mapping = self._get_provider_id_mapping()
                for pid, puuid in provider_mapping.items():
                    if puuid == result['provider_id']:
                        result['provider_id'] = pid
                        break
            # 【兼容性处理】确保symbol_source有默认值
            if not result.get('symbol_source'):
                result['symbol_source'] = 'leaderboard'
            # 【兼容性处理】确保is_virtual有默认值
            if result.get('is_virtual') is None:
                result['is_virtual'] = False
            else:
                result['is_virtual'] = bool(result.get('is_virtual', 0))
            # 【兼容性处理】确保auto_buy_enabled和auto_sell_enabled有默认值
            if result.get('auto_buy_enabled') is None:
                result['auto_buy_enabled'] = 1
            if result.get('auto_sell_enabled') is None:
                result['auto_sell_enabled'] = 1
            # 【兼容性处理】确保批次配置字段有默认值
            if result.get('buy_batch_size') is None:
                result['buy_batch_size'] = 1
            if result.get('buy_batch_execution_interval') is None:
                result['buy_batch_execution_interval'] = 60
            if result.get('buy_batch_execution_group_size') is None:
                result['buy_batch_execution_group_size'] = 1
            if result.get('sell_batch_size') is None:
                result['sell_batch_size'] = 1
            if result.get('sell_batch_execution_interval') is None:
                result['sell_batch_execution_interval'] = 60
            if result.get('sell_batch_execution_group_size') is None:
                result['sell_batch_execution_group_size'] = 1
            return result
        except Exception as e:
            logger.error(f"[Models] Failed to get model {model_id}: {e}")
            return None
    
    def get_all_models(self) -> List[Dict]:
        """
        Get all trading models
        
        Returns:
            所有模型信息列表
        """
        try:
            rows = self.query(f"""
                SELECT m.id, m.name, m.provider_id, m.model_name, m.initial_capital,
                       m.leverage, m.auto_buy_enabled, m.auto_sell_enabled, m.max_positions,
                       m.buy_batch_size, m.buy_batch_execution_interval, m.buy_batch_execution_group_size,
                       m.sell_batch_size, m.sell_batch_execution_interval, m.sell_batch_execution_group_size,
                       m.account_alias, m.is_virtual, m.symbol_source, m.created_at,
                       p.name as provider_name
                FROM {self.models_table} m
                LEFT JOIN {self.providers_table} p ON m.provider_id = p.id
                ORDER BY m.created_at DESC
            """)
            columns = ["id", "name", "provider_id", "model_name", "initial_capital",
                      "leverage", "auto_buy_enabled", "auto_sell_enabled", "max_positions",
                      "buy_batch_size", "buy_batch_execution_interval", "buy_batch_execution_group_size",
                      "sell_batch_size", "sell_batch_execution_interval", "sell_batch_execution_group_size",
                      "account_alias", "is_virtual", "symbol_source", "created_at", "provider_name"]
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
                # 【兼容性处理】确保symbol_source有默认值
                if not result.get('symbol_source'):
                    result['symbol_source'] = 'leaderboard'
                # 【兼容性处理】确保is_virtual有默认值
                if result.get('is_virtual') is None:
                    result['is_virtual'] = False
                # 【兼容性处理】确保max_positions有默认值
                if result.get('max_positions') is None:
                    result['max_positions'] = 3
                # 【兼容性处理】确保auto_buy_enabled和auto_sell_enabled有默认值
                if result.get('auto_buy_enabled') is None:
                    result['auto_buy_enabled'] = 1
                if result.get('auto_sell_enabled') is None:
                    result['auto_sell_enabled'] = 1
                # 【兼容性处理】确保批次配置字段有默认值
                if result.get('buy_batch_size') is None:
                    result['buy_batch_size'] = 1
                if result.get('buy_batch_execution_interval') is None:
                    result['buy_batch_execution_interval'] = 60
                if result.get('buy_batch_execution_group_size') is None:
                    result['buy_batch_execution_group_size'] = 1
                if result.get('sell_batch_size') is None:
                    result['sell_batch_size'] = 1
                if result.get('sell_batch_execution_interval') is None:
                    result['sell_batch_execution_interval'] = 60
                if result.get('sell_batch_execution_group_size') is None:
                    result['sell_batch_execution_group_size'] = 1
                else:
                    result['is_virtual'] = bool(result.get('is_virtual', 0))
            return results
        except Exception as e:
            logger.error(f"[Models] Failed to get all models: {e}")
            return []
    
    def is_model_auto_buy_enabled(self, model_id: int) -> bool:
        """
        Check auto buy flag for a model
        
        Args:
            model_id: 模型ID（整数）
        
        Returns:
            bool: True if auto_buy_enabled is 1, False if 0 or model not found
        """
        try:
            model = self.get_model(model_id)
            if not model:
                logger.debug(f"[Models] Model {model_id} not found, auto buy disabled")
                return False
            
            auto_buy_enabled = model.get('auto_buy_enabled')
            if auto_buy_enabled is None:
                auto_buy_enabled = 1
                logger.debug(f"[Models] Model {model_id} auto_buy_enabled is None, defaulting to 1")
            
            enabled = bool(auto_buy_enabled)
            logger.debug(f"[Models] Model {model_id} auto_buy_enabled={auto_buy_enabled} -> {enabled}")
            return enabled
            
        except Exception as e:
            logger.error(f"[Models] Failed to check auto buy flag for model {model_id}: {e}")
            return False
    
    def is_model_auto_sell_enabled(self, model_id: int) -> bool:
        """
        Check auto sell flag for a model
        
        Args:
            model_id: 模型ID（整数）
        
        Returns:
            bool: True if auto_sell_enabled is 1, False if 0 or model not found
        """
        try:
            model = self.get_model(model_id)
            if not model:
                logger.debug(f"[Models] Model {model_id} not found, auto sell disabled")
                return False
            
            auto_sell_enabled = model.get('auto_sell_enabled')
            if auto_sell_enabled is None:
                auto_sell_enabled = 1
                logger.debug(f"[Models] Model {model_id} auto_sell_enabled is None, defaulting to 1")
            
            enabled = bool(auto_sell_enabled)
            logger.debug(f"[Models] Model {model_id} auto_sell_enabled={auto_sell_enabled} -> {enabled}")
            return enabled
            
        except Exception as e:
            logger.error(f"[Models] Failed to check auto sell flag for model {model_id}: {e}")
            return False
    
    def set_model_auto_buy_enabled(self, model_id: int, enabled: bool) -> bool:
        """
        Enable or disable auto buy for a model
        
        Args:
            model_id: 模型ID（整数）
            enabled: 是否启用
        
        Returns:
            bool: 是否成功
        """
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return False
            
            self.command(f"""
                UPDATE `{self.models_table}` 
                SET `auto_buy_enabled` = %s
                WHERE `id` = %s
            """, (1 if enabled else 0, model_uuid))
            logger.info(f"[Models] Updated auto_buy_enabled to {enabled} for model {model_id}")
            return True
        except Exception as e:
            logger.error(f"[Models] Failed to update auto buy flag for model {model_id}: {e}")
            return False
    
    def set_model_auto_sell_enabled(self, model_id: int, enabled: bool) -> bool:
        """
        Enable or disable auto sell for a model
        
        Args:
            model_id: 模型ID（整数）
            enabled: 是否启用
        
        Returns:
            bool: 是否成功
        """
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return False
            
            self.command(f"""
                UPDATE `{self.models_table}` 
                SET `auto_sell_enabled` = %s
                WHERE `id` = %s
            """, (1 if enabled else 0, model_uuid))
            logger.info(f"[Models] Updated auto_sell_enabled to {enabled} for model {model_id}")
            return True
        except Exception as e:
            logger.error(f"[Models] Failed to update auto sell flag for model {model_id}: {e}")
            return False
    
    def set_model_leverage(self, model_id: int, leverage: int) -> bool:
        """
        Update model leverage
        
        Args:
            model_id: 模型ID（整数）
            leverage: 杠杆倍数
        
        Returns:
            bool: 是否成功
        """
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return False
            
            self.command(f"""
                UPDATE `{self.models_table}` 
                SET `leverage` = %s
                WHERE `id` = %s
            """, (leverage, model_uuid))
            return True
        except Exception as e:
            logger.error(f"[Models] Failed to update leverage for model {model_id}: {e}")
            return False
    
    def set_model_batch_config(self, model_id: int, 
                               buy_batch_size: int = None, buy_batch_execution_interval: int = None, buy_batch_execution_group_size: int = None,
                               sell_batch_size: int = None, sell_batch_execution_interval: int = None, sell_batch_execution_group_size: int = None) -> bool:
        """
        Update model batch configuration (批次配置)
        
        Args:
            model_id: 模型ID（整数）
            buy_batch_size: 买入批次大小
            buy_batch_execution_interval: 买入批次执行间隔（秒）
            buy_batch_execution_group_size: 买入批次执行组大小
            sell_batch_size: 卖出批次大小
            sell_batch_execution_interval: 卖出批次执行间隔（秒）
            sell_batch_execution_group_size: 卖出批次执行组大小
        
        Returns:
            bool: 是否成功
        """
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return False
            
            # 构建更新字段列表
            updates = []
            params = []
            
            if buy_batch_size is not None:
                buy_batch_size = max(1, int(buy_batch_size))
                updates.append("`buy_batch_size` = %s")
                params.append(buy_batch_size)
            
            if buy_batch_execution_interval is not None:
                buy_batch_execution_interval = max(0, int(buy_batch_execution_interval))
                updates.append("`buy_batch_execution_interval` = %s")
                params.append(buy_batch_execution_interval)
            
            if buy_batch_execution_group_size is not None:
                buy_batch_execution_group_size = max(1, int(buy_batch_execution_group_size))
                updates.append("`buy_batch_execution_group_size` = %s")
                params.append(buy_batch_execution_group_size)
            
            if sell_batch_size is not None:
                sell_batch_size = max(1, int(sell_batch_size))
                updates.append("`sell_batch_size` = %s")
                params.append(sell_batch_size)
            
            if sell_batch_execution_interval is not None:
                sell_batch_execution_interval = max(0, int(sell_batch_execution_interval))
                updates.append("`sell_batch_execution_interval` = %s")
                params.append(sell_batch_execution_interval)
            
            if sell_batch_execution_group_size is not None:
                sell_batch_execution_group_size = max(1, int(sell_batch_execution_group_size))
                updates.append("`sell_batch_execution_group_size` = %s")
                params.append(sell_batch_execution_group_size)
            
            if not updates:
                return True  # 没有需要更新的字段
            
            params.append(model_uuid)
            sql = f"""
                UPDATE `{self.models_table}` 
                SET {', '.join(updates)}
                WHERE `id` = %s
            """
            self.command(sql, tuple(params))
            logger.info(f"[Models] Updated batch config for model {model_id}")
            return True
        except Exception as e:
            logger.error(f"[Models] Failed to update batch config for model {model_id}: {e}")
            return False
    
    def set_model_max_positions(self, model_id: int, max_positions: int) -> bool:
        """
        Update model max_positions (最大持仓数量)
        
        Args:
            model_id: 模型ID（整数）
            max_positions: 最大持仓数量
        
        Returns:
            bool: 是否成功
        """
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                return False
            
            # 验证 max_positions 值
            if not isinstance(max_positions, int) or max_positions < 1:
                logger.error(f"[Models] Invalid max_positions value: {max_positions}, must be >= 1")
                return False
            
            self.command(f"""
                UPDATE `{self.models_table}` 
                SET `max_positions` = %s
                WHERE `id` = %s
            """, (max_positions, model_uuid))
            logger.info(f"[Models] Updated max_positions to {max_positions} for model {model_id}")
            return True
        except Exception as e:
            logger.error(f"[Models] Failed to update max_positions for model {model_id}: {e}")
            return False
    
    def set_model_provider_and_model_name(self, model_id: int, provider_id: int, model_name: str) -> bool:
        """
        Update model provider_id and model_name
        
        Args:
            model_id: 模型ID（整数）
            provider_id: 新的API提供方ID（整数）
            model_name: 新的模型名称（字符串）
        
        Returns:
            bool: 更新是否成功
        """
        try:
            model_mapping = self._get_model_id_mapping()
            model_uuid = model_mapping.get(model_id)
            if not model_uuid:
                logger.warning(f"[Models] Model {model_id} UUID not found")
                return False
            
            # 获取 provider UUID
            provider_mapping = self._get_provider_id_mapping()
            provider_uuid = provider_mapping.get(provider_id)
            if not provider_uuid:
                logger.warning(f"[Models] Provider {provider_id} UUID not found")
                return False
            
            self.command(f"""
                UPDATE `{self.models_table}` 
                SET `provider_id` = %s, `model_name` = %s
                WHERE `id` = %s
            """, (provider_uuid, model_name, model_uuid))
            
            logger.info(f"[Models] Updated model {model_id}: provider_id={provider_id}, model_name={model_name}")
            return True
        except Exception as e:
            logger.error(f"[Models] Failed to update provider and model_name for model {model_id}: {e}")
            return False

