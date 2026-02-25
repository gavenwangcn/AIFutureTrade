package com.aifuturetrade.controller.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

/**
 * WebSocket配置
 */
@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {

    private final TradeLogsWebSocketHandler tradeLogsWebSocketHandler;
    private final ModelLogsWebSocketHandler modelLogsWebSocketHandler;

    public WebSocketConfig(TradeLogsWebSocketHandler tradeLogsWebSocketHandler, 
                          ModelLogsWebSocketHandler modelLogsWebSocketHandler) {
        this.tradeLogsWebSocketHandler = tradeLogsWebSocketHandler;
        this.modelLogsWebSocketHandler = modelLogsWebSocketHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        // 交易容器日志端点（保留原有功能）
        registry.addHandler(tradeLogsWebSocketHandler, "/ws/trade-logs")
                .setAllowedOrigins("*");  // 允许所有来源，生产环境应该限制
        
        // 模型容器日志端点（支持buy/sell）
        registry.addHandler(modelLogsWebSocketHandler, "/ws/model-logs")
                .setAllowedOrigins("*");  // 允许所有来源，生产环境应该限制
    }
}

