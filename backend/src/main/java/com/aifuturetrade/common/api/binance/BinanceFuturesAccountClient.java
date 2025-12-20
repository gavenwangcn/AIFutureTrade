package com.aifuturetrade.common.api.binance;

import com.binance.connector.client.common.ApiResponse;
import lombok.extern.slf4j.Slf4j;

import java.util.Map;

/**
 * 币安期货账户客户端 - 专注于账户功能的客户端
 * 
 * 提供获取账户信息、账户资产等功能，支持传入不同的api_key和api_secret进行操作。
 * 主要用于账户管理和资产查询。
 * 
 * 参考 Binance 官方示例：
 * https://github.com/binance/binance-connector-java/tree/master/clients/derivatives-trading-usds-futures
 */
@Slf4j
public class BinanceFuturesAccountClient extends BinanceFuturesBase {
    
    /**
     * 构造函数，初始化币安期货账户客户端
     * 
     * @param apiKey 币安API密钥
     * @param apiSecret 币安API密钥
     * @param quoteAsset 计价资产，默认为USDT
     * @param baseUrl 自定义REST API基础路径（可选）
     * @param testnet 是否使用测试网络，默认False
     */
    public BinanceFuturesAccountClient(String apiKey, String apiSecret, String quoteAsset, 
                                       String baseUrl, Boolean testnet) {
        this.quoteAsset = (quoteAsset != null ? quoteAsset : "USDT").toUpperCase();
        initRestApi(apiKey, apiSecret, null, null, baseUrl);
    }
    
    /**
     * 构造函数，使用默认配置
     */
    public BinanceFuturesAccountClient(String apiKey, String apiSecret) {
        this(apiKey, apiSecret, "USDT", null, false);
    }
    
    /**
     * 获取账户信息
     * 
     * 参考 API: GET /fapi/v3/account
     * https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V3
     * 
     * @return 账户信息的Map对象
     */
    public Map<String, Object> getAccount() {
        try {
            log.info("[BinanceFuturesAccountClient] 开始获取账户信息");
            // 调用SDK API获取账户信息 - 使用null作为recvWindow参数（可选）
            ApiResponse<?> response = restApi.accountInformationV3((Long) null);
            Object data = getResponseData(response);
            Map<String, Object> accountInfo = toMap(data);
            log.info("[BinanceFuturesAccountClient] 账户信息获取成功");
            return accountInfo;
        } catch (Exception e) {
            log.error("[BinanceFuturesAccountClient] 获取账户信息失败: {}", e.getMessage(), e);
            throw new RuntimeException("获取账户信息失败: " + e.getMessage(), e);
        }
    }
    
    /**
     * 获取账户信息（V2版本）
     * 
     * 参考 API: GET /fapi/v2/account
     * https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V2
     * 
     * @return 账户信息的Map对象
     */
    public Map<String, Object> getAccountV2() {
        try {
            log.info("[BinanceFuturesAccountClient] 开始获取账户信息（V2）");
            // 调用SDK API获取账户信息V2 - 使用null作为recvWindow参数（可选）
            ApiResponse<?> response = restApi.accountInformationV2((Long) null);
            Object data = getResponseData(response);
            Map<String, Object> accountInfo = toMap(data);
            log.info("[BinanceFuturesAccountClient] 账户信息获取成功（V2）");
            return accountInfo;
        } catch (Exception e) {
            log.error("[BinanceFuturesAccountClient] 获取账户信息失败（V2）: {}", e.getMessage(), e);
            throw new RuntimeException("获取账户信息失败（V2）: " + e.getMessage(), e);
        }
    }
    
    /**
     * 获取账户余额
     * 
     * 参考 API: GET /fapi/v2/balance
     * https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V2
     * 
     * @return 账户余额列表
     */
    @SuppressWarnings("unchecked")
    public java.util.List<Map<String, Object>> getBalance() {
        try {
            log.info("[BinanceFuturesAccountClient] 开始获取账户余额");
            // 调用SDK API获取账户余额 - 使用null作为recvWindow参数（可选）
            ApiResponse<?> response = restApi.futuresAccountBalanceV2((Long) null);
            Object data = getResponseData(response);
            
            if (data instanceof java.util.List) {
                java.util.List<Object> balanceList = (java.util.List<Object>) data;
                java.util.List<Map<String, Object>> result = new java.util.ArrayList<>();
                for (Object item : balanceList) {
                    result.add(toMap(item));
                }
                log.info("[BinanceFuturesAccountClient] 账户余额获取成功，共 {} 条记录", result.size());
                return result;
            } else {
                java.util.List<Map<String, Object>> result = new java.util.ArrayList<>();
                result.add(toMap(data));
                return result;
            }
        } catch (Exception e) {
            log.error("[BinanceFuturesAccountClient] 获取账户余额失败: {}", e.getMessage(), e);
            throw new RuntimeException("获取账户余额失败: " + e.getMessage(), e);
        }
    }
    
    /**
     * 从ApiResponse中获取数据
     */
    private Object getResponseData(ApiResponse<?> response) {
        if (response == null) {
            return null;
        }
        try {
            // 尝试使用反射获取data字段或方法
            try {
                java.lang.reflect.Method dataMethod = response.getClass().getMethod("data");
                return dataMethod.invoke(response);
            } catch (NoSuchMethodException e) {
                try {
                    java.lang.reflect.Method getDataMethod = response.getClass().getMethod("getData");
                    return getDataMethod.invoke(response);
                } catch (NoSuchMethodException e2) {
                    // 尝试直接访问data字段
                    try {
                        java.lang.reflect.Field dataField = response.getClass().getField("data");
                        return dataField.get(response);
                    } catch (NoSuchFieldException e3) {
                        // 如果都失败，返回response本身
                        return response;
                    }
                }
            }
        } catch (Exception e) {
            log.warn("获取响应数据失败: {}", e.getMessage());
            return response;
        }
    }
}

