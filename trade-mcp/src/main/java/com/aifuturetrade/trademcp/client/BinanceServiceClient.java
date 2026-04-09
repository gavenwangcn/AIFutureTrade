package com.aifuturetrade.trademcp.client;

import com.aifuturetrade.trademcp.config.DownstreamProperties;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.UriComponentsBuilder;

import java.util.List;
import java.util.Map;

@Component
public class BinanceServiceClient {

    private final RestClient restClient;
    private final DownstreamProperties props;

    public BinanceServiceClient(RestClient restClient, DownstreamProperties props) {
        this.restClient = restClient;
        this.props = props;
    }

    private String baseUrl() {
        return props.getBinanceService().getBaseUrl();
    }

    public Map<String, Object> symbolPrices(List<String> symbols) {
        return restClient.post()
                .uri(baseUrl() + "/api/market-data/symbol-prices")
                .contentType(MediaType.APPLICATION_JSON)
                .body(symbols)
                .retrieve()
                .body(Map.class);
    }

    public Map<String, Object> klines(String symbol, String interval, Integer limit, Long startTime, Long endTime) {
        String uri = UriComponentsBuilder.fromHttpUrl(baseUrl() + "/api/market-data/klines")
                .queryParam("symbol", symbol)
                .queryParam("interval", interval)
                .queryParamIfPresent("limit", java.util.Optional.ofNullable(limit))
                .queryParamIfPresent("startTime", java.util.Optional.ofNullable(startTime))
                .queryParamIfPresent("endTime", java.util.Optional.ofNullable(endTime))
                .toUriString();
        return restClient.get()
                .uri(uri)
                .retrieve()
                .body(Map.class);
    }
}

