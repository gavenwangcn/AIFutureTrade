package com.aifuturetrade.common.async;

import com.aifuturetrade.service.MarketService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * 异步服务：涨跌幅榜同步
 * 
 * 定期同步涨跌幅榜数据，从数据库的24_market_tickers表查询数据。
 * 前端通过轮询方式获取数据，不再使用WebSocket推送。
 * 
 * 功能：
 * 1. 定期调用MarketService同步涨跌幅榜数据
 * 2. 记录同步日志和统计信息
 * 3. 支持优雅停止
 */
@Slf4j
@Service
public class LeaderboardAsyncService {

    @Autowired
    private MarketService marketService;

    @Value("${app.leaderboard-refresh:10}")
    private Integer leaderboardRefreshInterval;

    private final AtomicInteger cycleCount = new AtomicInteger(0);
    private volatile boolean running = false;

    /**
     * 启动涨跌幅榜同步循环
     * 
     * 使用Spring的@Scheduled注解实现定时任务，默认每10秒执行一次。
     * 可通过配置 app.leaderboard-refresh 调整刷新间隔（单位：秒）。
     * 
     * 注意：fixedDelayString 需要毫秒数，所以需要将配置的秒数乘以1000。
     */
    @Scheduled(fixedDelayString = "${app.leaderboard-refresh:10}000")
    public void syncLeaderboardLoop() {
        if (!running) {
            running = true;
            log.info("[LeaderboardAsyncService] 涨跌幅榜同步循环启动，刷新间隔: {} 秒", leaderboardRefreshInterval);
        }

        int cycle = cycleCount.incrementAndGet();
        LocalDateTime cycleStartTime = LocalDateTime.now();

        try {
            // 调用MarketService同步涨跌幅榜数据（不强制刷新）
            Map<String, Object> data = marketService.getMarketLeaderboard(10, false);

            // 检查同步结果（仅记录日志）
            if (data != null) {
                @SuppressWarnings("unchecked")
                java.util.List<Map<String, Object>> gainers = (java.util.List<Map<String, Object>>) data.get("gainers");
                @SuppressWarnings("unchecked")
                java.util.List<Map<String, Object>> losers = (java.util.List<Map<String, Object>>) data.get("losers");
                
                int gainersCount = gainers != null ? gainers.size() : 0;
                int losersCount = losers != null ? losers.size() : 0;
                
                log.debug(
                    "[LeaderboardAsyncService] [循环 #{}] 同步完成: 涨幅榜 {} 条, 跌幅榜 {} 条（前端通过轮询获取）",
                    cycle, gainersCount, losersCount
                );
            } else {
                log.warn("[LeaderboardAsyncService] [循环 #{}] 同步返回空数据", cycle);
            }
        } catch (Exception e) {
            long cycleDuration = java.time.Duration.between(cycleStartTime, LocalDateTime.now()).getSeconds();
            log.error("[LeaderboardAsyncService] [循环 #{}] 涨跌幅榜同步失败: {}, 耗时: {} 秒", 
                    cycle, e.getMessage(), cycleDuration, e);
        }
    }

    /**
     * 获取当前循环次数
     * @return 循环次数
     */
    public int getCycleCount() {
        return cycleCount.get();
    }

    /**
     * 停止同步循环
     */
    public void stop() {
        running = false;
        log.info("[LeaderboardAsyncService] 涨跌幅榜同步循环停止，总循环次数: {}", cycleCount.get());
    }
}

