package com.aifuturetrade.controller.config;

import com.aifuturetrade.service.DockerLogService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.io.IOException;
import java.util.concurrent.CompletableFuture;

/**
 * 交易日志WebSocket处理器
 * 处理前端WebSocket连接，实时推送Docker容器日志
 */
@Component
public class TradeLogsWebSocketHandler extends TextWebSocketHandler {

    private static final Logger logger = LoggerFactory.getLogger(TradeLogsWebSocketHandler.class);

    private final DockerLogService dockerLogService;
    private CompletableFuture<Void> currentLogStream;

    public TradeLogsWebSocketHandler(DockerLogService dockerLogService) {
        this.dockerLogService = dockerLogService;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) throws Exception {
        logger.info("WebSocket连接建立: {}", session.getId());
        
        // 开始流式获取日志
        currentLogStream = dockerLogService.streamLogs(
            session.getId(),
            logLine -> {
                try {
                    if (session.isOpen()) {
                        session.sendMessage(new TextMessage(logLine));
                    }
                } catch (IOException e) {
                    logger.error("发送日志消息失败", e);
                }
            }
        );

        // 处理流完成或错误
        currentLogStream.whenComplete((result, throwable) -> {
            if (throwable != null) {
                logger.error("日志流异常: {}", session.getId(), throwable);
                try {
                    if (session.isOpen()) {
                        session.sendMessage(new TextMessage("错误: " + throwable.getMessage()));
                    }
                } catch (IOException e) {
                    logger.error("发送错误消息失败", e);
                }
            }
        });
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) throws Exception {
        logger.info("WebSocket连接关闭: {}, Status: {}", session.getId(), status);
        
        // 停止日志流
        dockerLogService.stopLogStream(session.getId());
        
        if (currentLogStream != null && !currentLogStream.isDone()) {
            currentLogStream.cancel(true);
        }
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) throws Exception {
        // 处理客户端发送的消息（如果需要）
        String payload = message.getPayload();
        logger.debug("收到客户端消息: {}", payload);
        
        // 可以在这里处理控制命令，比如停止/重启日志流等
        if ("stop".equals(payload)) {
            dockerLogService.stopLogStream(session.getId());
        }
    }

    @Override
    public void handleTransportError(WebSocketSession session, Throwable exception) throws Exception {
        logger.error("WebSocket传输错误: {}", session.getId(), exception);
        dockerLogService.stopLogStream(session.getId());
    }
}

