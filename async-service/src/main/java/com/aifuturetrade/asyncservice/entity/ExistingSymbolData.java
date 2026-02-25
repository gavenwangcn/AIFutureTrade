package com.aifuturetrade.asyncservice.entity;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * 现有Symbol数据DTO
 * 用于存储从数据库查询的现有symbol的open_price、last_price、update_price_date
 */
@Data
public class ExistingSymbolData {
    /**
     * 交易对符号
     */
    private String symbol;
    
    /**
     * 开盘价（如果为0.0且updatePriceDate为null，则表示不存在）
     */
    private Double openPrice;
    
    /**
     * 最新价格
     */
    private Double lastPrice;
    
    /**
     * 价格更新日期
     */
    private LocalDateTime updatePriceDate;
}

