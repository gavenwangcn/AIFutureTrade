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
 * 交易通知表 trade_notify（盯盘等落库，独立于 alert_records）
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("trade_notify")
public class TradeNotifyDO implements Serializable {

    private static final long serialVersionUID = 1L;

    public static final String TYPE_LOOK = "LOOK";

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    @TableField("notify_type")
    private String notifyType;

    @TableField("market_look_id")
    private String marketLookId;

    @TableField("strategy_id")
    private String strategyId;

    @TableField("strategy_name")
    private String strategyName;

    private String symbol;

    private String title;

    private String message;

    @TableField("extra_json")
    private String extraJson;

    @TableField("created_at")
    private LocalDateTime createdAt;
}
