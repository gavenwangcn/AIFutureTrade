package com.aifuturetrade.asyncservice.service.impl;

import com.aifuturetrade.asyncservice.dao.mapper.MarketTickerMapper;
import com.aifuturetrade.asyncservice.service.PriceRefreshService;
import com.aifuturetrade.asyncservice.api.binance.BinanceFuturesClient;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.KlineCandlestickDataResponseItem;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;

/**
 * 价格刷新服务实现
 * 
 * 定期刷新24_market_tickers表的开盘价格。
 * 通过获取币安期货的日K线数据，使用昨天的收盘价作为今天的开盘价。
 */
@Slf4j
@Service
public class PriceRefreshServiceImpl implements PriceRefreshService {
    
    private final MarketTickerMapper marketTickerMapper;
    private BinanceFuturesClient binanceClient;
    
    @Value("${async.price-refresh.cron:*/5 * * * *}")
    private String cronExpression;
    
    @Value("${async.price-refresh.max-per-minute:1000}")
    private int maxPerMinute;
    
    @Value("${binance.api-key}")
    private String apiKey;
    
    @Value("${binance.secret-key}")
    private String secretKey;
    
    @Value("${binance.quote-asset:USDT}")
    private String quoteAsset;
    
    private final AtomicBoolean schedulerRunning = new AtomicBoolean(false);
    private ExecutorService executorService;
    
    public PriceRefreshServiceImpl(MarketTickerMapper marketTickerMapper) {
        this.marketTickerMapper = marketTickerMapper;
    }
    
    @PostConstruct
    public void initBinanceClient() {
        this.binanceClient = new BinanceFuturesClient(apiKey, secretKey, quoteAsset, null, false);
    }
    
    @PostConstruct
    public void init() {
        executorService = Executors.newFixedThreadPool(10);
    }
    
    @PreDestroy
    public void destroy() {
        stopScheduler();
        if (executorService != null) {
            executorService.shutdown();
        }
    }
    
    @Override
    public RefreshResult refreshAllPrices() {
        log.info("=".repeat(80));
        log.info("[PriceRefresh] ========== 开始执行异步价格刷新任务 ==========");
        // 使用UTC+8时区时间（与数据库时区一致）
        log.info("[PriceRefresh] 执行时间: {}", LocalDateTime.now(java.time.ZoneOffset.ofHours(8)));
        log.info("[PriceRefresh] Cron表达式: {}", cronExpression);
        log.info("[PriceRefresh] 每分钟最大刷新数量: {}", maxPerMinute);
        log.info("=".repeat(80));
        
        try {
            // 获取UTC+8时间，用于数据库查询
            LocalDateTime utc8Time = LocalDateTime.now(java.time.ZoneOffset.ofHours(8));
            
            // 查询需要刷新的symbol列表
            log.info("[PriceRefresh] [步骤1] 开始查询需要刷新价格的symbol列表...");
            List<String> symbols = marketTickerMapper.selectSymbolsNeedingPriceRefresh(utc8Time);
            
            log.info("[PriceRefresh] [步骤1] 查询完成，返回 {} 个symbol", 
                    symbols != null ? symbols.size() : 0);
            
            if (symbols == null || symbols.isEmpty()) {
                log.info("[PriceRefresh] [步骤1] ⚠️  没有需要刷新价格的symbol");
                log.info("=".repeat(80));
                log.info("[PriceRefresh] ========== 价格刷新任务完成（无数据需要刷新） ==========");
                log.info("=".repeat(80));
                return new RefreshResult(0, 0, 0);
            }
            
            log.info("[PriceRefresh] [步骤1] ✅ 找到 {} 个需要刷新的symbol", symbols.size());
            if (symbols.size() > 10) {
                log.info("[PriceRefresh] [步骤1] 需要刷新的symbol列表（前10个）: {}", 
                        symbols.subList(0, 10));
                log.info("[PriceRefresh] [步骤1] 需要刷新的symbol列表（后5个）: {}", 
                        symbols.subList(symbols.size() - 5, symbols.size()));
            } else {
                log.info("[PriceRefresh] [步骤1] 需要刷新的symbol列表: {}", symbols);
            }
            
            // 批量刷新
            return refreshPricesBatch(symbols);
            
        } catch (Exception e) {
            log.error("[PriceRefresh] ========== 异步价格刷新任务执行失败 ==========", e);
            log.error("=".repeat(80));
            return new RefreshResult(0, 0, 0);
        }
    }
    
