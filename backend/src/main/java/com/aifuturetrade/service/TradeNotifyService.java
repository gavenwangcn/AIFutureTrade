package com.aifuturetrade.service;

import com.aifuturetrade.common.util.PageRequest;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.service.dto.TradeNotifyDTO;

/**
 * 交易通知查询（由 Python 盯盘服务写入 trade_notify）
 */
public interface TradeNotifyService {

    TradeNotifyDTO getById(Long id);

    PageResult<TradeNotifyDTO> page(
            PageRequest pageRequest,
            String notifyType,
            String marketLookId,
            String strategyId,
            String symbol);
}
