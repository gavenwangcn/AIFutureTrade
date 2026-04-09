package com.aifuturetrade.service.mcp.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

/**
 * MCP 下单请求（细粒度，对齐 Binance Futures 常用字段）
 */
public class McpOrderCreateRequest {

    @NotBlank
    private String symbol;

    /**
     * BUY / SELL
     */
    @NotBlank
    private String side;

    /**
     * MARKET / LIMIT / STOP / STOP_MARKET / TAKE_PROFIT / TAKE_PROFIT_MARKET / ...
     */
    @NotBlank
    private String type;

    @NotNull
    private Double quantity;

    /**
     * LIMIT / STOP / TAKE_PROFIT 等可能需要
     */
    private Double price;

    /**
     * STOP / TAKE_PROFIT 等触发价
     */
    private Double stopPrice;

    /**
     * LONG / SHORT
     */
    private String positionSide;

    /**
     * 对于 closePosition 类订单，是否平仓（可选）
     */
    private Boolean closePosition;

    public String getSymbol() {
        return symbol;
    }

    public void setSymbol(String symbol) {
        this.symbol = symbol;
    }

    public String getSide() {
        return side;
    }

    public void setSide(String side) {
        this.side = side;
    }

    public String getType() {
        return type;
    }

    public void setType(String type) {
        this.type = type;
    }

    public Double getQuantity() {
        return quantity;
    }

    public void setQuantity(Double quantity) {
        this.quantity = quantity;
    }

    public Double getPrice() {
        return price;
    }

    public void setPrice(Double price) {
        this.price = price;
    }

    public Double getStopPrice() {
        return stopPrice;
    }

    public void setStopPrice(Double stopPrice) {
        this.stopPrice = stopPrice;
    }

    public String getPositionSide() {
        return positionSide;
    }

    public void setPositionSide(String positionSide) {
        this.positionSide = positionSide;
    }

    public Boolean getClosePosition() {
        return closePosition;
    }

    public void setClosePosition(Boolean closePosition) {
        this.closePosition = closePosition;
    }
}

