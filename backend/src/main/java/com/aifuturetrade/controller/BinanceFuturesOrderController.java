package com.aifuturetrade.controller;

import com.aifuturetrade.service.BinanceFuturesOrderService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * 控制器：币安期货订单
 */
@RestController
@RequestMapping("/api/binance-futures-order")
@Tag(name = "币安期货订单", description = "币安期货订单管理接口")
public class BinanceFuturesOrderController {

    @Autowired
    private BinanceFuturesOrderService binanceFuturesOrderService;

    /**
     * 一键卖出持仓合约
     */
    @PostMapping("/sell-position")
    @Operation(summary = "一键卖出持仓合约")
    public ResponseEntity<Map<String, Object>> sellPosition(
            @RequestParam(value = "modelId") String modelId,
            @RequestParam(value = "symbol") String symbol) {
        try {
            Map<String, Object> result = binanceFuturesOrderService.sellPosition(modelId, symbol);
            return new ResponseEntity<>(result, HttpStatus.OK);
        } catch (Exception e) {
            Map<String, Object> errorResult = new java.util.HashMap<>();
            errorResult.put("success", false);
            errorResult.put("error", e.getMessage());
            return new ResponseEntity<>(errorResult, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
}

