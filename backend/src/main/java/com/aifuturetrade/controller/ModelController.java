package com.aifuturetrade.controller;

import com.aifuturetrade.service.ModelService;
import com.aifuturetrade.service.ModelStrategyService;
import com.aifuturetrade.service.StrategyService;
import com.aifuturetrade.service.dto.ModelDTO;
import com.aifuturetrade.service.dto.StrategyDTO;
import com.aifuturetrade.service.dto.ModelStrategyDTO;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.common.util.PageRequest;
import com.aifuturetrade.dao.mapper.ModelStrategyMapper;
import io.swagger.v3.oas.annotations.Operation;
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
 * 控制器：交易模型
 * 处理交易模型相关的HTTP请求
 */
@Slf4j
@RestController
@RequestMapping("/api/models")
@Tag(name = "交易模型管理", description = "交易模型管理接口")
public class ModelController {

    @Autowired
    private ModelService modelService;

    @Autowired
    private StrategyService strategyService;

    @Autowired
    private ModelStrategyService modelStrategyService;

    @Autowired
    private ModelStrategyMapper modelStrategyMapper;

    /**
     * 获取所有交易模型
     * @return 交易模型列表
     */
    @GetMapping
    @Operation(summary = "获取所有交易模型")
    public ResponseEntity<List<ModelDTO>> getModels() {
        List<ModelDTO> models = modelService.getAllModels();
        return new ResponseEntity<>(models, HttpStatus.OK);
    }

    /**
     * 根据ID获取交易模型
     * @param modelId 模型ID
     * @return 交易模型
     */
    @GetMapping("/{modelId}")
    @Operation(summary = "根据ID获取交易模型")
    public ResponseEntity<ModelDTO> getModelById(@PathVariable(value = "modelId") String modelId) {
        ModelDTO model = modelService.getModelById(modelId);
        if (model != null) {
            return new ResponseEntity<>(model, HttpStatus.OK);
        } else {
            return new ResponseEntity<>(HttpStatus.NOT_FOUND);
        }
    }

    /**
     * 添加新的交易模型
     * @param modelDTO 交易模型信息
     * @return 新增的交易模型
     */
    @PostMapping
    @Operation(summary = "添加新的交易模型")
    public ResponseEntity<Map<String, Object>> addModel(@RequestBody ModelDTO modelDTO) {
        ModelDTO addedModel = modelService.addModel(modelDTO);
        Map<String, Object> response = new HashMap<>();
        response.put("id", addedModel.getId());
        response.put("message", "Model added successfully");
        return new ResponseEntity<>(response, HttpStatus.CREATED);
    }

