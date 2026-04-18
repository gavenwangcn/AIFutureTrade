package com.aifuturetrade.service;

import com.aifuturetrade.common.util.PageRequest;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.service.dto.MarketLookDTO;
import com.aifuturetrade.service.dto.MarketLookTaskDetailDTO;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 盯盘任务 market_look
 */
public interface MarketLookService {

    List<MarketLookDTO> listAll();

    /**
     * 活跃盯盘任务：执行中 RUNNING 与异步通知发送中 SENDING
     */
    List<MarketLookDTO> listRunning();

    /**
     * 分页查询；时间范围为可选，闭区间 [from, to]（与列 started_at / ended_at 比较）。
     */
    PageResult<MarketLookDTO> page(
            PageRequest pageRequest,
            String executionStatus,
            String symbol,
            String strategyId,
            String detailSummary,
            LocalDateTime startedAtFrom,
            LocalDateTime startedAtTo,
            LocalDateTime endedAtFrom,
            LocalDateTime endedAtTo);

    MarketLookDTO getById(String id);

    /**
     * 盯盘任务详情：market_look 与关联的 trade_notify（含 extra_json）
     */
    MarketLookTaskDetailDTO getTaskDetail(String id);

    MarketLookDTO create(MarketLookDTO dto);

    MarketLookDTO update(String id, MarketLookDTO dto);

    /**
     * 删除盯盘任务；删除后会再次查询主键以确认行已从库中消失（不仅依赖 DELETE 返回值）。
     */
    MarketLookDeleteOutcome delete(String id);

    /**
     * 仅更新执行状态；ENDED 时若 endedAt 为 null 则自动置为当前时间
     */
    MarketLookDTO patchStatus(String id, String executionStatus, LocalDateTime endedAt);

    /**
     * 结束唯一一条执行中的盯盘任务（RUNNING/SENDING）。若无或多条则抛出 {@link IllegalArgumentException}。
     */
    MarketLookDTO finishSingleRunning(LocalDateTime endedAt);
}
