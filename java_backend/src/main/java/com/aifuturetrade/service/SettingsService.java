package com.aifuturetrade.service;

import java.util.Map;

/**
 * 系统设置服务接口
 */
public interface SettingsService {

    /**
     * 获取系统设置
     */
    Map<String, Object> getSettings();

    /**
     * 更新系统设置
     */
    Map<String, Object> updateSettings(Map<String, Object> settings);

}

