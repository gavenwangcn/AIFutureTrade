package com.aifuturetrade.service.mcp.dto;

import java.util.ArrayList;
import java.util.List;

/**
 * MCP 受控 SQL 查询请求（仅 SELECT + 表 market_look）
 */
public class McpMarketLookSqlRequest {

    private String sql;
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
