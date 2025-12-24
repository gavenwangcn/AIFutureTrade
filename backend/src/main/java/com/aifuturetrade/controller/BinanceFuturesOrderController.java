package com.aifuturetrade.controller;

import com.aifuturetrade.service.BinanceFuturesOrderService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
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
@Api(tags = "币安期货订单")
public class BinanceFuturesOrderController {

    @Autowired
    private BinanceFuturesOrderService binanceFuturesOrderService;

    /**
     * 一键卖出持仓合约
     */
    @PostMapping("/sell-position")
    @ApiOperation("一键卖出持仓合约")
    public ResponseEntity<Map<String, Object>> sellPosition(
            @RequestParam String modelId,
            @RequestParam String symbol) {
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

