package com.aifuturetrade.binanceservice.service.impl;

import com.aifuturetrade.binanceservice.api.binance.BinanceConfig;
import com.aifuturetrade.binanceservice.api.binance.BinanceFuturesClient;
import com.aifuturetrade.binanceservice.indicators.KlineIndicatorCalculator;
import com.aifuturetrade.binanceservice.service.MarketDataService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import jakarta.annotation.PostConstruct;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 市场数据服务实现类
 * 提供币安期货市场数据查询功能
 */
@Slf4j
@Service
public class MarketDataServiceImpl implements MarketDataService {

    /** 未传 limit 时拉取根数（与 trade-mcp 约定一致，满足 MA99 等窗口） */
    private static final int DEFAULT_KLINE_LIMIT_WITH_INDICATORS = 299;

    @Autowired
    private BinanceConfig binanceConfig;

    private BinanceFuturesClient binanceFuturesClient;

    @PostConstruct
    public void init() {
        try {
            binanceFuturesClient = new BinanceFuturesClient(
                    binanceConfig.getApiKey(),
                    binanceConfig.getSecretKey(),
                    binanceConfig.getQuoteAsset(),
                    binanceConfig.getBaseUrl(),
                    binanceConfig.getTestnet()
            );
            log.info("[MarketDataServiceImpl] BinanceFuturesClient初始化成功");
        } catch (Exception e) {
            log.error("[MarketDataServiceImpl] BinanceFuturesClient初始化失败", e);
            throw new RuntimeException("BinanceFuturesClient初始化失败: " + e.getMessage(), e);
        }
    }

    /**
     * 获取指定交易对的24小时价格变动统计
     * 
     * @param symbols 交易对符号列表
     * @return 24小时统计数据
     */
    @Override
    public Map<String, Map<String, Object>> get24hTicker(List<String> symbols) {
        log.debug("[MarketDataServiceImpl] 获取24小时价格变动统计, symbols数量={}", symbols != null ? symbols.size() : 0);
        if (binanceFuturesClient == null) {
            log.error("[MarketDataServiceImpl] BinanceFuturesClient未初始化");
            return new HashMap<>();
        }
        return binanceFuturesClient.get24hTicker(symbols);
    }

    /**
     * 获取指定交易对的实时价格
     * 
     * @param symbols 交易对符号列表
     * @return 实时价格数据
     */
    @Override
    public Map<String, Map<String, Object>> getSymbolPrices(List<String> symbols) {
        log.debug("[MarketDataServiceImpl] 获取实时价格, symbols数量={}", symbols != null ? symbols.size() : 0);
        if (binanceFuturesClient == null) {
            log.error("[MarketDataServiceImpl] BinanceFuturesClient未初始化");
            return new HashMap<>();
        }
        return binanceFuturesClient.getSymbolPrices(symbols);
    }

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
    @Override
    public List<Map<String, Object>> getKlines(String symbol, String interval, Integer limit, 
                                               Long startTime, Long endTime) {
        log.debug("[MarketDataServiceImpl] 获取K线数据, symbol={}, interval={}, limit={}", 
                symbol, interval, limit);
        if (binanceFuturesClient == null) {
            log.error("[MarketDataServiceImpl] BinanceFuturesClient未初始化");
            return List.of();
        }
        return binanceFuturesClient.getKlines(symbol, interval, limit, startTime, endTime);
    }

    @Override
    public Map<String, Object> getKlinesWithIndicators(
            String symbol, String interval, Integer limit, Long startTime, Long endTime) {
        if (binanceFuturesClient == null) {
            log.error("[MarketDataServiceImpl] BinanceFuturesClient未初始化");
            Map<String, Object> err = new HashMap<>();
            err.put("success", false);
            err.put("data", List.of());
            err.put("message", "BinanceFuturesClient未初始化");
            return err;
        }
        int effectiveLimit = limit != null ? limit : DEFAULT_KLINE_LIMIT_WITH_INDICATORS;
        if (effectiveLimit <= 0) {
            effectiveLimit = DEFAULT_KLINE_LIMIT_WITH_INDICATORS;
        } else if (effectiveLimit > 1000) {
            effectiveLimit = 1000;
        }
        log.debug(
                "[MarketDataServiceImpl] 带指标K线, symbol={}, interval={}, limit={} (effective={})",
                symbol,
                interval,
                limit,
                effectiveLimit);
        List<Map<String, Object>> raw = getKlines(symbol, interval, effectiveLimit, startTime, endTime);
        List<Map<String, Object>> rows = new ArrayList<>();
        for (Map<String, Object> m : raw) {
            rows.add(new LinkedHashMap<>(m));
        }
        List<Map<String, Object>> enriched = KlineIndicatorCalculator.enrich(rows);
        Map<String, Object> response = new HashMap<>();
        response.put("success", true);
        response.put("data", enriched);
        if (!rows.isEmpty() && enriched.isEmpty() && rows.size() < KlineIndicatorCalculator.MIN_KLINES_FOR_FULL_INDICATORS) {
            response.put(
                    "indicatorSkipReason",
                    "K线根数 "
                            + rows.size()
                            + " 小于指标计算所需最少 "
                            + KlineIndicatorCalculator.MIN_KLINES_FOR_FULL_INDICATORS
                            + " 根（MA99/EMA99/KDJ 等），未返回带指标的 K 线。请将 limit 设为至少 "
                            + KlineIndicatorCalculator.MIN_KLINES_FOR_FULL_INDICATORS
                            + "（建议 120 或更大）。");
        }
        return response;
    }

    /**
     * 格式化交易对符号
     *
     * @param baseSymbol 基础交易对符号
     * @return 完整交易对符号
     */
    @Override
    public String formatSymbol(String baseSymbol) {
        if (binanceFuturesClient == null) {
            log.error("[MarketDataServiceImpl] BinanceFuturesClient未初始化");
            return baseSymbol;
        }
        return binanceFuturesClient.formatSymbol(baseSymbol);
    }

    /**
     * 获取跌幅榜
     * 注意：binance-service 主要提供币安 API 调用功能
     * 跌幅榜数据应该从数据库获取，建议使用 backend 服务的 /api/market/leaderboard/losers 端点
     * 这里返回空数据以避免错误
     * 
     * @param limit 返回的数据条数限制，可选
     * @return 跌幅榜数据
     */
    @Override
    public Map<String, Object> getMarketLeaderboardLosers(Integer limit) {
        log.warn("[MarketDataServiceImpl] getMarketLeaderboardLosers 被调用，但 binance-service 不提供此功能，建议使用 backend 服务");
        Map<String, Object> result = new HashMap<>();
        result.put("losers", new java.util.ArrayList<>());
        result.put("timestamp", System.currentTimeMillis());
        return result;
    }
}

