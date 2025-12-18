package com.aifuturetrade.controller;

import com.aifuturetrade.service.ModelService;
import com.aifuturetrade.service.dto.ModelDTO;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.common.util.PageRequest;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 控制器：交易模型
 * 处理交易模型相关的HTTP请求
 */
@RestController
@RequestMapping("/api/models")
@Api(tags = "交易模型管理")
public class ModelController {

    @Autowired
    private ModelService modelService;

    /**
     * 获取所有交易模型
     * @return 交易模型列表
     */
    @GetMapping
    @ApiOperation("获取所有交易模型")
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
    @ApiOperation("根据ID获取交易模型")
    public ResponseEntity<ModelDTO> getModelById(@PathVariable Integer modelId) {
        ModelDTO model = modelService.getModelById(modelId);
        return model != null ? new ResponseEntity<>(model, HttpStatus.OK) : new ResponseEntity<>(HttpStatus.NOT_FOUND);
    }

    /**
     * 添加新的交易模型
     * @param modelDTO 交易模型信息
     * @return 新增的交易模型
     */
    @PostMapping
    @ApiOperation("添加新的交易模型")
    public ResponseEntity<Map<String, Object>> addModel(@RequestBody ModelDTO modelDTO) {
        ModelDTO addedModel = modelService.addModel(modelDTO);
        return new ResponseEntity<>(Map.of(
                "id", addedModel.getId(),
                "message", "Model added successfully"
        ), HttpStatus.CREATED);
    }

    /**
     * 删除交易模型
     * @param modelId 模型ID
     * @return 删除操作结果
     */
    @DeleteMapping("/{modelId}")
    @ApiOperation("删除交易模型")
    public ResponseEntity<Map<String, Object>> deleteModel(@PathVariable Integer modelId) {
        Boolean deleted = modelService.deleteModel(modelId);
        if (deleted) {
            return new ResponseEntity<>(Map.of(
                    "success", true,
                    "message", "Model deleted successfully"
            ), HttpStatus.OK);
        } else {
            return new ResponseEntity<>(Map.of(
                    "success", false,
                    "error", "Failed to delete model"
            ), HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * 获取模型的投资组合数据
     * @param modelId 模型ID
     * @return 投资组合数据
     */
    @GetMapping("/{modelId}/portfolio")
    @ApiOperation("获取模型的投资组合数据")
    public ResponseEntity<Map<String, Object>> getPortfolio(@PathVariable Integer modelId) {
        Map<String, Object> portfolio = modelService.getPortfolio(modelId);
        return new ResponseEntity<>(portfolio, HttpStatus.OK);
    }

    /**
     * 获取模型的持仓合约symbol列表
     * @param modelId 模型ID
     * @return 持仓合约symbol列表
     */
    @GetMapping("/{modelId}/portfolio/symbols")
    @ApiOperation("获取模型的持仓合约symbol列表")
    public ResponseEntity<Map<String, Object>> getModelPortfolioSymbols(@PathVariable Integer modelId) {
        Map<String, Object> symbols = modelService.getModelPortfolioSymbols(modelId);
        return new ResponseEntity<>(symbols, HttpStatus.OK);
    }

    /**
     * 获取模型的交易历史记录
     * @param modelId 模型ID
     * @param limit 返回记录数限制
     * @return 交易历史记录
     */
    @GetMapping("/{modelId}/trades")
    @ApiOperation("获取模型的交易历史记录")
    public ResponseEntity<List<Map<String, Object>>> getTrades(@PathVariable Integer modelId, @RequestParam(defaultValue = "10") Integer limit) {
        List<Map<String, Object>> trades = modelService.getTrades(modelId, limit);
        return new ResponseEntity<>(trades, HttpStatus.OK);
    }

    /**
     * 获取模型的对话历史记录
     * @param modelId 模型ID
     * @param limit 返回记录数限制
     * @return 对话历史记录
     */
    @GetMapping("/{modelId}/conversations")
    @ApiOperation("获取模型的对话历史记录")
    public ResponseEntity<List<Map<String, Object>>> getConversations(@PathVariable Integer modelId, @RequestParam(defaultValue = "5") Integer limit) {
        List<Map<String, Object>> conversations = modelService.getConversations(modelId, limit);
        return new ResponseEntity<>(conversations, HttpStatus.OK);
    }

    /**
     * 获取模型的LLM API错误记录
     * @param modelId 模型ID
     * @param limit 返回记录数限制
     * @return LLM API错误记录
     */
    @GetMapping("/{modelId}/llm-api-errors")
    @ApiOperation("获取模型的LLM API错误记录")
    public ResponseEntity<List<Map<String, Object>>> getLlmApiErrors(@PathVariable Integer modelId, @RequestParam(defaultValue = "10") Integer limit) {
        List<Map<String, Object>> errors = modelService.getLlmApiErrors(modelId, limit);
        return new ResponseEntity<>(errors, HttpStatus.OK);
    }

    /**
     * 获取模型的提示词配置
     * @param modelId 模型ID
     * @return 提示词配置
     */
    @GetMapping("/{modelId}/prompts")
    @ApiOperation("获取模型的提示词配置")
    public ResponseEntity<Map<String, Object>> getModelPrompts(@PathVariable Integer modelId) {
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
    @ApiOperation("更新模型的提示词配置")
    public ResponseEntity<Map<String, Object>> updateModelPrompts(@PathVariable Integer modelId, @RequestBody Map<String, String> prompts) {
        String buyPrompt = prompts.get("buy_prompt");
        String sellPrompt = prompts.get("sell_prompt");
        Map<String, Object> result = modelService.updateModelPrompts(modelId, buyPrompt, sellPrompt);
        return new ResponseEntity<>(result, HttpStatus.OK);
    }

}