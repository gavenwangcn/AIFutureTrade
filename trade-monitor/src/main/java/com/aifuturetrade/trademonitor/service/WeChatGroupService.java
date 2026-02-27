package com.aifuturetrade.trademonitor.service;

import com.aifuturetrade.trademonitor.entity.WeChatGroupDO;
import com.baomidou.mybatisplus.core.metadata.IPage;

import java.util.List;

/**
 * 微信群配置服务接口
 */
public interface WeChatGroupService {

    /**
     * 分页查询微信群配置
     *
     * @param page 页码
     * @param size 每页大小
     * @param groupName 群组名称(可选)
     * @param isEnabled 是否启用(可选)
     * @return 分页结果
     */
    IPage<WeChatGroupDO> queryPage(Integer page, Integer size, String groupName, Boolean isEnabled);

    /**
     * 查询所有启用的微信群配置
     *
     * @return 启用的微信群列表
     */
    List<WeChatGroupDO> queryEnabledGroups();

    /**
     * 根据ID查询微信群配置
     *
     * @param id 配置ID
     * @return 微信群配置
     */
    WeChatGroupDO getById(Long id);

    /**
     * 创建微信群配置
     *
     * @param weChatGroup 微信群配置
     * @return 创建成功的配置
     */
    WeChatGroupDO create(WeChatGroupDO weChatGroup);

    /**
     * 更新微信群配置
     *
     * @param id 配置ID
     * @param weChatGroup 微信群配置
     * @return 更新成功的配置
     */
    WeChatGroupDO update(Long id, WeChatGroupDO weChatGroup);

    /**
     * 删除微信群配置
     *
     * @param id 配置ID
     */
    void delete(Long id);

    /**
     * 测试发送通知
     *
     * @param id 配置ID
     * @return 是否发送成功
     */
    boolean testSend(Long id);
}
