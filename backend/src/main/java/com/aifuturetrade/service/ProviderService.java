package com.aifuturetrade.service;

import com.aifuturetrade.service.dto.ProviderDTO;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.common.util.PageRequest;

import java.util.List;

/**
 * 业务逻辑接口：API提供方
 */
public interface ProviderService {

    /**
     * 查询所有API提供方
     * @return API提供方列表
     */
    List<ProviderDTO> getAllProviders();

    /**
     * 根据ID查询API提供方
     * @param id 提供方ID（UUID格式）
     * @return API提供方
     */
    ProviderDTO getProviderById(String id);

    /**
     * 添加API提供方
     * @param providerDTO API提供方信息
     * @return 新增的API提供方
     */
    ProviderDTO addProvider(ProviderDTO providerDTO);

    /**
     * 更新API提供方
     * @param providerDTO API提供方信息
     * @return 更新后的API提供方
     */
    ProviderDTO updateProvider(ProviderDTO providerDTO);

    /**
     * 删除API提供方
     * @param id 提供方ID（UUID格式）
     * @return 是否删除成功
     */
    Boolean deleteProvider(String id);

    /**
     * 分页查询API提供方
     * @param pageRequest 分页请求
     * @return 分页查询结果
     */
    PageResult<ProviderDTO> getProvidersByPage(PageRequest pageRequest);

    /**
     * 从API获取可用模型列表
     * @param apiUrl API URL
     * @param apiKey API密钥
     * @return 可用模型列表
     */
    List<String> fetchProviderModels(String apiUrl, String apiKey);

}