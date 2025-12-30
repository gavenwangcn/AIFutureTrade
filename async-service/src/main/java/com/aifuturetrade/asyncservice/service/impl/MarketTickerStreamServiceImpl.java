package com.aifuturetrade.asyncservice.service.impl;

import com.aifuturetrade.asyncservice.dao.mapper.MarketTickerMapper;
import com.aifuturetrade.asyncservice.entity.MarketTickerDO;
import com.aifuturetrade.asyncservice.service.MarketTickerStreamService;
import com.binance.connector.client.common.websocket.configuration.WebSocketClientConfiguration;
import com.binance.connector.client.common.websocket.service.StreamBlockingQueueWrapper;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.api.DerivativesTradingUsdsFuturesWebSocketStreams;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.DerivativesTradingUsdsFuturesWebSocketStreamsUtil;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.model.AllMarketTickersStreamsRequest;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.model.AllMarketTickersStreamsResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.model.AllMarketTickersStreamsResponseInner;
import lombok.extern.slf4j.Slf4j;
import org.eclipse.jetty.websocket.client.WebSocketClient;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import javax.annotation.PostConstruct;
import javax.annotation.PreDestroy;
import java.lang.reflect.Field;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 市场Ticker流服务实现
 * 
 * 通过币安WebSocket接收所有交易对的24小时ticker数据，
 * 并将数据存储到MySQL的24_market_tickers表中。
 */
@Slf4j
@Service
public class MarketTickerStreamServiceImpl implements MarketTickerStreamService {
    
    private final MarketTickerMapper marketTickerMapper;
    
    @Value("${async.market-ticker.max-connection-minutes:30}")
    private int maxConnectionMinutes;
    
    @Value("${async.market-ticker.reconnect-delay:120}")
    private int reconnectDelay;
    
    @Value("${async.market-ticker.message-timeout:30}")
    private int messageTimeout;
    
    @Value("${async.market-ticker.db-operation-timeout:20}")
    private int dbOperationTimeout;
    
    private DerivativesTradingUsdsFuturesWebSocketStreams webSocketStreams;
    private StreamBlockingQueueWrapper<AllMarketTickersStreamsResponse> streamQueue;
    private ExecutorService executorService;
    private Future<?> streamTask;
    private final AtomicBoolean running = new AtomicBoolean(false);
    private LocalDateTime connectionCreationTime;
    
    public MarketTickerStreamServiceImpl(MarketTickerMapper marketTickerMapper) {
        this.marketTickerMapper = marketTickerMapper;
    }
    
    @PostConstruct
    public void init() {
        executorService = Executors.newSingleThreadExecutor(r -> {
            Thread t = new Thread(r, "MarketTickerStream-Thread");
            t.setDaemon(true);
            return t;
        });
    }
    
    @PreDestroy
    public void destroy() {
        stopStream();
        if (executorService != null) {
            executorService.shutdown();
        }
    }
    
