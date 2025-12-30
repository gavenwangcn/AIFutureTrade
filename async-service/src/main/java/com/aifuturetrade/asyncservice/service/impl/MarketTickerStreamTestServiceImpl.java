/*
 * MarketTickerStreamTestServiceImpl
 * 
 * 完全按照Binance SDK官方示例 AllMarketTickersStreamsExample.java 实现的测试服务
 * 用于排查MarketTickerStreamServiceImpl启动失败的问题
 */

package com.aifuturetrade.asyncservice.service.impl;

import com.aifuturetrade.asyncservice.config.WebSocketConfig;
import com.aifuturetrade.asyncservice.service.MarketTickerStreamTestService;
import com.binance.connector.client.common.ApiException;
import com.binance.connector.client.common.websocket.adapter.stream.StreamConnectionWrapper;
import com.binance.connector.client.common.websocket.configuration.WebSocketClientConfiguration;
import com.binance.connector.client.common.websocket.service.StreamBlockingQueueWrapper;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.DerivativesTradingUsdsFuturesWebSocketStreamsUtil;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.api.DerivativesTradingUsdsFuturesWebSocketStreams;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.model.AllMarketTickersStreamsRequest;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.model.AllMarketTickersStreamsResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.model.AllMarketTickersStreamsResponseInner;
import lombok.extern.slf4j.Slf4j;
import org.eclipse.jetty.websocket.client.WebSocketClient;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import javax.annotation.PostConstruct;
import javax.annotation.PreDestroy;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * MarketTickerStreamTestServiceImpl - 测试服务实现
 * 
 * 完全复制SDK官方示例 AllMarketTickersStreamsExample.java 的实现方式
 * 用于验证Binance WebSocket SDK的基本功能和排查问题
 * 
 * 官方示例关键实现点：
 * 1. 使用 DerivativesTradingUsdsFuturesWebSocketStreamsUtil.getClientConfiguration() 获取配置
 * 2. 使用 new DerivativesTradingUsdsFuturesWebSocketStreams(clientConfiguration) 创建实例
 * 3. 使用 getApi().allMarketTickersStreams(request) 获取流
 * 4. 使用 response.take() 循环获取数据
 */
@Slf4j
@Service("marketTickerStreamTestService")
public class MarketTickerStreamTestServiceImpl implements MarketTickerStreamTestService {
    
    // ===== SDK示例中的核心组件 =====
    private final WebSocketConfig webSocketConfig;
    private DerivativesTradingUsdsFuturesWebSocketStreams api;
    private StreamBlockingQueueWrapper<AllMarketTickersStreamsResponse> response;
    private ExecutorService streamExecutor;
    private final AtomicBoolean running = new AtomicBoolean(false);
    
    public MarketTickerStreamTestServiceImpl(WebSocketConfig webSocketConfig) {
        this.webSocketConfig = webSocketConfig;
        log.info("[MarketTickerStreamTestImpl] 注入WebSocket配置: maxTextMessageSize={} bytes", 
                webSocketConfig.getMaxTextMessageSize());
    }
    
    /**
     * 初始化方法 - 按照SDK示例实现
     */
    @PostConstruct
    public void init() {
        log.info("[MarketTickerStreamTestImpl] 🚀 开始初始化测试服务（完全按照SDK官方示例）");
        
        try {
            // ===== 步骤1: 获取API实例 - SDK示例方式 =====
            log.info("[MarketTickerStreamTestImpl] 📋 步骤1: 按照SDK示例获取WebSocket API实例...");
            getApi();
            log.info("[MarketTickerStreamTestImpl] ✅ API实例获取成功");
            
            // ===== 步骤2: 启动流处理 - SDK示例方式 =====
            log.info("[MarketTickerStreamTestImpl] 📡 步骤2: 启动WebSocket流处理...");
            startStreamProcessing();
            log.info("[MarketTickerStreamTestImpl] ✅ 流处理启动成功");
            
            log.info("[MarketTickerStreamTestImpl] 🎉 测试服务初始化完成");
            
        } catch (Exception e) {
            log.error("[MarketTickerStreamTestImpl] ❌ 测试服务初始化失败", e);
            log.error("[MarketTickerStreamTestImpl] ❌ 异常类型: {}", e.getClass().getName());
            log.error("[MarketTickerStreamTestImpl] ❌ 异常消息: {}", e.getMessage());
            throw new RuntimeException("MarketTickerStreamTestImpl服务初始化失败", e);
        }
    }
    
