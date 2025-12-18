package com.aifuturetrade.service;

import com.aifuturetrade.service.dto.ModelDTO;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.common.util.PageRequest;

import java.util.List;
import java.util.Map;

/**
 * 业务逻辑接口：交易模型
 */
public interface ModelService {

    /**
     * 查询所有交易模型
     * @return 交易模型列表
     */
    List<ModelDTO> getAllModels();

    /**
     * 根据ID查询交易模型
     * @param id 模型ID
     * @return 交易模型
     */
    ModelDTO getModelById(Integer id);

    /**
     * 添加交易模型
     * @param modelDTO 交易模型信息
     * @return 新增的交易模型
     */
    ModelDTO addModel(ModelDTO modelDTO);

    /**
     * 更新交易模型
     * @param modelDTO 交易模型信息
     * @return 更新后的交易模型
     */
    ModelDTO updateModel(ModelDTO modelDTO);

    /**
     * 删除交易模型
     * @param id 模型ID
     * @return 是否删除成功
     */
    Boolean deleteModel(Integer id);

    /**
     * 分页查询交易模型
     * @param pageRequest 分页请求
     * @return 分页查询结果
     */
    PageResult<ModelDTO> getModelsByPage(PageRequest pageRequest);

    /**
     * 检查模型是否启用自动买入
     * @param modelId 模型ID
     * @return 1：启用，0：未启用
     */
    Boolean isModelAutoBuyEnabled(Integer modelId);

    /**
     * 检查模型是否启用自动卖出
     * @param modelId 模型ID
     * @return 1：启用，0：未启用
     */
    Boolean isModelAutoSellEnabled(Integer modelId);

    /**
     * 获取模型的投资组合数据
     * @param modelId 模型ID
     * @return 投资组合数据
     */
    Map<String, Object> getPortfolio(Integer modelId);

    /**
     * 获取模型的持仓合约symbol列表
     * @param modelId 模型ID
     * @return 持仓合约symbol列表
     */
    Map<String, Object> getModelPortfolioSymbols(Integer modelId);

    /**
     * 获取模型的交易历史记录
     * @param modelId 模型ID
     * @param limit 限制数量
     * @return 交易历史记录
     */
    List<Map<String, Object>> getTrades(Integer modelId, Integer limit);

    /**
     * 获取模型的对话历史记录
     * @param modelId 模型ID
     * @param limit 限制数量
     * @return 对话历史记录
     */
    List<Map<String, Object>> getConversations(Integer modelId, Integer limit);

    /**
     * 获取模型的LLM API错误记录
     * @param modelId 模型ID
     * @param limit 限制数量
     * @return LLM API错误记录
     */
    List<Map<String, Object>> getLlmApiErrors(Integer modelId, Integer limit);

    /**
     * 获取模型的提示词配置
     * @param modelId 模型ID
     * @return 提示词配置
     */
    Map<String, Object> getModelPrompts(Integer modelId);

    /**
     * 更新模型的提示词配置
     * @param modelId 模型ID
     * @param buyPrompt 买入提示词
     * @param sellPrompt 卖出提示词
     * @return 更新结果
     */
    Map<String, Object> updateModelPrompts(Integer modelId, String buyPrompt, String sellPrompt);

    /**
     * 更新模型的批次配置
     * @param modelId 模型ID
     * @param batchConfig 批次配置
     * @return 更新结果
     */
    Map<String, Object> updateModelBatchConfig(Integer modelId, Map<String, Object> batchConfig);

    /**
     * 更新模型的最大持仓数量
     * @param modelId 模型ID
     * @param maxPositions 最大持仓数量
     * @return 更新结果
     */
    Map<String, Object> updateModelMaxPositions(Integer modelId, Integer maxPositions);

    /**
     * 更新模型的杠杆倍数
     * @param modelId 模型ID
     * @param leverage 杠杆倍数
     * @return 更新结果
     */
    Map<String, Object> updateModelLeverage(Integer modelId, Integer leverage);

    /**
     * 更新模型的API提供方和模型名称
     * @param modelId 模型ID
     * @param providerId 新的API提供方ID
     * @param modelName 新的模型名称
     * @return 更新结果
     */
    Map<String, Object> updateModelProvider(Integer modelId, Integer providerId, String modelName);

    /**
     * 设置模型的自动交易开关
     * @param modelId 模型ID
     * @param autoBuyEnabled 是否启用自动买入
     * @param autoSellEnabled 是否启用自动卖出
     * @return 更新结果
     */
    Map<String, Object> setModelAutoTrading(Integer modelId, Boolean autoBuyEnabled, Boolean autoSellEnabled);

    /**
     * 获取聚合投资组合数据（所有模型）
     * @return 聚合投资组合数据
     */
    Map<String, Object> getAggregatedPortfolio();

}