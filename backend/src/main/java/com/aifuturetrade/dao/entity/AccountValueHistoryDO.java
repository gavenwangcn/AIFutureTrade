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
     * 账户别名
     */
    @TableField("account_alias")
    private String accountAlias;

    /**
     * 总余额
     */
    private Double balance;

    /**
     * 可用余额
     */
    @TableField("available_balance")
    private Double availableBalance;

    /**
     * 全仓钱包余额
     */
    @TableField("cross_wallet_balance")
    private Double crossWalletBalance;

    /**
     * 全仓未实现盈亏
     */
    @TableField("cross_un_pnl")
    private Double crossUnPnl;

    /**
     * 时间戳
     */
    private LocalDateTime timestamp;

}

