package com.aifuturetrade.service.dto;

import lombok.Data;

import java.util.List;

/**
 * 盯盘任务详情：主表 + 关联的 trade_notify（含 extra_json 快照）
 */
@Data
public class MarketLookTaskDetailDTO {

    private MarketLookDTO marketLook;
    /** 按创建时间倒序，条数有上限 */
    private List<TradeNotifyDTO> tradeNotifies;
}
