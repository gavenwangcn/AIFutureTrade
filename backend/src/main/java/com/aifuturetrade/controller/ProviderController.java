package com.aifuturetrade.controller;

import com.aifuturetrade.service.ProviderService;
import com.aifuturetrade.service.dto.ProviderDTO;
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
 * 控制器：API提供方
 * 处理API提供方相关的HTTP请求
 */
@RestController
@RequestMapping("/api/providers")
@Api(tags = "API提供方管理")
public class ProviderController {

    @Autowired
    private ProviderService providerService;

    /**
     * 获取所有API提供方
     * @return API提供方列表
     */
    @GetMapping
    @ApiOperation("获取所有API提供方")
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
    @ApiOperation("添加新的API提供方")
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
    @ApiOperation("删除API提供方")
    public ResponseEntity<Map<String, Object>> deleteProvider(@PathVariable String providerId) {
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
     * @param apiUrl API地址
     * @param apiKey API密钥
     * @return 可用模型列表
     */
    @PostMapping("/models")
    @ApiOperation("从提供方API获取可用的模型列表")
    public ResponseEntity<List<String>> fetchProviderModels(@RequestBody ProviderDTO providerDTO) {
        List<String> models = providerService.fetchProviderModels(providerDTO.getApiUrl(), providerDTO.getApiKey());
        return new ResponseEntity<>(models, HttpStatus.OK);
    }

}