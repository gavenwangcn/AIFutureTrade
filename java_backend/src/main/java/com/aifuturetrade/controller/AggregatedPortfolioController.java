package com.aifuturetrade.controller;

import com.aifuturetrade.service.ModelService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * 控制器：聚合投资组合
 * 提供独立的聚合投资组合接口路径，兼容前端调用
 */
@RestController
@RequestMapping("/api")
@Api(tags = "聚合投资组合")
public class AggregatedPortfolioController {

    @Autowired
    private ModelService modelService;

    /**
     * 获取聚合投资组合数据（所有模型）
     * 前端调用路径：/api/aggregated/portfolio
     * @return 聚合投资组合数据
     */
    @GetMapping("/aggregated/portfolio")
    @ApiOperation("获取聚合投资组合数据")
    public ResponseEntity<Map<String, Object>> getAggregatedPortfolio() {
        Map<String, Object> result = modelService.getAggregatedPortfolio();
        return new ResponseEntity<>(result, HttpStatus.OK);
    }
}

