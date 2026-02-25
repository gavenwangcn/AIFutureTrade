package com.aifuturetrade.service;

import java.util.List;

/**
 * 业务逻辑接口：AI提供方服务
 * 用于调用AI生成策略代码和获取模型列表
 */
public interface AiProviderService {

    /**
     * 从提供方API获取可用的模型列表
     * @param providerId 提供方ID
     * @return 可用模型列表
     */
    List<String> fetchModels(String providerId);

    /**
     * 从提供方API获取可用的模型列表（使用API URL和Key）
     * @param apiUrl API地址
     * @param apiKey API密钥
     * @param providerType 提供方类型
     * @return 可用模型列表
     */
    List<String> fetchModels(String apiUrl, String apiKey, String providerType);

    /**
     * 生成策略代码
     * @param providerId 提供方ID
     * @param modelName 模型名称
     * @param strategyContext 策略内容
     * @param strategyType 策略类型（buy/sell）
     * @return 生成的策略代码
     */
    String generateStrategyCode(String providerId, String modelName, String strategyContext, String strategyType);

    /**
     * 调用AI API生成内容
     * @param providerId 提供方ID
     * @param modelName 模型名称
     * @param prompt 提示词
     * @return AI返回的内容
     */
    String callAiApi(String providerId, String modelName, String prompt);
}

