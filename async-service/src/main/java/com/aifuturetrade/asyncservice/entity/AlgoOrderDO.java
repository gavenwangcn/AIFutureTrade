package com.aifuturetrade.asyncservice.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 数据对象：条件订单
 * 对应表名：algo_order
 */
@Data
@TableName("algo_order")
public class AlgoOrderDO implements Serializable {

    private static final long serialVersionUID = 1L;

    @TableId(value = "id", type = IdType.ASSIGN_UUID)
    private String id;

    @TableField("algoId")
    private Long algoId;

    @TableField("clientAlgoId")
    private String clientAlgoId;

    private String type;

    @TableField("algoType")
    private String algoType;

    @TableField("orderType")
    private String orderType;

    private String symbol;

    private String side;

    @TableField("positionSide")
    private String positionSide;

    private Double quantity;

    @TableField("algoStatus")
    private String algoStatus;

    @TableField("triggerPrice")
    private Double triggerPrice;

    private Double price;

    @TableField("error_reason")
    private String errorReason;

    @TableField("model_id")
    private String modelId;

    @TableField("strategy_decision_id")
    private String strategyDecisionId;

    @TableField("trade_id")
    private String tradeId;

    @TableField("created_at")
    private LocalDateTime createdAt;

    @TableField("updated_at")
    private LocalDateTime updatedAt;
}
