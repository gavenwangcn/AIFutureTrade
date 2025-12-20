package com.aifuturetrade.common.api.binance;

import com.binance.connector.client.common.ApiResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.Interval;
import lombok.extern.slf4j.Slf4j;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 币安期货客户端 - 封装币安官方衍生品SDK的高级接口
 * 
 * 提供简洁易用的方法来获取市场数据，自动处理SDK响应格式转换。
 * 
 * 参考 Binance 官方示例：
 * https://github.com/binance/binance-connector-java/tree/master/clients/derivatives-trading-usds-futures
 */
@Slf4j
public class BinanceFuturesClient extends BinanceFuturesBase {
    
    /**
     * 构造函数，初始化币安期货客户端
     * 
     * @param apiKey 币安API密钥
     * @param apiSecret 币安API密钥
     * @param quoteAsset 计价资产，默认为USDT
     * @param baseUrl 自定义REST API基础路径（可选）
     * @param testnet 是否使用测试网络，默认False
     */
    public BinanceFuturesClient(String apiKey, String apiSecret, String quoteAsset, 
                                String baseUrl, Boolean testnet) {
        this.quoteAsset = (quoteAsset != null ? quoteAsset : "USDT").toUpperCase();
        initRestApi(apiKey, apiSecret, null, null, baseUrl);
    }
    
    /**
     * 构造函数，使用默认配置
     */
    public BinanceFuturesClient(String apiKey, String apiSecret) {
        this(apiKey, apiSecret, "USDT", null, false);
    }
    
    /**
     * 获取指定交易对的24小时价格变动统计
     * 
     * @param symbols 交易对符号列表，如 ['BTCUSDT', 'ETHUSDT']
     * @return 字典，key为交易对符号，value为24小时统计数据
     */
    public Map<String, Map<String, Object>> get24hTicker(List<String> symbols) {
        log.info("[Binance Futures] 开始获取24小时价格变动统计，交易对数量: {}", symbols != null ? symbols.size() : 0);
        
        Map<String, Map<String, Object>> result = new HashMap<>();
        if (symbols == null || symbols.isEmpty()) {
            return result;
        }
        
        try {
            int total = symbols.size();
            int success = 0;
            long fetchStart = System.currentTimeMillis();
            
            for (int idx = 0; idx < symbols.size(); idx++) {
                String symbol = symbols.get(idx);
                String requestSymbol = symbol.toUpperCase();
                log.debug("[Binance Futures] 获取 {} 24小时统计 ({}/{})", requestSymbol, idx + 1, total);
                
                try {
                    long callStart = System.currentTimeMillis();
                    ApiResponse<?> response = restApi.ticker24hrPriceChangeStatistics(requestSymbol);
                    long callDuration = System.currentTimeMillis() - callStart;
                    
                    // 尝试多种方式获取响应数据
                    Object data = getResponseData(response);
                    Map<String, Object> tickerData = toMap(data);
                    
                    if (tickerData.isEmpty()) {
                        log.warn("[Binance Futures] {} 无返回数据，跳过", requestSymbol);
                        continue;
                    }
                    
                    // 匹配正确的交易对数据
                    String normalizedSymbol = requestSymbol.toUpperCase();
                    String symbolValue = (String) tickerData.getOrDefault("symbol", tickerData.get("s"));
                    if (symbolValue != null && symbolValue.toUpperCase().equals(normalizedSymbol)) {
                        result.put(symbol.toUpperCase(), tickerData);
                        success++;
                        log.debug("[Binance Futures] {} 获取成功, 耗时 {} 毫秒", requestSymbol, callDuration);
                    } else {
                        log.warn("[Binance Futures] {} 交易对不匹配，跳过", requestSymbol);
                    }
                    
                } catch (Exception symbolExc) {
                    log.warn("[Binance Futures] 获取 {} 失败: {}", requestSymbol, symbolExc.getMessage());
                    continue;
                }
            }
            
            long totalDuration = System.currentTimeMillis() - fetchStart;
            log.info("[Binance Futures] 24小时统计获取完成, 成功 {}/{}, 总耗时 {} 毫秒", 
                    success, total, totalDuration);
            
        } catch (Exception exc) {
            log.error("[Binance Futures] 获取24小时统计失败: {}", exc.getMessage(), exc);
        }
        
        return result;
    }
    
