package com.aifuturetrade.dao.entity;

import com.baomidou.mybatisplus.annotation.IdType;
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
     * 主键ID
     */
    @TableId(value = "id", type = IdType.AUTO)
    private Integer id;

    /**
     * 模型名称
     */
    private String name;

    /**
     * 提供方ID
     */
    private Integer providerId;

    /**
     * 模型名称（如gpt-3.5-turbo）
     */
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
     * 最大持仓数量
     */
    private Integer maxPositions;

    /**
     * 买入批次大小
     */
    private Integer buyBatchSize;

    /**
     * 买入批次执行间隔（秒）
     */
    private Integer buyBatchExecutionInterval;

    /**
     * 买入批次执行组大小
     */
    private Integer buyBatchExecutionGroupSize;

    /**
     * 卖出批次大小
     */
    private Integer sellBatchSize;

    /**
     * 卖出批次执行间隔（秒）
     */
    private Integer sellBatchExecutionInterval;

    /**
     * 卖出批次执行组大小
     */
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
     * 创建时间
     */
    private LocalDateTime createdAt;

    /**
     * 更新时间
     */
    private LocalDateTime updatedAt;

}