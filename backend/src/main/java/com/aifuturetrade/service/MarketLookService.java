package com.aifuturetrade.service;

import com.aifuturetrade.common.util.PageRequest;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.service.dto.MarketLookDTO;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 盯盘任务 market_look
 */
public interface MarketLookService {

    List<MarketLookDTO> listAll();

    /**
     * 执行中的盯盘任务（execution_status = RUNNING）
     */
    List<MarketLookDTO> listRunning();

    PageResult<MarketLookDTO> page(PageRequest pageRequest, String executionStatus, String symbol, String strategyId);

    MarketLookDTO getById(String id);

    MarketLookDTO create(MarketLookDTO dto);

    MarketLookDTO update(String id, MarketLookDTO dto);

    boolean delete(String id);

    /**
     * 仅更新执行状态；ENDED 时若 endedAt 为 null 则自动置为当前时间
     */
    MarketLookDTO patchStatus(String id, String executionStatus, LocalDateTime endedAt);
}
