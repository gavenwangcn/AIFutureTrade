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
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;
import org.eclipse.jetty.websocket.api.exceptions.MessageTooLargeException;
import org.eclipse.jetty.websocket.client.WebSocketClient;

/**
 * 市场Ticker流服务实现
 * 
 * 参考Python版本的market_streams.py实现，使用Binance SDK接收全市场ticker数据流，
 * 解析数据并同步到MySQL数据库。
 * 
 * 主要特性：
 * - 使用SDK泛型类解析数据（不使用反射）
 * - 简化的异常处理：仅对MessageTooLargeException进行特殊处理
 * - 批量同步：使用batchUpsertTickers批量插入/更新数据
 * - 异常处理：完善的错误处理和日志记录
 */
@Slf4j
@Service("marketTickerStreamService")
public class MarketTickerStreamServiceImpl implements MarketTickerStreamService {
    
    private final MarketTickerMapper marketTickerMapper;
    private DerivativesTradingUsdsFuturesWebSocketStreams api;
    private StreamBlockingQueueWrapper<AllMarketTickersStreamsResponse> response;
    private ExecutorService streamExecutor;
    private final AtomicBoolean running = new AtomicBoolean(false);
    private final AtomicBoolean reconnectRequested = new AtomicBoolean(false);
    private final AtomicLong lastReconnectAtMs = new AtomicLong(0);
    private final AtomicReference<Thread> streamThread = new AtomicReference<>();
    private final AtomicBoolean isActiveReconnecting = new AtomicBoolean(false);

    // 由本服务创建并持有，用于在重连前显式关闭旧连接，避免连接/线程泄漏
    private volatile WebSocketClient currentWebSocketClient;
    
    // 动态调整的最大消息大小（初始值为配置值，遇到MessageTooLargeException时自动增加）
    private final AtomicLong currentMaxMessageSize;
    
    @Autowired
    public MarketTickerStreamServiceImpl(WebSocketConfig webSocketConfig, MarketTickerMapper marketTickerMapper) {
        this.marketTickerMapper = marketTickerMapper;
        // 初始化当前最大消息大小为配置值
        this.currentMaxMessageSize = new AtomicLong(webSocketConfig.getMaxTextMessageSize());
        log.info("[MarketTickerStreamService] 初始化最大消息大小: {} bytes", currentMaxMessageSize.get());
    }
    
    /**
     * 初始化方法
     */
    @PostConstruct
    public void init() {
        log.info("[MarketTickerStreamService] 开始初始化市场Ticker流服务");
        
        try {
            // 获取API实例
            log.info("[MarketTickerStreamService] 获取WebSocket API实例...");
            getApi();
            log.info("[MarketTickerStreamService] API实例获取成功");
            
            log.info("[MarketTickerStreamService] 市场Ticker流服务初始化完成");
            
        } catch (Exception e) {
            log.error("[MarketTickerStreamService] 服务初始化失败", e);
            throw new RuntimeException("MarketTickerStreamService服务初始化失败", e);
        }
    }
    
    /**
     * 销毁方法
     */
    @PreDestroy
    public void destroy() {
        log.info("[MarketTickerStreamService] 正在关闭市场Ticker流服务...");
        stopStream();
        log.info("[MarketTickerStreamService] 市场Ticker流服务已关闭");
    }
    
    /**
     * 获取API实例
     * 使用动态调整的最大消息大小
     */
    @Override
    public synchronized DerivativesTradingUsdsFuturesWebSocketStreams getApi() {
        if (api == null) {
            WebSocketClientConfiguration clientConfiguration =
                    DerivativesTradingUsdsFuturesWebSocketStreamsUtil.getClientConfiguration();
            // 使用动态调整的最大消息大小
            long maxSize = currentMaxMessageSize.get();
            clientConfiguration.setMessageMaxSize(maxSize);
            clientConfiguration.setReconnectBatchSize(365);
            WebSocketClient webSocketClient = new WebSocketClient();
            MarketTickerStreamConnectionWrapper connectionWrapper =
                    new MarketTickerStreamConnectionWrapper(
                            clientConfiguration, webSocketClient, this::onWrapperWebSocketError);
            api = new DerivativesTradingUsdsFuturesWebSocketStreams(connectionWrapper);
            currentWebSocketClient = webSocketClient;
            log.info("[MarketTickerStreamService] 创建API实例，最大消息大小: {} bytes", maxSize);
        }
        return api;
    }

