package com.aifuturetrade.trademonitor.service.impl;

import com.aifuturetrade.trademonitor.dao.mapper.AlertRecordMapper;
import com.aifuturetrade.trademonitor.entity.AlertRecordDO;
import com.aifuturetrade.trademonitor.entity.dto.EventNotificationRequest;
import com.aifuturetrade.trademonitor.service.AlertService;
import com.aifuturetrade.trademonitor.service.DockerContainerService;
import com.aifuturetrade.trademonitor.service.WeChatNotificationService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;

/**
 * 告警服务实现类
 */
@Slf4j
@Service
public class AlertServiceImpl implements AlertService {

    @Autowired
    private AlertRecordMapper alertRecordMapper;

    @Autowired
    private WeChatNotificationService weChatNotificationService;

    @Autowired
    private DockerContainerService dockerContainerService;

    @Override
    @Transactional
    public Long handleEvent(EventNotificationRequest request) {
        try {
            log.info("收到事件通知: type={}, service={}, severity={}",
                    request.getEventType(), request.getServiceName(), request.getSeverity());

            // 创建告警记录
            AlertRecordDO alertRecord = new AlertRecordDO();
            alertRecord.setAlertType(request.getEventType());
            alertRecord.setServiceName(request.getServiceName());
            alertRecord.setSeverity(request.getSeverity());
            alertRecord.setTitle(request.getTitle());
            alertRecord.setMessage(request.getMessage());
            alertRecord.setStatus("OPEN");
            alertRecord.setWechatSent(false);
            alertRecord.setCreatedAt(LocalDateTime.now());
            alertRecord.setUpdatedAt(LocalDateTime.now());

            alertRecordMapper.insert(alertRecord);

            // 发送微信通知
            boolean wechatSuccess = weChatNotificationService.sendAlert(
                    request.getEventType(),
                    request.getTitle(),
                    request.getMessage()
            );

            if (wechatSuccess) {
                alertRecord.setWechatSent(true);
                alertRecord.setWechatSentAt(LocalDateTime.now());
                alertRecordMapper.updateById(alertRecord);
            }

            // 执行自动处置
            executeAutoAction(alertRecord);

            return alertRecord.getId();
        } catch (Exception e) {
            log.error("处理事件通知失败", e);
            throw new RuntimeException("处理事件通知失败: " + e.getMessage(), e);
        }
    }

    @Override
    @Transactional
    public boolean handleAlert(Long alertId) {
        try {
            AlertRecordDO alertRecord = alertRecordMapper.selectById(alertId);
            if (alertRecord == null) {
                log.error("告警记录不存在: {}", alertId);
                return false;
            }

            log.info("手动触发告警处置: id={}, type={}", alertId, alertRecord.getAlertType());

            // 执行处置动作
            executeAutoAction(alertRecord);

            return true;
        } catch (Exception e) {
            log.error("手动触发告警处置失败: {}", alertId, e);
            return false;
        }
    }

    /**
     * 执行自动处置动作
     */
    private void executeAutoAction(AlertRecordDO alertRecord) {
        try {
            String alertType = alertRecord.getAlertType();
            String serviceName = alertRecord.getServiceName();

            // 根据告警类型执行不同的处置动作
            if ("TICKER_SYNC_TIMEOUT".equals(alertType)) {
                // Ticker同步超时，重启async-service容器
                log.info("执行自动处置: 重启容器 {}", serviceName);

                boolean success = dockerContainerService.restartContainer(serviceName);

                String action = success ?
                        "已自动重启容器: " + serviceName :
                        "尝试重启容器失败: " + serviceName;

                alertRecord.setActionTaken(action);
                alertRecord.setStatus(success ? "HANDLING" : "OPEN");
                alertRecord.setUpdatedAt(LocalDateTime.now());
                alertRecordMapper.updateById(alertRecord);

                log.info("自动处置完成: {}", action);
            } else {
                log.info("告警类型 {} 无需自动处置", alertType);
            }
        } catch (Exception e) {
            log.error("执行自动处置失败", e);
        }
    }
}
