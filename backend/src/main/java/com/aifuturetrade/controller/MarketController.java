package com.aifuturetrade.controller;

import com.aifuturetrade.service.MarketService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 控制器：市场数据
 */
@RestController
@RequestMapping("/api/market")
@Tag(name = "市场数据管理", description = "市场数据管理接口")
public class MarketController {

    @Autowired
    private MarketService marketService;

    /**
     * 获取当前市场价格（仅返回配置的合约信息）
     */
    @GetMapping("/prices")
    @Operation(summary = "获取当前市场价格")
    public ResponseEntity<Map<String, Map<String, Object>>> getMarketPrices() {
        Map<String, Map<String, Object>> prices = marketService.getMarketPrices();
        return new ResponseEntity<>(prices, HttpStatus.OK);
    }

    /**
     * 获取技术指标
     */
    @GetMapping("/indicators/{symbol}")
    @Operation(summary = "获取技术指标")
    public ResponseEntity<Map<String, Object>> getMarketIndicators(@PathVariable(value = "symbol") String symbol) {
        Map<String, Object> indicators = marketService.getMarketIndicators(symbol);
        return new ResponseEntity<>(indicators, HttpStatus.OK);
    }

    /**
     * 获取涨幅榜
     */
    @GetMapping("/leaderboard/gainers")
    @Operation(summary = "获取涨幅榜")
    public ResponseEntity<Map<String, Object>> getMarketLeaderboardGainers(
            @RequestParam(value = "limit", required = false) Integer limit) {
        if (limit == null) {
            limit = 10;
        }
        Map<String, Object> result = marketService.getMarketLeaderboardGainers(limit);
        return new ResponseEntity<>(result, HttpStatus.OK);
    }

    /**
     * 获取跌幅榜
     */
    @GetMapping("/leaderboard/losers")
    @Operation(summary = "获取跌幅榜")
    public ResponseEntity<Map<String, Object>> getMarketLeaderboardLosers(
            @RequestParam(value = "limit", required = false) Integer limit) {
        if (limit == null) {
            limit = 10;
        }
        Map<String, Object> result = marketService.getMarketLeaderboardLosers(limit);
        return new ResponseEntity<>(result, HttpStatus.OK);
    }

    /**
     * 获取涨跌幅榜（已废弃，保留以兼容旧代码）
     */
    @GetMapping("/leaderboard")
    @Operation(summary = "获取涨跌幅榜（已废弃）")
    public ResponseEntity<Map<String, Object>> getMarketLeaderboard(
            @RequestParam(value = "limit", required = false) Integer limit,
            @RequestParam(value = "force", required = false, defaultValue = "0") Integer force) {
        if (limit == null) {
            limit = 10;
        }
        Map<String, Object> result = marketService.getMarketLeaderboard(limit, force != null && force == 1);
        return new ResponseEntity<>(result, HttpStatus.OK);
    }

    /**
     * 获取K线历史数据
     * 支持两种参数命名方式：start_time/end_time（下划线）和startTime/endTime（驼峰）
     */
    @GetMapping("/klines")
    @Operation(summary = "获取K线历史数据")
    public ResponseEntity<List<Map<String, Object>>> getMarketKlines(
            @RequestParam(value = "symbol") String symbol,
            @RequestParam(value = "interval", required = false, defaultValue = "5m") String interval,
            @RequestParam(value = "limit", required = false) Integer limit,
            @RequestParam(value = "start_time", required = false) String start_time,
            @RequestParam(value = "end_time", required = false) String end_time,
            @RequestParam(value = "startTime", required = false) String startTime,
            @RequestParam(value = "endTime", required = false) String endTime) {
        // 优先使用下划线命名（前端使用），如果没有则使用驼峰命名
        String startTimeParam = start_time != null ? start_time : startTime;
        String endTimeParam = end_time != null ? end_time : endTime;
        List<Map<String, Object>> klines = marketService.getMarketKlines(symbol, interval, limit, startTimeParam, endTimeParam);
        return new ResponseEntity<>(klines, HttpStatus.OK);
    }
}

