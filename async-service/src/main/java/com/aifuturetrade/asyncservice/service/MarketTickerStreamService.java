package com.aifuturetrade.asyncservice.service;

/**
 * 市场Ticker流服务接口
 * 
 * 负责通过币安WebSocket接收所有交易对的24小时ticker数据，
 * 并将数据存储到MySQL的24_market_tickers表中。
 * 
 * 主要功能：
 * - 建立WebSocket连接，订阅全市场ticker流
 * - 实时接收ticker数据并存储到数据库
 * - 自动重连（每30分钟重新建立连接，币安限制）
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
}