    /**
     * 销毁方法
     */
    @PreDestroy
    public void destroy() {
        log.info("[MarketTickerStreamTestImpl] 🛑 正在关闭测试服务...");
        stopStream();
        log.info("[MarketTickerStreamTestImpl] ✅ 测试服务已关闭");
    }
    
    /**
     * 获取API实例 - 使用MarketTickerStreamServiceImpl方式构建WebSocketClientConfiguration和WebSocketClient
     */
    @Override
    public DerivativesTradingUsdsFuturesWebSocketStreams getApi() {
        if (api == null) {
            log.info("[MarketTickerStreamTestImpl] [优化模式] 使用MarketTickerStreamServiceImpl方式创建WebSocketStreams实例...");
            
            try {
                // ===== 步骤1: 创建WebSocketClientConfiguration - MarketTickerStreamServiceImpl方式 =====
                log.info("[MarketTickerStreamTestImpl] [优化模式] 步骤1: 创建WebSocketClientConfiguration...");
                WebSocketClientConfiguration config = new WebSocketClientConfiguration();
                log.info("[MarketTickerStreamTestImpl] [优化模式] ✅ WebSocketClientConfiguration创建成功");
                log.info("[MarketTickerStreamTestImpl] [优化模式] 配置URL: {}", config.getUrl());
                
                // ===== 步骤2: 创建并配置WebSocketClient - MarketTickerStreamServiceImpl方式 =====
                log.info("[MarketTickerStreamTestImpl] [优化模式] 步骤2: 创建并配置WebSocketClient...");
                WebSocketClient webSocketClient = new WebSocketClient();
                
                // 设置最大文本消息大小为 200KB（币安市场ticker数据约 68KB，默认 65KB 不够）
                // 使用 Jetty WebSocketClient 提供的 setMaxTextMessageSize 方法
                int maxMessageSize = webSocketConfig.getMaxTextMessageSize(); // 从配置文件读取
                webSocketClient.setMaxTextMessageSize(maxMessageSize);
                webSocketClient.setMaxBinaryMessageSize(maxMessageSize);
                log.info("[MarketTickerStreamTestImpl] [优化模式] ✅ 已通过 setMaxTextMessageSize 方法设置最大消息大小为 {} 字节 ({})", 
                        maxMessageSize, formatBytes(maxMessageSize));
                
                // ===== 步骤3: 创建StreamConnectionWrapper - MarketTickerStreamServiceImpl方式 =====
                log.info("[MarketTickerStreamTestImpl] [优化模式] 步骤3: 创建StreamConnectionWrapper...");
                StreamConnectionWrapper connectionWrapper = new StreamConnectionWrapper(config, webSocketClient);
                log.info("[MarketTickerStreamTestImpl] [优化模式] ✅ StreamConnectionWrapper创建成功");
                
                // ===== 步骤4: 使用StreamConnectionInterface构造函数创建WebSocket Streams实例 =====
                log.info("[MarketTickerStreamTestImpl] [优化模式] 步骤4: 创建DerivativesTradingUsdsFuturesWebSocketStreams实例...");
                api = new DerivativesTradingUsdsFuturesWebSocketStreams(connectionWrapper);
                log.info("[MarketTickerStreamTestImpl] [优化模式] ✅ WebSocketStreams实例创建成功: {}", api != null ? "实例存在" : "实例为空");
                
            } catch (Exception e) {
                log.error("[MarketTickerStreamTestImpl] ❌ 优化模式创建API实例失败", e);
                log.error("[MarketTickerStreamTestImpl] ❌ 创建失败异常类型: {}", e.getClass().getName());
                log.error("[MarketTickerStreamTestImpl] ❌ 创建失败异常消息: {}", e.getMessage());
                throw new RuntimeException("无法创建WebSocket API实例", e);
            }
        }
        return api;
    }
    
