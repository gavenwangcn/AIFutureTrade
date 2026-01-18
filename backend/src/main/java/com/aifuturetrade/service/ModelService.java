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
     * @param id 模型ID（UUID格式）
     * @return 交易模型
     */
    ModelDTO getModelById(String id);

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
     * @param id 模型ID（UUID格式）
     * @return 是否删除成功
     */
    Boolean deleteModel(String id);

    /**
     * 分页查询交易模型
     * @param pageRequest 分页请求
     * @return 分页查询结果
     */
    PageResult<ModelDTO> getModelsByPage(PageRequest pageRequest);

    /**
     * 检查模型是否启用自动买入
     * @param modelId 模型ID（UUID格式）
     * @return 1：启用，0：未启用
     */
    Boolean isModelAutoBuyEnabled(String modelId);

    /**
     * 检查模型是否启用自动卖出
     * @param modelId 模型ID（UUID格式）
     * @return 1：启用，0：未启用
     */
    Boolean isModelAutoSellEnabled(String modelId);

    /**
     * 获取模型的投资组合数据
     * @param modelId 模型ID（UUID格式）
     * @return 投资组合数据
     */
    Map<String, Object> getPortfolio(String modelId);

    /**
     * 获取模型的持仓合约symbol列表
     * @param modelId 模型ID（UUID格式）
     * @return 持仓合约symbol列表
     */
    Map<String, Object> getModelPortfolioSymbols(String modelId);

    /**
     * 获取模型的交易历史记录（分页）
     * @param modelId 模型ID（UUID格式）
     * @param pageRequest 分页请求参数
     * @return 分页的交易历史记录
     */
    PageResult<Map<String, Object>> getTradesByPage(String modelId, PageRequest pageRequest);
    
    /**
     * 获取模型的交易历史记录（保留旧方法以兼容）
     * @param modelId 模型ID（UUID格式）
     * @param limit 限制数量
     * @return 交易历史记录
     */
    List<Map<String, Object>> getTrades(String modelId, Integer limit);

    /**
     * 获取模型的对话历史记录
     * @param modelId 模型ID（UUID格式）
     * @param limit 限制数量
     * @return 对话历史记录
     */
    List<Map<String, Object>> getConversations(String modelId, Integer limit);

    /**
     * 获取模型的提示词配置
     * @param modelId 模型ID（UUID格式）
     * @return 提示词配置
     */
    Map<String, Object> getModelPrompts(String modelId);

    /**
     * 更新模型的提示词配置
     * @param modelId 模型ID（UUID格式）
     * @param buyPrompt 买入提示词
     * @param sellPrompt 卖出提示词
     * @return 更新结果
     */
    Map<String, Object> updateModelPrompts(String modelId, String buyPrompt, String sellPrompt);

    /**
     * 更新模型的批次配置
     * @param modelId 模型ID（UUID格式）
     * @param batchConfig 批次配置
     * @return 更新结果
     */
    Map<String, Object> updateModelBatchConfig(String modelId, Map<String, Object> batchConfig);

    /**
     * 更新模型的最大持仓数量
     * @param modelId 模型ID（UUID格式）
     * @param maxPositions 最大持仓数量
     * @return 更新结果
     */
    Map<String, Object> updateModelMaxPositions(String modelId, Integer maxPositions);

    /**
     * 更新模型的杠杆倍数
     * @param modelId 模型ID（UUID格式）
     * @param leverage 杠杆倍数
     * @return 更新结果
     */
    Map<String, Object> updateModelLeverage(String modelId, Integer leverage);

    /**
     * 更新模型的自动平仓百分比
     * @param modelId 模型ID（UUID格式）
     * @param autoClosePercent 自动平仓百分比（0-100，null表示不启用）
     * @return 更新结果
     */
    Map<String, Object> updateModelAutoClosePercent(String modelId, Double autoClosePercent);

    /**
     * 更新模型的每日成交量过滤阈值（千万单位）
     * @param modelId 模型ID（UUID格式）
     * @param baseVolume 每日成交量过滤阈值（千万单位，null表示不过滤）
     * @return 更新结果
     */
    Map<String, Object> updateModelBaseVolume(String modelId, Double baseVolume);

    /**
     * 更新模型的API提供方和模型名称
     * @param modelId 模型ID（UUID格式）
     * @param providerId 新的API提供方ID（UUID格式）
     * @param modelName 新的模型名称
     * @return 更新结果
     */
    Map<String, Object> updateModelProvider(String modelId, String providerId, String modelName);

    /**
     * 设置模型的自动交易开关
     * @param modelId 模型ID（UUID格式）
     * @param autoBuyEnabled 是否启用自动买入
     * @param autoSellEnabled 是否启用自动卖出
     * @return 更新结果
     */
    Map<String, Object> setModelAutoTrading(String modelId, Boolean autoBuyEnabled, Boolean autoSellEnabled);

    /**
     * 获取聚合投资组合数据（所有模型）
     * @return 聚合投资组合数据
     */
    Map<String, Object> getAggregatedPortfolio();

    /**
     * 手动执行一次交易周期（同时执行买入和卖出）
     * @param modelId 模型ID（UUID格式）
     * @return 交易执行结果
     */
    Map<String, Object> executeTrading(String modelId);

    /**
     * 手动执行一次买入交易周期
     * @param modelId 模型ID（UUID格式）
     * @return 买入交易执行结果
     */
    Map<String, Object> executeBuyTrading(String modelId);

    /**
     * 手动执行一次卖出交易周期
     * @param modelId 模型ID（UUID格式）
     * @return 卖出交易执行结果
     */
    Map<String, Object> executeSellTrading(String modelId);

    /**
     * 禁用模型的自动买入功能
     * @param modelId 模型ID（UUID格式）
     * @return 更新后的自动买入状态
     */
    Map<String, Object> disableBuyTrading(String modelId);

    /**
     * 禁用模型的自动卖出功能
     * @param modelId 模型ID（UUID格式）
     * @return 更新后的自动卖出状态
     */
    Map<String, Object> disableSellTrading(String modelId);

}