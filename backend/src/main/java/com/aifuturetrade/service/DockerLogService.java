package com.aifuturetrade.service;

import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.function.Consumer;

/**
 * Docker日志服务接口
 * 用于从Docker容器获取实时日志流
 */
public interface DockerLogService {

    /**
     * 开始流式获取容器日志（使用默认容器名称）
     * 
     * @param sessionId WebSocket会话ID
     * @param logConsumer 日志消费者，用于处理接收到的日志行
     * @return CompletableFuture，用于异步控制
     */
    CompletableFuture<Void> streamLogs(String sessionId, Consumer<String> logConsumer);

    /**
     * 开始流式获取指定容器的日志
     * 
     * @param sessionId WebSocket会话ID
     * @param containerName 容器名称
     * @param logConsumer 日志消费者，用于处理接收到的日志行
     * @return CompletableFuture，用于异步控制
     */
    CompletableFuture<Void> streamLogs(String sessionId, String containerName, Consumer<String> logConsumer);

    /**
     * 停止指定会话的日志流
     * 
     * @param sessionId WebSocket会话ID
     */
    void stopLogStream(String sessionId);

    /**
     * 一次性读取指定容器最近若干行日志（stdout+stderr，非流式），供 HTTP/MCP 查询。
     *
     * @param containerName Docker 容器名称或 ID
     * @param tailLines     行数：默认 1000，范围 1～5000（与 Docker API tail 一致）
     * @return success、containerName、tail、lines（字符串行列表）、lineCount；失败时 success=false 与 error
     */
    Map<String, Object> getContainerLogTail(String containerName, int tailLines);
}
