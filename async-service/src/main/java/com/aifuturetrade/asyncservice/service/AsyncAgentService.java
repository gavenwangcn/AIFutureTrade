package com.aifuturetrade.asyncservice.service;

/**
 * 异步代理服务接口
 * 
 * 统一管理和调度各种后台异步任务服务。
 * 
 * 支持的任务：
 * - market_tickers: 市场ticker数据流服务
 * - price_refresh: 价格刷新服务
 * - market_symbol_offline: 市场Symbol下线服务
 * - all: 运行所有服务
 */
public interface AsyncAgentService {
    
    /**
     * 运行指定的异步任务
     * 
     * @param task 任务名称：market_tickers, price_refresh, market_symbol_offline, all
     * @param durationSeconds 可选，运行时长（秒）。如果为null，则无限运行
     * @throws IllegalArgumentException 如果任务名称无效
     */
    void runTask(String task, Integer durationSeconds);
    
    /**
     * 停止所有任务
     */
    void stopAllTasks();
    
    /**
     * 检查任务是否正在运行
     * 
     * @param task 任务名称
     * @return true如果正在运行，false否则
     */
    boolean isTaskRunning(String task);
}

