package com.aifuturetrade.common.api.trade;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * Trade服务配置类
 * 从application.yml读取配置信息
 */
@Data
@Component
@ConfigurationProperties(prefix = "trade")
public class TradeServiceConfig {

    /**
     * Trade服务基础URL（默认 http://trade:5000）
     * 可通过环境变量 TRADE_SERVICE_URL 覆盖
     */
    private String baseUrl = "http://trade:5000";

    /**
     * 连接超时时间（毫秒）
     */
    private Integer connectTimeout = 10000;

    /**
     * 读取超时时间（毫秒）
     */
    private Integer readTimeout = 30000;

    /**
     * 重试次数
     */
    private Integer retries = 3;

    /**
     * 重试间隔时间（毫秒）
     */
    private Integer backoff = 200;

}

