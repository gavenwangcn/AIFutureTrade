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
 * 数据对象：账户价值历史记录
 * 对应表名：account_value_historys
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("account_value_historys")
public class AccountValueHistoryDO implements Serializable {

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

