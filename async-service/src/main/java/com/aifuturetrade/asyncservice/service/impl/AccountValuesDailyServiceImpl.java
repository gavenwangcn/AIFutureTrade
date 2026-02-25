package com.aifuturetrade.asyncservice.service.impl;

import com.aifuturetrade.asyncservice.dao.mapper.AccountValuesDailyMapper;
import com.aifuturetrade.asyncservice.dao.mapper.AccountValuesMapper;
import com.aifuturetrade.asyncservice.dao.mapper.ModelMapper;
import com.aifuturetrade.asyncservice.entity.ModelDO;
import com.aifuturetrade.asyncservice.service.AccountValuesDailyService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 账户每日价值服务实现
 * 
 * 功能：
 * 1. 每天8点执行，记录每个模型的账户总值和可用现金到account_values_daily表
 */
@Slf4j
@Service
public class AccountValuesDailyServiceImpl implements AccountValuesDailyService {
    
    @Autowired
    private ModelMapper modelMapper;
    
    @Autowired
    private AccountValuesMapper accountValuesMapper;
    
    @Autowired
    private AccountValuesDailyMapper accountValuesDailyMapper;
    
    // Cron表达式配置，默认每两分钟执行一次
    @Value("${async.account-values-daily.cron:0 0 8 * * ?}")
    private String cronExpression;
    
    // 调度器运行状态
    private final AtomicBoolean schedulerRunning = new AtomicBoolean(false);
    
    /**
     * 记录所有模型的每日账户价值
     */
    @Override
    public void recordDailyAccountValues() {
        log.info("=".repeat(80));
        log.info("[AccountValuesDaily] ========== 开始执行每日账户价值记录任务 ==========");
        
        int totalModels = 0;
        int successCount = 0;
        int failedCount = 0;
        
        try {
            // 查询所有模型
            List<ModelDO> models = modelMapper.selectList(null);
            if (models == null || models.isEmpty()) {
                log.info("[AccountValuesDaily] ⚠️  没有找到任何模型");
                log.info("=".repeat(80));
                return;
            }
            
            totalModels = models.size();
            log.info("[AccountValuesDaily] 📊 查询到 {} 个模型", totalModels);
            
            // 查询所有账户价值（一次性查询，提高效率）
            List<Map<String, Object>> accountValuesList = accountValuesMapper.selectAllAccountValues();
            Map<String, Map<String, Object>> accountValuesMap = new java.util.HashMap<>();
            for (Map<String, Object> av : accountValuesList) {
                String modelId = (String) av.get("model_id");
                if (modelId != null) {
                    accountValuesMap.put(modelId, av);
                }
            }
            
            // 遍历每个模型，记录账户价值
            for (ModelDO model : models) {
                String modelId = model.getId();
                try {
                    // 从account_values表获取账户价值
                    Map<String, Object> accountValue = accountValuesMap.get(modelId);
                    
                    Double balance = null;
                    Double availableBalance = null;
                    
                    if (accountValue != null) {
                        Object balanceObj = accountValue.get("balance");
                        Object availableBalanceObj = accountValue.get("available_balance");
                        
                        if (balanceObj instanceof Number) {
                            balance = ((Number) balanceObj).doubleValue();
                        } else if (balanceObj != null) {
                            balance = Double.parseDouble(balanceObj.toString());
                        }
                        
                        if (availableBalanceObj instanceof Number) {
                            availableBalance = ((Number) availableBalanceObj).doubleValue();
                        } else if (availableBalanceObj != null) {
                            availableBalance = Double.parseDouble(availableBalanceObj.toString());
                        }
                    }
                    
                    // 如果account_values表中没有数据，使用模型的初始资金
                    if (balance == null || availableBalance == null) {
                        Double initialCapital = model.getInitialCapital();
                        if (initialCapital == null) {
                            initialCapital = 10000.0; // 默认值
                        }
                        balance = initialCapital;
                        availableBalance = initialCapital;
                        log.debug("[AccountValuesDaily] 模型 {} 在account_values表中无数据，使用初始资金: {}", 
                                modelId, initialCapital);
                    }
                    
                    // 记录到account_values_daily表
                    String recordId = UUID.randomUUID().toString();
                    // 获取UTC+8时区的当前时间（北京时间）
                    LocalDateTime createdAt = LocalDateTime.now(ZoneId.of("Asia/Shanghai"));
                    accountValuesDailyMapper.insertDailyAccountValue(
                            recordId, modelId, balance, availableBalance, createdAt);
                    
                    successCount++;
                    log.debug("[AccountValuesDaily] ✅ 模型 {} 记录成功: balance={}, available_balance={}", 
                            modelId, balance, availableBalance);
                    
                } catch (Exception e) {
                    failedCount++;
                    log.error("[AccountValuesDaily] ❌ 模型 {} 记录失败: {}", modelId, e.getMessage(), e);
                }
            }
            
            log.info("[AccountValuesDaily] ========== 每日账户价值记录任务完成 ==========");
            log.info("[AccountValuesDaily] 📊 统计: 总计={}, 成功={}, 失败={}", 
                    totalModels, successCount, failedCount);
            log.info("=".repeat(80));
            
        } catch (Exception e) {
            log.error("[AccountValuesDaily] ❌ 执行每日账户价值记录任务失败: {}", e.getMessage(), e);
            log.info(".".repeat(80));
        }
    }
    
    /**
     * 使用cron表达式启动定时调度器
     * 默认每两分钟执行一次
     */
    @Override
    @Scheduled(cron = "${async.account-values-daily.cron:0 */2 * * * ?}")
    public void startScheduler() {
        if (schedulerRunning.get()) {
            return;
        }
        
        schedulerRunning.set(true);
        try {
            recordDailyAccountValues();
        } finally {
            schedulerRunning.set(false);
        }
    }
    
    /**
     * 停止定时调度器
     */
    @Override
    public void stopScheduler() {
        schedulerRunning.set(false);
    }
}
