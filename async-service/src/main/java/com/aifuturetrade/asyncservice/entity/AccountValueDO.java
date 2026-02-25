package com.aifuturetrade.asyncservice.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 数据对象：账户价值
 * 对应表名：account_values
 */
@Data
@TableName("account_values")
public class AccountValueDO implements Serializable {

    private static final long serialVersionUID = 1L;

    @TableId(value = "id", type = IdType.ASSIGN_UUID)
    private String id;

    @TableField("model_id")
    private String modelId;

    @TableField("account_alias")
    private String accountAlias;

    private Double balance;

    @TableField("available_balance")
    private Double availableBalance;

    @TableField("cross_wallet_balance")
    private Double crossWalletBalance;

    @TableField("cross_pnl")
    private Double crossPnl;

    @TableField("cross_un_pnl")
    private Double crossUnPnl;

    private LocalDateTime timestamp;
}
