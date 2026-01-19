package com.aifuturetrade.asyncservice.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 数据对象：账户每日价值
 * 对应表名：account_values_daily
 */
@Data
@TableName("account_values_daily")
public class AccountValuesDailyDO implements Serializable {

    private static final long serialVersionUID = 1L;

    @TableId(value = "id", type = IdType.ASSIGN_UUID)
    private String id;

    @TableField("model_id")
    private String modelId;

    private Double balance;

    @TableField("available_balance")
    private Double availableBalance;

    @TableField("created_at")
    private LocalDateTime createdAt;
}
