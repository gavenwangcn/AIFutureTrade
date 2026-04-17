package com.aifuturetrade.trademonitor.service.impl;

import com.aifuturetrade.trademonitor.dao.mapper.WeChatGroupMapper;
import com.aifuturetrade.trademonitor.entity.WeChatGroupDO;
import com.aifuturetrade.trademonitor.service.WeChatNotificationService;
import com.aifuturetrade.trademonitor.service.WeChatSendOutcome;
import com.aifuturetrade.trademonitor.util.WeChatMarkdownLimiter;
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
import java.util.ArrayList;
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
    public WeChatSendOutcome sendAlert(String alertType, String title, String message) {
        try {
            // 查询启用的微信群配置
            LambdaQueryWrapper<WeChatGroupDO> queryWrapper = new LambdaQueryWrapper<>();
            queryWrapper.eq(WeChatGroupDO::getIsEnabled, true);

            List<WeChatGroupDO> groups = weChatGroupMapper.selectList(queryWrapper);

            if (groups.isEmpty()) {
                log.warn("没有启用的微信群配置，跳过发送通知");
                return WeChatSendOutcome.fail("没有启用的微信群配置，跳过发送通知");
            }

            List<String> failures = new ArrayList<>();
            boolean anyAttempt = false;
            for (WeChatGroupDO group : groups) {
                // 检查告警类型是否匹配
                if (group.getAlertTypes() != null && !group.getAlertTypes().isEmpty()) {
                    if (!group.getAlertTypes().contains(alertType)) {
                        log.debug("群组 {} 不接收 {} 类型的告警，跳过", group.getGroupName(), alertType);
                        continue;
                    }
                }

                anyAttempt = true;
                String err = sendToWebhookError(group.getWebhookUrl(), safeGroupLabel(group), title, message);
                if (err != null) {
                    failures.add(err);
                }
            }

            if (!anyAttempt) {
                return WeChatSendOutcome.ok();
            }
            if (failures.isEmpty()) {
                return WeChatSendOutcome.ok();
            }
            return WeChatSendOutcome.fail(String.join("\n", failures));
        } catch (Exception e) {
            log.error("发送微信告警失败", e);
            return WeChatSendOutcome.fail(
                    "发送微信告警异常: " + e.getClass().getSimpleName() + ": " + (e.getMessage() != null ? e.getMessage() : e.toString()));
        }
    }

    private static String safeGroupLabel(WeChatGroupDO group) {
        if (group == null) {
            return "未知群组";
        }
        String n = group.getGroupName();
        return n != null && !n.isBlank() ? n.trim() : ("id=" + group.getId());
    }

    /**
     * 发送消息到企业微信Webhook
     *
     * @return {@code null} 表示成功，否则为可落库的失败说明（已含群组标签）
     */
    private String sendToWebhookError(String webhookUrl, String groupLabel, String title, String message) {
        try {
            // 构造Markdown格式消息（企微 markdown.content 上限 4096）
            String content = WeChatMarkdownLimiter.clamp(buildMarkdownContent(title, message));

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
                return null;
            }
            String detail = describeWechatResponse(response);
            log.error("微信通知发送失败: group={} {}", groupLabel, detail);
            return "[" + groupLabel + "] " + detail;
        } catch (Exception e) {
            log.error("发送微信通知异常: {}", webhookUrl, e);
            return "[" + groupLabel + "] " + e.getClass().getSimpleName() + ": "
                    + (e.getMessage() != null ? e.getMessage() : e.toString());
        }
    }

    private static String describeWechatResponse(Map<String, Object> response) {
        if (response == null) {
            return "响应为空";
        }
        Object code = response.get("errcode");
        Object msg = response.get("errmsg");
        return "errcode=" + String.valueOf(code) + ", errmsg=" + String.valueOf(msg);
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
