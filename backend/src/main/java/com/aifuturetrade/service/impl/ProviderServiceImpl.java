package com.aifuturetrade.service.impl;

import com.aifuturetrade.dao.entity.ProviderDO;
import com.aifuturetrade.dao.mapper.ProviderMapper;
import com.aifuturetrade.service.ProviderService;
import com.aifuturetrade.service.dto.ProviderDTO;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.common.util.PageRequest;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import org.springframework.beans.BeanUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.stream.Collectors;

/**
 * 业务逻辑实现类：API提供方
 * 实现API提供方的业务逻辑
 */
@Service
public class ProviderServiceImpl implements ProviderService {

    @Autowired
    private ProviderMapper providerMapper;

    @Override
    public List<ProviderDTO> getAllProviders() {
        List<ProviderDO> providerDOList = providerMapper.selectAllProviders();
        return providerDOList.stream()
                .map(this::convertToDTO)
                .collect(Collectors.toList());
    }

    @Override
    public ProviderDTO getProviderById(String id) {
        ProviderDO providerDO = providerMapper.selectProviderById(id);
        return providerDO != null ? convertToDTO(providerDO) : null;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public ProviderDTO addProvider(ProviderDTO providerDTO) {
        // 验证必填字段
        if (providerDTO.getApiUrl() == null || providerDTO.getApiUrl().trim().isEmpty()) {
            throw new IllegalArgumentException("API URL 不能为空");
        }
        if (providerDTO.getApiKey() == null || providerDTO.getApiKey().trim().isEmpty()) {
            throw new IllegalArgumentException("API Key 不能为空");
        }
        
        ProviderDO providerDO = convertToDO(providerDTO);
        providerDO.setCreatedAt(LocalDateTime.now());
        providerDO.setUpdatedAt(LocalDateTime.now());
        providerMapper.insert(providerDO);
        return convertToDTO(providerDO);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public ProviderDTO updateProvider(ProviderDTO providerDTO) {
        ProviderDO providerDO = convertToDO(providerDTO);
        providerDO.setUpdatedAt(LocalDateTime.now());
        providerMapper.updateById(providerDO);
        return convertToDTO(providerDO);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Boolean deleteProvider(String id) {
        int result = providerMapper.deleteById(id);
        return result > 0;
    }

    @Override
    public PageResult<ProviderDTO> getProvidersByPage(PageRequest pageRequest) {
        Page<ProviderDO> page = new Page<>(pageRequest.getPageNum(), pageRequest.getPageSize());
        Page<ProviderDO> providerDOPage = providerMapper.selectPage(page, null);
        List<ProviderDTO> providerDTOList = providerDOPage.getRecords().stream()
                .map(this::convertToDTO)
                .collect(Collectors.toList());
        return PageResult.build(providerDTOList, providerDOPage.getTotal(), pageRequest.getPageNum(), pageRequest.getPageSize());
    }

    @Override
    public List<String> fetchProviderModels(String apiUrl, String apiKey) {
        try {
            java.net.http.HttpClient client = java.net.http.HttpClient.newBuilder()
                    .connectTimeout(java.time.Duration.ofSeconds(10))
                    .build();
            
            String url = apiUrl.endsWith("/") ? apiUrl + "models" : apiUrl + "/models";
            if (!url.contains("/v1")) {
                url = url.replace("/models", "/v1/models");
            }
            
            java.net.http.HttpRequest request = java.net.http.HttpRequest.newBuilder()
                    .uri(java.net.URI.create(url))
                    .header("Authorization", "Bearer " + apiKey)
                    .header("Content-Type", "application/json")
                    .GET()
                    .timeout(java.time.Duration.ofSeconds(10))
                    .build();
            
            java.net.http.HttpResponse<String> response = client.send(request, 
                    java.net.http.HttpResponse.BodyHandlers.ofString());
            
            if (response.statusCode() == 200) {
                com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
                com.fasterxml.jackson.databind.JsonNode jsonNode = mapper.readTree(response.body());
                com.fasterxml.jackson.databind.JsonNode dataNode = jsonNode.get("data");
                
                if (dataNode != null && dataNode.isArray()) {
                    java.util.List<String> models = new java.util.ArrayList<>();
                    for (com.fasterxml.jackson.databind.JsonNode modelNode : dataNode) {
                        String modelId = modelNode.get("id").asText();
                        // 过滤GPT模型或所有模型（根据提供方类型）
                        if (apiUrl.toLowerCase().contains("openai") || 
                            apiUrl.toLowerCase().contains("deepseek")) {
                            if (modelId.toLowerCase().contains("gpt") || 
                                modelId.toLowerCase().contains("deepseek")) {
                                models.add(modelId);
                            }
                        } else {
                            models.add(modelId);
                        }
                    }
                    return models;
                }
            }
            
            // 如果API调用失败，返回默认模型列表
            return List.of("gpt-3.5-turbo", "gpt-4", "gpt-4-turbo");
        } catch (Exception e) {
            // 如果API调用失败，返回默认模型列表
            return List.of("gpt-3.5-turbo", "gpt-4", "gpt-4-turbo");
        }
    }

    /**
     * 将DO转换为DTO
     * @param providerDO 数据对象
     * @return 数据传输对象
     */
    private ProviderDTO convertToDTO(ProviderDO providerDO) {
        ProviderDTO providerDTO = new ProviderDTO();
        BeanUtils.copyProperties(providerDO, providerDTO);
        return providerDTO;
    }

    /**
     * 将DTO转换为DO
     * @param providerDTO 数据传输对象
     * @return 数据对象
     */
    private ProviderDO convertToDO(ProviderDTO providerDTO) {
        ProviderDO providerDO = new ProviderDO();
        BeanUtils.copyProperties(providerDTO, providerDO);
        return providerDO;
    }

}