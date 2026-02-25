package com.aifuturetrade.controller;

import com.aifuturetrade.common.util.PageRequest;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.service.AlgoOrderService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * 条件订单控制器
 */
@Slf4j
@RestController
@RequestMapping("/api/algo-orders")
@Tag(name = "条件订单管理", description = "条件订单相关API")
public class AlgoOrderController {
    
    @Autowired
    private AlgoOrderService algoOrderService;
    
    /**
     * 根据模型ID分页查询条件订单
     * 
     * @param modelId 模型ID
     * @param page 页码，从1开始，默认为1
     * @param pageSize 每页记录数，默认为10
     * @return 分页的条件订单列表
     */
    @GetMapping("/model/{modelId}")
    @Operation(summary = "根据模型ID分页查询条件订单")
    public ResponseEntity<PageResult<Map<String, Object>>> getAlgoOrdersByModelId(
            @Parameter(description = "模型ID", required = true) @PathVariable(value = "modelId") String modelId,
            @Parameter(description = "页码", required = false) @RequestParam(value = "page", defaultValue = "1") Integer page,
            @Parameter(description = "每页记录数", required = false) @RequestParam(value = "pageSize", defaultValue = "10") Integer pageSize) {
        log.debug("[AlgoOrderController] 查询条件订单: modelId={}, page={}, pageSize={}", modelId, page, pageSize);
        
        PageRequest pageRequest = new PageRequest();
        pageRequest.setPageNum(page);
        pageRequest.setPageSize(pageSize);
        
        PageResult<Map<String, Object>> result = algoOrderService.getAlgoOrdersByPage(modelId, pageRequest);
        return new ResponseEntity<>(result, HttpStatus.OK);
    }
}
