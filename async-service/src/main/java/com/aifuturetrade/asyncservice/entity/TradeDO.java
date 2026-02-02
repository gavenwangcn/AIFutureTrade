package com.aifuturetrade.asyncservice.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 数据对象：交易记录
 * 对应表名：trades
 */
@Data
@TableName("trades")
public class TradeDO implements Serializable {

    private static final long serialVersionUID = 1L;

    @TableId(value = "id", type = IdType.ASSIGN_UUID)
    private String id;

    @TableField("model_id")
    private String modelId;

    private String future;

    private String signal;

    private Double quantity;

    private Double price;

    private Integer leverage;

    private String side;

    @TableField("position_side")
    private String positionSide;

    private Double pnl;

    private Double fee;

    @TableField("initial_margin")
    private Double initialMargin;

    @TableField("strategy_decision_id")
    private String strategyDecisionId;

    @TableField("orderId")
    private Long orderId;

    private String type;

    @TableField("origType")
    private String origType;

    private String error;

    private LocalDateTime timestamp;
}
