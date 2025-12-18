package com.aifuturetrade.service.impl;

import com.aifuturetrade.dal.entity.FutureDO;
import com.aifuturetrade.dal.mapper.FutureMapper;
import com.aifuturetrade.service.FutureService;
import com.aifuturetrade.service.dto.FutureDTO;
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
 * 业务逻辑实现类：合约配置
 * 实现合约配置的业务逻辑
 */
@Service
public class FutureServiceImpl implements FutureService {

    @Autowired
    private FutureMapper futureMapper;

    @Override
    public List<FutureDTO> getAllFutures() {
        List<FutureDO> futureDOList = futureMapper.selectAllFutures();
        return futureDOList.stream()
                .map(this::convertToDTO)
                .collect(Collectors.toList());
    }

    @Override
    public FutureDTO getFutureById(Integer id) {
        FutureDO futureDO = futureMapper.selectFutureById(id);
        return futureDO != null ? convertToDTO(futureDO) : null;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public FutureDTO addFuture(FutureDTO futureDTO) {
        FutureDO futureDO = convertToDO(futureDTO);
        futureDO.setCreatedAt(LocalDateTime.now());
        futureDO.setUpdatedAt(LocalDateTime.now());
        futureMapper.insert(futureDO);
        return convertToDTO(futureDO);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public FutureDTO updateFuture(FutureDTO futureDTO) {
        FutureDO futureDO = convertToDO(futureDTO);
        futureDO.setUpdatedAt(LocalDateTime.now());
        futureMapper.updateById(futureDO);
        return convertToDTO(futureDO);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Boolean deleteFuture(Integer id) {
        int result = futureMapper.deleteById(id);
        return result > 0;
    }

    @Override
    public PageResult<FutureDTO> getFuturesByPage(PageRequest pageRequest) {
        Page<FutureDO> page = new Page<>(pageRequest.getPageNum(), pageRequest.getPageSize());
        Page<FutureDO> futureDOPage = futureMapper.selectPage(page, null);
        List<FutureDTO> futureDTOList = futureDOPage.getRecords().stream()
                .map(this::convertToDTO)
                .collect(Collectors.toList());
        return PageResult.build(futureDTOList, futureDOPage.getTotal(), pageRequest.getPageNum(), pageRequest.getPageSize());
    }

    @Override
    public List<String> getTrackedSymbols() {
        return futureMapper.selectAllSymbols();
    }

    /**
     * 将DO转换为DTO
     * @param futureDO 数据对象
     * @return 数据传输对象
     */
    private FutureDTO convertToDTO(FutureDO futureDO) {
        FutureDTO futureDTO = new FutureDTO();
        BeanUtils.copyProperties(futureDO, futureDTO);
        return futureDTO;
    }

    /**
     * 将DTO转换为DO
     * @param futureDTO 数据传输对象
     * @return 数据对象
     */
    private FutureDO convertToDO(FutureDTO futureDTO) {
        FutureDO futureDO = new FutureDO();
        BeanUtils.copyProperties(futureDTO, futureDO);
        return futureDO;
    }

}