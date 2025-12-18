package com.aifuturetrade.service.dto;

import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 数据传输对象：策略
 * 用于Service层的数据传输
 */
@Data
public class StrategyDTO implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     * 主键ID
     */
    private String id;

    /**
     * 策略名称
     */
    private String name;

    /**
     * 策略类型（buy-买，sell-卖）
     */
    private String type;

    /**
     * 策略内容
     */
    private String strategyContext;

    /**
     * 策略代码
     */
    private String strategyCode;

    /**
     * 创建时间
     */
    private LocalDateTime createdAt;

    /**
     * 更新时间
     */
    private LocalDateTime updatedAt;

}

