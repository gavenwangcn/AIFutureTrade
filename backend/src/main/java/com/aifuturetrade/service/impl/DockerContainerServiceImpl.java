package com.aifuturetrade.service.impl;

import com.aifuturetrade.service.DockerContainerService;
import com.github.dockerjava.api.DockerClient;
import com.github.dockerjava.api.command.CreateContainerResponse;
import com.github.dockerjava.api.command.InspectContainerResponse;
import com.github.dockerjava.api.exception.NotFoundException;
import com.github.dockerjava.api.model.Network;
import java.util.List;
import com.github.dockerjava.core.DefaultDockerClientConfig;
import com.github.dockerjava.core.DockerClientImpl;
import com.github.dockerjava.httpclient5.ApacheDockerHttpClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import jakarta.annotation.PostConstruct;
import java.util.HashMap;
import java.util.Map;

/**
 * Docker容器管理服务实现类
 * 用于管理模型交易容器的创建、启动、停止和删除
 */
@Service
public class DockerContainerServiceImpl implements DockerContainerService {
    
    private static final Logger log = LoggerFactory.getLogger(DockerContainerServiceImpl.class);
    
    @Value("${docker.host:unix:///var/run/docker.sock}")
    private String dockerHost;
    
    @Value("${docker.network:aifuturetrade-network}")
    private String dockerNetwork;
    
    @Value("${docker.image.buy:aifuturetrade-model-buy}")
    private String defaultBuyImageName;
    
    @Value("${docker.image.sell:aifuturetrade-model-sell}")
    private String defaultSellImageName;
    
    private DockerClient dockerClient;
    
    @PostConstruct
    public void init() {
        try {
            // 创建Docker客户端配置（复用DockerLogServiceImpl的逻辑）
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
            
            // 确保 Docker 网络存在
            ensureNetworkExists();
        } catch (Exception e) {
            log.error("Docker容器管理服务初始化失败", e);
            throw new RuntimeException("Docker容器管理服务初始化失败: " + e.getMessage(), e);
        }
    }
    
    /**
     * 确保 Docker 网络存在，如果不存在则创建
     */
    private void ensureNetworkExists() {
        try {
            // 先尝试通过列表查找网络（更可靠的方法）
            try {
                List<Network> networks = dockerClient.listNetworksCmd().exec();
                boolean networkExists = networks.stream()
                        .anyMatch(n -> dockerNetwork.equals(n.getName()) || dockerNetwork.equals(n.getId()));
                if (networkExists) {
                    log.info("Docker 网络已存在: {}", dockerNetwork);
                    return;
                }
            } catch (Exception e) {
                log.debug("无法通过列表查找网络，将尝试直接检查: {}", e.getMessage());
            }
            
            // 尝试直接检查网络（使用 inspectNetworkCmd）
            try {
                dockerClient.inspectNetworkCmd()
                        .withNetworkId(dockerNetwork)
                        .exec();
                log.info("Docker 网络已存在: {}", dockerNetwork);
                return;
            } catch (NotFoundException e) {
                // 网络不存在，继续创建
                log.info("Docker 网络不存在，将创建: {}", dockerNetwork);
            } catch (Exception e) {
                log.debug("检查网络时出错，将尝试创建: {}", e.getMessage());
            }
            
            // 创建网络
            try {
                dockerClient.createNetworkCmd()
                        .withName(dockerNetwork)
                        .withDriver("bridge")
                        .exec();
                log.info("Docker 网络创建成功: {}", dockerNetwork);
            } catch (Exception e) {
                // 如果网络已存在（并发创建），忽略错误
                String errorMsg = e.getMessage() != null ? e.getMessage() : "";
                if (errorMsg.contains("already exists") || errorMsg.contains("already exist")) {
                    log.debug("Docker 网络已存在（并发创建）: {}", dockerNetwork);
                } else {
                    // 再次检查网络是否存在（可能在其他地方被创建了）
                    try {
                        List<Network> networks = dockerClient.listNetworksCmd().exec();
                        boolean networkExists = networks.stream()
                                .anyMatch(n -> dockerNetwork.equals(n.getName()) || dockerNetwork.equals(n.getId()));
                        if (networkExists) {
                            log.info("Docker 网络已存在（创建后检查）: {}", dockerNetwork);
                            return;
                        }
                        log.warn("创建 Docker 网络失败，且网络不存在: {} - {}", dockerNetwork, errorMsg);
                    } catch (Exception ex) {
                        log.warn("创建 Docker 网络失败，且无法验证: {} - {}", dockerNetwork, errorMsg);
                    }
                }
            }
        } catch (Exception e) {
            log.warn("确保 Docker 网络存在时出错，但继续运行: {} - {}", dockerNetwork, e.getMessage());
        }
    }
    
