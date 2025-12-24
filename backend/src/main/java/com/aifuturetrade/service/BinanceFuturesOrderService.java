package com.aifuturetrade.service;

import java.util.Map;

/**
 * 币安期货订单服务接口
 */
public interface BinanceFuturesOrderService {

    /**
     * 一键卖出持仓合约
     * 
     * @param modelId 模型ID
     * @param symbol 合约符号
     * @return 操作结果
     */
    Map<String, Object> sellPosition(String modelId, String symbol);
}

