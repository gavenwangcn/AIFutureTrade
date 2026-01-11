package com.aifuturetrade.asyncservice.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 数据对象：投资组合持仓（用于自动平仓服务）
 * 对应表名：portfolios
 */
@Data
@TableName("portfolios")
public class PortfolioDO implements Serializable {

    private static final long serialVersionUID = 1L;

    @TableId(value = "id", type = IdType.ASSIGN_UUID)
    private String id;

    @TableField("model_id")
    private String modelId;

    private String symbol;

    @TableField("position_side")
    private String positionSide;

    @TableField("position_amt")
    private Double positionAmt;

    @TableField("avg_price")
    private Double avgPrice;

    private Integer leverage;

    @TableField("initial_margin")
    private Double initialMargin;

    @TableField("unrealized_profit")
    private Double unrealizedProfit;

    @TableField("created_at")
    private LocalDateTime createdAt;

    @TableField("updated_at")
    private LocalDateTime updatedAt;
}

