package com.aifuturetrade.binanceservice.service;

import java.util.List;
import java.util.Map;

/**
 * 市场数据服务接口
 * 提供币安期货市场数据查询功能
 */
public interface MarketDataService {

    /**
     * 获取指定交易对的24小时价格变动统计
     * 
     * @param symbols 交易对符号列表
     * @return 24小时统计数据
     */
    Map<String, Map<String, Object>> get24hTicker(List<String> symbols);

    /**
     * 获取指定交易对的实时价格
     * 
     * @param symbols 交易对符号列表
     * @return 实时价格数据
     */
    Map<String, Map<String, Object>> getSymbolPrices(List<String> symbols);

    /**
     * 获取K线数据
     * 
     * @param symbol 交易对符号
     * @param interval K线间隔
     * @param limit 返回的K线数量
     * @param startTime 起始时间戳（毫秒），可选
     * @param endTime 结束时间戳（毫秒），可选
     * @return K线数据列表
     */
    List<Map<String, Object>> getKlines(String symbol, String interval, Integer limit, 
                                         Long startTime, Long endTime);

    /**
     * 格式化交易对符号
     * 
     * @param baseSymbol 基础交易对符号
     * @return 完整交易对符号
     */
    String formatSymbol(String baseSymbol);
}
