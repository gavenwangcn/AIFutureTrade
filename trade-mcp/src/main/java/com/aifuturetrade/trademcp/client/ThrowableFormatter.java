package com.aifuturetrade.trademcp.client;

/**
 * 将异常链格式化为可供 MCP 工具返回给模型的可读字符串，避免仅暴露第一层 {@link Throwable#getMessage()}。
 */
public final class ThrowableFormatter {

    private static final int MAX_CHARS = 12_000;
    private static final int MAX_CAUSE_DEPTH = 12;

    private ThrowableFormatter() {}

    /**
     * 格式：{@code Class: msg | Caused by: Class: msg ...}；过长截断并标注。
     */
    /** 遍历 cause 链末端，用于标注 rootCauseType */
    public static Throwable getRootCause(Throwable t) {
        if (t == null) {
            return null;
        }
        Throwable cur = t;
        int guard = 0;
        while (cur.getCause() != null && cur.getCause() != cur && guard++ < MAX_CAUSE_DEPTH) {
            cur = cur.getCause();
        }
        return cur;
    }

    public static String formatForClient(Throwable t) {
        if (t == null) {
            return "unknown (null throwable)";
        }
        StringBuilder sb = new StringBuilder();
        Throwable cur = t;
        int depth = 0;
        while (cur != null && depth < MAX_CAUSE_DEPTH) {
            if (depth > 0) {
                sb.append(" | Caused by: ");
            }
            sb.append(cur.getClass().getName());
            String m = cur.getMessage();
            if (m != null && !m.isBlank()) {
                sb.append(": ").append(m);
            }
            cur = cur.getCause();
            depth++;
        }
        if (cur != null) {
            sb.append(" | ...(more causes omitted)");
        }
        String s = sb.toString();
        if (s.length() > MAX_CHARS) {
            return s.substring(0, MAX_CHARS) + "...(truncated, maxChars=" + MAX_CHARS + ")";
        }
        return s;
    }
}
