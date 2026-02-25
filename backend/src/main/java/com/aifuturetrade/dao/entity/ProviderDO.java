package com.aifuturetrade.dao.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.experimental.Accessors;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 数据对象：API提供方
 * 对应表名：providers
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("providers")
public class ProviderDO implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     * 主键ID（UUID格式）
     */
    @TableId(value = "id", type = IdType.ASSIGN_UUID)
    private String id;

    /**
     * 提供方名称
     */
    private String name;

    /**
     * API URL
     */
    @TableField(value = "api_url", insertStrategy = com.baomidou.mybatisplus.annotation.FieldStrategy.IGNORED)
    private String apiUrl;

    /**
     * API密钥
     */
    @TableField(value = "api_key", insertStrategy = com.baomidou.mybatisplus.annotation.FieldStrategy.IGNORED)
    private String apiKey;

    /**
     * 支持的模型列表（逗号分隔）
     */
    private String models;

    /**
     * 提供方类型（openai、deepseek等）
     */
    @TableField("provider_type")
    private String providerType;

    /**
     * 创建时间
     */
    @TableField("created_at")
    private LocalDateTime createdAt;

    /**
     * 更新时间
     * 注意：数据库表中不存在此字段，使用 @TableField(exist = false) 标记
     */
    @TableField(exist = false)
    private LocalDateTime updatedAt;

}