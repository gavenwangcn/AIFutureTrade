/*
 * MarketTickerStreamTestServiceImpl
 * 
 * 完全按照Binance SDK官方示例 AllMarketTickersStreamsExample.java 实现的测试服务
 * 用于排查MarketTickerStreamServiceImpl启动失败的问题
 */

package com.aifuturetrade.asyncservice.service.impl;

import com.aifuturetrade.asyncservice.service.MarketTickerStreamTestService;
import com.binance.connector.client.common.ApiException;
import com.binance.connector.client.common.websocket.configuration.WebSocketClientConfiguration;
import com.binance.connector.client.common.websocket.service.StreamBlockingQueueWrapper;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.DerivativesTradingUsdsFuturesWebSocketStreamsUtil;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.api.DerivativesTradingUsdsFuturesWebSocketStreams;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.model.AllMarketTickersStreamsRequest;
import com.binance.connector.client.derivatives_trading_usds_futures.websocket.stream.model.AllMarketTickersStreamsResponse;
import lombok.extern.slf4j.Slf4j;
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
    private DerivativesTradingUsdsFuturesWebSocketStreams api;
    private StreamBlockingQueueWrapper<AllMarketTickersStreamsResponse> response;
    private ExecutorService streamExecutor;
    private final AtomicBoolean running = new AtomicBoolean(false);
    
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
     * 获取API实例 - 完全按照SDK官方示例 AllMarketTickersStreamsExample.getApi()
     */
    @Override
    public DerivativesTradingUsdsFuturesWebSocketStreams getApi() {
        if (api == null) {
            log.info("[MarketTickerStreamTestImpl] [SDK示例模式] 准备创建WebSocketStreams实例...");
            
            try {
                // ===== 完全按照SDK示例的getApi()方法实现 =====
                // SDK示例代码：
                // WebSocketClientConfiguration clientConfiguration =
                //         DerivativesTradingUsdsFuturesWebSocketStreamsUtil.getClientConfiguration();
                // api = new DerivativesTradingUsdsFuturesWebSocketStreams(clientConfiguration);
                
                log.info("[MarketTickerStreamTestImpl] [SDK示例模式] 调用 DerivativesTradingUsdsFuturesWebSocketStreamsUtil.getClientConfiguration()...");
                WebSocketClientConfiguration clientConfiguration =
                        DerivativesTradingUsdsFuturesWebSocketStreamsUtil.getClientConfiguration();
                log.info("[MarketTickerStreamTestImpl] [SDK示例模式] 客户端配置创建成功");
                log.info("[MarketTickerStreamTestImpl] [SDK示例模式] 配置URL: {}", clientConfiguration.getUrl());
                
                log.info("[MarketTickerStreamTestImpl] [SDK示例模式] 创建 DerivativesTradingUsdsFuturesWebSocketStreams 实例...");
                api = new DerivativesTradingUsdsFuturesWebSocketStreams(clientConfiguration);
                log.info("[MarketTickerStreamTestImpl] [SDK示例模式] WebSocketStreams实例创建成功: {}", api != null ? "实例存在" : "实例为空");
                
            } catch (Exception e) {
                log.error("[MarketTickerStreamTestImpl] ❌ SDK示例模式创建API实例失败", e);
                log.error("[MarketTickerStreamTestImpl] ❌ 创建失败异常类型: {}", e.getClass().getName());
                log.error("[MarketTickerStreamTestImpl] ❌ 创建失败异常消息: {}", e.getMessage());
                throw new RuntimeException("无法创建WebSocket API实例", e);
            }
        }
        return api;
    }
    
    /**
     * 启动流处理 - 完全按照SDK官方示例 allMarketTickersStreamsExample() 方法
     */
    public void startStreamProcessing() throws ApiException, InterruptedException {
        log.info("[MarketTickerStreamTestImpl] [SDK示例模式] 开始启动流处理...");
        
        try {
            running.set(true);
            
            // ===== 创建请求对象 - SDK示例方式 =====
            log.info("[MarketTickerStreamTestImpl] [SDK示例模式] 创建 AllMarketTickersStreamsRequest 请求对象...");
            AllMarketTickersStreamsRequest allMarketTickersStreamsRequest =
                    new AllMarketTickersStreamsRequest();
            log.info("[MarketTickerStreamTestImpl] [SDK示例模式] 请求对象创建成功");
            
            // ===== 获取流响应 - SDK示例方式 =====
            log.info("[MarketTickerStreamTestImpl] [SDK示例模式] 调用 getApi().allMarketTickersStreams() 获取流...");
            response = getApi().allMarketTickersStreams(allMarketTickersStreamsRequest);
            log.info("[MarketTickerStreamTestImpl] [SDK示例模式] 流响应获取成功: {}", response != null ? "响应存在" : "响应为空");
            
            // ===== 启动处理线程 - SDK示例方式 =====
            log.info("[MarketTickerStreamTestImpl] [SDK示例模式] 启动流数据处理线程...");
            streamExecutor = Executors.newSingleThreadExecutor(r -> {
                Thread t = new Thread(r, "MarketTickerTestStream");
                t.setDaemon(true);
                return t;
            });
            
            streamExecutor.submit(() -> {
                try {
                    // ===== 完全按照SDK示例的while循环处理数据 =====
                    // SDK示例代码：
                    // while (true) {
                    //     System.out.println(response.take());
                    // }
                    
                    log.info("[MarketTickerStreamTestImpl] [SDK示例模式] 开始进入数据处理循环...");
                    int messageCount = 0;
                    
                    while (running.get()) {
                        try {
                            log.debug("[MarketTickerStreamTestImpl] [SDK示例模式] 调用 response.take() 等待数据...");
                            AllMarketTickersStreamsResponse tickerResponse = response.take();
                            
                            messageCount++;
                            log.info("[MarketTickerStreamTestImpl] 📊 [SDK示例模式] 收到第 {} 条数据: {}", 
                                    messageCount, tickerResponse != null ? "有数据" : "空数据");
                            
                            // 按照SDK示例打印数据
                            if (messageCount <= 5) {
                                // 前5条数据详细打印
                                log.info("[MarketTickerStreamTestImpl] 📈 [SDK示例模式] 数据详情 (第{}条): {}", 
                                        messageCount, tickerResponse);
                            } else if (messageCount % 100 == 0) {
                                // 每100条数据打印一次统计
                                log.info("[MarketTickerStreamTestImpl] 📊 [SDK示例模式] 已处理 {} 条数据", messageCount);
                            }
                            
                        } catch (InterruptedException e) {
                            log.info("[MarketTickerStreamTestImpl] 🛑 [SDK示例模式] 流处理被中断");
                            Thread.currentThread().interrupt();
                            break;
                        } catch (Exception e) {
                            log.error("[MarketTickerStreamTestImpl] ❌ [SDK示例模式] 数据处理异常", e);
                            log.error("[MarketTickerStreamTestImpl] ❌ 异常类型: {}, 异常消息: {}", 
                                    e.getClass().getName(), e.getMessage());
                            // 继续处理，不中断流
                        }
                    }
                    
                    log.info("[MarketTickerStreamTestImpl] 🏁 [SDK示例模式] 数据处理循环结束，总计处理 {} 条数据", messageCount);
                    
                } catch (Exception e) {
                    log.error("[MarketTickerStreamTestImpl] ❌ [SDK示例模式] 流处理线程异常", e);
                }
            });
            
            log.info("[MarketTickerStreamTestImpl] ✅ [SDK示例模式] 流处理启动成功");
            
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
}