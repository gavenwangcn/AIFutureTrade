package com.aifuturetrade.service;

import java.util.List;
import java.util.Map;

/**
 * 市场数据服务接口
 */
public interface MarketService {

    /**
     * 获取市场价格（仅返回配置的合约信息）
     */
    Map<String, Map<String, Object>> getMarketPrices();

    /**
     * 获取技术指标
     */
    Map<String, Object> getMarketIndicators(String symbol);

    /**
     * 获取涨幅榜
     */
    Map<String, Object> getMarketLeaderboardGainers(Integer limit);

    /**
     * 获取跌幅榜
     */
    Map<String, Object> getMarketLeaderboardLosers(Integer limit);

    /**
     * 获取涨跌幅榜（已废弃，保留以兼容旧代码）
     */
    Map<String, Object> getMarketLeaderboard(Integer limit, Boolean force);

    /**
     * 获取K线历史数据
     */
    List<Map<String, Object>> getMarketKlines(String symbol, String interval, Integer limit, String startTime, String endTime);

}

