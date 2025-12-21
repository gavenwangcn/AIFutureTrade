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
 * 数据对象：账户价值
 * 对应表名：account_values
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("account_values")
public class AccountValuesDO implements Serializable {

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
     * 账户别名
     */
    private String accountAlias;

    /**
     * 总余额
     */
    private Double balance;

    /**
     * 可用余额
     */
    private Double availableBalance;

    /**
     * 全仓钱包余额
     */
    private Double crossWalletBalance;

    /**
     * 全仓未实现盈亏
     */
    private Double crossUnPnl;

    /**
     * 时间戳
     */
    private LocalDateTime timestamp;

}

