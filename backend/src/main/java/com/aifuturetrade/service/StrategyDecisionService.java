package com.aifuturetrade.service;

import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.common.util.PageRequest;

import java.util.List;
import java.util.Map;

/**
 * 业务逻辑接口：策略决策
 */
public interface StrategyDecisionService {

    /**
     * 根据模型ID查询策略决策记录（分页）
     * @param modelId 模型ID（UUID格式）
     * @param pageRequest 分页请求参数
     * @param status 可选：状态过滤（TRIGGERED/EXECUTED/REJECTED），为空则不过滤
     * @return 分页的策略决策记录
     */
    PageResult<Map<String, Object>> getDecisionsByPage(String modelId, PageRequest pageRequest, String status);

    /**
     * 兼容旧签名：不过滤 status
     */
    default PageResult<Map<String, Object>> getDecisionsByPage(String modelId, PageRequest pageRequest) {
        return getDecisionsByPage(modelId, pageRequest, null);
    }

    /**
     * 根据模型ID查询策略决策记录（保留旧方法以兼容）
     * @param modelId 模型ID（UUID格式）
     * @param limit 限制数量
     * @return 策略决策记录列表
     */
    List<Map<String, Object>> getDecisionsByModelId(String modelId, Integer limit);

}

