package com.aifuturetrade.service.impl;

import com.aifuturetrade.dao.entity.StrategyDO;
import com.aifuturetrade.dao.mapper.StrategyMapper;
import com.aifuturetrade.service.StrategyService;
import com.aifuturetrade.service.dto.StrategyDTO;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.common.util.PageRequest;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import org.springframework.beans.BeanUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * 业务逻辑实现类：策略
 * 实现策略的业务逻辑
 */
@Service
public class StrategyServiceImpl implements StrategyService {

    @Autowired
    private StrategyMapper strategyMapper;

    @Override
    public List<StrategyDTO> getAllStrategies() {
        List<StrategyDO> strategyDOList = strategyMapper.selectAllStrategies();
        return strategyDOList.stream()
                .map(this::convertToDTO)
                .collect(Collectors.toList());
    }

    @Override
    public StrategyDTO getStrategyById(String id) {
        StrategyDO strategyDO = strategyMapper.selectStrategyById(id);
        return strategyDO != null ? convertToDTO(strategyDO) : null;
    }

    @Override
    public List<StrategyDTO> getStrategiesByCondition(String name, String type) {
        LambdaQueryWrapper<StrategyDO> queryWrapper = new LambdaQueryWrapper<>();
        if (StringUtils.hasText(name)) {
            queryWrapper.like(StrategyDO::getName, name);
        }
        if (StringUtils.hasText(type)) {
            queryWrapper.eq(StrategyDO::getType, type);
        }
        queryWrapper.orderByDesc(StrategyDO::getCreatedAt);
        
        List<StrategyDO> strategyDOList = strategyMapper.selectList(queryWrapper);
        return strategyDOList.stream()
                .map(this::convertToDTO)
                .collect(Collectors.toList());
    }

    @Override
    public PageResult<StrategyDTO> getStrategiesByPage(PageRequest pageRequest, String name, String type) {
        Page<StrategyDO> page = new Page<>(pageRequest.getPageNum(), pageRequest.getPageSize());
        
        LambdaQueryWrapper<StrategyDO> queryWrapper = new LambdaQueryWrapper<>();
        if (StringUtils.hasText(name)) {
            queryWrapper.like(StrategyDO::getName, name);
        }
        if (StringUtils.hasText(type)) {
            queryWrapper.eq(StrategyDO::getType, type);
        }
        queryWrapper.orderByDesc(StrategyDO::getCreatedAt);
        
        Page<StrategyDO> strategyDOPage = strategyMapper.selectPage(page, queryWrapper);
        List<StrategyDTO> strategyDTOList = strategyDOPage.getRecords().stream()
                .map(this::convertToDTO)
                .collect(Collectors.toList());
        return PageResult.build(strategyDTOList, strategyDOPage.getTotal(), pageRequest.getPageNum(), pageRequest.getPageSize());
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public StrategyDTO addStrategy(StrategyDTO strategyDTO) {
        StrategyDO strategyDO = convertToDO(strategyDTO);
        if (strategyDO.getId() == null || strategyDO.getId().isEmpty()) {
            strategyDO.setId(UUID.randomUUID().toString());
        }
        strategyDO.setCreatedAt(LocalDateTime.now());
        strategyDO.setUpdatedAt(LocalDateTime.now());
        strategyMapper.insert(strategyDO);
        return convertToDTO(strategyDO);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public StrategyDTO updateStrategy(StrategyDTO strategyDTO) {
        StrategyDO strategyDO = convertToDO(strategyDTO);
        strategyDO.setUpdatedAt(LocalDateTime.now());
        strategyMapper.updateById(strategyDO);
        return convertToDTO(strategyDO);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Boolean deleteStrategy(String id) {
        int result = strategyMapper.deleteById(id);
        return result > 0;
    }

    /**
     * 将DO转换为DTO
     * @param strategyDO 数据对象
     * @return 数据传输对象
     */
    private StrategyDTO convertToDTO(StrategyDO strategyDO) {
        StrategyDTO strategyDTO = new StrategyDTO();
        BeanUtils.copyProperties(strategyDO, strategyDTO);
        return strategyDTO;
    }

    /**
     * 将DTO转换为DO
     * @param strategyDTO 数据传输对象
     * @return 数据对象
     */
    private StrategyDO convertToDO(StrategyDTO strategyDTO) {
        StrategyDO strategyDO = new StrategyDO();
        BeanUtils.copyProperties(strategyDTO, strategyDO);
        return strategyDO;
    }

}

