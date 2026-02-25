package com.aifuturetrade.service;

import java.util.Map;

/**
 * Docker容器管理服务接口
 * 用于管理模型交易容器的创建、启动、停止和删除
 */
public interface DockerContainerService {
    
    /**
     * 检查容器是否存在且正常运行
     * @param containerName 容器名称
     * @return true: 容器存在且运行中, false: 容器不存在或未运行
     */
    boolean isContainerRunning(String containerName);
    
    /**
     * 删除容器（如果存在）
     * @param containerName 容器名称
     * @return true: 删除成功或容器不存在, false: 删除失败
     */
    boolean removeContainer(String containerName);
    
    /**
     * 启动模型买入容器
     * @param modelId 模型ID
     * @param imageName 镜像名称（如：aifuturetrade-model-buy）
     * @param envVars 环境变量Map
     * @return 启动结果，包含success、containerName、message等字段
     */
    Map<String, Object> startModelBuyContainer(String modelId, String imageName, Map<String, String> envVars);
    
    /**
     * 启动模型卖出容器
     * @param modelId 模型ID
     * @param imageName 镜像名称（如：aifuturetrade-model-sell）
     * @param envVars 环境变量Map
     * @return 启动结果，包含success、containerName、message等字段
     */
    Map<String, Object> startModelSellContainer(String modelId, String imageName, Map<String, String> envVars);
    
    /**
     * 停止容器
     * @param containerName 容器名称
     * @return true: 停止成功, false: 停止失败或容器不存在
     */
    boolean stopContainer(String containerName);
}

