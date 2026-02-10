package com.aifuturetrade.controller;

import com.aifuturetrade.service.AiProviderService;
import com.aifuturetrade.service.StrategyCodeTesterService;
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
 * 控制器：AI提供方服务
 * 处理AI调用相关的HTTP请求
 */
@Slf4j
@RestController
@RequestMapping("/api/ai")
@Tag(name = "AI提供方服务", description = "AI提供方服务接口")
public class AiProviderController {

    @Autowired
    private AiProviderService aiProviderService;
    
    @Autowired
    private StrategyCodeTesterService strategyCodeTesterService;

    /**
     * 从提供方API获取可用的模型列表
     * @param request 包含providerId的请求体
     * @return 可用模型列表
     */
    @PostMapping("/models")
    @Operation(summary = "从提供方API获取可用的模型列表")
    public ResponseEntity<Map<String, Object>> fetchModels(@RequestBody Map<String, String> request) {
        String providerId = request.get("providerId");
        
        if (providerId == null) {
            Map<String, Object> error = new HashMap<>();
            error.put("error", "Provider ID is required");
            return new ResponseEntity<>(error, HttpStatus.BAD_REQUEST);
        }
        
        try {
            List<String> models = aiProviderService.fetchModels(providerId);
            Map<String, Object> response = new HashMap<>();
            response.put("models", models);
            return new ResponseEntity<>(response, HttpStatus.OK);
        } catch (Exception e) {
            Map<String, Object> error = new HashMap<>();
            error.put("error", "Failed to fetch models: " + e.getMessage());
            return new ResponseEntity<>(error, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * 生成策略代码
     * @param request 包含providerId、modelName、strategyContext、strategyType的请求体
     * @return 生成的策略代码
     */
    @PostMapping("/generate-strategy-code")
    @Operation(summary = "生成策略代码")
    public ResponseEntity<Map<String, Object>> generateStrategyCode(@RequestBody Map<String, String> request) {
        String providerId = request.get("providerId");
        String modelName = request.get("modelName");
        String strategyContext = request.get("strategyContext");
        String strategyType = request.get("strategyType");

        if (providerId == null || modelName == null || strategyContext == null || strategyType == null) {
            Map<String, Object> error = new HashMap<>();
            error.put("error", "providerId, modelName, strategyContext, and strategyType are required");
            return new ResponseEntity<>(error, HttpStatus.BAD_REQUEST);
        }

        if (!strategyType.equals("buy") && !strategyType.equals("sell")) {
            Map<String, Object> error = new HashMap<>();
            error.put("error", "strategyType must be 'buy' or 'sell'");
            return new ResponseEntity<>(error, HttpStatus.BAD_REQUEST);
        }

        try {
            String strategyCode = aiProviderService.generateStrategyCode(
                    providerId, modelName, strategyContext, strategyType);

            log.debug("[生成策略代码] 生成的策略代码: {}", strategyCode);

            // 自动测试生成的策略代码
            String strategyName = request.get("strategyName");
            if (strategyName == null || strategyName.trim().isEmpty()) {
                strategyName = "新" + ("buy".equals(strategyType) ? "买入" : "卖出") + "策略";
            }

            Map<String, Object> testResult = strategyCodeTesterService.testStrategyCode(
                    strategyCode, strategyType, strategyName);

            boolean testPassed = (Boolean) testResult.get("passed");
            log.info("[生成策略代码] 策略代码测试完成: testPassed={}", testPassed);

            Map<String, Object> response = new HashMap<>();
            response.put("strategyCode", strategyCode);
            response.put("testResult", testResult);
            response.put("testPassed", testPassed);

            return new ResponseEntity<>(response, HttpStatus.OK);
        } catch (Exception e) {
            Map<String, Object> error = new HashMap<>();
            error.put("error", "Failed to generate strategy code: " + e.getMessage());
            log.error("[生成策略代码] 生成策略代码失败: {}", e.getMessage(), e);
            return new ResponseEntity<>(error, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
}

