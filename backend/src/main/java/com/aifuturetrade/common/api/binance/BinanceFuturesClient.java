package com.aifuturetrade.common.api.binance;

import com.binance.connector.client.common.ApiResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.Interval;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.KlineCandlestickDataResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.KlineCandlestickDataResponseItem;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.SymbolPriceTickerV2Response;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.SymbolPriceTickerV2Response1;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.SymbolPriceTickerV2Response2;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.Ticker24hrPriceChangeStatisticsResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.Ticker24hrPriceChangeStatisticsResponse1;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.Ticker24hrPriceChangeStatisticsResponse2;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.Ticker24hrPriceChangeStatisticsResponse2Inner;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.SymbolPriceTickerV2Response2Inner;
import lombok.extern.slf4j.Slf4j;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
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
     * @param connectTimeout 连接超时时间（毫秒），默认10000ms
     * @param readTimeout 读取超时时间（毫秒），默认50000ms
     */
    public BinanceFuturesClient(String apiKey, String apiSecret, String quoteAsset, 
                                String baseUrl, Boolean testnet,
                                Integer connectTimeout, Integer readTimeout) {
        this.quoteAsset = (quoteAsset != null ? quoteAsset : "USDT").toUpperCase();
        initRestApi(apiKey, apiSecret, null, null, baseUrl, connectTimeout, readTimeout);
    }
    
    /**
     * 构造函数，使用默认配置
     */
    public BinanceFuturesClient(String apiKey, String apiSecret) {
        this(apiKey, apiSecret, "USDT", null, false, null, null);
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
                    ApiResponse<Ticker24hrPriceChangeStatisticsResponse> response = restApi.ticker24hrPriceChangeStatistics(requestSymbol);
                    long callDuration = System.currentTimeMillis() - callStart;
                    
                    // 直接使用SDK的getData()方法获取响应数据
                    Ticker24hrPriceChangeStatisticsResponse responseData = response.getData();
                    if (responseData == null) {
                        log.warn("[Binance Futures] {} 无返回数据，跳过", requestSymbol);
                        continue;
                    }
                    
                    // Ticker24hrPriceChangeStatisticsResponse是oneOf类型，需要使用getActualInstance()获取实际实例
                    Object actualInstance = responseData.getActualInstance();
                    if (actualInstance == null) {
                        log.warn("[Binance Futures] {} 响应数据实例为null，跳过", requestSymbol);
                        continue;
                    }
                    
                    // 根据实际实例类型提取数据
                    Map<String, Object> tickerData = new HashMap<>();
                    String symbolValue = null;
                    
                    if (actualInstance instanceof Ticker24hrPriceChangeStatisticsResponse1) {
                        Ticker24hrPriceChangeStatisticsResponse1 ticker = (Ticker24hrPriceChangeStatisticsResponse1) actualInstance;
                        symbolValue = ticker.getSymbol();
                        tickerData.put("symbol", ticker.getSymbol());
                        tickerData.put("priceChange", ticker.getPriceChange());
                        tickerData.put("priceChangePercent", ticker.getPriceChangePercent());
                        tickerData.put("weightedAvgPrice", ticker.getWeightedAvgPrice());
                        tickerData.put("lastPrice", ticker.getLastPrice());
                        tickerData.put("lastQty", ticker.getLastQty());
                        tickerData.put("openPrice", ticker.getOpenPrice());
                        tickerData.put("highPrice", ticker.getHighPrice());
                        tickerData.put("lowPrice", ticker.getLowPrice());
                        tickerData.put("volume", ticker.getVolume());
                        tickerData.put("quoteVolume", ticker.getQuoteVolume());
                        tickerData.put("openTime", ticker.getOpenTime());
                        tickerData.put("closeTime", ticker.getCloseTime());
                        tickerData.put("firstId", ticker.getFirstId());
                        tickerData.put("lastId", ticker.getLastId());
                        tickerData.put("count", ticker.getCount());
                    } else if (actualInstance instanceof Ticker24hrPriceChangeStatisticsResponse2) {
                        // Response2继承自ArrayList，可以直接当作List使用
                        Ticker24hrPriceChangeStatisticsResponse2 tickerList = (Ticker24hrPriceChangeStatisticsResponse2) actualInstance;
                        if (tickerList != null && !tickerList.isEmpty()) {
                            // 查找匹配的交易对
                            for (Ticker24hrPriceChangeStatisticsResponse2Inner ticker : tickerList) {
                                if (requestSymbol.equalsIgnoreCase(ticker.getSymbol())) {
                                    symbolValue = ticker.getSymbol();
                                    tickerData.put("symbol", ticker.getSymbol());
                                    tickerData.put("priceChange", ticker.getPriceChange());
                                    tickerData.put("priceChangePercent", ticker.getPriceChangePercent());
                                    tickerData.put("weightedAvgPrice", ticker.getWeightedAvgPrice());
                                    tickerData.put("lastPrice", ticker.getLastPrice());
                                    tickerData.put("lastQty", ticker.getLastQty());
                                    tickerData.put("openPrice", ticker.getOpenPrice());
                                    tickerData.put("highPrice", ticker.getHighPrice());
                                    tickerData.put("lowPrice", ticker.getLowPrice());
                                    tickerData.put("volume", ticker.getVolume());
                                    tickerData.put("quoteVolume", ticker.getQuoteVolume());
                                    tickerData.put("openTime", ticker.getOpenTime());
                                    tickerData.put("closeTime", ticker.getCloseTime());
                                    tickerData.put("firstId", ticker.getFirstId());
                                    tickerData.put("lastId", ticker.getLastId());
                                    tickerData.put("count", ticker.getCount());
                                    break;
                                }
                            }
                        }
                    }
                    
                    // 匹配正确的交易对数据
                    String normalizedSymbol = requestSymbol.toUpperCase();
                    
                    // 如果symbol匹配或者有lastPrice字段（说明是有效的价格数据），则添加结果
                    if (symbolValue != null && symbolValue.toUpperCase().equals(normalizedSymbol)) {
                        result.put(symbol.toUpperCase(), tickerData);
                        success++;
                        log.debug("[Binance Futures] {} 获取成功, 耗时 {} 毫秒", requestSymbol, callDuration);
                    } else if (tickerData.containsKey("lastPrice") && !tickerData.isEmpty()) {
                        // 即使symbol不匹配，如果有lastPrice字段，也认为是有效数据
                        result.put(symbol.toUpperCase(), tickerData);
                        success++;
                        log.debug("[Binance Futures] {} 获取成功（通过lastPrice字段验证）, 耗时 {} 毫秒", requestSymbol, callDuration);
                    } else {
                        log.warn("[Binance Futures] {} 交易对不匹配 (返回symbol: {}), 跳过", requestSymbol, symbolValue);
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
     * 使用 Symbol Price Ticker V2 API，参考官方示例实现。
     * 根据传入的symbol数量，逐个调用API获取每个交易对的价格。
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
            
            // 逐个调用API获取每个交易对的价格
            // 参考官方示例：symbolPriceTickerV2(symbol)
            for (int idx = 0; idx < symbols.size(); idx++) {
                String symbol = symbols.get(idx);
                String requestSymbol = symbol.toUpperCase();
                log.debug("[Binance Futures] 获取 {} 实时价格 ({}/{})", requestSymbol, idx + 1, total);
                
                try {
                    long callStart = System.currentTimeMillis();
                    
                    // 使用 symbolPriceTickerV2，参考官方示例
                    // 参考官方示例：symbolPriceTickerV2(symbol)
                    ApiResponse<SymbolPriceTickerV2Response> response = restApi.symbolPriceTickerV2(requestSymbol);
                    long callDuration = System.currentTimeMillis() - callStart;
                    
                    // 直接使用SDK的getData()方法获取响应数据
                    SymbolPriceTickerV2Response responseData = response.getData();
                    if (responseData == null) {
                        log.warn("[Binance Futures] {} 无返回数据，跳过", requestSymbol);
                        continue;
                    }
                    
                    // SymbolPriceTickerV2Response是oneOf类型，需要使用getActualInstance()获取实际实例
                    Object actualInstance = responseData.getActualInstance();
                    if (actualInstance == null) {
                        log.warn("[Binance Futures] {} 响应数据实例为null，跳过", requestSymbol);
                        continue;
                    }
                    
                    // 根据实际实例类型提取数据
                    Map<String, Object> priceData = new HashMap<>();
                    String symbolValue = null;
                    
                    if (actualInstance instanceof SymbolPriceTickerV2Response1) {
                        SymbolPriceTickerV2Response1 price = (SymbolPriceTickerV2Response1) actualInstance;
                        symbolValue = price.getSymbol();
                        priceData.put("symbol", price.getSymbol());
                        priceData.put("price", price.getPrice());
                        priceData.put("time", price.getTime());
                    } else if (actualInstance instanceof SymbolPriceTickerV2Response2) {
                        // Response2继承自ArrayList，可以直接当作List使用
                        SymbolPriceTickerV2Response2 priceList = (SymbolPriceTickerV2Response2) actualInstance;
                        if (priceList != null && !priceList.isEmpty()) {
                            // 查找匹配的交易对
                            for (SymbolPriceTickerV2Response2Inner price : priceList) {
                                if (requestSymbol.equalsIgnoreCase(price.getSymbol())) {
                                    symbolValue = price.getSymbol();
                                    priceData.put("symbol", price.getSymbol());
                                    priceData.put("price", price.getPrice());
                                    priceData.put("time", price.getTime());
                                    break;
                                }
                            }
                        }
                    }
                    
                    // 匹配正确的交易对数据
                    String normalizedSymbol = requestSymbol.toUpperCase();
                    
                    // 如果symbol匹配或者有price字段（说明是有效的价格数据），则添加结果
                    if (symbolValue != null && symbolValue.toUpperCase().equals(normalizedSymbol)) {
                        result.put(symbol.toUpperCase(), priceData);
                        success++;
                        log.debug("[Binance Futures] {} 获取成功, 耗时 {} 毫秒", requestSymbol, callDuration);
                    } else if (priceData.containsKey("price") && !priceData.isEmpty()) {
                        // 即使symbol不匹配，如果有price字段，也认为是有效数据
                        result.put(symbol.toUpperCase(), priceData);
                        success++;
                        log.debug("[Binance Futures] {} 获取成功（通过price字段验证）, 耗时 {} 毫秒", requestSymbol, callDuration);
                    } else {
                        log.warn("[Binance Futures] {} 交易对不匹配 (返回symbol: {}), 跳过", requestSymbol, symbolValue);
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
            // 如果 startTime 和 endTime 为空，自动计算时间范围
            Long calculatedStartTime = startTime;
            Long calculatedEndTime = endTime;
            
            if (calculatedStartTime == null || calculatedEndTime == null) {
                // endTime 取UTC+8当前时间
                calculatedEndTime = java.time.ZonedDateTime.now(java.time.ZoneOffset.ofHours(8)).toInstant().toEpochMilli();
                
                // 验证和转换limit参数（Binance API限制：1-1000）
                Long defaultLimit = ("1d".equals(interval) || "1w".equals(interval)) ? 99L : 499L;
                Long limitLong = (limit != null && limit > 0 && limit <= 1000) 
                    ? limit.longValue() 
                    : defaultLimit;
                
                // 计算interval对应的毫秒数
                long intervalMinutes = getIntervalMinutes(interval);
                long intervalMillis = intervalMinutes * 60 * 1000;
                
                // 将endTime向前跳一格（加上一个interval的时间）
                // 例如：如果当前是18:11:30，interval=1m，则endTime=18:12:30（当前时间+1分钟）
                // 例如：如果当前是18:11:30，interval=5m，则endTime=18:16:30（当前时间+5分钟）
                // 例如：如果当前是18:11:30，interval=1h，则endTime=19:11:30（当前时间+1小时）
                // 例如：如果当前是18:11:30，interval=1d，则endTime=明天18:11:30（当前时间+1天）
                // 这样确保返回的K线数据包含最新的K线周期
                calculatedEndTime = calculatedEndTime + intervalMillis;
                
                // startTime 根据 limit 和 interval 计算
                // 例如：limit=50, interval=1m，则 startTime = endTime - 50分钟
                // 由于endTime已对齐到K线周期开始，计算出的startTime也会对齐到K线周期开始
                long totalMinutes = limitLong * intervalMinutes;
                calculatedStartTime = calculatedEndTime - (totalMinutes * 60 * 1000);
                
                log.info("[Binance Futures] 自动计算时间范围: interval={} ({}分钟/根), limit={}, 总时间跨度={}分钟", 
                        interval, intervalMinutes, limitLong, totalMinutes);
                log.info("[Binance Futures] 计算的 startTime={}, endTime={}", calculatedStartTime, calculatedEndTime);
            }
            
            // 构建API调用参数
            Map<String, Object> params = new HashMap<>();
            params.put("symbol", symbol.toUpperCase());
            params.put("interval", interval);
            if (limit != null) {
                params.put("limit", limit);
            }
            if (calculatedStartTime != null) {
                params.put("startTime", calculatedStartTime);
            }
            if (calculatedEndTime != null) {
                params.put("endTime", calculatedEndTime);
            }
            
            // 调用API获取K线数据
            long apiStartTime = System.currentTimeMillis();
            List<KlineCandlestickDataResponseItem> items = null;
            
            try {
                String requestSymbol = symbol.toUpperCase();
                log.debug("[Binance Futures] 准备调用SDK获取K线数据, symbol={}, interval={}, limit={}, startTime={}, endTime={}", 
                        requestSymbol, interval, limit, calculatedStartTime, calculatedEndTime);
                
                // 将字符串interval转换为Interval枚举
                Interval intervalEnum = convertStringToInterval(interval);
                if (intervalEnum == null) {
                    log.error("[Binance Futures] 不支持的interval: {}", interval);
                    return new ArrayList<>();
                }
                
                // 验证和转换limit参数（Binance API限制：1-1000）
                // 1天（1d）和1周（1w）返回99根，其他interval返回499根
                Long defaultLimit = ("1d".equals(interval) || "1w".equals(interval)) ? 99L : 499L;
                Long limitLong = (limit != null && limit > 0 && limit <= 1000) 
                    ? limit.longValue() 
                    : defaultLimit;
                
                log.info("[Binance Futures] 调用参数: symbol={}, interval={}, startTime={}, endTime={}, limit={}", 
                        requestSymbol, intervalEnum, calculatedStartTime, calculatedEndTime, limitLong);
                
                // 调用SDK API获取K线数据
                // 参考官方示例：klineCandlestickData(symbol, interval, startTime, endTime, limit)
                ApiResponse<KlineCandlestickDataResponse> response = 
                        restApi.klineCandlestickData(requestSymbol, intervalEnum, calculatedStartTime, calculatedEndTime, limitLong);
                
                // 直接使用SDK的getData()方法获取KlineCandlestickDataResponse
                // KlineCandlestickDataResponse继承自ArrayList<KlineCandlestickDataResponseItem>，可以直接当作List使用
                if (response != null) {
                    KlineCandlestickDataResponse responseData = response.getData();
                    if (responseData != null) {
                        // KlineCandlestickDataResponse本身就是List<KlineCandlestickDataResponseItem>
                        items = responseData;
                        
                        if (items != null && !items.isEmpty()) {
                            log.debug("[Binance Futures] SDK响应获取成功, 返回 {} 条K线数据", items.size());
                        } else {
                            log.warn("[Binance Futures] SDK响应数据为空");
                        }
                    } else {
                        log.error("[Binance Futures] SDK响应数据为null");
                    }
                } else {
                    log.error("[Binance Futures] SDK响应为null");
                }
                
            } catch (Exception apiExc) {
                log.error("[Binance Futures] 调用SDK API失败: {}, 错误详情: {}", 
                        apiExc.getMessage(), apiExc.getClass().getName(), apiExc);
                // 不抛出异常，返回空列表，让上层处理
                items = null;
            }
            
            long apiDuration = System.currentTimeMillis() - apiStartTime;
            if (items != null) {
                log.info("[Binance Futures] API调用完成, 耗时: {} 毫秒, 返回 {} 条K线数据", 
                        apiDuration, items.size());
            } else {
                log.warn("[Binance Futures] API调用完成, 耗时: {} 毫秒, 但返回数据为空", apiDuration);
            }
            
            // 处理响应数据 - 直接使用SDK对象
            if (items != null && !items.isEmpty()) {
                for (KlineCandlestickDataResponseItem item : items) {
                    Map<String, Object> klineDict = new HashMap<>();
                    
                    // KlineCandlestickDataResponseItem继承自ArrayList<String>，可以直接当作List使用
                    // 直接使用item作为List<String>
                    if (item != null && item.size() >= 11) {
                        Long openTime = parseLong(item.get(0));
                        String openPrice = item.get(1);
                        String highPrice = item.get(2);
                        String lowPrice = item.get(3);
                        String closePrice = item.get(4);
                        String volume = item.get(5);
                        Long closeTime = parseLong(item.get(6));
                        String quoteAssetVolume = item.get(7);
                        Long numberOfTrades = parseLong(item.get(8));
                        String takerBuyBaseVolume = item.get(9);
                        String takerBuyQuoteVolume = item.get(10);
                        
                        // 时间戳转日期（UTC+8 香港/北京时间）：open_time_dt/open_time_dt_str 由 open_time 转换，close_time_dt/close_time_dt_str 由 close_time 转换
                        // 时间戳支持：10位=秒，13位=毫秒（自1970-01-01 00:00:00 UTC）；转换后 +8 小时对应服务器香港时间
                        LocalDateTime openTimeDt = null;
                        String openTimeDtStr = null;
                        if (openTime != null) {
                            long openTimeMs = toEpochMilli(openTime);
                            LocalDateTime openTimeLocal = Instant.ofEpochMilli(openTimeMs).atZone(ZoneOffset.ofHours(8)).toLocalDateTime();
                            openTimeDt = openTimeLocal;
                            openTimeDtStr = openTimeLocal.format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
                        }
                        LocalDateTime closeTimeDt = null;
                        String closeTimeDtStr = null;
                        if (closeTime != null) {
                            long closeTimeMs = toEpochMilli(closeTime);
                            LocalDateTime closeTimeLocal = Instant.ofEpochMilli(closeTimeMs).atZone(ZoneOffset.ofHours(8)).toLocalDateTime();
                            closeTimeDt = closeTimeLocal;
                            closeTimeDtStr = closeTimeLocal.format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
                        }
                        
                        klineDict.put("open_time", openTime);
                        klineDict.put("open_time_dt", openTimeDt);
                        klineDict.put("open_time_dt_str", openTimeDtStr);
                        klineDict.put("open", openPrice);
                        klineDict.put("high", highPrice);
                        klineDict.put("low", lowPrice);
                        klineDict.put("close", closePrice);
                        klineDict.put("volume", volume);
                        klineDict.put("close_time", closeTime);
                        klineDict.put("close_time_dt", closeTimeDt);
                        klineDict.put("close_time_dt_str", closeTimeDtStr);
                        klineDict.put("quote_asset_volume", quoteAssetVolume);
                        klineDict.put("number_of_trades", numberOfTrades);
                        klineDict.put("taker_buy_base_volume", takerBuyBaseVolume);
                        klineDict.put("taker_buy_quote_volume", takerBuyQuoteVolume);
                        
                        klines.add(klineDict);
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
     * 将时间戳统一为毫秒。支持 10 位（秒）或 13 位（毫秒），自 1970-01-01 00:00:00 UTC。
     */
    private long toEpochMilli(Long timestamp) {
        if (timestamp == null) {
            return 0L;
        }
        if (timestamp < 1_000_000_000_000L) {
            return timestamp * 1000L;
        }
        return timestamp;
    }
    
    /**
     * 根据interval字符串获取对应的分钟数
     * @param intervalStr 时间间隔字符串，如 "1m", "5m", "1h", "1d" 等
     * @return 对应的分钟数
     */
    private long getIntervalMinutes(String intervalStr) {
        if (intervalStr == null || intervalStr.isEmpty()) {
            return 1; // 默认1分钟
        }
        
        // 先检查大写M（月），因为toLowerCase()会把M变成m
        if (intervalStr.endsWith("M")) {
            // 月：1M
            String numStr = intervalStr.substring(0, intervalStr.length() - 1);
            try {
                return Long.parseLong(numStr) * 30 * 24 * 60; // 近似30天
            } catch (NumberFormatException e) {
                return 30 * 24 * 60;
            }
        }
        
        String lowerInterval = intervalStr.toLowerCase();
        
        // 解析数字和单位
        if (lowerInterval.endsWith("m")) {
            // 分钟：1m, 3m, 5m, 15m, 30m
            String numStr = lowerInterval.substring(0, lowerInterval.length() - 1);
            try {
                return Long.parseLong(numStr);
            } catch (NumberFormatException e) {
                return 1;
            }
        } else if (lowerInterval.endsWith("h")) {
            // 小时：1h, 2h, 4h, 6h, 8h, 12h
            String numStr = lowerInterval.substring(0, lowerInterval.length() - 1);
            try {
                return Long.parseLong(numStr) * 60;
            } catch (NumberFormatException e) {
                return 60;
            }
        } else if (lowerInterval.endsWith("d")) {
            // 天：1d, 3d
            String numStr = lowerInterval.substring(0, lowerInterval.length() - 1);
            try {
                return Long.parseLong(numStr) * 24 * 60;
            } catch (NumberFormatException e) {
                return 24 * 60;
            }
        } else if (lowerInterval.endsWith("w")) {
            // 周：1w
            String numStr = lowerInterval.substring(0, lowerInterval.length() - 1);
            try {
                return Long.parseLong(numStr) * 7 * 24 * 60;
            } catch (NumberFormatException e) {
                return 7 * 24 * 60;
            }
        }
        
        // 默认返回1分钟
        return 1;
    }
    
    /**
     * 将字符串interval转换为Interval枚举
     * 根据实际枚举值的toString()结果，枚举值可能是 "1m", "3m", "1h" 等格式
     * 或者 "INTERVAL_1m", "INTERVAL_3m" 等格式
     * 
     * @param intervalStr 字符串格式的interval，如 "1m", "5m", "1h", "1d" 等
     * @return Interval枚举值，如果不支持则返回null
     */
    private Interval convertStringToInterval(String intervalStr) {
        if (intervalStr == null || intervalStr.isEmpty()) {
            return null;
        }
        
        // 首先遍历所有枚举值，直接匹配toString()结果
        // 因为枚举值的toString()可能返回 "1m", "3m" 等格式
        try {
            Interval[] values = Interval.values();
            String inputLower = intervalStr.toLowerCase();
            String inputUpper = intervalStr.toUpperCase();
            
            // 优先尝试精确匹配（区分大小写）
            for (Interval interval : values) {
                String enumStr = interval.toString();
                // 精确匹配（区分大小写，避免"1m"匹配到"1M"）
                if (enumStr.equals(intervalStr)) {
                    log.debug("[Binance Futures] 精确匹配Interval枚举: {} -> {}", intervalStr, interval);
                    return interval;
                }
            }
            
            // 如果精确匹配失败，尝试忽略大小写匹配
            // 但要注意区分小写m（分钟）和大写M（月）
            for (Interval interval : values) {
                String enumStr = interval.toString();
                String enumLower = enumStr.toLowerCase();
                
                // 对于小写m（分钟），只匹配小写
                if (intervalStr.endsWith("m") && !intervalStr.endsWith("M")) {
                    if (enumLower.equals(inputLower) && enumStr.endsWith("m")) {
                        log.debug("[Binance Futures] 小写匹配Interval枚举: {} -> {}", intervalStr, interval);
                        return interval;
                    }
                }
                // 对于大写M（月），只匹配大写
                else if (intervalStr.endsWith("M") && !intervalStr.endsWith("m")) {
                    if (enumStr.toUpperCase().equals(inputUpper) && enumStr.endsWith("M")) {
                        log.debug("[Binance Futures] 大写匹配Interval枚举: {} -> {}", intervalStr, interval);
                        return interval;
                    }
                }
                // 其他情况，忽略大小写匹配
                else {
                    if (enumLower.equals(inputLower)) {
                        log.debug("[Binance Futures] 忽略大小写匹配Interval枚举: {} -> {}", intervalStr, interval);
                        return interval;
                    }
                }
            }
            
            // 如果直接匹配失败，尝试匹配枚举名称（可能包含INTERVAL_前缀）
            String[] possibleNames = {
                intervalStr,                           // 直接使用 1m, 3m
                "INTERVAL_" + intervalStr,            // INTERVAL_1m, INTERVAL_3m
                "INTERVAL_" + intervalStr.toLowerCase(), // INTERVAL_1m
                "INTERVAL_" + intervalStr.toUpperCase(), // INTERVAL_1M
            };
            
            for (String enumName : possibleNames) {
                try {
                    Interval result = Interval.valueOf(enumName);
                    log.debug("[Binance Futures] 通过枚举名称匹配Interval枚举: {} -> {}", intervalStr, result);
                    return result;
                } catch (IllegalArgumentException e) {
                    continue;
                }
            }
            
        } catch (Exception e) {
            log.warn("[Binance Futures] 查找Interval枚举失败: {}", e.getMessage());
        }
        
        log.error("[Binance Futures] 不支持的interval格式: {}", intervalStr);
        return null;
    }
}