    @Override
    public boolean isContainerRunning(String containerName) {
        try {
            InspectContainerResponse container = dockerClient.inspectContainerCmd(containerName).exec();
            if (container != null) {
                InspectContainerResponse.ContainerState state = container.getState();
                return state != null && state.getRunning() != null && state.getRunning();
            }
            return false;
        } catch (NotFoundException e) {
            log.debug("容器不存在: {}", containerName);
            return false;
        } catch (Exception e) {
            log.error("检查容器状态失败: {}", containerName, e);
            return false;
        }
    }
    
    @Override
    public boolean removeContainer(String containerName) {
        try {
            // 先检查容器是否存在
            try {
                dockerClient.inspectContainerCmd(containerName).exec();
            } catch (NotFoundException e) {
                log.debug("容器不存在，无需删除: {}", containerName);
                return true; // 容器不存在，视为删除成功
            }
            
            // 如果容器正在运行，先停止
            if (isContainerRunning(containerName)) {
                log.info("停止运行中的容器: {}", containerName);
                dockerClient.stopContainerCmd(containerName).exec();
                // 等待容器停止
                Thread.sleep(1000);
            }
            
            // 删除容器
            dockerClient.removeContainerCmd(containerName).exec();
            log.info("容器删除成功: {}", containerName);
            return true;
        } catch (NotFoundException e) {
            log.debug("容器不存在，无需删除: {}", containerName);
            return true;
        } catch (Exception e) {
            log.error("删除容器失败: {}", containerName, e);
            return false;
        }
    }
    
    @Override
    public Map<String, Object> startModelBuyContainer(String modelId, String imageName, Map<String, String> envVars) {
        String containerName = "buy-" + modelId;
        return startModelContainer(containerName, imageName != null ? imageName : defaultBuyImageName, envVars);
    }
    
    @Override
    public Map<String, Object> startModelSellContainer(String modelId, String imageName, Map<String, String> envVars) {
        String containerName = "sell-" + modelId;
        return startModelContainer(containerName, imageName != null ? imageName : defaultSellImageName, envVars);
    }
    
    private Map<String, Object> startModelContainer(String containerName, String imageName, Map<String, String> envVars) {
        Map<String, Object> result = new HashMap<>();
        
        try {
            // 确保网络存在
            ensureNetworkExists();
            
            // 检查容器是否已存在且运行中
            if (isContainerRunning(containerName)) {
                log.info("容器已存在且运行中: {}", containerName);
                result.put("success", true);
                result.put("containerName", containerName);
                result.put("message", "Container already running");
                return result;
            }
            
            // 如果容器存在但未运行，删除它
            if (removeContainer(containerName)) {
                log.info("已删除旧容器: {}", containerName);
            } else {
                log.warn("删除旧容器失败，但继续创建新容器: {}", containerName);
            }
            
            // 准备环境变量
            String[] envArray = null;
            if (envVars != null && !envVars.isEmpty()) {
                envArray = envVars.entrySet().stream()
                        .map(e -> e.getKey() + "=" + e.getValue())
                        .toArray(String[]::new);
            }
            
            // 创建容器配置（使用 HostConfig 替代已弃用的方法）
            com.github.dockerjava.api.model.HostConfig hostConfig = com.github.dockerjava.api.model.HostConfig.newHostConfig()
                    .withNetworkMode(dockerNetwork)
                    .withRestartPolicy(com.github.dockerjava.api.model.RestartPolicy.alwaysRestart());
            
            // 创建容器
            CreateContainerResponse createResponse = dockerClient.createContainerCmd(imageName)
                    .withName(containerName)
                    .withEnv(envArray != null ? envArray : new String[0])
                    .withHostConfig(hostConfig)
                    .exec();
            
            String containerId = createResponse.getId();
            log.info("容器创建成功: {} (ID: {})", containerName, containerId);
            
            // 启动容器
            dockerClient.startContainerCmd(containerId).exec();
            log.info("容器启动成功: {}", containerName);
            
            result.put("success", true);
            result.put("containerName", containerName);
            result.put("containerId", containerId);
            result.put("message", "Container started successfully");
            
        } catch (Exception e) {
            log.error("启动容器失败: {}", containerName, e);
            result.put("success", false);
            result.put("containerName", containerName);
            result.put("error", e.getMessage());
            result.put("message", "Failed to start container: " + e.getMessage());
        }
        
        return result;
    }
    
    @Override
    public boolean stopContainer(String containerName) {
        try {
            if (!isContainerRunning(containerName)) {
                log.debug("容器未运行: {}", containerName);
                return true; // 容器未运行，视为停止成功
            }
            
            dockerClient.stopContainerCmd(containerName).exec();
            log.info("容器停止成功: {}", containerName);
            return true;
        } catch (NotFoundException e) {
            log.debug("容器不存在: {}", containerName);
            return true;
        } catch (Exception e) {
            log.error("停止容器失败: {}", containerName, e);
            return false;
        }
    }
}

