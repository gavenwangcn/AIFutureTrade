package com.aifuturetrade.trademonitor.service;

/**
 * 微信通知服务接口
 */
public interface WeChatNotificationService {

    /**
     * 发送告警通知到微信群
     * @param alertType 告警类型
     * @param title 标题
     * @param message 消息内容
     * @return 是否发送成功
     */
    boolean sendAlert(String alertType, String title, String message);
}
