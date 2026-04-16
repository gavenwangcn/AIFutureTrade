package com.aifuturetrade.common.json;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 将 {@code java.time.*}、JDBC 时间类型等转为 JSON 友好值（通常为 ISO 字符串），
 * 避免 Jackson 2.19+ 在序列化 {@code Map<String,Object>} 嵌套未注册 JSR-310 模块时失败。
 */
public final class JsonSafeValues {

    private static final ZoneId CN = ZoneId.of("Asia/Shanghai");

    private JsonSafeValues() {}

    public static Object normalizeForJson(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof LocalDateTime ldt) {
            return ldt.format(DateTimeFormatter.ISO_LOCAL_DATE_TIME);
        }
        if (value instanceof OffsetDateTime odt) {
            return odt.format(DateTimeFormatter.ISO_OFFSET_DATE_TIME);
        }
        if (value instanceof ZonedDateTime zdt) {
            return zdt.format(DateTimeFormatter.ISO_OFFSET_DATE_TIME);
        }
        if (value instanceof Instant ins) {
            return ins.toString();
        }
        if (value instanceof java.sql.Timestamp ts) {
            return ts.toLocalDateTime().format(DateTimeFormatter.ISO_LOCAL_DATE_TIME);
        }
        if (value instanceof java.sql.Date sd) {
            return sd.toLocalDate().toString();
        }
        if (value instanceof java.util.Date d) {
            return Instant.ofEpochMilli(d.getTime())
                    .atZone(CN)
                    .toLocalDateTime()
                    .format(DateTimeFormatter.ISO_LOCAL_DATE_TIME);
        }
        return value;
    }

    public static Map<String, Object> sanitizeMap(Map<String, Object> row) {
        if (row == null) {
            return null;
        }
        Map<String, Object> m = new LinkedHashMap<>(row.size());
        for (Map.Entry<String, Object> e : row.entrySet()) {
            m.put(e.getKey(), normalizeForJson(e.getValue()));
        }
        return m;
    }

    public static List<Map<String, Object>> sanitizeMapList(List<Map<String, Object>> rows) {
        if (rows == null) {
            return null;
        }
        List<Map<String, Object>> out = new ArrayList<>(rows.size());
        for (Map<String, Object> row : rows) {
            out.add(sanitizeMap(row));
        }
        return out;
    }
}
