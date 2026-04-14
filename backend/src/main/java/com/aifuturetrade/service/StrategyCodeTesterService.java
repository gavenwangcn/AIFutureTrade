package com.aifuturetrade.service;

import java.util.Map;

/**
 * 策略代码测试服务接口
 * 用于验证AI生成的策略代码是否符合要求
 */
public interface StrategyCodeTesterService {
    
    /**
     * 测试策略代码
     * @param strategyCode 策略代码字符串
     * @param strategyType 策略类型（buy/sell）
     * @param strategyName 策略名称（用于日志）
     * @return 测试结果，包含passed、errors、warnings等字段
     */
    Map<String, Object> testStrategyCode(String strategyCode, String strategyType, String strategyName);
    
    /**
     * 验证策略代码是否通过测试
     * @param strategyCode 策略代码字符串
     * @param strategyType 策略类型（buy/sell）
     * @param strategyName 策略名称
     * @return 是否通过测试
     * @throws RuntimeException 如果测试失败，抛出异常，包含错误信息
     */
    boolean validateStrategyCode(String strategyCode, String strategyType, String strategyName);

    /**
     * 测试盯盘策略代码（需真实合约符号，调用 Trade 服务 validate-look-code）
     */
    Map<String, Object> testLookStrategyCode(String strategyCode, String strategyName, String symbol);

    /**
     * 校验盯盘策略代码是否通过测试
     */
    boolean validateLookStrategyCode(String strategyCode, String strategyName, String symbol);
}

