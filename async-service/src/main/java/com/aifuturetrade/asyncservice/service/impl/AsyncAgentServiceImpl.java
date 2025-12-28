package com.aifuturetrade.asyncservice.service.impl;

import com.aifuturetrade.asyncservice.service.AsyncAgentService;
import com.aifuturetrade.asyncservice.service.MarketSymbolOfflineService;
import com.aifuturetrade.asyncservice.service.MarketTickerStreamService;
import com.aifuturetrade.asyncservice.service.PriceRefreshService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import javax.annotation.PostConstruct;
import javax.annotation.PreDestroy;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

/**
 * 异步代理服务实现
 * 
 * 统一管理和调度各种后台异步任务服务。
 */
@Slf4j
@Service
public class AsyncAgentServiceImpl implements AsyncAgentService {
    
    private final MarketTickerStreamService marketTickerStreamService;
    private final PriceRefreshService priceRefreshService;
    private final MarketSymbolOfflineService marketSymbolOfflineService;
    
    private ExecutorService executorService;
    private final AtomicReference<Future<?>> marketTickersTask = new AtomicReference<>();
    private final AtomicReference<Future<?>> priceRefreshTask = new AtomicReference<>();
    private final AtomicReference<Future<?>> marketSymbolOfflineTask = new AtomicReference<>();
    
    private final AtomicBoolean allTasksRunning = new AtomicBoolean(false);
    
    public AsyncAgentServiceImpl(
            MarketTickerStreamService marketTickerStreamService,
            PriceRefreshService priceRefreshService,
            MarketSymbolOfflineService marketSymbolOfflineService) {
        this.marketTickerStreamService = marketTickerStreamService;
        this.priceRefreshService = priceRefreshService;
        this.marketSymbolOfflineService = marketSymbolOfflineService;
    }
    
    @PostConstruct
    public void init() {
        executorService = Executors.newCachedThreadPool(r -> {
            Thread t = new Thread(r, "AsyncAgent-Task-Thread");
            t.setDaemon(true);
            return t;
        });
    }
    
    @PreDestroy
    public void destroy() {
        stopAllTasks();
        if (executorService != null) {
            executorService.shutdown();
            try {
                if (!executorService.awaitTermination(60, TimeUnit.SECONDS)) {
                    executorService.shutdownNow();
                }
            } catch (InterruptedException e) {
                executorService.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
    }
    
    @Override
    public void runTask(String task, Integer durationSeconds) {
        log.info("[AsyncAgent] 启动任务 '{}' (duration={})", task, durationSeconds);
        
        switch (task) {
            case "market_tickers":
                runMarketTickersTask(durationSeconds);
                break;
            case "price_refresh":
                runPriceRefreshTask();
                break;
            case "market_symbol_offline":
                runMarketSymbolOfflineTask();
                break;
            case "all":
                runAllTasks(durationSeconds);
                break;
            default:
                throw new IllegalArgumentException(
                        "Unknown task '" + task + "'. Available: market_tickers, price_refresh, market_symbol_offline, all");
        }
    }
    
    @Override
    public void stopAllTasks() {
        log.info("[AsyncAgent] 停止所有任务");
        allTasksRunning.set(false);
        
        // 停止各个任务
        stopMarketTickersTask();
        stopPriceRefreshTask();
        stopMarketSymbolOfflineTask();
    }
    
    @Override
    public boolean isTaskRunning(String task) {
        switch (task) {
            case "market_tickers":
                return marketTickerStreamService.isRunning();
            case "price_refresh":
                return priceRefreshService != null; // 价格刷新服务通过定时任务运行
            case "market_symbol_offline":
                return marketSymbolOfflineService != null; // Symbol下线服务通过定时任务运行
            case "all":
                return allTasksRunning.get();
            default:
                return false;
        }
    }
    
    /**
     * 运行市场Ticker流任务
     */
    private void runMarketTickersTask(Integer durationSeconds) {
        Future<?> existingTask = marketTickersTask.get();
        if (existingTask != null && !existingTask.isDone()) {
            log.warn("[AsyncAgent] Market tickers task is already running");
            return;
        }
        
        Future<?> task = executorService.submit(() -> {
            try {
                marketTickerStreamService.startStream(durationSeconds);
            } catch (Exception e) {
                log.error("[AsyncAgent] Market tickers task error", e);
            }
        });
        
        marketTickersTask.set(task);
    }
    
    /**
     * 停止市场Ticker流任务
     */
    private void stopMarketTickersTask() {
        Future<?> task = marketTickersTask.getAndSet(null);
        if (task != null && !task.isDone()) {
            task.cancel(true);
            marketTickerStreamService.stopStream();
        }
    }
    
    /**
     * 运行价格刷新任务
     */
    private void runPriceRefreshTask() {
        // 价格刷新服务通过定时任务自动运行，这里可以手动触发一次
        executorService.submit(() -> {
            try {
                priceRefreshService.refreshAllPrices();
            } catch (Exception e) {
                log.error("[AsyncAgent] Price refresh task error", e);
            }
        });
    }
    
    /**
     * 停止价格刷新任务
     */
    private void stopPriceRefreshTask() {
        priceRefreshService.stopScheduler();
    }
    
    /**
     * 运行市场Symbol下线任务
     */
    private void runMarketSymbolOfflineTask() {
        // Symbol下线服务通过定时任务自动运行，这里可以手动触发一次
        executorService.submit(() -> {
            try {
                marketSymbolOfflineService.deleteOldSymbols();
            } catch (Exception e) {
                log.error("[AsyncAgent] Market symbol offline task error", e);
            }
        });
    }
    
    /**
     * 停止市场Symbol下线任务
     */
    private void stopMarketSymbolOfflineTask() {
        marketSymbolOfflineService.stopScheduler();
    }
    
    /**
     * 运行所有任务
     */
    private void runAllTasks(Integer durationSeconds) {
        if (allTasksRunning.get()) {
            log.warn("[AsyncAgent] All tasks are already running");
            return;
        }
        
        allTasksRunning.set(true);
        log.info("[AsyncAgent] 启动所有服务: market_tickers, price_refresh, market_symbol_offline");
        
        // 启动所有任务
        runMarketTickersTask(durationSeconds);
        
        // 价格刷新和Symbol下线服务通过定时任务自动运行
        // 如果需要立即执行，可以手动触发
        runPriceRefreshTask();
        runMarketSymbolOfflineTask();
        
        // 如果指定了运行时长，等待指定时间后停止
        if (durationSeconds != null) {
            executorService.submit(() -> {
                try {
                    Thread.sleep(durationSeconds * 1000L);
                    stopAllTasks();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    stopAllTasks();
                }
            });
        }
    }
}

