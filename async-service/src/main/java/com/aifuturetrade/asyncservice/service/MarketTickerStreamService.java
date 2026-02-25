package com.aifuturetrade.asyncservice.service;

/**
 * 市场Ticker流服务接口
 * 
 * 用于实时接收币安所有交易对的24小时ticker数据，并同步到数据库。
 * 
 * 主要功能：
 * - 通过Binance WebSocket SDK接收全市场ticker数据流
 * - 解析并标准化ticker数据
 * - 批量同步数据到MySQL的24_market_tickers表
 * - 支持自动重连（30分钟限制）
 */
public interface MarketTickerStreamService {
    
    /**
     * 启动ticker流服务
     * 
     * @param runSeconds 可选，运行时长（秒）。如果为null，则无限运行直到被取消
     * @throws Exception 如果启动失败
     */
    void startStream(Integer runSeconds) throws Exception;
    
    /**
     * 停止ticker流服务
     */
    void stopStream();
    
    /**
     * 检查服务是否正在运行
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

