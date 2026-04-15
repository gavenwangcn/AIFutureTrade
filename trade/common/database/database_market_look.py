"""
market_look 表访问：实时盯盘任务
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import trade.common.config as app_config
from .database_basic import create_pooled_db

logger = logging.getLogger(__name__)

EXECUTION_RUNNING = "RUNNING"
EXECUTION_SENDING = "SENDING"
EXECUTION_ENDED = "ENDED"

# 与 Java MarketLookDO.ENDED_AT_NOT_FINISHED_PLACEHOLDER 一致，满足 ended_at NOT NULL
ENDED_AT_NOT_FINISHED_PLACEHOLDER = datetime(2099, 12, 31, 23, 59, 59)


class MarketLookDatabase:
    def __init__(self, pool=None):
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
        self.table = "market_look"

    def _with_connection(self, func: Callable, *args, **kwargs) -> Any:
        conn = self._pool.connection()
        try:
            return func(conn, *args, **kwargs)
        finally:
            conn.close()

    def list_running(self) -> List[Dict]:
        """执行中任务"""

        def _run(conn):
            from pymysql import cursors

            sql = f"""
                SELECT id, symbol, strategy_id, strategy_name, execution_status, signal_result,
                       detail_summary, started_at, ended_at, created_at, updated_at
                FROM `{self.table}`
                WHERE execution_status = %s
                ORDER BY started_at ASC
            """
            cur = conn.cursor(cursors.DictCursor)
            try:
                cur.execute(sql, (EXECUTION_RUNNING,))
                return [dict(r) for r in cur.fetchall()]
            finally:
                cur.close()

        return self._with_connection(_run)

    def list_sending(self) -> List[Dict]:
        """通知队列中（异步发送中）的任务，用于进程重启后恢复队列。"""

        def _run(conn):
            from pymysql import cursors

            sql = f"""
                SELECT id, symbol, strategy_id, strategy_name, execution_status, signal_result,
                       detail_summary, started_at, ended_at, created_at, updated_at
                FROM `{self.table}`
                WHERE execution_status = %s
                ORDER BY updated_at ASC
            """
            cur = conn.cursor(cursors.DictCursor)
            try:
                cur.execute(sql, (EXECUTION_SENDING,))
                return [dict(r) for r in cur.fetchall()]
            finally:
                cur.close()

        return self._with_connection(_run)

    def update_signal_result(self, row_id: str, signal_result: str) -> None:
        def _run(conn):
            sql = f"""
                UPDATE `{self.table}`
                SET signal_result = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """
            cur = conn.cursor()
            try:
                cur.execute(sql, (signal_result, row_id))
                conn.commit()
            finally:
                cur.close()

        self._with_connection(_run)

    def update_status(
        self,
        row_id: str,
        status: str,
        ended_at: Optional[datetime] = None,
    ) -> None:
        def _run(conn):
            if ended_at is not None:
                sql = f"""
                    UPDATE `{self.table}`
                    SET execution_status = %s, ended_at = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """
                params = (status, ended_at, row_id)
            elif status == EXECUTION_ENDED:
                sql = f"""
                    UPDATE `{self.table}`
                    SET execution_status = %s, ended_at = NOW(), updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """
                params = (status, row_id)
            else:
                sql = f"""
                    UPDATE `{self.table}`
                    SET execution_status = %s, ended_at = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """
                params = (status, ENDED_AT_NOT_FINISHED_PLACEHOLDER, row_id)
            cur = conn.cursor()
            try:
                cur.execute(sql, params)
                conn.commit()
            finally:
                cur.close()

        self._with_connection(_run)

    def insert_row(
        self,
        symbol: str,
        strategy_id: str,
        strategy_name: Optional[str] = None,
        execution_status: str = EXECUTION_RUNNING,
        started_at: Optional[datetime] = None,
        row_id: Optional[str] = None,
        detail_summary: Optional[str] = None,
    ) -> str:
        rid = row_id or str(uuid.uuid4())
        st = started_at or datetime.now()

        def _run(conn):
            sql = f"""
                INSERT INTO `{self.table}`
                (id, symbol, strategy_id, strategy_name, execution_status, signal_result, detail_summary, started_at, ended_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cur = conn.cursor()
            try:
                cur.execute(
                    sql,
                    (
                        rid,
                        symbol,
                        strategy_id,
                        strategy_name,
                        execution_status,
                        None,
                        detail_summary,
                        st,
                        ENDED_AT_NOT_FINISHED_PLACEHOLDER
                        if execution_status == EXECUTION_RUNNING
                        else st,
                    ),
                )
                conn.commit()
            finally:
                cur.close()

        self._with_connection(_run)
        return rid
