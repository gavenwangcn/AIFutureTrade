package com.aifuturetrade.service.impl;

import com.aifuturetrade.dao.entity.StrategyDO;
import com.aifuturetrade.dao.mapper.StrategyMapper;
import com.aifuturetrade.service.StrategyService;
import com.aifuturetrade.service.StrategyCodeTesterService;
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
import lombok.extern.slf4j.Slf4j;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * 业务逻辑实现类：策略
 * 实现策略的业务逻辑
 */
@Slf4j
@Service
public class StrategyServiceImpl implements StrategyService {

    @Autowired
    private StrategyMapper strategyMapper;
    
    @Autowired
    private StrategyCodeTesterService strategyCodeTesterService;

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
        log.info("getStrategiesByPage - 开始分页查询策略，pageNum: {}, pageSize: {}, name: {}, type: {}", 
                pageRequest.getPageNum(), pageRequest.getPageSize(), name, type);
        
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
        log.info("getStrategiesByPage - 数据库查询结果，总记录数: {}, 当前页记录数: {}", 
                strategyDOPage.getTotal(), strategyDOPage.getRecords().size());
        
        List<StrategyDTO> strategyDTOList = strategyDOPage.getRecords().stream()
                .map(this::convertToDTO)
                .collect(Collectors.toList());
        
        PageResult<StrategyDTO> result = PageResult.build(strategyDTOList, strategyDOPage.getTotal(), pageRequest.getPageNum(), pageRequest.getPageSize());
        log.info("getStrategiesByPage - 返回分页结果，total: {}, pageNum: {}, pageSize: {}, data size: {}", 
                result.getTotal(), result.getPageNum(), result.getPageSize(), result.getData().size());
        
        return result;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public StrategyDTO addStrategy(StrategyDTO strategyDTO) {
        StrategyDO strategyDO = convertToDO(strategyDTO);
        if (strategyDO.getId() == null || strategyDO.getId().isEmpty()) {
            strategyDO.setId(UUID.randomUUID().toString());
        }
        
        // 如果提供了策略代码，进行测试验证
        if (strategyDO.getStrategyCode() != null && !strategyDO.getStrategyCode().trim().isEmpty()) {
            String strategyType = strategyDO.getType();
            String strategyName = strategyDO.getName() != null ? strategyDO.getName() : "新策略";
            
            if (strategyType == null || strategyType.trim().isEmpty()) {
                throw new IllegalArgumentException("策略类型不能为空，无法验证策略代码");
            }
            
            try {
                // 验证策略代码
                strategyCodeTesterService.validateStrategyCode(
                    strategyDO.getStrategyCode(), 
                    strategyType, 
                    strategyName
                );
                log.info("策略代码验证通过: {}", strategyName);
            } catch (Exception e) {
                log.error("策略代码验证失败: {}, 错误: {}", strategyName, e.getMessage());
                throw new RuntimeException("策略代码验证失败，无法保存: " + e.getMessage(), e);
            }
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
        
        // 如果更新了策略代码，进行测试验证
        if (strategyDO.getStrategyCode() != null && !strategyDO.getStrategyCode().trim().isEmpty()) {
            String strategyType = strategyDO.getType();
            String strategyName = strategyDO.getName() != null ? strategyDO.getName() : "策略";
            
            // 如果类型为空，尝试从数据库获取
            if (strategyType == null || strategyType.trim().isEmpty()) {
                StrategyDO existingStrategy = strategyMapper.selectById(strategyDO.getId());
                if (existingStrategy != null) {
                    strategyType = existingStrategy.getType();
                }
            }
            
            if (strategyType == null || strategyType.trim().isEmpty()) {
                throw new IllegalArgumentException("策略类型不能为空，无法验证策略代码");
            }
            
            try {
                // 验证策略代码
                strategyCodeTesterService.validateStrategyCode(
                    strategyDO.getStrategyCode(), 
                    strategyType, 
                    strategyName
                );
                log.info("策略代码验证通过: {}", strategyName);
            } catch (Exception e) {
                log.error("策略代码验证失败: {}, 错误: {}", strategyName, e.getMessage());
                throw new RuntimeException("策略代码验证失败，无法更新: " + e.getMessage(), e);
            }
        }
        
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

