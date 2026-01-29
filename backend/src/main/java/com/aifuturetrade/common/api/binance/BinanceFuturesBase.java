package com.aifuturetrade.common.api.binance;

import com.binance.connector.client.derivatives_trading_usds_futures.rest.DerivativesTradingUsdsFuturesRestApiUtil;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.api.DerivativesTradingUsdsFuturesRestApi;
import com.binance.connector.client.common.configuration.ClientConfiguration;
import com.binance.connector.client.common.configuration.SignatureConfiguration;
import lombok.extern.slf4j.Slf4j;

import java.util.HashMap;
import java.util.Map;

/**
 * 币安期货客户端基类 - 提供公共的工具方法
 * 
 * 所有币安期货客户端类都继承此基类，共享初始化配置等工具方法。
 * 
 * 参考 Binance 官方示例：
 * https://github.com/binance/binance-connector-java/tree/master/clients/derivatives-trading-usds-futures
 */
@Slf4j
public abstract class BinanceFuturesBase {
    
    protected String quoteAsset;
    protected DerivativesTradingUsdsFuturesRestApi restApi;
    
    /**
     * 格式化交易对符号，添加计价资产后缀
     * 
     * @param baseSymbol 基础交易对符号，如 'BTC'
     * @return 完整交易对符号，如 'BTCUSDT'
     */
    protected String formatSymbol(String baseSymbol) {
        if (baseSymbol == null || baseSymbol.isEmpty()) {
            return baseSymbol;
        }
        String upperSymbol = baseSymbol.toUpperCase();
        if (!upperSymbol.endsWith(quoteAsset)) {
            return upperSymbol + quoteAsset;
        }
        return upperSymbol;
    }
    
    /**
     * 初始化 REST API 客户端
     * 
     * @param apiKey API密钥
     * @param secretKey 密钥（HMAC认证方式）
     * @param privateKeyPath 私钥路径（RSA/ED25519认证方式）
     * @param privateKeyPass 私钥密码（如果私钥文件已加密）
     * @param baseUrl API基础URL
     * @param connectTimeout 连接超时时间（毫秒），默认10000ms
     * @param readTimeout 读取超时时间（毫秒），默认50000ms
     */
    protected void initRestApi(String apiKey, String secretKey, String privateKeyPath, 
                               String privateKeyPass, String baseUrl, 
                               Integer connectTimeout, Integer readTimeout) {
        try {
            // 使用官方工具类获取客户端配置
            ClientConfiguration clientConfiguration = DerivativesTradingUsdsFuturesRestApiUtil.getClientConfiguration();
            
            // 配置签名信息
            SignatureConfiguration signatureConfiguration = new SignatureConfiguration();
            signatureConfiguration.setApiKey(apiKey);
            
            // 根据配置选择认证方式
            if (privateKeyPath != null && !privateKeyPath.isEmpty()) {
                // 使用RSA/ED25519认证方式
                signatureConfiguration.setPrivateKey(privateKeyPath);
                if (privateKeyPass != null && !privateKeyPass.isEmpty()) {
                    signatureConfiguration.setPrivateKeyPass(privateKeyPass);
                }
                log.info("使用RSA/ED25519认证方式，私钥路径: {}", privateKeyPath);
            } else {
                // 使用HMAC认证方式
                signatureConfiguration.setSecretKey(secretKey);
                log.info("使用HMAC认证方式");
            }
            
            // 设置客户端配置
            clientConfiguration.setSignatureConfiguration(signatureConfiguration);
            
            // 设置超时时间（参考SDK文档：binance-connector-java-master/clients/derivatives-trading-usds-futures/docs/rest-api/timeout.md）
            // SDK默认值：connectTimeout=1000ms, readTimeout=5000ms
            // 这里使用配置的值，如果没有配置则使用默认值
            int connectTimeoutMs = (connectTimeout != null && connectTimeout > 0) ? connectTimeout : 10000;
            int readTimeoutMs = (readTimeout != null && readTimeout > 0) ? readTimeout : 50000;
            
            clientConfiguration.setConnectTimeout(connectTimeoutMs);
            clientConfiguration.setReadTimeout(readTimeoutMs);
            
            log.info("Binance API客户端超时配置: connectTimeout={}ms, readTimeout={}ms", connectTimeoutMs, readTimeoutMs);
            
            // 如果提供了baseUrl，设置基础路径
            if (baseUrl != null && !baseUrl.isEmpty()) {
                // 注意：ClientConfiguration 可能没有 setBasePath 方法
                // 具体实现可能需要通过其他方式设置
            }
            
            // 初始化API客户端
            restApi = new DerivativesTradingUsdsFuturesRestApi(clientConfiguration);
            
            log.info("Binance API客户端初始化完成，baseUrl: {}, quoteAsset: {}, connectTimeout: {}ms, readTimeout: {}ms", 
                    baseUrl, quoteAsset, connectTimeoutMs, readTimeoutMs);
        } catch (Exception e) {
            log.error("Binance API客户端初始化失败", e);
            throw new RuntimeException("Binance API客户端初始化失败: " + e.getMessage(), e);
        }
    }
    
    /**
     * 将响应对象转换为Map
     * 
     * @param obj 响应对象
     * @return Map对象
     */
    protected Map<String, Object> toMap(Object obj) {
        if (obj == null) {
            return new HashMap<>();
        }
        
        if (obj instanceof Map) {
            @SuppressWarnings("unchecked")
            Map<String, Object> map = (Map<String, Object>) obj;
            return map;
        }
        
        // 尝试使用反射获取属性
        Map<String, Object> result = new HashMap<>();
        try {
            java.lang.reflect.Field[] fields = obj.getClass().getDeclaredFields();
            for (java.lang.reflect.Field field : fields) {
                field.setAccessible(true);
                Object value = field.get(obj);
                if (value != null) {
                    result.put(field.getName(), value);
                }
            }
        } catch (Exception e) {
            log.warn("转换对象为Map失败: {}", e.getMessage());
        }
        
        return result;
    }
    
    /**
     * 获取 REST API 客户端实例
     * @return DerivativesTradingUsdsFuturesRestApi 实例
     */
    public DerivativesTradingUsdsFuturesRestApi getRestApi() {
        return restApi;
    }
}

