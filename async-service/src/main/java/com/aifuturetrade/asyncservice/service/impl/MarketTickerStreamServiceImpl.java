package com.aifuturetrade.asyncservice.service.impl;

import com.aifuturetrade.asyncservice.config.WebSocketConfig;
import com.aifuturetrade.asyncservice.dao.mapper.MarketTickerMapper;
import com.aifuturetrade.asyncservice.entity.MarketTickerDO;
import com.aifuturetrade.asyncservice.service.MarketTickerStreamService;
import com.binance.connector.client.common.websocket.adapter.stream.StreamConnectionWrapper;
import com.binance.connector.client.common.websocket.configuration.WebSocketClientConfiguration;
import com.binance.connector.client.common.websocket.service.StreamBlockingQueueWrapper;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.api.DerivativesTradingUsdsFuturesWebSocketStreams;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.DerivativesTradingUsdsFuturesWebSocketStreamsUtil;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.model.AllMarketTickersStreamsRequest;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.model.AllMarketTickersStreamsResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.model.AllMarketTickersStreamsResponseInner;
import lombok.extern.slf4j.Slf4j;
import org.eclipse.jetty.websocket.client.WebSocketClient;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import javax.annotation.PostConstruct;
import javax.annotation.PreDestroy;
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
    private final WebSocketConfig webSocketConfig;
    
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
    
    public MarketTickerStreamServiceImpl(MarketTickerMapper marketTickerMapper, WebSocketConfig webSocketConfig) {
        this.marketTickerMapper = marketTickerMapper;
        this.webSocketConfig = webSocketConfig;
        log.info("[MarketTickerStream] 注入WebSocket配置: maxTextMessageSize={} bytes", 
                webSocketConfig.getMaxTextMessageSize());
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
            // 1. 创建 WebSocketClientConfiguration
            log.info("[MarketTickerStream] 创建 WebSocketClientConfiguration...");
            WebSocketClientConfiguration config = new WebSocketClientConfiguration();
            
            log.info("[MarketTickerStream] WebSocket 配置创建成功，URL: {}", config.getUrl());
            
            // 2. 创建并配置 WebSocketClient（设置最大消息大小为 200KB）
            // 参考 SDK 测试代码：StreamConnectionWrapper 可以接受 WebSocketClient 参数
            // 使用 SDK 提供的 setMaxTextMessageSize 方法直接配置，无需反射
            log.info("[MarketTickerStream] 创建并配置 WebSocketClient...");
            WebSocketClient webSocketClient = new WebSocketClient();
            
            // 设置最大文本消息大小为 200KB（币安市场ticker数据约 68KB，默认 65KB 不够）
            // 使用 Jetty WebSocketClient 提供的 setMaxTextMessageSize 方法
            long maxMessageSize = webSocketConfig.getMaxTextMessageSize(); // 从配置文件读取
            webSocketClient.setMaxTextMessageSize(maxMessageSize);
            log.info("[MarketTickerStream] ✅ 已通过 setMaxTextMessageSize 方法设置最大消息大小为 {} 字节 ({})", 
                    maxMessageSize, formatBytes(maxMessageSize));
            
            // 3. 创建 StreamConnectionWrapper（使用配置好的 WebSocketClient）
            // 参考 SDK 测试代码：new StreamConnectionWrapper(config, webSocketClient)
            // 注意：根据测试代码，构造函数是 StreamConnectionWrapper(WebSocketClientConfiguration, WebSocketClient)
            log.info("[MarketTickerStream] 创建 StreamConnectionWrapper...");
            StreamConnectionWrapper connectionWrapper = new StreamConnectionWrapper(config, webSocketClient);
            log.info("[MarketTickerStream] StreamConnectionWrapper 创建成功");
            
            // 4. 使用 StreamConnectionInterface 构造函数创建 WebSocket Streams 实例
            // 参考 SDK 源码：DerivativesTradingUsdsFuturesWebSocketStreams(StreamConnectionInterface connection)
            log.info("[MarketTickerStream] 创建 DerivativesTradingUsdsFuturesWebSocketStreams 实例...");
            webSocketStreams = new DerivativesTradingUsdsFuturesWebSocketStreams(connectionWrapper);
            log.info("[MarketTickerStream] WebSocket Streams 实例创建成功");
            
            // 5. 创建请求对象
            log.info("[MarketTickerStream] 创建 AllMarketTickersStreamsRequest 请求对象...");
            AllMarketTickersStreamsRequest request = new AllMarketTickersStreamsRequest();
            log.info("[MarketTickerStream] 请求对象创建成功");
            
            // 6. 订阅全市场Ticker流 - 使用SDK标准方式
            log.info("[MarketTickerStream] 📡 订阅全市场Ticker流...");
            streamQueue = webSocketStreams.allMarketTickersStreams(request);
            log.info("[MarketTickerStream] 流订阅成功，开始接收数据...");
            
            // 7. 记录连接创建时间
            connectionCreationTime = LocalDateTime.now();
            log.info("[MarketTickerStream] ✅ WebSocket连接已建立，连接时间: {}", connectionCreationTime);
            
            // 8. 处理流数据 - 在单独的线程中处理
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
                    log.error("[MarketTickerStream] ❌ 异常堆栈:", e);
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
     * 格式化字节大小显示
     */
    private String formatBytes(long bytes) {
        if (bytes < 1024) {
            return bytes + "B";
        } else if (bytes < 1024 * 1024) {
            return String.format("%.1fKB", bytes / 1024.0);
        } else {
            return String.format("%.1fMB", bytes / (1024.0 * 1024.0));
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
    
}