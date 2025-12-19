package com.aifuturetrade.service.dto;

import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 数据传输对象：模型关联策略
 * 用于Service层的数据传输
 */
@Data
public class ModelStrategyDTO implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     * 主键ID
     */
    private String id;

    /**
     * 模型ID
     */
    private String modelId;

    /**
     * 策略ID
     */
    private String strategyId;

    /**
     * 策略类型（buy-买，sell-卖）
     */
    private String type;

    /**
     * 策略优先级，数字越大优先级越高
     */
    private Integer priority;

    /**
     * 创建时间
     */
    private LocalDateTime createdAt;

}

