package com.aifuturetrade.service.impl;

import com.aifuturetrade.common.api.trade.TradeServiceConfig;
import com.aifuturetrade.service.StrategyCodeTesterService;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

import javax.annotation.PostConstruct;
import java.util.HashMap;
import java.util.Map;

/**
 * 策略代码测试服务实现类
 * 通过调用Trade服务的HTTP API来验证策略代码
 */
@Slf4j
@Service
public class StrategyCodeTesterServiceImpl implements StrategyCodeTesterService {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private final TradeServiceConfig tradeConfig;
    private RestTemplate restTemplate;

    public StrategyCodeTesterServiceImpl(TradeServiceConfig tradeConfig) {
        this.tradeConfig = tradeConfig;
    }

    @PostConstruct
    public void init() {
        // 创建RestTemplate实例，配置超时时间
        org.springframework.http.client.SimpleClientHttpRequestFactory factory = 
            new org.springframework.http.client.SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(tradeConfig.getConnectTimeout());
        factory.setReadTimeout(tradeConfig.getReadTimeout());
        
        this.restTemplate = new RestTemplate(factory);
        
        log.info("策略代码测试服务初始化完成，Trade服务URL: {}", tradeConfig.getBaseUrl());
    }

    @Override
    public Map<String, Object> testStrategyCode(String strategyCode, String strategyType, String strategyName) {
        try {
            String url = tradeConfig.getBaseUrl() + "/api/strategy/validate-code";
            
            log.info("[StrategyCodeTester] 验证策略代码 - URL: {}, 类型: {}, 名称: {}", url, strategyType, strategyName);
            
            // 构建请求体
            Map<String, Object> requestBody = new HashMap<>();
            requestBody.put("strategy_code", strategyCode);
            requestBody.put("strategy_type", strategyType);
            requestBody.put("strategy_name", strategyName != null ? strategyName : "测试策略");
            
            // 设置请求头
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            
            // 将请求体转换为JSON字符串
            String requestBodyJson = objectMapper.writeValueAsString(requestBody);
            HttpEntity<String> entity = new HttpEntity<>(requestBodyJson, headers);
            
            // 发送POST请求
            ResponseEntity<String> response = restTemplate.exchange(
                url,
                HttpMethod.POST,
                entity,
                String.class
            );
            
            if (response.getStatusCode().is2xxSuccessful()) {
                String responseBody = response.getBody();
                if (responseBody != null && !responseBody.isEmpty()) {
                    // 将JSON字符串转换为Map
                    Map<String, Object> result = objectMapper.readValue(
                        responseBody,
                        new TypeReference<Map<String, Object>>() {}
                    );
                    
                    log.info("策略代码测试完成: {}, 通过: {}", strategyName, result.get("passed"));
                    return result;
                } else {
                    log.error("Trade服务返回空响应");
                    return createErrorResult("Trade服务返回空响应");
                }
            } else {
                log.error("Trade服务返回错误状态码: {}", response.getStatusCode());
                // 尝试解析错误响应
                String responseBody = response.getBody();
                if (responseBody != null && !responseBody.isEmpty()) {
                    try {
                        Map<String, Object> errorResult = objectMapper.readValue(
                            responseBody,
                            new TypeReference<Map<String, Object>>() {}
                        );
                        return errorResult;
                    } catch (Exception e) {
                        log.warn("无法解析错误响应: {}", e.getMessage());
                    }
                }
                return createErrorResult("Trade服务返回错误状态码: " + response.getStatusCode());
            }
            
        } catch (RestClientException e) {
            log.error("调用Trade服务API时发生异常: {}", e.getMessage(), e);
            return createErrorResult("调用Trade服务API失败: " + e.getMessage());
        } catch (Exception e) {
            log.error("测试策略代码时发生异常: {}", e.getMessage(), e);
            return createErrorResult("测试执行异常: " + e.getMessage());
        }
    }
    
    /**
     * 创建错误结果
     */
    private Map<String, Object> createErrorResult(String errorMessage) {
        Map<String, Object> errorResult = new HashMap<>();
        errorResult.put("passed", false);
        errorResult.put("errors", java.util.Arrays.asList(errorMessage));
        errorResult.put("warnings", java.util.Collections.emptyList());
        errorResult.put("test_results", new HashMap<>());
        return errorResult;
    }

    @Override
    public boolean validateStrategyCode(String strategyCode, String strategyType, String strategyName) {
        Map<String, Object> testResult = testStrategyCode(strategyCode, strategyType, strategyName);
        
        Boolean passed = (Boolean) testResult.get("passed");
        if (passed == null || !passed) {
            @SuppressWarnings("unchecked")
            java.util.List<String> errors = (java.util.List<String>) testResult.get("errors");
            String errorMessage = "策略代码验证失败";
            if (errors != null && !errors.isEmpty()) {
                errorMessage += ": " + String.join("; ", errors);
            }
            throw new RuntimeException(errorMessage);
        }
        
        return true;
    }
    
}

