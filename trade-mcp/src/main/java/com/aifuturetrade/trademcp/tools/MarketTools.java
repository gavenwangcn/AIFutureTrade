package com.aifuturetrade.trademcp.tools;

import com.aifuturetrade.trademcp.client.BinanceServiceClient;
import com.aifuturetrade.trademcp.indicators.KlineIndicatorCalculator;
import org.springframework.stereotype.Component;

import org.springaicommunity.mcp.annotation.McpTool;
import org.springaicommunity.mcp.annotation.McpToolParam;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Component
public class MarketTools {

    private final BinanceServiceClient binanceServiceClient;

    public MarketTools(BinanceServiceClient binanceServiceClient) {
        this.binanceServiceClient = binanceServiceClient;
    }

    @McpTool(name = "trade.market.symbol_prices", description = "批量查询symbol实时价格（不需要modelId；调用binance-service controller）")
    public Map<String, Object> symbolPrices(
            @McpToolParam(description = "交易对列表，如 [\"BTCUSDT\",\"ETHUSDT\"]", required = true) List<String> symbols) {
        return binanceServiceClient.symbolPrices(symbols);
    }

    @McpTool(name = "trade.market.klines", description = "查询K线（不需要modelId；调用binance-service controller）")
    public Map<String, Object> klines(
            @McpToolParam(description = "交易对", required = true) String symbol,
            @McpToolParam(description = "周期，如 1m/5m/15m/1h/4h/1d 等", required = true) String interval,
            @McpToolParam(description = "数量", required = false) Integer limit,
            @McpToolParam(description = "开始时间戳(ms)", required = false) Long startTime,
            @McpToolParam(description = "结束时间戳(ms)", required = false) Long endTime
    ) {
        return binanceServiceClient.klines(symbol, interval, limit, startTime, endTime);
    }

    @McpTool(name = "trade.market.klines_with_indicators", description = "查询K线并附加与 Python market_data 一致的技术指标（不需要modelId；先调 binance-service klines，再在本地计算指标）")
    public Map<String, Object> klinesWithIndicators(
            @McpToolParam(description = "交易对", required = true) String symbol,
            @McpToolParam(description = "周期，如 1m/5m/15m/1h/4h/1d 等", required = true) String interval,
            @McpToolParam(description = "数量", required = false) Integer limit,
            @McpToolParam(description = "开始时间戳(ms)", required = false) Long startTime,
            @McpToolParam(description = "结束时间戳(ms)", required = false) Long endTime
    ) {
        Map<String, Object> resp = binanceServiceClient.klines(symbol, interval, limit, startTime, endTime);
        if (!Boolean.TRUE.equals(resp.get("success"))) {
            return resp;
        }
        Object dataObj = resp.get("data");
        if (!(dataObj instanceof List)) {
            return resp;
        }
        @SuppressWarnings("unchecked")
        List<Object> raw = (List<Object>) dataObj;
        List<Map<String, Object>> rows = new ArrayList<>();
        for (Object o : raw) {
            if (o instanceof Map) {
                @SuppressWarnings("unchecked")
                Map<String, Object> m = (Map<String, Object>) o;
                Map<String, Object> row = new LinkedHashMap<>(m);
                rows.add(row);
            }
        }
        List<Map<String, Object>> enriched = KlineIndicatorCalculator.enrich(rows);
        Map<String, Object> out = new LinkedHashMap<>(resp);
        out.put("data", enriched);
        return out;
    }
}

