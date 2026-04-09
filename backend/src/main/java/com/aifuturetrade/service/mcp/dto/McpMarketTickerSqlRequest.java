package com.aifuturetrade.service.mcp.dto;

import java.util.ArrayList;
import java.util.List;

/**
 * MCP 受控 SQL 查询请求（仅 SELECT + 表 24_market_tickers）
 */
public class McpMarketTickerSqlRequest {

    /**
     * 完整 SELECT 语句，使用 ? 作为占位符
     */
    private String sql;

    /**
     * 与 ? 顺序一致的参数（字符串/数字）
     */
    private List<Object> params = new ArrayList<>();

    public String getSql() {
        return sql;
    }

    public void setSql(String sql) {
        this.sql = sql;
    }

    public List<Object> getParams() {
        return params;
    }

    public void setParams(List<Object> params) {
        this.params = params;
    }
}
