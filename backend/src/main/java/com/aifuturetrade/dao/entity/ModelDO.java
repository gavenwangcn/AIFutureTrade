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
 * 数据对象：交易模型
 * 对应表名：models
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("models")
public class ModelDO implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     * 主键ID（UUID格式）
     */
    @TableId(value = "id", type = IdType.ASSIGN_UUID)
    private String id;

    /**
     * 模型名称
     */
    private String name;

    /**
     * 提供方ID（UUID格式）
     */
    @TableField("provider_id")
    private String providerId;

    /**
     * 模型名称（如gpt-3.5-turbo）
     */
    @TableField("model_name")
    private String modelName;

    /**
     * 初始资金
     */
    @TableField("initial_capital")
    private Double initialCapital;

    /**
     * 杠杆倍数
     */
    private Integer leverage;

    /**
     * API密钥
     */
    @TableField("api_key")
    private String apiKey;

    /**
     * API密钥密码
     */
    @TableField("api_secret")
    private String apiSecret;

    /**
     * 账户别名
     */
    @TableField("account_alias")
    private String accountAlias;

    /**
     * 是否虚拟账户（1：是，0：否）
     */
    @TableField("is_virtual")
    private Boolean isVirtual;

    /**
     * 交易对数据源（leaderboard或future）
     */
    @TableField("symbol_source")
    private String symbolSource;

    /**
     * 交易类型（ai或strategy）
     */
    @TableField("trade_type")
    private String tradeType;

    /**
     * 最大持仓数量
     */
    @TableField("max_positions")
    private Integer maxPositions;

    /**
     * 买入批次大小
     */
    @TableField("buy_batch_size")
    private Integer buyBatchSize;

    /**
     * 买入批次执行间隔（秒）
     */
    @TableField("buy_batch_execution_interval")
    private Integer buyBatchExecutionInterval;

    /**
     * 买入批次执行组大小
     */
    @TableField("buy_batch_execution_group_size")
    private Integer buyBatchExecutionGroupSize;

    /**
     * 卖出批次大小
     */
    @TableField("sell_batch_size")
    private Integer sellBatchSize;

    /**
     * 卖出批次执行间隔（秒）
     */
    @TableField("sell_batch_execution_interval")
    private Integer sellBatchExecutionInterval;

    /**
     * 卖出批次执行组大小
     */
    @TableField("sell_batch_execution_group_size")
    private Integer sellBatchExecutionGroupSize;

    /**
     * 是否自动买入（1：是，0：否）
     */
    @TableField("auto_buy_enabled")
    private Boolean autoBuyEnabled;

    /**
     * 是否自动卖出（1：是，0：否）
     */
    @TableField("auto_sell_enabled")
    private Boolean autoSellEnabled;

    /**
     * 自动平仓百分比（当损失本金达到此百分比时自动平仓）
     */
    @TableField("auto_close_percent")
    private Double autoClosePercent;

    /**
     * 每日成交量过滤阈值（以千万为单位），NULL表示不过滤
     */
    @TableField("base_volume")
    private Double baseVolume;

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