    /**
     * 获取指定交易对的实时价格
     * 
     * @param symbols 交易对符号列表，如 ['BTCUSDT', 'ETHUSDT']
     * @return 字典，key为交易对符号，value为实时价格数据
     */
    public Map<String, Map<String, Object>> getSymbolPrices(List<String> symbols) {
        log.debug("[Binance Futures] 开始获取实时价格，交易对数量: {}", symbols != null ? symbols.size() : 0);
        
        Map<String, Map<String, Object>> result = new HashMap<>();
        if (symbols == null || symbols.isEmpty()) {
            return result;
        }
        
        try {
            int total = symbols.size();
            int success = 0;
            long fetchStart = System.currentTimeMillis();
            
            for (int idx = 0; idx < symbols.size(); idx++) {
                String symbol = symbols.get(idx);
                String requestSymbol = symbol.toUpperCase();
                log.debug("[Binance Futures] 获取 {} 实时价格 ({}/{})", requestSymbol, idx + 1, total);
                
                try {
                    long callStart = System.currentTimeMillis();
                    ApiResponse<?> response = restApi.symbolPriceTicker(requestSymbol);
                    long callDuration = System.currentTimeMillis() - callStart;
                    
                    // 尝试多种方式获取响应数据
                    Object data = getResponseData(response);
                    Map<String, Object> priceData = toMap(data);
                    
                    if (priceData.isEmpty()) {
                        log.warn("[Binance Futures] {} 无返回数据，跳过", requestSymbol);
                        continue;
                    }
                    
                    // 匹配正确的交易对数据
                    String normalizedSymbol = requestSymbol.toUpperCase();
                    String symbolValue = (String) priceData.getOrDefault("symbol", priceData.get("s"));
                    if (symbolValue != null && symbolValue.toUpperCase().equals(normalizedSymbol)) {
                        result.put(symbol.toUpperCase(), priceData);
                        success++;
                        log.debug("[Binance Futures] {} 获取成功, 耗时 {} 毫秒", requestSymbol, callDuration);
                    } else {
                        log.warn("[Binance Futures] {} 交易对不匹配，跳过", requestSymbol);
                    }
                    
                } catch (Exception symbolExc) {
                    log.warn("[Binance Futures] 获取 {} 失败: {}", requestSymbol, symbolExc.getMessage());
                    continue;
                }
            }
            
            long totalDuration = System.currentTimeMillis() - fetchStart;
            log.debug("[Binance Futures] 实时价格获取完成, 成功 {}/{}, 总耗时 {} 毫秒", 
                    success, total, totalDuration);
            
        } catch (Exception exc) {
            log.error("[Binance Futures] 获取实时价格失败: {}", exc.getMessage(), exc);
        }
        
        return result;
    }
    
