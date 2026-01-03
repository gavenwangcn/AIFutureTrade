package com.aifuturetrade.asyncservice.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * WebSocket配置属性类
 * 从application.yml中读取WebSocket相关配置
 * 
 * 注意：不使用 @Component，而是通过 @EnableConfigurationProperties 在 AsyncServiceApplication 中启用
 * 这样可以避免重复创建 bean（@Component 和 @EnableConfigurationProperties 会创建两个 bean）
 */
@Data
@ConfigurationProperties(prefix = "async.websocket")
public class WebSocketConfig {
    
    /**
     * 最大文本消息大小（字节）
     */
    private Long maxTextMessageSize = 204800L; 
    
    /**
     * 最大二进制消息大小（字节）
     */
    private Long maxBinaryMessageSize = 80000L; 
    
    /**
     * WebSocket客户端配置
     */
    private Client client = new Client();
    
    /**
     * Jetty特定配置
     */
    private Jetty jetty = new Jetty();
    
    @Data
    public static class Client {
        private int connectTimeout = 10000;
        private int readTimeout = 60000;
        private int writeTimeout = 10000;
        private int bufferSize = 8192;
    }
    
    @Data
    public static class Jetty {
        private boolean compressionEnabled = true;
        private int compressionMinSize = 1024;
        private int compressionMaxInputSize = 1048576; // 1MB
    }
}