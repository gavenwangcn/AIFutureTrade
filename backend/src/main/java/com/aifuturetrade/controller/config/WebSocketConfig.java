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

    public WebSocketConfig(TradeLogsWebSocketHandler tradeLogsWebSocketHandler) {
        this.tradeLogsWebSocketHandler = tradeLogsWebSocketHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(tradeLogsWebSocketHandler, "/ws/trade-logs")
                .setAllowedOrigins("*");  // 允许所有来源，生产环境应该限制
    }
}