    /**
     * 启动流处理 - 使用MarketTickerStreamServiceImpl方式
     */
    public void startStreamProcessing() throws ApiException, InterruptedException {
        log.info("[MarketTickerStreamTestImpl] [优化模式] 开始启动流处理...");
        
        try {
            running.set(true);
            
            // ===== 创建请求对象 - MarketTickerStreamServiceImpl方式 =====
            log.info("[MarketTickerStreamTestImpl] [优化模式] 创建 AllMarketTickersStreamsRequest 请求对象...");
            AllMarketTickersStreamsRequest allMarketTickersStreamsRequest =
                    new AllMarketTickersStreamsRequest();
            log.info("[MarketTickerStreamTestImpl] [优化模式] 请求对象创建成功");
            
            // ===== 获取流响应 - MarketTickerStreamServiceImpl方式 =====
            log.info("[MarketTickerStreamTestImpl] [优化模式] 调用 getApi().allMarketTickersStreams() 获取流...");
            response = getApi().allMarketTickersStreams(allMarketTickersStreamsRequest);
            log.info("[MarketTickerStreamTestImpl] [优化模式] 流响应获取成功: {}", response != null ? "响应存在" : "响应为空");
            
            // ===== 启动处理线程 - MarketTickerStreamServiceImpl方式 =====
            log.info("[MarketTickerStreamTestImpl] [优化模式] 启动流数据处理线程...");
            streamExecutor = Executors.newSingleThreadExecutor(r -> {
                Thread t = new Thread(r, "MarketTickerTestStream");
                t.setDaemon(true);
                return t;
            });
            
            streamExecutor.submit(() -> {
                try {
                    // ===== 使用MarketTickerStreamServiceImpl方式的while循环处理数据 =====
                    log.info("[MarketTickerStreamTestImpl] [优化模式] 开始进入数据处理循环...");
                    log.info("[MarketTickerStreamTestImpl] [优化模式] 等待接收WebSocket消息...");
                    int messageCount = 0;
                    long startTime = System.currentTimeMillis();
                    
                    while (running.get()) {
                        try {
                            // 使用 take() 阻塞等待数据
                            AllMarketTickersStreamsResponse tickerResponse = response.take();
                            
                            messageCount++;
                            long currentTime = System.currentTimeMillis();
                            long elapsedSeconds = (currentTime - startTime) / 1000;
                            
                            // 每条消息都打印基本信息
                            if (tickerResponse != null) {
                                // 打印消息统计信息
                                log.info("[MarketTickerStreamTestImpl] ========== 收到第 {} 条消息 (运行 {} 秒) ==========", 
                                        messageCount, elapsedSeconds);
                                
                                // AllMarketTickersStreamsResponse 继承自 ArrayList<AllMarketTickersStreamsResponseInner>
                                // 可以直接使用 List 的方法访问数据
                                int tickerCount = tickerResponse.size();
                                log.info("[MarketTickerStreamTestImpl] 📈 包含 {} 个交易对的ticker数据", tickerCount);
                                
                                if (tickerCount > 0) {
                                    // 打印前10个ticker的详细信息
                                    int printCount = Math.min(10, tickerCount);
                                    log.info("[MarketTickerStreamTestImpl] ┌─────────────────────────────────────────────────────────────────────────────────────────────┐");
                                    log.info("[MarketTickerStreamTestImpl] │ 序号 │ 交易对    │ 最新价      │ 涨跌额      │ 涨跌幅      │ 成交量        │ 成交额        │");
                                    log.info("[MarketTickerStreamTestImpl] ├─────┼───────────┼─────────────┼─────────────┼─────────────┼───────────────┼───────────────┤");
                                    
                                    for (int i = 0; i < printCount; i++) {
                                        AllMarketTickersStreamsResponseInner ticker = tickerResponse.get(i);
                                        
                                        // 提取关键字段
                                        String symbol = ticker.getsLowerCase() != null ? ticker.getsLowerCase() : "N/A";
                                        String lastPrice = ticker.getcLowerCase() != null ? ticker.getcLowerCase() : "N/A";
                                        String priceChange = ticker.getpLowerCase() != null ? ticker.getpLowerCase() : "N/A";
                                        String priceChangePercent = ticker.getP() != null ? ticker.getP() + "%" : "N/A";
                                        String volume = ticker.getvLowerCase() != null ? ticker.getvLowerCase() : "N/A";
                                        String quoteVolume = ticker.getqLowerCase() != null ? ticker.getqLowerCase() : "N/A";
                                        
                                        // 格式化字符串，确保对齐
                                        String symbolStr = symbol.length() > 9 ? symbol.substring(0, 9) : String.format("%-9s", symbol);
                                        String lastPriceStr = lastPrice.length() > 11 ? lastPrice.substring(0, 11) : String.format("%-11s", lastPrice);
                                        String priceChangeStr = priceChange.length() > 11 ? priceChange.substring(0, 11) : String.format("%-11s", priceChange);
                                        String priceChangePercentStr = priceChangePercent.length() > 11 ? priceChangePercent.substring(0, 11) : String.format("%-11s", priceChangePercent);
                                        String volumeStr = volume.length() > 13 ? volume.substring(0, 13) : String.format("%-13s", volume);
                                        String quoteVolumeStr = quoteVolume.length() > 13 ? quoteVolume.substring(0, 13) : String.format("%-13s", quoteVolume);
                                        
                                        log.info(String.format("[MarketTickerStreamTestImpl] │ %3d │ %-9s │ %-11s │ %-11s │ %-11s │ %-13s │ %-13s │", 
                                                i + 1, symbolStr, lastPriceStr, priceChangeStr, 
                                                priceChangePercentStr, volumeStr, quoteVolumeStr));
                                    }
                                    log.info("[MarketTickerStreamTestImpl] └─────────────────────────────────────────────────────────────────────────────────────────────┘");
                                    
                                    if (tickerCount > printCount) {
                                        log.info("[MarketTickerStreamTestImpl]   ... 还有 {} 个ticker未显示", tickerCount - printCount);
                                    }
                                    
                                    // 打印第一个ticker的完整信息作为示例
                                    if (messageCount <= 5 && tickerCount > 0) {
                                        AllMarketTickersStreamsResponseInner firstTicker = tickerResponse.get(0);
                                        log.info("[MarketTickerStreamTestImpl] 📊 第一个Ticker完整信息:");
                                        log.info("[MarketTickerStreamTestImpl]   - Symbol (s): {}", firstTicker.getsLowerCase());
                                        log.info("[MarketTickerStreamTestImpl]   - Event Time (E): {}", firstTicker.getE());
                                        log.info("[MarketTickerStreamTestImpl]   - Price Change (p): {}", firstTicker.getpLowerCase());
                                        log.info("[MarketTickerStreamTestImpl]   - Price Change % (P): {}", firstTicker.getP());
                                        log.info("[MarketTickerStreamTestImpl]   - Weighted Avg Price (w): {}", firstTicker.getwLowerCase());
                                        log.info("[MarketTickerStreamTestImpl]   - Last Price (c): {}", firstTicker.getcLowerCase());
                                        log.info("[MarketTickerStreamTestImpl]   - Last Qty (Q): {}", firstTicker.getQ());
                                        log.info("[MarketTickerStreamTestImpl]   - Open Price (o): {}", firstTicker.getoLowerCase());
                                        log.info("[MarketTickerStreamTestImpl]   - High Price (h): {}", firstTicker.gethLowerCase());
                                        log.info("[MarketTickerStreamTestImpl]   - Low Price (l): {}", firstTicker.getlLowerCase());
                                        log.info("[MarketTickerStreamTestImpl]   - Volume (v): {}", firstTicker.getvLowerCase());
                                        log.info("[MarketTickerStreamTestImpl]   - Quote Volume (q): {}", firstTicker.getqLowerCase());
                                        log.info("[MarketTickerStreamTestImpl]   - Open Time (O): {}", firstTicker.getO());
                                        log.info("[MarketTickerStreamTestImpl]   - Close Time (C): {}", firstTicker.getC());
                                        log.info("[MarketTickerStreamTestImpl]   - First Trade ID (F): {}", firstTicker.getF());
                                        log.info("[MarketTickerStreamTestImpl]   - Last Trade ID (L): {}", firstTicker.getL());
                                        log.info("[MarketTickerStreamTestImpl]   - Trade Count (n): {}", firstTicker.getnLowerCase());
                                    }
                                } else {
                                    log.warn("[MarketTickerStreamTestImpl] ⚠️ 响应中不包含任何ticker数据");
                                }
                                
                                // 前10条消息详细打印，之后每10条打印一次摘要
                                if (messageCount <= 10) {
                                    log.info("[MarketTickerStreamTestImpl] ✅ [详细模式] 第 {} 条消息处理完成", messageCount);
                                } else if (messageCount % 10 == 0) {
                                    log.info("[MarketTickerStreamTestImpl] ✅ [摘要模式] 已处理 {} 条消息 (运行 {} 秒, 平均 {} 个ticker/条)", 
                                            messageCount, elapsedSeconds, tickerCount);
                                }
                            } else {
                                log.warn("[MarketTickerStreamTestImpl] ⚠️ 收到空响应 (第 {} 条)", messageCount);
                            }
                            
                        } catch (InterruptedException e) {
                            log.info("[MarketTickerStreamTestImpl] 🛑 [优化模式] 流处理被中断");
                            Thread.currentThread().interrupt();
                            break;
                        } catch (NullPointerException e) {
                            log.warn("[MarketTickerStreamTestImpl] ⚠️ [优化模式] 检测到空指针异常，可能收到空消息，跳过处理", e);
                            // 记录异常信息但不中断流
                            log.debug("[MarketTickerStreamTestImpl] 异常详情: 消息={}, 堆栈={}", 
                                    e.getMessage() != null ? e.getMessage() : "null", e.getStackTrace());
                        } catch (Exception e) {
                            log.error("[MarketTickerStreamTestImpl] ❌ [优化模式] 数据处理异常", e);
                            log.error("[MarketTickerStreamTestImpl] ❌ 异常类型: {}, 异常消息: {}", 
                                    e.getClass().getName(), e.getMessage());
                            log.error("[MarketTickerStreamTestImpl] ❌ 异常堆栈:", e);
                            
                            // 针对特定异常类型的处理
                            if (e instanceof com.binance.connector.client.common.ApiException) {
                                com.binance.connector.client.common.ApiException apiEx = (com.binance.connector.client.common.ApiException) e;
                                if (apiEx.getMessage() != null && apiEx.getMessage().contains("NullPointerException")) {
                                    log.warn("[MarketTickerStreamTestImpl] ⚠️ [优化模式] 检测到WebSocket SDK内部空指针异常，继续处理", apiEx);
                                } else {
                                    log.error("[MarketTickerStreamTestImpl] ❌ [优化模式] API异常，停止流", apiEx);
                                    break; // 严重的API异常需要停止流
                                }
                            }
                            // 继续处理，不中断流
                        }
                    }
                    
                    log.info("[MarketTickerStreamTestImpl] 🏁 [优化模式] 数据处理循环结束，总计处理 {} 条数据", messageCount);
                    
                } catch (Exception e) {
                    log.error("[MarketTickerStreamTestImpl] ❌ [优化模式] 流处理线程异常", e);
                }
            });
            
            log.info("[MarketTickerStreamTestImpl] ✅ [优化模式] 流处理启动成功");
            
        } catch (Exception e) {
            log.error("[MarketTickerStreamTestImpl] ❌ [SDK示例模式] 启动流处理失败", e);
            throw e;
        }
    }
    
