package com.aifuturetrade.asyncservice.service.impl;

import com.aifuturetrade.asyncservice.service.AsyncAgentService;
import com.aifuturetrade.asyncservice.service.MarketSymbolOfflineService;
import com.aifuturetrade.asyncservice.service.PriceRefreshService;
import com.aifuturetrade.asyncservice.service.MarketTickerStreamService;
import com.aifuturetrade.asyncservice.service.AccountValuesDailyService;
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
 * - PriceRefreshService: 价格刷新服务
 * - MarketSymbolOfflineService: 市场Symbol下线服务
 */
@Slf4j
@Service
public class AsyncAgentServiceImpl implements AsyncAgentService {
    
    // 市场Ticker流服务
    @Autowired(required = false)
    private MarketTickerStreamService marketTickerStreamService;
    
    // 账户每日价值服务
    @Autowired(required = false)
    private AccountValuesDailyService accountValuesDailyService;
    
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
        

        if (marketTickerStreamService != null) {
            log.info("[AsyncAgentServiceImpl] ✅ MarketTickerStreamService 已加载: {}", 
                    marketTickerStreamService.getClass().getSimpleName());
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
            case "market_tickers":
                runMarketTickersTask(durationSeconds);
                break;
            case "price_refresh":
                runPriceRefreshTask();
                break;
            case "market_symbol_offline":
                runMarketSymbolOfflineTask();
                break;
            case "account_values_daily":
                runAccountValuesDailyTask();
                break;
            case "all":
                runAllTasks(durationSeconds);
                break;
            default:
                log.error("[AsyncAgentServiceImpl] ❌ 未知的任务类型: task={}", task);
                throw new IllegalArgumentException(
                        "Unknown task '" + task + "'. Available: market_tickers, price_refresh, market_symbol_offline, account_values_daily, all");
        }
    }
    
    @Override
    public void stopAllTasks() {
        log.info("[AsyncAgentServiceImpl] 🛑 收到停止所有任务请求");
        allTasksRunning.set(false);
        
        // 停止各个任务
        log.info("[AsyncAgentServiceImpl] 🛑 正在停止各个任务...");
        stopMarketTickersTask();
        stopPriceRefreshTask();
        stopMarketSymbolOfflineTask();
        stopAccountValuesDailyTask();
        log.info("[AsyncAgentServiceImpl] ✅ 所有任务已停止");
    }
    
    @Override
    public boolean isTaskRunning(String task) {
        switch (task) {
            case "market_tickers":
                return marketTickerStreamService != null && marketTickerStreamService.isRunning();
            case "price_refresh":
                return priceRefreshService != null; // 价格刷新服务通过定时任务运行
            case "market_symbol_offline":
                return marketSymbolOfflineService != null; // Symbol下线服务通过定时任务运行
            case "account_values_daily":
                return accountValuesDailyService != null; // 账户每日价值服务通过定时任务运行
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
     * 运行账户每日价值记录任务
     * 依赖@Scheduled注解和cron表达式进行定时触发
     */
    private void runAccountValuesDailyTask() {
        // 账户每日价值服务通过@Scheduled注解自动运行，无需立即执行
        // 这里保持方法存在是为了与其他任务保持一致的API设计
        log.info("[AsyncAgentServiceImpl] Account values daily task is configured with cron expression, will be triggered automatically");
        
        // 可以选择手动触发一次，或者只依赖cron表达式
        // 以下代码为手动触发一次的实现，如果不需要可以注释掉
        /*
executorService.submit(() -> {
            try {
                if (accountValuesDailyService != null) {
                    accountValuesDailyService.recordDailyAccountValues();
                } else {
                    log.warn("[AsyncAgentServiceImpl] AccountValuesDailyService is null");
                }
            } catch (Exception e) {
                log.error("[AsyncAgentServiceImpl] Account values daily task error", e);
            }
        });
        */
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
     * 停止账户每日价值任务
     */
    private void stopAccountValuesDailyTask() {
        if (accountValuesDailyService != null) {
            accountValuesDailyService.stopScheduler();
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
        log.info("[AsyncAgentServiceImpl] 启动所有服务: market_tickers, price_refresh, market_symbol_offline");
        
        // 启动所有任务
        runMarketTickersTask(durationSeconds);
        
        // 价格刷新、Symbol下线和账户每日价值服务通过定时任务自动运行
        // 如果需要立即执行，可以手动触发
        runPriceRefreshTask();
        runMarketSymbolOfflineTask();
        runAccountValuesDailyTask();
        
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
     * 运行市场Ticker流任务
     */
    private void runMarketTickersTask(Integer durationSeconds) {
        // 检查是否有可用的MarketTickerStreamService
        if (marketTickerStreamService == null) {
            log.error("[AsyncAgentServiceImpl] ❌ 没有可用的MarketTickerStreamService实现");
            return;
        }
        
        log.info("[AsyncAgentServiceImpl] 🎯 启动MarketTickerStream服务: {}", 
                marketTickerStreamService.getClass().getSimpleName());
        
        Future<?> task = executorService.submit(() -> {
            try {
                marketTickerStreamService.startStream(durationSeconds);
                log.info("[AsyncAgentServiceImpl] ✅ MarketTickerStreamService已启动");
            } catch (Exception e) {
                log.error("[AsyncAgentServiceImpl] Market tickers task error", e);
            }
        });
        
        marketTickersTask.set(task);
    }
    
    /**
     * 停止市场Ticker流任务
     */
    private void stopMarketTickersTask() {
        log.info("[AsyncAgentServiceImpl] 🛑 停止MarketTickerStream任务");
        
        Future<?> task = marketTickersTask.get();
        if (task != null && !task.isDone()) {
            task.cancel(true);
        }
        
        // 如果有可用的服务，停止流处理
        if (marketTickerStreamService != null && marketTickerStreamService.isRunning()) {
            log.info("[AsyncAgentServiceImpl] 🛑 正在停止MarketTickerStreamService...");
            marketTickerStreamService.stopStream();
        }
        
        marketTickersTask.set(null);
        log.info("[AsyncAgentServiceImpl] ✅ MarketTickerStream任务已停止");
    }
}