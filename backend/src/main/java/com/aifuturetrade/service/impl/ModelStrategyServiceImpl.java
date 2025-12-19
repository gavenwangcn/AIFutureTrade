package com.aifuturetrade.service.impl;

import com.aifuturetrade.dao.entity.ModelStrategyDO;
import com.aifuturetrade.dao.mapper.ModelStrategyMapper;
import com.aifuturetrade.service.ModelStrategyService;
import com.aifuturetrade.service.dto.ModelStrategyDTO;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import org.springframework.beans.BeanUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * 业务逻辑实现类：模型关联策略
 * 实现模型关联策略的业务逻辑
 */
@Service
public class ModelStrategyServiceImpl implements ModelStrategyService {

    @Autowired
    private ModelStrategyMapper modelStrategyMapper;

    @Override
    public List<ModelStrategyDTO> getAllModelStrategies() {
        List<ModelStrategyDO> modelStrategyDOList = modelStrategyMapper.selectAllModelStrategies();
        return modelStrategyDOList.stream()
                .map(this::convertToDTO)
                .collect(Collectors.toList());
    }

    @Override
    public ModelStrategyDTO getModelStrategyById(String id) {
        ModelStrategyDO modelStrategyDO = modelStrategyMapper.selectModelStrategyById(id);
        return modelStrategyDO != null ? convertToDTO(modelStrategyDO) : null;
    }

    @Override
    public List<ModelStrategyDTO> getModelStrategiesByModelId(String modelId) {
        List<ModelStrategyDO> modelStrategyDOList = modelStrategyMapper.selectModelStrategiesByModelId(modelId);
        return modelStrategyDOList.stream()
                .map(this::convertToDTO)
                .collect(Collectors.toList());
    }

    @Override
    public List<ModelStrategyDTO> getModelStrategiesByStrategyId(String strategyId) {
        List<ModelStrategyDO> modelStrategyDOList = modelStrategyMapper.selectModelStrategiesByStrategyId(strategyId);
        return modelStrategyDOList.stream()
                .map(this::convertToDTO)
                .collect(Collectors.toList());
    }

    @Override
    public List<ModelStrategyDTO> getModelStrategiesByModelIdAndType(String modelId, String type) {
        List<ModelStrategyDO> modelStrategyDOList = modelStrategyMapper.selectModelStrategiesByModelIdAndType(modelId, type);
        return modelStrategyDOList.stream()
                .map(this::convertToDTO)
                .collect(Collectors.toList());
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public ModelStrategyDTO addModelStrategy(ModelStrategyDTO modelStrategyDTO) {
        // 检查是否已存在相同的关联
        LambdaQueryWrapper<ModelStrategyDO> queryWrapper = new LambdaQueryWrapper<>();
        queryWrapper.eq(ModelStrategyDO::getModelId, modelStrategyDTO.getModelId())
                .eq(ModelStrategyDO::getStrategyId, modelStrategyDTO.getStrategyId())
                .eq(ModelStrategyDO::getType, modelStrategyDTO.getType());
        ModelStrategyDO existing = modelStrategyMapper.selectOne(queryWrapper);
        if (existing != null) {
            throw new RuntimeException("该模型已关联此策略，无法重复关联");
        }

        ModelStrategyDO modelStrategyDO = convertToDO(modelStrategyDTO);
        if (modelStrategyDO.getId() == null || modelStrategyDO.getId().isEmpty()) {
            modelStrategyDO.setId(UUID.randomUUID().toString());
        }
        if (modelStrategyDO.getPriority() == null) {
            modelStrategyDO.setPriority(0);
        }
        modelStrategyDO.setCreatedAt(LocalDateTime.now());
        modelStrategyMapper.insert(modelStrategyDO);
        return convertToDTO(modelStrategyDO);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Boolean deleteModelStrategy(String id) {
        int result = modelStrategyMapper.deleteById(id);
        return result > 0;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Boolean deleteModelStrategyByModelIdAndStrategyIdAndType(String modelId, String strategyId, String type) {
        LambdaQueryWrapper<ModelStrategyDO> queryWrapper = new LambdaQueryWrapper<>();
        queryWrapper.eq(ModelStrategyDO::getModelId, modelId)
                .eq(ModelStrategyDO::getStrategyId, strategyId)
                .eq(ModelStrategyDO::getType, type);
        int result = modelStrategyMapper.delete(queryWrapper);
        return result > 0;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public ModelStrategyDTO updateModelStrategyPriority(String id, Integer priority) {
        ModelStrategyDO modelStrategyDO = modelStrategyMapper.selectById(id);
        if (modelStrategyDO == null) {
            throw new RuntimeException("模型策略关联不存在");
        }
        modelStrategyDO.setPriority(priority != null ? priority : 0);
        modelStrategyMapper.updateById(modelStrategyDO);
        return convertToDTO(modelStrategyDO);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Boolean batchSaveModelStrategies(String modelId, String type, List<ModelStrategyDTO> modelStrategies) {
        // 先删除该模型该类型的所有关联
        LambdaQueryWrapper<ModelStrategyDO> deleteWrapper = new LambdaQueryWrapper<>();
        deleteWrapper.eq(ModelStrategyDO::getModelId, modelId)
                .eq(ModelStrategyDO::getType, type);
        modelStrategyMapper.delete(deleteWrapper);

        // 再批量插入新的关联
        for (ModelStrategyDTO dto : modelStrategies) {
            ModelStrategyDO modelStrategyDO = new ModelStrategyDO();
            modelStrategyDO.setId(UUID.randomUUID().toString());
            modelStrategyDO.setModelId(modelId);
            modelStrategyDO.setStrategyId(dto.getStrategyId());
            modelStrategyDO.setType(type);
            modelStrategyDO.setPriority(dto.getPriority() != null ? dto.getPriority() : 0);
            modelStrategyDO.setCreatedAt(LocalDateTime.now());
            modelStrategyMapper.insert(modelStrategyDO);
        }
        return true;
    }

    /**
     * 将DO转换为DTO
     * @param modelStrategyDO 数据对象
     * @return 数据传输对象
     */
    private ModelStrategyDTO convertToDTO(ModelStrategyDO modelStrategyDO) {
        ModelStrategyDTO modelStrategyDTO = new ModelStrategyDTO();
        BeanUtils.copyProperties(modelStrategyDO, modelStrategyDTO);
        return modelStrategyDTO;
    }

    /**
     * 将DTO转换为DO
     * @param modelStrategyDTO 数据传输对象
     * @return 数据对象
     */
    private ModelStrategyDO convertToDO(ModelStrategyDTO modelStrategyDTO) {
        ModelStrategyDO modelStrategyDO = new ModelStrategyDO();
        BeanUtils.copyProperties(modelStrategyDTO, modelStrategyDO);
        return modelStrategyDO;
    }

}

