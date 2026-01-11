package com.aifuturetrade.asyncservice.service;

/**
 * 自动平仓服务接口
 * 
 * 功能：
 * - 定时检查所有持仓的损失百分比
 * - 当损失达到配置的阈值时，自动执行市场价卖出操作
 */
public interface AutoCloseService {
    
    /**
     * 执行自动平仓检查
     * 检查所有持仓，如果损失达到阈值则自动平仓
     * 
     * @return 处理结果统计
     */
    AutoCloseResult checkAndClosePositions();
    
    /**
     * 启动定时任务
     */
    void startScheduler();
    
    /**
     * 停止定时任务
     */
    void stopScheduler();
    
    /**
     * 检查定时任务是否正在运行
     * 
     * @return true如果正在运行，false否则
     */
    boolean isSchedulerRunning();
}

