package com.aifuturetrade.asyncservice.service.impl;

import com.aifuturetrade.asyncservice.dao.mapper.MarketTickerMapper;
import com.aifuturetrade.asyncservice.service.MarketSymbolOfflineService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import javax.annotation.PostConstruct;
import javax.annotation.PreDestroy;
import java.time.LocalDateTime;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 市场Symbol下线服务实现
 * 
 * 定时删除过期的ticker数据。
 * 删除ingestion_time早于（当前时间 - 保留分钟数）的所有记录。
 */
@Slf4j
@Service
public class MarketSymbolOfflineServiceImpl implements MarketSymbolOfflineService {
    
    private final MarketTickerMapper marketTickerMapper;
    
    @Value("${async.market-symbol-offline.cron:*/30 * * * *}")
    private String cronExpression;
    
    @Value("${async.market-symbol-offline.retention-minutes:30}")
    private int retentionMinutes;
    
    private final AtomicBoolean schedulerRunning = new AtomicBoolean(false);
    
    public MarketSymbolOfflineServiceImpl(MarketTickerMapper marketTickerMapper) {
        this.marketTickerMapper = marketTickerMapper;
    }
    
    @PostConstruct
    public void init() {
        log.info("[MarketSymbolOfflineServiceImpl] 🛠️ 市场Symbol下线服务初始化完成");
        log.info("[MarketSymbolOfflineServiceImpl] 📅 调度Cron表达式: {}", cronExpression);
        log.info("[MarketSymbolOfflineServiceImpl] ⏱️ 数据保留分钟数: {}", retentionMinutes);
    }
    
    @PreDestroy
    public void destroy() {
        log.info("[MarketSymbolOfflineServiceImpl] 🛑 收到服务销毁信号，停止调度器...");
        stopScheduler();
        log.info("[MarketSymbolOfflineServiceImpl] 👋 市场Symbol下线服务已销毁");
    }
    
    @Override
    public long deleteOldSymbols() {
        LocalDateTime deleteStartTime = LocalDateTime.now();
        log.info("=".repeat(80));
        log.info("[MarketSymbolOffline] ========== 开始执行异步市场Symbol下线任务 ==========");
        log.info("[MarketSymbolOffline] 执行时间: {}", deleteStartTime);
        log.info("=".repeat(80));
        
        try {
            // 计算截止日期
            LocalDateTime cutoffDate = LocalDateTime.now().minusMinutes(retentionMinutes);
            log.info("[MarketSymbolOffline] [步骤1] 计算截止日期: 当前时间 - {} 分钟 = {}", 
                    retentionMinutes, cutoffDate);
            
            // 查询要删除的记录数量
            log.info("[MarketSymbolOffline] [步骤2] 查询要删除的记录数量...");
            Long recordCount = marketTickerMapper.countOldTickers(cutoffDate);
            
            if (recordCount == null || recordCount == 0) {
                log.info("[MarketSymbolOffline] [步骤2] ⚠️  没有需要删除的记录");
                log.info("=".repeat(80));
                log.info("[MarketSymbolOffline] ========== Symbol下线任务完成（无数据需要删除） ==========");
                log.info("=".repeat(80));
                return 0;
            }
            
            log.info("[MarketSymbolOffline] [步骤2] ✅ 查询完成，找到 {} 条需要删除的记录", recordCount);
            
            // 执行删除操作
            log.info("[MarketSymbolOffline] [步骤3] 执行删除操作...");
            int deletedCount = marketTickerMapper.deleteOldTickers(cutoffDate);
            
            // 计算总耗时
            long totalDuration = java.time.Duration.between(deleteStartTime, LocalDateTime.now()).getSeconds();
            
            // 输出详细统计信息
            log.info("=".repeat(80));
            log.info("[MarketSymbolOffline] ========== 异步市场Symbol下线任务执行完成 ==========");
            log.info("[MarketSymbolOffline] 执行时间: {}", deleteStartTime);
            log.info("[MarketSymbolOffline] 完成时间: {}", LocalDateTime.now());
            log.info("[MarketSymbolOffline] 总耗时: {} 秒 ({} 分钟)", totalDuration, totalDuration / 60.0);
            log.info("[MarketSymbolOffline] 统计信息:");
            log.info("[MarketSymbolOffline]   - 保留分钟: {} 分钟", retentionMinutes);
            log.info("[MarketSymbolOffline]   - 截止日期: {}", cutoffDate);
            log.info("[MarketSymbolOffline]   - 删除记录数: {} 条", deletedCount);
            log.info("=".repeat(80));
            
            return deletedCount;
            
        } catch (Exception e) {
            long totalDuration = java.time.Duration.between(deleteStartTime, LocalDateTime.now()).getSeconds();
            log.error("=".repeat(80));
            log.error("[MarketSymbolOfflineServiceImpl] ========== 异步市场Symbol下线任务执行失败 ==========");
            log.error("[MarketSymbolOfflineServiceImpl] 执行时间: {}", deleteStartTime);
            log.error("[MarketSymbolOfflineServiceImpl] 失败时间: {}", LocalDateTime.now());
            log.error("[MarketSymbolOfflineServiceImpl] 总耗时: {} 秒", totalDuration);
            log.error("[MarketSymbolOfflineServiceImpl] 错误信息: ", e);
            log.error("=".repeat(80));
            return 0;
        }
    }
    
    @Override
    @Scheduled(cron = "${async.market-symbol-offline.cron:*/30 * * * *}")
    public void startScheduler() {
        if (schedulerRunning.get()) {
            return;
        }
        
        schedulerRunning.set(true);
        try {
            deleteOldSymbols();
        } finally {
            schedulerRunning.set(false);
        }
    }
    
    @Override
    public void stopScheduler() {
        schedulerRunning.set(false);
    }
}

