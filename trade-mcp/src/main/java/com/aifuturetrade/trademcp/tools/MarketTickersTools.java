package com.aifuturetrade.trademcp.tools;

import com.aifuturetrade.trademcp.client.BackendClient;
import org.springframework.stereotype.Component;
import org.springaicommunity.mcp.annotation.McpTool;
import org.springaicommunity.mcp.annotation.McpToolParam;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 库表 24_market_tickers 市场数据（经 backend 读 MySQL，不需要 modelId）
 */
@Component
public class MarketTickersTools {

    private final BackendClient backendClient;

    public MarketTickersTools(BackendClient backendClient) {
        this.backendClient = backendClient;
    }

    @McpTool(name = "trade.market_tickers.rows", description = "分页查询 24_market_tickers 原始行，支持单/多 symbol、side、价格与涨跌幅与成交额区间、排序")
    public Map<String, Object> rows(
            @McpToolParam(description = "页码，从 1 开始", required = false) Integer page,
            @McpToolParam(description = "每页条数，最大 500", required = false) Integer size,
            @McpToolParam(description = "单个交易对，如 BTCUSDT", required = false) String symbol,
            @McpToolParam(description = "多个交易对", required = false) List<String> symbols,
            @McpToolParam(description = "逗号分隔交易对，如 BTCUSDT,ETHUSDT", required = false) String symbolsCsv,
            @McpToolParam(description = "方向 LONG/SHORT", required = false) String side,
            @McpToolParam(description = "最新价下限", required = false) Double minLastPrice,
            @McpToolParam(description = "最新价上限", required = false) Double maxLastPrice,
            @McpToolParam(description = "24h 涨跌幅%% 下限", required = false) Double minPriceChangePercent,
            @McpToolParam(description = "24h 涨跌幅%% 上限", required = false) Double maxPriceChangePercent,
            @McpToolParam(description = "计价成交额下限", required = false) Double minQuoteVolume,
            @McpToolParam(description = "计价成交额上限", required = false) Double maxQuoteVolume,
            @McpToolParam(description = "排序列：id/event_time/symbol/last_price/quote_volume/price_change_percent/base_volume/ingestion_time", required = false) String orderBy,
            @McpToolParam(description = "是否升序，默认 false（降序）", required = false) Boolean orderAsc) {
        return backendClient.marketTickersRows(
                page, size, symbol, symbols, symbolsCsv, side,
                minLastPrice, maxLastPrice,
                minPriceChangePercent, maxPriceChangePercent,
                minQuoteVolume, maxQuoteVolume,
                orderBy, orderAsc);
    }

    @McpTool(name = "trade.market_tickers.rows_count", description = "与 rows 相同筛选条件下的总行数")
    public Map<String, Object> rowsCount(
            @McpToolParam(description = "单个交易对", required = false) String symbol,
            @McpToolParam(description = "多个交易对", required = false) List<String> symbols,
            @McpToolParam(description = "逗号分隔交易对", required = false) String symbolsCsv,
            @McpToolParam(description = "方向 LONG/SHORT", required = false) String side,
            @McpToolParam(description = "最新价下限", required = false) Double minLastPrice,
            @McpToolParam(description = "最新价上限", required = false) Double maxLastPrice,
            @McpToolParam(description = "24h 涨跌幅%% 下限", required = false) Double minPriceChangePercent,
            @McpToolParam(description = "24h 涨跌幅%% 上限", required = false) Double maxPriceChangePercent,
            @McpToolParam(description = "计价成交额下限", required = false) Double minQuoteVolume,
            @McpToolParam(description = "计价成交额上限", required = false) Double maxQuoteVolume) {
        return backendClient.marketTickersRowsCount(
                symbol, symbols, symbolsCsv, side,
                minLastPrice, maxLastPrice,
                minPriceChangePercent, maxPriceChangePercent,
                minQuoteVolume, maxQuoteVolume);
    }

    @McpTool(name = "trade.market_tickers.snapshot", description = "每个 symbol 仅最新一条（按 event_time），分页；可限定 symbols 或查全市场")
    public Map<String, Object> snapshot(
            @McpToolParam(description = "页码", required = false) Integer page,
            @McpToolParam(description = "每页条数", required = false) Integer size,
            @McpToolParam(description = "限定交易对列表", required = false) List<String> symbols,
            @McpToolParam(description = "逗号分隔交易对", required = false) String symbolsCsv) {
        return backendClient.marketTickersSnapshot(page, size, symbols, symbolsCsv);
    }

    @McpTool(name = "trade.market_tickers.snapshot_count", description = "snapshot 模式下的 symbol 分组总数")
    public Map<String, Object> snapshotCount(
            @McpToolParam(description = "限定交易对列表", required = false) List<String> symbols,
            @McpToolParam(description = "逗号分隔交易对", required = false) String symbolsCsv) {
        return backendClient.marketTickersSnapshotCount(symbols, symbolsCsv);
    }

    @McpTool(name = "trade.market_tickers.all_symbols", description = "库中全部 distinct 交易对列表")
    public Map<String, Object> allSymbols() {
        return backendClient.marketTickersAllSymbols();
    }

    @McpTool(name = "trade.market_tickers.latest", description = "单个交易对在库中的最新一条 ticker 行")
    public Map<String, Object> latest(
            @McpToolParam(description = "交易对，如 BTCUSDT", required = true) String symbol) {
        return backendClient.marketTickersLatest(symbol);
    }

    @McpTool(name = "trade.market_tickers.sql", description = "受控 SELECT：SQL 必须包含表名 24_market_tickers，仅允许只读查询；params 与 ? 占位符顺序一致")
    public Map<String, Object> sql(
            @McpToolParam(description = "SELECT 语句，使用 ? 传参", required = true) String sql,
            @McpToolParam(description = "与 ? 顺序一致的参数列表", required = false) List<Object> params) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("sql", sql);
        body.put("params", params == null ? List.of() : params);
        return backendClient.marketTickersSql(body);
    }
}
