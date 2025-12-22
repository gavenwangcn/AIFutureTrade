package com.aifuturetrade.controller;

import com.aifuturetrade.service.StrategyService;
import com.aifuturetrade.service.dto.StrategyDTO;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.common.util.PageRequest;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 控制器：策略管理
 * 处理策略相关的HTTP请求
 */
@RestController
@RequestMapping("/api/strategies")
@Api(tags = "策略管理")
public class StrategyController {
    private static final Logger logger = LoggerFactory.getLogger(StrategyController.class);

    @Autowired
    private StrategyService strategyService;

    /**
     * 获取所有策略
     * @return 策略列表
     */
    @GetMapping
    @ApiOperation("获取所有策略")
    public ResponseEntity<List<StrategyDTO>> getAllStrategies() {
        logger.info("开始获取所有策略");
        List<StrategyDTO> strategies = strategyService.getAllStrategies();
        logger.info("获取所有策略成功，共 {} 条记录", strategies.size());
        return new ResponseEntity<>(strategies, HttpStatus.OK);
    }

    /**
     * 根据ID获取策略
     * @param id 策略ID
     * @return 策略
     */
    @GetMapping("/{id}")
    @ApiOperation("根据ID获取策略")
    public ResponseEntity<StrategyDTO> getStrategyById(@PathVariable String id) {
        logger.info("开始根据ID获取策略，ID: {}", id);
        StrategyDTO strategy = strategyService.getStrategyById(id);
        if (strategy != null) {
            logger.info("根据ID获取策略成功，策略名称: {}", strategy.getName());
            return new ResponseEntity<>(strategy, HttpStatus.OK);
        } else {
            logger.info("根据ID获取策略失败，未找到ID为 {} 的策略", id);
            return new ResponseEntity<>(HttpStatus.NOT_FOUND);
        }
    }

    /**
     * 根据条件查询策略（支持名称和类型筛选）
     * @param name 策略名称（可选，模糊查询）
     * @param type 策略类型（可选，buy/sell）
     * @return 策略列表
     */
    @GetMapping("/search")
    @ApiOperation("根据条件查询策略")
    public ResponseEntity<List<StrategyDTO>> searchStrategies(
            @RequestParam(required = false) String name,
            @RequestParam(required = false) String type) {
        logger.info("开始根据条件查询策略，名称: {}, 类型: {}", name, type);
        List<StrategyDTO> strategies = strategyService.getStrategiesByCondition(name, type);
        logger.info("根据条件查询策略成功，共 {} 条记录", strategies.size());
        return new ResponseEntity<>(strategies, HttpStatus.OK);
    }

    /**
     * 分页查询策略
     * @param pageNum 页码（从1开始）
     * @param pageSize 每页大小
     * @param name 策略名称（可选）
     * @param type 策略类型（可选）
     * @return 分页查询结果
     */
    @GetMapping("/page")
    @ApiOperation("分页查询策略")
    public ResponseEntity<PageResult<StrategyDTO>> getStrategiesByPage(
            @RequestParam(defaultValue = "1") Integer pageNum,
            @RequestParam(defaultValue = "10") Integer pageSize,
            @RequestParam(required = false) String name,
            @RequestParam(required = false) String type) {
        logger.info("开始分页查询策略，页码: {}, 每页大小: {}, 名称: {}, 类型: {}", pageNum, pageSize, name, type);
        PageRequest pageRequest = new PageRequest();
        pageRequest.setPageNum(pageNum);
        pageRequest.setPageSize(pageSize);
        PageResult<StrategyDTO> result = strategyService.getStrategiesByPage(pageRequest, name, type);
        logger.info("分页查询策略成功，总记录数: {}, 当前页记录数: {}", result.getTotal(), result.getList().size());
        return new ResponseEntity<>(result, HttpStatus.OK);
    }

    /**
     * 添加新的策略
     * @param strategyDTO 策略信息
     * @return 新增的策略
     */
    @PostMapping
    @ApiOperation("添加新的策略")
    public ResponseEntity<Map<String, Object>> addStrategy(@RequestBody StrategyDTO strategyDTO) {
        logger.info("开始添加新策略，策略名称: {}, 类型: {}", strategyDTO.getName(), strategyDTO.getType());
        StrategyDTO addedStrategy = strategyService.addStrategy(strategyDTO);
        logger.info("添加策略成功，策略ID: {}", addedStrategy.getId());
        Map<String, Object> response = new HashMap<>();
        response.put("id", addedStrategy.getId());
        response.put("message", "Strategy added successfully");
        return new ResponseEntity<>(response, HttpStatus.CREATED);
    }

    /**
     * 更新策略
     * @param id 策略ID
     * @param strategyDTO 策略信息
     * @return 更新后的策略
     */
    @PutMapping("/{id}")
    @ApiOperation("更新策略")
    public ResponseEntity<Map<String, Object>> updateStrategy(
            @PathVariable String id,
            @RequestBody StrategyDTO strategyDTO) {
        logger.info("开始更新策略，策略ID: {}", id);
        strategyDTO.setId(id);
        StrategyDTO updatedStrategy = strategyService.updateStrategy(strategyDTO);
        logger.info("更新策略成功，策略ID: {}", updatedStrategy.getId());
        Map<String, Object> response = new HashMap<>();
        response.put("id", updatedStrategy.getId());
        response.put("message", "Strategy updated successfully");
        return new ResponseEntity<>(response, HttpStatus.OK);
    }

    /**
     * 删除策略
     * @param id 策略ID
     * @return 删除操作结果
     */
    @DeleteMapping("/{id}")
    @ApiOperation("删除策略")
    public ResponseEntity<Map<String, Object>> deleteStrategy(@PathVariable String id) {
        logger.info("开始删除策略，策略ID: {}", id);
        Boolean deleted = strategyService.deleteStrategy(id);
        Map<String, Object> response = new HashMap<>();
        if (deleted) {
            logger.info("删除策略成功，策略ID: {}", id);
            response.put("success", true);
            response.put("message", "Strategy deleted successfully");
            return new ResponseEntity<>(response, HttpStatus.OK);
        } else {
            logger.error("删除策略失败，策略ID: {}", id);
            response.put("success", false);
            response.put("error", "Failed to delete strategy");
            return new ResponseEntity<>(response, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

}

