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
 * 数据对象：交易记录
 * 对应表名：trades
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("trades")
public class TradeDO implements Serializable {

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
     * 合约ID（已废弃，使用future字段）
     */
    @TableField(exist = false)
    private Integer futureId;

    /**
     * 合约符号（如BTC）
     */
    private String future;

    /**
     * 交易信号（buy_to_long, buy_to_short, sell_to_long, sell_to_short, close_position, stop_loss, take_profit）
     */
    @TableField("`signal`")
    private String signal;

    /**
     * 交易价格
     */
    private Double price;

    /**
     * 交易数量
     */
    private Double quantity;

    /**
     * 盈亏金额
     */
    private Double pnl;

    /**
     * 手续费
     */
    private Double fee;

    /**
     * 原始保证金（用于计算盈亏百分比）
     */
    @TableField("initial_margin")
    private Double initialMargin;

    /**
     * 状态（success, failed）
     */
    @TableField(exist = false)
    private String status;

    /**
     * 交易时间
     */
    private LocalDateTime timestamp;

    /**
     * 创建时间（数据库表中不存在此字段，使用timestamp字段）
     */
    @TableField(exist = false)
    private LocalDateTime createdAt;

    /**
     * 系统订单号（从SDK接口返回）
     */
    @TableField("orderId")
    private Long orderId;

    /**
     * 订单类型（从SDK接口返回）
     */
    @TableField("type")
    private String type;

    /**
     * 触发前订单类型（从SDK接口返回）
     */
    @TableField("origType")
    private String origType;

    /**
     * 错误消息（当接口返回错误时记录）
     */
    @TableField("error")
    private String error;

    /**
     * 交易方向（buy/sell）
     */
    @TableField("side")
    private String side;

    /**
     * 持仓方向（LONG/SHORT）
     */
    @TableField("position_side")
    private String positionSide;

    /**
     * 杠杆倍数
     */
    @TableField("leverage")
    private Integer leverage;

    /**
     * 关联的持仓ID（portfolios.id），记录交易时对应的持仓记录
     */
    @TableField("portfolios_id")
    private String portfoliosId;

}