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
 * 数据对象：账户每日价值记录
 * 对应表名：account_values_daily
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("account_values_daily")
public class AccountValuesDailyDO implements Serializable {

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
     * 账户总值
     */
    private Double balance;

    /**
     * 可用现金
     */
    @TableField("available_balance")
    private Double availableBalance;

    /**
     * 创建时间（UTC+8时区）
     */
    @TableField("created_at")
    private LocalDateTime createdAt;

}
