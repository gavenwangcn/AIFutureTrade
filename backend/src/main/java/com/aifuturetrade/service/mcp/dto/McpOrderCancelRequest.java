package com.aifuturetrade.service.mcp.dto;

import jakarta.validation.constraints.NotBlank;

public class McpOrderCancelRequest {

    @NotBlank
    private String symbol;

    /**
     * Binance orderId（可选，与 origClientOrderId 二选一）
     */
    private Long orderId;

    /**
     * origClientOrderId（可选，与 orderId 二选一）
     */
    private String origClientOrderId;

    public String getSymbol() {
        return symbol;
    }

    public void setSymbol(String symbol) {
        this.symbol = symbol;
    }

    public Long getOrderId() {
        return orderId;
    }

    public void setOrderId(Long orderId) {
        this.orderId = orderId;
    }

    public String getOrigClientOrderId() {
        return origClientOrderId;
    }

    public void setOrigClientOrderId(String origClientOrderId) {
        this.origClientOrderId = origClientOrderId;
    }
}

