"""
盯盘 notify 异步队列：收到 notify 信号后落库 SENDING 并入队，由后台线程 FIFO 调用 trade-monitor 推送并落库 trade_notify，成功后置 ENDED。
进程重启时从 DB 加载 SENDING 行重新入队。
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

JOB_KIND_LOOK_NOTIFY = "look_notify"

# 与 LookEngine 配合：主线程在 start_market_look 中注入
_look_engine = None  # type: Optional[Any]
_worker_thread: Optional[threading.Thread] = None
_worker_lock = threading.Lock()
_notify_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()

MAX_NOTIFY_RETRIES = 25


def start_look_notify_worker(look_engine: Any) -> None:
    """启动守护线程，幂等。"""
    global _look_engine, _worker_thread
    with _worker_lock:
        _look_engine = look_engine
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        _worker_thread = threading.Thread(
            target=_worker_loop,
            name="look-notify-worker",
            daemon=True,
        )
        _worker_thread.start()
        logger.info("look notify worker thread started")


def enqueue_look_notify(job: Dict[str, Any]) -> None:
    if job.get("kind") != JOB_KIND_LOOK_NOTIFY:
        job = {**job, "kind": JOB_KIND_LOOK_NOTIFY}
    _notify_queue.put(job)


def hydrate_sending_queue(look_engine: Any) -> None:
    """启动时将 DB 中 SENDING 任务重新入队。"""
    rows = look_engine.market_look_db.list_sending()
    for row in rows:
        job = job_from_sending_row(row)
        if job:
            enqueue_look_notify(job)
            logger.info(
                "re-queued SENDING market_look id=%s",
                row.get("id"),
            )
        else:
            logger.warning(
                "SENDING row missing queue_payload, skip re-queue: id=%s",
                row.get("id"),
            )


def job_from_sending_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sr = row.get("signal_result")
    if not sr:
        return None
    try:
        d = json.loads(sr) if isinstance(sr, str) else sr
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    qp = d.get("queue_payload")
    if not isinstance(qp, dict):
        return None
    rid = row.get("id")
    if not rid:
        return None
    return {
        "kind": JOB_KIND_LOOK_NOTIFY,
        "market_look_id": str(rid),
        "queue_payload": qp,
        "retries": 0,
    }


def _worker_loop() -> None:
    while True:
        try:
            job = _notify_queue.get()
            try:
                _dispatch_job(job)
            except Exception:
                logger.exception("look notify job error: %s", job.get("market_look_id"))
            finally:
                _notify_queue.task_done()
        except Exception:
            logger.exception("look notify worker loop error")


def _dispatch_job(job: Dict[str, Any]) -> None:
    eng = _look_engine
    if eng is None:
        logger.error("look_engine not initialized; cannot process notify job")
        return
    kind = job.get("kind")
    if kind != JOB_KIND_LOOK_NOTIFY:
        logger.warning("unknown notify job kind: %s", kind)
        return
    row_id = job.get("market_look_id")
    qp = job.get("queue_payload")
    if not row_id or not isinstance(qp, dict):
        logger.warning("invalid notify job payload")
        return
    retries = int(job.get("retries") or 0)
    ok = eng.process_notify_queue_payload(str(row_id), qp)
    if ok:
        return
    if retries >= MAX_NOTIFY_RETRIES:
        logger.error(
            "look notify abandoned after %s retries: market_look_id=%s",
            MAX_NOTIFY_RETRIES,
            row_id,
        )
        eng.abandon_notify_queue(str(row_id), "notify_failed_max_retries")
        return
    job["retries"] = retries + 1
    delay = min(5 * (2 ** min(retries, 6)), 120)
    time.sleep(delay)
    _notify_queue.put(job)

