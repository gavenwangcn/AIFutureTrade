package com.aifuturetrade.service.dto;

import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 数据传输对象：合约配置
 * 用于Service层的数据传输
 */
@Data
public class FutureDTO implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     * 主键ID
     */
    private Integer id;

    /**
     * 交易对符号（如BTC）
     */
    private String symbol;

    /**
     * 合约符号（如BTCUSDT）
     */
    private String contractSymbol;

    /**
     * 合约名称（如比特币永续合约）
     */
    private String name;

    /**
     * 交易所（默认BINANCE_FUTURES）
     */
    private String exchange;

    /**
     * 相关链接
     */
    private String link;

    /**
     * 排序顺序
     */
    private Integer sortOrder;

    /**
     * 创建时间
     */
    private LocalDateTime createdAt;

    /**
     * 更新时间
     */
    private LocalDateTime updatedAt;

}