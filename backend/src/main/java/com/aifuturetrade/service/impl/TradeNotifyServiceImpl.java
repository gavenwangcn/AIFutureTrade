package com.aifuturetrade.service.impl;

import com.aifuturetrade.common.util.PageRequest;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.dao.entity.TradeNotifyDO;
import com.aifuturetrade.dao.mapper.TradeNotifyMapper;
import com.aifuturetrade.service.TradeNotifyService;
import com.aifuturetrade.service.dto.TradeNotifyDTO;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import org.springframework.beans.BeanUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.List;
import java.util.stream.Collectors;

@Service
public class TradeNotifyServiceImpl implements TradeNotifyService {

    @Autowired
    private TradeNotifyMapper tradeNotifyMapper;

    @Override
    public TradeNotifyDTO getById(Long id) {
        if (id == null) {
            return null;
        }
        TradeNotifyDO row = tradeNotifyMapper.selectById(id);
        return row != null ? toDto(row) : null;
    }

    @Override
    public PageResult<TradeNotifyDTO> page(
            PageRequest pageRequest,
            String notifyType,
            String marketLookId,
            String strategyId,
            String symbol) {
        int pageNum = pageRequest.getPageNum() != null && pageRequest.getPageNum() > 0 ? pageRequest.getPageNum() : 1;
        int pageSize = pageRequest.getPageSize() != null && pageRequest.getPageSize() > 0 ? pageRequest.getPageSize() : 10;

        LambdaQueryWrapper<TradeNotifyDO> q = new LambdaQueryWrapper<>();
        if (StringUtils.hasText(notifyType) && !"undefined".equalsIgnoreCase(notifyType)) {
            q.eq(TradeNotifyDO::getNotifyType, notifyType.trim());
        }
        if (StringUtils.hasText(marketLookId) && !"undefined".equalsIgnoreCase(marketLookId)) {
            q.eq(TradeNotifyDO::getMarketLookId, marketLookId.trim());
        }
        if (StringUtils.hasText(strategyId) && !"undefined".equalsIgnoreCase(strategyId)) {
            q.eq(TradeNotifyDO::getStrategyId, strategyId.trim());
        }
        if (StringUtils.hasText(symbol) && !"undefined".equalsIgnoreCase(symbol)) {
            q.like(TradeNotifyDO::getSymbol, symbol.trim());
        }
        q.orderByDesc(TradeNotifyDO::getCreatedAt);

        Page<TradeNotifyDO> page = new Page<>(pageNum, pageSize);
        Page<TradeNotifyDO> result = tradeNotifyMapper.selectPage(page, q);
        List<TradeNotifyDTO> list = result.getRecords().stream().map(this::toDto).collect(Collectors.toList());
        return PageResult.build(list, result.getTotal(), pageNum, pageSize);
    }

    private TradeNotifyDTO toDto(TradeNotifyDO row) {
        TradeNotifyDTO dto = new TradeNotifyDTO();
        BeanUtils.copyProperties(row, dto);
        return dto;
    }
}