    /**
     * 获取K线数据
     * 
     * @param symbol 交易对符号，如 'BTCUSDT'
     * @param interval K线间隔，如 '1m', '5m', '1h', '1d' 等
     * @param limit 返回的K线数量，默认120
     * @param startTime 起始时间戳（毫秒），可选
     * @param endTime 结束时间戳（毫秒），可选
     * @return K线数据列表，每个元素为包含完整K线信息的字典
     */
    public List<Map<String, Object>> getKlines(String symbol, String interval, Integer limit, 
                                               Long startTime, Long endTime) {
        log.info("[Binance Futures] 开始获取K线数据, symbol={}, interval={}, limit={}, startTime={}, endTime={}", 
                symbol, interval, limit, startTime, endTime);
        
        List<Map<String, Object>> klines = new ArrayList<>();
        
        try {
            // 构建API调用参数
            Map<String, Object> params = new HashMap<>();
            params.put("symbol", symbol.toUpperCase());
            params.put("interval", interval);
            if (limit != null) {
                params.put("limit", limit);
            }
            if (startTime != null) {
                params.put("startTime", startTime);
            }
            if (endTime != null) {
                params.put("endTime", endTime);
            }
            
            // 调用API获取K线数据
            long apiStartTime = System.currentTimeMillis();
            ApiResponse<?> response = null;
            Object data = null;
            
            try {
                String requestSymbol = symbol.toUpperCase();
                log.debug("[Binance Futures] 准备调用SDK获取K线数据, symbol={}, interval={}, limit={}, startTime={}, endTime={}", 
                        requestSymbol, interval, limit, startTime, endTime);
                
                // 将字符串interval转换为Interval枚举
                Interval intervalEnum = convertStringToInterval(interval);
                if (intervalEnum == null) {
                    log.error("[Binance Futures] 不支持的interval: {}", interval);
                    return new ArrayList<>();
                }
                
                // 验证和转换limit参数
                // Binance API限制：limit必须在1-1000之间，推荐使用1-500
                // 注意：即使提供了startTime/endTime，limit参数也必须有效（不能为null）
                Long limitLong;
                if (limit == null || limit <= 0) {
                    // 如果limit为null或无效，使用默认值
                    // 根据interval选择合理的默认值
                    if ("1w".equals(interval)) {
                        limitLong = 100L;  // 周线：100周数据
                    } else if ("1d".equals(interval)) {
                        limitLong = 500L;  // 日线：500天数据
                    } else {
                        limitLong = 500L;  // 其他：500条数据
                    }
                    log.debug("[Binance Futures] limit参数无效或为空，使用默认值: {} (interval: {})", limitLong, interval);
                } else if (limit > 1000) {
                    // 如果limit超过最大值，限制为1000
                    limitLong = 1000L;
                    log.warn("[Binance Futures] limit参数 {} 超过最大值1000，已限制为1000", limit);
                } else {
                    limitLong = limit.longValue();
                }
                
                log.debug("[Binance Futures] 最终调用参数: symbol={}, interval={}, limit={}, startTime={}, endTime={}", 
                        requestSymbol, intervalEnum, limitLong, startTime, endTime);
                
                // 调用SDK API获取K线数据
                // 方法签名：klineCandlestickData(String symbol, Interval interval, Long limit, Long startTime, Long endTime)
                // 注意：limit参数不能为null，必须是一个有效的Long值（1-1000之间）
                response = restApi.klineCandlestickData(requestSymbol, intervalEnum, limitLong, startTime, endTime);
                
                // 获取响应数据
                if (response != null) {
                    data = getResponseData(response);
                    log.debug("[Binance Futures] SDK响应获取成功, data类型: {}, 是否为List: {}", 
                            data != null ? data.getClass().getName() : "null", 
                            data instanceof List);
                } else {
                    log.error("[Binance Futures] SDK响应为null");
                }
                
            } catch (Exception apiExc) {
                log.error("[Binance Futures] 调用SDK API失败: {}, 错误详情: {}", 
                        apiExc.getMessage(), apiExc.getClass().getName(), apiExc);
                // 不抛出异常，返回空列表，让上层处理
                data = null;
            }
            
            long apiDuration = System.currentTimeMillis() - apiStartTime;
            if (data instanceof List) {
                log.info("[Binance Futures] API调用完成, 耗时: {} 毫秒, 返回 {} 条K线数据", 
                        apiDuration, ((List<?>) data).size());
            } else {
                log.warn("[Binance Futures] API调用完成, 耗时: {} 毫秒, 但返回数据不是List类型: {}", 
                        apiDuration, data != null ? data.getClass().getName() : "null");
            }
            
            // 处理响应数据
            if (data instanceof List) {
                @SuppressWarnings("unchecked")
                List<Object> dataList = (List<Object>) data;
                
                for (Object item : dataList) {
                    Map<String, Object> klineDict = new HashMap<>();
                    
                    if (item instanceof List) {
                        @SuppressWarnings("unchecked")
                        List<Object> klineList = (List<Object>) item;
                        
                        if (klineList.size() >= 11) {
                            Long openTime = parseLong(klineList.get(0));
                            String openPrice = String.valueOf(klineList.get(1));
                            String highPrice = String.valueOf(klineList.get(2));
                            String lowPrice = String.valueOf(klineList.get(3));
                            String closePrice = String.valueOf(klineList.get(4));
                            String volume = String.valueOf(klineList.get(5));
                            Long closeTime = parseLong(klineList.get(6));
                            String quoteAssetVolume = String.valueOf(klineList.get(7));
                            Long numberOfTrades = parseLong(klineList.get(8));
                            String takerBuyBaseVolume = String.valueOf(klineList.get(9));
                            String takerBuyQuoteVolume = String.valueOf(klineList.get(10));
                            
                            // 转换时间戳为日期格式
                            LocalDateTime openTimeDt = openTime != null ? 
                                    LocalDateTime.ofInstant(Instant.ofEpochMilli(openTime), ZoneId.systemDefault()) : null;
                            LocalDateTime closeTimeDt = closeTime != null ? 
                                    LocalDateTime.ofInstant(Instant.ofEpochMilli(closeTime), ZoneId.systemDefault()) : null;
                            
                            klineDict.put("open_time", openTime);
                            klineDict.put("open_time_dt", openTimeDt);
                            klineDict.put("open", openPrice);
                            klineDict.put("high", highPrice);
                            klineDict.put("low", lowPrice);
                            klineDict.put("close", closePrice);
                            klineDict.put("volume", volume);
                            klineDict.put("close_time", closeTime);
                            klineDict.put("close_time_dt", closeTimeDt);
                            klineDict.put("quote_asset_volume", quoteAssetVolume);
                            klineDict.put("number_of_trades", numberOfTrades);
                            klineDict.put("taker_buy_base_volume", takerBuyBaseVolume);
                            klineDict.put("taker_buy_quote_volume", takerBuyQuoteVolume);
                            
                            klines.add(klineDict);
                        }
                    } else {
                        // 如果是字典或模型对象
                        Map<String, Object> entry = toMap(item);
                        if (!entry.isEmpty()) {
                            Long openTime = parseLong(entry.get("open_time") != null ? entry.get("open_time") : 
                                    entry.get("openTime") != null ? entry.get("openTime") : entry.get("t"));
                            String openPrice = String.valueOf(entry.getOrDefault("open", entry.getOrDefault("o", "")));
                            String highPrice = String.valueOf(entry.getOrDefault("high", entry.getOrDefault("h", "")));
                            String lowPrice = String.valueOf(entry.getOrDefault("low", entry.getOrDefault("l", "")));
                            String closePrice = String.valueOf(entry.getOrDefault("close", entry.getOrDefault("c", "")));
                            String volume = String.valueOf(entry.getOrDefault("volume", entry.getOrDefault("v", "")));
                            Long closeTime = parseLong(entry.get("close_time") != null ? entry.get("close_time") : 
                                    entry.get("closeTime"));
                            String quoteAssetVolume = String.valueOf(entry.getOrDefault("quote_asset_volume", 
                                    entry.getOrDefault("quoteAssetVolume", entry.getOrDefault("q", ""))));
                            Long numberOfTrades = parseLong(entry.get("number_of_trades") != null ? 
                                    entry.get("number_of_trades") : entry.get("numberOfTrades") != null ? 
                                    entry.get("numberOfTrades") : entry.get("n"));
                            String takerBuyBaseVolume = String.valueOf(entry.getOrDefault("taker_buy_base_volume", 
                                    entry.getOrDefault("takerBuyBaseVolume", entry.getOrDefault("V", ""))));
                            String takerBuyQuoteVolume = String.valueOf(entry.getOrDefault("taker_buy_quote_volume", 
                                    entry.getOrDefault("takerBuyQuoteVolume", entry.getOrDefault("Q", ""))));
                            
                            // 转换时间戳为日期格式
                            LocalDateTime openTimeDt = null;
                            LocalDateTime closeTimeDt = null;
                            if (openTime != null) {
                                openTimeDt = LocalDateTime.ofInstant(Instant.ofEpochMilli(openTime), ZoneId.systemDefault());
                            }
                            if (closeTime != null) {
                                closeTimeDt = LocalDateTime.ofInstant(Instant.ofEpochMilli(closeTime), ZoneId.systemDefault());
                            }
                            
                            klineDict.put("open_time", openTime);
                            klineDict.put("open_time_dt", openTimeDt);
                            klineDict.put("open", openPrice);
                            klineDict.put("high", highPrice);
                            klineDict.put("low", lowPrice);
                            klineDict.put("close", closePrice);
                            klineDict.put("volume", volume);
                            klineDict.put("close_time", closeTime);
                            klineDict.put("close_time_dt", closeTimeDt);
                            klineDict.put("quote_asset_volume", quoteAssetVolume);
                            klineDict.put("number_of_trades", numberOfTrades);
                            klineDict.put("taker_buy_base_volume", takerBuyBaseVolume);
                            klineDict.put("taker_buy_quote_volume", takerBuyQuoteVolume);
                            
                            klines.add(klineDict);
                        }
                    }
                }
            }
            
            log.info("[Binance Futures] K线数据获取完成, 返回 {} 条K线", klines.size());
            return klines;
            
        } catch (Exception exc) {
            log.error("[Binance Futures] 获取K线数据失败: {}, symbol={}, interval={}, limit={}", 
                    exc.getMessage(), symbol, interval, limit, exc);
            return new ArrayList<>();
        }
    }
    
