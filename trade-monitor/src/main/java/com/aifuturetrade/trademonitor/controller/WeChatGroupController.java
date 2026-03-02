package com.aifuturetrade.trademonitor.controller;

import com.aifuturetrade.trademonitor.entity.WeChatGroupDO;
import com.aifuturetrade.trademonitor.service.WeChatGroupService;
import com.baomidou.mybatisplus.core.metadata.IPage;
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
 * 微信群配置管理接口
 */
@Slf4j
@RestController
@RequestMapping("/api/wechat-groups")
@Tag(name = "微信群配置管理", description = "微信群配置的增删改查接口")
public class WeChatGroupController {

    @Autowired
    private WeChatGroupService weChatGroupService;

    @GetMapping
    @Operation(summary = "分页查询微信群配置")
    public ResponseEntity<Map<String, Object>> queryPage(
            @Parameter(description = "页码") @RequestParam(defaultValue = "1") Integer page,
            @Parameter(description = "每页大小") @RequestParam(defaultValue = "10") Integer size,
            @Parameter(description = "群组名称") @RequestParam(required = false) String groupName,
            @Parameter(description = "是否启用") @RequestParam(required = false) Boolean isEnabled
    ) {
        IPage<WeChatGroupDO> result = weChatGroupService.queryPage(page, size, groupName, isEnabled);

        Map<String, Object> response = new HashMap<>();
        response.put("records", result.getRecords());
        response.put("total", result.getTotal());
        response.put("page", result.getCurrent());
        response.put("size", result.getSize());

        return ResponseEntity.ok(response);
    }

    @GetMapping("/enabled")
    @Operation(summary = "查询所有启用的微信群配置")
    public ResponseEntity<List<WeChatGroupDO>> queryEnabledGroups() {
        List<WeChatGroupDO> groups = weChatGroupService.queryEnabledGroups();
        return ResponseEntity.ok(groups);
    }

    @GetMapping("/{id}")
    @Operation(summary = "根据ID查询微信群配置")
    public ResponseEntity<WeChatGroupDO> getById(
            @Parameter(description = "配置ID") @PathVariable Long id
    ) {
        WeChatGroupDO weChatGroup = weChatGroupService.getById(id);
        return ResponseEntity.ok(weChatGroup);
    }

    @PostMapping
    @Operation(summary = "创建微信群配置")
    public ResponseEntity<WeChatGroupDO> create(@RequestBody WeChatGroupDO weChatGroup) {
        WeChatGroupDO created = weChatGroupService.create(weChatGroup);
        return ResponseEntity.ok(created);
    }

    @PutMapping("/{id}")
    @Operation(summary = "更新微信群配置")
    public ResponseEntity<WeChatGroupDO> update(
            @Parameter(description = "配置ID") @PathVariable Long id,
            @RequestBody WeChatGroupDO weChatGroup
    ) {
        WeChatGroupDO updated = weChatGroupService.update(id, weChatGroup);
        return ResponseEntity.ok(updated);
    }

    @DeleteMapping("/{id}")
    @Operation(summary = "删除微信群配置")
    public ResponseEntity<Map<String, Object>> delete(
            @Parameter(description = "配置ID") @PathVariable Long id
    ) {
        weChatGroupService.delete(id);
        Map<String, Object> response = new HashMap<>();
        response.put("success", true);
        response.put("message", "删除成功");
        return ResponseEntity.ok(response);
    }

    @PostMapping("/{id}/test")
    @Operation(summary = "测试发送通知")
    public ResponseEntity<Map<String, Object>> testSend(
            @Parameter(description = "配置ID") @PathVariable Long id
    ) {
        boolean success = weChatGroupService.testSend(id);
        Map<String, Object> response = new HashMap<>();
        response.put("success", success);
        response.put("message", success ? "测试发送成功" : "测试发送失败");
        return ResponseEntity.ok(response);
    }
}