    /**
     * SDK ConnectionWrapper.onWebSocketError 回调：触发业务侧重连。
     * 说明：此回调可能发生在 Jetty/WebSocket 线程；这里不做重连耗时操作，只做”去抖 + 唤醒流线程”。
     */
    private void onWrapperWebSocketError(Throwable cause) {
        if (!running.get()) {
            log.debug(“[MarketTickerStreamService] 服务已停止, 忽略WebSocket错误回调”);
            return;
        }

        // 如果正在主动重连, 忽略由stop()触发的close事件, 避免重连死循环
        if (isActiveReconnecting.get()) {
            log.debug(“[MarketTickerStreamService] 正在主动重连中, 忽略WebSocket关闭事件”);
            return;
        }

        // 检查是否是正常关闭(应用关闭时触发)
        if (cause != null) {
            String msg = cause.getMessage();
            if (msg != null && (msg.contains(“Container being shut down”) ||
                               msg.contains(“Session Closed”) ||
                               msg.contains(“is not started”))) {
                log.debug(“[MarketTickerStreamService] 检测到正常关闭事件, 不触发重连: {}”, msg);
                return;
            }
        }

        long now = System.currentTimeMillis();
        long last = lastReconnectAtMs.get();
        // 1 秒内多次错误只触发一次, 避免风暴
        if (now - last < 1000) {
            return;
        }
        lastReconnectAtMs.set(now);

        log.warn(“[MarketTickerStreamService] WebSocketError(断链/异常)触发重连: {}”,
                cause != null ? cause.getMessage() : “null”, cause);

        reconnectRequested.set(true);

        // 唤醒正在 response.take() 阻塞的流线程, 让其切换到新连接
        Thread t = streamThread.get();
        if (t != null) {
            t.interrupt();
        }
    }
    
    /**
     * 重新创建API实例（用于处理MessageTooLargeException后调整消息大小）
     */
    private void recreateApi() {
        log.info("[MarketTickerStreamService] 重新创建API实例...");
        closeCurrentConnectionNoThrow();
        api = null; // 强制重新创建
        getApi(); // 触发重新创建
    }

    /**
     * 重连/停止前显式关闭当前连接，避免旧 WebSocketClient/Session 残留。
     * 说明：binance-connector 的 Streams API 本身未暴露 close 方法，这里通过停止我们创建的 Jetty WebSocketClient 来释放资源。
     */
    private void closeCurrentConnectionNoThrow() {
        // 先断开引用，避免并发重复 stop
        WebSocketClient ws = currentWebSocketClient;
        currentWebSocketClient = null;

        if (ws == null) {
            return;
        }
        try {
            // 设置主动重连标志，避免stop()触发的close事件被当作异常断链
            isActiveReconnecting.set(true);
            ws.stop();
            log.info("[MarketTickerStreamService] 已停止旧 WebSocketClient，释放旧连接资源");
        } catch (Exception e) {
            log.warn("[MarketTickerStreamService] 停止旧 WebSocketClient 失败（忽略）", e);
        } finally {
            // 延迟重置标志，确保所有close事件都被忽略
            try {
                TimeUnit.MILLISECONDS.sleep(500);
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
            }
            isActiveReconnecting.set(false);
        }
    }
    
