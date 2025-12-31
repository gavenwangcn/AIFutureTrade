package com.aifuturetrade.service.impl;

import com.aifuturetrade.service.DockerLogService;
import com.github.dockerjava.api.DockerClient;
import com.github.dockerjava.api.async.ResultCallback;
import com.github.dockerjava.api.model.Frame;
import com.github.dockerjava.core.DefaultDockerClientConfig;
import com.github.dockerjava.core.DockerClientImpl;
import com.github.dockerjava.httpclient5.ApacheDockerHttpClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.io.Closeable;
import java.io.IOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Consumer;

/**
 * Docker日志服务实现类
 * 用于从Docker容器获取实时日志流
 */
@Service
public class DockerLogServiceImpl implements DockerLogService {

    private static final Logger logger = LoggerFactory.getLogger(DockerLogServiceImpl.class);

    @Value("${docker.host:unix:///var/run/docker.sock}")
    private String dockerHost;

    @Value("${docker.container-name:aifuturetrade-trade}")
    private String containerName;

    private DockerClient dockerClient;
    private ExecutorService executorService;
    private final ConcurrentHashMap<String, Closeable> activeStreams = new ConcurrentHashMap<>();

    @PostConstruct
    public void init() {
        try {
            // 创建Docker客户端配置
            DefaultDockerClientConfig.Builder configBuilder = DefaultDockerClientConfig.createDefaultConfigBuilder();
            
            // 检测操作系统类型
            String osName = System.getProperty("os.name", "").toLowerCase();
            boolean isWindows = osName.contains("win");
            
            // 根据dockerHost配置设置Docker URI
            String finalDockerHost = dockerHost;
            if (dockerHost == null || dockerHost.trim().isEmpty()) {
                // 根据操作系统选择默认连接方式
                if (isWindows) {
                    // Windows系统使用TCP连接
                    finalDockerHost = "tcp://localhost:2375";
                    logger.info("检测到Windows系统，使用默认TCP连接: {}", finalDockerHost);
                } else {
                    // Linux/Mac系统使用Unix socket
                    finalDockerHost = "unix:///var/run/docker.sock";
                    logger.info("检测到Linux/Mac系统，使用默认Unix socket: {}", finalDockerHost);
                }
            } else {
                // 规范化Unix socket路径
                if (dockerHost.startsWith("unix://")) {
                    if (isWindows) {
                        logger.warn("Windows系统不支持Unix socket，请使用TCP连接（如: tcp://localhost:2375）");
                        // Windows上强制使用TCP
                        finalDockerHost = "tcp://localhost:2375";
                    } else {
                        // 确保Unix socket格式正确：unix:///path/to/socket（三个斜杠）
                        String path = dockerHost.substring(7); // 移除 "unix://"
                        if (!path.startsWith("/")) {
                            // 如果路径不是以/开头，添加/
                            path = "/" + path;
                        }
                        finalDockerHost = "unix://" + path;
                        logger.info("使用Unix socket连接: {}", finalDockerHost);
                    }
                } else if (dockerHost.startsWith("tcp://") || 
                          dockerHost.startsWith("http://") || 
                          dockerHost.startsWith("https://")) {
                    // TCP/HTTP连接
                    finalDockerHost = dockerHost;
                    logger.info("使用TCP/HTTP连接: {}", finalDockerHost);
                } else {
                    // 如果不是标准格式，根据操作系统选择
                    if (isWindows) {
                        // Windows上尝试作为TCP连接
                        if (dockerHost.contains(":")) {
                            finalDockerHost = "tcp://" + dockerHost;
                        } else {
                            finalDockerHost = "tcp://" + dockerHost + ":2375";
                        }
                        logger.warn("Docker host格式不明确: {}, 在Windows上尝试作为TCP连接: {}", dockerHost, finalDockerHost);
                    } else {
                        // Linux/Mac上尝试作为Unix socket路径
                        String path = dockerHost.trim();
                        if (!path.startsWith("/")) {
                            path = "/" + path;
                        }
                        finalDockerHost = "unix://" + path;
                        logger.warn("Docker host格式不明确: {}, 尝试作为Unix socket路径: {}", dockerHost, finalDockerHost);
                    }
                }
            }
            
            // 设置Docker主机地址
            configBuilder.withDockerHost(finalDockerHost);
            DefaultDockerClientConfig config = configBuilder.build();
            
            logger.info("Docker客户端配置 - Host: {}", config.getDockerHost());

            // 创建Docker HTTP客户端
            // 注意：对于Unix socket，ApacheDockerHttpClient会自动处理
            try {
                ApacheDockerHttpClient.Builder httpClientBuilder = new ApacheDockerHttpClient.Builder()
                        .dockerHost(config.getDockerHost())
                        .sslConfig(config.getSSLConfig());
                
                // 设置连接池大小（如果方法存在）
                try {
                    httpClientBuilder.maxConnections(100);
                } catch (Exception e) {
                    logger.debug("无法设置maxConnections，使用默认值: {}", e.getMessage());
                }
                
                ApacheDockerHttpClient httpClient = httpClientBuilder.build();
                
                // 创建Docker客户端
                dockerClient = DockerClientImpl.getInstance(config, httpClient);
                
                logger.info("Docker HTTP客户端创建成功");
            } catch (Exception e) {
                logger.error("创建Docker HTTP客户端失败: {}", e.getMessage(), e);
                throw new RuntimeException("创建Docker HTTP客户端失败: " + e.getMessage(), e);
            }

            // 测试连接
            try {
                dockerClient.pingCmd().exec();
                logger.info("Docker连接测试成功");
            } catch (Exception e) {
                logger.warn("Docker连接测试失败，但继续初始化: {}", e.getMessage());
            }

            // 创建线程池用于处理日志流
            executorService = Executors.newCachedThreadPool(r -> {
                Thread t = new Thread(r, "docker-log-stream-" + System.currentTimeMillis());
                t.setDaemon(true);
                return t;
            });

            logger.info("Docker日志服务初始化成功, Docker Host: {}, Container: {}", finalDockerHost, containerName);
        } catch (Exception e) {
            logger.error("Docker日志服务初始化失败", e);
            throw new RuntimeException("Docker日志服务初始化失败: " + e.getMessage(), e);
        }
    }

