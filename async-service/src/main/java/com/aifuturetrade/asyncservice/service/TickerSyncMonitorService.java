package com.aifuturetrade.asyncservice.service;

/**
 * Ticker同步监控服务接口
 */
public interface TickerSyncMonitorService {

    /**
     * 记录ticker同步日志
     */
    void recordTickerSyncLog();

    /**
     * 启动监控
     */
    void startMonitoring();

    /**
     * 停止监控
     */
    void stopMonitoring();
}
