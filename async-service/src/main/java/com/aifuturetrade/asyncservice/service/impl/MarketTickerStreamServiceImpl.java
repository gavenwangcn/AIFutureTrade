package com.aifuturetrade.asyncservice.service.impl;

import com.aifuturetrade.asyncservice.config.WebSocketConfig;
import com.aifuturetrade.asyncservice.dao.mapper.MarketTickerMapper;
import com.aifuturetrade.asyncservice.entity.ExistingSymbolData;
import com.aifuturetrade.asyncservice.entity.MarketTickerDO;
import com.aifuturetrade.asyncservice.service.MarketTickerStreamService;
import com.binance.connector.client.common.websocket.configuration.WebSocketClientConfiguration;
import com.binance.connector.client.common.websocket.service.StreamBlockingQueueWrapper;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.DerivativesTradingUsdsFuturesWebSocketStreamsUtil;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.api.DerivativesTradingUsdsFuturesWebSocketStreams;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.model.AllMarketTickersStreamsRequest;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.model.AllMarketTickersStreamsResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.model.AllMarketTickersStreamsResponseInner;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 市场Ticker流服务实现
 * 
 * 参考Python版本的market_streams.py实现，使用Binance SDK接收全市场ticker数据流，
 * 解析数据并同步到MySQL数据库。
 * 
 * 主要特性：
 * - 使用SDK泛型类解析数据（不使用反射）
 * - 自动重连：每30分钟自动重新建立连接（币安WebSocket连接限制）
 * - 批量同步：使用batchUpsertTickers批量插入/更新数据
 * - 异常处理：完善的错误处理和日志记录
 */
@Slf4j
@Service("marketTickerStreamService")
public class MarketTickerStreamServiceImpl implements MarketTickerStreamService {
    
    private final WebSocketConfig webSocketConfig;
    private final MarketTickerMapper marketTickerMapper;
    private DerivativesTradingUsdsFuturesWebSocketStreams api;
    private StreamBlockingQueueWrapper<AllMarketTickersStreamsResponse> response;
    private ExecutorService streamExecutor;
    private final AtomicBoolean running = new AtomicBoolean(false);
    
    // 连接生命周期管理
    private LocalDateTime connectionCreationTime;
    // 最大连接时长：30分钟（0.5小时）
    private static final double MAX_CONNECTION_HOURS = 0.5;
    
    @Autowired
    public MarketTickerStreamServiceImpl(WebSocketConfig webSocketConfig, MarketTickerMapper marketTickerMapper) {
        this.webSocketConfig = webSocketConfig;
        this.marketTickerMapper = marketTickerMapper;
    }
    
    /**
     * 初始化方法
     */
    @PostConstruct
    public void init() {
        log.info("[MarketTickerStreamService] 🚀 开始初始化市场Ticker流服务");
        
        try {
            // 获取API实例
            log.info("[MarketTickerStreamService] 📋 获取WebSocket API实例...");
            getApi();
            log.info("[MarketTickerStreamService] ✅ API实例获取成功");
            
            log.info("[MarketTickerStreamService] 🎉 市场Ticker流服务初始化完成");
            
        } catch (Exception e) {
            log.error("[MarketTickerStreamService] ❌ 服务初始化失败", e);
            throw new RuntimeException("MarketTickerStreamService服务初始化失败", e);
        }
    }
    
    /**
     * 销毁方法
     */
    @PreDestroy
    public void destroy() {
        log.info("[MarketTickerStreamService] 🛑 正在关闭市场Ticker流服务...");
        stopStream();
        log.info("[MarketTickerStreamService] ✅ 市场Ticker流服务已关闭");
    }
    
    /**
     * 获取API实例
     */
    @Override
    public DerivativesTradingUsdsFuturesWebSocketStreams getApi() {
        if (api == null) {
            WebSocketClientConfiguration clientConfiguration =
                    DerivativesTradingUsdsFuturesWebSocketStreamsUtil.getClientConfiguration();
            clientConfiguration.setMessageMaxSize(webSocketConfig.getMaxTextMessageSize());
            api = new DerivativesTradingUsdsFuturesWebSocketStreams(clientConfiguration);
        }
        return api;
    }
    
