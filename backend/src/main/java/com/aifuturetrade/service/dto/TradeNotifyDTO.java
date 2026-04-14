package com.aifuturetrade.service.dto;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * 交易通知 trade_notify 对外 DTO
 */
@Data
public class TradeNotifyDTO {

    private Long id;
    private String notifyType;
    private String marketLookId;
    private String strategyId;
    private String strategyName;
    private String symbol;
    private String title;
    private String message;
    /** JSON 字符串 */
    private String extraJson;
    private LocalDateTime createdAt;
}
