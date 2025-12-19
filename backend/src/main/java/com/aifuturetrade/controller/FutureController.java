package com.aifuturetrade.controller;

import com.aifuturetrade.service.FutureService;
import com.aifuturetrade.service.dto.FutureDTO;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.common.util.PageRequest;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 控制器：合约配置
 * 处理合约配置相关的HTTP请求
 */
@RestController
@RequestMapping("/api/futures")
@Api(tags = "合约配置管理")
public class FutureController {

    @Autowired
    private FutureService futureService;

    /**
     * 获取所有合约配置
     * @return 合约配置列表
     */
    @GetMapping
    @ApiOperation("获取所有合约配置")
    public ResponseEntity<List<FutureDTO>> listFutures() {
        List<FutureDTO> futures = futureService.getAllFutures();
        return new ResponseEntity<>(futures, HttpStatus.OK);
    }

    /**
     * 添加新的合约配置
     * @param futureDTO 合约配置信息
     * @return 新增的合约配置
     */
    @PostMapping
    @ApiOperation("添加新的合约配置")
    public ResponseEntity<FutureDTO> addFutureConfig(@RequestBody FutureDTO futureDTO) {
        FutureDTO addedFuture = futureService.addFuture(futureDTO);
        return new ResponseEntity<>(addedFuture, HttpStatus.CREATED);
    }

    /**
     * 删除合约配置
     * @param futureId 合约ID
     * @return 删除操作结果
     */
    @DeleteMapping("/{futureId}")
    @ApiOperation("删除合约配置")
    public ResponseEntity<Map<String, Object>> deleteFutureConfig(@PathVariable Integer futureId) {
        Boolean deleted = futureService.deleteFuture(futureId);
        Map<String, Object> response = new HashMap<>();
        if (deleted) {
            response.put("success", true);
            response.put("message", "Future deleted successfully");
            return new ResponseEntity<>(response, HttpStatus.OK);
        } else {
            response.put("success", false);
            response.put("error", "Failed to delete future");
            return new ResponseEntity<>(response, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * 获取所有合约符号列表
     * @return 合约符号列表
     */
    @GetMapping("/symbols")
    @ApiOperation("获取所有合约符号列表")
    public ResponseEntity<List<String>> getTrackedSymbols() {
        List<String> symbols = futureService.getTrackedSymbols();
        return new ResponseEntity<>(symbols, HttpStatus.OK);
    }

}