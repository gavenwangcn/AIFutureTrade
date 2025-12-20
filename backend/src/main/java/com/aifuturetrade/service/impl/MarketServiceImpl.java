package com.aifuturetrade.service.impl;

import com.aifuturetrade.common.api.binance.BinanceConfig;
import com.aifuturetrade.common.api.binance.BinanceFuturesClient;
import com.aifuturetrade.dao.mapper.FutureMapper;
import com.aifuturetrade.dao.mapper.MarketTickerMapper;
import com.aifuturetrade.service.MarketService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 业务逻辑实现类：市场数据服务
 */
@Slf4j
@Service
public class MarketServiceImpl implements MarketService {

    @Autowired
    private FutureMapper futureMapper;

    @Autowired
    private MarketTickerMapper marketTickerMapper;

    @Autowired
    private BinanceConfig binanceConfig;

    private BinanceFuturesClient futuresClient;

    @Value("${app.kline-data-source:sdk}")
    private String klineDataSource;

    @Value("${app.leaderboard-refresh:10}")
    private Integer leaderboardRefresh;

    /**
     * 初始化 Binance Futures Client
     */
    private BinanceFuturesClient getFuturesClient() {
        if (futuresClient == null) {
            futuresClient = new BinanceFuturesClient(
                    binanceConfig.getApiKey(),
                    binanceConfig.getSecretKey(),
                    binanceConfig.getQuoteAsset(),
                    binanceConfig.getBaseUrl(),
                    binanceConfig.getTestnet()
            );
        }
        return futuresClient;
    }

    @Override
    public Map<String, Map<String, Object>> getMarketPrices() {
        log.info("[MarketService] 获取市场价格");
        try {
            // 获取配置的合约列表
            List<com.aifuturetrade.dao.entity.FutureDO> futureConfigs = futureMapper.selectList(null);
            if (futureConfigs == null || futureConfigs.isEmpty()) {
                log.warn("[MarketService] 未配置任何合约，返回空价格数据");
                return new HashMap<>();
            }

            // 构建symbol到contract_symbol的映射
            Map<String, String> symbolToContract = new HashMap<>();
            List<String> contractSymbols = new ArrayList<>();
            for (com.aifuturetrade.dao.entity.FutureDO future : futureConfigs) {
                String symbol = future.getSymbol() != null ? future.getSymbol().toUpperCase() : "";
                String contractSymbol = future.getContractSymbol() != null ? future.getContractSymbol().toUpperCase() : "";
                if (contractSymbol.isEmpty()) {
                    contractSymbol = symbol + "USDT";
                }
                if (!symbol.isEmpty()) {
                    symbolToContract.put(symbol, contractSymbol);
                    contractSymbols.add(contractSymbol);
                }
            }

            // 从 Binance API 获取价格
            BinanceFuturesClient client = getFuturesClient();
            Map<String, Map<String, Object>> pricesData = client.getSymbolPrices(contractSymbols);

            // 将返回结果中的key从contract_symbol转换为symbol
            Map<String, Map<String, Object>> result = new HashMap<>();
            for (Map.Entry<String, String> entry : symbolToContract.entrySet()) {
                String symbol = entry.getKey();
                String contractSymbol = entry.getValue();
                Map<String, Object> priceInfo = pricesData.get(contractSymbol);
                if (priceInfo != null) {
                    priceInfo.put("symbol", symbol);
                    priceInfo.put("contract_symbol", contractSymbol);
                    priceInfo.put("source", "configured");
                    // 添加name
                    for (com.aifuturetrade.dao.entity.FutureDO future : futureConfigs) {
                        if (symbol.equalsIgnoreCase(future.getSymbol())) {
                            if (future.getName() != null) {
                                priceInfo.put("name", future.getName());
                            }
                            break;
                        }
                    }
                    result.put(symbol, priceInfo);
                }
            }

            log.debug("[MarketService] 成功获取 {} 个交易对的价格数据", result.size());
            return result;
        } catch (Exception e) {
            log.error("[MarketService] 获取市场价格失败: {}", e.getMessage(), e);
            return new HashMap<>();
        }
    }

