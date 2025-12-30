package com.aifuturetrade.asyncservice.service.impl;

import com.aifuturetrade.asyncservice.service.AsyncAgentService;
import com.aifuturetrade.asyncservice.service.MarketSymbolOfflineService;
import com.aifuturetrade.asyncservice.service.PriceRefreshService;
import com.aifuturetrade.asyncservice.service.MarketTickerStreamTestService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
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
 * 
 * 支持的服务：
 * - MarketTickerStreamService: 市场Ticker流服务
 * - MarketTickerStreamTestService: 市场Ticker流测试服务（独立加载）
 * - PriceRefreshService: 价格刷新服务
 * - MarketSymbolOfflineService: 市场Symbol下线服务
 */
@Slf4j
@Service
public class AsyncAgentServiceImpl implements AsyncAgentService {
    
    // 市场Ticker流测试服务（独立加载）
    @Autowired(required = false)
    private MarketTickerStreamTestService marketTickerStreamTestService;
    
    private final AtomicBoolean allTasksRunning = new AtomicBoolean(false);
    
    private final PriceRefreshService priceRefreshService;
    private final MarketSymbolOfflineService marketSymbolOfflineService;
    
    // 任务状态管理
    private final AtomicReference<Future<?>> marketTickersTask = new AtomicReference<>();
    private final AtomicReference<Future<?>> priceRefreshTask = new AtomicReference<>();
    private final AtomicReference<Future<?>> marketSymbolOfflineTask = new AtomicReference<>();
    
    private ExecutorService executorService;
    
    public AsyncAgentServiceImpl(
            PriceRefreshService priceRefreshService,
            MarketSymbolOfflineService marketSymbolOfflineService) {
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
        

        if (marketTickerStreamTestService != null) {
            log.info("[AsyncAgentServiceImpl] ✅ MarketTickerStreamTestService 已加载: {}", 
                    marketTickerStreamTestService.getClass().getSimpleName());
        }
        
        log.info("[AsyncAgentServiceImpl] 🛠️ 异步代理服务初始化完成，线程池已创建");
    }
    
