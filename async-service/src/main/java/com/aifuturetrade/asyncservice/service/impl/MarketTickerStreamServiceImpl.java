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
                    log.info("[MarketTickerStream] [DEBUG] 开始单次运行模式，运行时长: {} 秒", runSeconds);
                    runStreamOnce(runSeconds);
                    log.info("[MarketTickerStream] [DEBUG] 单次运行完成");
                } else {
                    // 无限运行，每30分钟自动重连
                    log.info("[MarketTickerStream] [DEBUG] 开始持续运行模式");
                    long startTime = System.currentTimeMillis();
                    while (running.get()) {
                        try {
                            reconnectCount++;
                            log.info("[MarketTickerStream] 🔗 [重连 {}] 开始建立WebSocket连接...", reconnectCount);
                            log.info("[MarketTickerStream] [DEBUG] 调用 runStreamOnce 开始，当前 running.get()={}", running.get());
                            
                            runStreamOnce(null);
                            reconnectCount = 0; // 重置重连计数
                            log.info("[MarketTickerStream] [DEBUG] runStreamOnce 正常返回，重连计数已重置");
                            
                            // 检查是否达到运行时长限制
                            if (runSeconds != null) {
                                long elapsed = (System.currentTimeMillis() - startTime) / 1000;
                                if (elapsed >= runSeconds) {
                                    log.info("[MarketTickerStream] ⏹️ 达到运行时长限制 {} 秒，停止流服务", runSeconds);
                                    break;
                                }
                            }
                            
                            // 等待一段时间后重连
                            log.info("[MarketTickerStream] ⏳ 等待 {} 秒后重新连接...", reconnectDelay);
                            Thread.sleep(reconnectDelay * 1000L);
                            
                        } catch (InterruptedException e) {
                            log.info("[MarketTickerStream] 🛑 WebSocket连接被中断");
                            Thread.currentThread().interrupt();
                            break;
                        } catch (Exception e) {
                            log.error("[MarketTickerStream] ❌ Stream error in main loop: {}", e.getMessage(), e);
                            log.error("[MarketTickerStream] ❌ 异常类型: {}, 异常消息: {}", e.getClass().getName(), e.getMessage());
                            reconnectCount++;
                            
                            // 等待一段时间后重连
                            try {
                                log.info("[MarketTickerStream] ⏳ [重连 {}] 等待5秒后重新连接...", reconnectCount);
                                Thread.sleep(5000);
                            } catch (InterruptedException ie) {
                                Thread.currentThread().interrupt();
                                break;
                            }
                        }
                    }
                    log.info("[MarketTickerStream] [DEBUG] 持续运行循环结束，当前 running.get()={}", running.get());
                }
            } catch (Exception e) {
                log.error("[MarketTickerStream] ❌ Stream processing error in outer catch", e);
                log.error("[MarketTickerStream] ❌ 外层异常类型: {}, 异常消息: {}", e.getClass().getName(), e.getMessage());
                log.error("[MarketTickerStream] ❌ 外层异常详细堆栈:", e);
            } finally {
                log.info("[MarketTickerStream] [DEBUG] 进入 finally 块，设置 running=false");
                running.set(false);
                log.info("[MarketTickerStream] 🏁 WebSocket流服务已停止");
            }
        });
    }
    
    /**
     * 运行一次流连接（最多30分钟）
     */
    private void runStreamOnce(Integer runSeconds) throws Exception {
        try {
            log.info("[MarketTickerStream] [DEBUG] 开始 runStreamOnce 方法，runSeconds={}", runSeconds);
            
            // 1. 获取 WebSocket 配置
            log.info("[MarketTickerStream] [DEBUG] 开始获取 WebSocket 配置...");
            WebSocketClientConfiguration config = null;
            try {
                config = DerivativesTradingUsdsFuturesWebSocketStreamsUtil.getClientConfiguration();
                log.info("[MarketTickerStream] [DEBUG] WebSocket 配置获取成功: {}", config != null ? "配置对象不为空" : "配置对象为空");
                
                if (config != null) {
                    log.info("[MarketTickerStream] [DEBUG] 配置详情: url={}", config.getUrl());
                }
            } catch (Exception configException) {
                log.error("[MarketTickerStream] ❌ WebSocket 配置获取失败: {}", configException.getClass().getName());
                log.error("[MarketTickerStream] ❌ 配置获取异常消息: {}", configException.getMessage());
                log.error("[MarketTickerStream] ❌ 配置获取异常堆栈:", configException);
                throw configException;
            }
            
            if (config == null) {
                log.error("[MarketTickerStream] ❌ WebSocket 配置为空");
                throw new RuntimeException("WebSocket configuration is null");
            }
            
            // 2. 初始化 WebSocket Streams - 增强异常处理
            log.info("[MarketTickerStream] [DEBUG] 开始初始化 WebSocket Streams...");
            try {
                log.info("[MarketTickerStream] [DEBUG] 准备创建 DerivativesTradingUsdsFuturesWebSocketStreams 实例...");
                log.info("[MarketTickerStream] [DEBUG] 配置对象信息: url={}", 
                         config.getUrl());
                
                webSocketStreams = new DerivativesTradingUsdsFuturesWebSocketStreams(config);
                log.info("[MarketTickerStream] [DEBUG] WebSocket Streams 初始化成功: {}", webSocketStreams != null ? "Streams对象不为空" : "Streams对象为空");
            } catch (Exception streamsException) {
                log.error("[MarketTickerStream] ❌ WebSocket Streams 初始化失败: {}", streamsException.getClass().getName());
                log.error("[MarketTickerStream] ❌ Streams初始化异常消息: {}", streamsException.getMessage());
                log.error("[MarketTickerStream] ❌ Streams初始化异常原因: {}", streamsException.getCause() != null ? streamsException.getCause().getMessage() : "无具体原因");
                log.error("[MarketTickerStream] ❌ Streams初始化异常堆栈:", streamsException);
                
                // 尝试诊断常见问题
                if (streamsException.getMessage() != null) {
                    String msg = streamsException.getMessage().toLowerCase();
                    if (msg.contains("classnotfound") || msg.contains("noclassdeffound")) {
                        log.error("[MarketTickerStream] 🔍 诊断: 可能是依赖类缺失，请检查Maven依赖是否正确安装");
                    } else if (msg.contains("no such method") || msg.contains("method not found")) {
                        log.error("[MarketTickerStream] 🔍 诊断: 可能是API方法不匹配，请检查Binance SDK版本");
                    } else if (msg.contains("connection") || msg.contains("network")) {
                        log.error("[MarketTickerStream] 🔍 诊断: 可能是网络连接问题，请检查网络连接");
                    } else if (msg.contains("timeout")) {
                        log.error("[MarketTickerStream] 🔍 诊断: 可能是连接超时，请检查网络延迟");
                    }
                }
                
                throw streamsException;
            }
            
            if (webSocketStreams == null) {
                log.error("[MarketTickerStream] ❌ WebSocket Streams 初始化失败: 对象为空");
                throw new RuntimeException("WebSocket streams initialization failed");
            }
            
            // 3. 创建请求对象
            log.info("[MarketTickerStream] [DEBUG] 开始创建请求对象...");
            AllMarketTickersStreamsRequest request = null;
            try {
                request = new AllMarketTickersStreamsRequest();
                log.info("[MarketTickerStream] [DEBUG] Request 创建成功: {}", request != null ? "Request对象不为空" : "Request对象为空");
            } catch (Exception requestException) {
                log.error("[MarketTickerStream] ❌ Request 创建失败: {}", requestException.getClass().getName());
                log.error("[MarketTickerStream] ❌ Request创建异常消息: {}", requestException.getMessage());
                throw requestException;
            }
            
            // 4. 订阅全市场Ticker流 - 使用正确的API方法
            log.info("[MarketTickerStream] 📡 正在订阅全市场Ticker流...");
            log.info("[MarketTickerStream] [DEBUG] 开始调用 webSocketStreams.allMarketTickersStreams(request)...");
            
            try {
                streamQueue = webSocketStreams.allMarketTickersStreams(request);
                log.info("[MarketTickerStream] [DEBUG] allMarketTickersStreams 调用成功，streamQueue: {}", streamQueue != null ? "队列不为空" : "队列为空");
            } catch (Exception wsException) {
                log.error("[MarketTickerStream] ❌ WebSocket 订阅失败: {}", wsException.getClass().getName());
                log.error("[MarketTickerStream] ❌ WebSocket 订阅异常消息: {}", wsException.getMessage());
                log.error("[MarketTickerStream] ❌ WebSocket 订阅异常堆栈:", wsException);
                throw wsException;
            }
            
            // 5. 记录连接创建时间
            connectionCreationTime = LocalDateTime.now();
            log.info("[MarketTickerStream] ✅ WebSocket连接已建立, 开始处理流数据...");
            log.info("[MarketTickerStream] [DEBUG] connectionCreationTime: {}", connectionCreationTime);
            
            // 6. 处理流数据
            log.info("[MarketTickerStream] [DEBUG] 开始调用 processStream 方法...");
            processStream(runSeconds);
            log.info("[MarketTickerStream] [DEBUG] processStream 方法执行完成");
            
        } catch (Exception e) {
            log.error("[MarketTickerStream] ❌ runStreamOnce 方法执行异常", e);
            log.error("[MarketTickerStream] ❌ 异常类型: {}", e.getClass().getName());
            log.error("[MarketTickerStream] ❌ 异常消息: {}", e.getMessage());
            log.error("[MarketTickerStream] ❌ 异常堆栈:", e);
            throw e; // 重新抛出异常，让上层处理
        } finally {
            log.info("[MarketTickerStream] [DEBUG] 进入 finally 块，设置 running=false");
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
     * 处理WebSocket流数据 - 优化版本，遵循SDK最佳实践
     */
    private void processStream(Integer runSeconds) {
        long startTime = System.currentTimeMillis();
        long messageCount = 0;
        
        log.info("[MarketTickerStream] [DEBUG] processStream 方法开始，runSeconds={}, startTime={}", runSeconds, startTime);
        
        try {
            log.info("[MarketTickerStream] 📊 开始处理WebSocket流数据...");
            
            // SDK设计理念：使用take()进行无限循环获取数据
            while (running.get()) {
                log.debug("[MarketTickerStream] [DEBUG] while循环开始，当前 running.get()={}, messageCount={}", running.get(), messageCount);
                
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
                
                // 从队列中获取ticker数据（遵循SDK最佳实践）
                log.debug("[MarketTickerStream] [DEBUG] 开始从队列获取数据...");
                try {
                    log.debug("[MarketTickerStream] [DEBUG] 调用 streamQueue.take()，当前队列: {}", streamQueue != null ? "队列存在" : "队列为空");
                    AllMarketTickersStreamsResponse response = streamQueue.take();
                    log.debug("[MarketTickerStream] [DEBUG] 从队列获取到数据: {}", response != null ? "有数据" : "空数据");
                    
                    messageCount++;
                    if (messageCount % 100 == 0) {
                        log.info("[MarketTickerStream] 📈 已处理 {} 条消息", messageCount);
                    }
                    handleMessage(response);
                    log.debug("[MarketTickerStream] [DEBUG] 消息处理完成");
                } catch (InterruptedException e) {
                    log.info("[MarketTickerStream] 🛑 Stream interrupted");
                    Thread.currentThread().interrupt();
                    break;
                } catch (Exception e) {
                    log.error("[MarketTickerStream] ❌ Error processing message", e);
                    log.error("[MarketTickerStream] ❌ 消息处理异常类型: {}, 异常消息: {}", e.getClass().getName(), e.getMessage());
                    // 继续处理，不中断流
                }
                log.debug("[MarketTickerStream] [DEBUG] while循环继续");
            }
            
            log.info("[MarketTickerStream] [DEBUG] processStream while循环结束");
            
        } catch (Exception e) {
            log.error("[MarketTickerStream] ❌ Stream processing error", e);
            log.error("[MarketTickerStream] ❌ processStream异常类型: {}, 异常消息: {}", e.getClass().getName(), e.getMessage());
        } finally {
            long totalTime = (System.currentTimeMillis() - startTime) / 1000;
            log.info("[MarketTickerStream] 🏁 Stream processing finished: 总计处理 {} 条消息, 运行 {} 秒", 
                    messageCount, totalTime);
            log.info("[MarketTickerStream] [DEBUG] processStream finally块完成");
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