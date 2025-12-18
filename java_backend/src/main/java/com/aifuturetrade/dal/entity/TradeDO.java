package com.aifuturetrade.dal.entity;

import com.baomidou.mybatisplus.annotation.IdType;
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
     * 主键ID
     */
    @TableId(value = "id", type = IdType.AUTO)
    private Integer id;

    /**
     * 模型ID
     */
    private Integer modelId;

    /**
     * 合约ID
     */
    private Integer futureId;

    /**
     * 合约符号（如BTC）
     */
    private String future;

    /**
     * 交易信号（buy_to_enter, sell_to_enter, close_position, stop_loss, take_profit）
     */
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
     * 消息
     */
    private String message;

    /**
     * 状态（success, failed）
     */
    private String status;

    /**
     * 交易时间
     */
    private LocalDateTime timestamp;

    /**
     * 创建时间
     */
    private LocalDateTime createdAt;

}