    @Override
    public void startStream(Integer runSeconds) throws Exception {
        if (running.get()) {
            log.warn("[MarketTickerStream] ⚠️ Stream is already running");
            return;
        }
        
        running.set(true);
        connectionCreationTime = LocalDateTime.now();
        
        log.info("=".repeat(80));
        log.info("[MarketTickerStream] ========== 🔌 启动市场Ticker流服务 ==========");
        log.info("[MarketTickerStream] 🕐 启动时间: {}", LocalDateTime.now());
        log.info("[MarketTickerStream] ⏱️  最大连接时长: {} 分钟", maxConnectionMinutes);
        log.info("[MarketTickerStream] 🔄  重连延迟: {} 秒", reconnectDelay);
        log.info("[MarketTickerStream] ⌛  消息超时: {} 秒", messageTimeout);
        log.info("[MarketTickerStream] 🗄️  数据库操作超时: {} 秒", dbOperationTimeout);
        log.info("[MarketTickerStream] 🏃 运行模式: {}", runSeconds != null ? 
                String.format("单次运行 %d 秒", runSeconds) : "持续运行(自动重连)");
        log.info("=".repeat(80));
        
        // 启动流处理任务（支持自动重连）
        streamTask = executorService.submit(() -> {
            int reconnectCount = 0;
            try {
                if (runSeconds != null) {
                    // 如果指定了运行时长，只运行一次
                    log.info("[MarketTickerStream] 开始单次运行模式，运行时长: {} 秒", runSeconds);
                    startStreamProcessing(runSeconds);
                    log.info("[MarketTickerStream] 单次运行完成");
                } else {
                    // 无限运行，每30分钟自动重连
                    log.info("[MarketTickerStream] 开始持续运行模式（自动重连）");
                    while (running.get()) {
                        try {
                            reconnectCount++;
                            log.info("[MarketTickerStream] 🔗 [重连 {}] 开始建立WebSocket连接...", reconnectCount);
                            
                            // 启动流处理（会自动在30分钟后重连）
                            startStreamProcessing(null);
                            
                            reconnectCount = 0; // 重置重连计数
                            log.info("[MarketTickerStream] 连接正常结束，准备重连");
                            
                            // 等待一段时间后重连
                            if (running.get()) {
                                log.info("[MarketTickerStream] ⏳ 等待 {} 秒后重新连接...", reconnectDelay);
                                Thread.sleep(reconnectDelay * 1000L);
                            }
                            
                        } catch (InterruptedException e) {
                            log.info("[MarketTickerStream] 🛑 WebSocket连接被中断");
                            Thread.currentThread().interrupt();
                            break;
                        } catch (Exception e) {
                            log.error("[MarketTickerStream] ❌ Stream error in main loop: {}", e.getMessage(), e);
                            log.error("[MarketTickerStream] ❌ 异常类型: {}, 异常消息: {}", e.getClass().getName(), e.getMessage());
                            reconnectCount++;
                            
                            // 等待一段时间后重连
                            if (running.get()) {
                                try {
                                    log.info("[MarketTickerStream] ⏳ [重连 {}] 等待5秒后重新连接...", reconnectCount);
                                    Thread.sleep(5000);
                                } catch (InterruptedException ie) {
                                    Thread.currentThread().interrupt();
                                    break;
                                }
                            }
                        }
                    }
                    log.info("[MarketTickerStream] 持续运行循环结束");
                }
            } catch (Exception e) {
                log.error("[MarketTickerStream] ❌ Stream processing error in outer catch", e);
                log.error("[MarketTickerStream] ❌ 外层异常类型: {}, 异常消息: {}", e.getClass().getName(), e.getMessage());
            } finally {
                running.set(false);
                log.info("[MarketTickerStream] 🏁 WebSocket流服务已停止");
            }
        });
    }
    
    /**
     * 启动流处理 - 参考SDK官方示例实现
     * 完全按照 MarketTickerStreamTestServiceImpl 的方式构建和启动流
     */
    private void startStreamProcessing(Integer runSeconds) throws Exception {
        log.info("[MarketTickerStream] 开始启动流处理...");
        
        try {
            // 1. 获取 WebSocket 配置
            log.info("[MarketTickerStream] 获取 WebSocket 配置...");
            WebSocketClientConfiguration config = DerivativesTradingUsdsFuturesWebSocketStreamsUtil.getClientConfiguration();
            
            log.info("[MarketTickerStream] WebSocket 配置获取成功，URL: {}", config.getUrl());
            
            // 2. 创建 WebSocket Streams 实例
            log.info("[MarketTickerStream] 创建 DerivativesTradingUsdsFuturesWebSocketStreams 实例...");
            webSocketStreams = new DerivativesTradingUsdsFuturesWebSocketStreams(config);
            log.info("[MarketTickerStream] WebSocket Streams 实例创建成功");
            
            // 2.1 通过反射设置 WebSocketClient 的最大消息大小
            // 系统属性可能没有生效，需要直接设置 WebSocketClient 的 Policy
            try {
                configureWebSocketMaxMessageSize(webSocketStreams, 200 * 1024); // 200KB
                log.info("[MarketTickerStream] ✅ WebSocket 最大消息大小已设置为 200KB");
            } catch (Exception e) {
                log.warn("[MarketTickerStream] ⚠️ 设置 WebSocket 最大消息大小失败: {}", e.getMessage());
                log.warn("[MarketTickerStream] ⚠️ 将使用默认值，可能遇到消息过大错误");
            }
            
            // 3. 创建请求对象
            log.info("[MarketTickerStream] 创建 AllMarketTickersStreamsRequest 请求对象...");
            AllMarketTickersStreamsRequest request = new AllMarketTickersStreamsRequest();
            log.info("[MarketTickerStream] 请求对象创建成功");
            
            // 4. 订阅全市场Ticker流 - 使用SDK标准方式
            log.info("[MarketTickerStream] 📡 订阅全市场Ticker流...");
            streamQueue = webSocketStreams.allMarketTickersStreams(request);
            log.info("[MarketTickerStream] 流订阅成功，开始接收数据...");
            
            // 5. 记录连接创建时间
            connectionCreationTime = LocalDateTime.now();
            log.info("[MarketTickerStream] ✅ WebSocket连接已建立，连接时间: {}", connectionCreationTime);
            
            // 6. 处理流数据 - 在单独的线程中处理
            processStream(runSeconds);
            
        } catch (Exception e) {
            log.error("[MarketTickerStream] ❌ 启动流处理失败", e);
            log.error("[MarketTickerStream] ❌ 异常类型: {}, 异常消息: {}", e.getClass().getName(), e.getMessage());
            throw e;
        }
    }
    
