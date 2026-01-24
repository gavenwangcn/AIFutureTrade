package com.aifuturetrade.service.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 数据传输对象：交易模型
 * 用于Service层的数据传输
 */
@Data
public class ModelDTO implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     * 主键ID（UUID格式）
     */
    private String id;

    /**
     * 模型名称
     */
    private String name;

    /**
     * 提供方ID（UUID格式）
     * 支持两种命名方式：provider_id（snake_case）和 providerId（camelCase）
     */
    @JsonProperty("provider_id")
    @JsonAlias({"providerId"})
    private String providerId;

    /**
     * 模型名称（如gpt-3.5-turbo）
     * 支持两种命名方式：model_name（snake_case）和 modelName（camelCase）
     */
    @JsonProperty("model_name")
    @JsonAlias({"modelName"})
    private String modelName;

    /**
     * 初始资金
     */
    private Double initialCapital;

    /**
     * 杠杆倍数
     */
    private Integer leverage;

    /**
     * API密钥
     */
    private String apiKey;

    /**
     * API密钥密码
     */
    private String apiSecret;

    /**
     * 账户别名
     */
    private String accountAlias;

    /**
     * 是否虚拟账户（1：是，0：否）
     */
    private Boolean isVirtual;

    /**
     * 交易对数据源（leaderboard或future）
     */
    private String symbolSource;

    /**
     * 交易类型（ai或strategy）
     */
    private String tradeType;

    /**
     * 最大持仓数量
     * 支持两种命名方式：max_positions（snake_case）和 maxPositions（camelCase）
     */
    @JsonProperty("max_positions")
    @JsonAlias({"maxPositions"})
    private Integer maxPositions;

    /**
     * 买入批次大小
     * 支持两种命名方式：buy_batch_size（snake_case）和 buyBatchSize（camelCase）
     */
    @JsonProperty("buy_batch_size")
    @JsonAlias({"buyBatchSize"})
    private Integer buyBatchSize;

    /**
     * 买入批次执行间隔（秒）
     * 支持两种命名方式：buy_batch_execution_interval（snake_case）和 buyBatchExecutionInterval（camelCase）
     */
    @JsonProperty("buy_batch_execution_interval")
    @JsonAlias({"buyBatchExecutionInterval"})
    private Integer buyBatchExecutionInterval;

    /**
     * 买入批次执行组大小
     * 支持两种命名方式：buy_batch_execution_group_size（snake_case）和 buyBatchExecutionGroupSize（camelCase）
     */
    @JsonProperty("buy_batch_execution_group_size")
    @JsonAlias({"buyBatchExecutionGroupSize"})
    private Integer buyBatchExecutionGroupSize;

    /**
     * 卖出批次大小
     * 支持两种命名方式：sell_batch_size（snake_case）和 sellBatchSize（camelCase）
     */
    @JsonProperty("sell_batch_size")
    @JsonAlias({"sellBatchSize"})
    private Integer sellBatchSize;

    /**
     * 卖出批次执行间隔（秒）
     * 支持两种命名方式：sell_batch_execution_interval（snake_case）和 sellBatchExecutionInterval（camelCase）
     */
    @JsonProperty("sell_batch_execution_interval")
    @JsonAlias({"sellBatchExecutionInterval"})
    private Integer sellBatchExecutionInterval;

    /**
     * 卖出批次执行组大小
     * 支持两种命名方式：sell_batch_execution_group_size（snake_case）和 sellBatchExecutionGroupSize（camelCase）
     */
    @JsonProperty("sell_batch_execution_group_size")
    @JsonAlias({"sellBatchExecutionGroupSize"})
    private Integer sellBatchExecutionGroupSize;

    /**
     * 是否自动买入（1：是，0：否）
     */
    private Boolean autoBuyEnabled;

    /**
     * 是否自动卖出（1：是，0：否）
     */
    private Boolean autoSellEnabled;

    /**
     * 自动平仓百分比（当损失本金达到此百分比时自动平仓）
     * 支持两种命名方式：auto_close_percent（snake_case）和 autoClosePercent（camelCase）
     */
    @JsonProperty("auto_close_percent")
    @JsonAlias({"autoClosePercent"})
    private Double autoClosePercent;

    /**
     * 每日成交量过滤阈值（以千万为单位），NULL表示不过滤
     * 支持两种命名方式：base_volume（snake_case）和 baseVolume（camelCase）
     * 兼容旧字段名：quote_volume（snake_case）和 quoteVolume（camelCase）
     */
    @JsonProperty("base_volume")
    @JsonAlias({"baseVolume", "quote_volume", "quoteVolume"})
    private Double baseVolume;

    /**
     * 目标每日收益率（百分比），NULL表示不限制
     * 支持两种命名方式：daily_return（snake_case）和 dailyReturn（camelCase）
     */
    @JsonProperty("daily_return")
    @JsonAlias({"dailyReturn"})
    private Double dailyReturn;

    /**
     * 连续亏损次数阈值，达到此值后暂停买入交易，NULL表示不限制
     * 支持两种命名方式：losses_num（snake_case）和 lossesNum（camelCase）
     */
    @JsonProperty("losses_num")
    @JsonAlias({"lossesNum"})
    private Integer lossesNum;

    /**
     * 创建时间
     */
    private LocalDateTime createdAt;

    /**
     * 更新时间
     */
    private LocalDateTime updatedAt;

}