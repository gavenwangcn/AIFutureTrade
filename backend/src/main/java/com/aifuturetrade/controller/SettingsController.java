package com.aifuturetrade.controller;

import com.aifuturetrade.service.SettingsService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * 控制器：系统设置
 */
@RestController
@RequestMapping("/api/settings")
@Tag(name = "系统设置管理", description = "系统设置管理接口")
public class SettingsController {

    @Autowired
    private SettingsService settingsService;

    /**
     * 获取系统设置
     */
    @GetMapping
    @Operation(summary = "获取系统设置")
    public ResponseEntity<Map<String, Object>> getSettings() {
        Map<String, Object> settings = settingsService.getSettings();
        return new ResponseEntity<>(settings, HttpStatus.OK);
    }

    /**
     * 更新系统设置
     */
    @PutMapping
    @Operation(summary = "更新系统设置")
    public ResponseEntity<Map<String, Object>> updateSettings(@RequestBody Map<String, Object> settingsData) {
        Map<String, Object> result = settingsService.updateSettings(settingsData);
        return new ResponseEntity<>(result, HttpStatus.OK);
    }
}