    /**
     * 获取K线数据（简化版本，不指定时间范围）
     */
    public List<Map<String, Object>> getKlines(String symbol, String interval, Integer limit) {
        return getKlines(symbol, interval, limit, null, null);
    }
    
    /**
     * 从ApiResponse中获取数据
     */
    private Object getResponseData(ApiResponse<?> response) {
        if (response == null) {
            return null;
        }
        try {
            // 尝试使用反射获取data字段或方法
            try {
                java.lang.reflect.Method dataMethod = response.getClass().getMethod("data");
                return dataMethod.invoke(response);
            } catch (NoSuchMethodException e) {
                try {
                    java.lang.reflect.Method getDataMethod = response.getClass().getMethod("getData");
                    return getDataMethod.invoke(response);
                } catch (NoSuchMethodException e2) {
                    // 尝试直接访问data字段
                    try {
                        java.lang.reflect.Field dataField = response.getClass().getField("data");
                        return dataField.get(response);
                    } catch (NoSuchFieldException e3) {
                        // 如果都失败，返回response本身
                        return response;
                    }
                }
            }
        } catch (Exception e) {
            log.warn("获取响应数据失败: {}", e.getMessage());
            return response;
        }
    }
    
    /**
     * 解析Long值
     */
    private Long parseLong(Object obj) {
        if (obj == null) {
            return null;
        }
        if (obj instanceof Long) {
            return (Long) obj;
        }
        if (obj instanceof Integer) {
            return ((Integer) obj).longValue();
        }
        if (obj instanceof String) {
            try {
                return Long.parseLong((String) obj);
            } catch (NumberFormatException e) {
                return null;
            }
        }
        if (obj instanceof Number) {
            return ((Number) obj).longValue();
        }
        return null;
    }
    
