package com.aifuturetrade.service.mcp.util;

import java.util.Locale;
import java.util.regex.Pattern;

/**
 * 限制 MCP 传入的 SQL 为只读 SELECT，且必须涉及表 24_market_tickers。
 * 注意：任意字符串拼接 SQL 均有风险，生产环境建议仅内网或加鉴权。
 */
public final class MarketTickerSqlGuard {

    private static final int MAX_SQL_LENGTH = 20_000;
    private static final Pattern MULTI_STMT = Pattern.compile(";\\s*\\S");

    private MarketTickerSqlGuard() {
    }

    public static void validate(String sql) {
        if (sql == null || sql.isBlank()) {
            throw new IllegalArgumentException("sql 不能为空");
        }
        String s = sql.trim();
        if (s.length() > MAX_SQL_LENGTH) {
            throw new IllegalArgumentException("sql 长度超过限制");
        }
        String lower = s.toLowerCase(Locale.ROOT);
        if (!lower.startsWith("select")) {
            throw new IllegalArgumentException("仅允许 SELECT 查询");
        }
        if (MULTI_STMT.matcher(s).find()) {
            throw new IllegalArgumentException("不允许多条语句（请勿使用分号拼接第二条语句）");
        }
        String[] banned = {
                " insert ", " update ", " delete ", " drop ", " truncate ", " alter ",
                " grant ", " revoke ", " merge ", " call ", " exec ", " execute ",
                " into outfile", " infile ", " load_file", " benchmark(", " sleep(",
                " pg_sleep", " waitfor delay", " information_schema"
        };
        String padded = " " + lower + " ";
        for (String b : banned) {
            if (padded.contains(b)) {
                throw new IllegalArgumentException("SQL 包含禁止关键字: " + b.trim());
            }
        }
        if (padded.contains("--") || padded.contains("/*")) {
            throw new IllegalArgumentException("不允许 SQL 注释");
        }
        if (!lower.contains("24_market_tickers")) {
            throw new IllegalArgumentException("SQL 必须查询表 24_market_tickers");
        }
    }
}
