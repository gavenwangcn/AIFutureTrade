package com.aifuturetrade.asyncservice.api.binance;

import com.binance.connector.client.derivatives_trading_usds_futures.rest.DerivativesTradingUsdsFuturesRestApiUtil;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.api.DerivativesTradingUsdsFuturesRestApi;
import com.binance.connector.client.common.configuration.ClientConfiguration;
import com.binance.connector.client.common.configuration.SignatureConfiguration;
import lombok.extern.slf4j.Slf4j;

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
     */
    protected void initRestApi(String apiKey, String secretKey, String privateKeyPath, 
                               String privateKeyPass, String baseUrl) {
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
            
            // 如果提供了baseUrl，设置基础路径
            if (baseUrl != null && !baseUrl.isEmpty()) {
                // 注意：ClientConfiguration 可能没有 setBasePath 方法
                // 具体实现可能需要通过其他方式设置
            }
            
            // 初始化API客户端
            restApi = new DerivativesTradingUsdsFuturesRestApi(clientConfiguration);
            
            log.info("Binance API客户端初始化完成，baseUrl: {}, quoteAsset: {}", baseUrl, quoteAsset);
        } catch (Exception e) {
            log.error("Binance API客户端初始化失败", e);
            throw new RuntimeException("Binance API客户端初始化失败: " + e.getMessage(), e);
        }
    }
    
    /**
     * 获取 REST API 客户端实例
     * @return DerivativesTradingUsdsFuturesRestApi 实例
     */
    public DerivativesTradingUsdsFuturesRestApi getRestApi() {
        return restApi;
    }
}
