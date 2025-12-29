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
            log.warn("[MarketTickerStream] Stream is already running");
            return;
        }
        
        running.set(true);
        connectionCreationTime = LocalDateTime.now();
        
        log.info("=".repeat(80));
        log.info("[MarketTickerStream] ========== 启动市场Ticker流服务 ==========");
        log.info("[MarketTickerStream] 启动时间: {}", LocalDateTime.now());
        log.info("[MarketTickerStream] 最大连接时长: {} 分钟", maxConnectionMinutes);
        log.info("=".repeat(80));
        
        // 启动流处理任务（支持自动重连）
        streamTask = executorService.submit(() -> {
            try {
                if (runSeconds != null) {
                    // 如果指定了运行时长，只运行一次
                    runStreamOnce(runSeconds);
                } else {
                    // 无限运行，每30分钟自动重连
                    long startTime = System.currentTimeMillis();
                    while (running.get()) {
                        try {
                            runStreamOnce(null);
                            
                            // 检查是否达到运行时长限制
                            if (runSeconds != null) {
                                long elapsed = (System.currentTimeMillis() - startTime) / 1000;
                                if (elapsed >= runSeconds) {
                                    break;
                                }
                            }
                            
                            // 等待一段时间后重连
                            log.info("[MarketTickerStream] 等待 {} 秒后重新连接...", reconnectDelay);
                            Thread.sleep(reconnectDelay * 1000L);
                            
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                            break;
                        } catch (Exception e) {
                            log.error("[MarketTickerStream] Stream error, reconnecting...", e);
                            // 等待一段时间后重连
                            try {
                                Thread.sleep(5000);
                            } catch (InterruptedException ie) {
                                Thread.currentThread().interrupt();
                                break;
                            }
                        }
                    }
                }
            } catch (Exception e) {
                log.error("[MarketTickerStream] Stream processing error", e);
            } finally {
                running.set(false);
            }
        });
    }
    
    /**
     * 运行一次流连接（最多30分钟）
     */
    private void runStreamOnce(Integer runSeconds) throws Exception {
        // 创建WebSocket配置
        WebSocketClientConfiguration config = DerivativesTradingUsdsFuturesWebSocketStreamsUtil.getClientConfiguration();
        webSocketStreams = new DerivativesTradingUsdsFuturesWebSocketStreams(config);
        
        // 订阅全市场ticker流
        AllMarketTickersStreamsRequest request = new AllMarketTickersStreamsRequest();
        streamQueue = webSocketStreams.allMarketTickersStreams(request);
        
        // 记录连接创建时间
        connectionCreationTime = LocalDateTime.now();
        
        // 处理流数据
        processStream(runSeconds);
    }
    
    @Override
    public void stopStream() {
        if (!running.get()) {
            return;
        }
        
        log.info("[MarketTickerStream] 停止市场Ticker流服务");
        running.set(false);
        
        if (streamTask != null) {
            streamTask.cancel(true);
        }
        
        // 注意：Java SDK的StreamBlockingQueueWrapper没有直接的unsubscribe方法
        // 连接会在关闭时自动取消订阅
    }
    
    @Override
    public boolean isRunning() {
        return running.get();
    }
    
    /**
     * 处理WebSocket流数据
     */
    private void processStream(Integer runSeconds) {
        long startTime = System.currentTimeMillis();
        
        try {
            while (running.get()) {
                // 检查运行时长限制
                if (runSeconds != null) {
                    long elapsed = (System.currentTimeMillis() - startTime) / 1000;
                    if (elapsed >= runSeconds) {
                        log.info("[MarketTickerStream] 达到运行时长限制 {} 秒，停止流服务", runSeconds);
                        break;
                    }
                }
                
                // 检查连接时长限制（30分钟）
                if (shouldReconnect()) {
                    log.info("[MarketTickerStream] 连接达到 {} 分钟限制，需要重新连接", maxConnectionMinutes);
                    break;
                }
                
                // 从队列中获取ticker数据（阻塞等待）
                try {
                    AllMarketTickersStreamsResponse response = streamQueue.take();
                    if (response != null) {
                        handleMessage(response);
                    }
                } catch (InterruptedException e) {
                    log.info("[MarketTickerStream] Stream interrupted");
                    Thread.currentThread().interrupt();
                    break;
                } catch (Exception e) {
                    log.error("[MarketTickerStream] Error processing message", e);
                    // 继续处理，不中断流
                }
            }
        } catch (Exception e) {
            log.error("[MarketTickerStream] Stream processing error", e);
        } finally {
            log.info("[MarketTickerStream] Stream processing finished");
        }
    }
    
    /**
     * 处理接收到的ticker消息
     */
    private void handleMessage(AllMarketTickersStreamsResponse response) {
        try {
            List<MarketTickerDO> tickers = normalizeTickers(response);
            if (tickers.isEmpty()) {
                return;
            }
            
            // 批量插入或更新到数据库
            marketTickerMapper.batchUpsertTickers(tickers);
            log.debug("[MarketTickerStream] 成功处理 {} 个ticker数据", tickers.size());
            
        } catch (Exception e) {
            log.error("[MarketTickerStream] Error handling message", e);
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
                return tickers;
            }
            
            for (AllMarketTickersStreamsResponseInner inner : response) {
                MarketTickerDO ticker = normalizeSingleTicker(inner);
                if (ticker != null) {
                    tickers.add(ticker);
                }
            }
        } catch (Exception e) {
            log.error("[MarketTickerStream] Error normalizing tickers", e);
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
        
        long elapsedMinutes = java.time.Duration.between(connectionCreationTime, LocalDateTime.now()).toMinutes();
        return elapsedMinutes >= maxConnectionMinutes;
    }
}