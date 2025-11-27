"""
UTC8 市场行情数据转换处理器

功能：
- 将24_market_tickers表中的24小时滚动窗口数据转换为UTC 8点固定数据
- 支持多线程批量处理
- 定期执行数据转换任务

数据转换逻辑：
1. 24小时滚动窗口数据：以requestTime为基准，向前追溯24小时
2. 转换为UTC 8点固定数据：将滚动窗口数据转换为固定UTC 8点（00:00:00）到下一个UTC 8点（23:59:59）的24小时数据
3. 对于每个UTC 8点周期，聚合该周期内的所有数据，取最新的stats_close_time对应的数据
"""
from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta, date
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict

import config as app_config
from database_clickhouse import ClickHouseDatabase

logger = logging.getLogger(__name__)

# UTC 8点时间偏移
UTC8_OFFSET = timezone(timedelta(hours=8))


class UTC8TickerProcessor:
    """UTC8 市场行情数据转换处理器"""
    
    def __init__(self):
        """初始化处理器"""
        self.db: Optional[ClickHouseDatabase] = None
        self.source_table = getattr(app_config, 'CLICKHOUSE_MARKET_TICKER_TABLE', '24_market_tickers')
        self.target_table = getattr(app_config, 'CLICKHOUSE_UTC8_TICKER_TABLE', '24_market_tickers_utc8')
        self.batch_size = getattr(app_config, 'UTC8_BATCH_SIZE', 1000)
        self.thread_count = getattr(app_config, 'UTC8_THREAD_COUNT', 4)
        self.lookback_hours = getattr(app_config, 'UTC8_LOOKBACK_HOURS', 48)
        
    def ensure_target_table(self) -> None:
        """确保目标表存在"""
        if not self.db:
            self.db = ClickHouseDatabase(auto_init_tables=False)
        
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {self.target_table} (
            utc8_date Date,
            utc8_period_start DateTime,
            utc8_period_end DateTime,
            symbol String,
            price_change Float64,
            price_change_percent Float64,
            side String,
            change_percent_text String,
            average_price Float64,
            last_price Float64,
            last_trade_volume Float64,
            open_price Float64,
            high_price Float64,
            low_price Float64,
            base_volume Float64,
            quote_volume Float64,
            stats_open_time DateTime,
            stats_close_time DateTime,
            first_trade_id UInt64,
            last_trade_id UInt64,
            trade_count UInt64,
            event_time DateTime,
            ingestion_time DateTime DEFAULT now(),
            created_at DateTime DEFAULT now()
        )
        ENGINE = MergeTree
        ORDER BY (utc8_date, symbol, stats_close_time)
        """
        self.db.command(ddl)
        logger.info(f"[UTC8 Processor] 确保目标表存在: {self.target_table}")
    
    def get_utc8_period(self, dt: datetime) -> Tuple[datetime, datetime, date]:
        """
        根据时间戳计算所属的UTC 8点周期
        
        UTC 8点周期定义：
        - 从UTC 8:00:00开始，到下一个UTC 8:00:00结束（即UTC 8:00:00到UTC 7:59:59）
        - 例如：2025-11-27 08:00:00 UTC 到 2025-11-28 07:59:59 UTC
        
        Args:
            dt: 时间戳（UTC时间）
            
        Returns:
            (period_start, period_end, utc8_date)
            - period_start: UTC 8点周期的开始时间（UTC 8:00:00）
            - period_end: UTC 8点周期的结束时间（下一个UTC 8:00:00 - 1秒）
            - utc8_date: UTC 8点日期对象（date类型），基于UTC 8时区的日期
        """
        # 转换为UTC 8时区
        dt_utc8 = dt.astimezone(UTC8_OFFSET)
        
        # 获取UTC 8点的日期（YYYY-MM-DD）
        # 如果当前时间在UTC 8:00:00之前，则属于前一天的UTC 8点周期
        # 如果当前时间在UTC 8:00:00之后，则属于当天的UTC 8点周期
        if dt_utc8.hour < 8:
            # 在UTC 8点之前，属于前一天的UTC 8点周期
            utc8_date = (dt_utc8.date() - timedelta(days=1))
        else:
            # 在UTC 8点之后，属于当天的UTC 8点周期
            utc8_date = dt_utc8.date()
        
        # 计算UTC 8点周期的开始时间（UTC 8:00:00）
        period_start_utc8 = datetime.combine(utc8_date, datetime.min.time().replace(hour=8))
        period_start = period_start_utc8.replace(tzinfo=UTC8_OFFSET).astimezone(timezone.utc)
        
        # 计算UTC 8点周期的结束时间（下一个UTC 8:00:00 - 1秒）
        period_end_utc8 = period_start_utc8 + timedelta(days=1) - timedelta(seconds=1)
        period_end = period_end_utc8.replace(tzinfo=UTC8_OFFSET).astimezone(timezone.utc)
        
        return period_start, period_end, utc8_date
    
    def query_source_data(
        self, 
        lookback_hours: int = 48,
        symbols: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        查询源表中的数据
        
        Args:
            lookback_hours: 查询最近N小时的数据
            symbols: 可选的交易对列表，如果指定则只查询这些交易对
            
        Returns:
            数据列表
        """
        if not self.db:
            self.db = ClickHouseDatabase(auto_init_tables=False)
        
        # 计算时间阈值
        time_threshold = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        time_threshold_str = time_threshold.strftime('%Y-%m-%d %H:%M:%S')
        
        # 构建查询SQL
        symbol_filter = ""
        if symbols:
            symbols_str = "', '".join(symbols)
            symbol_filter = f"AND symbol IN ('{symbols_str}')"
        
        query = f"""
        SELECT 
            event_time,
            symbol,
            price_change,
            price_change_percent,
            side,
            change_percent_text,
            average_price,
            last_price,
            last_trade_volume,
            open_price,
            high_price,
            low_price,
            base_volume,
            quote_volume,
            stats_open_time,
            stats_close_time,
            first_trade_id,
            last_trade_id,
            trade_count,
            ingestion_time
        FROM {self.source_table}
        WHERE ingestion_time > '{time_threshold_str}'
        {symbol_filter}
        ORDER BY symbol, stats_close_time DESC
        """
        
        def _execute_query(client):
            return client.query(query)
        
        logger.info(f"[UTC8 Processor] 查询源数据: lookback_hours={lookback_hours}, symbols={len(symbols) if symbols else 'all'}")
        result = self.db._with_connection(_execute_query)
        
        # 转换为字典列表
        columns = [
            "event_time", "symbol", "price_change", "price_change_percent", "side",
            "change_percent_text", "average_price", "last_price", "last_trade_volume",
            "open_price", "high_price", "low_price", "base_volume", "quote_volume",
            "stats_open_time", "stats_close_time", "first_trade_id", "last_trade_id",
            "trade_count", "ingestion_time"
        ]
        
        rows = []
        for row in result.result_rows:
            row_dict = dict(zip(columns, row))
            rows.append(row_dict)
        
        logger.info(f"[UTC8 Processor] 查询完成，共 {len(rows)} 条数据")
        return rows
    
    def convert_to_utc8_data(self, source_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        将源数据转换为UTC 8点固定数据
        
        优化后的转换逻辑：
        1. 根据stats_close_time确定所属的UTC 8点周期
           - UTC 8点周期：从UTC 8:00:00到下一个UTC 8:00:00（即UTC 8:00:00到UTC 7:59:59）
        2. 对于每个(utc8_period, symbol)组合：
           a. 找到UTC8周期结束时（或最接近）的数据作为周期结束数据
           b. 找到UTC8周期开始时（或最接近）的数据作为周期开始数据
           c. 基于周期开始和结束的价格，重新计算price_change_percent
        3. 生成UTC 8点固定数据
        
        Args:
            source_rows: 源数据列表
            
        Returns:
            转换后的UTC 8点数据列表
        """
        logger.info(f"[UTC8 Processor] 开始转换数据，源数据量: {len(source_rows)}")
        
        # 按symbol分组，便于查找每个symbol在不同时间点的数据
        symbol_data: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in source_rows:
            try:
                symbol = row.get('symbol', '')
                stats_close_time = row.get('stats_close_time')
                if not symbol or not stats_close_time:
                    continue
                
                stats_close_dt = self._to_datetime(stats_close_time)
                if not stats_close_dt:
                    continue
                
                symbol_data[symbol].append({
                    'stats_close_time': stats_close_dt,
                    'data': row
                })
            except Exception as e:
                logger.warning(f"[UTC8 Processor] 处理数据行失败: {e}, row: {row.get('symbol', 'N/A')}")
                continue
        
        # 对每个symbol的数据按时间排序
        for symbol in symbol_data:
            symbol_data[symbol].sort(key=lambda x: x['stats_close_time'])
        
        # 按(utc8_period, symbol)分组，计算UTC8周期数据
        grouped_data: Dict[Tuple[str, str], Dict[str, Any]] = {}
        
        for symbol, rows in symbol_data.items():
            for row_info in rows:
                try:
                    stats_close_dt = row_info['stats_close_time']
                    row = row_info['data']
                    
                    # 计算UTC 8点周期
                    period_start, period_end, utc8_date = self.get_utc8_period(stats_close_dt)
                    
                    # 分组键：(utc8_date, symbol) - 使用date对象
                    group_key = (utc8_date, symbol)
                    
                    if group_key not in grouped_data:
                        grouped_data[group_key] = {
                            'utc8_date': utc8_date,
                            'utc8_period_start': period_start,
                            'utc8_period_end': period_end,
                            'period_end_data': row,  # 周期结束时的数据
                            'period_end_time': stats_close_dt,
                            'period_start_data': None,  # 周期开始时的数据（待查找）
                            'period_start_time': None,
                        }
                    else:
                        # 更新周期结束数据（取最接近周期结束的数据）
                        existing_end_time = grouped_data[group_key]['period_end_time']
                        if stats_close_dt > existing_end_time and stats_close_dt <= period_end:
                            grouped_data[group_key]['period_end_data'] = row
                            grouped_data[group_key]['period_end_time'] = stats_close_dt
                except Exception as e:
                    logger.warning(f"[UTC8 Processor] 处理数据行失败: {e}, symbol={symbol}")
                    continue
        
        # 为每个分组查找周期开始时的数据
        for group_key, group_data in grouped_data.items():
            symbol = group_key[1]
            period_start = group_data['utc8_period_start']
            
            # 在该symbol的所有数据中，查找最接近周期开始时间的数据
            best_start_data = None
            best_start_time = None
            min_time_diff = float('inf')
            
            for row_info in symbol_data.get(symbol, []):
                stats_close_dt = row_info['stats_close_time']
                # 查找在周期开始时间附近的数据（允许前后1小时的范围）
                if period_start - timedelta(hours=1) <= stats_close_dt <= period_start + timedelta(hours=1):
                    time_diff = abs((stats_close_dt - period_start).total_seconds())
                    if time_diff < min_time_diff:
                        min_time_diff = time_diff
                        best_start_data = row_info['data']
                        best_start_time = stats_close_dt
            
            if best_start_data:
                group_data['period_start_data'] = best_start_data
                group_data['period_start_time'] = best_start_time
        
        # 转换为输出格式，重新计算price_change_percent
        result = []
        for group_key, group_data in grouped_data.items():
            period_end_row = group_data['period_end_data']
            period_start_row = group_data.get('period_start_data')
            
            # 获取周期开始和结束时的价格
            period_start_price = None
            if period_start_row:
                # 优先使用last_price（如果可用），否则使用open_price
                period_start_price = period_start_row.get('last_price') or period_start_row.get('open_price', 0)
            else:
                # 如果没有找到周期开始数据，使用周期结束数据的open_price作为近似值
                period_start_price = period_end_row.get('open_price', 0)
                logger.debug(
                    f"[UTC8 Processor] 未找到周期开始数据，使用近似值: symbol={group_key[1]}, utc8_date={group_key[0]}"
                )
            
            period_end_price = period_end_row.get('last_price', 0)
            
            # 重新计算price_change和price_change_percent
            if period_start_price and period_start_price > 0:
                price_change = period_end_price - period_start_price
                price_change_percent = (price_change / period_start_price) * 100.0
            else:
                # 如果无法计算，使用原始值
                price_change = period_end_row.get('price_change', 0)
                price_change_percent = period_end_row.get('price_change_percent', 0)
                logger.warning(
                    f"[UTC8 Processor] 无法重新计算price_change_percent，使用原始值: symbol={group_key[1]}, utc8_date={group_key[0]}"
                )
            
            # 确定side和change_percent_text
            side = "loser" if price_change_percent < 0 else "gainer"
            change_percent_text = f"{price_change_percent:.2f}%"
            
            result.append({
                'utc8_date': group_data['utc8_date'],
                'utc8_period_start': group_data['utc8_period_start'],
                'utc8_period_end': group_data['utc8_period_end'],
                'symbol': period_end_row.get('symbol', ''),
                'price_change': price_change,
                'price_change_percent': price_change_percent,
                'side': side,
                'change_percent_text': change_percent_text,
                'average_price': period_end_row.get('average_price', 0),
                'last_price': period_end_price,
                'last_trade_volume': period_end_row.get('last_trade_volume', 0),
                'open_price': period_start_price,  # UTC8周期开始时的价格
                'high_price': period_end_row.get('high_price', 0),
                'low_price': period_end_row.get('low_price', 0),
                'base_volume': period_end_row.get('base_volume', 0),
                'quote_volume': period_end_row.get('quote_volume', 0),
                'stats_open_time': self._to_datetime(period_end_row.get('stats_open_time')),
                'stats_close_time': group_data['period_end_time'],
                'first_trade_id': period_end_row.get('first_trade_id', 0),
                'last_trade_id': period_end_row.get('last_trade_id', 0),
                'trade_count': period_end_row.get('trade_count', 0),
                'event_time': self._to_datetime(period_end_row.get('event_time')),
                'ingestion_time': self._to_datetime(period_end_row.get('ingestion_time')) or datetime.now(timezone.utc)
            })
        
        logger.info(f"[UTC8 Processor] 转换完成，生成 {len(result)} 条UTC8数据（已重新计算price_change_percent）")
        return result
    
    def _to_datetime(self, value: Any) -> Optional[datetime]:
        """将值转换为datetime对象"""
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        try:
            if isinstance(value, (int, float)):
                # 毫秒时间戳
                if value > 1e10:
                    value = value / 1000.0
                return datetime.fromtimestamp(value, tz=timezone.utc)
            if isinstance(value, str):
                # 尝试解析字符串
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S.%f']:
                    try:
                        dt = datetime.strptime(value, fmt)
                        return dt.replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
        except Exception:
            pass
        return None
    
    def upsert_utc8_data(self, utc8_rows: List[Dict[str, Any]]) -> None:
        """
        插入或更新UTC8数据到目标表
        
        使用REPLACE策略：对于相同的(utc8_date, symbol)，删除旧数据后插入新数据
        
        Args:
            utc8_rows: UTC8数据列表
        """
        if not utc8_rows:
            return
        
        if not self.db:
            self.db = ClickHouseDatabase(auto_init_tables=False)
        
        # 按(utc8_date, symbol)分组，准备删除旧数据
        date_symbol_pairs = set()
        for row in utc8_rows:
            utc8_date = row.get('utc8_date')
            symbol = row.get('symbol')
            if utc8_date and symbol:
                date_symbol_pairs.add((utc8_date, symbol))
        
        # 删除旧数据（使用ALTER TABLE DELETE）
        if date_symbol_pairs:
            logger.info(f"[UTC8 Processor] 准备删除 {len(date_symbol_pairs)} 个(utc8_date, symbol)组合的旧数据...")
            for utc8_date, symbol in date_symbol_pairs:
                try:
                    # 将date对象转换为字符串用于SQL查询
                    utc8_date_str = utc8_date.strftime('%Y-%m-%d') if hasattr(utc8_date, 'strftime') else str(utc8_date)
                    delete_sql = f"""
                    ALTER TABLE {self.target_table}
                    DELETE WHERE utc8_date = '{utc8_date_str}' AND symbol = '{symbol}'
                    """
                    self.db.command(delete_sql)
                except Exception as e:
                    logger.warning(f"[UTC8 Processor] 删除旧数据失败: utc8_date={utc8_date}, symbol={symbol}, error={e}")
        
        # 准备插入数据
        column_names = [
            "utc8_date", "utc8_period_start", "utc8_period_end", "symbol",
            "price_change", "price_change_percent", "side", "change_percent_text",
            "average_price", "last_price", "last_trade_volume",
            "open_price", "high_price", "low_price",
            "base_volume", "quote_volume",
            "stats_open_time", "stats_close_time",
            "first_trade_id", "last_trade_id", "trade_count",
            "event_time", "ingestion_time"
        ]
        
        prepared_rows = []
        for row in utc8_rows:
            try:
                # 确保utc8_date是date对象
                utc8_date = row.get('utc8_date')
                if isinstance(utc8_date, str):
                    # 如果是字符串，转换为date对象
                    utc8_date = datetime.strptime(utc8_date, '%Y-%m-%d').date()
                elif isinstance(utc8_date, datetime):
                    # 如果是datetime对象，提取date部分
                    utc8_date = utc8_date.date()
                elif not isinstance(utc8_date, date):
                    # 如果既不是字符串也不是date对象，尝试转换
                    if hasattr(utc8_date, 'date'):
                        utc8_date = utc8_date.date()
                    else:
                        logger.warning(f"[UTC8 Processor] 无法转换utc8_date: {utc8_date}, type={type(utc8_date)}")
                        continue
                
                row_data = [
                    utc8_date,  # 使用转换后的date对象
                    row.get('utc8_period_start'),
                    row.get('utc8_period_end'),
                    row.get('symbol', ''),
                    float(row.get('price_change', 0)),
                    float(row.get('price_change_percent', 0)),
                    row.get('side', 'neutral'),
                    row.get('change_percent_text', '0.00%'),
                    float(row.get('average_price', 0)),
                    float(row.get('last_price', 0)),
                    float(row.get('last_trade_volume', 0)),
                    float(row.get('open_price', 0)),
                    float(row.get('high_price', 0)),
                    float(row.get('low_price', 0)),
                    float(row.get('base_volume', 0)),
                    float(row.get('quote_volume', 0)),
                    row.get('stats_open_time'),
                    row.get('stats_close_time'),
                    int(row.get('first_trade_id', 0)),
                    int(row.get('last_trade_id', 0)),
                    int(row.get('trade_count', 0)),
                    row.get('event_time'),
                    row.get('ingestion_time') or datetime.now(timezone.utc)
                ]
                prepared_rows.append(row_data)
            except Exception as e:
                logger.warning(f"[UTC8 Processor] 准备数据行失败: {e}, symbol={row.get('symbol', 'N/A')}")
                continue
        
        # 批量插入
        if prepared_rows:
            logger.info(f"[UTC8 Processor] 准备插入 {len(prepared_rows)} 条数据到 {self.target_table}...")
            self.db.insert_rows(self.target_table, prepared_rows, column_names)
            logger.info(f"[UTC8 Processor] ✅ 数据插入完成")
        else:
            logger.warning(f"[UTC8 Processor] 没有有效数据可插入")
    
    def process_symbols_batch(
        self, 
        symbols: List[str],
        lookback_hours: int
    ) -> int:
        """
        批量处理指定交易对的数据
        
        Args:
            symbols: 交易对列表
            lookback_hours: 查询最近N小时的数据
            
        Returns:
            处理的数据条数
        """
        try:
            # 查询源数据
            source_rows = self.query_source_data(lookback_hours=lookback_hours, symbols=symbols)
            
            if not source_rows:
                logger.debug(f"[UTC8 Processor] 批次 {len(symbols)} 个交易对，无数据")
                return 0
            
            # 转换为UTC8数据
            utc8_rows = self.convert_to_utc8_data(source_rows)
            
            if not utc8_rows:
                logger.debug(f"[UTC8 Processor] 批次 {len(symbols)} 个交易对，转换后无数据")
                return 0
            
            # 写入目标表
            self.upsert_utc8_data(utc8_rows)
            
            logger.info(f"[UTC8 Processor] 批次处理完成: {len(symbols)} 个交易对, {len(utc8_rows)} 条UTC8数据")
            return len(utc8_rows)
        except Exception as e:
            logger.error(f"[UTC8 Processor] 批次处理失败: {e}", exc_info=True)
            return 0
    
    def process_all_data(self, lookback_hours: Optional[int] = None) -> Dict[str, Any]:
        """
        处理所有数据（多线程批量处理）
        
        Args:
            lookback_hours: 查询最近N小时的数据，如果为None则使用配置值
            
        Returns:
            处理结果统计
        """
        if not self.db:
            self.db = ClickHouseDatabase(auto_init_tables=False)
        
        # 确保目标表存在
        self.ensure_target_table()
        
        # 清理旧数据（只保留最近2天的数据）
        retention_days = getattr(app_config, 'MARKET_TICKER_RETENTION_DAYS', 2)
        try:
            self.db.cleanup_old_market_tickers(retention_days=retention_days)
        except Exception as e:
            logger.warning(f"[UTC8 Processor] 清理旧数据失败: {e}")
        
        lookback = lookback_hours or self.lookback_hours
        
        logger.info(f"[UTC8 Processor] ========== 开始处理所有数据 ==========")
        logger.info(f"[UTC8 Processor] 配置: lookback_hours={lookback}, batch_size={self.batch_size}, thread_count={self.thread_count}")
        
        start_time = datetime.now()
        
        # 1. 获取所有唯一的交易对
        logger.info(f"[UTC8 Processor] [步骤1] 获取所有交易对...")
        time_threshold = datetime.now(timezone.utc) - timedelta(hours=lookback)
        time_threshold_str = time_threshold.strftime('%Y-%m-%d %H:%M:%S')
        query_symbols = f"""
        SELECT DISTINCT symbol
        FROM {self.source_table}
        WHERE ingestion_time > '{time_threshold_str}'
        ORDER BY symbol
        """
        
        def _execute_query(client):
            return client.query(query_symbols)
        
        result = self.db._with_connection(_execute_query)
        all_symbols = [row[0] for row in result.result_rows if row[0]]
        
        logger.info(f"[UTC8 Processor] [步骤1] 获取到 {len(all_symbols)} 个唯一交易对")
        
        if not all_symbols:
            logger.warning(f"[UTC8 Processor] 没有找到任何交易对数据")
            return {
                'success': False,
                'total_symbols': 0,
                'processed_rows': 0,
                'duration_seconds': 0
            }
        
        # 2. 将交易对分批
        batches = []
        for i in range(0, len(all_symbols), self.batch_size):
            batches.append(all_symbols[i:i + self.batch_size])
        
        logger.info(f"[UTC8 Processor] [步骤2] 分为 {len(batches)} 个批次，每批最多 {self.batch_size} 个交易对")
        
        # 3. 多线程批量处理
        total_processed = 0
        successful_batches = 0
        failed_batches = 0
        
        logger.info(f"[UTC8 Processor] [步骤3] 开始多线程批量处理（{self.thread_count} 个线程）...")
        
        with ThreadPoolExecutor(max_workers=self.thread_count) as executor:
            futures = []
            for batch_idx, batch_symbols in enumerate(batches, 1):
                future = executor.submit(
                    self.process_symbols_batch,
                    batch_symbols,
                    lookback
                )
                futures.append((batch_idx, len(batches), future, batch_symbols))
            
            # 等待所有批次完成
            for batch_idx, total_batches, future, batch_symbols in futures:
                try:
                    processed_count = future.result(timeout=300)  # 5分钟超时
                    total_processed += processed_count
                    successful_batches += 1
                    logger.info(f"[UTC8 Processor] [批次 {batch_idx}/{total_batches}] 完成: {len(batch_symbols)} 个交易对, {processed_count} 条数据")
                except Exception as e:
                    failed_batches += 1
                    logger.error(f"[UTC8 Processor] [批次 {batch_idx}/{total_batches}] 失败: {e}", exc_info=True)
        
        duration = (datetime.now() - start_time).total_seconds()
        
        logger.info(f"[UTC8 Processor] ========== 处理完成 ==========")
        logger.info(f"[UTC8 Processor] 统计: 总交易对数={len(all_symbols)}, 成功批次={successful_batches}, 失败批次={failed_batches}")
        logger.info(f"[UTC8 Processor] 统计: 处理数据量={total_processed}, 耗时={duration:.2f}秒")
        
        return {
            'success': True,
            'total_symbols': len(all_symbols),
            'total_batches': len(batches),
            'successful_batches': successful_batches,
            'failed_batches': failed_batches,
            'processed_rows': total_processed,
            'duration_seconds': duration
        }


async def run_utc8_processor(interval_seconds: Optional[int] = None) -> None:
    """
    运行UTC8数据转换处理器（异步）
    
    Args:
        interval_seconds: 处理间隔（秒），如果为None则只执行一次
    """
    processor = UTC8TickerProcessor()
    
    if interval_seconds:
        logger.info(f"[UTC8 Processor] 启动定期处理任务，间隔: {interval_seconds} 秒")
        while True:
            try:
                processor.process_all_data()
            except Exception as e:
                logger.error(f"[UTC8 Processor] 处理失败: {e}", exc_info=True)
            
            await asyncio.sleep(interval_seconds)
    else:
        logger.info(f"[UTC8 Processor] 执行单次处理任务")
        processor.process_all_data()


if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=getattr(logging, app_config.LOG_LEVEL, logging.INFO),
        format=app_config.LOG_FORMAT,
        datefmt=app_config.LOG_DATE_FORMAT,
    )
    
    interval = getattr(app_config, 'UTC8_PROCESS_INTERVAL', 300)
    
    try:
        asyncio.run(run_utc8_processor(interval_seconds=interval))
    except KeyboardInterrupt:
        logger.info("[UTC8 Processor] 被用户中断")
        sys.exit(0)

