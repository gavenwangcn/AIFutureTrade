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
import java.net.URI;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 模型日志WebSocket处理器
 * 处理前端WebSocket连接，实时推送模型容器（buy/sell）日志
 * 支持通过URL参数传递modelId和类型（buy/sell）
 */
@Component
public class ModelLogsWebSocketHandler extends TextWebSocketHandler {

    private static final Logger logger = LoggerFactory.getLogger(ModelLogsWebSocketHandler.class);

    private final DockerLogService dockerLogService;
    private final ConcurrentHashMap<String, CompletableFuture<Void>> activeStreams = new ConcurrentHashMap<>();

    public ModelLogsWebSocketHandler(DockerLogService dockerLogService) {
        this.dockerLogService = dockerLogService;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) throws Exception {
        logger.info("模型日志WebSocket连接建立: {}", session.getId());
        
        // 从URL中解析参数
        URI uri = session.getUri();
        String query = uri != null ? uri.getQuery() : null;
        String modelId = null;
        String type = null; // buy or sell
        
        if (query != null) {
            String[] params = query.split("&");
            for (String param : params) {
                String[] keyValue = param.split("=");
                if (keyValue.length == 2) {
                    String key = keyValue[0];
                    String value = keyValue[1];
                    if ("modelId".equals(key)) {
                        modelId = value;
                    } else if ("type".equals(key)) {
                        type = value;
                    }
                }
            }
        }
        
        // 验证参数
        if (modelId == null || modelId.trim().isEmpty()) {
            logger.error("缺少modelId参数: {}", session.getId());
            session.sendMessage(new TextMessage("错误: 缺少modelId参数"));
            session.close();
            return;
        }
        
        if (type == null || (!"buy".equals(type) && !"sell".equals(type))) {
            logger.error("缺少或无效的type参数（必须是buy或sell）: {}", session.getId());
            session.sendMessage(new TextMessage("错误: 缺少或无效的type参数（必须是buy或sell）"));
            session.close();
            return;
        }
        
        // 构建容器名称：buy-{modelId} 或 sell-{modelId}
        String containerName = type + "-" + modelId;
        logger.info("开始获取模型容器日志: containerName={}, modelId={}, type={}", containerName, modelId, type);
        
        // 开始流式获取日志
        CompletableFuture<Void> logStream = dockerLogService.streamLogs(
            session.getId(),
            containerName,
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
        
        // 保存流引用
        activeStreams.put(session.getId(), logStream);

        // 处理流完成或错误
        logStream.whenComplete((result, throwable) -> {
            activeStreams.remove(session.getId());
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
        logger.info("模型日志WebSocket连接关闭: {}, Status: {}", session.getId(), status);
        
        // 停止日志流
        dockerLogService.stopLogStream(session.getId());
        
        CompletableFuture<Void> logStream = activeStreams.remove(session.getId());
        if (logStream != null && !logStream.isDone()) {
            logStream.cancel(true);
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
        activeStreams.remove(session.getId());
    }
}