    @Override
    public void stopStream() {
        if (!running.get()) {
            log.info("[MarketTickerStream] ℹ️  MarketTickerStream服务已经在停止状态");
            return;
        }
        
        log.info("[MarketTickerStream] 🛑 收到停止信号，正在停止市场Ticker流服务...");
        running.set(false);
        
        if (streamTask != null) {
            streamTask.cancel(true);
            log.info("[MarketTickerStream] ℹ️  流任务已取消");
        }
        
        log.info("[MarketTickerStream] ✅ MarketTickerStream服务已停止");
        // 注意：Java SDK的StreamBlockingQueueWrapper没有直接的unsubscribe方法
        // 连接会在关闭时自动取消订阅
    }
    
    @Override
    public boolean isRunning() {
        return running.get();
    }
    
    /**
     * 处理WebSocket流数据 - 参考SDK官方示例实现
     * 完全按照 MarketTickerStreamTestServiceImpl 的方式处理数据
     */
    private void processStream(Integer runSeconds) {
        long startTime = System.currentTimeMillis();
        long messageCount = 0;
        
        log.info("[MarketTickerStream] 📊 开始处理WebSocket流数据...");
        log.info("[MarketTickerStream] 等待接收WebSocket消息...");
        
        try {
            // SDK设计理念：使用take()进行无限循环获取数据
            // 参考 MarketTickerStreamTestServiceImpl 的实现方式
            while (running.get()) {
                try {
                    // 检查运行时长限制
                    if (runSeconds != null) {
                        long elapsed = (System.currentTimeMillis() - startTime) / 1000;
                        if (elapsed >= runSeconds) {
                            log.info("[MarketTickerStream] ⏹️ 达到运行时长限制 {} 秒，停止流服务", runSeconds);
                            break;
                        }
                    }
                    
                    // 检查连接时长限制（30分钟）
                    if (shouldReconnect()) {
                        log.info("[MarketTickerStream] 🔄 连接达到 {} 分钟限制，需要重新连接", maxConnectionMinutes);
                        break;
                    }
                    
                    // 使用 take() 阻塞等待数据，这是SDK示例的标准方式
                    AllMarketTickersStreamsResponse response = streamQueue.take();
                    
                    messageCount++;
                    long elapsedSeconds = (System.currentTimeMillis() - startTime) / 1000;
                    
                    // 处理消息
                    if (response != null) {
                        // AllMarketTickersStreamsResponse 继承自 ArrayList<AllMarketTickersStreamsResponseInner>
                        // 可以直接使用 List 的方法访问数据
                        int tickerCount = response.size();
                        
                        if (messageCount % 100 == 0 || messageCount <= 10) {
                            log.info("[MarketTickerStream] 📈 收到第 {} 条消息 (运行 {} 秒), 包含 {} 个ticker数据", 
                                    messageCount, elapsedSeconds, tickerCount);
                        }
                        
                        // 处理并存储ticker数据
                        handleMessage(response);
                        
                    } else {
                        log.warn("[MarketTickerStream] ⚠️ 收到空响应 (第 {} 条)", messageCount);
                    }
                    
                } catch (InterruptedException e) {
                    log.info("[MarketTickerStream] 🛑 流处理被中断");
                    Thread.currentThread().interrupt();
                    break;
                } catch (Exception e) {
                    log.error("[MarketTickerStream] ❌ 数据处理异常", e);
                    log.error("[MarketTickerStream] ❌ 异常类型: {}, 异常消息: {}", 
                            e.getClass().getName(), e.getMessage());
                    // 继续处理，不中断流
                }
            }
            
        } catch (Exception e) {
            log.error("[MarketTickerStream] ❌ Stream processing error", e);
            log.error("[MarketTickerStream] ❌ processStream异常类型: {}, 异常消息: {}", 
                    e.getClass().getName(), e.getMessage());
        } finally {
            long totalTime = (System.currentTimeMillis() - startTime) / 1000;
            log.info("[MarketTickerStream] 🏁 Stream processing finished: 总计处理 {} 条消息, 运行 {} 秒", 
                    messageCount, totalTime);
        }
    }
    
