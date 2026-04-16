package com.aifuturetrade.trademonitor.controller;

import com.aifuturetrade.trademonitor.entity.dto.EventNotificationRequest;
import com.aifuturetrade.trademonitor.service.AlertService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 事件接收控制器
 */
@Slf4j
@RestController
@RequestMapping("/api/events")
@Tag(name = "事件管理", description = "事件通知接收接口")
public class EventController {

    @Autowired
    private AlertService alertService;

    @PostMapping("/notify")
    @Operation(summary = "接收事件通知", description = "接收其他服务的异常事件通知")
    public ResponseEntity<Map<String, Object>> notifyEvent(
            @RequestBody EventNotificationRequest request,
            HttpServletRequest httpRequest) {
        try {
            String metaKeys = "-";
            if (request.getMetadata() != null && !request.getMetadata().isEmpty()) {
                Set<String> keys = request.getMetadata().keySet();
                metaKeys = keys.stream().sorted().collect(Collectors.joining(","));
            }
            String msgPreview = request.getMessage() == null ? "" : request.getMessage();
            if (msgPreview.length() > 500) {
                msgPreview = msgPreview.substring(0, 500) + "...(truncated)";
            }
            log.info(
                    "[trade-monitor][EventNotify] 已解析 JSON 请求体 | client={} | eventType={} | serviceName={} | severity={} | "
                            + "title={} | messageLen={} | messagePreview={} | metadataKeys=[{}]",
                    httpRequest.getRemoteAddr(),
                    request.getEventType(),
                    request.getServiceName(),
                    request.getSeverity(),
                    request.getTitle(),
                    request.getMessage() != null ? request.getMessage().length() : 0,
                    msgPreview,
                    metaKeys);

            Long alertId = alertService.handleEvent(request);

            log.info(
                    "[trade-monitor][EventNotify] 处理完成 | alertId={} | eventType={} | serviceName={}",
                    alertId,
                    request.getEventType(),
                    request.getServiceName());

            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("alertId", alertId);
            response.put("message", "事件通知已接收并处理");

            return ResponseEntity.ok(response);
        } catch (Exception e) {
            log.error(
                    "[trade-monitor][EventNotify] 处理失败 | client={} | error={}",
                    httpRequest != null ? httpRequest.getRemoteAddr() : "-",
                    e.getMessage(),
                    e);

            Map<String, Object> response = new HashMap<>();
            response.put("success", false);
            response.put("message", "处理事件通知失败: " + e.getMessage());

            return ResponseEntity.status(500).body(response);
        }
    }
}
