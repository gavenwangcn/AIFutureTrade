package com.aifuturetrade.asyncservice.service;

/**
 * 账户每日价值服务接口
 * 
 * 功能：
 * 1. 每天8点执行，记录每个模型的账户总值和可用现金
 */
public interface AccountValuesDailyService {
    
    /**
     * 记录所有模型的每日账户价值
     * 每天8点执行
     */
    void recordDailyAccountValues();
    
    /**
     * 启动定时调度器
     * 使用cron表达式配置执行频率
     */
    void startScheduler();
    
    /**
     * 停止定时调度器
     */
    void stopScheduler();
}