    /**
     * 删除交易模型
     * @param modelId 模型ID
     * @return 删除操作结果
     */
    @DeleteMapping("/{modelId}")
    @Operation(summary = "删除交易模型")
    public ResponseEntity<Map<String, Object>> deleteModel(@PathVariable(value = "modelId") String modelId) {
        Boolean deleted = modelService.deleteModel(modelId);
        Map<String, Object> response = new HashMap<>();
        if (deleted) {
            response.put("success", true);
            response.put("message", "Model deleted successfully");
            return new ResponseEntity<>(response, HttpStatus.OK);
        } else {
            response.put("success", false);
            response.put("error", "Failed to delete model");
            return new ResponseEntity<>(response, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * 获取模型的投资组合数据
     * @param modelId 模型ID
     * @return 投资组合数据
     */
    @GetMapping("/{modelId}/portfolio")
    @Operation(summary = "获取模型的投资组合数据")
    public ResponseEntity<Map<String, Object>> getPortfolio(@PathVariable(value = "modelId") String modelId) {
        Map<String, Object> portfolio = modelService.getPortfolio(modelId);
        return new ResponseEntity<>(portfolio, HttpStatus.OK);
    }

    /**
     * 获取模型的持仓合约symbol列表
     * @param modelId 模型ID
     * @return 持仓合约symbol列表
     */
    @GetMapping("/{modelId}/portfolio/symbols")
    @Operation(summary = "获取模型的持仓合约symbol列表")
    public ResponseEntity<Map<String, Object>> getModelPortfolioSymbols(@PathVariable(value = "modelId") String modelId) {
        Map<String, Object> symbols = modelService.getModelPortfolioSymbols(modelId);
        return new ResponseEntity<>(symbols, HttpStatus.OK);
    }

    /**
     * 获取模型的交易历史记录（分页）
     * @param modelId 模型ID
     * @param page 页码，从1开始，默认为1
     * @param pageSize 每页记录数，默认为10
     * @return 分页的交易历史记录
     */
    @GetMapping("/{modelId}/trades")
    @Operation(summary = "获取模型的交易历史记录（分页）")
    public ResponseEntity<PageResult<Map<String, Object>>> getTrades(
            @PathVariable(value = "modelId") String modelId,
            @RequestParam(value = "page", defaultValue = "1") Integer page,
            @RequestParam(value = "pageSize", defaultValue = "10") Integer pageSize) {
        PageRequest pageRequest = new PageRequest();
        pageRequest.setPageNum(page);
        pageRequest.setPageSize(pageSize);
        PageResult<Map<String, Object>> result = modelService.getTradesByPage(modelId, pageRequest);
        return new ResponseEntity<>(result, HttpStatus.OK);
    }

    /**
     * 获取模型的对话历史记录
     * @param modelId 模型ID
     * @param limit 返回记录数限制
     * @return 对话历史记录
     */
    @GetMapping("/{modelId}/conversations")
    @Operation(summary = "获取模型的对话历史记录")
    public ResponseEntity<List<Map<String, Object>>> getConversations(@PathVariable(value = "modelId") String modelId, @RequestParam(value = "limit", defaultValue = "20") Integer limit) {
        List<Map<String, Object>> conversations = modelService.getConversations(modelId, limit);
        return new ResponseEntity<>(conversations, HttpStatus.OK);
    }

    /**
     * 获取模型的提示词配置
     * @param modelId 模型ID
     * @return 提示词配置
     */
    @GetMapping("/{modelId}/prompts")
    @Operation(summary = "获取模型的提示词配置")
    public ResponseEntity<Map<String, Object>> getModelPrompts(@PathVariable(value = "modelId") String modelId) {
        Map<String, Object> prompts = modelService.getModelPrompts(modelId);
        return new ResponseEntity<>(prompts, HttpStatus.OK);
    }

    /**
     * 更新模型的提示词配置
     * @param modelId 模型ID
     * @param prompts 提示词配置
     * @return 更新操作结果
     */
    @PutMapping("/{modelId}/prompts")
    @Operation(summary = "更新模型的提示词配置")
    public ResponseEntity<Map<String, Object>> updateModelPrompts(@PathVariable(value = "modelId") String modelId, @RequestBody Map<String, String> prompts) {
        String buyPrompt = prompts.get("buy_prompt");
        String sellPrompt = prompts.get("sell_prompt");
        Map<String, Object> result = modelService.updateModelPrompts(modelId, buyPrompt, sellPrompt);
        return new ResponseEntity<>(result, HttpStatus.OK);
    }

    /**
     * 更新模型的批次配置
     * @param modelId 模型ID
     * @param batchConfig 批次配置
     * @return 更新操作结果
     */
    @PostMapping("/{modelId}/batch-config")
    @Operation(summary = "更新模型的批次配置")
    public ResponseEntity<Map<String, Object>> updateModelBatchConfig(@PathVariable(value = "modelId") String modelId, @RequestBody Map<String, Object> batchConfig) {
        Map<String, Object> result = modelService.updateModelBatchConfig(modelId, batchConfig);
        return new ResponseEntity<>(result, HttpStatus.OK);
    }

    /**
     * 更新模型的最大持仓数量
     * @param modelId 模型ID
     * @param requestBody 请求体，包含max_positions
     * @return 更新操作结果
     */
    @PostMapping("/{modelId}/max_positions")
    @Operation(summary = "更新模型的最大持仓数量")
    public ResponseEntity<Map<String, Object>> updateModelMaxPositions(@PathVariable(value = "modelId") String modelId, @RequestBody Map<String, Object> requestBody) {
        log.info("[ModelController] 更新模型最大持仓数量请求: modelId={}, requestBody={}", modelId, requestBody);
        Object maxPositionsObj = requestBody.get("max_positions");
        log.info("[ModelController] 从requestBody获取的max_positions值: value={}, type={}, isNull={}", 
                maxPositionsObj, 
                maxPositionsObj != null ? maxPositionsObj.getClass().getName() : "null",
                maxPositionsObj == null);
        if (maxPositionsObj == null) {
            Map<String, Object> errorResult = new HashMap<>();
            errorResult.put("success", false);
            errorResult.put("message", "max_positions is required");
            return new ResponseEntity<>(errorResult, HttpStatus.BAD_REQUEST);
        }
        Integer maxPositions;
        if (maxPositionsObj instanceof Number) {
            maxPositions = ((Number) maxPositionsObj).intValue();
        } else if (maxPositionsObj instanceof String) {
            try {
                maxPositions = Integer.parseInt((String) maxPositionsObj);
            } catch (NumberFormatException e) {
                Map<String, Object> errorResult = new HashMap<>();
                errorResult.put("success", false);
                errorResult.put("message", "Invalid max_positions format: " + maxPositionsObj);
                return new ResponseEntity<>(errorResult, HttpStatus.BAD_REQUEST);
            }
        } else {
            log.warn("[ModelController] max_positions类型无效: type={}, value={}", maxPositionsObj.getClass().getName(), maxPositionsObj);
            Map<String, Object> errorResult = new HashMap<>();
            errorResult.put("success", false);
            errorResult.put("message", "Invalid max_positions type: " + maxPositionsObj.getClass().getName());
            return new ResponseEntity<>(errorResult, HttpStatus.BAD_REQUEST);
        }
        log.info("[ModelController] 解析后的max_positions值: {}", maxPositions);
        Map<String, Object> result = modelService.updateModelMaxPositions(modelId, maxPositions);
        log.info("[ModelController] 更新模型最大持仓数量完成: modelId={}, maxPositions={}, result={}", modelId, maxPositions, result);
        return new ResponseEntity<>(result, HttpStatus.OK);
    }

    /**
     * 更新模型的杠杆倍数
     * @param modelId 模型ID
     * @param requestBody 请求体，包含leverage
     * @return 更新操作结果
     */
    @PostMapping("/{modelId}/leverage")
    @Operation(summary = "更新模型的杠杆倍数")
    public ResponseEntity<Map<String, Object>> updateModelLeverage(@PathVariable(value = "modelId") String modelId, @RequestBody Map<String, Object> requestBody) {
        Integer leverage = ((Number) requestBody.get("leverage")).intValue();
        Map<String, Object> result = modelService.updateModelLeverage(modelId, leverage);
        return new ResponseEntity<>(result, HttpStatus.OK);
    }

    /**
     * 更新模型的自动平仓百分比
     * @param modelId 模型ID
     * @param requestBody 请求体，包含auto_close_percent
     * @return 更新操作结果
     */
    @PostMapping("/{modelId}/auto_close_percent")
    @Operation(summary = "更新模型的自动平仓百分比")
    public ResponseEntity<Map<String, Object>> updateModelAutoClosePercent(@PathVariable(value = "modelId") String modelId, @RequestBody Map<String, Object> requestBody) {
        Object autoClosePercentObj = requestBody.get("auto_close_percent");
        Double autoClosePercent = null;
        if (autoClosePercentObj != null) {
            if (autoClosePercentObj instanceof Number) {
                autoClosePercent = ((Number) autoClosePercentObj).doubleValue();
            } else if (autoClosePercentObj instanceof String) {
                String str = (String) autoClosePercentObj;
                if (!str.isEmpty()) {
                    autoClosePercent = Double.parseDouble(str);
                }
            }
        }
        Map<String, Object> result = modelService.updateModelAutoClosePercent(modelId, autoClosePercent);
        return new ResponseEntity<>(result, HttpStatus.OK);
    }

    /**
     * 更新模型的API提供方和模型名称
     * @param modelId 模型ID
     * @param requestBody 请求体，包含provider_id和model_name
     * @return 更新操作结果
     */
    @PutMapping("/{modelId}/provider")
    @Operation(summary = "更新模型的API提供方和模型名称")
    public ResponseEntity<Map<String, Object>> updateModelProvider(@PathVariable(value = "modelId") String modelId, @RequestBody Map<String, Object> requestBody) {
        String providerId = (String) requestBody.get("provider_id");
        String modelName = (String) requestBody.get("model_name");
        Map<String, Object> result = modelService.updateModelProvider(modelId, providerId, modelName);
        return new ResponseEntity<>(result, HttpStatus.OK);
    }

    /**
     * 设置模型的自动交易开关
     * 兼容两种格式：
     * 1. {enabled: true} - 前端使用的格式，同时设置买入和卖出
     * 2. {auto_buy_enabled: true, auto_sell_enabled: true} - 分别设置买入和卖出
     * @param modelId 模型ID
     * @param requestBody 请求体
     * @return 更新操作结果
     */
    @PostMapping("/{modelId}/auto-trading")
    @Operation(summary = "设置模型的自动交易开关")
    public ResponseEntity<Map<String, Object>> setModelAutoTrading(@PathVariable(value = "modelId") String modelId, @RequestBody Map<String, Object> requestBody) {
        Boolean autoBuyEnabled;
        Boolean autoSellEnabled;
        
        // 兼容前端格式：{enabled: true}
        if (requestBody.containsKey("enabled")) {
            Object enabledObj = requestBody.get("enabled");
            Boolean enabled = enabledObj instanceof Boolean ? 
                    (Boolean) enabledObj : 
                    ((Number) enabledObj).intValue() == 1;
            autoBuyEnabled = enabled;
            autoSellEnabled = enabled;
        } else {
            // 兼容格式：{auto_buy_enabled: true, auto_sell_enabled: true}
            Object buyEnabledObj = requestBody.get("auto_buy_enabled");
            Object sellEnabledObj = requestBody.get("auto_sell_enabled");
            
            autoBuyEnabled = buyEnabledObj instanceof Boolean ? 
                    (Boolean) buyEnabledObj : 
                    buyEnabledObj != null && ((Number) buyEnabledObj).intValue() == 1;
            autoSellEnabled = sellEnabledObj instanceof Boolean ? 
                    (Boolean) sellEnabledObj : 
                    sellEnabledObj != null && ((Number) sellEnabledObj).intValue() == 1;
        }
        
        Map<String, Object> result = modelService.setModelAutoTrading(modelId, autoBuyEnabled, autoSellEnabled);
        return new ResponseEntity<>(result, HttpStatus.OK);
    }

    /**
     * 获取聚合投资组合数据（所有模型）
     * 支持两种路径：/api/models/aggregated/portfolio 和 /api/aggregated/portfolio
     * @return 聚合投资组合数据
     */
    @GetMapping("/aggregated/portfolio")
    @Operation(summary = "获取聚合投资组合数据")
    public ResponseEntity<Map<String, Object>> getAggregatedPortfolio() {
        Map<String, Object> result = modelService.getAggregatedPortfolio();
        return new ResponseEntity<>(result, HttpStatus.OK);
    }

    /**
     * 手动执行一次交易周期（同时执行买入和卖出）
     * @param modelId 模型ID
     * @return 交易执行结果
     */
    @PostMapping("/{modelId}/execute")
    @Operation(summary = "手动执行一次交易周期（同时执行买入和卖出）")
    public ResponseEntity<Map<String, Object>> executeTrading(@PathVariable(value = "modelId") String modelId) {
        Map<String, Object> result = modelService.executeTrading(modelId);
        return new ResponseEntity<>(result, HttpStatus.OK);
    }

    /**
     * 启用模型自动买入（设置 auto_buy_enabled = true）
     * @param modelId 模型ID
     * @return 更新结果
     */
    @PostMapping("/{modelId}/execute-buy")
    @Operation(summary = "启用模型自动买入")
    public ResponseEntity<Map<String, Object>> executeBuyTrading(@PathVariable(value = "modelId") String modelId) {
        Map<String, Object> result = modelService.executeBuyTrading(modelId);
        return new ResponseEntity<>(result, HttpStatus.OK);
    }

    /**
     * 启用模型自动卖出（设置 auto_sell_enabled = true）
     * @param modelId 模型ID
     * @return 更新结果
     */
    @PostMapping("/{modelId}/execute-sell")
    @Operation(summary = "启用模型自动卖出")
    public ResponseEntity<Map<String, Object>> executeSellTrading(@PathVariable(value = "modelId") String modelId) {
        Map<String, Object> result = modelService.executeSellTrading(modelId);
        return new ResponseEntity<>(result, HttpStatus.OK);
    }

    /**
     * 禁用模型的自动买入功能
     * @param modelId 模型ID
     * @return 更新后的自动买入状态
     */
    @PostMapping("/{modelId}/disable-buy")
    @Operation(summary = "禁用模型的自动买入功能")
    public ResponseEntity<Map<String, Object>> disableBuyTrading(@PathVariable(value = "modelId") String modelId) {
        Map<String, Object> result = modelService.disableBuyTrading(modelId);
        return new ResponseEntity<>(result, HttpStatus.OK);
    }

    /**
     * 禁用模型的自动卖出功能
     * @param modelId 模型ID
     * @return 更新后的自动卖出状态
     */
    @PostMapping("/{modelId}/disable-sell")
    @Operation(summary = "禁用模型的自动卖出功能")
    public ResponseEntity<Map<String, Object>> disableSellTrading(@PathVariable(value = "modelId") String modelId) {
        Map<String, Object> result = modelService.disableSellTrading(modelId);
        return new ResponseEntity<>(result, HttpStatus.OK);
    }

    /**
     * 获取模型策略配置页面所需的数据
     * 返回策略列表（支持搜索和分页）和当前模型已关联的策略列表
     * @param modelId 模型ID
     * @param name 策略名称（可选，模糊查询）
     * @param type 策略类型（可选，buy/sell）
     * @param pageNum 页码（从1开始，默认1）
     * @param pageSize 每页大小（默认10）
     * @return 策略配置数据
     */
    @GetMapping("/{modelId}/strategy-config")
    @Operation(summary = "获取模型策略配置数据")
    public ResponseEntity<Map<String, Object>> getModelStrategyConfig(
            @PathVariable(value = "modelId") String modelId,
            @RequestParam(value = "name", required = false) String name,
            @RequestParam(value = "type", required = false) String type,
            @RequestParam(value = "pageNum", defaultValue = "1") Integer pageNum,
            @RequestParam(value = "pageSize", defaultValue = "10") Integer pageSize) {
        // 过滤掉 "undefined" 字符串，转换为 null
        if (name != null && ("undefined".equalsIgnoreCase(name) || name.trim().isEmpty())) {
            name = null;
        }
        if (type != null && ("undefined".equalsIgnoreCase(type) || type.trim().isEmpty())) {
            type = null;
        }
        
        // 分页查询策略列表（支持搜索）
        PageRequest pageRequest = new PageRequest();
        pageRequest.setPageNum(pageNum);
        pageRequest.setPageSize(pageSize);
        PageResult<StrategyDTO> strategiesPage = strategyService.getStrategiesByPage(pageRequest, name, type);
        
        // 获取当前模型已关联的策略列表（包含策略详细信息）
        List<Map<String, Object>> modelStrategiesWithInfo = modelStrategyMapper.selectModelStrategiesWithStrategyInfoByModelId(modelId);
        
        // 构建返回数据
        Map<String, Object> result = new HashMap<>();
        result.put("strategies", strategiesPage.getData());
        result.put("total", strategiesPage.getTotal());
        result.put("pageNum", strategiesPage.getPageNum());
        result.put("pageSize", strategiesPage.getPageSize());
        result.put("totalPages", strategiesPage.getTotalPages());
        result.put("modelStrategies", modelStrategiesWithInfo);
        
        return new ResponseEntity<>(result, HttpStatus.OK);
    }

    /**
     * 批量保存模型策略配置
     * @param modelId 模型ID
     * @param requestBody 请求体，包含策略配置列表
     * @return 保存操作结果
     */
    @PostMapping("/{modelId}/strategy-config")
    @Operation(summary = "批量保存模型策略配置")
    public ResponseEntity<Map<String, Object>> saveModelStrategyConfig(
            @PathVariable(value = "modelId") String modelId,
            @RequestBody Map<String, Object> requestBody) {
        try {
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> strategies = (List<Map<String, Object>>) requestBody.get("strategies");
            
            if (strategies == null || strategies.isEmpty()) {
                // 如果没有策略，删除该模型的所有策略关联
                List<ModelStrategyDTO> existingStrategies = modelStrategyService.getModelStrategiesByModelId(modelId);
                for (ModelStrategyDTO existing : existingStrategies) {
                    modelStrategyService.deleteModelStrategy(existing.getId());
                }
                
                Map<String, Object> response = new HashMap<>();
                response.put("success", true);
                response.put("message", "模型策略配置保存成功");
                return new ResponseEntity<>(response, HttpStatus.OK);
            }
            
            // 按类型分组处理策略
            Map<String, List<Map<String, Object>>> strategiesByType = new HashMap<>();
            for (Map<String, Object> strategy : strategies) {
                String strategyId = (String) strategy.get("strategyId");
                
                // 获取策略信息以确定类型
                StrategyDTO strategyDTO = strategyService.getStrategyById(strategyId);
                if (strategyDTO == null) {
                    continue;
                }
                String type = strategyDTO.getType();
                
                strategiesByType.computeIfAbsent(type, k -> new java.util.ArrayList<>()).add(strategy);
            }
            
            // 为每种类型批量保存策略
            for (Map.Entry<String, List<Map<String, Object>>> entry : strategiesByType.entrySet()) {
                String type = entry.getKey();
                List<Map<String, Object>> typeStrategies = entry.getValue();
                
                List<ModelStrategyDTO> modelStrategies = typeStrategies.stream().map(map -> {
                    ModelStrategyDTO dto = new ModelStrategyDTO();
                    dto.setStrategyId((String) map.get("strategyId"));
                    dto.setPriority(map.get("priority") != null ? ((Number) map.get("priority")).intValue() : 0);
                    return dto;
                }).collect(java.util.stream.Collectors.toList());
                
                modelStrategyService.batchSaveModelStrategies(modelId, type, modelStrategies);
            }
            
            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("message", "模型策略配置保存成功");
            return new ResponseEntity<>(response, HttpStatus.OK);
        } catch (Exception e) {
            Map<String, Object> response = new HashMap<>();
            response.put("success", false);
            response.put("error", e.getMessage());
            return new ResponseEntity<>(response, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

}