package com.aifuturetrade.asyncservice.entity;

import lombok.Data;

/**
 * 持仓记录与模型信息的联合查询结果
 */
@Data
public class PortfolioWithModelInfo {
    
    private String modelId;
    private String symbol;
    private String positionSide;
    private Double positionAmt;
    private Double avgPrice;
    private Double initialMargin;
    private Double autoClosePercent;
    private String apiKey;
    private String apiSecret;
}

