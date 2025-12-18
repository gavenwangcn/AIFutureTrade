package com.aifuturetrade.dal.entity;

import com.baomidou.mybatisplus.annotation.IdType;
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
     * 主键ID
     */
    @TableId(value = "id", type = IdType.AUTO)
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