package com.aifuturetrade.trademcp.client;

import com.aifuturetrade.trademcp.config.DownstreamProperties;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.UriComponentsBuilder;

import java.util.List;
import java.util.Map;

@Component
public class BackendClient {

    private final RestClient restClient;
    private final DownstreamProperties props;

    public BackendClient(RestClient restClient, DownstreamProperties props) {
        this.restClient = restClient;
        this.props = props;
    }

    private String baseUrl() {
        return props.getBackend().getBaseUrl();
    }

    public Map<String, Object> accountInfo(String modelId) {
        return restClient.get()
                .uri(baseUrl() + "/api/mcp/binance-futures/account/account-info?modelId={modelId}", modelId)
                .retrieve()
                .body(Map.class);
    }

    public Map<String, Object> balance(String modelId) {
        return restClient.get()
                .uri(baseUrl() + "/api/mcp/binance-futures/account/balance?modelId={modelId}", modelId)
                .retrieve()
                .body(Map.class);
    }

    public Map<String, Object> positions(String modelId) {
        return restClient.get()
                .uri(baseUrl() + "/api/mcp/binance-futures/account/positions?modelId={modelId}", modelId)
                .retrieve()
                .body(Map.class);
    }

    public Map<String, Object> sellPosition(String modelId, String symbol) {
        return restClient.post()
                .uri(baseUrl() + "/api/mcp/binance-futures/order/sell-position?modelId={modelId}&symbol={symbol}", modelId, symbol)
                .retrieve()
                .body(Map.class);
    }

    public Map<String, Object> orderCreate(String modelId, Map<String, Object> body) {
        return restClient.post()
                .uri(baseUrl() + "/api/mcp/binance-futures/order/create?modelId={modelId}", modelId)
                .contentType(MediaType.APPLICATION_JSON)
                .body(body)
                .retrieve()
                .body(Map.class);
    }

    public Map<String, Object> orderCancel(String modelId, Map<String, Object> body) {
        return restClient.post()
                .uri(baseUrl() + "/api/mcp/binance-futures/order/cancel?modelId={modelId}", modelId)
                .contentType(MediaType.APPLICATION_JSON)
                .body(body)
                .retrieve()
                .body(Map.class);
    }

    public Map<String, Object> orderGet(String modelId, String symbol, Long orderId, String origClientOrderId) {
        UriComponentsBuilder b = UriComponentsBuilder.fromHttpUrl(baseUrl() + "/api/mcp/binance-futures/order/get")
                .queryParam("modelId", modelId)
                .queryParam("symbol", symbol);
        if (orderId != null) {
            b.queryParam("orderId", orderId);
        }
        if (origClientOrderId != null && !origClientOrderId.isEmpty()) {
            b.queryParam("origClientOrderId", origClientOrderId);
        }
        return restClient.get()
                .uri(b.toUriString())
                .retrieve()
                .body(Map.class);
    }

    public Map<String, Object> openOrders(String modelId, String symbol) {
        UriComponentsBuilder b = UriComponentsBuilder.fromHttpUrl(baseUrl() + "/api/mcp/binance-futures/order/open-orders")
                .queryParam("modelId", modelId);
        if (symbol != null && !symbol.isEmpty()) {
            b.queryParam("symbol", symbol);
        }
        return restClient.get()
                .uri(b.toUriString())
                .retrieve()
                .body(Map.class);
    }
}

