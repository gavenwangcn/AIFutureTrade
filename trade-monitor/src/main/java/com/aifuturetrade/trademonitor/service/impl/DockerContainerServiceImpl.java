package com.aifuturetrade.trademonitor.service.impl;

import com.aifuturetrade.trademonitor.service.DockerContainerService;
import com.github.dockerjava.api.DockerClient;
import com.github.dockerjava.api.command.InspectContainerResponse;
import com.github.dockerjava.api.exception.NotFoundException;
import com.github.dockerjava.core.DefaultDockerClientConfig;
import com.github.dockerjava.core.DockerClientImpl;
import com.github.dockerjava.httpclient5.ApacheDockerHttpClient;
import jakarta.annotation.PostConstruct;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

/**
 * Docker容器管理服务实现类
 */
@Slf4j
@Service
public class DockerContainerServiceImpl implements DockerContainerService {

    @Value("${docker.host:unix:///var/run/docker.sock}")
    private String dockerHost;

    private DockerClient dockerClient;

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
                if (isWindows) {
                    finalDockerHost = "tcp://localhost:2375";
                } else {
                    finalDockerHost = "unix:///var/run/docker.sock";
                }
            } else {
                if (dockerHost.startsWith("unix://")) {
                    if (isWindows) {
                        finalDockerHost = "tcp://localhost:2375";
                    } else {
                        String path = dockerHost.substring(7);
                        if (!path.startsWith("/")) {
                            path = "/" + path;
                        }
                        finalDockerHost = "unix://" + path;
                    }
                } else if (!dockerHost.startsWith("tcp://") &&
                           !dockerHost.startsWith("http://") &&
                           !dockerHost.startsWith("https://")) {
                    if (isWindows) {
                        if (dockerHost.contains(":")) {
                            finalDockerHost = "tcp://" + dockerHost;
                        } else {
                            finalDockerHost = "tcp://" + dockerHost + ":2375";
                        }
                    } else {
                        String path = dockerHost.trim();
                        if (!path.startsWith("/")) {
                            path = "/" + path;
                        }
                        finalDockerHost = "unix://" + path;
                    }
                }
            }

            configBuilder.withDockerHost(finalDockerHost);
            DefaultDockerClientConfig config = configBuilder.build();

            // 创建Docker HTTP客户端
            ApacheDockerHttpClient httpClient = new ApacheDockerHttpClient.Builder()
                    .dockerHost(config.getDockerHost())
                    .sslConfig(config.getSSLConfig())
                    .maxConnections(100)
                    .build();

            // 创建Docker客户端
            dockerClient = DockerClientImpl.getInstance(config, httpClient);

            // 测试连接
            try {
                dockerClient.pingCmd().exec();
                log.info("Docker容器管理服务初始化成功, Docker Host: {}", finalDockerHost);
            } catch (Exception e) {
                log.warn("Docker连接测试失败，但继续初始化: {}", e.getMessage());
            }
        } catch (Exception e) {
            log.error("Docker容器管理服务初始化失败", e);
            throw new RuntimeException("Docker容器管理服务初始化失败: " + e.getMessage(), e);
        }
    }

    @Override
    public boolean restartContainer(String containerName) {
        try {
            log.info("开始重启容器: {}", containerName);
            dockerClient.restartContainerCmd(containerName).exec();
            log.info("容器重启成功: {}", containerName);
            return true;
        } catch (NotFoundException e) {
            log.error("容器不存在: {}", containerName);
            return false;
        } catch (Exception e) {
            log.error("重启容器失败: {}", containerName, e);
            return false;
        }
    }

    @Override
    public boolean isContainerRunning(String containerName) {
        try {
            InspectContainerResponse response = dockerClient.inspectContainerCmd(containerName).exec();
            Boolean running = response.getState().getRunning();
            return running != null && running;
        } catch (NotFoundException e) {
            log.debug("容器不存在: {}", containerName);
            return false;
        } catch (Exception e) {
            log.error("检查容器状态失败: {}", containerName, e);
            return false;
        }
    }
}
