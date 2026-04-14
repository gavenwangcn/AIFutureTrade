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
                logger.error("trade-monitor notify failed: %s %s", resp.status, body)
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
                return ok, alert_id
            except Exception:
                return True, None
    except Exception as e:
        logger.error("post_event_notify failed: %s", e)
        return False, None