    /**
     * 处理接收到的ticker消息
     */
    private void handleMessage(AllMarketTickersStreamsResponse response) {
        try {
            if (response == null || response.isEmpty()) {
                log.warn("[MarketTickerStream] ⚠️ 收到空的ticker响应");
                return;
            }
            
            List<MarketTickerDO> tickers = normalizeTickers(response);
            if (tickers.isEmpty()) {
                log.warn("[MarketTickerStream] ⚠️ 标准化后的ticker数据为空");
                return;
            }
            
            // 批量插入或更新到数据库
            log.info("[MarketTickerStream] 🗄️  准备批量更新 {} 个ticker数据到数据库...", tickers.size());
            marketTickerMapper.batchUpsertTickers(tickers);
            log.debug("[MarketTickerStream] ✅ 成功处理 {} 个ticker数据", tickers.size());
            
        } catch (Exception e) {
            log.error("[MarketTickerStream] ❌ Error handling message", e);
        }
    }
    
    /**
     * 标准化ticker数据
     * AllMarketTickersStreamsResponse继承自ArrayList<AllMarketTickersStreamsResponseInner>
     */
    private List<MarketTickerDO> normalizeTickers(AllMarketTickersStreamsResponse response) {
        List<MarketTickerDO> tickers = new ArrayList<>();
        
        try {
            // AllMarketTickersStreamsResponse继承自ArrayList，可以直接遍历
            if (response == null || response.isEmpty()) {
                log.debug("[MarketTickerStream] ℹ️ 响应为空，跳过处理");
                return tickers;
            }
            
            int nullCount = 0;
            for (AllMarketTickersStreamsResponseInner inner : response) {
                MarketTickerDO ticker = normalizeSingleTicker(inner);
                if (ticker != null) {
                    tickers.add(ticker);
                } else {
                    nullCount++;
                }
            }
            
            if (nullCount > 0) {
                log.warn("[MarketTickerStream] ⚠️ 跳过 {} 个无效的ticker数据", nullCount);
            }
            
        } catch (Exception e) {
            log.error("[MarketTickerStream] ❌ Error normalizing tickers", e);
        }
        
        return tickers;
    }
    
