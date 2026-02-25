package com.aifuturetrade.service.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;
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
     * 序列化时使用 snake_case (strategy_context)
     * 反序列化时同时支持 camelCase (strategyContext) 和 snake_case (strategy_context)
     */
    @JsonProperty("strategy_context")
    @JsonAlias({"strategyContext"})
    private String strategyContext;

    /**
     * 策略代码
     * 序列化时使用 snake_case (strategy_code)
     * 反序列化时同时支持 camelCase (strategyCode) 和 snake_case (strategy_code)
     */
    @JsonProperty("strategy_code")
    @JsonAlias({"strategyCode"})
    private String strategyCode;

    /**
     * 创建时间
     * 序列化时使用 snake_case (created_at)
     * 反序列化时同时支持 camelCase (createdAt) 和 snake_case (created_at)
     */
    @JsonProperty("created_at")
    @JsonAlias({"createdAt"})
    private LocalDateTime createdAt;

    /**
     * 更新时间
     * 序列化时使用 snake_case (updated_at)
     * 反序列化时同时支持 camelCase (updatedAt) 和 snake_case (updated_at)
     */
    @JsonProperty("updated_at")
    @JsonAlias({"updatedAt"})
    private LocalDateTime updatedAt;

}

