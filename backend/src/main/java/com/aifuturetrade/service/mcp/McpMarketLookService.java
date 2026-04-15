package com.aifuturetrade.service.mcp;

import java.util.List;
import java.util.Map;

/**
 * MCP：盯盘表 market_look 受控只读 SQL
 */
public interface McpMarketLookService {

    /**
     * 仅允许 SELECT，且 SQL 文本中须包含 market_look；params 与 ? 顺序一致。
     */
    Map<String, Object> executeValidatedSql(String sql, List<Object> params);
}
