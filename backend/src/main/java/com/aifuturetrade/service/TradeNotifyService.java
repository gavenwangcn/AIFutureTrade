package com.aifuturetrade.service;

import com.aifuturetrade.common.util.PageRequest;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.service.dto.TradeNotifyDTO;

import java.util.List;

/**
 * 交易通知查询（由 Python 盯盘服务写入 trade_notify）
 */
public interface TradeNotifyService {

    TradeNotifyDTO getById(Long id);

    /**
     * 某盯盘任务下的通知记录，按创建时间倒序；limit 建议 1–200。
     */
    List<TradeNotifyDTO> listByMarketLookId(String marketLookId, int limit);

    PageResult<TradeNotifyDTO> page(
            PageRequest pageRequest,
            String notifyType,
            String marketLookId,
            String strategyId,
            String symbol);
}