    /**
     * 启动ticker流服务
     * 
     * 参考Python版本的run_market_ticker_stream实现：
     * - 如果指定了runSeconds，只运行一次
     * - 如果未指定runSeconds，会无限循环运行，每次连接30分钟后自动重连
     */
    @Override
    public void startStream(Integer runSeconds) throws Exception {
        log.info("[MarketTickerStreamService] 🚀 启动ticker流服务（运行时长: {}秒）", 
                runSeconds != null ? runSeconds : "无限");
        
        if (running.get()) {
            log.warn("[MarketTickerStreamService] ⚠️ 服务已在运行中，跳过启动");
            return;
        }
        
        running.set(true);
        
        // 创建流处理线程池
        streamExecutor = Executors.newSingleThreadExecutor(r -> {
            Thread t = new Thread(r, "MarketTickerStream-Thread");
            t.setDaemon(true);
            return t;
        });
        
        // 提交流处理任务
        streamExecutor.submit(() -> {
            try {
                if (runSeconds != null) {
                    // 如果指定了运行时间，只运行一次
                    streamOnce(runSeconds);
                } else {
                    // 无限运行，每次连接30分钟后自动重连
                    streamWithAutoReconnect();
                }
            } catch (Exception e) {
                log.error("[MarketTickerStreamService] ❌ 流处理异常", e);
            } finally {
                running.set(false);
            }
        });
        
        log.info("[MarketTickerStreamService] ✅ ticker流服务启动成功");
    }
    
    /**
     * 运行一次流（指定时长）
     */
    private void streamOnce(int runSeconds) throws Exception {
        log.info("[MarketTickerStreamService] 📡 开始单次流处理（运行{}秒）", runSeconds);
        
        try {
            // 记录连接创建时间
            connectionCreationTime = LocalDateTime.now();
            log.debug("[MarketTickerStreamService] Creating new WebSocket connection");
            
            // 创建请求并获取流
            AllMarketTickersStreamsRequest request = new AllMarketTickersStreamsRequest();
            response = getApi().allMarketTickersStreams(request);
            log.info("[MarketTickerStreamService] ✅ WebSocket连接已建立");
            log.debug("[MarketTickerStreamService] Connection created at: {}", connectionCreationTime);
            
            // 计算结束时间
            long endTime = System.currentTimeMillis() + (runSeconds * 1000L);
            
            // 循环接收数据
            while (running.get() && System.currentTimeMillis() < endTime) {
                try {
                    AllMarketTickersStreamsResponse tickerResponse = response.take();
                    handleMessage(tickerResponse);
                } catch (InterruptedException e) {
                    log.warn("[MarketTickerStreamService] ⚠️ 流处理被中断");
                    Thread.currentThread().interrupt();
                    break;
                } catch (Exception e) {
                    log.error("[MarketTickerStreamService] ❌ 处理消息时出错", e);
                    // 继续处理下一条消息
                }
            }
            
            log.info("[MarketTickerStreamService] ✅ 单次流处理完成");
            
        } catch (Exception e) {
            log.error("[MarketTickerStreamService] ❌ 流处理失败", e);
            throw e;
        }
    }
    
