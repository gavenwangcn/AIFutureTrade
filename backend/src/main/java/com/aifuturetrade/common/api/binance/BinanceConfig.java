package com.aifuturetrade.common.api.binance;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * Binance API配置类
 * 从application.yml读取配置信息
 */
@Data
@Component
@ConfigurationProperties(prefix = "binance")
public class BinanceConfig {

    /**
     * API密钥
     */
    private String apiKey;

    /**
     * API密钥密码（HMAC认证方式）
     */
    private String secretKey;

    /**
     * 私钥文件路径（RSA/ED25519认证方式）
     */
    private String privateKeyPath;

    /**
     * 私钥密码（如果私钥文件已加密）
     */
    private String privateKeyPass;

    /**
     * API基础URL
     */
    private String baseUrl;

    /**
     * 是否使用测试网
     */
    private Boolean testnet;

    /**
     * 报价资产（如USDT）
     */
    private String quoteAsset;

    /**
     * 连接超时时间（毫秒）
     */
    private Integer connectTimeout = 10000;

    /**
     * 读取超时时间（毫秒）
     */
    private Integer readTimeout = 50000;

    /**
     * 重试次数
     */
    private Integer retries = 3;

    /**
     * 重试间隔时间（毫秒）
     */
    private Integer backoff = 200;

    /**
     * 是否启用压缩
     */
    private Boolean compression = true;

}