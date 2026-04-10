package com.aifuturetrade.trademcp.tools;

import com.aifuturetrade.trademcp.client.BackendClient;
import org.springframework.stereotype.Component;
import org.springaicommunity.mcp.annotation.McpTool;
import org.springaicommunity.mcp.annotation.McpToolParam;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 库表 24_market_tickers 市场数据（经 backend 读 MySQL，不需要 modelId）。
 * 列定义与 backend {@code MarketTickerDO} / 表结构一致，SQL 中请使用下划线列名。
 */
@Component
public class MarketTickersTools {

    /**
     * MCP 工具长描述：供模型理解受控 SQL 与表字段（与 {@code 24_market_tickers} 实际列一致）。
     */
    private static final String MARKET_TICKERS_SQL_TOOL_DESCRIPTION =
            "受控只读 SELECT：SQL 必须包含表名 24_market_tickers（建议反引号 `24_market_tickers`）；仅允许 SELECT，禁止写操作；"
                    + "params 与 SQL 中 ? 占位符从左到右一一对应。"
                    + " 表字段（MySQL 列名均为 snake_case）："
                    + "id BIGINT 主键自增；"
                    + "event_time DATETIME 行情事件时间；"
                    + "symbol VARCHAR 交易对如 BTCUSDT；"
                    + "price_change DOUBLE 价格变动；"
                    + "price_change_percent DOUBLE 24h 涨跌幅（比例或百分数依库内约定，可与 change_percent_text 对照）；"
                    + "side VARCHAR 方向 LONG/SHORT；"
                    + "change_percent_text VARCHAR 涨跌幅展示文本；"
                    + "average_price DOUBLE 均价；"
                    + "last_price DOUBLE 最新价；"
                    + "last_trade_volume DOUBLE 最后一笔成交量；"
                    + "open_price/high_price/low_price DOUBLE 开高低；"
                    + "base_volume DOUBLE 基础资产成交量；"
                    + "quote_volume DOUBLE 计价成交额（如 USDT）；"
                    + "stats_open_time/stats_close_time DATETIME 24h 统计窗口起止；"
                    + "first_trade_id/last_trade_id BIGINT 首末成交 ID；"
                    + "trade_count BIGINT 成交笔数；"
                    + "ingestion_time DATETIME 数据写入库时间；"
                    + "update_price_date DATETIME 价格更新日期。"
                    + " 示例：SELECT symbol,last_price,quote_volume,price_change_percent,event_time FROM `24_market_tickers` "
                    + "WHERE symbol=? ORDER BY event_time DESC LIMIT 20";

    private static final String MARKET_TICKERS_SQL_PARAM_SQL =
            "只读 SELECT 字符串，必须出现 24_market_tickers；用 ? 占位参数（防注入），例如："
                    + "SELECT * FROM `24_market_tickers` WHERE symbol=? AND last_price>? LIMIT 50";

    private static final String MARKET_TICKERS_SQL_PARAM_PARAMS =
            "与 SQL 中 ? 从左到右顺序一致的参数列表，如 [\"BTCUSDT\", 50000.0]；无占位符时可省略或传空数组";

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

    @McpTool(name = "trade.market_tickers.sql", description = MARKET_TICKERS_SQL_TOOL_DESCRIPTION)
    public Map<String, Object> sql(
            @McpToolParam(description = MARKET_TICKERS_SQL_PARAM_SQL, required = true) String sql,
            @McpToolParam(description = MARKET_TICKERS_SQL_PARAM_PARAMS, required = false) List<Object> params) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("sql", sql);
        body.put("params", params == null ? List.of() : params);
        return backendClient.marketTickersSql(body);
    }
}
