package com.aifuturetrade.controller;

import com.aifuturetrade.service.SettingsService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
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
@Api(tags = "系统设置管理")
public class SettingsController {

    @Autowired
    private SettingsService settingsService;

    /**
     * 获取系统设置
     */
    @GetMapping
    @ApiOperation("获取系统设置")
    public ResponseEntity<Map<String, Object>> getSettings() {
        Map<String, Object> settings = settingsService.getSettings();
        return new ResponseEntity<>(settings, HttpStatus.OK);
    }

    /**
     * 更新系统设置
     */
    @PutMapping
    @ApiOperation("更新系统设置")
    public ResponseEntity<Map<String, Object>> updateSettings(@RequestBody Map<String, Object> settingsData) {
        Map<String, Object> result = settingsService.updateSettings(settingsData);
        return new ResponseEntity<>(result, HttpStatus.OK);
    }
}

