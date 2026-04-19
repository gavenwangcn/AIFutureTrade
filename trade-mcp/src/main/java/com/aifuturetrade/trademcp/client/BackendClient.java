package com.aifuturetrade.trademcp.client;

import com.aifuturetrade.trademcp.config.DownstreamProperties;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriComponentsBuilder;

import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Component
public class BackendClient {

    private final DownstreamJsonExchange json;
    private final DownstreamProperties props;

    public BackendClient(DownstreamJsonExchange json, DownstreamProperties props) {
        this.json = json;
        this.props = props;
    }

    private String baseUrl() {
        return props.getBackend().getBaseUrl();
    }

    public Map<String, Object> accountInfo(String modelId) {
        return json.get(baseUrl() + "/api/mcp/binance-futures/account/account-info?modelId={modelId}", modelId);
    }

    public Map<String, Object> balance(String modelId) {
        return json.get(baseUrl() + "/api/mcp/binance-futures/account/balance?modelId={modelId}", modelId);
    }

    public Map<String, Object> positions(String modelId) {
        return json.get(baseUrl() + "/api/mcp/binance-futures/account/positions?modelId={modelId}", modelId);
    }

    public Map<String, Object> sellPosition(String modelId, String symbol) {
        return json.postJson(baseUrl() + "/api/mcp/binance-futures/order/sell-position?modelId={modelId}&symbol={symbol}", Map.of(), modelId, symbol);
    }

    public Map<String, Object> orderCreate(String modelId, Map<String, Object> body) {
        return json.postJson(baseUrl() + "/api/mcp/binance-futures/order/create?modelId={modelId}", body, modelId);
    }

    public Map<String, Object> orderCancel(String modelId, Map<String, Object> body) {
        return json.postJson(baseUrl() + "/api/mcp/binance-futures/order/cancel?modelId={modelId}", body, modelId);
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
        return json.get(URI.create(b.toUriString()));
    }

    public Map<String, Object> openOrders(String modelId, String symbol) {
        UriComponentsBuilder b = UriComponentsBuilder.fromUriString(baseUrl() + "/api/mcp/binance-futures/order/open-orders")
                .queryParam("modelId", modelId);
        if (symbol != null && !symbol.isEmpty()) {
            b.queryParam("symbol", symbol);
        }
        return json.get(URI.create(b.toUriString()));
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
        return json.get(URI.create(b.toUriString()));
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
        return json.get(URI.create(b.toUriString()));
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
        return json.get(URI.create(b.toUriString()));
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
        return json.get(URI.create(b.toUriString()));
    }

    public Map<String, Object> marketTickersAllSymbols() {
        return json.get(baseUrl() + "/api/mcp/market-tickers/symbols");
    }

    public Map<String, Object> marketTickersLatest(String symbol) {
        return json.get(baseUrl() + "/api/mcp/market-tickers/latest?symbol={symbol}", symbol);
    }

    public Map<String, Object> marketTickersSql(Map<String, Object> body) {
        return json.postJson(URI.create(baseUrl() + "/api/mcp/market-tickers/sql"), body);
    }

    // --- 盯盘 market_look + 策略 strategys（主库 backend）---

    public Map<String, Object> marketLookCreate(Map<String, Object> body) {
        return json.postJson(URI.create(baseUrl() + "/api/market-look"), body);
    }

    public Map<String, Object> strategyCreate(Map<String, Object> body) {
        return json.postJson(URI.create(baseUrl() + "/api/strategies"), body);
    }

    /**
     * 按策略 ID 调用 AI 重新生成策略代码（可选覆盖 strategy_context / validate_symbol），测试通过后落库。
     */
    public Map<String, Object> strategyRegenerateCode(String strategyId, Map<String, Object> body) {
        String enc = URLEncoder.encode(strategyId, StandardCharsets.UTF_8);
        return json.postJson(URI.create(baseUrl() + "/api/strategies/" + enc + "/regenerate-code"), body);
    }

    /**
     * 直接提交策略代码（不调用模型）；服务端先执行与「获取代码」相同的测试，仅通过时写入 {@code strategy_code}。
     */
    public Map<String, Object> strategyApplySubmittedCode(String strategyId, Map<String, Object> body) {
        String enc = URLEncoder.encode(strategyId, StandardCharsets.UTF_8);
        return json.postJson(URI.create(baseUrl() + "/api/strategies/" + enc + "/update-strategy-code"), body);
    }

    public Map<String, Object> strategyGetById(String id) {
        String enc = URLEncoder.encode(id, StandardCharsets.UTF_8);
        return json.get(URI.create(baseUrl() + "/api/strategies/" + enc));
    }

    /**
     * 按主键删除 strategys 一行，对应 {@code DELETE /api/strategies/{id}}。
     */
    public Map<String, Object> strategyDelete(String strategyId) {
        String enc = URLEncoder.encode(strategyId, StandardCharsets.UTF_8);
        return json.delete(URI.create(baseUrl() + "/api/strategies/" + enc));
    }

