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
     * 交易对符号（如BTCUSDT）
     */
    private String symbol;

    /**
     * 最新价格
     */
    private Double lastPrice;

    /**
     * 24小时价格变化百分比
     */
    private Double priceChangePercent;

    /**
     * 24小时成交量（计价货币）
     */
    private Double quoteVolume;

    /**
     * 事件时间
     */
    private LocalDateTime eventTime;

    /**
     * 方向（LONG/SHORT）
     */
    private String side;

    /**
     * 数据摄入时间
     */
    private LocalDateTime ingestionTime;
}

