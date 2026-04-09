package com.aifuturetrade.service.mcp;

import java.util.List;
import java.util.Map;

/**
 * MCP：24_market_tickers 全市场合约行情（读库，无需 modelId）
 */
public interface McpMarketTickersService {

    /** 分页查询原始行（多条件） */
    Map<String, Object> queryRows(
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
            Boolean orderAsc);

    /** 与 queryRows 相同条件下的总行数 */
    Map<String, Object> countRows(
            String symbol,
            List<String> symbols,
            String side,
            Double minLastPrice,
            Double maxLastPrice,
            Double minPriceChangePercent,
            Double maxPriceChangePercent,
            Double minQuoteVolume,
            Double maxQuoteVolume);

    /** 每个 symbol 最新一条（全市场或限定 symbols），分页 */
    Map<String, Object> querySnapshot(
            Integer page,
            Integer size,
            List<String> symbols);

    Map<String, Object> countSnapshot(List<String> symbols);

    /** 全部 distinct symbol 列表 */
    Map<String, Object> listAllSymbols();

    /** 单 symbol 最新一条 */
    Map<String, Object> getLatestBySymbol(String symbol);

    /**
     * 受控原生查询：仅允许 SELECT，且必须包含表 24_market_tickers。
     * 使用占位符 ? 传参，params 顺序与 SQL 中 ? 一致。
     */
    Map<String, Object> executeValidatedSql(String sql, List<Object> params);
}
