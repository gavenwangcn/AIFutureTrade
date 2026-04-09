package com.aifuturetrade.trademcp.client;

import com.aifuturetrade.trademcp.config.BinanceServiceUriSelector;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.UriComponentsBuilder;

import java.util.List;
import java.util.Map;

@Component
public class BinanceServiceClient {

    /** 与产品约定：未传 limit 时默认拉取 499 根 K 线 */
    public static final int DEFAULT_KLINE_LIMIT = 499;

    private final RestClient restClient;
    private final BinanceServiceUriSelector binanceUris;

    public BinanceServiceClient(RestClient restClient, BinanceServiceUriSelector binanceUris) {
        this.restClient = restClient;
        this.binanceUris = binanceUris;
    }

    private String nextBinanceBaseUrl() {
        return binanceUris.nextBaseUrl();
    }

    public Map<String, Object> symbolPrices(List<String> symbols) {
        return restClient.post()
                .uri(nextBinanceBaseUrl() + "/api/market-data/symbol-prices")
                .contentType(MediaType.APPLICATION_JSON)
                .body(symbols)
                .retrieve()
                .body(Map.class);
    }

    public Map<String, Object> klines(String symbol, String interval, Integer limit, Long startTime, Long endTime) {
        int effectiveLimit = limit != null ? limit : DEFAULT_KLINE_LIMIT;
        String uri = UriComponentsBuilder.fromHttpUrl(nextBinanceBaseUrl() + "/api/market-data/klines")
                .queryParam("symbol", symbol)
                .queryParam("interval", interval)
                .queryParam("limit", effectiveLimit)
                .queryParamIfPresent("startTime", java.util.Optional.ofNullable(startTime))
                .queryParamIfPresent("endTime", java.util.Optional.ofNullable(endTime))
                .toUriString();
        return restClient.get()
                .uri(uri)
                .retrieve()
                .body(Map.class);
    }
}