    @Override
    public boolean refreshPriceForSymbol(String symbol) {
        try {
            // 获取最近2天的日K线数据
            log.info("[PriceRefresh] 🔍 Symbol {}: 开始获取日K线数据...", symbol);
            List<Map<String, Object>> klines = binanceClient.getKlines(symbol, "1d", 2, null, null);
            
            log.info("[PriceRefresh] 📊 Symbol {}: 获取K线数据完成, 返回 {} 条记录", 
                    symbol, klines != null ? klines.size() : 0);
            
            if (klines == null || klines.isEmpty()) {
                log.warn("[PriceRefresh] ⚠️ Symbol {}: 没有K线数据", symbol);
                return false;
            }
            
            Double openPrice = null;
            String priceSource = "";
            
            if (klines.size() == 1) {
                // 如果只有1条K线，使用这条K线的开盘价
                Map<String, Object> singleKline = klines.get(0);
                log.info("[PriceRefresh] 📈 Symbol {}: 只有1条K线数据 - openTime={}, open={}, close={}", 
                        symbol, singleKline.get("open_time"), singleKline.get("open_price"), singleKline.get("close_price"));
                
                openPrice = extractOpenPrice(singleKline);
                priceSource = "单条K线的开盘价";
                
                log.info("[PriceRefresh] 💰 Symbol {}: 提取的{} = {}", symbol, priceSource, openPrice);
            } else {
                // 如果有2条或更多K线，使用第一条（昨天）的收盘价作为今天的开盘价
                Map<String, Object> yesterdayKline = klines.get(0);
                Map<String, Object> todayKline = klines.get(1);
                log.info("[PriceRefresh] 📈 Symbol {}: 昨天K线数据 - openTime={}, open={}, close={}", 
                        symbol, yesterdayKline.get("open_time"), yesterdayKline.get("open_price"), yesterdayKline.get("close_price"));
                log.info("[PriceRefresh] 📈 Symbol {}: 今天K线数据 - openTime={}, open={}, close={}", 
                        symbol, todayKline.get("open_time"), todayKline.get("open_price"), todayKline.get("close_price"));
                
                openPrice = extractClosePrice(yesterdayKline);
                priceSource = "昨天收盘价";
                
                log.info("[PriceRefresh] 💰 Symbol {}: 提取的{} = {}", symbol, priceSource, openPrice);
            }
            
            if (openPrice == null || openPrice <= 0) {
                log.warn("[PriceRefresh] ⚠️ Symbol {}: 无效的价格: {}", symbol, openPrice);
                return false;
            }
            
            // 更新open_price和update_price_date
            // 参考Python版本的逻辑：使用UTC+8时间作为update_price_date
            // 注意：updateOpenPrice方法内部会使用当前UTC+8时间，传入的updateDate参数会被忽略（为了兼容性仍然传递）
            LocalDateTime updateDate = LocalDateTime.now(java.time.ZoneOffset.ofHours(8));
            log.info("[PriceRefresh] 🗄️  Symbol {}: 开始更新数据库 open_price = {} ({}), update_price_date = {} (UTC+8)", 
                    symbol, openPrice, priceSource, updateDate);
            
            int updated = marketTickerMapper.updateOpenPrice(symbol, openPrice, updateDate);
            
            if (updated > 0) {
                log.info("[PriceRefresh] ✅ Symbol {}: 成功更新数据库 ({} = {}), 影响行数: {}", 
                        symbol, priceSource, openPrice, updated);
                return true;
            } else {
                log.warn("[PriceRefresh] ❌ Symbol {}: 更新open_price失败, 影响行数: {}", symbol, updated);
                return false;
            }
            
        } catch (Exception e) {
            log.error("[PriceRefresh] ❌ Symbol {}: Error refreshing price", symbol, e);
            return false;
        }
    }
    
