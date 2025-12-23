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
        log.info("[StrategyDecisionController] 查询策略决策: modelId={}, page={}, pageSize={}", modelId, page, pageSize);
        
        try {
            PageRequest pageRequest = new PageRequest();
            pageRequest.setPageNum(page);
            pageRequest.setPageSize(pageSize);
            
            log.debug("[StrategyDecisionController] 调用Service查询策略决策: modelId={}, pageRequest={}", modelId, pageRequest);
            PageResult<Map<String, Object>> result = strategyDecisionService.getDecisionsByPage(modelId, pageRequest);
            
            log.info("[StrategyDecisionController] 查询成功: modelId={}, total={}, dataSize={}", 
                    modelId, result.getTotal(), result.getData() != null ? result.getData().size() : 0);
            
            log.debug("[StrategyDecisionController] Service返回结果详情: pageNum={}, pageSize={}, totalPages={}", 
                    result.getPageNum(), result.getPageSize(), result.getTotalPages());
            
            if (result.getData() != null && !result.getData().isEmpty()) {
                log.debug("[StrategyDecisionController] 第一条决策数据示例: {}", result.getData().get(0));
            } else {
                log.debug("[StrategyDecisionController] 查询结果为空，没有找到策略决策记录");
            }
            
            return new ResponseEntity<>(result, HttpStatus.OK);
        } catch (Exception e) {
            log.error("[StrategyDecisionController] 查询策略决策失败: modelId={}, page={}, pageSize={}, error={}", 
                    modelId, page, pageSize, e.getMessage(), e);
            PageResult<Map<String, Object>> errorResult = PageResult.build(new java.util.ArrayList<>(), 0L, page, pageSize);
            return new ResponseEntity<>(errorResult, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

}

