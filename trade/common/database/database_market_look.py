"""
market_look 表访问：实时盯盘任务
"""

import logging
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import pymysql
import trade.common.config as app_config
from .database_basic import create_pooled_db

logger = logging.getLogger(__name__)


def _is_transient_mysql_error(exc: BaseException) -> bool:
    """长间隔轮询时连接可能被服务端回收，池内连接失效会导致 InterfaceError / OperationalError 等，可重试。"""
    if isinstance(exc, pymysql.err.InterfaceError):
        return True
    if isinstance(exc, pymysql.err.OperationalError) and exc.args:
        code = exc.args[0]
        if code in (2006, 2013, 2003, 2014, 2055):
            return True
    if isinstance(exc, pymysql.err.InternalError) and exc.args:
        msg = str(exc.args[1]).lower() if len(exc.args) > 1 else ""
        if "packet sequence" in msg or "lost connection" in msg:
            return True
    err_name = type(exc).__name__.lower()
    err_text = str(exc).lower()
    if any(k in err_text for k in ("gone away", "broken pipe", "reset by peer", "read of closed file")):
        return True
    if any(k in err_name for k in ("interfaceerror", "timeouterror", "connectionerror")):
        return True
    return False


def _discard_pool_connection(conn) -> None:
    if not conn:
        return
    try:
        conn.rollback()
    except Exception:
        pass
    try:
        conn.close()
    except Exception:
        pass

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
        max_retries = 3
        retry_delay = 0.5
        for attempt in range(max_retries):
            conn = None
            try:
                conn = self._pool.connection()
                return func(conn, *args, **kwargs)
            except Exception as e:
                _discard_pool_connection(conn)
                conn = None
                if attempt < max_retries - 1 and _is_transient_mysql_error(e):
                    wait = retry_delay * (2**attempt)
                    logger.warning(
                        "[MarketLookDatabase] transient MySQL error (attempt %s/%s): %s: %s. retry in %.2fs",
                        attempt + 1,
                        max_retries,
                        type(e).__name__,
                        e,
                        wait,
                    )
                    time.sleep(wait)
                    continue
                raise
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass

    def list_running(self) -> List[Dict]:
        """执行中任务"""

        def _run(conn):
            from pymysql import cursors

            sql = f"""
                SELECT id, symbol, strategy_id, strategy_name, execution_status, signal_result,
                       detail_summary, end_log, started_at, ended_at, created_at, updated_at
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
                       detail_summary, end_log, started_at, ended_at, created_at, updated_at
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

    def get_by_id(self, row_id: str) -> Optional[Dict]:
        """按主键取单行（用于合并更新 signal_result 等）。"""

        def _run(conn):
            from pymysql import cursors

            sql = f"""
                SELECT id, symbol, strategy_id, strategy_name, execution_status, signal_result,
                       detail_summary, end_log, started_at, ended_at, created_at, updated_at
                FROM `{self.table}`
                WHERE id = %s
                LIMIT 1
            """
            cur = conn.cursor(cursors.DictCursor)
            try:
                cur.execute(sql, (row_id,))
                r = cur.fetchone()
                return dict(r) if r else None
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
        end_log: Optional[str] = None,
    ) -> None:
        """更新执行状态；任务结束时可写入 end_log（非策略信号类结束说明）。"""

        def _run(conn):
            sets = ["execution_status = %s"]
            params: List[Any] = [status]

            if ended_at is not None:
                sets.append("ended_at = %s")
                params.append(ended_at)
            elif status == EXECUTION_ENDED:
                sets.append("ended_at = NOW()")
            else:
                sets.append("ended_at = %s")
                params.append(ENDED_AT_NOT_FINISHED_PLACEHOLDER)

            if end_log is not None:
                sets.append("end_log = %s")
                params.append(end_log)

            sets.append("updated_at = CURRENT_TIMESTAMP")
            params.append(row_id)
            sql = f"""
                UPDATE `{self.table}`
                SET {", ".join(sets)}
                WHERE id = %s
            """
            cur = conn.cursor()
            try:
                cur.execute(sql, tuple(params))
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