    @Override
    public Map<String, Object> getMarketIndicators(String symbol) {
        log.info("[MarketService] 获取技术指标, symbol={}", symbol);
        // TODO: 实现技术指标计算逻辑
        // 需要从 Binance API 获取 K 线数据，然后计算 MA、MACD、RSI 等指标
        Map<String, Object> result = new HashMap<>();
        result.put("symbol", symbol);
        result.put("timeframes", new HashMap<>());
        result.put("error", "技术指标计算功能待实现");
        return result;
    }

    @Override
    public Map<String, Object> getMarketLeaderboardGainers(Integer limit) {
        log.info("[MarketService] 获取涨幅榜, limit={}", limit);
        try {
            if (limit == null) {
                limit = 10;
            }
            
            List<Map<String, Object>> rawGainers = marketTickerMapper.selectGainersFromTickers(limit);
            List<Map<String, Object>> gainers = formatLeaderboardData(rawGainers, "gainer");
            
            Map<String, Object> result = new HashMap<>();
            result.put("gainers", gainers);
            result.put("timestamp", System.currentTimeMillis());
            return result;
        } catch (Exception e) {
            log.error("[MarketService] 获取涨幅榜失败: {}", e.getMessage(), e);
            Map<String, Object> result = new HashMap<>();
            result.put("gainers", new ArrayList<>());
            result.put("timestamp", System.currentTimeMillis());
            return result;
        }
    }

    @Override
    public Map<String, Object> getMarketLeaderboardLosers(Integer limit) {
        log.info("[MarketService] 获取跌幅榜, limit={}", limit);
        try {
            if (limit == null) {
                limit = 10;
            }
            
            List<Map<String, Object>> rawLosers = marketTickerMapper.selectLosersFromTickers(limit);
            List<Map<String, Object>> losers = formatLeaderboardData(rawLosers, "loser");
            
            Map<String, Object> result = new HashMap<>();
            result.put("losers", losers);
            result.put("timestamp", System.currentTimeMillis());
            return result;
        } catch (Exception e) {
            log.error("[MarketService] 获取跌幅榜失败: {}", e.getMessage(), e);
            Map<String, Object> result = new HashMap<>();
            result.put("losers", new ArrayList<>());
            result.put("timestamp", System.currentTimeMillis());
            return result;
        }
    }

    @Override
    public Map<String, Object> getMarketLeaderboard(Integer limit, Boolean force) {
        log.info("[MarketService] 获取涨跌幅榜, limit={}, force={}", limit, force);
        try {
            if (limit == null) {
                limit = 10;
            }
            
            // 一次查询获取涨幅榜和跌幅榜数据
            List<Map<String, Object>> rawGainers = marketTickerMapper.selectGainersFromTickers(limit);
            List<Map<String, Object>> rawLosers = marketTickerMapper.selectLosersFromTickers(limit);
            
            List<Map<String, Object>> gainers = formatLeaderboardData(rawGainers, "gainer");
            List<Map<String, Object>> losers = formatLeaderboardData(rawLosers, "loser");
            
            Map<String, Object> result = new HashMap<>();
            result.put("gainers", gainers);
            result.put("losers", losers);
            result.put("timestamp", System.currentTimeMillis());
            return result;
        } catch (Exception e) {
            log.error("[MarketService] 获取涨跌幅榜失败: {}", e.getMessage(), e);
            Map<String, Object> result = new HashMap<>();
            result.put("gainers", new ArrayList<>());
            result.put("losers", new ArrayList<>());
            result.put("timestamp", System.currentTimeMillis());
            return result;
        }
    }

    /**
     * 格式化涨跌幅榜数据
     * @param rawData 原始数据列表
     * @param side 类型（gainer或loser）
     * @return 格式化后的数据列表
     */
    private List<Map<String, Object>> formatLeaderboardData(List<Map<String, Object>> rawData, String side) {
        List<Map<String, Object>> formatted = new ArrayList<>();
        int position = 1;
        
        for (Map<String, Object> row : rawData) {
            String symbol = getStringValue(row, "symbol");
            String contractSymbol = symbol;
            String name = symbol;
            if (symbol != null && symbol.endsWith("USDT")) {
                name = symbol.replace("USDT", "");
            }
            
            Double priceChangePercent = getDoubleValue(row, "price_change_percent");
            Double lastPrice = getDoubleValue(row, "last_price");
            Double quoteVolume = getDoubleValue(row, "quote_volume");
            Object eventTime = row.get("event_time");
            
            Map<String, Object> item = new HashMap<>();
            item.put("symbol", symbol);
            item.put("contract_symbol", contractSymbol);
            item.put("name", name);
            item.put("exchange", "BINANCE_FUTURES");
            item.put("side", side);
            item.put("position", position++);
            item.put("price", lastPrice);
            item.put("change_percent", priceChangePercent);
            item.put("quote_volume", quoteVolume);
            item.put("timeframes", "");
            item.put("event_time", eventTime);
            
            formatted.add(item);
        }
        
        return formatted;
    }

