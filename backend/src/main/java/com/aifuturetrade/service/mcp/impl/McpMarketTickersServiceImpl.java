package com.aifuturetrade.service.mcp.impl;

import com.aifuturetrade.dao.entity.MarketTickerDO;
import com.aifuturetrade.dao.mapper.MarketTickerMapper;
import com.aifuturetrade.service.mcp.McpMarketTickersService;
import com.aifuturetrade.service.mcp.util.MarketTickerSqlGuard;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

@Service
public class McpMarketTickersServiceImpl implements McpMarketTickersService {

    private static final int DEFAULT_PAGE_SIZE = 20;
    private static final int MAX_PAGE_SIZE = 500;

    private static final Set<String> ORDER_COLUMNS = Set.of(
            "id", "event_time", "symbol", "last_price", "quote_volume",
            "price_change_percent", "base_volume", "ingestion_time");

    @Autowired
    private MarketTickerMapper marketTickerMapper;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Override
    public Map<String, Object> queryRows(
            Integer page,
            Integer size,
            String symbol,
            List<String> symbols,
            String side,
            Double minLastPrice,
            Double maxLastPrice,
            Double minPriceChangePercent,
            Double maxPriceChangePercent,
            Double minQuoteVolume,
            Double maxQuoteVolume,
            String orderBy,
            Boolean orderAsc) {
        int p = page == null || page < 1 ? 1 : page;
        int s = size == null || size < 1 ? DEFAULT_PAGE_SIZE : Math.min(size, MAX_PAGE_SIZE);
        QueryWrapper<MarketTickerDO> w = buildRowWrapper(
                symbol, symbols, side,
                minLastPrice, maxLastPrice,
                minPriceChangePercent, maxPriceChangePercent,
                minQuoteVolume, maxQuoteVolume);
        applyOrder(w, orderBy, orderAsc != null && orderAsc);
        Page<MarketTickerDO> result = marketTickerMapper.selectPage(new Page<>(p, s), w);
        Map<String, Object> out = new HashMap<>();
        out.put("success", true);
        out.put("data", result.getRecords());
        out.put("total", result.getTotal());
        out.put("page", p);
        out.put("size", s);
        out.put("pages", result.getPages());
        return out;
    }

    @Override
    public Map<String, Object> countRows(
            String symbol,
            List<String> symbols,
            String side,
            Double minLastPrice,
            Double maxLastPrice,
            Double minPriceChangePercent,
            Double maxPriceChangePercent,
            Double minQuoteVolume,
            Double maxQuoteVolume) {
        QueryWrapper<MarketTickerDO> w = buildRowWrapper(
                symbol, symbols, side,
                minLastPrice, maxLastPrice,
                minPriceChangePercent, maxPriceChangePercent,
                minQuoteVolume, maxQuoteVolume);
        Long total = marketTickerMapper.selectCount(w);
        Map<String, Object> out = new HashMap<>();
        out.put("success", true);
        out.put("total", total);
        return out;
    }

    private QueryWrapper<MarketTickerDO> buildRowWrapper(
            String symbol,
            List<String> symbols,
            String side,
            Double minLastPrice,
            Double maxLastPrice,
            Double minPriceChangePercent,
            Double maxPriceChangePercent,
            Double minQuoteVolume,
            Double maxQuoteVolume) {
        QueryWrapper<MarketTickerDO> w = new QueryWrapper<>();
        if (symbol != null && !symbol.isBlank()) {
            w.eq("symbol", symbol.trim().toUpperCase(Locale.ROOT));
        }
        if (symbols != null && !symbols.isEmpty()) {
            List<String> up = new ArrayList<>();
            for (String x : symbols) {
                if (x != null && !x.isBlank()) {
                    up.add(x.trim().toUpperCase(Locale.ROOT));
                }
            }
            if (!up.isEmpty()) {
                w.in("symbol", up);
            }
        }
        if (side != null && !side.isBlank()) {
            w.eq("side", side.trim().toUpperCase(Locale.ROOT));
        }
        if (minLastPrice != null) {
            w.ge("last_price", minLastPrice);
        }
        if (maxLastPrice != null) {
            w.le("last_price", maxLastPrice);
        }
        if (minPriceChangePercent != null) {
            w.ge("price_change_percent", minPriceChangePercent);
        }
        if (maxPriceChangePercent != null) {
            w.le("price_change_percent", maxPriceChangePercent);
        }
        if (minQuoteVolume != null) {
            w.ge("quote_volume", minQuoteVolume);
        }
        if (maxQuoteVolume != null) {
            w.le("quote_volume", maxQuoteVolume);
        }
        return w;
    }

