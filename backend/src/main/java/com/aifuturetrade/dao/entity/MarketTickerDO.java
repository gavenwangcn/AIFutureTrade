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
 * 数据对象：市场Ticker数据
 * 对应表名：24_market_tickers
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("24_market_tickers")
public class MarketTickerDO implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     * 主键ID（自增）
     */
    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    /**
     * 事件时间
     */
    @TableField("event_time")
    private LocalDateTime eventTime;

    /**
     * 交易对符号（如BTCUSDT）
     */
    private String symbol;

    /**
     * 价格变化
     */
    @TableField("price_change")
    private Double priceChange;

    /**
     * 24小时价格变化百分比
     */
    @TableField("price_change_percent")
    private Double priceChangePercent;

    /**
     * 方向（LONG/SHORT）
     */
    private String side;

    /**
     * 变化百分比文本
     */
    @TableField("change_percent_text")
    private String changePercentText;

    /**
     * 平均价格
     */
    @TableField("average_price")
    private Double averagePrice;

    /**
     * 最新价格
     */
    @TableField("last_price")
    private Double lastPrice;

    /**
     * 最后交易量
     */
    @TableField("last_trade_volume")
    private Double lastTradeVolume;

    /**
     * 开盘价
     */
    @TableField("open_price")
    private Double openPrice;

    /**
     * 最高价
     */
    @TableField("high_price")
    private Double highPrice;

    /**
     * 最低价
     */
    @TableField("low_price")
    private Double lowPrice;

    /**
     * 基础成交量
     */
    @TableField("base_volume")
    private Double baseVolume;

    /**
     * 24小时成交量（计价货币）
     */
    @TableField("quote_volume")
    private Double quoteVolume;

    /**
     * 统计开始时间
     */
    @TableField("stats_open_time")
    private LocalDateTime statsOpenTime;

    /**
     * 统计结束时间
     */
    @TableField("stats_close_time")
    private LocalDateTime statsCloseTime;

    /**
     * 第一笔交易ID
     */
    @TableField("first_trade_id")
    private Long firstTradeId;

    /**
     * 最后一笔交易ID
     */
    @TableField("last_trade_id")
    private Long lastTradeId;

    /**
     * 交易数量
     */
    @TableField("trade_count")
    private Long tradeCount;

    /**
     * 数据摄入时间
     */
    @TableField("ingestion_time")
    private LocalDateTime ingestionTime;

    /**
     * 价格更新日期
     */
    @TableField("update_price_date")
    private LocalDateTime updatePriceDate;
}

