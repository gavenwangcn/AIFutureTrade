package com.aifuturetrade.controller;

import com.aifuturetrade.service.MarketService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
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
@Api(tags = "市场数据管理")
public class MarketController {

    @Autowired
    private MarketService marketService;

    /**
     * 获取当前市场价格（仅返回配置的合约信息）
     */
    @GetMapping("/prices")
    @ApiOperation("获取当前市场价格")
    public ResponseEntity<Map<String, Map<String, Object>>> getMarketPrices() {
        Map<String, Map<String, Object>> prices = marketService.getMarketPrices();
        return new ResponseEntity<>(prices, HttpStatus.OK);
    }

    /**
     * 获取技术指标
     */
    @GetMapping("/indicators/{symbol}")
    @ApiOperation("获取技术指标")
    public ResponseEntity<Map<String, Object>> getMarketIndicators(@PathVariable String symbol) {
        Map<String, Object> indicators = marketService.getMarketIndicators(symbol);
        return new ResponseEntity<>(indicators, HttpStatus.OK);
    }

    /**
     * 获取涨幅榜
     */
    @GetMapping("/leaderboard/gainers")
    @ApiOperation("获取涨幅榜")
    public ResponseEntity<Map<String, Object>> getMarketLeaderboardGainers(
            @RequestParam(required = false) Integer limit) {
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
    @ApiOperation("获取跌幅榜")
    public ResponseEntity<Map<String, Object>> getMarketLeaderboardLosers(
            @RequestParam(required = false) Integer limit) {
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
    @ApiOperation("获取涨跌幅榜（已废弃）")
    public ResponseEntity<Map<String, Object>> getMarketLeaderboard(
            @RequestParam(required = false) Integer limit,
            @RequestParam(required = false, defaultValue = "0") Integer force) {
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
    @ApiOperation("获取K线历史数据")
    public ResponseEntity<List<Map<String, Object>>> getMarketKlines(
            @RequestParam String symbol,
            @RequestParam(required = false, defaultValue = "5m") String interval,
            @RequestParam(required = false) Integer limit,
            @RequestParam(required = false) String start_time,
            @RequestParam(required = false) String end_time,
            @RequestParam(required = false) String startTime,
            @RequestParam(required = false) String endTime) {
        // 优先使用下划线命名（前端使用），如果没有则使用驼峰命名
        String startTimeParam = start_time != null ? start_time : startTime;
        String endTimeParam = end_time != null ? end_time : endTime;
        List<Map<String, Object>> klines = marketService.getMarketKlines(symbol, interval, limit, startTimeParam, endTimeParam);
        return new ResponseEntity<>(klines, HttpStatus.OK);
    }
}

