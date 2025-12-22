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
    public List<StrategyDTO> getStrategiesByKeyword(String keyword, String type) {
        LambdaQueryWrapper<StrategyDO> queryWrapper = new LambdaQueryWrapper<>();
        if (StringUtils.hasText(keyword)) {
            queryWrapper.and(wrapper -> wrapper
                    .like(StrategyDO::getName, keyword)
                    .or()
                    .like(StrategyDO::getStrategyContext, keyword)
            );
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
        log.info("[StrategyService] 开始分页查询策略列表");
        log.info("[StrategyService] 查询参数 - 页码: {}, 每页大小: {}, 策略名称: {}, 策略类型: {}", 
                pageRequest.getPageNum(), pageRequest.getPageSize(), name, type);
        
        Page<StrategyDO> page = new Page<>(pageRequest.getPageNum(), pageRequest.getPageSize());
        
        LambdaQueryWrapper<StrategyDO> queryWrapper = new LambdaQueryWrapper<>();
        // 过滤掉 null、"undefined" 字符串和空字符串
        if (StringUtils.hasText(name) && !"undefined".equalsIgnoreCase(name)) {
            queryWrapper.like(StrategyDO::getName, name);
            log.info("[StrategyService] 添加名称模糊查询条件: {}", name);
        } else {
            log.info("[StrategyService] 策略名称为空或undefined，不添加名称查询条件");
        }
        if (StringUtils.hasText(type) && !"undefined".equalsIgnoreCase(type)) {
            queryWrapper.eq(StrategyDO::getType, type);
            log.info("[StrategyService] 添加类型精确查询条件: {}", type);
        } else {
            log.info("[StrategyService] 策略类型为空或undefined，不添加类型查询条件");
        }
        queryWrapper.orderByDesc(StrategyDO::getCreatedAt);
        
        log.info("[StrategyService] 执行数据库查询...");
        Page<StrategyDO> strategyDOPage = strategyMapper.selectPage(page, queryWrapper);
        log.info("[StrategyService] 数据库查询完成 - 总记录数: {}, 当前页记录数: {}", 
                strategyDOPage.getTotal(), strategyDOPage.getRecords().size());
        
        if (strategyDOPage.getRecords().size() > 0) {
            StrategyDO firstRecord = strategyDOPage.getRecords().get(0);
            log.info("[StrategyService] 查询结果示例（第一条）: ID={}, 名称={}, 类型={}, 创建时间={}", 
                    firstRecord.getId(), firstRecord.getName(), firstRecord.getType(), firstRecord.getCreatedAt());
        } else {
            log.warn("[StrategyService] 查询结果为空！请检查strategys表中是否有数据");
        }
        
        List<StrategyDTO> strategyDTOList = strategyDOPage.getRecords().stream()
                .map(this::convertToDTO)
                .collect(Collectors.toList());
        
        PageResult<StrategyDTO> result = PageResult.build(strategyDTOList, strategyDOPage.getTotal(), pageRequest.getPageNum(), pageRequest.getPageSize());
        log.info("[StrategyService] 分页查询完成 - 返回DTO列表大小: {}, 总记录数: {}", 
                strategyDTOList.size(), result.getTotal());
        
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

