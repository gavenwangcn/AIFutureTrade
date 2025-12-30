"""
市场行情数据表操作模块 - 24_market_tickers 表

本模块提供市场行情数据的增删改查操作，包括：
1. 行情数据更新和插入（upsert）
2. 开盘价更新
3. 涨跌榜查询
4. 数据清理

主要组件：
- MarketTickersDatabase: 市场行情数据操作类
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Callable
import pymysql
from pymysql import cursors
from .database_basic import create_pooled_db
import trade.common.config as app_config

MARKET_TICKER_TABLE = "24_market_tickers"

logger = logging.getLogger(__name__)


def _to_datetime(value: Any) -> Optional[datetime]:
    """Convert various datetime formats to naive datetime object (consistent with ingestion_time format)."""
    if value is None:
        return None
    
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            utc_value = value.astimezone(timezone.utc)
            return utc_value.replace(tzinfo=None)
        else:
            return value
    
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp <= 0:
            logger.warning("[MarketTickers] Invalid timestamp value: %s", timestamp)
            return None
        
        MIN_VALID_TIMESTAMP_SECONDS = 946684800
        if timestamp < MIN_VALID_TIMESTAMP_SECONDS:
            logger.warning("[MarketTickers] Timestamp value too small: %s", timestamp)
            return None
        
        MAX_REASONABLE_TIMESTAMP_SECONDS = 4102444800
        if timestamp > MAX_REASONABLE_TIMESTAMP_SECONDS:
            timestamp = timestamp / 1000.0
        
        try:
            return datetime.fromtimestamp(timestamp)
        except (ValueError, OSError) as e:
            logger.warning("[MarketTickers] Failed to convert timestamp %s to datetime: %s", value, e)
            return None
    
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if dt.tzinfo is not None:
                utc_dt = dt.astimezone(timezone.utc)
                return utc_dt.replace(tzinfo=None)
            return dt
        except ValueError:
            try:
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d']:
                    try:
                        return datetime.strptime(value, fmt)
                    except ValueError:
                        continue
            except Exception:
                pass
    
    return None


def _to_beijing_datetime(value: Any) -> Optional[datetime]:
    """Convert various datetime formats to naive datetime object in Beijing time (UTC+8)."""
    utc_naive_dt = _to_datetime(value)
    if utc_naive_dt is None:
        return None
    
    try:
        utc_dt = utc_naive_dt.replace(tzinfo=timezone.utc)
        beijing_tz = timezone(timedelta(hours=8))
        beijing_dt = utc_dt.astimezone(beijing_tz)
        return beijing_dt.replace(tzinfo=None)
    except Exception as e:
        logger.warning("[MarketTickers] Failed to convert to Beijing time: %s", e)
        return None


class MarketTickersDatabase:
    """
    市场行情数据操作类
    
    封装24_market_tickers表的所有数据库操作。
    """
    
    def __init__(self, pool=None):
        """
        初始化市场行情数据库操作类
        
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
        
        self.market_ticker_table = MARKET_TICKER_TABLE
    
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
                            logger.debug(f"[MarketTickers] Error rolling back transaction: {rollback_error}")
                        
                        # 对于所有错误，关闭连接，DBUtils会自动处理损坏的连接
                        try:
                            conn.close()
                        except Exception as close_error:
                            logger.debug(f"[MarketTickers] Error closing connection: {close_error}")
                        finally:
                            # 确保连接引用被清除，即使关闭失败也要标记为已处理
                            conn = None
                    except Exception as close_error:
                        logger.error(f"[MarketTickers] Critical error closing failed connection: {close_error}")
                        # 即使发生异常，也要清除连接引用
                        conn = None
                
                if attempt < max_retries - 1:
                    if is_network_error and (isinstance(e, pymysql.err.MySQLError) and e.args[0] == 1213 or 'deadlock' in error_msg.lower()):
                        wait_time = 1.0 * (1.5 ** attempt)
                        logger.warning(
                            f"[MarketTickers] Deadlock error on attempt {attempt + 1}/{max_retries}: "
                            f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                        )
                    else:
                        wait_time = retry_delay * (2 ** attempt)
                        if is_network_error:
                            logger.warning(
                                f"[MarketTickers] Network error on attempt {attempt + 1}/{max_retries}: "
                                f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                            )
                        else:
                            logger.warning(
                                f"[MarketTickers] Error on attempt {attempt + 1}/{max_retries}: "
                                f"{error_type}: {error_msg}. Retrying in {wait_time:.2f} seconds..."
                            )
                    
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"[MarketTickers] Failed after {max_retries} attempts. Last error: {error_type}: {error_msg}"
                    )
                    raise
            finally:
                if connection_acquired and conn:
                    try:
                        logger.warning(
                            f"[MarketTickers] Connection not closed in finally block, closing it"
                        )
                        try:
                            conn.rollback()
                            conn.close()
                        except Exception:
                            pass
                    except Exception as final_error:
                        logger.debug(f"[MarketTickers] Error in finally block: {final_error}")
    
    def get_existing_symbol_data(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """获取数据库中已存在交易对的最新数据。"""
        if not symbols:
            return {}
        
        try:
            placeholders = ', '.join(['%s'] * len(symbols))
            query = f"""
            SELECT 
                symbol,
                open_price,
                last_price,
                update_price_date
            FROM `{self.market_ticker_table}`
            WHERE symbol IN ({placeholders})
            """
            
            def _execute_query(conn):
                cursor = conn.cursor()
                try:
                    cursor.execute(query, symbols)
                    return cursor.fetchall()
                finally:
                    cursor.close()
            
            result = self._with_connection(_execute_query)
            
            symbol_data = {}
            for row in result:
                if isinstance(row, dict):
                    symbol = row['symbol']
                    open_price_raw = row['open_price']
                    last_price = row.get('last_price')
                    update_price_date = row.get('update_price_date')
                else:
                    symbol = row[0]
                    open_price_raw = row[1]
                    last_price = row[2] if len(row) > 2 else None
                    update_price_date = row[3] if len(row) > 3 else None
                
                if open_price_raw == 0.0 and update_price_date is None:
                    open_price = None
                else:
                    open_price = open_price_raw if open_price_raw is not None else None
                
                symbol_data[symbol] = {
                    "open_price": open_price,
                    "last_price": last_price,
                    "update_price_date": update_price_date
                }
            
            return symbol_data
        except Exception as e:
            logger.warning("[MarketTickers] Failed to get existing symbol data: %s", e)
            return {}
    
    def upsert_market_tickers(self, rows: Iterable[Dict[str, Any]]) -> None:
        """更新或插入市场行情数据（upsert操作）。"""
        logger.info("[MarketTickers] Starting upsert_market_tickers")
        
        if not rows:
            logger.info("[MarketTickers] No rows provided for upsert, returning")
            return
        
        rows_list = list(rows)
        usdt_rows = [row for row in rows_list if row.get("symbol", "").endswith("USDT")]
        logger.info("[MarketTickers] 从%d条总数据中筛选出%d条USDT交易对数据", len(rows_list), len(usdt_rows))
        
        if not usdt_rows:
            logger.debug("[MarketTickers] No USDT symbols to upsert")
            return
        
        processed_rows = []
        
        for row in usdt_rows:
            normalized = dict(row)
            
            symbol = normalized.get("symbol")
            if not symbol:
                logger.debug("[MarketTickers] Skipping row without symbol: %s", row)
                continue
            
            if "open_price" in normalized:
                del normalized["open_price"]
                logger.debug("[MarketTickers] 移除了%s的open_price字段", symbol)
            if "update_price_date" in normalized:
                del normalized["update_price_date"]
                logger.debug("[MarketTickers] 移除了%s的update_price_date字段", symbol)
            
            normalized["event_time"] = _to_beijing_datetime(normalized.get("event_time"))
            normalized["stats_open_time"] = _to_beijing_datetime(normalized.get("stats_open_time"))
            normalized["stats_close_time"] = _to_beijing_datetime(normalized.get("stats_close_time"))
            
            logger.debug("[MarketTickers] Adding symbol %s to upsert list", symbol)
            processed_rows.append((symbol, normalized))
        
        logger.debug("[MarketTickers] Processed %d USDT symbols for upsert", len(processed_rows))
        
        if not processed_rows:
            logger.debug("[MarketTickers] No symbols to upsert after processing, returning")
            return
        
        symbols_to_process = [symbol for symbol, _ in processed_rows]
        existing_data = self.get_existing_symbol_data(symbols_to_process)
        logger.debug("[MarketTickers] Retrieved existing data for %d symbols", len(existing_data))
        
        total_upserted = 0
        total_updated = 0
        total_inserted = 0
        total_failed = 0
        
        logger.debug("[MarketTickers] Processing %d symbols as one batch", len(processed_rows))
        
        def _execute_upsert_batch(conn, batch):
            nonlocal total_upserted, total_updated, total_inserted, total_failed
            
            insert_sql = f"""
            INSERT INTO `{self.market_ticker_table}` 
            (`event_time`, `symbol`, `price_change`, `price_change_percent`, 
             `side`, `change_percent_text`, `average_price`, `last_price`, 
             `last_trade_volume`, `open_price`, `high_price`, `low_price`, 
             `base_volume`, `quote_volume`, `stats_open_time`, `stats_close_time`, 
             `first_trade_id`, `last_trade_id`, `trade_count`, `update_price_date`,
             `ingestion_time`)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                event_time = VALUES(event_time),
                price_change = VALUES(price_change),
                price_change_percent = VALUES(price_change_percent),
                side = VALUES(side),
                change_percent_text = VALUES(change_percent_text),
                average_price = VALUES(average_price),
                last_price = VALUES(last_price),
                last_trade_volume = VALUES(last_trade_volume),
                high_price = VALUES(high_price),
                low_price = VALUES(low_price),
                base_volume = VALUES(base_volume),
                quote_volume = VALUES(quote_volume),
                stats_open_time = VALUES(stats_open_time),
                stats_close_time = VALUES(stats_close_time),
                first_trade_id = VALUES(first_trade_id),
                last_trade_id = VALUES(last_trade_id),
                trade_count = VALUES(trade_count),
                ingestion_time = VALUES(ingestion_time)
            """
            
            batch_params = []
            valid_symbols = []
            
            for symbol, normalized in batch:
                try:
                    logger.debug("[MarketTickers] Processing symbol: %s", symbol)
                    
                    try:
                        current_last_price = float(normalized.get("last_price", 0))
                        logger.debug("[MarketTickers] Extracted last_price for %s: %f", symbol, current_last_price)
                    except (TypeError, ValueError) as e:
                        current_last_price = 0.0
                        logger.warning("[MarketTickers] Failed to extract last_price for %s: %s", symbol, e)
                    
                    existing_symbol_data = existing_data.get(symbol)
                    existing_open_price = existing_symbol_data.get("open_price") if existing_symbol_data else None
                    existing_update_price_date = existing_symbol_data.get("update_price_date") if existing_symbol_data else None
                    
                    logger.debug("[MarketTickers] Existing data for %s: open_price=%s", symbol, existing_open_price)
                    
                    if existing_open_price is not None and existing_open_price != 0 and current_last_price != 0:
                        logger.debug("[MarketTickers] Calculating price change for %s", symbol)
                        
                        try:
                            existing_open_price_float = float(existing_open_price)
                            current_last_price_float = float(current_last_price)
                            
                            price_change = current_last_price_float - existing_open_price_float
                            price_change_percent = (price_change / existing_open_price_float) * 100
                            side = "gainer" if price_change_percent >= 0 else "loser"
                            change_percent_text = f"{price_change_percent:.2f}%"
                            
                            logger.debug("[MarketTickers] Calculated price change for %s: %f (%.2f%%)", 
                                       symbol, price_change, price_change_percent)
                            
                            normalized["price_change"] = price_change
                            normalized["price_change_percent"] = price_change_percent
                            normalized["side"] = side
                            normalized["change_percent_text"] = change_percent_text
                            normalized["open_price"] = existing_open_price_float
                            normalized["update_price_date"] = existing_update_price_date
                        except (TypeError, ValueError) as e:
                            logger.warning("[MarketTickers] Failed to calculate price change for symbol %s: %s", symbol, e)
                            normalized["price_change"] = 0.0
                            normalized["price_change_percent"] = 0.0
                            normalized["side"] = ""
                            normalized["change_percent_text"] = ""
                            try:
                                existing_open_price_float = float(existing_open_price) if existing_open_price else 0.0
                            except (TypeError, ValueError):
                                existing_open_price_float = 0.0
                            normalized["open_price"] = existing_open_price_float
                            normalized["update_price_date"] = existing_update_price_date
                    else:
                        logger.debug("[MarketTickers] Not calculating price change for %s", symbol)
                        normalized["price_change"] = 0.0
                        normalized["price_change_percent"] = 0.0
                        normalized["side"] = ""
                        normalized["change_percent_text"] = ""
                        normalized["open_price"] = 0.0
                        normalized["update_price_date"] = existing_update_price_date if existing_symbol_data else None
                    
                    double_fields = [
                        "price_change", "price_change_percent", "average_price", "last_price",
                        "last_trade_volume", "open_price", "high_price", "low_price",
                        "base_volume", "quote_volume"
                    ]
                    for field in double_fields:
                        if normalized.get(field) is None:
                            normalized[field] = 0.0
                            logger.debug("[MarketTickers] Set %s.%s to 0.0", symbol, field)
                    
                    bigint_fields = ["first_trade_id", "last_trade_id", "trade_count"]
                    for field in bigint_fields:
                        if normalized.get(field) is None:
                            normalized[field] = 0
                            logger.debug("[MarketTickers] Set %s.%s to 0", symbol, field)
                    
                    string_fields = ["side", "change_percent_text"]
                    for field in string_fields:
                        if normalized.get(field) is None:
                            normalized[field] = ""
                            logger.debug("[MarketTickers] Set %s.%s to empty string", symbol, field)
                    
                    datetime_fields = ["event_time", "stats_open_time", "stats_close_time"]
                    for field in datetime_fields:
                        field_value = normalized.get(field)
                        if field_value is None:
                            normalized[field] = datetime.now(timezone(timedelta(hours=8)))
                            logger.debug("[MarketTickers] 设置%s.%s为当前时间", symbol, field)
                        elif isinstance(field_value, datetime) and field_value.tzinfo is not None:
                            normalized[field] = field_value.astimezone(timezone.utc).replace(tzinfo=None)
                            logger.debug("[MarketTickers] 转换%s.%s为naive datetime", symbol, field)
                    
                    if normalized.get("event_time") is None:
                        logger.warning(
                            "[MarketTickers] Skipping market ticker for symbol %s: invalid event_time value",
                            symbol
                        )
                        continue
                    
                    logger.debug("[MarketTickers] Final normalized data for %s", symbol)
                    
                    insert_open_price = normalized.get("open_price", 0.0)
                    insert_update_price_date = normalized.get("update_price_date")
                    
                    if not existing_symbol_data:
                        insert_open_price = 0.0
                        insert_update_price_date = None
                        logger.debug("[MarketTickers] 设置%s的open_price为0.0（新插入）", symbol)
                    
                    insert_params = (
                        normalized.get("event_time"),
                        symbol,
                        normalized.get("price_change", 0.0),
                        normalized.get("price_change_percent", 0.0),
                        normalized.get("side", ""),
                        normalized.get("change_percent_text", ""),
                        normalized.get("average_price", 0.0),
                        normalized.get("last_price", 0.0),
                        normalized.get("last_trade_volume", 0.0),
                        insert_open_price,
                        normalized.get("high_price", 0.0),
                        normalized.get("low_price", 0.0),
                        normalized.get("base_volume", 0.0),
                        normalized.get("quote_volume", 0.0),
                        normalized.get("stats_open_time"),
                        normalized.get("stats_close_time"),
                        normalized.get("first_trade_id", 0),
                        normalized.get("last_trade_id", 0),
                        normalized.get("trade_count", 0),
                        insert_update_price_date,
                        _to_beijing_datetime(datetime.now(timezone.utc))
                    )
                    
                    batch_params.append(insert_params)
                    valid_symbols.append(symbol)
                    
                except Exception as e:
                    logger.error("[MarketTickers] Failed to prepare data for symbol %s: %s", symbol, e, exc_info=True)
                    total_failed += 1
                    continue
            
            if not batch_params:
                logger.debug("[MarketTickers] No valid data to upsert in this batch")
                return
            
            cursor = None
            try:
                try:
                    conn.ping(reconnect=True)
                    logger.debug("[MarketTickers] Connection ping successful")
                except (AttributeError, Exception) as ping_error:
                    logger.warning("[MarketTickers] Connection is not healthy: %s, will retry", ping_error)
                    raise Exception(f"Connection lost: {ping_error}")
                
                if hasattr(conn, '_sock') and conn._sock is None:
                    logger.warning("[MarketTickers] Connection socket is closed, will retry")
                    raise Exception("Connection socket is closed")
                
                cursor = conn.cursor()
                logger.debug("[MarketTickers] Executing batch upsert for %d symbols", len(batch_params))
                cursor.executemany(insert_sql, batch_params)
                
                affected_rows = cursor.rowcount
                logger.debug("[MarketTickers] Batch upsert affected %d rows", affected_rows)
                
                total_upserted += affected_rows
                total_updated += affected_rows
                
                conn.commit()
                logger.debug("[MarketTickers] Batch upsert committed successfully")
                
            except (pymysql.err.InterfaceError, pymysql.err.OperationalError, pymysql.err.InternalError, ValueError, Exception) as db_error:
                if cursor:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                cursor = None
                error_type = type(db_error).__name__
                error_msg = str(db_error)
                
                if (isinstance(db_error, (pymysql.err.InterfaceError, pymysql.err.OperationalError, pymysql.err.InternalError)) or 
                    'interface' in error_type.lower() or 'operational' in error_type.lower() or 
                    'internalerror' in error_type.lower() or
                    'PyMemoryView_FromBuffer' in error_msg or 'buf must not be NULL' in error_msg or
                    'Packet sequence number' in error_msg):
                    logger.warning("[MarketTickers] Database connection or memory error: %s, will retry", db_error)
                    raise Exception(f"Database connection or memory error: {db_error}")
                else:
                    raise
            
            if cursor:
                cursor.close()
                cursor = None
        
        def _execute_current_batch(conn):
            return _execute_upsert_batch(conn, processed_rows)
        
        self._with_connection(_execute_current_batch)
        
        logger.debug("[MarketTickers] Upsert completed: %d total symbols processed", len(processed_rows))
    
    def update_open_price(self, symbol: str, open_price: float, update_date: datetime) -> bool:
        """更新指定symbol的open_price和update_price_date。"""
        update_data = [{
            'symbol': symbol,
            'open_price': open_price
        }]
        results = self.update_open_price_batch(update_data, batch_size=1)
        return results[0] if results else False
    
    def update_open_price_batch(self, update_data: List[Dict[str, Any]], batch_size: int = 100) -> List[bool]:
        """批量更新多个symbol的open_price和update_price_date。"""
        if not update_data:
            return []
            
        try:
            utc8 = timezone(timedelta(hours=8))
            update_price_date = datetime.now(utc8)
            
            results = []
            for i in range(0, len(update_data), batch_size):
                batch = update_data[i:i+batch_size]
                if not batch:
                    continue
                    
                case_statements = []
                params = []
                symbols = []
                
                for item in batch:
                    symbol = item.get('symbol')
                    open_price = float(item.get('open_price', 0.0))
                    
                    if not symbol:
                        results.append(False)
                        continue
                        
                    symbols.append(symbol)
                    case_statements.append(f"WHEN `symbol` = %s THEN %s")
                    params.extend([symbol, open_price])
                    
                if not symbols:
                    continue
                    
                update_query = f"""
                UPDATE `{self.market_ticker_table}`
                SET 
                    `open_price` = CASE 
                        {' '.join(case_statements)} 
                        ELSE `open_price`
                    END,
                    `price_change` = CASE 
                        {' '.join([f"WHEN `symbol` = %s THEN CASE WHEN `last_price` > 0 AND %s > 0 THEN `last_price` - %s ELSE 0.0 END" for _ in symbols])} 
                        ELSE `price_change`
                    END,
                    `price_change_percent` = CASE 
                        {' '.join([f"WHEN `symbol` = %s THEN CASE WHEN `last_price` > 0 AND %s > 0 THEN ((`last_price` - %s) / %s) * 100 ELSE 0.0 END" for _ in symbols])} 
                        ELSE `price_change_percent`
                    END,
                    `side` = CASE 
                        {' '.join([f"WHEN `symbol` = %s THEN CASE WHEN `last_price` > 0 AND %s > 0 THEN CASE WHEN ((`last_price` - %s) / %s) * 100 >= 0 THEN 'gainer' ELSE 'loser' END ELSE '' END" for _ in symbols])} 
                        ELSE `side`
                    END,
                    `change_percent_text` = CASE 
                        {' '.join([f"WHEN `symbol` = %s THEN CASE WHEN `last_price` > 0 AND %s > 0 THEN CONCAT(FORMAT(((`last_price` - %s) / %s) * 100, 2), '%%') ELSE '' END" for _ in symbols])} 
                        ELSE `change_percent_text`
                    END,
                    `update_price_date` = %s
                WHERE `symbol` IN ({', '.join(['%s' for _ in symbols])})
                """
                
                for item in batch:
                    symbol = item.get('symbol')
                    open_price = float(item.get('open_price', 0.0))
                    params.extend([symbol, open_price, open_price])
                    params.extend([symbol, open_price, open_price, open_price])
                    params.extend([symbol, open_price, open_price, open_price])
                    params.extend([symbol, open_price, open_price, open_price])
                
                params.append(update_price_date)
                params.extend(symbols)
                
                def _execute_batch_update(conn):
                    cursor = conn.cursor()
                    try:
                        cursor.execute(update_query, params)
                        affected_rows = cursor.rowcount
                        logger.debug(
                            "[MarketTickers] Batch updated open_price for %s symbols | affected rows: %s",
                            len(symbols),
                            affected_rows
                        )
                        return affected_rows
                    finally:
                        cursor.close()
                
                affected_rows = self._with_connection(_execute_batch_update)
                batch_results = [True] * len(batch)
                results.extend(batch_results)
                
            return results
        except Exception as e:
            logger.error("[MarketTickers] Failed to batch update open_price: %s", e, exc_info=True)
            return [False] * len(update_data)
    
    def get_symbols_needing_price_refresh(self) -> List[str]:
        """获取需要刷新价格的symbol列表。"""
        try:
            one_hour_ago = datetime.now(timezone(timedelta(hours=8))) - timedelta(hours=1)
            
            sql = f"""
            SELECT `symbol`
            FROM `{self.market_ticker_table}`
            WHERE `update_price_date` IS NULL 
               OR `update_price_date` < %s
            ORDER BY `event_time`
            """
            
            def _execute_query(conn):
                cursor = conn.cursor()
                try:
                    real_sql = cursor.mogrify(sql, (one_hour_ago,))
                    logger.info("[MarketTickers] Executing get_symbols_needing_price_refresh SQL: %s", real_sql)
                    
                    cursor.execute(sql, (one_hour_ago,))
                    rows = cursor.fetchall()
                    symbols = []
                    for row in rows:
                        if isinstance(row, dict):
                            symbols.append(row['symbol'])
                        elif isinstance(row, (list, tuple)):
                            symbols.append(row[0])
                        else:
                            symbols.append(str(row))
                    return symbols
                finally:
                    cursor.close()
            
            symbols = self._with_connection(_execute_query)
            logger.debug(
                "[MarketTickers] Found %s symbols needing price refresh",
                len(symbols)
            )
            return symbols if symbols else []
        except Exception as e:
            logger.error("[MarketTickers] Failed to get symbols needing price refresh: %s", e)
            return []
    
    def count_old_tickers(self, cutoff_date: datetime) -> int:
        """统计需要删除的过期ticker记录数量。"""
        try:
            query = f"""
            SELECT COUNT(*) FROM `{self.market_ticker_table}`
            WHERE ingestion_time < %s
            """
            
            def _execute_query(conn):
                cursor = conn.cursor()
                try:
                    cursor.execute(query, (cutoff_date,))
                    result = cursor.fetchone()
                    if result is None:
                        return 0
                    elif isinstance(result, dict):
                        return int(list(result.values())[0]) if result else 0
                    elif isinstance(result, (list, tuple)):
                        return int(result[0]) if len(result) > 0 else 0
                    else:
                        return 0
                finally:
                    cursor.close()
            
            count = self._with_connection(_execute_query)
            logger.debug(
                "[MarketTickers] Found %d old ticker records before %s",
                count,
                cutoff_date.strftime('%Y-%m-%d %H:%M:%S UTC')
            )
            return count
        except Exception as e:
            logger.error("[MarketTickers] Failed to count old tickers: %s", e, exc_info=True)
            return 0
    
    def delete_old_tickers(self, cutoff_date: datetime) -> int:
        """删除过期的ticker记录。"""
        try:
            query = f"""
            DELETE FROM `{self.market_ticker_table}`
            WHERE ingestion_time < %s
            """
            
            def _execute_delete(conn):
                cursor = conn.cursor()
                try:
                    cursor.execute(query, (cutoff_date,))
                    deleted_count = cursor.rowcount
                    conn.commit()
                    return deleted_count
                except Exception as e:
                    conn.rollback()
                    raise e
                finally:
                    cursor.close()
            
            deleted_count = self._with_connection(_execute_delete)
            logger.info(
                "[MarketTickers] Deleted %d old ticker records before %s",
                deleted_count,
                cutoff_date.strftime('%Y-%m-%d %H:%M:%S UTC')
            )
            return deleted_count
        except Exception as e:
            logger.error("[MarketTickers] Failed to delete old tickers: %s", e, exc_info=True)
            return 0
    
    def get_gainers_from_tickers(self, limit: int = 10) -> List[Dict[str, Any]]:
        """从 24_market_tickers 表获取涨幅榜数据。"""
        try:
            query = f"""
            SELECT 
                `symbol`, `price_change_percent`, `last_price`, `quote_volume`,
                `event_time`, `side`
            FROM `{self.market_ticker_table}`
            WHERE `price_change_percent` IS NOT NULL
            AND `price_change_percent` > 0
            ORDER BY `price_change_percent` DESC
            LIMIT %s
            """
            
            def _execute_query(conn):
                cursor = conn.cursor()
                try:
                    cursor.execute(query, (limit,))
                    rows = cursor.fetchall()
                    
                    result = []
                    for idx, row in enumerate(rows, 1):
                        if isinstance(row, dict):
                            result.append({
                                'symbol': row.get('symbol', ''),
                                'contract_symbol': row.get('symbol', ''),
                                'name': row.get('symbol', '').replace('USDT', '') if row.get('symbol', '').endswith('USDT') else row.get('symbol', ''),
                                'exchange': 'BINANCE_FUTURES',
                                'side': 'gainer',
                                'position': idx,
                                'price': float(row.get('last_price', 0.0)),
                                'change_percent': float(row.get('price_change_percent', 0.0)),
                                'quote_volume': float(row.get('quote_volume', 0.0)),
                                'timeframes': '',
                                'event_time': row.get('event_time'),
                            })
                        elif isinstance(row, (list, tuple)):
                            result.append({
                                'symbol': row[0] if len(row) > 0 else '',
                                'contract_symbol': row[0] if len(row) > 0 else '',
                                'name': (row[0] if len(row) > 0 else '').replace('USDT', '') if (row[0] if len(row) > 0 else '').endswith('USDT') else (row[0] if len(row) > 0 else ''),
                                'exchange': 'BINANCE_FUTURES',
                                'side': 'gainer',
                                'position': idx,
                                'price': float(row[2]) if len(row) > 2 and row[2] is not None else 0.0,
                                'change_percent': float(row[1]) if len(row) > 1 and row[1] is not None else 0.0,
                                'quote_volume': float(row[3]) if len(row) > 3 and row[3] is not None else 0.0,
                                'timeframes': '',
                                'event_time': row[4] if len(row) > 4 else None,
                            })
                    return result
                finally:
                    cursor.close()
            
            return self._with_connection(_execute_query)
        except Exception as e:
            logger.error("[MarketTickers] Failed to get gainers from tickers: %s", e, exc_info=True)
            return []
    
    def get_losers_from_tickers(self, limit: int = 10) -> List[Dict[str, Any]]:
        """从 24_market_tickers 表获取跌幅榜数据。"""
        try:
            query = f"""
            SELECT 
                `symbol`, `price_change_percent`, `last_price`, `quote_volume`,
                `event_time`, `side`
            FROM `{self.market_ticker_table}`
            WHERE `price_change_percent` IS NOT NULL
            AND `price_change_percent` < 0
            ORDER BY ABS(`price_change_percent`) DESC
            LIMIT %s
            """
            
            def _execute_query(conn):
                cursor = conn.cursor()
                try:
                    cursor.execute(query, (limit,))
                    rows = cursor.fetchall()
                    
                    result = []
                    for idx, row in enumerate(rows, 1):
                        if isinstance(row, dict):
                            result.append({
                                'symbol': row.get('symbol', ''),
                                'contract_symbol': row.get('symbol', ''),
                                'name': row.get('symbol', '').replace('USDT', '') if row.get('symbol', '').endswith('USDT') else row.get('symbol', ''),
                                'exchange': 'BINANCE_FUTURES',
                                'side': 'loser',
                                'position': idx,
                                'price': float(row.get('last_price', 0.0)),
                                'change_percent': float(row.get('price_change_percent', 0.0)),
                                'quote_volume': float(row.get('quote_volume', 0.0)),
                                'timeframes': '',
                                'event_time': row.get('event_time'),
                            })
                        elif isinstance(row, (list, tuple)):
                            result.append({
                                'symbol': row[0] if len(row) > 0 else '',
                                'contract_symbol': row[0] if len(row) > 0 else '',
                                'name': (row[0] if len(row) > 0 else '').replace('USDT', '') if (row[0] if len(row) > 0 else '').endswith('USDT') else (row[0] if len(row) > 0 else ''),
                                'exchange': 'BINANCE_FUTURES',
                                'side': 'loser',
                                'position': idx,
                                'price': float(row[2]) if len(row) > 2 and row[2] is not None else 0.0,
                                'change_percent': float(row[1]) if len(row) > 1 and row[1] is not None else 0.0,
                                'quote_volume': float(row[3]) if len(row) > 3 and row[3] is not None else 0.0,
                                'timeframes': '',
                                'event_time': row[4] if len(row) > 4 else None,
                            })
                    return result
                finally:
                    cursor.close()
            
            return self._with_connection(_execute_query)
        except Exception as e:
            logger.error("[MarketTickers] Failed to get losers from tickers: %s", e, exc_info=True)
            return []
    
    def get_leaderboard_from_tickers(self, limit: int = 10) -> Dict[str, List[Dict[str, Any]]]:
        """从 24_market_tickers 表获取涨幅榜和跌幅榜数据（一次查询）。"""
        try:
            query = f"""
            (SELECT 
                'gainer' as type, `symbol`, `price_change_percent`, `last_price`, `quote_volume`, `event_time`
            FROM `{self.market_ticker_table}`
            WHERE `price_change_percent` IS NOT NULL
            AND `price_change_percent` > 0
            ORDER BY `price_change_percent` DESC
            LIMIT %s)
            UNION ALL
            (SELECT 
                'loser' as type, `symbol`, `price_change_percent`, `last_price`, `quote_volume`, `event_time`
            FROM `{self.market_ticker_table}`
            WHERE `price_change_percent` IS NOT NULL
            AND `price_change_percent` < 0
            ORDER BY ABS(`price_change_percent`) DESC
            LIMIT %s)
            """
            
            def _execute_query(conn):
                cursor = conn.cursor()
                try:
                    cursor.execute(query, (limit, limit))
                    rows = cursor.fetchall()
                    
                    gainers = []
                    losers = []
                    
                    type_rows = {'gainer': [], 'loser': []}
                    for row in rows:
                        if isinstance(row, dict):
                            row_type = row.get('type', '')
                            if row_type in type_rows:
                                type_rows[row_type].append(row)
                        elif isinstance(row, (list, tuple)):
                            row_type = row[0] if len(row) > 0 else ''
                            if row_type in type_rows:
                                type_rows[row_type].append(row)
                    
                    for idx, row in enumerate(type_rows['gainer'], 1):
                        if isinstance(row, dict):
                            gainers.append({
                                'symbol': row.get('symbol', ''),
                                'contract_symbol': row.get('symbol', ''),
                                'name': row.get('symbol', '').replace('USDT', '') if row.get('symbol', '').endswith('USDT') else row.get('symbol', ''),
                                'exchange': 'BINANCE_FUTURES',
                                'side': 'gainer',
                                'position': idx,
                                'price': float(row.get('last_price', 0.0)),
                                'change_percent': float(row.get('price_change_percent', 0.0)),
                                'quote_volume': float(row.get('quote_volume', 0.0)),
                                'timeframes': '',
                                'event_time': row.get('event_time'),
                            })
                        elif isinstance(row, (list, tuple)):
                            gainers.append({
                                'symbol': row[1] if len(row) > 1 else '',
                                'contract_symbol': row[1] if len(row) > 1 else '',
                                'name': (row[1] if len(row) > 1 else '').replace('USDT', '') if (row[1] if len(row) > 1 else '').endswith('USDT') else (row[1] if len(row) > 1 else ''),
                                'exchange': 'BINANCE_FUTURES',
                                'side': 'gainer',
                                'position': idx,
                                'price': float(row[3]) if len(row) > 3 and row[3] is not None else 0.0,
                                'change_percent': float(row[2]) if len(row) > 2 and row[2] is not None else 0.0,
                                'quote_volume': float(row[4]) if len(row) > 4 and row[4] is not None else 0.0,
                                'timeframes': '',
                                'event_time': row[5] if len(row) > 5 else None,
                            })
                    
                    for idx, row in enumerate(type_rows['loser'], 1):
                        if isinstance(row, dict):
                            losers.append({
                                'symbol': row.get('symbol', ''),
                                'contract_symbol': row.get('symbol', ''),
                                'name': row.get('symbol', '').replace('USDT', '') if row.get('symbol', '').endswith('USDT') else row.get('symbol', ''),
                                'exchange': 'BINANCE_FUTURES',
                                'side': 'loser',
                                'position': idx,
                                'price': float(row.get('last_price', 0.0)),
                                'change_percent': float(row.get('price_change_percent', 0.0)),
                                'quote_volume': float(row.get('quote_volume', 0.0)),
                                'timeframes': '',
                                'event_time': row.get('event_time'),
                            })
                        elif isinstance(row, (list, tuple)):
                            losers.append({
                                'symbol': row[1] if len(row) > 1 else '',
                                'contract_symbol': row[1] if len(row) > 1 else '',
                                'name': (row[1] if len(row) > 1 else '').replace('USDT', '') if (row[1] if len(row) > 1 else '').endswith('USDT') else (row[1] if len(row) > 1 else ''),
                                'exchange': 'BINANCE_FUTURES',
                                'side': 'loser',
                                'position': idx,
                                'price': float(row[3]) if len(row) > 3 and row[3] is not None else 0.0,
                                'change_percent': float(row[2]) if len(row) > 2 and row[2] is not None else 0.0,
                                'quote_volume': float(row[4]) if len(row) > 4 and row[4] is not None else 0.0,
                                'timeframes': '',
                                'event_time': row[5] if len(row) > 5 else None,
                            })
                    
                    return {'gainers': gainers, 'losers': losers}
                finally:
                    cursor.close()
            
            return self._with_connection(_execute_query)
        except Exception as e:
            logger.error("[MarketTickers] Failed to get leaderboard from tickers: %s", e, exc_info=True)
            return {'gainers': [], 'losers': []}
    
    def get_model_portfolio_symbols(self, model_id: int) -> List[str]:
        """获取指定模型的持仓合约symbol列表"""
        try:
            query = f"""
            SELECT DISTINCT symbol
            FROM portfolios
            WHERE model_id = %s AND position_amt != 0
            ORDER BY symbol ASC
            """
            
            def _execute_query(conn):
                cursor = conn.cursor()
                try:
                    cursor.execute(query, (model_id,))
                    rows = cursor.fetchall()
                    symbols = []
                    for row in rows:
                        if isinstance(row, dict):
                            symbols.append(row.get('symbol', ''))
                        elif len(row) > 0:
                            symbols.append(row[0])
                    return symbols
                finally:
                    cursor.close()
            
            return self._with_connection(_execute_query)
        except Exception as e:
            logger.error("[MarketTickers] Failed to get model portfolio symbols: %s", e)
            return []
    
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
    
    def insert_rows(self, table: str, rows: List[List[Any]], column_names: List[str]) -> None:
        """Insert rows into a table."""
        if not rows:
            return
        
        def _execute_insert(conn):
            cursor = conn.cursor()
            try:
                # 构建INSERT语句
                columns_str = ', '.join([f"`{col}`" for col in column_names])
                placeholders = ', '.join(['%s'] * len(column_names))
                sql = f"INSERT INTO `{table}` ({columns_str}) VALUES ({placeholders})"
                
                # 批量插入
                cursor.executemany(sql, rows)
            finally:
                cursor.close()
        
        self._with_connection(_execute_insert)
    
    def ensure_market_ticker_table(self) -> None:
        """Create the 24h market ticker table if it does not exist."""
        from .database_init import DatabaseInitializer
        def _command(sql: str, params: tuple = None) -> Any:
            def _execute_command(conn):
                cursor = conn.cursor()
                try:
                    if params:
                        cursor.execute(sql, params)
                    else:
                        cursor.execute(sql)
                    return cursor.rowcount
                finally:
                    cursor.close()
            return self._with_connection(_execute_command)
        initializer = DatabaseInitializer(_command)
        initializer.ensure_market_ticker_table(self.market_ticker_table)