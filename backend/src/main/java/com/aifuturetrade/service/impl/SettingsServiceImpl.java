package com.aifuturetrade.service.impl;

import com.aifuturetrade.dao.entity.SettingsDO;
import com.aifuturetrade.dao.mapper.SettingsMapper;
import com.aifuturetrade.service.SettingsService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.Map;

/**
 * 业务逻辑实现类：系统设置
 */
@Slf4j
@Service
public class SettingsServiceImpl implements SettingsService {

    @Autowired
    private SettingsMapper settingsMapper;

    @Override
    public Map<String, Object> getSettings() {
        SettingsDO settings = settingsMapper.selectOne(null);
        if (settings == null) {
            // 如果不存在，创建默认设置
            settings = createDefaultSettings();
        }
        
        Map<String, Object> result = new HashMap<>();
        result.put("buy_frequency_minutes", settings.getBuyFrequencyMinutes());
        result.put("sell_frequency_minutes", settings.getSellFrequencyMinutes());
        result.put("trading_fee_rate", settings.getTradingFeeRate());
        result.put("show_system_prompt", settings.getShowSystemPrompt());
        result.put("conversation_limit", settings.getConversationLimit());
        result.put("trades_display_count", 5); // 从配置读取
        result.put("trades_query_limit", 10); // 从配置读取
        return result;
    }

    @Override
    @Transactional
    public Map<String, Object> updateSettings(Map<String, Object> settingsData) {
        SettingsDO settings = settingsMapper.selectOne(null);
        if (settings == null) {
            settings = createDefaultSettings();
        }
        
        if (settingsData.containsKey("buy_frequency_minutes")) {
            settings.setBuyFrequencyMinutes((Integer) settingsData.get("buy_frequency_minutes"));
        }
        if (settingsData.containsKey("sell_frequency_minutes")) {
            settings.setSellFrequencyMinutes((Integer) settingsData.get("sell_frequency_minutes"));
        }
        if (settingsData.containsKey("trading_fee_rate")) {
            settings.setTradingFeeRate(((Number) settingsData.get("trading_fee_rate")).doubleValue());
        }
        if (settingsData.containsKey("show_system_prompt")) {
            Object value = settingsData.get("show_system_prompt");
            settings.setShowSystemPrompt(value instanceof Boolean ? (Boolean) value : 
                value instanceof Integer ? ((Integer) value) == 1 : 
                "1".equals(String.valueOf(value)) || "true".equalsIgnoreCase(String.valueOf(value)));
        }
        if (settingsData.containsKey("conversation_limit")) {
            settings.setConversationLimit((Integer) settingsData.get("conversation_limit"));
        }
        
        settings.setUpdatedAt(LocalDateTime.now());
        settingsMapper.updateById(settings);
        
        Map<String, Object> result = new HashMap<>();
        result.put("success", true);
        result.put("message", "Settings updated successfully");
        return result;
    }

    private SettingsDO createDefaultSettings() {
        SettingsDO settings = new SettingsDO();
        settings.setBuyFrequencyMinutes(5);
        settings.setSellFrequencyMinutes(5);
        settings.setTradingFeeRate(0.001);
        settings.setShowSystemPrompt(false);
        settings.setConversationLimit(5);
        settings.setCreatedAt(LocalDateTime.now());
        settings.setUpdatedAt(LocalDateTime.now());
        settingsMapper.insert(settings);
        return settings;
    }
}

