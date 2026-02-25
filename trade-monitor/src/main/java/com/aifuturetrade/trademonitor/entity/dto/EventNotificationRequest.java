package com.aifuturetrade.trademonitor.entity.dto;

import lombok.Data;

import java.util.Map;

/**
 * 事件通知请求DTO
 */
@Data
public class EventNotificationRequest {

    /**
     * 事件类型
     */
    private String eventType;

    /**
     * 服务名称
     */
    private String serviceName;

    /**
     * 严重程度(INFO,WARNING,ERROR,CRITICAL)
     */
    private String severity;

    /**
     * 告警标题
     */
    private String title;

    /**
     * 告警详细信息
     */
    private String message;

    /**
     * 元数据
     */
    private Map<String, Object> metadata;
}
