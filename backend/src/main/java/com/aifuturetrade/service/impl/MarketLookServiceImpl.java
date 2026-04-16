package com.aifuturetrade.service.impl;

import com.aifuturetrade.dao.entity.MarketLookDO;
import com.aifuturetrade.dao.entity.StrategyDO;
import com.aifuturetrade.dao.mapper.MarketLookMapper;
import com.aifuturetrade.dao.mapper.StrategyMapper;
import com.aifuturetrade.common.util.PageRequest;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.service.MarketLookDeleteOutcome;
import com.aifuturetrade.service.MarketLookService;
import com.aifuturetrade.service.dto.MarketLookDTO;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import org.springframework.beans.BeanUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.util.Arrays;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * market_look 业务实现
 */
@Service
public class MarketLookServiceImpl implements MarketLookService {

    @Autowired
    private MarketLookMapper marketLookMapper;

    @Autowired
    private StrategyMapper strategyMapper;

    @Override
    public List<MarketLookDTO> listAll() {
        LambdaQueryWrapper<MarketLookDO> q = new LambdaQueryWrapper<>();
        q.orderByDesc(MarketLookDO::getStartedAt).orderByDesc(MarketLookDO::getCreatedAt);
        return marketLookMapper.selectList(q).stream()
                .map(this::toDto)
                .collect(Collectors.toList());
    }

    @Override
    public List<MarketLookDTO> listRunning() {
        LambdaQueryWrapper<MarketLookDO> q = new LambdaQueryWrapper<>();
        q.in(
                MarketLookDO::getExecutionStatus,
                Arrays.asList(MarketLookDO.STATUS_RUNNING, MarketLookDO.STATUS_SENDING));
        q.orderByDesc(MarketLookDO::getStartedAt);
        return marketLookMapper.selectList(q).stream()
                .map(this::toDto)
                .collect(Collectors.toList());
    }

    @Override
    public PageResult<MarketLookDTO> page(
            PageRequest pageRequest,
            String executionStatus,
            String symbol,
            String strategyId,
            String detailSummary,
            LocalDateTime startedAtFrom,
            LocalDateTime startedAtTo,
            LocalDateTime endedAtFrom,
            LocalDateTime endedAtTo) {
        int pageNum = pageRequest.getPageNum() != null && pageRequest.getPageNum() > 0 ? pageRequest.getPageNum() : 1;
        int pageSize = pageRequest.getPageSize() != null && pageRequest.getPageSize() > 0 ? pageRequest.getPageSize() : 10;

        LambdaQueryWrapper<MarketLookDO> q = new LambdaQueryWrapper<>();
        if (StringUtils.hasText(executionStatus) && !"undefined".equalsIgnoreCase(executionStatus)) {
            q.eq(MarketLookDO::getExecutionStatus, executionStatus.trim());
        }
        if (StringUtils.hasText(symbol) && !"undefined".equalsIgnoreCase(symbol)) {
            q.like(MarketLookDO::getSymbol, symbol.trim());
        }
        if (StringUtils.hasText(strategyId) && !"undefined".equalsIgnoreCase(strategyId)) {
            q.eq(MarketLookDO::getStrategyId, strategyId.trim());
        }
        if (StringUtils.hasText(detailSummary) && !"undefined".equalsIgnoreCase(detailSummary)) {
            q.like(MarketLookDO::getDetailSummary, detailSummary.trim());
        }
        if (startedAtFrom != null) {
            q.ge(MarketLookDO::getStartedAt, startedAtFrom);
        }
        if (startedAtTo != null) {
            q.le(MarketLookDO::getStartedAt, startedAtTo);
        }
        if (endedAtFrom != null) {
            q.ge(MarketLookDO::getEndedAt, endedAtFrom);
        }
        if (endedAtTo != null) {
            q.le(MarketLookDO::getEndedAt, endedAtTo);
        }
        q.orderByDesc(MarketLookDO::getStartedAt).orderByDesc(MarketLookDO::getCreatedAt);

        Page<MarketLookDO> page = new Page<>(pageNum, pageSize);
        Page<MarketLookDO> result = marketLookMapper.selectPage(page, q);
        List<MarketLookDTO> list = result.getRecords().stream().map(this::toDto).collect(Collectors.toList());
        return PageResult.build(list, result.getTotal(), pageNum, pageSize);
    }