    @PreDestroy
    public void destroy() {
        // 关闭所有活动的日志流
        activeStreams.values().forEach(stream -> {
            try {
                stream.close();
            } catch (IOException e) {
                logger.warn("关闭日志流失败", e);
            }
        });
        activeStreams.clear();

        // 关闭线程池
        if (executorService != null) {
            executorService.shutdown();
        }

        // 关闭Docker客户端
        if (dockerClient != null) {
            try {
                dockerClient.close();
            } catch (IOException e) {
                logger.warn("关闭Docker客户端失败", e);
            }
        }

        logger.info("Docker日志服务已关闭");
    }

    @Override
    public CompletableFuture<Void> streamLogs(String sessionId, Consumer<String> logConsumer) {
        CompletableFuture<Void> future = new CompletableFuture<>();

        executorService.submit(() -> {
            try {
                // 验证容器名称
                if (containerName == null || containerName.trim().isEmpty()) {
                    String errorMsg = "错误: 容器名称未配置";
                    logConsumer.accept(errorMsg);
                    future.completeExceptionally(new IllegalArgumentException("容器名称未配置"));
                    return;
                }
                
                // 检查容器是否存在
                try {
                    dockerClient.inspectContainerCmd(containerName).exec();
                } catch (Exception e) {
                    logger.error("容器不存在或无法访问: {}", containerName, e);
                    String errorMsg = "错误: 容器 " + (containerName != null ? containerName : "未知") + " 不存在或无法访问";
                    logConsumer.accept(errorMsg);
                    future.completeExceptionally(e);
                    return;
                }

                // 创建日志流回调
                ResultCallback.Adapter<Frame> callback = new ResultCallback.Adapter<Frame>() {
                    @Override
                    public void onNext(Frame frame) {
                        try {
                            byte[] payload = frame.getPayload();
                            if (payload != null && payload.length > 0) {
                                String logLine = new String(payload);
                                // 移除末尾的换行符（如果有），因为前端会处理换行
                                logLine = logLine.replaceAll("[\r\n]+$", "");
                                if (!logLine.isEmpty()) {
                                    logConsumer.accept(logLine);
                                }
                            }
                        } catch (Exception e) {
                            logger.error("处理日志行失败", e);
                        }
                    }

                    @Override
                    public void onError(Throwable throwable) {
                        logger.error("日志流错误", throwable);
                        String errorMsg = throwable.getMessage();
                        if (errorMsg == null) {
                            errorMsg = throwable.getClass().getSimpleName();
                        }
                        logConsumer.accept("错误: " + errorMsg);
                        future.completeExceptionally(throwable);
                    }

                    @Override
                    public void onComplete() {
                        logger.info("日志流完成: {}", sessionId);
                        future.complete(null);
                    }
                };

                // 开始流式获取日志
                dockerClient.logContainerCmd(containerName)
                        .withStdOut(true)
                        .withStdErr(true)
                        .withFollowStream(true)
                        .withTail(100)  // 获取最后100行日志
                        .exec(callback);

                // 保存流引用以便后续关闭
                activeStreams.put(sessionId, callback);

                logger.info("开始流式获取容器日志: {}, Session: {}", containerName, sessionId);
            } catch (Exception e) {
                logger.error("启动日志流失败", e);
                String errorMsg = e.getMessage();
                if (errorMsg == null) {
                    errorMsg = e.getClass().getSimpleName();
                }
                logConsumer.accept("错误: " + errorMsg);
                future.completeExceptionally(e);
            }
        });

        return future;
    }

    @Override
    public void stopLogStream(String sessionId) {
        Closeable stream = activeStreams.remove(sessionId);
        if (stream != null) {
            try {
                stream.close();
                logger.info("停止日志流: {}", sessionId);
            } catch (IOException e) {
                logger.warn("停止日志流失败: {}", sessionId, e);
            }
        }
    }
}

