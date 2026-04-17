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
     * @return 发送结果；失败时 {@link WeChatSendOutcome#getErrorDetail()} 含可落库说明
     */
    WeChatSendOutcome sendAlert(String alertType, String title, String message);
}
