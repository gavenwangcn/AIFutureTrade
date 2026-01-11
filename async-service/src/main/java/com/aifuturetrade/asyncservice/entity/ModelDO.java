package com.aifuturetrade.asyncservice.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 数据对象：交易模型（用于自动平仓服务）
 * 对应表名：models
 */
@Data
@TableName("models")
public class ModelDO implements Serializable {

    private static final long serialVersionUID = 1L;

    @TableId(value = "id", type = IdType.ASSIGN_UUID)
    private String id;

    private String name;

    @TableField("provider_id")
    private String providerId;

    @TableField("model_name")
    private String modelName;

    @TableField("initial_capital")
    private Double initialCapital;

    private Integer leverage;

    @TableField("api_key")
    private String apiKey;

    @TableField("api_secret")
    private String apiSecret;

    @TableField("account_alias")
    private String accountAlias;

    @TableField("is_virtual")
    private Boolean isVirtual;

    @TableField("symbol_source")
    private String symbolSource;

    @TableField("trade_type")
    private String tradeType;

    @TableField("max_positions")
    private Integer maxPositions;

    @TableField("auto_buy_enabled")
    private Boolean autoBuyEnabled;

    @TableField("auto_sell_enabled")
    private Boolean autoSellEnabled;

    @TableField("auto_close_percent")
    private Double autoClosePercent;

    @TableField("created_at")
    private LocalDateTime createdAt;
}

