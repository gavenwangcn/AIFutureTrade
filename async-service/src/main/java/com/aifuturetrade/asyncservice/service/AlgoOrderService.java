package com.aifuturetrade.asyncservice.service;

/**
 * 条件订单服务接口
 * 
 * 功能：
 * 1. 定时检查algo_order表中状态为"new"的条件订单
 * 2. 查询对应symbol的市场价格
 * 3. 根据positionSide判断是否触发成交条件
 * 4. 如果触发，执行交易并更新相关表（trades、account_value_historys、account_values等）
 */
public interface AlgoOrderService {
    
    /**
     * 检查并处理条件订单
     * 
     * @return 处理结果
     */
    AlgoOrderProcessResult processAlgoOrders();
    
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
