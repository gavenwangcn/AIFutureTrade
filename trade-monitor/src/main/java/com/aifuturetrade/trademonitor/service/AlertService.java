package com.aifuturetrade.trademonitor.service;

import com.aifuturetrade.trademonitor.entity.dto.EventNotificationRequest;

/**
 * 告警服务接口
 */
public interface AlertService {

    /**
     * 处理事件通知
     * @param request 事件通知请求
     * @return 告警记录ID
     */
    Long handleEvent(EventNotificationRequest request);

    /**
     * 手动触发告警处置
     * @param alertId 告警ID
     * @return 是否成功
     */
    boolean handleAlert(Long alertId);
}
