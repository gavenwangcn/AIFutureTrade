package com.aifuturetrade.service;

import java.util.concurrent.CompletableFuture;
import java.util.function.Consumer;

/**
 * Docker日志服务接口
 * 用于从Docker容器获取实时日志流
 */
public interface DockerLogService {

    /**
     * 开始流式获取容器日志
     * 
     * @param sessionId WebSocket会话ID
     * @param logConsumer 日志消费者，用于处理接收到的日志行
     * @return CompletableFuture，用于异步控制
     */
    CompletableFuture<Void> streamLogs(String sessionId, Consumer<String> logConsumer);

    /**
     * 停止指定会话的日志流
     * 
     * @param sessionId WebSocket会话ID
     */
    void stopLogStream(String sessionId);
}
