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
        UriComponentsBuilder b = UriComponentsBuilder.fromUriString(baseUrl() + "/api/mcp/binance-futures/order/get")
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
        UriComponentsBuilder b = UriComponentsBuilder.fromUriString(baseUrl() + "/api/mcp/binance-futures/order/open-orders")
                .queryParam("modelId", modelId);
        if (symbol != null && !symbol.isEmpty()) {
            b.queryParam("symbol", symbol);
        }
        return restClient.get()
                .uri(b.toUriString())
                .retrieve()
                .body(Map.class);
    }

    /** 24_market_tickers：分页原始行 */
    public Map<String, Object> marketTickersRows(
            Integer page,
            Integer size,
            String symbol,
            List<String> symbols,
            String symbolsCsv,
            String side,
            Double minLastPrice,
            Double maxLastPrice,
            Double minPriceChangePercent,
            Double maxPriceChangePercent,
            Double minQuoteVolume,
            Double maxQuoteVolume,
            String orderBy,
            Boolean orderAsc) {
        UriComponentsBuilder b = UriComponentsBuilder.fromUriString(baseUrl() + "/api/mcp/market-tickers/rows");
        if (page != null) {
            b.queryParam("page", page);
        }
        if (size != null) {
            b.queryParam("size", size);
        }
        if (symbol != null && !symbol.isEmpty()) {
            b.queryParam("symbol", symbol);
        }
        if (symbols != null) {
            for (String s : symbols) {
                if (s != null && !s.isEmpty()) {
                    b.queryParam("symbols", s);
                }
            }
        }
        if (symbolsCsv != null && !symbolsCsv.isEmpty()) {
            b.queryParam("symbolsCsv", symbolsCsv);
        }
        if (side != null && !side.isEmpty()) {
            b.queryParam("side", side);
        }
        if (minLastPrice != null) {
            b.queryParam("minLastPrice", minLastPrice);
        }
        if (maxLastPrice != null) {
            b.queryParam("maxLastPrice", maxLastPrice);
        }
        if (minPriceChangePercent != null) {
            b.queryParam("minPriceChangePercent", minPriceChangePercent);
        }
        if (maxPriceChangePercent != null) {
            b.queryParam("maxPriceChangePercent", maxPriceChangePercent);
        }
        if (minQuoteVolume != null) {
            b.queryParam("minQuoteVolume", minQuoteVolume);
        }
        if (maxQuoteVolume != null) {
            b.queryParam("maxQuoteVolume", maxQuoteVolume);
        }
        if (orderBy != null && !orderBy.isEmpty()) {
            b.queryParam("orderBy", orderBy);
        }
        if (orderAsc != null) {
            b.queryParam("orderAsc", orderAsc);
        }
        return restClient.get().uri(b.toUriString()).retrieve().body(Map.class);
    }

    public Map<String, Object> marketTickersRowsCount(
            String symbol,
            List<String> symbols,
            String symbolsCsv,
            String side,
            Double minLastPrice,
            Double maxLastPrice,
            Double minPriceChangePercent,
            Double maxPriceChangePercent,
            Double minQuoteVolume,
            Double maxQuoteVolume) {
        UriComponentsBuilder b = UriComponentsBuilder.fromUriString(baseUrl() + "/api/mcp/market-tickers/rows/count");
        if (symbol != null && !symbol.isEmpty()) {
            b.queryParam("symbol", symbol);
        }
        if (symbols != null) {
            for (String s : symbols) {
                if (s != null && !s.isEmpty()) {
                    b.queryParam("symbols", s);
                }
            }
        }
        if (symbolsCsv != null && !symbolsCsv.isEmpty()) {
            b.queryParam("symbolsCsv", symbolsCsv);
        }
        if (side != null && !side.isEmpty()) {
            b.queryParam("side", side);
        }
        if (minLastPrice != null) {
            b.queryParam("minLastPrice", minLastPrice);
        }
        if (maxLastPrice != null) {
            b.queryParam("maxLastPrice", maxLastPrice);
        }
        if (minPriceChangePercent != null) {
            b.queryParam("minPriceChangePercent", minPriceChangePercent);
        }
        if (maxPriceChangePercent != null) {
            b.queryParam("maxPriceChangePercent", maxPriceChangePercent);
        }
        if (minQuoteVolume != null) {
            b.queryParam("minQuoteVolume", minQuoteVolume);
        }
        if (maxQuoteVolume != null) {
            b.queryParam("maxQuoteVolume", maxQuoteVolume);
        }
        return restClient.get().uri(b.toUriString()).retrieve().body(Map.class);
    }

    public Map<String, Object> marketTickersSnapshot(Integer page, Integer size, List<String> symbols, String symbolsCsv) {
        UriComponentsBuilder b = UriComponentsBuilder.fromUriString(baseUrl() + "/api/mcp/market-tickers/snapshot");
        if (page != null) {
            b.queryParam("page", page);
        }
        if (size != null) {
            b.queryParam("size", size);
        }
        if (symbols != null) {
            for (String s : symbols) {
                if (s != null && !s.isEmpty()) {
                    b.queryParam("symbols", s);
                }
            }
        }
        if (symbolsCsv != null && !symbolsCsv.isEmpty()) {
            b.queryParam("symbolsCsv", symbolsCsv);
        }
        return restClient.get().uri(b.toUriString()).retrieve().body(Map.class);
    }

    public Map<String, Object> marketTickersSnapshotCount(List<String> symbols, String symbolsCsv) {
        UriComponentsBuilder b = UriComponentsBuilder.fromUriString(baseUrl() + "/api/mcp/market-tickers/snapshot/count");
        if (symbols != null) {
            for (String s : symbols) {
                if (s != null && !s.isEmpty()) {
                    b.queryParam("symbols", s);
                }
            }
        }
        if (symbolsCsv != null && !symbolsCsv.isEmpty()) {
            b.queryParam("symbolsCsv", symbolsCsv);
        }
        return restClient.get().uri(b.toUriString()).retrieve().body(Map.class);
    }

    public Map<String, Object> marketTickersAllSymbols() {
        return restClient.get()
                .uri(baseUrl() + "/api/mcp/market-tickers/symbols")
                .retrieve()
                .body(Map.class);
    }

    public Map<String, Object> marketTickersLatest(String symbol) {
        return restClient.get()
                .uri(baseUrl() + "/api/mcp/market-tickers/latest?symbol={symbol}", symbol)
                .retrieve()
                .body(Map.class);
    }

    public Map<String, Object> marketTickersSql(Map<String, Object> body) {
        return restClient.post()
                .uri(baseUrl() + "/api/mcp/market-tickers/sql")
                .contentType(MediaType.APPLICATION_JSON)
                .body(body)
                .retrieve()
                .body(Map.class);
    }
}

