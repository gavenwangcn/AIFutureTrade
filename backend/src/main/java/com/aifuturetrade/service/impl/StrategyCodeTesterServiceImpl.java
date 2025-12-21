package com.aifuturetrade.service.impl;

import com.aifuturetrade.service.StrategyCodeTesterService;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/**
 * 策略代码测试服务实现类
 * 通过调用Python测试脚本来验证策略代码
 */
@Slf4j
@Service
public class StrategyCodeTesterServiceImpl implements StrategyCodeTesterService {

    private final ObjectMapper objectMapper = new ObjectMapper();
    
    @Value("${python.executable:python}")
    private String pythonExecutable;
    
    @Value("${project.root.path:}")
    private String projectRootPath;

    @Override
    public Map<String, Object> testStrategyCode(String strategyCode, String strategyType, String strategyName) {
        try {
            // 创建临时文件存储策略代码
            Path tempFile = Files.createTempFile("strategy_code_", ".py");
            try {
                Files.write(tempFile, strategyCode.getBytes(StandardCharsets.UTF_8));
                
                // 构建Python脚本路径
                String scriptPath = getPythonTestScriptPath(strategyType);
                
                // 构建命令
                ProcessBuilder processBuilder = new ProcessBuilder(
                    pythonExecutable,
                    scriptPath,
                    tempFile.toString(),
                    strategyName != null ? strategyName : "测试策略"
                );
                
                // 设置工作目录为项目根目录
                if (projectRootPath != null && !projectRootPath.isEmpty()) {
                    processBuilder.directory(new File(projectRootPath));
                }
                
                // 设置环境变量
                Map<String, String> env = processBuilder.environment();
                env.put("PYTHONUNBUFFERED", "1");
                
                // 启动进程
                Process process = processBuilder.start();
                
                // 读取输出
                StringBuilder output = new StringBuilder();
                StringBuilder errorOutput = new StringBuilder();
                
                try (BufferedReader reader = new BufferedReader(
                        new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8));
                     BufferedReader errorReader = new BufferedReader(
                        new InputStreamReader(process.getErrorStream(), StandardCharsets.UTF_8))) {
                    
                    String line;
                    while ((line = reader.readLine()) != null) {
                        output.append(line).append("\n");
                    }
                    
                    while ((line = errorReader.readLine()) != null) {
                        errorOutput.append(line).append("\n");
                    }
                }
                
                // 等待进程完成，最多等待30秒
                boolean finished = process.waitFor(30, TimeUnit.SECONDS);
                if (!finished) {
                    process.destroyForcibly();
                    throw new RuntimeException("Python测试脚本执行超时（30秒）");
                }
                
                int exitCode = process.exitValue();
                
                if (exitCode != 0) {
                    log.error("Python测试脚本执行失败，退出码: {}, 错误输出: {}", exitCode, errorOutput.toString());
                    throw new RuntimeException("策略代码测试失败: " + errorOutput.toString());
                }
                
                // 解析JSON输出
                String jsonOutput = output.toString().trim();
                if (jsonOutput.isEmpty()) {
                    throw new RuntimeException("Python测试脚本未返回结果");
                }
                
                // 查找JSON部分（可能包含日志输出）
                int jsonStart = jsonOutput.indexOf("{");
                int jsonEnd = jsonOutput.lastIndexOf("}");
                if (jsonStart == -1 || jsonEnd == -1) {
                    throw new RuntimeException("Python测试脚本返回格式不正确: " + jsonOutput);
                }
                
                String jsonStr = jsonOutput.substring(jsonStart, jsonEnd + 1);
                @SuppressWarnings("unchecked")
                Map<String, Object> result = (Map<String, Object>) objectMapper.readValue(jsonStr, Map.class);
                
                log.info("策略代码测试完成: {}, 通过: {}", strategyName, result.get("passed"));
                
                return result;
                
            } finally {
                // 删除临时文件
                try {
                    Files.deleteIfExists(tempFile);
                } catch (IOException e) {
                    log.warn("删除临时文件失败: {}", tempFile, e);
                }
            }
            
        } catch (Exception e) {
            log.error("测试策略代码时发生异常: {}", e.getMessage(), e);
            Map<String, Object> errorResult = new HashMap<>();
            errorResult.put("passed", false);
            errorResult.put("errors", java.util.Arrays.asList("测试执行异常: " + e.getMessage()));
            errorResult.put("warnings", java.util.Collections.emptyList());
            errorResult.put("test_results", new HashMap<>());
            return errorResult;
        }
    }

    @Override
    public boolean validateStrategyCode(String strategyCode, String strategyType, String strategyName) {
        Map<String, Object> testResult = testStrategyCode(strategyCode, strategyType, strategyName);
        
        Boolean passed = (Boolean) testResult.get("passed");
        if (passed == null || !passed) {
            @SuppressWarnings("unchecked")
            java.util.List<String> errors = (java.util.List<String>) testResult.get("errors");
            String errorMessage = "策略代码验证失败";
            if (errors != null && !errors.isEmpty()) {
                errorMessage += ": " + String.join("; ", errors);
            }
            throw new RuntimeException(errorMessage);
        }
        
        return true;
    }
    
    /**
     * 获取Python测试脚本路径
     */
    private String getPythonTestScriptPath(String strategyType) {
        // 如果设置了项目根路径，使用绝对路径
        if (projectRootPath != null && !projectRootPath.isEmpty()) {
            if ("buy".equalsIgnoreCase(strategyType)) {
                return Paths.get(projectRootPath, "trade", "strategy", "strategy_code_tester_wrapper_buy.py").toString();
            } else {
                return Paths.get(projectRootPath, "trade", "strategy", "strategy_code_tester_wrapper_sell.py").toString();
            }
        }
        
        // 否则使用相对路径（假设脚本在项目根目录）
        if ("buy".equalsIgnoreCase(strategyType)) {
            return "trade/strategy/strategy_code_tester_wrapper_buy.py";
        } else {
            return "trade/strategy/strategy_code_tester_wrapper_sell.py";
        }
    }
}

