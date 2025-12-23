package com.aifuturetrade.controller;

import com.aifuturetrade.service.StrategyDecisionService;
import com.aifuturetrade.common.util.PageRequest;
import com.aifuturetrade.common.util.PageResult;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import io.swagger.annotations.ApiParam;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * 控制器：策略决策
 */
@Slf4j
@RestController
@RequestMapping("/api/strategy-decisions")
@Api(tags = "策略决策管理")
public class StrategyDecisionController {

    @Autowired
    private StrategyDecisionService strategyDecisionService;

    /**
     * 根据模型ID查询策略决策记录（分页）
     * @param modelId 模型ID（UUID格式）
     * @param page 页码，从1开始，默认为1
     * @param pageSize 每页记录数，默认为10
     * @return 分页的策略决策记录
     */
    @GetMapping("/model/{modelId}")
    @ApiOperation("根据模型ID查询策略决策记录（分页）")
    public ResponseEntity<PageResult<Map<String, Object>>> getDecisionsByModelId(
            @ApiParam(value = "模型ID", required = true) @PathVariable String modelId,
            @ApiParam(value = "页码", required = false) @RequestParam(defaultValue = "1") Integer page,
            @ApiParam(value = "每页记录数", required = false) @RequestParam(defaultValue = "10") Integer pageSize) {
        try {
            PageRequest pageRequest = new PageRequest();
            pageRequest.setPageNum(page);
            pageRequest.setPageSize(pageSize);
            PageResult<Map<String, Object>> result = strategyDecisionService.getDecisionsByPage(modelId, pageRequest);
            return new ResponseEntity<>(result, HttpStatus.OK);
        } catch (Exception e) {
            log.error("Failed to get strategy decisions for model {}: {}", modelId, e.getMessage(), e);
            PageResult<Map<String, Object>> errorResult = PageResult.build(new java.util.ArrayList<>(), 0L, page, pageSize);
            return new ResponseEntity<>(errorResult, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

}

