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
 * 数据对象：策略
 * 对应表名：strategys
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("strategys")
public class StrategyDO implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     * 主键ID
     */
    @TableId(value = "id", type = IdType.ASSIGN_UUID)
    private String id;

    /**
     * 策略名称
     */
    private String name;

    /**
     * 策略类型（buy-买，sell-卖，look-盯盘）
     */
    private String type;

    /**
     * 盯盘策略校验/测试用合约符号（如 BTC、BTCUSDT），仅 type=look 时使用
     */
    @TableField("validate_symbol")
    private String validateSymbol;

    /**
     * 策略内容
     */
    @TableField("strategy_context")
    private String strategyContext;

    /**
     * 策略代码
     */
    @TableField("strategy_code")
    private String strategyCode;

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

