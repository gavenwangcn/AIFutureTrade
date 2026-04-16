package com.aifuturetrade.trademonitor.util;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * 企业微信机器人 markdown 消息体单条上限 4096 字符（超出返回 errcode=40058）。
 */
public final class WeChatMarkdownLimiter {

    private static final Logger log = LoggerFactory.getLogger(WeChatMarkdownLimiter.class);

    /** 官方限制：markdown.content 最大长度 */
    public static final int MAX_MARKDOWN_CHARS = 4096;

    private static final String SHORT_SUFFIX = "\n\n...(已截断)";

    private WeChatMarkdownLimiter() {}

    /**
     * 将正文限制在企微上限内；超长则截断并追加说明。
     *
     * @param markdown 完整 markdown 正文（含标题、时间等）
     * @return 长度不超过 {@link #MAX_MARKDOWN_CHARS} 的字符串
     */
    public static String clamp(String markdown) {
        if (markdown == null || markdown.isEmpty()) {
            return markdown;
        }
        int originalLen = markdown.length();
        if (originalLen <= MAX_MARKDOWN_CHARS) {
            return markdown;
        }

        String suffix = String.format(
                "%n%n> ...(内容已截断，原长度 %d 字符，企业微信单条上限 %d)",
                originalLen,
                MAX_MARKDOWN_CHARS);
        int maxPrefix = MAX_MARKDOWN_CHARS - suffix.length();
        if (maxPrefix < 32) {
            suffix = SHORT_SUFFIX;
            maxPrefix = MAX_MARKDOWN_CHARS - suffix.length();
        }

        String head = safePrefixByCodeUnits(markdown, maxPrefix);
        String out = head + suffix;
        log.warn(
                "企业微信 Markdown 超长已截断: 原 {} 字符 -> 发送 {} 字符",
                originalLen,
                out.length());
        return out;
    }

    /** 取前 maxUnits 个 char（UTF-16 码元），避免在高代理项中间截断。 */
    static String safePrefixByCodeUnits(String s, int maxUnits) {
        if (s.length() <= maxUnits) {
            return s;
        }
        if (maxUnits <= 0) {
            return "";
        }
        int end = maxUnits;
        if (Character.isHighSurrogate(s.charAt(end - 1))) {
            end--;
        }
        return s.substring(0, end);
    }
}