    /**
     * 检测并处理MessageTooLargeException
     * 如果检测到此异常，自动增加最大消息大小并重新创建API实例
     * 
     * @param e 异常对象（可以是Exception或Throwable）
     * @return true如果检测到MessageTooLargeException并已处理，false otherwise
     */
    private boolean handleMessageTooLargeException(Throwable e) {
        // 只判断是否为MessageTooLargeException异常
        if (!(e instanceof MessageTooLargeException)) {
            return false;
        }
        
        MessageTooLargeException mte = (MessageTooLargeException) e;
        String errorMessage = mte.getMessage() != null ? mte.getMessage() : "";
        
        // 从异常消息中提取实际消息大小（如果可能）
        long actualSize = 0;
        long configuredSize = currentMaxMessageSize.get();
        
        // 尝试从异常消息中提取实际大小
        try {
            if (errorMessage.contains("(actual)")) {
                String[] parts = errorMessage.split("\\(actual\\)");
                if (parts.length > 1) {
                    String sizePart = parts[1].trim();
                    String sizeStr = sizePart.replaceAll("[^0-9]", "");
                    if (!sizeStr.isEmpty()) {
                        actualSize = Long.parseLong(sizeStr);
                    }
                }
            }
            if (actualSize == 0 && errorMessage.contains(">")) {
                String[] parts = errorMessage.split(">");
                if (parts.length > 0) {
                    String actualPart = parts[0];
                    String[] actualParts = actualPart.split("\\(");
                    if (actualParts.length > 1) {
                        String sizeStr = actualParts[1].replaceAll("[^0-9]", "");
                        if (!sizeStr.isEmpty()) {
                            actualSize = Long.parseLong(sizeStr);
                        }
                    }
                }
            }
        } catch (Exception parseEx) {
            log.info("[MarketTickerStreamService] 无法从异常消息中解析实际消息大小: {}", errorMessage, parseEx);
        }
        
        // 计算新的最大消息大小：实际大小 + 20% 缓冲
        long newMaxSize;
        if (actualSize > 0) {
            newMaxSize = (long) (actualSize * 1.2); // 增加20%缓冲
        } else {
            newMaxSize = configuredSize + 20000; // 增加20KB
        }
        
        // 限制最大值为500KB，避免无限增长
        long maxAllowedSize = 500 * 1024; // 500KB
        if (newMaxSize > maxAllowedSize) {
            newMaxSize = maxAllowedSize;
            log.warn("[MarketTickerStreamService] 新计算的最大消息大小 {} bytes 超过限制 {} bytes，使用限制值", 
                    newMaxSize, maxAllowedSize);
        }
        
        log.warn("[MarketTickerStreamService] 检测到MessageTooLargeException: {}", errorMessage);
        log.warn("[MarketTickerStreamService] 当前最大消息大小: {} bytes, 实际消息大小: {} bytes", 
                configuredSize, actualSize > 0 ? actualSize : "未知");
        log.info("[MarketTickerStreamService] 将最大消息大小从 {} bytes 增加到 {} bytes", 
                configuredSize, newMaxSize);
        
        // 更新最大消息大小
        currentMaxMessageSize.set(newMaxSize);
        
        // 重新创建API实例
        recreateApi();
        
        return true;
    }
    
    /**
     * 检查异常是否是 org.eclipse.jetty.websocket.api.exceptions 包下的异常
     * 
     * @param e 异常对象
     * @return true如果是WebSocket异常，false otherwise
     */
    private boolean isWebSocketException(Throwable e) {
        if (e == null) {
            return false;
        }
        
        // 检查异常类型
        Class<?> exceptionClass = e.getClass();
        String className = exceptionClass.getName();
        
        // 检查是否是 org.eclipse.jetty.websocket.api.exceptions 包下的异常
        if (className.startsWith("org.eclipse.jetty.websocket.api.exceptions.")) {
            return true;
        }
        
        // 检查异常消息中是否包含WebSocket相关关键词
        String errorMessage = e.getMessage() != null ? e.getMessage().toLowerCase() : "";
        if (errorMessage.contains("websocket") || 
            errorMessage.contains("message too large") ||
            errorMessage.contains("messagetoolargeexception")) {
            return true;
        }
        
        return false;
    }
    
    /**
     * 处理WebSocket异常并重新建立连接
     * 
     * @param e 异常对象
     * @return true如果处理了WebSocket异常并重新建立了连接，false otherwise
     */
    private boolean handleWebSocketException(Exception e) {
        // 检查是否是MessageTooLargeException，需要特殊处理（调整消息大小）
        if (e instanceof MessageTooLargeException) {
            log.error("[MarketTickerStreamService] 捕获到MessageTooLargeException异常，将调整消息大小并重新建立连接", e);
            return handleMessageTooLargeException(e);
        }
        
        // 检查异常链中是否包含MessageTooLargeException
        Throwable cause = e.getCause();
        while (cause != null) {
            if (cause instanceof MessageTooLargeException) {
                log.error("[MarketTickerStreamService] 在异常链中检测到MessageTooLargeException，将调整消息大小并重新建立连接", cause);
                // 直接处理MessageTooLargeException，不需要再封装
                return handleMessageTooLargeException(cause);
            }
            cause = cause.getCause();
        }
        
        // 其他WebSocket异常，直接重新建立连接
        log.error("[MarketTickerStreamService] 捕获到WebSocket异常，将重新建立连接", e);
        return reconnectStream();
    }
    
