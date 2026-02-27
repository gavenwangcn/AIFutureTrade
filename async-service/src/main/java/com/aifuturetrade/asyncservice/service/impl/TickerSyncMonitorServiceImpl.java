package com.aifuturetrade.asyncservice.service.impl;

import com.aifuturetrade.asyncservice.service.TickerSyncMonitorService;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Ticker同步监控服务实现类
 */
@Slf4j
@Service
public class TickerSyncMonitorServiceImpl implements TickerSyncMonitorService {

    @Value("${trade-monitor.base-url:http://trade-monitor:5005}")
    private String tradeMonitorBaseUrl;

    @Value("${async.monitor.ticker-sync-timeout-minutes:3}")
    private int tickerSyncTimeoutMinutes;

    @Value("${async.monitor.check-interval-seconds:60}")
    private int checkIntervalSeconds;

    @Value("${async.service.container-name:aifuturetrade-async-service}")
    private String containerName;

    private final RestTemplate restTemplate;
    private final AtomicReference<LocalDateTime> lastTickerSyncTime = new AtomicReference<>();
    private final AtomicBoolean isMonitoring = new AtomicBoolean(false);
    private ScheduledExecutorService scheduler;

    public TickerSyncMonitorServiceImpl(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    @PostConstruct
    public void init() {
        log.info("Ticker同步监控服务初始化: timeout={}分钟, checkInterval={}秒",
                tickerSyncTimeoutMinutes, checkIntervalSeconds);
    }

    @Override
    public void recordTickerSyncLog() {
        lastTickerSyncTime.set(LocalDateTime.now());
        log.debug("记录ticker同步时间: {}", lastTickerSyncTime.get());
    }

    @Override
    public void startMonitoring() {
        if (isMonitoring.compareAndSet(false, true)) {
            log.info("启动Ticker同步监控");

            // 初始化最后同步时间
            lastTickerSyncTime.set(LocalDateTime.now());

            // 创建定时任务
            scheduler = Executors.newSingleThreadScheduledExecutor(r -> {
                Thread thread = new Thread(r, "ticker-sync-monitor");
                thread.setDaemon(true);
                return thread;
            });

            scheduler.scheduleAtFixedRate(
                    this::checkTickerSyncStatus,
                    checkIntervalSeconds,
                    checkIntervalSeconds,
                    TimeUnit.SECONDS
            );

            log.info("Ticker同步监控已启动");
        } else {
            log.warn("Ticker同步监控已经在运行中");
        }
    }

    @Override
    public void stopMonitoring() {
        if (isMonitoring.compareAndSet(true, false)) {
            log.info("停止Ticker同步监控");

            if (scheduler != null && !scheduler.isShutdown()) {
                scheduler.shutdown();
                try {
                    if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                        scheduler.shutdownNow();
                    }
                } catch (InterruptedException e) {
                    scheduler.shutdownNow();
                    Thread.currentThread().interrupt();
                }
            }

            log.info("Ticker同步监控已停止");
        }
    }

    @PreDestroy
    public void destroy() {
        stopMonitoring();
    }

    /**
     * 检查ticker同步状态
     */
    private void checkTickerSyncStatus() {
        try {
            LocalDateTime lastSync = lastTickerSyncTime.get();
            if (lastSync == null) {
                log.debug("尚未记录ticker同步时间，跳过检查");
                return;
            }

            long minutesSinceLastSync = ChronoUnit.MINUTES.between(lastSync, LocalDateTime.now());

            if (minutesSinceLastSync >= tickerSyncTimeoutMinutes) {
                log.error("Ticker同步超时: 已经{}分钟未同步数据", minutesSinceLastSync);
                sendAlertToTradeMonitor(minutesSinceLastSync);

                // 重置最后同步时间，避免重复告警
                lastTickerSyncTime.set(LocalDateTime.now());
            } else {
                log.debug("Ticker同步正常: 距离上次同步{}分钟", minutesSinceLastSync);
            }
        } catch (Exception e) {
            log.error("检查ticker同步状态失败", e);
        }
    }

    /**
     * 发送告警到trade-monitor
     */
    private void sendAlertToTradeMonitor(long minutesSinceLastSync) {
        try {
            String url = tradeMonitorBaseUrl + "/api/events/notify";

            Map<String, Object> request = new HashMap<>();
            request.put("eventType", "TICKER_SYNC_TIMEOUT");
            request.put("serviceName", containerName);
            request.put("severity", "ERROR");
            request.put("title", "Ticker同步超时告警");
            request.put("message", String.format(
                    "**服务**: %s\n\n" +
                    "**问题**: Ticker数据同步已超过%d分钟未输出日志\n\n" +
                    "**距离上次同步**: %d分钟\n\n" +
                    "**处置动作**: 系统将自动重启容器",
                    containerName, tickerSyncTimeoutMinutes, minutesSinceLastSync
            ));

            Map<String, Object> metadata = new HashMap<>();
            metadata.put("lastSyncTime", lastTickerSyncTime.get().toString());
            metadata.put("minutesSinceLastSync", minutesSinceLastSync);
            metadata.put("timeoutThreshold", tickerSyncTimeoutMinutes);
            request.put("metadata", metadata);

            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);

            HttpEntity<Map<String, Object>> httpRequest = new HttpEntity<>(request, headers);

            Map<String, Object> response = restTemplate.postForObject(url, httpRequest, Map.class);

            if (response != null && Boolean.TRUE.equals(response.get("success"))) {
                log.info("告警已发送到trade-monitor: alertId={}", response.get("alertId"));
            } else {
                log.error("发送告警到trade-monitor失败: {}", response);
            }
        } catch (Exception e) {
            log.error("发送告警到trade-monitor异常", e);
        }
    }
}