    @PreDestroy
    public void destroy() {
        log.info("[AsyncAgentServiceImpl] 🛑 收到服务销毁信号，开始清理资源...");
        stopAllTasks();
        if (executorService != null) {
            log.info("[AsyncAgentServiceImpl] ⏳ 正在关闭线程池...");
            executorService.shutdown();
            try {
                if (!executorService.awaitTermination(60, TimeUnit.SECONDS)) {
                    log.warn("[AsyncAgentServiceImpl] ⚠️ 线程池未在60秒内完全关闭，强制关闭");
                    executorService.shutdownNow();
                } else {
                    log.info("[AsyncAgentServiceImpl] ✅ 线程池已成功关闭");
                }
            } catch (InterruptedException e) {
                log.error("[AsyncAgentServiceImpl] ❌ 等待线程池关闭时被中断", e);
                executorService.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
        log.info("[AsyncAgentServiceImpl] 👋 服务销毁完成");
    }
    
    @Override
    public void runTask(String task, Integer durationSeconds) {
        log.info("[AsyncAgentServiceImpl] 🚀 收到启动任务请求: task={}, durationSeconds={}", task, durationSeconds);
        
        switch (task) {
            case "market_tickers_test":
                runMarketTickersTestTask(durationSeconds);
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
                log.error("[AsyncAgentServiceImpl] ❌ 未知的任务类型: task={}", task);
                throw new IllegalArgumentException(
                        "Unknown task '" + task + "'. Available: market_tickers, market_tickers_test, price_refresh, market_symbol_offline, all");
        }
    }
    
    @Override
    public void stopAllTasks() {
        log.info("[AsyncAgentServiceImpl] 🛑 收到停止所有任务请求");
        allTasksRunning.set(false);
        
        // 停止各个任务
        log.info("[AsyncAgentServiceImpl] 🛑 正在停止各个任务...");
        //stopMarketTickersTask();
        stopMarketTickersTestTask();  // 停止测试服务
        stopPriceRefreshTask();
        stopMarketSymbolOfflineTask();
        log.info("[AsyncAgentServiceImpl] ✅ 所有任务已停止");
    }
    
    @Override
    public boolean isTaskRunning(String task) {
        switch (task) {
            case "market_tickers_test":
                return marketTickerStreamTestService != null && marketTickerStreamTestService.isRunning();
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
     * 运行价格刷新任务
     */
    private void runPriceRefreshTask() {
        // 价格刷新服务通过定时任务自动运行，这里可以手动触发一次
        executorService.submit(() -> {
            try {
                if (priceRefreshService != null) {
                    priceRefreshService.refreshAllPrices();
                } else {
                    log.warn("[AsyncAgentServiceImpl] PriceRefreshService is null");
                }
            } catch (Exception e) {
                log.error("[AsyncAgentServiceImpl] Price refresh task error", e);
            }
        });
    }
    
    /**
     * 停止价格刷新任务
     */
    private void stopPriceRefreshTask() {
        if (priceRefreshService != null) {
            priceRefreshService.stopScheduler();
        }
    }
    
    /**
     * 运行市场Symbol下线任务
     */
    private void runMarketSymbolOfflineTask() {
        // Symbol下线服务通过定时任务自动运行，这里可以手动触发一次
        executorService.submit(() -> {
            try {
                if (marketSymbolOfflineService != null) {
                    marketSymbolOfflineService.deleteOldSymbols();
                } else {
                    log.warn("[AsyncAgentServiceImpl] MarketSymbolOfflineService is null");
                }
            } catch (Exception e) {
                log.error("[AsyncAgentServiceImpl] Market symbol offline task error", e);
            }
        });
    }
    
    /**
     * 停止市场Symbol下线任务
     */
    private void stopMarketSymbolOfflineTask() {
        if (marketSymbolOfflineService != null) {
            marketSymbolOfflineService.stopScheduler();
        }
    }
    
    /**
     * 运行所有任务
     */
    private void runAllTasks(Integer durationSeconds) {
        if (allTasksRunning.get()) {
            log.warn("[AsyncAgentServiceImpl] All tasks are already running");
            return;
        }
        
        allTasksRunning.set(true);
        log.info("[AsyncAgentServiceImpl] 启动所有服务: market_tickers, market_tickers_test, price_refresh, market_symbol_offline");
        
        // 启动所有任务
        //runMarketTickersTask(durationSeconds);
        runMarketTickersTestTask(durationSeconds);  // 启动测试服务
        
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
    
    /**
     * 运行市场Ticker流测试任务
     */
    private void runMarketTickersTestTask(Integer durationSeconds) {
        // 检查是否有可用的MarketTickerStreamTestService
        if (marketTickerStreamTestService == null) {
            log.error("[AsyncAgentServiceImpl] ❌ 没有可用的MarketTickerStreamTestService实现");
            return;
        }
        
        log.info("[AsyncAgentServiceImpl] 🎯 启动MarketTickerStreamTest服务: {}", 
                marketTickerStreamTestService.getClass().getSimpleName());
        
        Future<?> task = executorService.submit(() -> {
            try {
                // 测试服务在@PostConstruct中已自动启动，这里不需要额外操作
                log.info("[AsyncAgentServiceImpl] ✅ MarketTickerStreamTestService已在启动时自动加载");
            } catch (Exception e) {
                log.error("[AsyncAgentServiceImpl] Market tickers test task error", e);
            }
        });
        
        marketTickersTask.set(task);
    }
    
    /**
     * 停止市场Ticker流测试任务
     */
    private void stopMarketTickersTestTask() {
        log.info("[AsyncAgentServiceImpl] 🛑 停止MarketTickerStreamTest任务");
        
        Future<?> task = marketTickersTask.get();
        if (task != null && !task.isDone()) {
            task.cancel(true);
        }
        
        // 如果有可用的测试服务，可以在这里添加额外的停止逻辑
        if (marketTickerStreamTestService != null && marketTickerStreamTestService.isRunning()) {
            log.info("[AsyncAgentServiceImpl] 🛑 正在停止MarketTickerStreamTestService...");
            marketTickerStreamTestService.stopStream();
        }
        
        marketTickersTask.set(null);
        log.info("[AsyncAgentServiceImpl] ✅ MarketTickerStreamTest任务已停止");
    }
}