    /**
     * 停止流处理
     */
    @Override
    public void stopStream() {
        log.info("[MarketTickerStreamTestImpl] 🛑 正在停止测试流...");
        
        running.set(false);
        
        if (streamExecutor != null && !streamExecutor.isShutdown()) {
            streamExecutor.shutdown();
            log.info("[MarketTickerStreamTestImpl] ℹ️  流处理线程已关闭");
        }
        
        log.info("[MarketTickerStreamTestImpl] ✅ 测试流已停止");
    }
    
    /**
     * 启动ticker流服务
     */
    @Override
    public void startStream(Integer runSeconds) throws Exception {
        log.info("[MarketTickerStreamTestImpl] 🚀 启动ticker流服务（运行时长: {}秒）", 
                runSeconds != null ? runSeconds : "无限");
        
        try {
            // 如果指定了运行时间，则在指定时间后停止
            if (runSeconds != null) {
                Executors.newSingleThreadExecutor().submit(() -> {
                    try {
                        Thread.sleep(runSeconds * 1000L);
                        stopStream();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                });
            }
            
            log.info("[MarketTickerStreamTestImpl] ✅ ticker流服务启动成功");
            
        } catch (Exception e) {
            log.error("[MarketTickerStreamTestImpl] ❌ ticker流服务启动失败", e);
            throw e;
        }
    }
    
    /**
     * 检查服务状态
     */
    @Override
    public boolean isRunning() {
        return running.get();
    }
    
    /**
     * 格式化字节大小显示
     */
    private String formatBytes(int bytes) {
        if (bytes < 1024) {
            return bytes + "B";
        } else if (bytes < 1024 * 1024) {
            return String.format("%.1fKB", bytes / 1024.0);
        } else {
            return String.format("%.1fMB", bytes / (1024.0 * 1024.0));
        }
    }
}