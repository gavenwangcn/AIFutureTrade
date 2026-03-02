package com.aifuturetrade.trademonitor.service.impl;

import com.aifuturetrade.trademonitor.dao.mapper.WeChatGroupMapper;
import com.aifuturetrade.trademonitor.entity.WeChatGroupDO;
import com.aifuturetrade.trademonitor.service.WeChatNotificationService;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 微信通知服务实现类
 */
@Slf4j
@Service
public class WeChatNotificationServiceImpl implements WeChatNotificationService {

    @Autowired
    private WeChatGroupMapper weChatGroupMapper;

    @Autowired
    private RestTemplate restTemplate;

    private static final DateTimeFormatter FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    @Override
    public boolean sendAlert(String alertType, String title, String message) {
        try {
            // 查询启用的微信群配置
            LambdaQueryWrapper<WeChatGroupDO> queryWrapper = new LambdaQueryWrapper<>();
            queryWrapper.eq(WeChatGroupDO::getIsEnabled, true);

            List<WeChatGroupDO> groups = weChatGroupMapper.selectList(queryWrapper);

            if (groups.isEmpty()) {
                log.warn("没有启用的微信群配置，跳过发送通知");
                return false;
            }

            boolean allSuccess = true;
            for (WeChatGroupDO group : groups) {
                // 检查告警类型是否匹配
                if (group.getAlertTypes() != null && !group.getAlertTypes().isEmpty()) {
                    if (!group.getAlertTypes().contains(alertType)) {
                        log.debug("群组 {} 不接收 {} 类型的告警，跳过", group.getGroupName(), alertType);
                        continue;
                    }
                }

                boolean success = sendToWebhook(group.getWebhookUrl(), title, message);
                if (!success) {
                    allSuccess = false;
                }
            }

            return allSuccess;
        } catch (Exception e) {
            log.error("发送微信告警失败", e);
            return false;
        }
    }

    /**
     * 发送消息到企业微信Webhook
     */
    private boolean sendToWebhook(String webhookUrl, String title, String message) {
        try {
            // 构造Markdown格式消息
            String content = buildMarkdownContent(title, message);

            Map<String, Object> requestBody = new HashMap<>();
            requestBody.put("msgtype", "markdown");

            Map<String, String> markdown = new HashMap<>();
            markdown.put("content", content);
            requestBody.put("markdown", markdown);

            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);

            HttpEntity<Map<String, Object>> request = new HttpEntity<>(requestBody, headers);

            Map<String, Object> response = restTemplate.postForObject(webhookUrl, request, Map.class);

            if (response != null && Integer.valueOf(0).equals(response.get("errcode"))) {
                log.info("微信通知发送成功: {}", title);
                return true;
            } else {
                log.error("微信通知发送失败: {}", response);
                return false;
            }
        } catch (Exception e) {
            log.error("发送微信通知异常: {}", webhookUrl, e);
            return false;
        }
    }

    /**
     * 构造Markdown格式内容
     */
    private String buildMarkdownContent(String title, String message) {
        StringBuilder sb = new StringBuilder();
        sb.append("### ").append(title).append("\n\n");
        sb.append("> **时间**: ").append(LocalDateTime.now().format(FORMATTER)).append("\n\n");
        sb.append(message);
        return sb.toString();
    }
}
