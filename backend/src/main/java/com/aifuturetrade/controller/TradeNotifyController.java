package com.aifuturetrade.controller;

import com.aifuturetrade.common.util.PageRequest;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.service.TradeNotifyService;
import com.aifuturetrade.service.dto.TradeNotifyDTO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * 交易通知 trade_notify 查询接口（写入由 Python 盯盘等服务完成）
 */
@RestController
@RequestMapping("/api/trade-notify")
@Tag(name = "交易通知", description = "trade_notify 分页与详情")
public class TradeNotifyController {

    @Autowired
    private TradeNotifyService tradeNotifyService;

    @GetMapping("/{id}")
    @Operation(summary = "按主键查询交易通知")
    public ResponseEntity<TradeNotifyDTO> getById(@PathVariable("id") Long id) {
        TradeNotifyDTO dto = tradeNotifyService.getById(id);
        return dto != null ? ResponseEntity.ok(dto) : ResponseEntity.notFound().build();
    }

    @GetMapping("/page")
    @Operation(summary = "分页查询交易通知")
    public ResponseEntity<PageResult<TradeNotifyDTO>> page(
            @RequestParam(value = "pageNum", defaultValue = "1") Integer pageNum,
            @RequestParam(value = "pageSize", defaultValue = "10") Integer pageSize,
            @Parameter(description = "如 LOOK")
            @RequestParam(value = "notify_type", required = false) String notifyType,
            @RequestParam(value = "market_look_id", required = false) String marketLookId,
            @RequestParam(value = "strategy_id", required = false) String strategyId,
            @RequestParam(value = "symbol", required = false) String symbol) {
        PageRequest pr = new PageRequest();
        pr.setPageNum(pageNum);
        pr.setPageSize(pageSize);
        return ResponseEntity.ok(tradeNotifyService.page(pr, notifyType, marketLookId, strategyId, symbol));
    }
}
