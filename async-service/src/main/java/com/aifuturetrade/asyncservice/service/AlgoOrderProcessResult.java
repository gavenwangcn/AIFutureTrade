package com.aifuturetrade.asyncservice.service;

import lombok.Data;

/**
 * 条件订单处理结果
 */
@Data
public class AlgoOrderProcessResult {
    
    /**
     * 检查的订单总数
     */
    private int totalChecked;
    
    /**
     * 已触发的订单数
     */
    private int triggeredCount;
    
    /**
     * 已执行的订单数
     */
    private int executedCount;
    
    /**
     * 失败的订单数
     */
    private int failedCount;
    
    /**
     * 跳过的订单数
     */
    private int skippedCount;
}
