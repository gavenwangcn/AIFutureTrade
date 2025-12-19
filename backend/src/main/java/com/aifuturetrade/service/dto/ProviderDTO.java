package com.aifuturetrade.service.dto;

import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 数据传输对象：API提供方
 * 用于Service层的数据传输
 */
@Data
public class ProviderDTO implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     * 主键ID
     */
    private Integer id;

    /**
     * 提供方名称
     */
    private String name;

    /**
     * API URL
     */
    private String apiUrl;

    /**
     * API密钥
     */
    private String apiKey;

    /**
     * 支持的模型列表（逗号分隔）
     */
    private String models;

    /**
     * 提供方类型（openai、deepseek等）
     */
    private String providerType;

    /**
     * 创建时间
     */
    private LocalDateTime createdAt;

    /**
     * 更新时间
     */
    private LocalDateTime updatedAt;

}