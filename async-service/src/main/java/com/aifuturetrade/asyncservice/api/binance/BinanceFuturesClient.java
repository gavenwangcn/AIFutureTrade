package com.aifuturetrade.asyncservice.api.binance;

import com.binance.connector.client.common.ApiResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.Interval;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.KlineCandlestickDataResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.SymbolPriceTickerV2Response;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.SymbolPriceTickerV2Response1;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.SymbolPriceTickerV2Response2;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.SymbolPriceTickerV2Response2Inner;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.Ticker24hrPriceChangeStatisticsResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.Ticker24hrPriceChangeStatisticsResponse1;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.Ticker24hrPriceChangeStatisticsResponse2;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.Ticker24hrPriceChangeStatisticsResponse2Inner;
import lombok.extern.slf4j.Slf4j;

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
            for (int idx = 0; idx < symbols.size(); idx++) {
                String symbol = symbols.get(idx);
                String requestSymbol = symbol.toUpperCase();
                log.debug("[Binance Futures] 获取 {} 实时价格 ({}/{})", requestSymbol, idx + 1, total);
                
                try {
                    long callStart = System.currentTimeMillis();
                    
                    // 使用 symbolPriceTickerV2，参考官方示例
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
     * Kline/candlestick bars for a symbol. Klines are uniquely identified by their open time.
     * If startTime and endTime are not sent, the most recent klines are returned.
     * 
     * @param symbol 交易对符号，如 'BTCUSDT'
     * @param interval 时间间隔，如 '1d' 表示日K线
     * @param limit 返回数据数量，默认100，最大1000
     * @return KlineCandlestickDataResponse K线数据列表，每个元素包含：
     *         [0] 开盘时间, [1] 开盘价, [2] 最高价, [3] 最低价, [4] 收盘价, [5] 成交量,
     *         [6] 收盘时间, [7] 成交额, [8] 成交次数, [9] 主动买入成交量, [10] 主动买入成交额, [11] 忽略
     */
    public KlineCandlestickDataResponse getKlines(String symbol, String interval, int limit) {
        String requestSymbol = symbol.toUpperCase();
        log.debug("[Binance Futures] 开始获取 {} K线数据, 间隔: {}, 数量: {}", requestSymbol, interval, limit);
        
        KlineCandlestickDataResponse result = null;
        
        try {
            long callStart = System.currentTimeMillis();
            
            // 将字符串间隔转换为Interval枚举
            Interval intervalEnum = parseInterval(interval);
            
            // 调用API获取K线数据
            ApiResponse<KlineCandlestickDataResponse> response = restApi.klineCandlestickData(
                    requestSymbol, intervalEnum, null, null, (long) limit);
            
            long callDuration = System.currentTimeMillis() - callStart;
            
            // 获取响应数据
            KlineCandlestickDataResponse responseData = response.getData();
            if (responseData != null && !responseData.isEmpty()) {
                result = responseData;
                log.debug("[Binance Futures] {} K线数据获取成功, 返回 {} 条记录, 耗时 {} 毫秒", 
                        requestSymbol, result.size(), callDuration);
            } else {
                log.warn("[Binance Futures] {} K线数据为空", requestSymbol);
            }
            
        } catch (Exception exc) {
            log.error("[Binance Futures] 获取 {} K线数据失败: {}", requestSymbol, exc.getMessage(), exc);
        }
        
        return result;
    }
    
    /**
     * 将字符串间隔转换为Interval枚举
     * 
     * @param interval 字符串间隔，如 '1m', '5m', '1h', '4h', '1d'
     * @return Interval枚举值
     */
    private Interval parseInterval(String interval) {
        if (interval == null || interval.isEmpty()) {
            return Interval.INTERVAL_1d;
        }
        
        switch (interval.toLowerCase()) {
            case "1m": return Interval.INTERVAL_1m;
            case "3m": return Interval.INTERVAL_3m;
            case "5m": return Interval.INTERVAL_5m;
            case "15m": return Interval.INTERVAL_15m;
            case "30m": return Interval.INTERVAL_30m;
            case "1h": return Interval.INTERVAL_1h;
            case "2h": return Interval.INTERVAL_2h;
            case "4h": return Interval.INTERVAL_4h;
            case "6h": return Interval.INTERVAL_6h;
            case "8h": return Interval.INTERVAL_8h;
            case "12h": return Interval.INTERVAL_12h;
            case "1d": return Interval.INTERVAL_1d;
            case "3d": return Interval.INTERVAL_3d;
            case "1w": return Interval.INTERVAL_1w;
            case "1M": return Interval.INTERVAL_1M;
            default: return Interval.INTERVAL_1d;
        }
    }
    
    /**
     * 关闭客户端连接
     * 
     * 注意：DerivativesTradingUsdsFuturesRestApi没有close方法，
     * SDK内部使用HttpClient管理连接，JVM会自动清理资源
     */
    public void close() {
        log.info("[Binance Futures] 客户端连接已关闭（SDK使用HTTP连接池管理）");
    }
}

