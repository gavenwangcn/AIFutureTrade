package com.aifuturetrade.binanceservice.controller;

import com.aifuturetrade.binanceservice.service.MarketDataService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 市场数据控制器
 * 提供币安期货市场数据查询API
 */
@Slf4j
@RestController
@RequestMapping({"/api/market-data", "/api/market"})
@Tag(name = "市场数据管理", description = "市场数据管理接口")
public class MarketDataController {

    @Autowired
    private MarketDataService marketDataService;

    /**
     * 获取指定交易对的24小时价格变动统计
     */
    @PostMapping("/24h-ticker")
    @Operation(summary = "获取24小时价格变动统计")
    public ResponseEntity<Map<String, Object>> get24hTicker(
            @Parameter(description = "交易对符号列表", required = true) @RequestBody List<String> symbols) {
        log.debug("[MarketDataController] 接收到24小时统计请求: symbols数量={}", symbols != null ? symbols.size() : 0);
        try {
            Map<String, Map<String, Object>> result = marketDataService.get24hTicker(symbols);
            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("data", result);
            return new ResponseEntity<>(response, HttpStatus.OK);
        } catch (Exception e) {
            log.error("[MarketDataController] 获取24小时统计失败: {}", e.getMessage(), e);
            Map<String, Object> errorResponse = new HashMap<>();
            errorResponse.put("success", false);
            errorResponse.put("message", "获取24小时统计失败: " + e.getMessage());
            return new ResponseEntity<>(errorResponse, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * 获取指定交易对的实时价格
     */
    @PostMapping("/symbol-prices")
    @Operation(summary = "获取实时价格")
    public ResponseEntity<Map<String, Object>> getSymbolPrices(
            @Parameter(description = "交易对符号列表", required = true) @RequestBody List<String> symbols) {
        log.debug("[MarketDataController] 接收到实时价格请求: symbols数量={}", symbols != null ? symbols.size() : 0);
        try {
            Map<String, Map<String, Object>> result = marketDataService.getSymbolPrices(symbols);
            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("data", result);
            return new ResponseEntity<>(response, HttpStatus.OK);
        } catch (Exception e) {
            log.error("[MarketDataController] 获取实时价格失败: {}", e.getMessage(), e);
            Map<String, Object> errorResponse = new HashMap<>();
            errorResponse.put("success", false);
            errorResponse.put("message", "获取实时价格失败: " + e.getMessage());
            return new ResponseEntity<>(errorResponse, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * 获取K线数据
     */
    @GetMapping("/klines")
    @Operation(summary = "获取K线数据")
    public ResponseEntity<Map<String, Object>> getKlines(
            @Parameter(description = "交易对符号", required = true) @RequestParam(value = "symbol") String symbol,
            @Parameter(description = "K线间隔", required = true) @RequestParam(value = "interval") String interval,
            @Parameter(description = "返回的K线数量", required = false) @RequestParam(value = "limit", required = false) Integer limit,
            @Parameter(description = "起始时间戳（毫秒）", required = false) @RequestParam(value = "startTime", required = false) Long startTime,
            @Parameter(description = "结束时间戳（毫秒）", required = false) @RequestParam(value = "endTime", required = false) Long endTime) {
        log.debug("[MarketDataController] 接收到K线数据请求: symbol={}, interval={}, limit={}", 
                symbol, interval, limit);
        try {
            List<Map<String, Object>> result = marketDataService.getKlines(symbol, interval, limit, startTime, endTime);
            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("data", result);
            return new ResponseEntity<>(response, HttpStatus.OK);
        } catch (Exception e) {
            log.error("[MarketDataController] 获取K线数据失败: {}", e.getMessage(), e);
            Map<String, Object> errorResponse = new HashMap<>();
            errorResponse.put("success", false);
            errorResponse.put("message", "获取K线数据失败: " + e.getMessage());
            return new ResponseEntity<>(errorResponse, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * 格式化交易对符号
     */
    @GetMapping("/format-symbol")
    @Operation(summary = "格式化交易对符号")
    public ResponseEntity<Map<String, Object>> formatSymbol(
            @Parameter(description = "基础交易对符号", required = true) @RequestParam(value = "baseSymbol") String baseSymbol) {
        log.debug("[MarketDataController] 接收到格式化符号请求: baseSymbol={}", baseSymbol);
        try {
            String result = marketDataService.formatSymbol(baseSymbol);
            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("data", result);
            return new ResponseEntity<>(response, HttpStatus.OK);
        } catch (Exception e) {
            log.error("[MarketDataController] 格式化符号失败: {}", e.getMessage(), e);
            Map<String, Object> errorResponse = new HashMap<>();
            errorResponse.put("success", false);
            errorResponse.put("message", "格式化符号失败: " + e.getMessage());
            return new ResponseEntity<>(errorResponse, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * 获取跌幅榜
     */
    @GetMapping("/leaderboard/losers")
    @Operation(summary = "获取跌幅榜")
    public ResponseEntity<Map<String, Object>> getMarketLeaderboardLosers(
            @Parameter(description = "返回的数据条数限制", required = false) 
            @RequestParam(value = "limit", required = false) Integer limit) {
        log.debug("[MarketDataController] 接收到跌幅榜请求: limit={}", limit);
        try {
            Map<String, Object> result = marketDataService.getMarketLeaderboardLosers(limit);
            return new ResponseEntity<>(result, HttpStatus.OK);
        } catch (Exception e) {
            log.error("[MarketDataController] 获取跌幅榜失败: {}", e.getMessage(), e);
            Map<String, Object> errorResponse = new HashMap<>();
            errorResponse.put("losers", new java.util.ArrayList<>());
            errorResponse.put("timestamp", System.currentTimeMillis());
            return new ResponseEntity<>(errorResponse, HttpStatus.OK);
        }
    }
}