    /**
     * 无限运行流（自动重连）
     * 
     * 参考Python版本的实现：每次连接30分钟后自动重连
     */
    private void streamWithAutoReconnect() throws Exception {
        log.info("[MarketTickerStreamService] 📡 开始自动重连流处理");
        
        while (running.get()) {
            try {
                // 记录连接创建时间
                connectionCreationTime = LocalDateTime.now();
                log.debug("[MarketTickerStreamService] Creating new WebSocket connection");
                log.info("[MarketTickerStreamService] 🔄 创建新的WebSocket连接");
                
                // 创建请求并获取流
                AllMarketTickersStreamsRequest request = new AllMarketTickersStreamsRequest();
                response = getApi().allMarketTickersStreams(request);
                log.info("[MarketTickerStreamService] ✅ WebSocket连接已建立");
                log.debug("[MarketTickerStreamService] Connection created at: {}", connectionCreationTime);
                
                // 循环接收数据，直到需要重连
                while (running.get() && !shouldReconnect()) {
                    try {
                        AllMarketTickersStreamsResponse tickerResponse = response.take();
                        handleMessage(tickerResponse);
                    } catch (InterruptedException e) {
                        log.warn("[MarketTickerStreamService] ⚠️ 流处理被中断");
                        Thread.currentThread().interrupt();
                        return;
                    } catch (Exception e) {
                        log.error("[MarketTickerStreamService] ❌ 处理消息时出错", e);
                        // 继续处理下一条消息
                    }
                }
                
                // 检查是否需要重连
                if (shouldReconnect()) {
                    log.debug("[MarketTickerStreamService] Connection reached 30-minute limit, reconnecting...");
                    log.info("[MarketTickerStreamService] 🔄 连接已达到30分钟限制，准备重连...");
                    // 等待一小段时间后重连，避免快速重连循环
                    Thread.sleep(5000);
                }
                
            } catch (InterruptedException e) {
                log.warn("[MarketTickerStreamService] ⚠️ 流处理被中断");
                Thread.currentThread().interrupt();
                break;
            } catch (Exception e) {
                log.error("[MarketTickerStreamService] Streaming error: {}", e.getMessage(), e);
                log.error("[MarketTickerStreamService] ❌ 流处理异常，5秒后重连...", e);
                // 等待5秒后重连，避免快速重连循环
                try {
                    Thread.sleep(5000);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
        }
        
        log.info("[MarketTickerStreamService] ✅ 自动重连流处理结束");
    }
    
    /**
     * 检查是否需要重新连接
     * 
     * 币安WebSocket连接有30分钟的限制，超过30分钟需要重新建立连接。
     * 
     * @return true如果需要重新连接，否则返回false
     */
    private boolean shouldReconnect() {
        if (connectionCreationTime == null) {
            log.debug("[MarketTickerStreamService] Connection creation time not recorded, no reconnect needed");
            return false;
        }
        long elapsedSeconds = java.time.Duration.between(connectionCreationTime, LocalDateTime.now()).getSeconds();
        double elapsedHours = elapsedSeconds / 3600.0;
        boolean needReconnect = elapsedHours >= MAX_CONNECTION_HOURS;
        if (needReconnect) {
            log.debug("[MarketTickerStreamService] Connection elapsed time: {} hours (limit: {} hours), reconnect needed", 
                    elapsedHours, MAX_CONNECTION_HOURS);
        } else {
            log.debug("[MarketTickerStreamService] Connection elapsed time: {} hours (limit: {} hours), no reconnect needed", 
                    elapsedHours, MAX_CONNECTION_HOURS);
        }
        return needReconnect;
    }
    
    /**
     * 处理WebSocket接收到的ticker消息
     * 
     * 参考Python版本的_handle_message实现：
     * 1. 从AllMarketTickersStreamsResponse中提取ticker数据列表
     * 2. 标准化每个ticker数据（参考_normalize_ticker）
     * 3. 筛选USDT交易对
     * 4. 查询现有数据并计算price_change等字段
     * 5. 批量插入/更新到数据库（使用batchUpsertTickers）
     * 
     * @param tickerResponse SDK返回的AllMarketTickersStreamsResponse对象
     */
    private void handleMessage(AllMarketTickersStreamsResponse tickerResponse) {
        try {
            log.debug("[MarketTickerStreamService] Starting to handle message");
            
            // AllMarketTickersStreamsResponse继承自ArrayList<AllMarketTickersStreamsResponseInner>
            // 直接遍历即可获取所有ticker数据
            if (tickerResponse == null || tickerResponse.isEmpty()) {
                log.debug("[MarketTickerStreamService] 消息为空，跳过处理");
                log.info("[MarketTickerStreamService] No tickers to process");
                return;
            }
            
            int tickerCount = tickerResponse.size();
            log.debug("[MarketTickerStreamService] Extracted {} tickers from message", tickerCount);
            log.debug("[MarketTickerStreamService] 提取到{}个ticker数据", tickerCount);
            
            // 步骤1: 标准化ticker数据
            List<MarketTickerDO> allNormalizedTickers = new ArrayList<>();
            for (AllMarketTickersStreamsResponseInner inner : tickerResponse) {
                MarketTickerDO tickerDO = normalizeTicker(inner);
                if (tickerDO != null) {
                    allNormalizedTickers.add(tickerDO);
                }
            }
            
            if (allNormalizedTickers.isEmpty()) {
                log.debug("[MarketTickerStreamService] 没有有效的ticker数据，跳过数据库操作");
                log.info("[MarketTickerStreamService] No tickers to process");
                return;
            }
            
            // 步骤2: 筛选USDT交易对（参考Python版本的逻辑）
            List<MarketTickerDO> usdtTickers = allNormalizedTickers.stream()
                    .filter(t -> t.getSymbol() != null && t.getSymbol().endsWith("USDT"))
                    .collect(Collectors.toList());
            
            log.info("[MarketTickerStreamService] 从{}条总数据中筛选出{}条USDT交易对数据", 
                    allNormalizedTickers.size(), usdtTickers.size());
            
            if (usdtTickers.isEmpty()) {
                log.debug("[MarketTickerStreamService] No USDT symbols to upsert");
                return;
            }
            
            // 步骤3: 查询现有数据（参考Python版本的get_existing_symbol_data）
            List<String> symbols = usdtTickers.stream()
                    .map(MarketTickerDO::getSymbol)
                    .collect(Collectors.toList());
            
            log.debug("[MarketTickerStreamService] Querying existing data for {} symbols", symbols.size());
            List<ExistingSymbolData> existingDataList = marketTickerMapper.getExistingSymbolData(symbols);
            
            // 转换为Map便于查找
            Map<String, ExistingSymbolData> existingDataMap = new HashMap<>();
            for (ExistingSymbolData data : existingDataList) {
                existingDataMap.put(data.getSymbol(), data);
            }
            log.debug("[MarketTickerStreamService] Retrieved existing data for {} symbols", existingDataMap.size());
            
            // 步骤4: 计算price_change等字段并准备最终数据（参考Python版本的逻辑）
            List<MarketTickerDO> finalTickers = new ArrayList<>();
            for (MarketTickerDO ticker : usdtTickers) {
                String symbol = ticker.getSymbol();
                ExistingSymbolData existingData = existingDataMap.get(symbol);
                
                // 获取当前last_price
                Double currentLastPrice = ticker.getLastPrice();
                if (currentLastPrice == null) {
                    currentLastPrice = 0.0;
                }
                
                // 获取existing_open_price（参考Python版本的逻辑）
                // Python版本逻辑：
                // if open_price_raw == 0.0 and update_price_date is None:
                //     open_price = None
                // else:
                //     open_price = open_price_raw if open_price_raw is not None else None
                Double existingOpenPrice = null;
                LocalDateTime existingUpdatePriceDate = null;
                if (existingData != null) {
                    Double openPriceRaw = existingData.getOpenPrice();
                    LocalDateTime updatePriceDate = existingData.getUpdatePriceDate();
                    
                    // 如果open_price为0.0且update_price_date为null，则表示不存在（open_price应该为None/null）
                    if (openPriceRaw != null && openPriceRaw == 0.0 && updatePriceDate == null) {
                        existingOpenPrice = null; // 表示不存在
                    } else if (openPriceRaw != null) {
                        existingOpenPrice = openPriceRaw;
                    }
                    existingUpdatePriceDate = updatePriceDate;
                    
                    log.debug("[MarketTickerStreamService] Existing data for {}: open_price={}, update_price_date={}", 
                            symbol, existingOpenPrice, existingUpdatePriceDate);
                }
                
                // 计算price_change等字段（参考Python版本的逻辑）
                if (existingOpenPrice != null && existingOpenPrice != 0.0 && currentLastPrice != 0.0) {
                    try {
                        double priceChange = currentLastPrice - existingOpenPrice;
                        double priceChangePercent = (priceChange / existingOpenPrice) * 100.0;
                        String side = priceChangePercent >= 0 ? "gainer" : "loser";
                        String changePercentText = String.format("%.2f%%", priceChangePercent);
                        
                        log.debug("[MarketTickerStreamService] Calculated price change for {}: {} ({:.2f}%)", 
                                symbol, priceChange, priceChangePercent);
                        
                        ticker.setPriceChange(priceChange);
                        ticker.setPriceChangePercent(priceChangePercent);
                        ticker.setSide(side);
                        ticker.setChangePercentText(changePercentText);
                        ticker.setOpenPrice(existingOpenPrice);
                        ticker.setUpdatePriceDate(existingUpdatePriceDate);
                    } catch (Exception e) {
                        log.warn("[MarketTickerStreamService] Failed to calculate price change for symbol {}: {}", symbol, e.getMessage());
                        ticker.setPriceChange(0.0);
                        ticker.setPriceChangePercent(0.0);
                        ticker.setSide("");
                        ticker.setChangePercentText("");
                        ticker.setOpenPrice(existingOpenPrice != null ? existingOpenPrice : 0.0);
                        ticker.setUpdatePriceDate(existingUpdatePriceDate);
                    }
                } else {
                    log.debug("[MarketTickerStreamService] Not calculating price change for {}", symbol);
                    ticker.setPriceChange(0.0);
                    ticker.setPriceChangePercent(0.0);
                    ticker.setSide("");
                    ticker.setChangePercentText("");
                    // 参考Python版本的逻辑：
                    // 如果不存在existing_symbol_data，则open_price设为0.0，update_price_date设为null
                    // 如果存在existing_symbol_data，则使用existing_open_price和existing_update_price_date
                    if (existingData == null) {
                        ticker.setOpenPrice(0.0);
                        ticker.setUpdatePriceDate(null);
                        log.debug("[MarketTickerStreamService] 设置{}的open_price为0.0（新插入）", symbol);
                    } else {
                        ticker.setOpenPrice(existingOpenPrice != null ? existingOpenPrice : 0.0);
                        ticker.setUpdatePriceDate(existingUpdatePriceDate);
                    }
                }
                
                // 参考Python版本的逻辑：在INSERT时，如果不存在existing_symbol_data，则open_price=0.0，update_price_date=NULL
                // 如果存在existing_symbol_data，则使用existing_open_price和existing_update_price_date
                // 参考Python版本：insert_open_price和insert_update_price_date的处理
                if (existingData == null) {
                    // 新插入：open_price=0.0，update_price_date=NULL（参考Python版本：if not existing_symbol_data）
                    ticker.setOpenPrice(0.0);
                    ticker.setUpdatePriceDate(null);
                }
                // 如果存在existing_symbol_data，则使用上面已设置的值（existing_open_price和existing_update_price_date）
                
                // 设置默认值（参考Python版本的逻辑）
                if (ticker.getPriceChange() == null) ticker.setPriceChange(0.0);
                if (ticker.getPriceChangePercent() == null) ticker.setPriceChangePercent(0.0);
                if (ticker.getSide() == null) ticker.setSide("");
                if (ticker.getChangePercentText() == null) ticker.setChangePercentText("");
                if (ticker.getAveragePrice() == null) ticker.setAveragePrice(0.0);
                if (ticker.getLastPrice() == null) ticker.setLastPrice(0.0);
                if (ticker.getLastTradeVolume() == null) ticker.setLastTradeVolume(0.0);
                if (ticker.getOpenPrice() == null) ticker.setOpenPrice(0.0);
                if (ticker.getHighPrice() == null) ticker.setHighPrice(0.0);
                if (ticker.getLowPrice() == null) ticker.setLowPrice(0.0);
                if (ticker.getBaseVolume() == null) ticker.setBaseVolume(0.0);
                if (ticker.getQuoteVolume() == null) ticker.setQuoteVolume(0.0);
                if (ticker.getFirstTradeId() == null) ticker.setFirstTradeId(0L);
                if (ticker.getLastTradeId() == null) ticker.setLastTradeId(0L);
                if (ticker.getTradeCount() == null) ticker.setTradeCount(0L);
                
                // 转换时区为北京时区（UTC+8）（参考Python版本的_to_beijing_datetime）
                if (ticker.getEventTime() != null) {
                    ticker.setEventTime(toBeijingDateTime(ticker.getEventTime()));
                }
                if (ticker.getStatsOpenTime() != null) {
                    ticker.setStatsOpenTime(toBeijingDateTime(ticker.getStatsOpenTime()));
                }
                if (ticker.getStatsCloseTime() != null) {
                    ticker.setStatsCloseTime(toBeijingDateTime(ticker.getStatsCloseTime()));
                }
                
                // ingestion_time使用当前北京时区时间
                ticker.setIngestionTime(LocalDateTime.now(ZoneOffset.ofHours(8)));
                
                finalTickers.add(ticker);
            }
            
            int finalCount = finalTickers.size();
            log.debug("[MarketTickerStreamService] Normalized {} tickers for database upsert", finalCount);
            log.debug("[MarketTickerStreamService] 标准化了{}个ticker数据，准备批量同步到数据库", finalCount);
            
            // 记录部分关键数据用于调试（前3个作为样本）
            if (finalTickers.size() > 0) {
                int sampleSize = Math.min(3, finalTickers.size());
                List<MarketTickerDO> sample = finalTickers.subList(0, sampleSize);
                log.debug("[MarketTickerStreamService] Normalized data sample (first {}): {}", sampleSize, 
                        sample.stream()
                                .map(t -> String.format("symbol=%s, lastPrice=%s, openPrice=%s, priceChangePercent=%s", 
                                        t.getSymbol(), t.getLastPrice(), t.getOpenPrice(), t.getPriceChangePercent()))
                                .reduce((a, b) -> a + "; " + b)
                                .orElse(""));
            }
            
            // 步骤5: 批量插入/更新到数据库
            try {
                log.debug("[MarketTickerStreamService] Calling batchUpsertTickers for {} symbols", finalCount);
                long startTime = System.currentTimeMillis();
                marketTickerMapper.batchUpsertTickers(finalTickers);
                long duration = System.currentTimeMillis() - startTime;
                log.debug("[MarketTickerStreamService] Successfully completed batchUpsertTickers in {} ms", duration);
                log.info("[MarketTickerStreamService] ✅ 成功同步{}个ticker数据到数据库（耗时{}ms）", finalCount, duration);
            } catch (Exception e) {
                log.error("[MarketTickerStreamService] Error during batchUpsertTickers: {}", e.getMessage(), e);
                log.error("[MarketTickerStreamService] ❌ 批量同步ticker数据到数据库失败", e);
            }
            
            log.debug("[MarketTickerStreamService] Finished handling message");
            
        } catch (Exception e) {
            log.error("[MarketTickerStreamService] Unexpected error in message handling: {}", e.getMessage(), e);
            log.error("[MarketTickerStreamService] ❌ 处理ticker消息时出错", e);
        }
    }
    
    /**
     * 将时间转换为北京时区（UTC+8）
     * 参考Python版本的_to_beijing_datetime实现
     * 
     * Python版本的逻辑：
     * 1. 先将naive datetime转换为UTC（假设输入是UTC）
     * 2. 转换为北京时区（UTC+8）
     * 3. 返回naive datetime（去掉时区信息）
     * 
     * @param dateTime 原始时间（假设为UTC naive datetime）
     * @return 北京时区时间（naive datetime）
     */
    private LocalDateTime toBeijingDateTime(LocalDateTime dateTime) {
        if (dateTime == null) {
            return null;
        }
        try {
            // 假设输入是UTC时间（naive datetime），先转换为UTC Instant
            Instant instant = dateTime.atZone(ZoneOffset.UTC).toInstant();
            // 转换为北京时区（UTC+8）
            return LocalDateTime.ofInstant(instant, ZoneOffset.ofHours(8));
        } catch (Exception e) {
            log.warn("[MarketTickerStreamService] Failed to convert to Beijing time: {}", e.getMessage());
            return dateTime;
        }
    }
    
    /**
     * 标准化ticker数据
     * 
     * 参考Python版本的_normalize_ticker实现，将SDK返回的AllMarketTickersStreamsResponseInner
     * 转换为MarketTickerDO对象。
     * 
     * 注意：不再从报文中解析以下字段，这些字段将在PriceRefreshService中根据业务逻辑计算：
     * - price_change: 价格变化
     * - price_change_percent: 价格变化百分比
     * - side: 涨跌方向（gainer/loser）
     * - change_percent_text: 价格变化百分比文本
     * - open_price: 开盘价
     * 
     * @param inner SDK返回的AllMarketTickersStreamsResponseInner对象
     * @return 标准化后的MarketTickerDO对象，如果数据无效则返回null
     */
    private MarketTickerDO normalizeTicker(AllMarketTickersStreamsResponseInner inner) {
        if (inner == null) {
            return null;
        }
        
        try {
            // 先获取symbol用于日志
            String symbol = inner.getsLowerCase();
            log.debug("[MarketTickerStreamService] Normalizing ticker data for symbol: {}", symbol);
            
            // 记录原始数据（仅关键字段）
            log.debug("[MarketTickerStreamService] Raw ticker data for {}: E={}, s={}, w={}, c={}, h={}, l={}, v={}, q={}", 
                    symbol, inner.getE(), symbol, inner.getwLowerCase(), inner.getcLowerCase(), 
                    inner.gethLowerCase(), inner.getlLowerCase(), inner.getvLowerCase(), inner.getqLowerCase());
            
            MarketTickerDO tickerDO = new MarketTickerDO();
            
            // 事件时间（E字段，毫秒时间戳）
            // 注意：币安返回的时间戳是UTC时间，后续会在handleMessage中转换为北京时区
            Long eventTimeMs = inner.getE();
            if (eventTimeMs != null && eventTimeMs > 0) {
                // 先转换为UTC时间
                tickerDO.setEventTime(LocalDateTime.ofInstant(
                    Instant.ofEpochMilli(eventTimeMs), ZoneOffset.UTC));
            }
            
            // 交易对符号（s字段，小写）
            if (symbol == null || symbol.isEmpty()) {
                log.debug("[MarketTickerStreamService] Symbol为空，跳过此ticker");
                return null;
            }
            tickerDO.setSymbol(symbol);
            
            // 加权平均价（w字段，小写）
            String wValue = inner.getwLowerCase();
            if (wValue != null && !wValue.isEmpty()) {
                try {
                    tickerDO.setAveragePrice(Double.parseDouble(wValue));
                } catch (NumberFormatException e) {
                    log.debug("[MarketTickerStreamService] 无法解析average_price: {}", wValue);
                }
            }
            
            // 最新价格（c字段，小写）
            String cValue = inner.getcLowerCase();
            if (cValue != null && !cValue.isEmpty()) {
                try {
                    tickerDO.setLastPrice(Double.parseDouble(cValue));
                } catch (NumberFormatException e) {
                    log.debug("[MarketTickerStreamService] 无法解析last_price: {}", cValue);
                }
            }
            
            // 最新交易量（Q字段）
            String qValue = inner.getQ();
            if (qValue != null && !qValue.isEmpty()) {
                try {
                    tickerDO.setLastTradeVolume(Double.parseDouble(qValue));
                } catch (NumberFormatException e) {
                    log.debug("[MarketTickerStreamService] 无法解析last_trade_volume: {}", qValue);
                }
            }
            
            // 24小时最高价（h字段，小写）
            String hValue = inner.gethLowerCase();
            if (hValue != null && !hValue.isEmpty()) {
                try {
                    tickerDO.setHighPrice(Double.parseDouble(hValue));
                } catch (NumberFormatException e) {
                    log.debug("[MarketTickerStreamService] 无法解析high_price: {}", hValue);
                }
            }
            
            // 24小时最低价（l字段，小写）
            String lValue = inner.getlLowerCase();
            if (lValue != null && !lValue.isEmpty()) {
                try {
                    tickerDO.setLowPrice(Double.parseDouble(lValue));
                } catch (NumberFormatException e) {
                    log.debug("[MarketTickerStreamService] 无法解析low_price: {}", lValue);
                }
            }
            
            // 24小时基础资产成交量（v字段，小写）
            String vValue = inner.getvLowerCase();
            if (vValue != null && !vValue.isEmpty()) {
                try {
                    tickerDO.setBaseVolume(Double.parseDouble(vValue));
                } catch (NumberFormatException e) {
                    log.debug("[MarketTickerStreamService] 无法解析base_volume: {}", vValue);
                }
            }
            
            // 24小时计价资产成交量（q字段，小写）
            String qLowerValue = inner.getqLowerCase();
            if (qLowerValue != null && !qLowerValue.isEmpty()) {
                try {
                    tickerDO.setQuoteVolume(Double.parseDouble(qLowerValue));
                } catch (NumberFormatException e) {
                    log.debug("[MarketTickerStreamService] 无法解析quote_volume: {}", qLowerValue);
                }
            }
            
            // 统计开始时间（O字段，毫秒时间戳）
            // 注意：币安返回的时间戳是UTC时间，后续会在handleMessage中转换为北京时区
            Long oValue = inner.getO();
            if (oValue != null && oValue > 0) {
                tickerDO.setStatsOpenTime(LocalDateTime.ofInstant(
                    Instant.ofEpochMilli(oValue), ZoneOffset.UTC));
            }
            
            // 统计结束时间（C字段，毫秒时间戳）
            // 注意：币安返回的时间戳是UTC时间，后续会在handleMessage中转换为北京时区
            Long cValueLong = inner.getC();
            if (cValueLong != null && cValueLong > 0) {
                tickerDO.setStatsCloseTime(LocalDateTime.ofInstant(
                    Instant.ofEpochMilli(cValueLong), ZoneOffset.UTC));
            }
            
            // 第一笔交易ID（F字段）
            Long fValue = inner.getF();
            if (fValue != null) {
                tickerDO.setFirstTradeId(fValue);
            }
            
            // 最后一笔交易ID（L字段）
            Long lValueLong = inner.getL();
            if (lValueLong != null) {
                tickerDO.setLastTradeId(lValueLong);
            }
            
            // 24小时交易笔数（n字段，小写）
            Long nValue = inner.getnLowerCase();
            if (nValue != null) {
                tickerDO.setTradeCount(nValue);
            }
            
            // 数据摄入时间（当前时间，将在handleMessage中设置为北京时区）
            // 这里先不设置，在handleMessage中统一处理
            
            // 记录标准化后的数据（仅关键字段）
            log.debug("[MarketTickerStreamService] Normalized ticker data for {}: symbol={}, eventTime={}, " +
                    "averagePrice={}, lastPrice={}, highPrice={}, lowPrice={}, baseVolume={}, quoteVolume={}, " +
                    "tradeCount={}", 
                    symbol, tickerDO.getSymbol(), tickerDO.getEventTime(), 
                    tickerDO.getAveragePrice(), tickerDO.getLastPrice(), 
                    tickerDO.getHighPrice(), tickerDO.getLowPrice(), 
                    tickerDO.getBaseVolume(), tickerDO.getQuoteVolume(), 
                    tickerDO.getTradeCount());
            
            return tickerDO;
            
        } catch (Exception e) {
            log.error("[MarketTickerStreamService] ❌ 标准化ticker数据时出错", e);
            return null;
        }
    }
    
    /**
     * 停止流处理
     */
    @Override
    public void stopStream() {
        log.info("[MarketTickerStreamService] 🛑 正在停止ticker流...");
        
        running.set(false);
        
        if (streamExecutor != null && !streamExecutor.isShutdown()) {
            streamExecutor.shutdown();
            try {
                if (!streamExecutor.awaitTermination(60, TimeUnit.SECONDS)) {
                    log.warn("[MarketTickerStreamService] ⚠️ 流处理线程未在60秒内完全关闭，强制关闭");
                    streamExecutor.shutdownNow();
                } else {
                    log.info("[MarketTickerStreamService] ✅ 流处理线程已成功关闭");
                }
            } catch (InterruptedException e) {
                log.error("[MarketTickerStreamService] ❌ 等待流处理线程关闭时被中断", e);
                streamExecutor.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
        
        log.info("[MarketTickerStreamService] ✅ ticker流已停止");
    }
    
    /**
     * 检查服务状态
     */
    @Override
    public boolean isRunning() {
        return running.get();
    }
}

