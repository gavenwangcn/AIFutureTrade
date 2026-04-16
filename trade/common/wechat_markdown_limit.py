"""
企业微信机器人 markdown.content 单条上限 4096 字符（errcode=40058）。
与 trade-monitor `WeChatMarkdownLimiter`、`WeChatNotificationServiceImpl.buildMarkdownContent`、
`AlertServiceImpl` 追加「告警记录ID」行的拼接顺序对齐，对 Python 侧发送的 message 做兜底截断。
"""

from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# 与 com.aifuturetrade.trademonitor.util.WeChatMarkdownLimiter.MAX_MARKDOWN_CHARS 一致
MAX_MARKDOWN_CHARS = 4096

# Java 追加："\n\n告警记录ID: " + alertId + "（trade-monitor.alert_records）"
# 告警 ID 按最坏位数预留（bigint）
_WORST_ALERT_ID_STR = "9" * 22


def _java_alert_record_suffix_len() -> int:
    s = "\n\n告警记录ID: " + _WORST_ALERT_ID_STR + "（trade-monitor.alert_records）"
    return len(s)


def build_markdown_header_like_java(title: str) -> str:
    """与 WeChatNotificationServiceImpl.buildMarkdownContent 中标题、时间行一致。"""
    mt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"### {title}\n\n> **时间**: {mt}\n\n"


def clamp_notify_title_and_message_for_wechat(title: str, message: str) -> tuple[str, str]:
    """
    约束发往 trade-monitor 的 title、message：使 Java 拼接为
    markdown = header + message + alert_suffix 后长度不超过 4096。

    超长则截断 title（极少）或 message，并记录日志。
    """
    if not isinstance(message, str):
        message = "" if message is None else str(message)
    if not isinstance(title, str):
        title = "" if title is None else str(title)

    suffix_budget = _java_alert_record_suffix_len()
    title_out = title

    def _budget() -> tuple[str, int]:
        h = build_markdown_header_like_java(title_out)
        mb = MAX_MARKDOWN_CHARS - len(h) - suffix_budget
        return h, mb

    header, max_body = _budget()
    if max_body < 80:
        logger.warning(
            "[wechat_markdown_limit] 标题过长，截短 title 以适配企微 %s 字符上限",
            MAX_MARKDOWN_CHARS,
        )
        title_out = title_out[:120]
        header, max_body = _budget()
    if max_body <= 0:
        return title_out[:80], f"(正文无法容纳；企微上限 {MAX_MARKDOWN_CHARS})"

    if len(message) <= max_body:
        return title_out, message

    notice = (
        f"\n\n...(已截断，原 {len(message)} 字符；企微整段上限 {MAX_MARKDOWN_CHARS}，"
        f"已预留告警记录 ID 行)"
    )
    keep = max_body - len(notice)
    if keep < 32:
        notice = "\n\n...(已截断)"
        keep = max_body - len(notice)
    keep = max(0, keep)
    body = message[:keep]
    if body and 0xD800 <= ord(body[-1]) <= 0xDBFF:
        body = body[:-1]
    out = body + notice
    logger.warning(
        "[wechat_markdown_limit] message 已截断: %s -> %s 字符",
        len(message),
        len(out),
    )
    return title_out, out