    /**
     * 重新建立WebSocket连接
     *
     * @return true如果成功重新建立连接，false otherwise
     */
    private boolean reconnectStream() {
        try {
            // 断链后不要立即重连：休息2分钟再重建，避免频繁重连风暴
            if (running.get()) {
                log.warn("[MarketTickerStreamService] 2分钟后重建WebSocket连接（可被停止/中断提前结束等待）");
                try {
                    // 分段睡眠，便于 stopStream() interrupt 及时生效（2分钟 = 120秒）
                    for (int i = 0; i < 120 && running.get(); i++) {
                        TimeUnit.SECONDS.sleep(1);
                    }
                } catch (InterruptedException ie) {
                    // stopStream() 或其他重连信号会中断等待；若仍在运行则继续执行重连
                    if (!running.get()) {
                        Thread.currentThread().interrupt();
                        return false;
                    }
                }
            }

            log.info("[MarketTickerStreamService] 开始重新建立WebSocket连接...");
            
            // 重新创建API实例（使用当前的最大消息大小）
            recreateApi();
            
            // 重新创建请求并获取流
            AllMarketTickersStreamsRequest request = new AllMarketTickersStreamsRequest();
            response = getApi().allMarketTickersStreams(request);
            
            log.info("[MarketTickerStreamService] WebSocket连接已重新建立");
            return true;
        } catch (Exception e) {
            log.error("[MarketTickerStreamService] 重新建立WebSocket连接失败", e);
            return false;
        }
    }
    
    /**
     * 异常处理
     * 处理所有 org.eclipse.jetty.websocket.api.exceptions 包下的异常，并重新建立连接
     * 
     * @param e 异常对象
     * @return true如果处理了WebSocket异常并重新建立了连接，false otherwise
     */
    private boolean handleException(Exception e) {
        // 检查是否是WebSocket异常
        if (isWebSocketException(e)) {
            log.warn("[MarketTickerStreamService] 检测到WebSocket异常: {} - {}", 
                    e.getClass().getSimpleName(), 
                    e.getMessage() != null ? e.getMessage() : "");
            return handleWebSocketException(e);
        }
        
        // 检查异常链中是否包含WebSocket异常
        Throwable cause = e.getCause();
        while (cause != null) {
            if (isWebSocketException(cause)) {
                log.warn("[MarketTickerStreamService] 在异常链中检测到WebSocket异常: {} - {}", 
                        cause.getClass().getSimpleName(), 
                        cause.getMessage() != null ? cause.getMessage() : "");
                return handleWebSocketException(new Exception(cause));
            }
            cause = cause.getCause();
        }
        
        // 其他异常只记录日志，不进行重连
        String errorMessage = e.getMessage() != null ? e.getMessage() : "";
        String exceptionType = e.getClass().getSimpleName();
        log.warn("[MarketTickerStreamService] 处理异常: {} - {}", exceptionType, errorMessage);
        
        return false;
    }
    
