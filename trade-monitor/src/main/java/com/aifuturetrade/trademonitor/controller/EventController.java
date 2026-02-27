package com.aifuturetrade.trademonitor.controller;

import com.aifuturetrade.trademonitor.entity.dto.EventNotificationRequest;
import com.aifuturetrade.trademonitor.service.AlertService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.Map;

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
    public ResponseEntity<Map<String, Object>> notifyEvent(@RequestBody EventNotificationRequest request) {
        try {
            log.info("接收到事件通知: {}", request);

            Long alertId = alertService.handleEvent(request);

            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("alertId", alertId);
            response.put("message", "事件通知已接收并处理");

            return ResponseEntity.ok(response);
        } catch (Exception e) {
            log.error("处理事件通知失败", e);

            Map<String, Object> response = new HashMap<>();
            response.put("success", false);
            response.put("message", "处理事件通知失败: " + e.getMessage());

            return ResponseEntity.status(500).body(response);
        }
    }
}
