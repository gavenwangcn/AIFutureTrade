package com.aifuturetrade.asyncservice.service;

/**
 * 市场Symbol下线服务接口
 * 
 * 负责定时删除过期的ticker数据。
 * 删除ingestion_time早于（当前时间 - 保留分钟数）的所有记录。
 * 
 * 主要功能：
 * - 统计需要删除的记录数量
 * - 批量删除过期的ticker数据
 * - 根据cron表达式定时执行清理任务
 */
public interface MarketSymbolOfflineService {
    
    /**
     * 删除过期的symbol数据
     * 
     * @return 删除的记录数
     */
    long deleteOldSymbols();
    
    /**
     * 启动定时清理调度器
     */
    void startScheduler();
    
    /**
     * 停止定时清理调度器
     */
    void stopScheduler();
}

