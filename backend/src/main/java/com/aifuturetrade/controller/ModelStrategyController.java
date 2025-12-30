package com.aifuturetrade.controller;

import com.aifuturetrade.service.ModelStrategyService;
import com.aifuturetrade.service.dto.ModelStrategyDTO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 控制器：模型关联策略管理
 * 处理模型关联策略相关的HTTP请求
 */
@RestController
@RequestMapping("/api/model-strategies")
@Tag(name = "模型关联策略管理", description = "模型关联策略管理接口")
public class ModelStrategyController {

    @Autowired
    private ModelStrategyService modelStrategyService;

    /**
     * 获取所有模型策略关联
     * @return 模型策略关联列表
     */
    @GetMapping
    @Operation(summary = "获取所有模型策略关联")
    public ResponseEntity<List<ModelStrategyDTO>> getAllModelStrategies() {
        List<ModelStrategyDTO> modelStrategies = modelStrategyService.getAllModelStrategies();
        return new ResponseEntity<>(modelStrategies, HttpStatus.OK);
    }

    /**
     * 根据ID获取模型策略关联
     * @param id 关联ID
     * @return 模型策略关联
     */
    @GetMapping("/{id}")
    @Operation(summary = "根据ID获取模型策略关联")
    public ResponseEntity<ModelStrategyDTO> getModelStrategyById(@PathVariable String id) {
        ModelStrategyDTO modelStrategy = modelStrategyService.getModelStrategyById(id);
        return modelStrategy != null ? new ResponseEntity<>(modelStrategy, HttpStatus.OK) : new ResponseEntity<>(HttpStatus.NOT_FOUND);
    }

    /**
     * 根据模型ID获取模型策略关联
     * @param modelId 模型ID
     * @return 模型策略关联列表
     */
    @GetMapping("/model/{modelId}")
    @Operation(summary = "根据模型ID获取模型策略关联")
    public ResponseEntity<List<ModelStrategyDTO>> getModelStrategiesByModelId(@PathVariable String modelId) {
        List<ModelStrategyDTO> modelStrategies = modelStrategyService.getModelStrategiesByModelId(modelId);
        return new ResponseEntity<>(modelStrategies, HttpStatus.OK);
    }

    /**
     * 根据策略ID获取模型策略关联
     * @param strategyId 策略ID
     * @return 模型策略关联列表
     */
    @GetMapping("/strategy/{strategyId}")
    @Operation(summary = "根据策略ID获取模型策略关联")
    public ResponseEntity<List<ModelStrategyDTO>> getModelStrategiesByStrategyId(@PathVariable String strategyId) {
        List<ModelStrategyDTO> modelStrategies = modelStrategyService.getModelStrategiesByStrategyId(strategyId);
        return new ResponseEntity<>(modelStrategies, HttpStatus.OK);
    }

    /**
     * 根据模型ID和类型获取模型策略关联
     * @param modelId 模型ID
     * @param type 策略类型
     * @return 模型策略关联列表
     */
    @GetMapping("/model/{modelId}/type/{type}")
    @Operation(summary = "根据模型ID和类型获取模型策略关联")
    public ResponseEntity<List<ModelStrategyDTO>> getModelStrategiesByModelIdAndType(
            @PathVariable String modelId,
            @PathVariable String type) {
        List<ModelStrategyDTO> modelStrategies = modelStrategyService.getModelStrategiesByModelIdAndType(modelId, type);
        return new ResponseEntity<>(modelStrategies, HttpStatus.OK);
    }

    /**
     * 添加新的模型策略关联
     * @param modelStrategyDTO 模型策略关联信息
     * @return 新增的模型策略关联
     */
    @PostMapping
    @Operation(summary = "添加新的模型策略关联")
    public ResponseEntity<Map<String, Object>> addModelStrategy(@RequestBody ModelStrategyDTO modelStrategyDTO) {
        try {
            ModelStrategyDTO addedModelStrategy = modelStrategyService.addModelStrategy(modelStrategyDTO);
            Map<String, Object> response = new HashMap<>();
            response.put("id", addedModelStrategy.getId());
            response.put("message", "Model strategy added successfully");
            return new ResponseEntity<>(response, HttpStatus.CREATED);
        } catch (RuntimeException e) {
            Map<String, Object> response = new HashMap<>();
            response.put("success", false);
            response.put("error", e.getMessage());
            return new ResponseEntity<>(response, HttpStatus.BAD_REQUEST);
        }
    }