    /**
     * 将字符串interval转换为Interval枚举
     * @param intervalStr 字符串格式的interval，如 "1m", "5m", "1h", "1d" 等
     * @return Interval枚举值，如果不支持则返回null
     */
    private Interval convertStringToInterval(String intervalStr) {
        if (intervalStr == null || intervalStr.isEmpty()) {
            return null;
        }
        
        String upperInterval = intervalStr.toUpperCase();
        
        // 尝试多种可能的枚举命名格式
        String[] possibleNames = {
            "INTERVAL_" + upperInterval,           // INTERVAL_1M, INTERVAL_5M
            "INTERVAL_" + upperInterval.replaceAll("[^A-Z0-9]", ""),  // INTERVAL_1M (移除特殊字符)
            upperInterval,                         // 直接使用 1M, 5M
            intervalStr                            // 保持原样 1m, 5m
        };
        
        for (String enumName : possibleNames) {
            try {
                return Interval.valueOf(enumName);
            } catch (IllegalArgumentException e) {
                // 继续尝试下一个
                continue;
            }
        }
        
        // 如果所有格式都失败，尝试使用反射查找所有枚举值
        try {
            Interval[] values = Interval.values();
            for (Interval interval : values) {
                // 检查枚举值的字符串表示是否匹配
                String enumStr = interval.toString().toUpperCase();
                if (enumStr.equals(upperInterval) || 
                    enumStr.endsWith(upperInterval) ||
                    enumStr.contains(upperInterval)) {
                    return interval;
                }
            }
        } catch (Exception e) {
            log.warn("[Binance Futures] 使用反射查找Interval枚举失败: {}", e.getMessage());
        }
        
        log.error("[Binance Futures] 不支持的interval格式: {}", intervalStr);
        return null;
    }
}

