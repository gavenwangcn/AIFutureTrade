package com.aifuturetrade.common.jackson;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;

import java.io.IOException;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.DateTimeParseException;
import java.time.temporal.ChronoField;

/**
 * 反序列化 JSON 中的 {@link LocalDateTime}，兼容：
 * <ul>
 *   <li>ISO-8601 本地：{@code 2026-04-16T15:03:05}</li>
 *   <li>常见 SQL/前端：{@code 2026-04-16 15:03:05}（空格）</li>
 *   <li>带偏移：{@code 2026-04-16T15:03:05+08:00}、{@code 2026-04-16T15:03:05Z}（取「本地日期时间」部分写入 {@link LocalDateTime}）</li>
 * </ul>
 */
public class FlexibleLocalDateTimeDeserializer extends JsonDeserializer<LocalDateTime> {

    private static final DateTimeFormatter SPACE_SEP =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private static final DateTimeFormatter SPACE_SEP_WITH_MILLIS = new DateTimeFormatterBuilder()
            .appendPattern("yyyy-MM-dd HH:mm:ss")
            .optionalStart()
            .appendFraction(ChronoField.MILLI_OF_SECOND, 1, 3, true)
            .optionalEnd()
            .toFormatter();

    @Override
    public LocalDateTime deserialize(JsonParser p, DeserializationContext ctxt) throws IOException {
        String raw = p.getValueAsString();
        if (raw == null) {
            return null;
        }
        String s = raw.trim();
        if (s.isEmpty()) {
            return null;
        }

        // 带时区偏移 / Z：先按 OffsetDateTime / ZonedDateTime 解析再取本地字段
        if (endsWithZoneOrOffset(s)) {
            try {
                return OffsetDateTime.parse(s).toLocalDateTime();
            } catch (DateTimeParseException ignored) {
                // continue
            }
            try {
                return ZonedDateTime.parse(s).toLocalDateTime();
            } catch (DateTimeParseException ignored) {
                // continue
            }
        }

        // 无偏移：空格换 T 后 ISO 本地
        try {
            return LocalDateTime.parse(s.replace(" ", "T"));
        } catch (DateTimeParseException ignored) {
            // continue
        }
        try {
            return LocalDateTime.parse(s, SPACE_SEP);
        } catch (DateTimeParseException ignored) {
            // continue
        }
        try {
            return LocalDateTime.parse(s, SPACE_SEP_WITH_MILLIS);
        } catch (DateTimeParseException e) {
            throw ctxt.weirdStringException(
                    raw,
                    LocalDateTime.class,
                    "支持 ISO 本地、yyyy-MM-dd HH:mm:ss[.SSS]、或带 +08:00/Z 的偏移时间");
        }
    }

    private static boolean endsWithZoneOrOffset(String s) {
        if (s.isEmpty()) {
            return false;
        }
        char last = s.charAt(s.length() - 1);
        if (last == 'Z' || last == 'z') {
            return true;
        }
        // +08:00、-05:00，或末尾带地区 ID 的 ZonedDateTime（含多个字母）
        int plus = s.indexOf('+', 10);
        if (plus > 0) {
            return true;
        }
        // 排除日期段里的 '-'，查找时区前的 '-': ...T15:03:05-05:00
        int t = s.indexOf('T');
        if (t > 0) {
            int dashAfterTime = s.indexOf('-', t + 1);
            return dashAfterTime > 0 && dashAfterTime > t + 3;
        }
        return false;
    }
}
