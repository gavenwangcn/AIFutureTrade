"""
trade_notify 表：交易侧通知落库（盯盘等），独立于 alert_records。
"""

import json
import logging
from typing import Any, Callable, Dict, Optional

import trade.common.config as app_config
from .database_basic import create_pooled_db

logger = logging.getLogger(__name__)

NOTIFY_TYPE_LOOK = "LOOK"


class TradeNotifyDatabase:
    def __init__(self, pool=None, table: str = "trade_notify"):
        if pool is None:
            self._pool = create_pooled_db(
                host=app_config.MYSQL_HOST,
                port=app_config.MYSQL_PORT,
                user=app_config.MYSQL_USER,
                password=app_config.MYSQL_PASSWORD,
                database=app_config.MYSQL_DATABASE,
                charset="utf8mb4",
                mincached=2,
                maxconnections=20,
                blocking=True,
            )
        else:
            self._pool = pool
        self.table = table

    def _with_connection(self, func: Callable, *args, **kwargs) -> Any:
        conn = self._pool.connection()
        try:
            return func(conn, *args, **kwargs)
        finally:
            conn.close()

    def insert_look_notify(
        self,
        *,
        market_look_id: Optional[str],
        strategy_id: str,
        strategy_name: Optional[str],
        symbol: str,
        title: str,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        插入一条盯盘类交易通知，并在正文末尾追加 trade_notify 主键便于查询。

        Returns:
            新建行 id
        """

        def _run(conn):
            extra_s: Optional[str] = None
            if extra is not None:
                extra_s = json.dumps(extra, ensure_ascii=False, default=str)

            if extra_s is None:
                sql_ins = f"""
                    INSERT INTO `{self.table}`
                    (notify_type, market_look_id, strategy_id, strategy_name, symbol, title, message, extra_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NULL)
                """
                params = (
                    NOTIFY_TYPE_LOOK,
                    market_look_id,
                    strategy_id,
                    strategy_name,
                    symbol,
                    title,
                    message,
                )
            else:
                sql_ins = f"""
                    INSERT INTO `{self.table}`
                    (notify_type, market_look_id, strategy_id, strategy_name, symbol, title, message, extra_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, CAST(%s AS JSON))
                """
                params = (
                    NOTIFY_TYPE_LOOK,
                    market_look_id,
                    strategy_id,
                    strategy_name,
                    symbol,
                    title,
                    message,
                    extra_s,
                )

            cur = conn.cursor()
            try:
                cur.execute(sql_ins, params)
                nid = cur.lastrowid
                if not nid:
                    conn.rollback()
                    raise RuntimeError("trade_notify insert returned no lastrowid")
                suffix = f"\n\n交易通知ID (trade_notify.id): {nid}"
                sql_up = f"""
                    UPDATE `{self.table}`
                    SET message = CONCAT(message, %s)
                    WHERE id = %s
                """
                cur.execute(sql_up, (suffix, nid))
                conn.commit()
                return int(nid)
            except Exception:
                conn.rollback()
                raise
            finally:
                cur.close()

        return self._with_connection(_run)
