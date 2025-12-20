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
 * 数据对象：投资组合持仓
 * 对应表名：portfolios
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("portfolios")
public class PortfolioDO implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     * 主键ID（UUID格式）
     */
    @TableId(value = "id", type = IdType.ASSIGN_UUID)
    private String id;

    /**
     * 模型ID（UUID格式）
     */
    private String modelId;

    /**
     * 合约符号（如BTCUSDT）
     */
    private String symbol;

    /**
     * 持仓方向（LONG/SHORT）
     */
    private String positionSide;

    /**
     * 持仓数量
     */
    private Double positionAmt;

    /**
     * 平均开仓价格
     */
    private Double avgPrice;

    /**
     * 杠杆倍数
     */
    private Integer leverage;

    /**
     * 未实现盈亏
     */
    private Double unrealizedProfit;

    /**
     * 创建时间
     */
    private LocalDateTime createdAt;

    /**
     * 更新时间
     */
    private LocalDateTime updatedAt;

}