    /**
     * 批量刷新价格
     */
    private RefreshResult refreshPricesBatch(List<String> symbols) {
        int total = symbols.size();
        AtomicInteger success = new AtomicInteger(0);
        AtomicInteger failed = new AtomicInteger(0);
        
        log.info("[PriceRefresh] [步骤2] 开始批量刷新: 总计 {} 个symbol, 每分钟最多处理 {} 个", 
                total, maxPerMinute);
        long startTime = System.currentTimeMillis();
        
        // 分批处理，每批最多maxPerMinute个
        int batchSize = maxPerMinute;
        int batchCount = (total + batchSize - 1) / batchSize;
        
        log.info("[PriceRefresh] [步骤2] 将分为 {} 个批次处理，每批最多 {} 个symbol", 
                batchCount, batchSize);
        
        for (int batchIdx = 0; batchIdx < batchCount; batchIdx++) {
            int start = batchIdx * batchSize;
            int end = Math.min(start + batchSize, total);
            List<String> batch = symbols.subList(start, end);
            
            log.info("[PriceRefresh] [批量刷新] [批次 {}/{}] 开始处理，包含 {} 个symbol: [{}]", 
                    batchIdx + 1, batchCount, batch.size(), 
                    String.join(", ", batch.stream().limit(10).collect(Collectors.toList())) + 
                    (batch.size() > 10 ? "..." : ""));
            
            long batchStartTime = System.currentTimeMillis();
            // 使用CountDownLatch等待当前批次所有任务完成
            CountDownLatch latch = new CountDownLatch(batch.size());
            
            // 并发刷新当前批次的所有symbol
            for (String symbol : batch) {
                executorService.submit(() -> {
                    try {
                        if (refreshPriceForSymbol(symbol)) {
                            success.incrementAndGet();
                        } else {
                            failed.incrementAndGet();
                        }
                    } finally {
                        latch.countDown();
                    }
                });
            }
            
            // 等待当前批次所有任务完成（最多等待5分钟）
            try {
                boolean completed = latch.await(5, TimeUnit.MINUTES);
                long batchCost = System.currentTimeMillis() - batchStartTime;
                if (!completed) {
                    log.warn("[PriceRefresh] [批量刷新] [批次 {}/{}] ⚠️ 等待超时(已用{}ms)，部分任务可能未完成", 
                            batchIdx + 1, batchCount, batchCost);
                } else {
                    log.info("[PriceRefresh] [批量刷新] [批次 {}/{}] ✅ 处理完成(用时{}ms)", 
                            batchIdx + 1, batchCount, batchCost);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                log.warn("[PriceRefresh] [批量刷新] [批次 {}/{}] 被中断", batchIdx + 1, batchCount);
                break;
            }
            
            log.info("[PriceRefresh] [批量刷新] [批次 {}/{}] 📊 批次统计: 成功 {}, 失败 {}, 总计 {}", 
                    batchIdx + 1, batchCount, success.get(), failed.get(), success.get() + failed.get());
            
            // 如果不是最后一批，等待1分钟再处理下一批
            if (batchIdx < batchCount - 1) {
                log.info("[PriceRefresh] [批量刷新] [批次 {}/{}] ⏳ 等待60秒后处理下一批次...", 
                        batchIdx + 1, batchCount);
                try {
                    Thread.sleep(60000);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
        }
        
        int successCount = success.get();
        int failedCount = failed.get();
        long totalCost = System.currentTimeMillis() - startTime;
        log.info("[PriceRefresh] [批量刷新] ✅ 批量刷新完成: 总计 {}, 成功 {} ({}%), 失败 {} ({}%), 总耗时 {}ms", 
                total, successCount, (total > 0 ? successCount * 100.0 / total : 0), 
                failedCount, (total > 0 ? failedCount * 100.0 / total : 0), totalCost);
        
        return new RefreshResult(total, successCount, failedCount);
    }
    
    /**
     * 从K线数据中提取开盘价
     * 支持新SDK的KlineCandlestickDataResponseItem类型和旧的Map类型
     * 
     * @param klineData K线数据对象
     * @return 开盘价，如果提取失败返回null
     */
    private Double extractOpenPrice(Object klineData) {
        try {
            if (klineData == null) {
                return null;
            }
            
            // 处理新SDK类型 KlineCandlestickDataResponseItem (继承ArrayList<String>)
            // 索引1是开盘价: [0]开盘时间,[1]开盘价,[2]最高价,[3]最低价,[4]收盘价,[5]成交量...
            if (klineData instanceof KlineCandlestickDataResponseItem) {
                KlineCandlestickDataResponseItem sdkKline = (KlineCandlestickDataResponseItem) klineData;
                if (sdkKline.size() > 1) {
                    String openPriceStr = sdkKline.get(1);
                    if (openPriceStr != null && !openPriceStr.isEmpty()) {
                        try {
                            return Double.parseDouble(openPriceStr);
                        } catch (NumberFormatException e) {
                            log.warn("[PriceRefresh] Invalid open_price format in SDK kline: {}", openPriceStr);
                        }
                    }
                }
                return null;
            }
            
            // 处理旧的Map类型
            if (klineData instanceof Map) {
                @SuppressWarnings("unchecked")
                Map<String, Object> kline = (Map<String, Object>) klineData;
                
                // BinanceFuturesClient返回的Map中包含"open_price"字段（String类型）
                Object openObj = kline.get("open_price");
                if (openObj == null) {
                    // 如果没有open_price，尝试open字段
                    openObj = kline.get("open");
                }
                
                if (openObj == null) {
                    log.warn("[PriceRefresh] Kline data missing open_price field");
                    return null;
                }
                
                if (openObj instanceof Number) {
                    return ((Number) openObj).doubleValue();
                } else if (openObj instanceof String) {
                    try {
                        return Double.parseDouble((String) openObj);
                    } catch (NumberFormatException e) {
                        log.warn("[PriceRefresh] Invalid open_price format: {}", openObj);
                        return null;
                    }
                } else {
                    log.warn("[PriceRefresh] Unexpected open_price type: {}", openObj.getClass());
                    return null;
                }
            }
            
            log.warn("[PriceRefresh] Unsupported kline data type: {}", klineData.getClass());
            return null;
            
        } catch (Exception e) {
            log.error("[PriceRefresh] Error extracting open price from kline", e);
            return null;
        }
    }
    
    /**
     * 从K线数据中提取收盘价
     * 支持新SDK的KlineCandlestickDataResponseItem类型和旧的Map类型
     */
    private Double extractClosePrice(Object klineData) {
        try {
            if (klineData == null) {
                return null;
            }
            
            // 处理新SDK类型 KlineCandlestickDataResponseItem (继承ArrayList<String>)
            // 索引4是收盘价: [0]开盘时间,[1]开盘价,[2]最高价,[3]最低价,[4]收盘价,[5]成交量...
            if (klineData instanceof KlineCandlestickDataResponseItem) {
                KlineCandlestickDataResponseItem sdkKline = (KlineCandlestickDataResponseItem) klineData;
                if (sdkKline.size() > 4) {
                    String closePriceStr = sdkKline.get(4);
                    if (closePriceStr != null && !closePriceStr.isEmpty()) {
                        try {
                            return Double.parseDouble(closePriceStr);
                        } catch (NumberFormatException e) {
                            log.warn("[PriceRefresh] Invalid close_price format in SDK kline: {}", closePriceStr);
                        }
                    }
                }
                return null;
            }
            
            // 处理旧的Map类型
            if (klineData instanceof Map) {
                @SuppressWarnings("unchecked")
                Map<String, Object> kline = (Map<String, Object>) klineData;
                
                // BinanceFuturesClient返回的Map中包含"close_price"字段（String类型）
                Object closeObj = kline.get("close_price");
                if (closeObj == null) {
                    // 如果没有close_price，尝试close字段
                    closeObj = kline.get("close");
                }
                
                if (closeObj == null) {
                    log.warn("[PriceRefresh] Kline data missing close_price field");
                    return null;
                }
                
                if (closeObj instanceof Number) {
                    return ((Number) closeObj).doubleValue();
                } else if (closeObj instanceof String) {
                    try {
                        return Double.parseDouble((String) closeObj);
                    } catch (NumberFormatException e) {
                        log.warn("[PriceRefresh] Invalid close_price format: {}", closeObj);
                        return null;
                    }
                } else {
                    log.warn("[PriceRefresh] Unexpected close_price type: {}", closeObj.getClass());
                    return null;
                }
            }
            
            log.warn("[PriceRefresh] Unsupported kline data type: {}", klineData.getClass());
            return null;
            
        } catch (Exception e) {
            log.error("[PriceRefresh] Error extracting close price from kline", e);
            return null;
        }
    }
    
    @Override
    @Scheduled(cron = "${async.price-refresh.cron:0 */5 * * * *}")
    public void startScheduler() {
        if (schedulerRunning.get()) {
            return;
        }
        
        schedulerRunning.set(true);
        try {
            refreshAllPrices();
        } finally {
            schedulerRunning.set(false);
        }
    }
    
    @Override
    public void stopScheduler() {
        schedulerRunning.set(false);
    }
}

