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
    private static final String BASE_URL = "wss://fstream.binance.com";
    private static final boolean HAS_TIME_UNIT = false;
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
            WebSocketClientConfiguration clientConfiguration =
                    DerivativesTradingUsdsFuturesWebSocketStreamsUtil.getClientConfiguration();
                    clientConfiguration.setMessageMaxSize(75000L);
            api = new DerivativesTradingUsdsFuturesWebSocketStreams(clientConfiguration);
        }
        return api;
    }
    
    /**
     * 启动流处理 - 使用MarketTickerStreamServiceImpl方式
     */
    public void startStreamProcessing() throws ApiException, InterruptedException {
        log.info("[MarketTickerStreamTestImpl] [优化模式] 开始启动流处理...");
        
        try {
        AllMarketTickersStreamsRequest allMarketTickersStreamsRequest =
                new AllMarketTickersStreamsRequest();
        StreamBlockingQueueWrapper<AllMarketTickersStreamsResponse> response =
                getApi().allMarketTickersStreams(allMarketTickersStreamsRequest);
        while (true) {
            log.info("[MarketTickerStreamTestImpl] ✅ ticker流服务启动成功:"+response.take());
            //System.out.println(response.take());
        }
            
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
    private String formatBytes(long bytes) {
        if (bytes < 1024) {
            return bytes + "B";
        } else if (bytes < 1024 * 1024) {
            return String.format("%.1fKB", bytes / 1024.0);
        } else {
            return String.format("%.1fMB", bytes / (1024.0 * 1024.0));
        }
    }
}