package com.aifuturetrade.service.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;
import java.util.Map;

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
     * 策略类型（buy-买，sell-卖，look-盯盘）
     */
    private String type;

    /**
     * 盯盘策略校验/测试用合约符号（如 BTC 或 BTCUSDT），仅 type=look 时使用
     */
    @JsonProperty("validate_symbol")
    @JsonAlias({"validateSymbol"})
    private String validateSymbol;

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
     * 仅当本次创建由服务端 AI 生成策略代码时回填，便于 MCP/前端展示与复核。
     */
    @JsonProperty("generation_test_passed")
    @JsonInclude(JsonInclude.Include.NON_NULL)
    @JsonAlias({"generationTestPassed"})
    private Boolean generationTestPassed;

    /**
     * 与 {@link #generationTestPassed} 同时出现；结构与「获取代码」测试返回一致。
     */
    @JsonProperty("generation_test_result")
    @JsonInclude(JsonInclude.Include.NON_NULL)
    @JsonAlias({"generationTestResult"})
    private Map<String, Object> generationTestResult;

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

