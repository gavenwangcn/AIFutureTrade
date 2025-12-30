package com.aifuturetrade.asyncservice.service;

/**
 * 市场Ticker流测试服务接口
 * 
 * 用于测试和排查MarketTickerStreamService启动失败的问题，
 * 完全按照Binance SDK官方示例 AllMarketTickersStreamsExample.java 实现。
 * 
 * 主要功能：
 * - 验证Binance WebSocket SDK的基本功能
 * - 测试所有市场ticker数据流接收
 * - 提供详细的调试日志和状态信息
 */
public interface MarketTickerStreamTestService {
    
    /**
     * 启动测试流服务
     * 
     * @param runSeconds 可选，运行时长（秒）。如果为null，则无限运行直到被取消
     * @throws Exception 如果启动失败
     */
    void startStream(Integer runSeconds) throws Exception;
    
    /**
     * 停止测试流服务
     */
    void stopStream();
    
    /**
     * 检查测试服务是否正在运行
     * 
     * @return true如果正在运行，false否则
     */
    boolean isRunning();
    
    /**
     * 获取WebSocket API实例
     * 
     * @return DerivativesTradingUsdsFuturesWebSocketStreams API实例
     */
    Object getApi();
}