    /**
     * 启动ticker流服务
     */
    @Override
    public void startStream(Integer runSeconds) throws Exception {
        log.info("[MarketTickerStreamService] 启动ticker流服务（运行时长: {}秒）", 
                runSeconds != null ? runSeconds : "无限");
        
        if (running.get()) {
            log.warn("[MarketTickerStreamService] 服务已在运行中，跳过启动");
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
                streamOnce(runSeconds);
            } catch (Exception e) {
                log.error("[MarketTickerStreamService] 流处理异常", e);
            } finally {
                running.set(false);
            }
        });
        
        log.info("[MarketTickerStreamService] ticker流服务启动成功");
    }
    
    /**
     * 运行流处理
     */
    private void streamOnce(Integer runSeconds) throws Exception {
        log.info("[MarketTickerStreamService] 开始流处理（运行{}秒）", 
                runSeconds != null ? runSeconds : "无限");
        
        try {
            streamThread.set(Thread.currentThread());
            log.debug("[MarketTickerStreamService] Creating WebSocket connection");
            
            // 创建请求并获取流
            AllMarketTickersStreamsRequest request = new AllMarketTickersStreamsRequest();
            response = getApi().allMarketTickersStreams(request);
            log.info("[MarketTickerStreamService] WebSocket连接已建立");
            
            // 计算结束时间（如果指定了运行时间）
            Long endTime = null;
            if (runSeconds != null) {
                endTime = System.currentTimeMillis() + (runSeconds * 1000L);
            }
            
            // 循环接收数据
            while (running.get()) {
                // 检查是否超时
                if (endTime != null && System.currentTimeMillis() >= endTime) {
                    log.info("[MarketTickerStreamService] 运行时间到达限制，停止流处理");
                    break;
                }
                
                try {
                    // 若 SDK 回调触发了重连请求，则优先重连再取数据，避免继续阻塞旧连接
                    if (reconnectRequested.getAndSet(false)) {
                        log.info("[MarketTickerStreamService] 收到断链重连请求，开始重建连接...");
                        reconnectStream();
                        continue;
                    }

                    AllMarketTickersStreamsResponse tickerResponse = response.take();
                    handleMessage(tickerResponse);
                } catch (InterruptedException e) {
                    if (!running.get()) {
                        log.warn("[MarketTickerStreamService] 流处理被中断（服务停止）");
                        Thread.currentThread().interrupt();
                        break;
                    }
                    // 通常是 onWebSocketError 触发的 interrupt，用于打断 take()，以便重连后继续运行
                    log.warn("[MarketTickerStreamService] 流处理被中断（触发重连）");
                    reconnectRequested.set(false); // 避免重复
                    reconnectStream();
                    continue;
                } catch (Exception e) {
                    log.info("[MarketTickerStreamService] 流处理出现异常: {}", e.getMessage());
                    // 处理所有WebSocket异常（包括MessageTooLargeException），并重新建立连接
                    if (handleException(e)) {
                        // handleException已经处理了重连逻辑，这里只需要记录日志
                        log.info("[MarketTickerStreamService] 已处理WebSocket异常并重新建立连接，继续处理消息");
                    } else {
                        log.error("[MarketTickerStreamService] 处理消息时出错（非WebSocket异常）", e);
                        // 非WebSocket异常，继续处理下一条消息，不进行重连
                    }
                }
            }
            
            log.info("[MarketTickerStreamService] 流处理完成");
            
        } catch (Exception e) {
            log.error("[MarketTickerStreamService] 流处理失败", e);
            throw e;
        } finally {
            streamThread.set(null);
        }
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
                log.info("[MarketTickerStreamService] 成功同步{}个ticker数据到数据库（耗时{}ms）", finalCount, duration);
            } catch (Exception e) {
                log.error("[MarketTickerStreamService] Error during batchUpsertTickers: {}", e.getMessage(), e);
                log.error("[MarketTickerStreamService] 批量同步ticker数据到数据库失败", e);
            }
            
            log.debug("[MarketTickerStreamService] Finished handling message");
            
        } catch (Exception e) {
            log.error("[MarketTickerStreamService] Unexpected error in message handling: {}", e.getMessage(), e);
            log.error("[MarketTickerStreamService] 处理ticker消息时出错", e);
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
            log.error("[MarketTickerStreamService] 标准化ticker数据时出错", e);
            return null;
        }
    }
    
    /**
     * 停止流处理
     */
    @Override
    public void stopStream() {
        log.info("[MarketTickerStreamService] 正在停止ticker流...");
        
        running.set(false);
        Thread t = streamThread.get();
        if (t != null) {
            t.interrupt();
        }
        closeCurrentConnectionNoThrow();
        
        if (streamExecutor != null && !streamExecutor.isShutdown()) {
            streamExecutor.shutdown();
            try {
                if (!streamExecutor.awaitTermination(60, TimeUnit.SECONDS)) {
                    log.warn("[MarketTickerStreamService] 流处理线程未在60秒内完全关闭，强制关闭");
                    streamExecutor.shutdownNow();
                } else {
                    log.info("[MarketTickerStreamService] 流处理线程已成功关闭");
                }
            } catch (InterruptedException e) {
                log.error("[MarketTickerStreamService] 等待流处理线程关闭时被中断", e);
                streamExecutor.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
        
        log.info("[MarketTickerStreamService] ticker流已停止");
    }
    
    /**
     * 检查服务状态
     */
    @Override
    public boolean isRunning() {
        return running.get();
    }
}