    private void applyOrder(QueryWrapper<MarketTickerDO> w, String orderBy, boolean asc) {
        String col = orderBy == null || orderBy.isBlank() ? "event_time" : orderBy.trim().toLowerCase(Locale.ROOT);
        if (!ORDER_COLUMNS.contains(col)) {
            col = "event_time";
        }
        w.orderBy(true, asc, col);
    }

    @Override
    public Map<String, Object> querySnapshot(Integer page, Integer size, List<String> symbols) {
        int p = page == null || page < 1 ? 1 : page;
        int s = size == null || size < 1 ? DEFAULT_PAGE_SIZE : Math.min(size, MAX_PAGE_SIZE);
        long offset = (long) (p - 1) * s;
        List<String> symFilter = (symbols == null || symbols.isEmpty()) ? null : normalizeSymbols(symbols);
        Long totalG = marketTickerMapper.countLatestPerSymbolGroups(symFilter);
        long total = totalG == null ? 0L : totalG;
        List<MarketTickerDO> rows = marketTickerMapper.selectLatestPerSymbolPage(symFilter, offset, s);
        Map<String, Object> out = new HashMap<>();
        out.put("success", true);
        out.put("data", rows);
        out.put("total", total);
        out.put("page", p);
        out.put("size", s);
        out.put("pages", total == 0 ? 0 : (int) Math.ceil((double) total / s));
        return out;
    }

    @Override
    public Map<String, Object> countSnapshot(List<String> symbols) {
        List<String> symFilter = (symbols == null || symbols.isEmpty()) ? null : normalizeSymbols(symbols);
        Long totalG = marketTickerMapper.countLatestPerSymbolGroups(symFilter);
        Map<String, Object> out = new HashMap<>();
        out.put("success", true);
        out.put("total", totalG == null ? 0L : totalG);
        return out;
    }

    private static List<String> normalizeSymbols(List<String> symbols) {
        List<String> up = new ArrayList<>();
        for (String x : symbols) {
            if (x != null && !x.isBlank()) {
                up.add(x.trim().toUpperCase(Locale.ROOT));
            }
        }
        return up.isEmpty() ? null : up;
    }

    @Override
    public Map<String, Object> listAllSymbols() {
        List<String> list = marketTickerMapper.selectDistinctSymbols();
        Map<String, Object> out = new HashMap<>();
        out.put("success", true);
        out.put("data", list == null ? List.of() : list);
        out.put("total", list == null ? 0 : list.size());
        return out;
    }

    @Override
    public Map<String, Object> getLatestBySymbol(String symbol) {
        if (symbol == null || symbol.isBlank()) {
            Map<String, Object> err = new HashMap<>();
            err.put("success", false);
            err.put("error", "symbol 不能为空");
            return err;
        }
        MarketTickerDO row = marketTickerMapper.selectLatestRowBySymbol(symbol.trim().toUpperCase(Locale.ROOT));
        Map<String, Object> out = new HashMap<>();
        out.put("success", true);
        out.put("data", row);
        return out;
    }

    @Override
    public Map<String, Object> executeValidatedSql(String sql, List<Object> params) {
        MarketTickerSqlGuard.validate(sql);
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
        Map<String, Object> out = new HashMap<>();
        out.put("success", true);
        out.put("data", rows);
        out.put("total", rows.size());
        return out;
    }
}
