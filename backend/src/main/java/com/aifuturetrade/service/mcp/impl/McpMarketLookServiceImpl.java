package com.aifuturetrade.service.mcp.impl;

import com.aifuturetrade.common.json.JsonSafeValues;
import com.aifuturetrade.service.mcp.McpMarketLookService;
import com.aifuturetrade.service.mcp.util.MarketLookSqlGuard;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
public class McpMarketLookServiceImpl implements McpMarketLookService {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Override
    public Map<String, Object> executeValidatedSql(String sql, List<Object> params) {
        MarketLookSqlGuard.validate(sql);
        List<Object> args = params == null ? List.of() : params;
        List<Map<String, Object>> rows = jdbcTemplate.query(
                sql,
                (rs, rowNum) -> {
                    int n = rs.getMetaData().getColumnCount();
                    Map<String, Object> m = new HashMap<>();
                    for (int i = 1; i <= n; i++) {
                        String label = rs.getMetaData().getColumnLabel(i);
                        m.put(label, rs.getObject(i));
                    }
                    return m;
                },
                args.toArray());
        rows = JsonSafeValues.sanitizeMapList(rows);
        Map<String, Object> out = new HashMap<>();
        out.put("success", true);
        out.put("data", rows);
        out.put("total", rows.size());
        return out;
    }
}
