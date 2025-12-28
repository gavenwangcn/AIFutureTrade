package com.aifuturetrade.asyncservice.config;

import com.aifuturetrade.asyncservice.service.AsyncAgentService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * 异步服务启动监听器
 * 
 * 在Spring Boot应用启动完成后，自动启动配置的异步服务。
 * 使用延迟启动确保所有Bean都已完全初始化。
 */
@Slf4j
@Component
public class AsyncServiceStartupListener implements ApplicationListener<ApplicationReadyEvent> {
    
    @Autowired
    private AsyncAgentService asyncAgentService;
    
    /**
     * 启动时自动启动的任务
     * 可选值：market_tickers, price_refresh, market_symbol_offline, all
     * 默认值：all（启动所有服务）
     */
    @Value("${async.auto-start-task:all}")
    private String autoStartTask;
    
    /**
     * 是否启用自动启动
     * 默认值：true（启用）
     */
    @Value("${async.auto-start-enabled:true}")
    private boolean autoStartEnabled;
    
    /**
     * 启动延迟（秒）
     * 默认值：3秒，确保所有Bean都已完全初始化
     */
    @Value("${async.auto-start-delay:3}")
    private int autoStartDelay;
    
    private final ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor(r -> {
        Thread t = new Thread(r, "AsyncServiceStartup-Delay");
        t.setDaemon(true);
        return t;
    });
    
    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        if (!autoStartEnabled) {
            log.info("[AsyncServiceStartup] 自动启动已禁用，跳过服务启动");
            log.info("[AsyncServiceStartup] 提示：可通过REST API手动启动服务");
            log.info("[AsyncServiceStartup] 示例：curl -X POST http://localhost:5003/api/async/task/all");
            return;
        }
        
        log.info("=".repeat(80));
        log.info("[AsyncServiceStartup] ========== 应用启动完成，准备自动启动异步服务 ==========");
        log.info("[AsyncServiceStartup] 自动启动任务: {}", autoStartTask);
        log.info("[AsyncServiceStartup] 启动延迟: {} 秒（确保所有Bean初始化完成）", autoStartDelay);
        log.info("[AsyncServiceStartup] 注意：价格刷新和Symbol下线服务会通过定时任务自动运行");
        log.info("=".repeat(80));
        
        // 延迟启动，确保所有Bean都已完全初始化
        scheduler.schedule(() -> {
            try {
                log.info("[AsyncServiceStartup] 延迟启动完成，开始启动异步服务...");
                
                // 启动配置的任务（null表示无限运行）
                asyncAgentService.runTask(autoStartTask, null);
                
                // 等待一小段时间让服务启动
                Thread.sleep(2000);
                
                log.info("[AsyncServiceStartup] ✅ 异步服务 '{}' 已启动", autoStartTask);
                log.info("[AsyncServiceStartup] 服务状态：");
                log.info("[AsyncServiceStartup]   - market_tickers: {}", 
                        asyncAgentService.isTaskRunning("market_tickers") ? "运行中" : "未运行");
                log.info("[AsyncServiceStartup]   - price_refresh: 定时任务已启用（通过@Scheduled自动运行）");
                log.info("[AsyncServiceStartup]   - market_symbol_offline: 定时任务已启用（通过@Scheduled自动运行）");
                log.info("=".repeat(80));
            } catch (IllegalArgumentException e) {
                log.error("[AsyncServiceStartup] ❌ 无效的任务名称: {}", autoStartTask);
                log.error("[AsyncServiceStartup] 可用任务: market_tickers, price_refresh, market_symbol_offline, all");
                log.error("=".repeat(80));
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                log.warn("[AsyncServiceStartup] 启动过程被中断");
            } catch (Exception e) {
                log.error("[AsyncServiceStartup] ❌ 启动异步服务失败: {}", autoStartTask, e);
                log.error("[AsyncServiceStartup] 提示：可通过REST API手动启动服务");
                log.error("[AsyncServiceStartup] 示例：curl -X POST http://localhost:5003/api/async/task/{}", autoStartTask);
                log.error("=".repeat(80));
                // 不抛出异常，允许应用继续运行
            }
        }, autoStartDelay, TimeUnit.SECONDS);
    }
}