    @Override
    public MarketLookDTO getById(String id) {
        MarketLookDO row = marketLookMapper.selectById(id);
        return row != null ? toDto(row) : null;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public MarketLookDTO create(MarketLookDTO dto) {
        if (dto == null || !StringUtils.hasText(dto.getSymbol()) || !StringUtils.hasText(dto.getStrategyId())) {
            throw new IllegalArgumentException("symbol 与 strategy_id 不能为空");
        }
        if (!StringUtils.hasText(dto.getDetailSummary()) || dto.getDetailSummary().trim().isEmpty()) {
            throw new IllegalArgumentException("详情摘要 detail_summary 不能为空");
        }
        StrategyDO strategy = strategyMapper.selectById(dto.getStrategyId());
        if (strategy == null) {
            throw new IllegalArgumentException("策略不存在: " + dto.getStrategyId());
        }
        if (!"look".equalsIgnoreCase(strategy.getType())) {
            throw new IllegalArgumentException("盯盘任务必须关联 type=look 的策略，当前策略类型为: " + strategy.getType());
        }

        MarketLookDO row = new MarketLookDO();
        row.setId(StringUtils.hasText(dto.getId()) ? dto.getId() : UUID.randomUUID().toString());
        row.setSymbol(dto.getSymbol().trim().toUpperCase());
        row.setStrategyId(dto.getStrategyId().trim());
        row.setStrategyName(StringUtils.hasText(dto.getStrategyName()) ? dto.getStrategyName().trim() : strategy.getName());
        String status = StringUtils.hasText(dto.getExecutionStatus()) ? dto.getExecutionStatus().trim().toUpperCase() : MarketLookDO.STATUS_RUNNING;
        if (!MarketLookDO.STATUS_RUNNING.equals(status) && !MarketLookDO.STATUS_ENDED.equals(status)) {
            throw new IllegalArgumentException("execution_status 必须为 RUNNING 或 ENDED");
        }
        row.setExecutionStatus(status);
        row.setSignalResult(dto.getSignalResult());
        row.setDetailSummary(dto.getDetailSummary().trim());
        row.setEndLog(StringUtils.hasText(dto.getEndLog()) ? dto.getEndLog().trim() : null);

        LocalDateTime now = LocalDateTime.now();
        if (MarketLookDO.STATUS_RUNNING.equals(status)) {
            LocalDateTime started = dto.getStartedAt() != null ? dto.getStartedAt() : now;
            LocalDateTime ended = dto.getEndedAt() != null ? dto.getEndedAt() : started.plusHours(24);
            if (!ended.isAfter(started)) {
                throw new IllegalArgumentException("结束时间 ended_at 必须晚于开始时间 started_at");
            }
            row.setStartedAt(started);
            row.setEndedAt(ended);
        } else {
            LocalDateTime started = dto.getStartedAt() != null ? dto.getStartedAt() : now;
            LocalDateTime ended = dto.getEndedAt() != null ? dto.getEndedAt() : now;
            row.setStartedAt(started);
            row.setEndedAt(ended);
            if (ended.isBefore(started)) {
                throw new IllegalArgumentException("ended_at 不能早于 started_at");
            }
        }
        row.setCreatedAt(now);
        row.setUpdatedAt(now);

        marketLookMapper.insert(row);
        return toDto(row);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public MarketLookDTO update(String id, MarketLookDTO dto) {
        MarketLookDO existing = marketLookMapper.selectById(id);
        if (existing == null) {
            throw new IllegalArgumentException("记录不存在: " + id);
        }
        if (dto == null) {
            throw new IllegalArgumentException("请求体不能为空");
        }

        if (existing.getStartedAt() == null) {
            existing.setStartedAt(LocalDateTime.now());
        }
        if (existing.getEndedAt() == null) {
            existing.setEndedAt(MarketLookDO.STATUS_ENDED.equals(existing.getExecutionStatus())
                    ? existing.getStartedAt()
                    : MarketLookDO.ENDED_AT_NOT_FINISHED_PLACEHOLDER);
        }

        if (StringUtils.hasText(dto.getSymbol())) {
            existing.setSymbol(dto.getSymbol().trim().toUpperCase());
        }
        if (StringUtils.hasText(dto.getStrategyId())) {
            StrategyDO strategy = strategyMapper.selectById(dto.getStrategyId());
            if (strategy == null) {
                throw new IllegalArgumentException("策略不存在: " + dto.getStrategyId());
            }
            if (!"look".equalsIgnoreCase(strategy.getType())) {
                throw new IllegalArgumentException("盯盘任务必须关联 type=look 的策略");
            }
            existing.setStrategyId(dto.getStrategyId().trim());
            if (StringUtils.hasText(dto.getStrategyName())) {
                existing.setStrategyName(dto.getStrategyName().trim());
            } else {
                existing.setStrategyName(strategy.getName());
            }
        } else if (StringUtils.hasText(dto.getStrategyName())) {
            existing.setStrategyName(dto.getStrategyName().trim());
        }

        if (StringUtils.hasText(dto.getExecutionStatus())) {
            String status = dto.getExecutionStatus().trim().toUpperCase();
            if (!MarketLookDO.STATUS_RUNNING.equals(status) && !MarketLookDO.STATUS_ENDED.equals(status)) {
                throw new IllegalArgumentException("execution_status 必须为 RUNNING 或 ENDED");
            }
            existing.setExecutionStatus(status);
            if (MarketLookDO.STATUS_ENDED.equals(status)) {
                LocalDateTime ended = dto.getEndedAt() != null ? dto.getEndedAt() : LocalDateTime.now();
                existing.setEndedAt(ended);
                if (existing.getStartedAt() != null && ended.isBefore(existing.getStartedAt())) {
                    throw new IllegalArgumentException("ended_at 不能早于 started_at");
                }
            } else {
                existing.setEndedAt(MarketLookDO.ENDED_AT_NOT_FINISHED_PLACEHOLDER);
            }
        } else if (dto.getEndedAt() != null) {
            existing.setEndedAt(dto.getEndedAt());
        }

        if (dto.getSignalResult() != null) {
            existing.setSignalResult(dto.getSignalResult());
        }
        if (dto.getDetailSummary() != null) {
            String ds = dto.getDetailSummary().trim();
            existing.setDetailSummary(ds.isEmpty() ? null : ds);
        }
        if (dto.getEndLog() != null) {
            String el = dto.getEndLog().trim();
            existing.setEndLog(el.isEmpty() ? null : el);
        }
        if (dto.getStartedAt() != null) {
            existing.setStartedAt(dto.getStartedAt());
        }

        existing.setUpdatedAt(LocalDateTime.now());
        marketLookMapper.updateById(existing);
        return toDto(existing);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public MarketLookDeleteOutcome delete(String id) {
        if (!StringUtils.hasText(id)) {
            return MarketLookDeleteOutcome.NOT_FOUND;
        }
        String trimmed = id.trim();
        MarketLookDO existing = marketLookMapper.selectById(trimmed);
        if (existing == null) {
            return MarketLookDeleteOutcome.NOT_FOUND;
        }
        int affected = marketLookMapper.deleteById(trimmed);
        if (affected <= 0) {
            return MarketLookDeleteOutcome.NO_ROWS_DELETED;
        }
        MarketLookDO stillThere = marketLookMapper.selectById(trimmed);
        if (stillThere != null) {
            return MarketLookDeleteOutcome.VERIFY_FAILED;
        }
        return MarketLookDeleteOutcome.VERIFIED_REMOVED;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public MarketLookDTO patchStatus(String id, String executionStatus, LocalDateTime endedAt) {
        MarketLookDO existing = marketLookMapper.selectById(id);
        if (existing == null) {
            throw new IllegalArgumentException("记录不存在: " + id);
        }
        if (existing.getStartedAt() == null) {
            existing.setStartedAt(LocalDateTime.now());
        }
        if (existing.getEndedAt() == null) {
            existing.setEndedAt(MarketLookDO.STATUS_ENDED.equals(existing.getExecutionStatus())
                    ? existing.getStartedAt()
                    : MarketLookDO.ENDED_AT_NOT_FINISHED_PLACEHOLDER);
        }
        if (!StringUtils.hasText(executionStatus)) {
            throw new IllegalArgumentException("execution_status 不能为空");
        }
        String status = executionStatus.trim().toUpperCase();
        if (!MarketLookDO.STATUS_RUNNING.equals(status) && !MarketLookDO.STATUS_ENDED.equals(status)) {
            throw new IllegalArgumentException("execution_status 必须为 RUNNING 或 ENDED");
        }
        existing.setExecutionStatus(status);
        if (MarketLookDO.STATUS_ENDED.equals(status)) {
            LocalDateTime end = endedAt != null ? endedAt : LocalDateTime.now();
            existing.setEndedAt(end);
            if (existing.getStartedAt() != null && end.isBefore(existing.getStartedAt())) {
                throw new IllegalArgumentException("ended_at 不能早于 started_at");
            }
        } else {
            existing.setEndedAt(MarketLookDO.ENDED_AT_NOT_FINISHED_PLACEHOLDER);
        }
        existing.setUpdatedAt(LocalDateTime.now());
        marketLookMapper.updateById(existing);
        return toDto(existing);
    }

    private MarketLookDTO toDto(MarketLookDO row) {
        MarketLookDTO dto = new MarketLookDTO();
        BeanUtils.copyProperties(row, dto);
        return dto;
    }
}
