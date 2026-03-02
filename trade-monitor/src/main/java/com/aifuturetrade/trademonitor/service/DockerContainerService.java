package com.aifuturetrade.trademonitor.service;

/**
 * Docker容器管理服务接口
 */
public interface DockerContainerService {

    /**
     * 重启容器
     * @param containerName 容器名称
     * @return 是否成功
     */
    boolean restartContainer(String containerName);

    /**
     * 检查容器是否运行
     * @param containerName 容器名称
     * @return 是否运行
     */
    boolean isContainerRunning(String containerName);
}
