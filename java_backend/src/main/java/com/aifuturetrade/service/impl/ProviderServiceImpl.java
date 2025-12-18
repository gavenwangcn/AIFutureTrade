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
import java.util.ArrayList;
import java.util.Arrays;
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
    public ProviderDTO getProviderById(Integer id) {
        ProviderDO providerDO = providerMapper.selectProviderById(id);
        return providerDO != null ? convertToDTO(providerDO) : null;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public ProviderDTO addProvider(ProviderDTO providerDTO) {
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
    public Boolean deleteProvider(Integer id) {
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
        // TODO: 实现从API获取可用模型列表的逻辑
        // 示例代码，实际需要调用具体的API
        return new ArrayList<>(Arrays.asList("gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"));
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