    /**
     * 标准化单个ticker数据
     * 根据AllMarketTickersStreamsResponseInner的字段映射
     */
    private MarketTickerDO normalizeSingleTicker(AllMarketTickersStreamsResponseInner inner) {
        try {
            if (inner == null) {
                return null;
            }
            
            MarketTickerDO ticker = new MarketTickerDO();
            
            // 事件时间 (E: Long, 毫秒时间戳)
            if (inner.getE() != null) {
                ticker.setEventTime(LocalDateTime.ofInstant(
                    Instant.ofEpochMilli(inner.getE()), ZoneId.systemDefault()));
            }
            
            // 交易对符号 (s: String)
            ticker.setSymbol(inner.getsLowerCase());
            
            // 加权平均价 (w: String)
            if (inner.getwLowerCase() != null) {
                try {
                    ticker.setAveragePrice(Double.parseDouble(inner.getwLowerCase()));
                } catch (NumberFormatException e) {
                    log.warn("[MarketTickerStream] Invalid average_price: {}", inner.getwLowerCase());
                }
            }
            
            // 最新价格 (c: String)
            if (inner.getcLowerCase() != null) {
                try {
                    ticker.setLastPrice(Double.parseDouble(inner.getcLowerCase()));
                } catch (NumberFormatException e) {
                    log.warn("[MarketTickerStream] Invalid last_price: {}", inner.getcLowerCase());
                }
            }
            
            // 最后交易量 (Q: String)
            if (inner.getQ() != null) {
                try {
                    ticker.setLastTradeVolume(Double.parseDouble(inner.getQ()));
                } catch (NumberFormatException e) {
                    log.warn("[MarketTickerStream] Invalid last_trade_volume: {}", inner.getQ());
                }
            }
            
            // 最高价 (h: String)
            if (inner.gethLowerCase() != null) {
                try {
                    ticker.setHighPrice(Double.parseDouble(inner.gethLowerCase()));
                } catch (NumberFormatException e) {
                    log.warn("[MarketTickerStream] Invalid high_price: {}", inner.gethLowerCase());
                }
            }
            
            // 最低价 (l: String)
            if (inner.getlLowerCase() != null) {
                try {
                    ticker.setLowPrice(Double.parseDouble(inner.getlLowerCase()));
                } catch (NumberFormatException e) {
                    log.warn("[MarketTickerStream] Invalid low_price: {}", inner.getlLowerCase());
                }
            }
            
            // 基础成交量 (v: String)
            if (inner.getvLowerCase() != null) {
                try {
                    ticker.setBaseVolume(Double.parseDouble(inner.getvLowerCase()));
                } catch (NumberFormatException e) {
                    log.warn("[MarketTickerStream] Invalid base_volume: {}", inner.getvLowerCase());
                }
            }
            
            // 计价资产成交量 (q: String)
            if (inner.getqLowerCase() != null) {
                try {
                    ticker.setQuoteVolume(Double.parseDouble(inner.getqLowerCase()));
                } catch (NumberFormatException e) {
                    log.warn("[MarketTickerStream] Invalid quote_volume: {}", inner.getqLowerCase());
                }
            }
            
            // 统计开始时间 (O: Long, 毫秒时间戳)
            if (inner.getO() != null) {
                ticker.setStatsOpenTime(LocalDateTime.ofInstant(
                    Instant.ofEpochMilli(inner.getO()), ZoneId.systemDefault()));
            }
            
            // 统计结束时间 (C: Long, 毫秒时间戳)
            if (inner.getC() != null) {
                ticker.setStatsCloseTime(LocalDateTime.ofInstant(
                    Instant.ofEpochMilli(inner.getC()), ZoneId.systemDefault()));
            }
            
            // 第一笔交易ID (F: Long)
            ticker.setFirstTradeId(inner.getF());
            
            // 最后一笔交易ID (L: Long)
            ticker.setLastTradeId(inner.getL());
            
            // 交易数量 (n: Long)
            ticker.setTradeCount(inner.getnLowerCase());
            
            // 数据摄入时间
            ticker.setIngestionTime(LocalDateTime.now());
            
            return ticker;
        } catch (Exception e) {
            log.error("[MarketTickerStream] Error normalizing single ticker", e);
            return null;
        }
    }
    
    /**
     * 检查是否需要重新连接
     */
    private boolean shouldReconnect() {
        if (connectionCreationTime == null) {
            return false;
        }
        
        LocalDateTime now = LocalDateTime.now();
        Duration duration = Duration.between(connectionCreationTime, now);
        long minutes = duration.toMinutes();
        
        log.debug("[MarketTickerStream] [DEBUG] 连接时长检查: 当前时间={}, 连接创建时间={}, 已运行 {} 分钟", 
                 now, connectionCreationTime, minutes);
        
        return minutes >= maxConnectionMinutes;
    }
    
