"""
调用 trade-monitor 的事件接口：落库 alert_records 并发送企微。
微信群需配置 alert_types 包含 TRADE_ALERT（交易告警）。
"""

import json
import logging
from typing import Any, Dict, Optional, Tuple

import trade.common.config as app_config

logger = logging.getLogger(__name__)

# 与 wechat_groups.alert_types 匹配：交易类盯盘通知
ALERT_TYPE_TRADE = "TRADE_ALERT"

# 日志中单条 message 最大字符数，避免刷屏
_LOG_MESSAGE_MAX = 4000


def _payload_preview_for_log(payload: Dict[str, Any]) -> str:
    """生成可打印的 JSON 字符串；message 过长时截断并标注原长度。"""
    try:
        out = dict(payload)
        msg = out.get("message")
        if isinstance(msg, str) and len(msg) > _LOG_MESSAGE_MAX:
            out["message"] = msg[:_LOG_MESSAGE_MAX] + f"...(truncated, total_len={len(msg)})"
        return json.dumps(out, ensure_ascii=False, default=str)
    except Exception:
        return str(payload)


def post_event_notify(
    title: str,
    message: str,
    *,
    event_type: str = ALERT_TYPE_TRADE,
    service_name: str = "market_look",
    severity: str = "INFO",
    metadata: Optional[Dict[str, Any]] = None,
    base_url: Optional[str] = None,
) -> Tuple[bool, Optional[int]]:
    """
    POST {base}/api/events/notify

    Returns:
        (success, alert_id): alert_id 为 trade-monitor 落库后的 alert_records.id，失败或未返回时为 None。
    """
    base = (base_url or getattr(app_config, "TRADE_MONITOR_BASE_URL", None) or "").rstrip("/")
    if not base:
        logger.warning("TRADE_MONITOR_BASE_URL 未配置，跳过告警推送")
        return False, None
    url = f"{base}/api/events/notify"
    payload = {
        "eventType": event_type,
        "serviceName": service_name,
        "severity": severity,
        "title": title,
        "message": message,
        "metadata": metadata or {},
    }
    body_len = len(message) if isinstance(message, str) else 0
    logger.info(
        "[trade-monitor] 发送事件通知 -> 服务 aifuturetrade-trade-monitor (HTTP) | POST %s | "
        "Content-Type=application/json | title=%s | message_len=%s | payload_json=%s",
        url,
        title,
        body_len,
        _payload_preview_for_log(payload),
    )
    try:
        import urllib.request
        import urllib.error

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if resp.status >= 400:
                logger.error(
                    "trade-monitor notify failed: status=%s url=%s body=%s",
                    resp.status,
                    url,
                    body[:2000],
                )
                return False, None
            try:
                j = json.loads(body)
                ok = bool(j.get("success", True))
                raw_aid = j.get("alertId")
                alert_id: Optional[int] = None
                if raw_aid is not None:
                    try:
                        alert_id = int(raw_aid)
                    except (TypeError, ValueError):
                        pass
                logger.info(
                    "[trade-monitor] 事件通知响应 OK | url=%s | http_status=%s | success=%s | alertId=%s | response_body=%s",
                    url,
                    resp.status,
                    ok,
                    alert_id,
                    body[:2000] + ("..." if len(body) > 2000 else ""),
                )
                return ok, alert_id
            except Exception:
                logger.info(
                    "[trade-monitor] 事件通知响应（JSON 解析跳过）| url=%s | http_status=%s | raw=%s",
                    url,
                    resp.status,
                    body[:2000],
                )
                return True, None
    except Exception as e:
        logger.error(
            "post_event_notify failed: url=%s | error=%s",
            url,
            e,
            exc_info=True,
        )
        return False, None
