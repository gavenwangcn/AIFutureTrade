package com.aifuturetrade.controller;

import com.aifuturetrade.service.ProviderService;
import com.aifuturetrade.service.dto.ProviderDTO;
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
 * 控制器：API提供方
 * 处理API提供方相关的HTTP请求
 */
@RestController
@RequestMapping("/api/providers")
@Tag(name = "API提供方管理", description = "API提供方管理接口")
public class ProviderController {

    @Autowired
    private ProviderService providerService;

    /**
     * 获取所有API提供方
     * @return API提供方列表
     */
    @GetMapping
    @Operation(summary = "获取所有API提供方")
    public ResponseEntity<List<ProviderDTO>> getAllProviders() {
        List<ProviderDTO> providers = providerService.getAllProviders();
        return new ResponseEntity<>(providers, HttpStatus.OK);
    }

    /**
     * 添加新的API提供方
     * @param providerDTO API提供方信息
     * @return 新增的API提供方
     */
    @PostMapping
    @Operation(summary = "添加新的API提供方")
    public ResponseEntity<ProviderDTO> addProvider(@RequestBody ProviderDTO providerDTO) {
        ProviderDTO addedProvider = providerService.addProvider(providerDTO);
        return new ResponseEntity<>(addedProvider, HttpStatus.CREATED);
    }

    /**
     * 删除API提供方
     * @param providerId 提供方ID
     * @return 删除操作结果
     */
    @DeleteMapping("/{providerId}")
    @Operation(summary = "删除API提供方")
    public ResponseEntity<Map<String, Object>> deleteProvider(@PathVariable(value = "providerId") String providerId) {
        Boolean deleted = providerService.deleteProvider(providerId);
        Map<String, Object> response = new HashMap<>();
        if (deleted) {
            response.put("success", true);
            response.put("message", "Provider deleted successfully");
            return new ResponseEntity<>(response, HttpStatus.OK);
        } else {
            response.put("success", false);
            response.put("error", "Failed to delete provider");
            return new ResponseEntity<>(response, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * 从提供方API获取可用的模型列表
     * @param request 包含apiUrl和apiKey的请求体
     * @return 可用模型列表
     */
    @PostMapping("/models")
    @Operation(summary = "从提供方API获取可用的模型列表")
    public ResponseEntity<Map<String, Object>> fetchProviderModels(@RequestBody Map<String, String> request) {
        String apiUrl = request.get("apiUrl");
        String apiKey = request.get("apiKey");
        
        if (apiUrl == null || apiKey == null) {
            Map<String, Object> error = new HashMap<>();
            error.put("error", "API URL and key are required");
            return new ResponseEntity<>(error, HttpStatus.BAD_REQUEST);
        }
        
        try {
            List<String> models = providerService.fetchProviderModels(apiUrl, apiKey);
            Map<String, Object> response = new HashMap<>();
            response.put("models", models);
            return new ResponseEntity<>(response, HttpStatus.OK);
        } catch (Exception e) {
            Map<String, Object> error = new HashMap<>();
            error.put("error", "Failed to fetch models: " + e.getMessage());
            return new ResponseEntity<>(error, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

}