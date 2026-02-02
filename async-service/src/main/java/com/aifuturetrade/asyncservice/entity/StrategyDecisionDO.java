package com.aifuturetrade.asyncservice.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 数据对象：策略决策
 * 对应表名：strategy_decisions
 */
@Data
@TableName("strategy_decisions")
public class StrategyDecisionDO implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     * 主键ID（UUID格式）
     */
    @TableId(value = "id", type = IdType.ASSIGN_UUID)
    private String id;

    /**
     * 模型ID（UUID格式）
     */
    @TableField("model_id")
    private String modelId;

    /**
     * 一次交易循环ID（用于关联同一轮触发/执行）
     */
    @TableField("cycle_id")
    private String cycleId;

    /**
     * 策略名称
     */
    @TableField("strategy_name")
    private String strategyName;

    /**
     * 策略类型（buy或sell）
     */
    @TableField("strategy_type")
    private String strategyType;

    /**
     * 状态：TRIGGERED/EXECUTED/REJECTED
     */
    private String status;

    /**
     * 交易信号
     */
    @TableField("`signal`")
    private String signal;

    /**
     * 合约名称
     */
    @TableField("`symbol`")
    private String symbol;

    /**
     * 数量
     */
    private BigDecimal quantity;

    /**
     * 杠杆
     */
    private Integer leverage;

    /**
     * 期望价格（可空）
     */
    private BigDecimal price;

    /**
     * 触发价格（可空）
     */
    @TableField("stop_price")
    private BigDecimal stopPrice;

    /**
     * 触发理由（可空）
     */
    private String justification;

    /**
     * 关联的trades.id（当EXECUTED时写入）
     */
    @TableField("trade_id")
    private String tradeId;

    /**
     * 拒绝/失败原因（当REJECTED时写入）
     */
    @TableField("error_reason")
    private String errorReason;

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
