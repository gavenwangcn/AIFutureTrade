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
 * 数据对象：系统设置
 * 对应表名：settings
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("settings")
public class SettingsDO implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     * 主键ID（UUID格式）
     */
    @TableId(value = "id", type = IdType.ASSIGN_UUID)
    private String id;

    /**
     * 买入交易频率（分钟）
     */
    private Integer buyFrequencyMinutes;

    /**
     * 卖出交易频率（分钟）
     */
    private Integer sellFrequencyMinutes;

    /**
     * 手续费率
     */
    private Double tradingFeeRate;

    /**
     * 是否显示系统提示（1：是，0：否）
     */
    private Boolean showSystemPrompt;

    /**
     * AI对话显示数量限制
     */
    private Integer conversationLimit;

    /**
     * 策略API提供方ID（用于AI生成策略代码）
     */
    @TableField("strategy_provider")
    private String strategyProvider;

    /**
     * 策略API模型名称（用于AI生成策略代码）
     */
    @TableField("strategy_model")
    private String strategyModel;

    /**
     * 策略生成温度参数（temperature）
     */
    @TableField("strategy_temperature")
    private Double strategyTemperature;

    /**
     * 策略生成最大token数（max_tokens）
     */
    @TableField("strategy_max_tokens")
    private Integer strategyMaxTokens;

    /**
     * 策略生成top_p参数
     */
    @TableField("strategy_top_p")
    private Double strategyTopP;

    /**
     * 策略生成top_k参数
     */
    @TableField("strategy_top_k")
    private Integer strategyTopK;

    /**
     * 创建时间
     */
    @TableField("created_at")
    private LocalDateTime createdAt;

    /**
     * 更新时间
     */
    @TableField("updated_at")
    private LocalDateTime updatedAt;

}

