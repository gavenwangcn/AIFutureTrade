package com.aifuturetrade.trademcp.client;

import com.aifuturetrade.trademcp.config.BinanceServiceUriSelector;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriComponentsBuilder;

import java.net.URI;
import java.util.List;
import java.util.Map;

@Component
public class BinanceServiceClient {

    /** 与产品约定：未传 limit 时默认拉取 499 根 K 线 */
    public static final int DEFAULT_KLINE_LIMIT = 499;

    /** 带指标 K 线：未传 limit 时由下游默认 299（与 binance-service 一致） */
    public static final int DEFAULT_KLINE_LIMIT_WITH_INDICATORS = 299;

    private final DownstreamJsonExchange json;
    private final BinanceServiceUriSelector binanceUris;

    public BinanceServiceClient(DownstreamJsonExchange json, BinanceServiceUriSelector binanceUris) {
        this.json = json;
        this.binanceUris = binanceUris;
    }

    private String nextBinanceBaseUrl() {
        return binanceUris.nextBaseUrl();
    }

    public Map<String, Object> symbolPrices(List<String> symbols) {
        return json.postJson(URI.create(nextBinanceBaseUrl() + "/api/market-data/symbol-prices"), symbols);
    }

    public Map<String, Object> klines(String symbol, String interval, Integer limit, Long startTime, Long endTime) {
        int effectiveLimit = limit != null ? limit : DEFAULT_KLINE_LIMIT;
        String uri = UriComponentsBuilder.fromUriString(nextBinanceBaseUrl() + "/api/market-data/klines")
                .queryParam("symbol", symbol)
                .queryParam("interval", interval)
                .queryParam("limit", effectiveLimit)
                .queryParamIfPresent("startTime", java.util.Optional.ofNullable(startTime))
                .queryParamIfPresent("endTime", java.util.Optional.ofNullable(endTime))
                .toUriString();
        return json.get(URI.create(uri));
    }

    /**
     * 带技术指标的 K 线：由 binance-service {@code GET /api/market-data/klines-with-indicators} 计算，本客户端仅转发。
     */
    public Map<String, Object> klinesWithIndicators(String symbol, String interval, Integer limit, Long startTime, Long endTime) {
        int effectiveLimit = limit != null ? limit : DEFAULT_KLINE_LIMIT_WITH_INDICATORS;
        String uri = UriComponentsBuilder.fromUriString(nextBinanceBaseUrl() + "/api/market-data/klines-with-indicators")
                .queryParam("symbol", symbol)
                .queryParam("interval", interval)
                .queryParam("limit", effectiveLimit)
                .queryParamIfPresent("startTime", java.util.Optional.ofNullable(startTime))
                .queryParamIfPresent("endTime", java.util.Optional.ofNullable(endTime))
                .toUriString();
        return json.get(URI.create(uri));
    }
}
