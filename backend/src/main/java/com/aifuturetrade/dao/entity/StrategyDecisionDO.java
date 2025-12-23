package com.aifuturetrade.dao.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.experimental.Accessors;

import java.io.Serializable;
import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 数据对象：策略决策
 * 对应表名：strategy_decisions
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
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
     * 交易信号
     */
    private String signal;

    /**
     * 合约名称
     */
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
     * 创建时间
     */
    @TableField("created_at")
    private LocalDateTime createdAt;

}

