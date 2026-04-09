package com.aifuturetrade.service.mcp;

import com.aifuturetrade.service.mcp.dto.McpOrderCancelRequest;
import com.aifuturetrade.service.mcp.dto.McpOrderCreateRequest;

import java.util.List;
import java.util.Map;

public interface McpBinanceFuturesOrderService {

    Map<String, Object> create(String modelId, McpOrderCreateRequest request);

    Map<String, Object> cancel(String modelId, McpOrderCancelRequest request);

    Map<String, Object> get(String modelId, String symbol, Long orderId, String origClientOrderId);

    List<Map<String, Object>> openOrders(String modelId, String symbol);

    Map<String, Object> sellPosition(String modelId, String symbol);
}

