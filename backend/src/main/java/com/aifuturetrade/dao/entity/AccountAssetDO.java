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
 * 数据对象：账户资产
 * 对应表名：account_asset
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("account_asset")
public class AccountAssetDO implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     * 账户别名（唯一标识）
     */
    @TableId(value = "account_alias", type = IdType.INPUT)
    private String accountAlias;

    /**
     * 账户名称
     */
    private String accountName;

    /**
     * API密钥
     */
    private String apiKey;

    /**
     * API密钥密码
     */
    private String apiSecret;

    /**
     * 总初始保证金
     */
    private Double totalInitialMargin;

    /**
     * 总维持保证金
     */
    private Double totalMaintMargin;

    /**
     * 总钱包余额
     */
    private Double totalWalletBalance;

    /**
     * 总未实现盈亏
     */
    private Double totalUnrealizedProfit;

    /**
     * 总保证金余额
     */
    private Double totalMarginBalance;

    /**
     * 总持仓初始保证金
     */
    private Double totalPositionInitialMargin;

    /**
     * 总挂单初始保证金
     */
    private Double totalOpenOrderInitialMargin;

    /**
     * 总全仓钱包余额
     */
    private Double totalCrossWalletBalance;

    /**
     * 总全仓未实现盈亏
     */
    private Double totalCrossUnPnl;

    /**
     * 可用余额
     */
    private Double availableBalance;

    /**
     * 最大可提取金额
     */
    private Double maxWithdrawAmount;

    /**
     * 更新时间（毫秒时间戳）
     */
    private Long updateTime;

    /**
     * 创建时间
     */
    private LocalDateTime createdAt;

}

