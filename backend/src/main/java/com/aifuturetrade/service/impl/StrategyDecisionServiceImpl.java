package com.aifuturetrade.service.impl;

import com.aifuturetrade.dao.entity.StrategyDecisionDO;
import com.aifuturetrade.dao.mapper.StrategyDecisionMapper;
import com.aifuturetrade.service.StrategyDecisionService;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.common.util.PageRequest;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 业务逻辑实现类：策略决策
 */
@Slf4j
@Service
public class StrategyDecisionServiceImpl implements StrategyDecisionService {

    @Autowired
    private StrategyDecisionMapper strategyDecisionMapper;

    @Override
    public PageResult<Map<String, Object>> getDecisionsByPage(String modelId, PageRequest pageRequest) {
        try {
            // 设置默认值
            Integer pageNum = pageRequest.getPageNum() != null && pageRequest.getPageNum() > 0 ? pageRequest.getPageNum() : 1;
            Integer pageSize = pageRequest.getPageSize() != null && pageRequest.getPageSize() > 0 ? pageRequest.getPageSize() : 10;
            
            // 查询总数
            Long total = strategyDecisionMapper.countDecisionsByModelId(modelId);
            log.debug("Strategy decisions total count for model {}: {}", modelId, total);
            
            // 使用MyBatis-Plus的Page进行分页查询
            Page<StrategyDecisionDO> page = new Page<>(pageNum, pageSize);
            QueryWrapper<StrategyDecisionDO> queryWrapper = new QueryWrapper<>();
            queryWrapper.eq("model_id", modelId);
            queryWrapper.orderByDesc("created_at");
            Page<StrategyDecisionDO> decisionDOPage = strategyDecisionMapper.selectPage(page, queryWrapper);
            
            List<StrategyDecisionDO> decisionDOList = decisionDOPage.getRecords();
            log.debug("Queried {} strategy decisions for model {} (page {}, pageSize {})", decisionDOList.size(), modelId, pageNum, pageSize);
            
            List<Map<String, Object>> decisions = convertDecisionsToMapList(decisionDOList);
            
            return PageResult.build(decisions, total, pageNum, pageSize);
        } catch (Exception e) {
            log.error("Failed to get strategy decisions by page for model {}: {}", modelId, e.getMessage(), e);
            return PageResult.build(new ArrayList<>(), 0L, pageRequest.getPageNum() != null ? pageRequest.getPageNum() : 1, pageRequest.getPageSize() != null ? pageRequest.getPageSize() : 10);
        }
    }

    @Override
    public List<Map<String, Object>> getDecisionsByModelId(String modelId, Integer limit) {
        try {
            if (limit == null || limit <= 0) {
                limit = 100; // 默认100条
            }
            
            List<StrategyDecisionDO> decisions = strategyDecisionMapper.selectDecisionsByModelId(modelId, limit);
            return convertDecisionsToMapList(decisions);
        } catch (Exception e) {
            log.error("Failed to get strategy decisions for model {}: {}", modelId, e.getMessage(), e);
            return new ArrayList<>();
        }
    }

    /**
     * 将StrategyDecisionDO列表转换为Map列表
     */
    private List<Map<String, Object>> convertDecisionsToMapList(List<StrategyDecisionDO> decisions) {
        List<Map<String, Object>> result = new ArrayList<>();
        for (StrategyDecisionDO decision : decisions) {
            Map<String, Object> decisionMap = new HashMap<>();
            decisionMap.put("id", decision.getId());
            decisionMap.put("modelId", decision.getModelId());
            decisionMap.put("strategyName", decision.getStrategyName());
            decisionMap.put("strategyType", decision.getStrategyType());
            decisionMap.put("signal", decision.getSignal());
            decisionMap.put("symbol", decision.getSymbol());
            decisionMap.put("quantity", decision.getQuantity());
            decisionMap.put("leverage", decision.getLeverage());
            decisionMap.put("price", decision.getPrice());
            decisionMap.put("stopPrice", decision.getStopPrice());
            decisionMap.put("justification", decision.getJustification());
            decisionMap.put("createdAt", decision.getCreatedAt());
            result.add(decisionMap);
        }
        return result;
    }

}

