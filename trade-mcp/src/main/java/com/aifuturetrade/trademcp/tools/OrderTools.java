package com.aifuturetrade.trademcp.tools;

import com.aifuturetrade.trademcp.client.BackendClient;
import org.springframework.stereotype.Component;

import org.springframework.ai.mcp.annotation.McpTool;
import org.springframework.ai.mcp.annotation.McpToolParam;

import java.util.HashMap;
import java.util.Map;

@Component
public class OrderTools {

    private final BackendClient backendClient;

    public OrderTools(BackendClient backendClient) {
        this.backendClient = backendClient;
    }

    @McpTool(name = "trade_order_sell_position", description = "一键平仓（必须传modelId；调用backend controller，落库）")
    public Map<String, Object> sellPosition(
            @McpToolParam(description = "模型ID", required = true) String modelId,
            @McpToolParam(description = "交易对，如BTCUSDT或BTC", required = true) String symbol) {
        return backendClient.sellPosition(modelId, symbol);
    }

    @McpTool(name = "trade_order_create", description = "创建订单（必须传modelId；调用backend controller，落库）")
    public Map<String, Object> create(
            @McpToolParam(description = "模型ID", required = true) String modelId,
            @McpToolParam(description = "交易对", required = true) String symbol,
            @McpToolParam(description = "BUY/SELL", required = true) String side,
            @McpToolParam(description = "订单类型，如 MARKET/STOP/STOP_MARKET/TAKE_PROFIT/TAKE_PROFIT_MARKET", required = true) String type,
            @McpToolParam(description = "数量", required = true) Double quantity,
            @McpToolParam(description = "价格（部分类型需要）", required = false) Double price,
            @McpToolParam(description = "触发价（部分类型需要）", required = false) Double stopPrice,
            @McpToolParam(description = "持仓方向 LONG/SHORT（双向持仓必填）", required = false) String positionSide
    ) {
        Map<String, Object> body = new HashMap<>();
        body.put("symbol", symbol);
        body.put("side", side);
        body.put("type", type);
        body.put("quantity", quantity);
        body.put("price", price);
        body.put("stopPrice", stopPrice);
        body.put("positionSide", positionSide);
        return backendClient.orderCreate(modelId, body);
    }

    @McpTool(name = "trade_order_cancel", description = "撤销订单（必须传modelId；调用backend controller）")
    public Map<String, Object> cancel(
            @McpToolParam(description = "模型ID", required = true) String modelId,
            @McpToolParam(description = "交易对", required = true) String symbol,
            @McpToolParam(description = "订单ID（二选一）", required = false) Long orderId,
            @McpToolParam(description = "客户端订单ID（二选一）", required = false) String origClientOrderId
    ) {
        Map<String, Object> body = new HashMap<>();
        body.put("symbol", symbol);
        body.put("orderId", orderId);
        body.put("origClientOrderId", origClientOrderId);
        return backendClient.orderCancel(modelId, body);
    }

    @McpTool(name = "trade_order_get", description = "查询订单（必须传modelId；调用backend controller）")
    public Map<String, Object> get(
            @McpToolParam(description = "模型ID", required = true) String modelId,
            @McpToolParam(description = "交易对", required = true) String symbol,
            @McpToolParam(description = "订单ID（二选一）", required = false) Long orderId,
            @McpToolParam(description = "客户端订单ID（二选一）", required = false) String origClientOrderId
    ) {
        return backendClient.orderGet(modelId, symbol, orderId, origClientOrderId);
    }

    @McpTool(name = "trade_order_open_orders", description = "查询当前挂单（必须传modelId；调用backend controller）")
    public Map<String, Object> openOrders(
            @McpToolParam(description = "模型ID", required = true) String modelId,
            @McpToolParam(description = "交易对（可选）", required = false) String symbol
    ) {
        return backendClient.openOrders(modelId, symbol);
    }
}

