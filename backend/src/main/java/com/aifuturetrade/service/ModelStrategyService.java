package com.aifuturetrade.service;

import com.aifuturetrade.service.dto.ModelStrategyDTO;

import java.util.List;

/**
 * 业务逻辑接口：模型关联策略
 */
public interface ModelStrategyService {

    /**
     * 查询所有模型策略关联
     * @return 模型策略关联列表
     */
    List<ModelStrategyDTO> getAllModelStrategies();

    /**
     * 根据ID查询模型策略关联
     * @param id 关联ID
     * @return 模型策略关联
     */
    ModelStrategyDTO getModelStrategyById(String id);

    /**
     * 根据模型ID查询模型策略关联
     * @param modelId 模型ID
     * @return 模型策略关联列表
     */
    List<ModelStrategyDTO> getModelStrategiesByModelId(String modelId);

    /**
     * 根据策略ID查询模型策略关联
     * @param strategyId 策略ID
     * @return 模型策略关联列表
     */
    List<ModelStrategyDTO> getModelStrategiesByStrategyId(String strategyId);

    /**
     * 根据模型ID和类型查询模型策略关联
     * @param modelId 模型ID
     * @param type 策略类型
     * @return 模型策略关联列表
     */
    List<ModelStrategyDTO> getModelStrategiesByModelIdAndType(String modelId, String type);

    /**
     * 添加模型策略关联
     * @param modelStrategyDTO 模型策略关联信息
     * @return 新增的模型策略关联
     */
    ModelStrategyDTO addModelStrategy(ModelStrategyDTO modelStrategyDTO);

    /**
     * 删除模型策略关联
     * @param id 关联ID
     * @return 是否删除成功
     */
    Boolean deleteModelStrategy(String id);

    /**
     * 根据模型ID和策略ID和类型删除模型策略关联
     * @param modelId 模型ID
     * @param strategyId 策略ID
     * @param type 策略类型
     * @return 是否删除成功
     */
    Boolean deleteModelStrategyByModelIdAndStrategyIdAndType(String modelId, String strategyId, String type);

    /**
     * 更新模型策略关联的优先级
     * @param id 关联ID
     * @param priority 优先级
     * @return 更新后的模型策略关联
     */
    ModelStrategyDTO updateModelStrategyPriority(String id, Integer priority);

    /**
     * 批量保存模型策略关联（用于一次性保存多个关联）
     * @param modelId 模型ID
     * @param type 策略类型
     * @param modelStrategies 模型策略关联列表
     * @return 保存结果
     */
    Boolean batchSaveModelStrategies(String modelId, String type, List<ModelStrategyDTO> modelStrategies);

}

