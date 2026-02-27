package com.aifuturetrade.trademonitor.controller;

import com.aifuturetrade.trademonitor.dao.mapper.AlertRecordMapper;
import com.aifuturetrade.trademonitor.dao.mapper.WeChatGroupMapper;
import com.aifuturetrade.trademonitor.entity.AlertRecordDO;
import com.aifuturetrade.trademonitor.entity.WeChatGroupDO;
import com.aifuturetrade.trademonitor.service.AlertService;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 告警管理控制器
 */
@Slf4j
@RestController
@RequestMapping("/api/alerts")
@Tag(name = "告警管理", description = "告警记录查询和处理接口")
public class AlertController {

    @Autowired
    private AlertRecordMapper alertRecordMapper;

    @Autowired
    private WeChatGroupMapper weChatGroupMapper;

    @Autowired
    private AlertService alertService;

    @GetMapping
    @Operation(summary = "查询告警记录", description = "分页查询告警记录，支持按类型、服务名、状态过滤")
    public ResponseEntity<Map<String, Object>> getAlerts(
            @Parameter(description = "页码") @RequestParam(defaultValue = "1") Integer page,
            @Parameter(description = "每页大小") @RequestParam(defaultValue = "20") Integer pageSize,
            @Parameter(description = "告警类型") @RequestParam(required = false) String alertType,
            @Parameter(description = "服务名称") @RequestParam(required = false) String serviceName,
            @Parameter(description = "状态") @RequestParam(required = false) String status) {
        try {
            LambdaQueryWrapper<AlertRecordDO> queryWrapper = new LambdaQueryWrapper<>();

            if (alertType != null && !alertType.isEmpty()) {
                queryWrapper.eq(AlertRecordDO::getAlertType, alertType);
            }
            if (serviceName != null && !serviceName.isEmpty()) {
                queryWrapper.eq(AlertRecordDO::getServiceName, serviceName);
            }
            if (status != null && !status.isEmpty()) {
                queryWrapper.eq(AlertRecordDO::getStatus, status);
            }

            queryWrapper.orderByDesc(AlertRecordDO::getCreatedAt);

            Page<AlertRecordDO> pageParam = new Page<>(page, pageSize);
            IPage<AlertRecordDO> result = alertRecordMapper.selectPage(pageParam, queryWrapper);

            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("data", result.getRecords());
            response.put("total", result.getTotal());
            response.put("page", result.getCurrent());
            response.put("pageSize", result.getSize());

            return ResponseEntity.ok(response);
        } catch (Exception e) {
            log.error("查询告警记录失败", e);

            Map<String, Object> response = new HashMap<>();
            response.put("success", false);
            response.put("message", "查询告警记录失败: " + e.getMessage());

            return ResponseEntity.status(500).body(response);
        }
    }

    @PostMapping("/{id}/handle")
    @Operation(summary = "手动触发告警处置", description = "手动触发指定告警的处置动作")
    public ResponseEntity<Map<String, Object>> handleAlert(
            @Parameter(description = "告警ID") @PathVariable Long id) {
        try {
            boolean success = alertService.handleAlert(id);

            Map<String, Object> response = new HashMap<>();
            response.put("success", success);
            response.put("message", success ? "告警处置已触发" : "告警处置失败");

            return ResponseEntity.ok(response);
        } catch (Exception e) {
            log.error("手动触发告警处置失败", e);

            Map<String, Object> response = new HashMap<>();
            response.put("success", false);
            response.put("message", "手动触发告警处置失败: " + e.getMessage());

            return ResponseEntity.status(500).body(response);
        }
    }

    @GetMapping("/wechat-groups")
    @Operation(summary = "查询微信群配置", description = "查询所有微信群配置")
    public ResponseEntity<Map<String, Object>> getWeChatGroups() {
        try {
            List<WeChatGroupDO> groups = weChatGroupMapper.selectList(null);

            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("data", groups);

            return ResponseEntity.ok(response);
        } catch (Exception e) {
            log.error("查询微信群配置失败", e);

            Map<String, Object> response = new HashMap<>();
            response.put("success", false);
            response.put("message", "查询微信群配置失败: " + e.getMessage());

            return ResponseEntity.status(500).body(response);
        }
    }
}
