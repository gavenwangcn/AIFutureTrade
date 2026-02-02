package com.aifuturetrade.service;

import com.aifuturetrade.common.util.PageRequest;
import com.aifuturetrade.common.util.PageResult;

import java.util.Map;

/**
 * 条件订单服务接口
 */
public interface AlgoOrderService {
    
    /**
     * 根据模型ID分页查询条件订单
     * 
     * @param modelId 模型ID
     * @param pageRequest 分页请求
     * @return 分页结果
     */
    PageResult<Map<String, Object>> getAlgoOrdersByPage(String modelId, PageRequest pageRequest);
}