    /**
     * 删除模型策略关联
     * @param id 关联ID
     * @return 删除操作结果
     */
    @DeleteMapping("/{id}")
    @Operation(summary = "删除模型策略关联")
    public ResponseEntity<Map<String, Object>> deleteModelStrategy(@PathVariable String id) {
        Boolean deleted = modelStrategyService.deleteModelStrategy(id);
        Map<String, Object> response = new HashMap<>();
        if (deleted) {
            response.put("success", true);
            response.put("message", "Model strategy deleted successfully");
            return new ResponseEntity<>(response, HttpStatus.OK);
        } else {
            response.put("success", false);
            response.put("error", "Failed to delete model strategy");
            return new ResponseEntity<>(response, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * 根据模型ID、策略ID和类型删除模型策略关联
     * @param modelId 模型ID
     * @param strategyId 策略ID
     * @param type 策略类型
     * @return 删除操作结果
     */
    @DeleteMapping("/model/{modelId}/strategy/{strategyId}/type/{type}")
    @Operation(summary = "根据模型ID、策略ID和类型删除模型策略关联")
    public ResponseEntity<Map<String, Object>> deleteModelStrategyByModelIdAndStrategyIdAndType(
            @PathVariable String modelId,
            @PathVariable String strategyId,
            @PathVariable String type) {
        Boolean deleted = modelStrategyService.deleteModelStrategyByModelIdAndStrategyIdAndType(modelId, strategyId, type);
        Map<String, Object> response = new HashMap<>();
        if (deleted) {
            response.put("success", true);
            response.put("message", "Model strategy deleted successfully");
            return new ResponseEntity<>(response, HttpStatus.OK);
        } else {
            response.put("success", false);
            response.put("error", "Failed to delete model strategy");
            return new ResponseEntity<>(response, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * 更新模型策略关联的优先级
     * @param id 关联ID
     * @param priority 优先级
     * @return 更新操作结果
     */
    @PutMapping("/{id}/priority")
    @Operation(summary = "更新模型策略关联的优先级")
    public ResponseEntity<Map<String, Object>> updateModelStrategyPriority(
            @PathVariable String id,
            @RequestBody Map<String, Integer> request) {
        try {
            Integer priority = request.get("priority");
            ModelStrategyDTO updated = modelStrategyService.updateModelStrategyPriority(id, priority);
            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("message", "Priority updated successfully");
            response.put("data", updated);
            return new ResponseEntity<>(response, HttpStatus.OK);
        } catch (RuntimeException e) {
            Map<String, Object> response = new HashMap<>();
            response.put("success", false);
            response.put("error", e.getMessage());
            return new ResponseEntity<>(response, HttpStatus.BAD_REQUEST);
        }
    }

    /**
     * 批量保存模型策略关联
     * @param modelId 模型ID
     * @param type 策略类型
     * @param request 请求体，包含模型策略关联列表
     * @return 保存操作结果
     */
    @PostMapping("/model/{modelId}/type/{type}/batch")
    @Operation(summary = "批量保存模型策略关联")
    public ResponseEntity<Map<String, Object>> batchSaveModelStrategies(
            @PathVariable String modelId,
            @PathVariable String type,
            @RequestBody Map<String, Object> request) {
        try {
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> strategies = (List<Map<String, Object>>) request.get("strategies");
            List<ModelStrategyDTO> modelStrategies = strategies.stream().map(map -> {
                ModelStrategyDTO dto = new ModelStrategyDTO();
                dto.setStrategyId((String) map.get("strategyId"));
                dto.setPriority(map.get("priority") != null ? ((Number) map.get("priority")).intValue() : 0);
                return dto;
            }).collect(java.util.stream.Collectors.toList());
            
            Boolean result = modelStrategyService.batchSaveModelStrategies(modelId, type, modelStrategies);
            Map<String, Object> response = new HashMap<>();
            response.put("success", result);
            response.put("message", "Model strategies saved successfully");
            return new ResponseEntity<>(response, HttpStatus.OK);
        } catch (Exception e) {
            Map<String, Object> response = new HashMap<>();
            response.put("success", false);
            response.put("error", e.getMessage());
            return new ResponseEntity<>(response, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

}