    /**
     * 从Map中获取字符串值
     */
    private String getStringValue(Map<String, Object> map, String key) {
        Object value = map.get(key);
        return value != null ? value.toString() : "";
    }

    /**
     * 从Map中获取Double值
     */
    private Double getDoubleValue(Map<String, Object> map, String key) {
        Object value = map.get(key);
        if (value == null) {
            return 0.0;
        }
        if (value instanceof Number) {
            return ((Number) value).doubleValue();
        }
        try {
            return Double.parseDouble(value.toString());
        } catch (Exception e) {
            return 0.0;
        }
    }

    @Override
    public List<Map<String, Object>> getMarketKlines(String symbol, String interval, Integer limit, String startTime, String endTime) {
        log.info("[MarketService] 获取K线数据, symbol={}, interval={}, limit={}, startTime={}, endTime={}", 
                symbol, interval, limit, startTime, endTime);
        try {
            BinanceFuturesClient client = getFuturesClient();
            
            // 解析时间参数
            Long startTimestamp = null;
            Long endTimestamp = null;
            if (startTime != null && !startTime.isEmpty()) {
                try {
                    LocalDateTime start = LocalDateTime.parse(startTime.replace("Z", ""));
                    startTimestamp = start.toInstant(ZoneOffset.UTC).toEpochMilli();
                } catch (Exception e) {
                    log.warn("[MarketService] 解析 startTime 失败: {}", startTime);
                }
            }
            if (endTime != null && !endTime.isEmpty()) {
                try {
                    LocalDateTime end = LocalDateTime.parse(endTime.replace("Z", ""));
                    endTimestamp = end.toInstant(ZoneOffset.UTC).toEpochMilli();
                } catch (Exception e) {
                    log.warn("[MarketService] 解析 endTime 失败: {}", endTime);
                }
            }

            // 根据不同的interval设置不同的默认limit
            if (limit == null) {
                if ("1d".equals(interval)) {
                    limit = 499;
                } else if ("1w".equals(interval)) {
                    limit = 99;
                } else {
                    limit = 499;
                }
            }
            
            // 验证limit参数的有效性（Binance API限制：1-1000）
            if (limit != null) {
                if (limit <= 0) {
                    log.warn("[MarketService] limit参数 {} 无效，使用默认值500", limit);
                    limit = 500;
                } else if (limit > 1000) {
                    log.warn("[MarketService] limit参数 {} 超过最大值1000，已限制为1000", limit);
                    limit = 1000;
                }
            }

            // 调用 Binance API 获取 K 线数据
            List<Map<String, Object>> klines = client.getKlines(symbol, interval, limit, startTimestamp, endTimestamp);

            // 格式化 K 线数据
            List<Map<String, Object>> formattedKlines = new ArrayList<>();
            for (Map<String, Object> kline : klines) {
                Map<String, Object> formatted = new HashMap<>();
                formatted.put("timestamp", kline.get("open_time"));
                formatted.put("open", kline.get("open"));
                formatted.put("high", kline.get("high"));
                formatted.put("low", kline.get("low"));
                formatted.put("close", kline.get("close"));
                formatted.put("volume", kline.get("volume"));
                formatted.put("turnover", kline.get("quote_asset_volume"));
                formattedKlines.add(formatted);
            }

            log.info("[MarketService] 成功获取 {} 条K线数据", formattedKlines.size());
            return formattedKlines;
        } catch (Exception e) {
            log.error("[MarketService] 获取K线数据失败: {}", e.getMessage(), e);
            return new ArrayList<>();
        }
    }
}

