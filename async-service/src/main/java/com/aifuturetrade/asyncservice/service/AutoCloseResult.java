package com.aifuturetrade.asyncservice.service;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 自动平仓服务执行结果
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class AutoCloseResult {
    
    /**
     * 检查的持仓总数
     */
    private int totalChecked;
    
    /**
     * 触发平仓的持仓数量
     */
    private int closedCount;
    
    /**
     * 平仓失败的持仓数量
     */
    private int failedCount;
    
    /**
     * 跳过的持仓数量（未达到阈值或其他原因）
     */
    private int skippedCount;
}

