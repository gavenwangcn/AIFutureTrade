package com.aifuturetrade.asyncservice.service.impl;

import com.aifuturetrade.asyncservice.dao.mapper.AlgoOrderMapper;
import com.aifuturetrade.asyncservice.dao.mapper.StrategyDecisionMapper;
import com.aifuturetrade.asyncservice.service.AlgoOrderCleanupService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import jakarta.annotation.PreDestroy;
import java.time.LocalDateTime;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 条件订单清理服务实现
 *
 * 定期清理已取消的历史条件订单，避免数据库中积累过多无用数据
 */
@Slf4j
@Service
public class AlgoOrderCleanupServiceImpl implements AlgoOrderCleanupService {

    private final AlgoOrderMapper algoOrderMapper;
    private final StrategyDecisionMapper strategyDecisionMapper;

    @Value("${async.algo-order-cleanup.retention-hours:1}")
    private int retentionHours;

    @Value("${async.algo-order-cleanup.cron:0 */10 * * * *}")
    private String cronExpression;

    @Value("${async.algo-order-cleanup.enabled:true}")
    private boolean cleanupEnabled;

    private final AtomicBoolean schedulerRunning = new AtomicBoolean(false);

    public AlgoOrderCleanupServiceImpl(AlgoOrderMapper algoOrderMapper, StrategyDecisionMapper strategyDecisionMapper) {
        this.algoOrderMapper = algoOrderMapper;
        this.strategyDecisionMapper = strategyDecisionMapper;
    }

    @PreDestroy
    public void destroy() {
        stopScheduler();
    }

    @Override
    public CleanupResult cleanupCancelledOrders() {
        log.info("=" .repeat(80));
        log.info("[AlgoOrderCleanup] ========== 开始执行条件订单清理任务 ==========");
        // 使用UTC+8时区时间（与数据库时区一致）
        log.info("[AlgoOrderCleanup] 执行时间: {}", LocalDateTime.now(java.time.ZoneOffset.ofHours(8)));
        log.info("[AlgoOrderCleanup] Cron表达式: {}", cronExpression);
        log.info("[AlgoOrderCleanup] 数据保留时长: {} 小时", retentionHours);
        log.info("=".repeat(80));

        try {
            // 计算时间阈值：当前时间减去保留时长
            LocalDateTime utc8Time = LocalDateTime.now(java.time.ZoneOffset.ofHours(8));
            LocalDateTime beforeTime = utc8Time.minusHours(retentionHours);

            log.info("[AlgoOrderCleanup] [步骤1] 计算时间阈值");
            log.info("[AlgoOrderCleanup] [步骤1] 当前时间(UTC+8): {}", utc8Time);
            log.info("[AlgoOrderCleanup] [步骤1] 删除阈值时间(UTC+8): {}", beforeTime);
            log.info("[AlgoOrderCleanup] [步骤1] 将删除状态为CANCELLED且创建时间早于 {} 的订单及相关策略决策", beforeTime);

            // 先删除相关的策略决策数据
            log.info("[AlgoOrderCleanup] [步骤2] 开始删除相关的策略决策数据...");
            int deletedStrategyCount = strategyDecisionMapper.deleteByRelatedCancelledOrders(beforeTime);
            log.info("[AlgoOrderCleanup] [步骤2] ✅ 策略决策删除完成，共删除 {} 条记录", deletedStrategyCount);

            // 再删除条件订单数据
            log.info("[AlgoOrderCleanup] [步骤3] 开始删除条件订单数据...");
            int deletedOrderCount = algoOrderMapper.deleteCancelledOrdersBeforeTime(beforeTime);
            log.info("[AlgoOrderCleanup] [步骤3] ✅ 条件订单删除完成，共删除 {} 条记录", deletedOrderCount);

            int totalDeleted = deletedStrategyCount + deletedOrderCount;
            log.info("=".repeat(80));
            log.info("[AlgoOrderCleanup] ========== 条件订单清理任务完成 ==========");
            log.info("[AlgoOrderCleanup] 总计删除: {} 条记录（策略决策: {}, 条件订单: {}）",
                    totalDeleted, deletedStrategyCount, deletedOrderCount);
            log.info("=".repeat(80));

            return new CleanupResult(totalDeleted, true,
                    String.format("清理成功，删除 %d 条记录（策略决策: %d, 条件订单: %d）",
                            totalDeleted, deletedStrategyCount, deletedOrderCount));

        } catch (Exception e) {
            log.error("[AlgoOrderCleanup] ========== 条件订单清理任务执行失败 ==========", e);
            log.error("=".repeat(80));
            return new CleanupResult(0, false, "清理失败: " + e.getMessage());
        }
    }

    @Override
    @Scheduled(cron = "${async.algo-order-cleanup.cron:0 */10 * * * *}")
    public void startScheduler() {
        if (!cleanupEnabled) {
            log.debug("[AlgoOrderCleanup] 清理任务已禁用，跳过执行");
            return;
        }

        if (schedulerRunning.get()) {
            log.debug("[AlgoOrderCleanup] 清理任务正在执行中，跳过本次调度");
            return;
        }

        schedulerRunning.set(true);
        try {
            cleanupCancelledOrders();
        } finally {
            schedulerRunning.set(false);
        }
    }

    @Override
    public void stopScheduler() {
        schedulerRunning.set(false);
        log.info("[AlgoOrderCleanup] 清理任务已停止");
    }

    @Override
    public boolean isSchedulerRunning() {
        return cleanupEnabled;
    }
}
