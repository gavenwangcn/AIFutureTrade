package com.aifuturetrade.asyncservice.entity;

import lombok.Data;
import lombok.experimental.Accessors;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 数据对象：市场Ticker数据
 * 对应表名：24_market_tickers
 */
@Data
@Accessors(chain = true)
public class MarketTickerDO implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     * 主键ID（自增）
     */
    private Long id;

    /**
     * 事件时间
     */
    private LocalDateTime eventTime;

    /**
     * 交易对符号（如BTCUSDT）
     */
    private String symbol;

    /**
     * 价格变化
     */
    private Double priceChange;

    /**
     * 24小时价格变化百分比
     */
    private Double priceChangePercent;

    /**
     * 方向（LONG/SHORT）
     */
    private String side;

    /**
     * 变化百分比文本
     */
    private String changePercentText;

    /**
     * 平均价格
     */
    private Double averagePrice;

    /**
     * 最新价格
     */
    private Double lastPrice;

    /**
     * 最后交易量
     */
    private Double lastTradeVolume;

    /**
     * 开盘价
     */
    private Double openPrice;

    /**
     * 最高价
     */
    private Double highPrice;

    /**
     * 最低价
     */
    private Double lowPrice;

    /**
     * 基础成交量
     */
    private Double baseVolume;

    /**
     * 24小时成交量（计价货币）
     */
    private Double quoteVolume;

    /**
     * 统计开始时间
     */
    private LocalDateTime statsOpenTime;

    /**
     * 统计结束时间
     */
    private LocalDateTime statsCloseTime;

    /**
     * 第一笔交易ID
     */
    private Long firstTradeId;

    /**
     * 最后一笔交易ID
     */
    private Long lastTradeId;

    /**
     * 交易数量
     */
    private Long tradeCount;

    /**
     * 数据摄入时间
     */
    private LocalDateTime ingestionTime;

    /**
     * 价格更新日期
     */
    private LocalDateTime updatePriceDate;
}
