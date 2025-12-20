package com.aifuturetrade.common.api.trade;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;
import javax.annotation.PostConstruct;
import java.util.HashMap;
import java.util.Map;

/**
 * Trade服务API客户端
 * 用于调用trade服务的交易执行相关接口
 */
@Slf4j
@Component
public class TradeServiceClient {

    private final TradeServiceConfig tradeConfig;
    private RestTemplate restTemplate;
    private ObjectMapper objectMapper;

    public TradeServiceClient(TradeServiceConfig tradeConfig) {
        this.tradeConfig = tradeConfig;
        this.objectMapper = new ObjectMapper();
    }

    @PostConstruct
    public void init() {
        // 创建RestTemplate实例
        // 注意：Spring Boot 2.7.x 需要手动创建 RestTemplate
        // 可以配置超时时间等参数
        org.springframework.http.client.SimpleClientHttpRequestFactory factory = 
            new org.springframework.http.client.SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(tradeConfig.getConnectTimeout());
        factory.setReadTimeout(tradeConfig.getReadTimeout());
        
        this.restTemplate = new RestTemplate(factory);
        
        log.info("Trade服务客户端初始化完成，baseUrl: {}", tradeConfig.getBaseUrl());
    }

    /**
     * 手动执行一次买入交易周期
     * @param modelId 模型ID（UUID格式）
     * @return 买入交易执行结果
     */
    public Map<String, Object> executeBuyTrading(String modelId) {
        String url = tradeConfig.getBaseUrl() + "/api/models/" + modelId + "/execute-buy";
        return executePostRequest(url, "执行买入交易");
    }

    /**
     * 手动执行一次卖出交易周期
     * @param modelId 模型ID（UUID格式）
     * @return 卖出交易执行结果
     */
    public Map<String, Object> executeSellTrading(String modelId) {
        String url = tradeConfig.getBaseUrl() + "/api/models/" + modelId + "/execute-sell";
        return executePostRequest(url, "执行卖出交易");
    }

    /**
     * 禁用模型的自动买入功能
     * @param modelId 模型ID（UUID格式）
     * @return 更新后的自动买入状态
     */
    public Map<String, Object> disableBuyTrading(String modelId) {
        String url = tradeConfig.getBaseUrl() + "/api/models/" + modelId + "/disable-buy";
        return executePostRequest(url, "禁用自动买入");
    }

    /**
     * 禁用模型的自动卖出功能
     * @param modelId 模型ID（UUID格式）
     * @return 更新后的自动卖出状态
     */
    public Map<String, Object> disableSellTrading(String modelId) {
        String url = tradeConfig.getBaseUrl() + "/api/models/" + modelId + "/disable-sell";
        return executePostRequest(url, "禁用自动卖出");
    }

    /**
     * 执行POST请求
     * @param url 请求URL
     * @param operation 操作描述（用于日志）
     * @return 响应结果
     */
    private Map<String, Object> executePostRequest(String url, String operation) {
        try {
            log.info("[TradeServiceClient] {} - URL: {}", operation, url);
            
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            HttpEntity<String> entity = new HttpEntity<>(headers);
            
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
                    log.info("[TradeServiceClient] {} 成功: {}", operation, result);
                    return result;
                } else {
                    log.warn("[TradeServiceClient] {} 响应体为空", operation);
                    return createErrorResponse("响应体为空");
                }
            } else {
                log.error("[TradeServiceClient] {} 失败，状态码: {}", operation, response.getStatusCode());
                return createErrorResponse("请求失败，状态码: " + response.getStatusCode());
            }
        } catch (RestClientException e) {
            log.error("[TradeServiceClient] {} 请求异常: {}", operation, e.getMessage(), e);
            return createErrorResponse("请求异常: " + e.getMessage());
        } catch (Exception e) {
            log.error("[TradeServiceClient] {} 处理异常: {}", operation, e.getMessage(), e);
            return createErrorResponse("处理异常: " + e.getMessage());
        }
    }

    /**
     * 创建错误响应
     * @param errorMessage 错误信息
     * @return 错误响应Map
     */
    private Map<String, Object> createErrorResponse(String errorMessage) {
        Map<String, Object> errorResponse = new HashMap<>();
        errorResponse.put("error", errorMessage);
        errorResponse.put("success", false);
        return errorResponse;
    }
}