    /**
     * 通过反射配置 WebSocketClient 的最大消息大小
     * 参考 Binance SDK 源码结构，通过反射访问内部的 WebSocketClient 并设置 Policy
     * 
     * @param webSocketStreams WebSocket Streams 实例
     * @param maxSize 最大消息大小（字节）
     */
    private void configureWebSocketMaxMessageSize(DerivativesTradingUsdsFuturesWebSocketStreams webSocketStreams, int maxSize) {
        try {
            // 1. 获取 WebSocketStreams 内部的 connectionWrapper 字段
            Field connectionWrapperField = findField(webSocketStreams.getClass(), "connectionWrapper");
            if (connectionWrapperField == null) {
                log.warn("[MarketTickerStream] ⚠️ 未找到 connectionWrapper 字段");
                return;
            }
            
            connectionWrapperField.setAccessible(true);
            Object connectionWrapper = connectionWrapperField.get(webSocketStreams);
            if (connectionWrapper == null) {
                log.warn("[MarketTickerStream] ⚠️ connectionWrapper 为空");
                return;
            }
            
            // 2. 获取 ConnectionWrapper 内部的 webSocketClient 字段
            Field webSocketClientField = findField(connectionWrapper.getClass(), "webSocketClient");
            if (webSocketClientField == null) {
                log.warn("[MarketTickerStream] ⚠️ 未找到 webSocketClient 字段");
                return;
            }
            
            webSocketClientField.setAccessible(true);
            Object webSocketClientObj = webSocketClientField.get(connectionWrapper);
            if (webSocketClientObj == null) {
                log.warn("[MarketTickerStream] ⚠️ webSocketClient 为空");
                return;
            }
            
            // 3. 如果是 WebSocketClient 类型，通过反射设置 maxTextMessageSize
            if (webSocketClientObj instanceof WebSocketClient) {
                WebSocketClient webSocketClient = (WebSocketClient) webSocketClientObj;
                
                // Jetty 10 中，WebSocketClient 可能没有直接的 getPolicy() 方法
                // 尝试通过反射访问内部的 policy 字段或使用 setMaxTextMessageSize 方法
                try {
                    // 方法1: 尝试调用 setMaxTextMessageSize 方法（如果存在）
                    try {
                        java.lang.reflect.Method setMaxTextMessageSizeMethod = 
                            webSocketClient.getClass().getMethod("setMaxTextMessageSize", int.class);
                        setMaxTextMessageSizeMethod.invoke(webSocketClient, maxSize);
                        log.info("[MarketTickerStream] ✅ 已通过 setMaxTextMessageSize 方法设置最大消息大小为 {} 字节", maxSize);
                        return;
                    } catch (NoSuchMethodException e) {
                        // 方法不存在，继续尝试其他方式
                    }
                    
                    // 方法2: 尝试访问内部的 policy 字段
                    Field policyField = findField(webSocketClient.getClass(), "policy");
                    if (policyField != null) {
                        policyField.setAccessible(true);
                        Object policy = policyField.get(webSocketClient);
                        if (policy != null) {
                            // 尝试调用 policy 的 setMaxTextMessageSize 方法
                            try {
                                java.lang.reflect.Method policySetMethod = 
                                    policy.getClass().getMethod("setMaxTextMessageSize", int.class);
                                policySetMethod.invoke(policy, maxSize);
                                log.info("[MarketTickerStream] ✅ 已通过 Policy.setMaxTextMessageSize 设置最大消息大小为 {} 字节", maxSize);
                                return;
                            } catch (NoSuchMethodException e) {
                                log.warn("[MarketTickerStream] ⚠️ Policy 没有 setMaxTextMessageSize 方法");
                            }
                        }
                    }
                    
                    // 方法3: 尝试访问 WebSocketCoreSession 相关的配置
                    log.warn("[MarketTickerStream] ⚠️ 无法直接设置 WebSocketClient 的最大消息大小，将依赖系统属性");
                    
                } catch (Exception e) {
                    log.warn("[MarketTickerStream] ⚠️ 设置 WebSocketClient 最大消息大小失败: {}", e.getMessage());
                }
            } else {
                log.warn("[MarketTickerStream] ⚠️ webSocketClient 不是 WebSocketClient 类型: {}", 
                        webSocketClientObj.getClass().getName());
            }
            
        } catch (Exception e) {
            log.error("[MarketTickerStream] ❌ 配置 WebSocket 最大消息大小失败", e);
            throw new RuntimeException("配置 WebSocket 最大消息大小失败", e);
        }
    }
    
    /**
     * 查找字段（包括父类）
     */
    private Field findField(Class<?> clazz, String fieldName) {
        Class<?> currentClass = clazz;
        while (currentClass != null) {
            try {
                Field field = currentClass.getDeclaredField(fieldName);
                return field;
            } catch (NoSuchFieldException e) {
                currentClass = currentClass.getSuperclass();
            }
        }
        return null;
    }
}