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
                    binanceConfig.getTestnet(),
                    binanceConfig.getConnectTimeout(),
                    binanceConfig.getReadTimeout()
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

            // 从 24_market_tickers 表获取涨幅百分比和成交额
            Map<String, Map<String, Object>> tickerDataMap = new HashMap<>();
            try {
                List<Map<String, Object>> tickerDataList = marketTickerMapper.selectTickersBySymbols(contractSymbols);
                // 构建symbol到ticker数据的映射（使用contract_symbol作为key）
                for (Map<String, Object> ticker : tickerDataList) {
                    String tickerSymbol = (String) ticker.get("symbol");
                    if (tickerSymbol != null) {
                        tickerDataMap.put(tickerSymbol.toUpperCase(), ticker);
                    }
                }
                log.debug("[MarketService] 从24_market_tickers表获取到 {} 条ticker数据", tickerDataMap.size());
            } catch (Exception e) {
                log.warn("[MarketService] 从24_market_tickers表获取数据失败: {}", e.getMessage());
            }

            // 将返回结果中的key从contract_symbol转换为symbol，并合并ticker数据
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
                    
                    // 从24_market_tickers表获取涨幅百分比和成交额
                    Map<String, Object> tickerData = tickerDataMap.get(contractSymbol);
                    if (tickerData != null) {
                        // 添加涨幅百分比（price_change_percent，有正负号）
                        Object priceChangePercent = tickerData.get("price_change_percent");
                        if (priceChangePercent != null) {
                            priceInfo.put("change_24h", priceChangePercent);
                        }
                        // 添加当日成交额（quote_volume）
                        Object quoteVolume = tickerData.get("quote_volume");
                        if (quoteVolume != null) {
                            priceInfo.put("daily_volume", quoteVolume);
                            priceInfo.put("quote_volume", quoteVolume); // 同时提供quote_volume字段以便兼容
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
            Double baseVolume = getDoubleValue(row, "base_volume");
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
            item.put("base_volume", baseVolume);
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
    
    /**
     * 从Map中获取Long值
     */
    private Long getLongValue(Map<String, Object> map, String key) {
        Object value = map.get(key);
        if (value == null) {
            return null;
        }
        if (value instanceof Number) {
            return ((Number) value).longValue();
        }
        try {
            return Long.parseLong(value.toString());
        } catch (Exception e) {
            return null;
        }
    }
    
    /**
     * 将数值保留6位小数
     */
    private double roundTo6Decimals(double value) {
        return Math.round(value * 1000000.0) / 1000000.0;
    }
    
    /**
     * 将timestamp（毫秒）转换为datetime字符串用于验证（使用 UTC+8 时区）
     */
    private String formatTimestamp(Long timestamp) {
        if (timestamp == null || timestamp == 0) {
            return "N/A";
        }
        try {
            java.time.Instant instant = java.time.Instant.ofEpochMilli(timestamp);
            java.time.ZoneId utcPlus8 = java.time.ZoneId.of("Asia/Shanghai");
            java.time.ZonedDateTime zonedDateTime = instant.atZone(utcPlus8);
            return zonedDateTime.format(java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss 'UTC+8'"));
        } catch (Exception e) {
            return timestamp + " (转换失败: " + e.getMessage() + ")";
        }
    }

    @Override
    public List<Map<String, Object>> getMarketKlines(String symbol, String interval, Integer limit, String startTime, String endTime) {
        log.info("[MarketService] 获取K线数据, symbol={}, interval={}, limit={}", 
                symbol, interval, limit);
        try {
            BinanceFuturesClient client = getFuturesClient();

            // 根据interval类型设置默认limit
            // 1天（1d）和1周（1w）返回99根，其他interval返回499根
            if (limit == null) {
                if ("1d".equals(interval) || "1w".equals(interval)) {
                    limit = 99;
                } else {
                    limit = 499;
                }
            }
            
            // 验证limit参数的有效性（Binance API限制：1-1000）
            if (limit != null) {
                if (limit <= 0) {
                    // 根据interval设置默认值
                    if ("1d".equals(interval) || "1w".equals(interval)) {
                        log.warn("[MarketService] limit参数 {} 无效，使用默认值99", limit);
                        limit = 99;
                    } else {
                        log.warn("[MarketService] limit参数 {} 无效，使用默认值499", limit);
                        limit = 499;
                    }
                } else if (limit > 1000) {
                    log.warn("[MarketService] limit参数 {} 超过最大值1000，已限制为1000", limit);
                    limit = 1000;
                }
            }

            // 调用 Binance API 获取 K 线数据（不传入startTime和endTime）
            List<Map<String, Object>> klinesRaw = client.getKlines(symbol, interval, limit, null, null);

            // SDK返回的数据是倒序的（从新到旧），数组[0]是最新的K线，数组[-1]是最旧的K线
            // 注意：K线页面已改为仅使用历史数据，不再订阅实时K线更新，因此保留所有数据（包括最新K线）
            log.debug("[MarketService] SDK返回{}条K线数据（倒序：最新→最旧），保留所有数据（包括最新K线）", 
                    klinesRaw != null ? klinesRaw.size() : 0);

            // 格式化 K 线数据，价格保留6位小数
            List<Map<String, Object>> formattedKlines = new ArrayList<>();
            if (klinesRaw != null && !klinesRaw.isEmpty()) {
                for (Map<String, Object> kline : klinesRaw) {
                    // 转换为浮点数并保留6位小数
                    double formattedOpen = roundTo6Decimals(getDoubleValue(kline, "open"));
                    double formattedHigh = roundTo6Decimals(getDoubleValue(kline, "high"));
                    double formattedLow = roundTo6Decimals(getDoubleValue(kline, "low"));
                    double formattedClose = roundTo6Decimals(getDoubleValue(kline, "close"));
                    
                    Map<String, Object> formatted = new HashMap<>();
                    formatted.put("timestamp", kline.get("open_time"));
                    formatted.put("open", formattedOpen);
                    formatted.put("high", formattedHigh);
                    formatted.put("low", formattedLow);
                    formatted.put("close", formattedClose);
                    formatted.put("volume", getDoubleValue(kline, "volume"));
                    formatted.put("turnover", getDoubleValue(kline, "quote_asset_volume"));
                    formattedKlines.add(formatted);
                }
                
                // 由于SDK返回的数据是倒序的（从新到旧），需要按timestamp升序排序（从旧到新）
                // 确保与前端期望的数据顺序一致
                // 前端K线图表从左到右显示，左边是最旧的数据，右边是最新的数据，所以需要从旧到新的顺序
                formattedKlines.sort((a, b) -> {
                    Long timestampA = getLongValue(a, "timestamp");
                    Long timestampB = getLongValue(b, "timestamp");
                    if (timestampA == null && timestampB == null) return 0;
                    if (timestampA == null) return -1;
                    if (timestampB == null) return 1;
                    return timestampA.compareTo(timestampB);
                });
                
                log.info("[MarketService] SDK查询完成，共获取 {} 条K线数据（已排序为从旧到新，包含最新K线）", 
                        formattedKlines.size());
                
                // 验证数据顺序：确保第一条时间戳小于最后一条时间戳（从旧到新，timestamp升序）
                // 前端K线图表从左到右显示，左边是最旧的数据（第一条），右边是最新的数据（最后一条）
                // 所以数据顺序应该是：第一条（最旧）< 最后一条（最新）
                if (formattedKlines.size() > 1) {
                    Long firstTimestamp = getLongValue(formattedKlines.get(0), "timestamp");
                    Long lastTimestamp = getLongValue(formattedKlines.get(formattedKlines.size() - 1), "timestamp");
                    
                    if (firstTimestamp != null && lastTimestamp != null) {
                        String firstTimestampStr = formatTimestamp(firstTimestamp);
                        String lastTimestampStr = formatTimestamp(lastTimestamp);
                        
                        if (firstTimestamp >= lastTimestamp) {
                            log.warn("[MarketService] ⚠️ 数据顺序异常：第一条时间戳({}, {}) >= 最后一条({}, {})，" +
                                    "重新排序以确保从旧到新的顺序（与前端K线图表从左到右的要求一致）",
                                    firstTimestamp, firstTimestampStr, lastTimestamp, lastTimestampStr);
                            
                            // 重新排序
                            formattedKlines.sort((a, b) -> {
                                Long timestampA = getLongValue(a, "timestamp");
                                Long timestampB = getLongValue(b, "timestamp");
                                if (timestampA == null && timestampB == null) return 0;
                                if (timestampA == null) return -1;
                                if (timestampB == null) return 1;
                                return timestampA.compareTo(timestampB);
                            });
                            
                            // 重新验证
                            firstTimestamp = getLongValue(formattedKlines.get(0), "timestamp");
                            lastTimestamp = getLongValue(formattedKlines.get(formattedKlines.size() - 1), "timestamp");
                            firstTimestampStr = formatTimestamp(firstTimestamp);
                            lastTimestampStr = formatTimestamp(lastTimestamp);
                            
                            log.debug("[MarketService] ✓ 重新排序后：第一条时间戳={} ({}), 最后一条时间戳={} ({})",
                                    firstTimestamp, firstTimestampStr, lastTimestamp, lastTimestampStr);
                        } else {
                            log.debug("[MarketService] ✓ 数据顺序验证通过：第一条时间戳={} ({}) < 最后一条时间戳={} ({}) " +
                                    "（从旧到新，符合前端K线图表从左到右的显示要求）",
                                    firstTimestamp, firstTimestampStr, lastTimestamp, lastTimestampStr);
                        }
                    }
                }
            }

            // 记录返回数据信息
            int klinesCount = formattedKlines.size();
            log.info("[MarketService] 获取K线历史数据查询完成: symbol={}, interval={}, 返回数据条数={}", 
                    symbol, interval, klinesCount);
            
            if (klinesCount > 0) {
                // 记录第一条和最后一条数据的时间戳（用于调试）
                Map<String, Object> firstKline = formattedKlines.get(0);
                Map<String, Object> lastKline = formattedKlines.get(formattedKlines.size() - 1);
                Long firstTimestamp = getLongValue(firstKline, "timestamp");
                Long lastTimestamp = getLongValue(lastKline, "timestamp");
                
                String firstTimestampStr = formatTimestamp(firstTimestamp);
                String lastTimestampStr = formatTimestamp(lastTimestamp);
                
                log.info("[MarketService] 获取K线历史数据时间范围: 第一条timestamp={} ({}), " +
                        "最后一条timestamp={} ({}), 共返回{}条数据",
                        firstTimestamp, firstTimestampStr, lastTimestamp, lastTimestampStr, klinesCount);
                
                // 记录第一条数据的详细信息（用于调试数据格式）
                log.debug("[MarketService] 获取K线历史数据示例（第一条）: {}", firstKline);
                log.debug("[MarketService] 获取K线历史数据示例（最后一条）: {}", lastKline);
            } else {
                log.warn("[MarketService] 未找到K线历史数据: symbol={}, interval={}", symbol, interval);
            }
            
            return formattedKlines;
        } catch (Exception e) {
            log.error("[MarketService] 获取K线数据失败: {}", e.getMessage(), e);
            return new ArrayList<>();
        }
    }
}