    /**
     * 分页查询策略；固定 type=look 时用于盯盘策略列表。返回 PageResult JSON（含 data 数组）。
     */
    public Map<String, Object> strategyPageByType(Integer pageNum, Integer pageSize, String name, String type) {
        UriComponentsBuilder b = UriComponentsBuilder.fromUriString(baseUrl() + "/api/strategies/page");
        b.queryParam("pageNum", pageNum != null && pageNum > 0 ? pageNum : 1);
        b.queryParam("pageSize", pageSize != null && pageSize > 0 ? pageSize : 50);
        if (name != null && !name.isEmpty()) {
            b.queryParam("name", name);
        }
        if (type != null && !type.isEmpty()) {
            b.queryParam("type", type);
        }
        return json.get(URI.create(b.toUriString()));
    }

    public Map<String, Object> marketLookPage(
            Integer pageNum,
            Integer pageSize,
            String executionStatus,
            String symbol,
            String strategyId,
            String detailSummary,
            String startedAtFrom,
            String startedAtTo,
            String endedAtFrom,
            String endedAtTo) {
        UriComponentsBuilder b = UriComponentsBuilder.fromUriString(baseUrl() + "/api/market-look/page");
        if (pageNum != null) {
            b.queryParam("pageNum", pageNum);
        }
        if (pageSize != null) {
            b.queryParam("pageSize", pageSize);
        }
        if (executionStatus != null && !executionStatus.isEmpty()) {
            b.queryParam("execution_status", executionStatus);
        }
        if (symbol != null && !symbol.isEmpty()) {
            b.queryParam("symbol", symbol);
        }
        if (strategyId != null && !strategyId.isEmpty()) {
            b.queryParam("strategy_id", strategyId);
        }
        if (detailSummary != null && !detailSummary.isEmpty()) {
            b.queryParam("detail_summary", detailSummary);
        }
        if (startedAtFrom != null && !startedAtFrom.isEmpty()) {
            b.queryParam("started_at_from", startedAtFrom);
        }
        if (startedAtTo != null && !startedAtTo.isEmpty()) {
            b.queryParam("started_at_to", startedAtTo);
        }
        if (endedAtFrom != null && !endedAtFrom.isEmpty()) {
            b.queryParam("ended_at_from", endedAtFrom);
        }
        if (endedAtTo != null && !endedAtTo.isEmpty()) {
            b.queryParam("ended_at_to", endedAtTo);
        }
        return json.get(URI.create(b.toUriString()));
    }

    public Map<String, Object> marketLookGetById(String id) {
        String enc = URLEncoder.encode(id, StandardCharsets.UTF_8);
        return json.get(URI.create(baseUrl() + "/api/market-look/" + enc));
    }

    /**
     * 删除盯盘任务；成功时 success=true 且 verifiedAbsent=true（服务端 DELETE 后再次 select 确认行已不存在）。
     */
    public Map<String, Object> marketLookDelete(String id) {
        String enc = URLEncoder.encode(id, StandardCharsets.UTF_8);
        return json.delete(URI.create(baseUrl() + "/api/market-look/" + enc));
    }

    /**
     * 更新盯盘任务（部分字段）；PUT /api/market-look/{id}。例如仅传 ended_at 可调整计划截止时间且不结束任务。
     */
    public Map<String, Object> marketLookUpdate(String marketLookId, Map<String, Object> body) {
        String enc = URLEncoder.encode(marketLookId, StandardCharsets.UTF_8);
        return json.putJson(URI.create(baseUrl() + "/api/market-look/" + enc), body);
    }

    /**
     * 结束盯盘任务：PATCH /api/market-look/{id}/end，请求体仅含 ended_at（可选；省略则由服务端使用当前上海时间）。
     */
    public Map<String, Object> marketLookFinishById(String marketLookId, String endedAt) {
        String enc = URLEncoder.encode(marketLookId, StandardCharsets.UTF_8);
        Map<String, Object> body = new LinkedHashMap<>();
        if (endedAt != null && !endedAt.isEmpty()) {
            body.put("ended_at", endedAt);
        }
        return json.patchJson(URI.create(baseUrl() + "/api/market-look/" + enc + "/end"), body.isEmpty() ? Map.of() : body);
    }

    public Map<String, Object> marketLookSql(Map<String, Object> body) {
        return json.postJson(URI.create(baseUrl() + "/api/mcp/market-look/sql"), body);
    }

    /**
     * 固定盯盘容器 {@code aifuturetrade-model-look-1} 最近若干行日志；默认 1000 行，最多 5000（服务端裁剪）。
     */
    public Map<String, Object> lookContainerLogs(Integer tail) {
        UriComponentsBuilder b =
                UriComponentsBuilder.fromUriString(baseUrl() + "/api/mcp/docker/look-container/logs");
        if (tail != null) {
            b.queryParam("tail", tail);
        }
        return json.get(URI.create(b.toUriString()));
    }
}
