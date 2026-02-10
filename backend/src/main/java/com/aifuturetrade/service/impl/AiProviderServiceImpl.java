package com.aifuturetrade.service.impl;

import com.aifuturetrade.service.AiProviderService;
import com.aifuturetrade.service.ProviderService;
import com.aifuturetrade.service.SettingsService;
import com.aifuturetrade.service.dto.ProviderDTO;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;

/**
 * 业务逻辑实现类：AI提供方服务
 * 实现AI调用相关功能
 */
@Slf4j
@Service
public class AiProviderServiceImpl implements AiProviderService {

    @Autowired
    private ProviderService providerService;

    @Autowired
    private SettingsService settingsService;

    private final ObjectMapper objectMapper = new ObjectMapper();
    private final HttpClient httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(30))
            .build();

    @Override
    public List<String> fetchModels(String providerId) {
        ProviderDTO provider = providerService.getProviderById(providerId);
        if (provider == null) {
            throw new IllegalArgumentException("Provider not found: " + providerId);
        }
        return fetchModels(provider.getApiUrl(), provider.getApiKey(), provider.getProviderType());
    }

    @Override
    public List<String> fetchModels(String apiUrl, String apiKey, String providerType) {
        try {
            String url = normalizeApiUrl(apiUrl) + "/models";
            
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("Authorization", "Bearer " + apiKey)
                    .header("Content-Type", "application/json")
                    .GET()
                    .timeout(Duration.ofSeconds(10))
                    .build();
            
            HttpResponse<String> response = httpClient.send(request, 
                    HttpResponse.BodyHandlers.ofString());
            
            if (response.statusCode() == 200) {
                JsonNode jsonNode = objectMapper.readTree(response.body());
                JsonNode dataNode = jsonNode.get("data");
                
                if (dataNode != null && dataNode.isArray()) {
                    List<String> models = new ArrayList<>();
                    for (JsonNode modelNode : dataNode) {
                        String modelId = modelNode.get("id").asText();
                        // 根据提供方类型过滤模型
                        if (shouldIncludeModel(modelId, providerType, apiUrl)) {
                            models.add(modelId);
                        }
                    }
                    return models;
                }
            }
            
            // 如果API调用失败，返回默认模型列表
            return getDefaultModels(providerType);
        } catch (Exception e) {
            log.error("Failed to fetch models from API: {}", e.getMessage(), e);
            return getDefaultModels(providerType);
        }
    }

    @Override
    public String generateStrategyCode(String providerId, String modelName, String strategyContext, String strategyType) {
        // 构建prompt
        String prompt = buildStrategyPrompt(strategyContext, strategyType);
        
        // 调用AI API
        return callAiApi(providerId, modelName, prompt);
    }

    @Override
    public String callAiApi(String providerId, String modelName, String prompt) {
        ProviderDTO provider = providerService.getProviderById(providerId);
        if (provider == null) {
            throw new IllegalArgumentException("Provider not found: " + providerId);
        }
        
        String providerType = provider.getProviderType() != null ? 
                provider.getProviderType().toLowerCase() : "openai";
        
        try {
            // 根据provider_type判断调用哪个API，参考Python版本的_call_llm方法逻辑
            if (providerType.equals("anthropic")) {
                return callAnthropicApi(provider.getApiUrl(), provider.getApiKey(), modelName, prompt);
            } else if (providerType.equals("gemini")) {
                return callGeminiApi(provider.getApiUrl(), provider.getApiKey(), modelName, prompt);
            } else if (providerType.equals("openai") || providerType.equals("azure_openai") || providerType.equals("deepseek")) {
                // OpenAI兼容API（包括openai、azure_openai、deepseek等）
                return callOpenAiCompatibleApi(provider.getApiUrl(), provider.getApiKey(), modelName, prompt);
            } else {
                // 默认使用OpenAI兼容的API
                log.warn("Unknown provider type: {}, using OpenAI compatible API", providerType);
                return callOpenAiCompatibleApi(provider.getApiUrl(), provider.getApiKey(), modelName, prompt);
            }
        } catch (Exception e) {
            log.error("Failed to call AI API: {}", e.getMessage(), e);
            throw new RuntimeException("AI API call failed: " + e.getMessage(), e);
        }
    }

    /**
     * 调用OpenAI兼容的API
     * 参考Python版本的_call_openai_api方法
     * 支持OpenAI、Azure OpenAI、DeepSeek等兼容OpenAI API格式的提供商
     * 使用HTTP客户端实现，匹配Python版本使用OpenAI SDK的逻辑
     */
    private String callOpenAiCompatibleApi(String apiUrl, String apiKey, String modelName, String prompt) throws Exception {
        long startTime = System.currentTimeMillis();
        try {
            // 规范化base_url，确保以/v1结尾，参考Python版本的逻辑
            String baseUrl = normalizeApiUrl(apiUrl);
            String url = baseUrl + "/chat/completions";

            // 获取配置参数
            Map<String, Object> config = getStrategyConfig();
            Double temperature = getConfigDouble(config, "strategy_temperature", 0.0);
            Integer maxTokens = getConfigInteger(config, "strategy_max_tokens", 8192);
            // 确保max_tokens至少为1，使用数据库配置的值，不做上限限制
            maxTokens = Math.max(1, maxTokens);
            log.info("[OpenAI API] 使用配置参数: max_tokens={} (从数据库读取)", maxTokens);
            Double topP = getConfigDouble(config, "strategy_top_p", 0.9);
            
            // 构建请求体，参考Python版本的实现
            Map<String, Object> requestBody = new HashMap<>();
            requestBody.put("model", modelName);
            requestBody.put("temperature", temperature);
            requestBody.put("max_tokens", maxTokens);
            // OpenAI API 支持 top_p 参数
            if (topP != null) {
                requestBody.put("top_p", topP);
            }
            
            List<Map<String, String>> messages = new ArrayList<>();
            Map<String, String> systemMessage = new HashMap<>();
            String systemContent = "You are a professional cryptocurrency trading strategy code generator. Output ONLY the Python code, without any JSON wrapper, markdown code blocks, or explanations. The output must be pure Python code that can be directly executed.";
            systemMessage.put("role", "system");
            systemMessage.put("content", systemContent);
            messages.add(systemMessage);
            
            Map<String, String> userMessage = new HashMap<>();
            userMessage.put("role", "user");
            userMessage.put("content", prompt);
            messages.add(userMessage);
            
            requestBody.put("messages", messages);
            
            // 估算 token 数量
            int systemTokenCount = estimateTokenCount(systemContent);
            int promptTokenCount = estimateTokenCount(prompt);
            int totalInputTokenCount = systemTokenCount + promptTokenCount;
            
            String requestBodyJson = objectMapper.writeValueAsString(requestBody);
            int requestBodySize = requestBodyJson.length();
            
            // 记录请求详细信息
            log.info("[OpenAI API] 开始调用API: url={}, model={}, temperature={}, max_tokens={}, top_p={}, timeout=5分钟", 
                    url, modelName, temperature, maxTokens, topP);
            log.info("[OpenAI API] 输入Token估算: system_tokens={}, prompt_tokens={}, total_input_tokens={}, request_body_size={} bytes", 
                    systemTokenCount, promptTokenCount, totalInputTokenCount, requestBodySize);
            
            // 构建HTTP请求
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("Authorization", "Bearer " + apiKey)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(requestBodyJson))
                    .timeout(Duration.ofMinutes(5))  // 超时时间设置为5分钟
                    .build();
            
            // 发送请求
            HttpResponse<String> response = httpClient.send(request, 
                    HttpResponse.BodyHandlers.ofString());
            
            long elapsedTime = System.currentTimeMillis() - startTime;
            
            // 记录响应信息
            log.info("[OpenAI API] 收到响应: status_code={}, elapsed_time={}ms", response.statusCode(), elapsedTime);

            // 处理响应
            String responseBody = response.body();
            if (response.statusCode() == 200) {
                JsonNode jsonNode = objectMapper.readTree(responseBody);
                
                // 尝试提取 token 使用信息（如果 API 返回）
                try {
                    JsonNode usage = jsonNode.get("usage");
                    if (usage != null) {
                        int promptTokens = usage.has("prompt_tokens") ? usage.get("prompt_tokens").asInt() : 0;
                        int completionTokens = usage.has("completion_tokens") ? usage.get("completion_tokens").asInt() : 0;
                        int totalTokens = usage.has("total_tokens") ? usage.get("total_tokens").asInt() : 0;
                        log.info("[OpenAI API] Token使用情况: prompt_tokens={}, completion_tokens={}, total_tokens={}", 
                                promptTokens, completionTokens, totalTokens);
                    }
                } catch (Exception e) {
                    log.debug("[OpenAI API] 无法解析token使用信息: {}", e.getMessage());
                }
                
                JsonNode choices = jsonNode.get("choices");
                if (choices != null && choices.isArray() && choices.size() > 0) {
                    JsonNode message = choices.get(0).get("message");
                    if (message != null) {
                        String content = message.get("content").asText();
                        int responseContentLength = content != null ? content.length() : 0;
                        int responseTokenEstimate = estimateTokenCount(content);
                        log.info("[OpenAI API] 响应内容长度: {} chars, 估算tokens: {}",
                                responseContentLength, responseTokenEstimate);

                        // 记录原始返回内容（用于调试）
                        log.info("[OpenAI API] 原始返回内容: {}", content);

                        // 提取代码
                        String extractedCode = extractCodeFromResponse(content);

                        // 记录提取后的代码（用于调试）
                        log.info("[OpenAI API] 提取的策略代码: {}", extractedCode);

                        return extractedCode;
                    }
                }
            }
            
            log.error("[OpenAI API] API调用失败: status_code={}, response_body={}", 
                    response.statusCode(), response.body());
            throw new RuntimeException("Failed to get response from OpenAI API: " + response.statusCode() + 
                    ", body: " + response.body());
            
        } catch (java.net.http.HttpTimeoutException e) {
            // 对应Python版本的APIConnectionError
            String errorMsg = String.format("API connection failed: %s", e.getMessage());
            log.error("OpenAI API: {}", errorMsg);
            throw new RuntimeException(errorMsg, e);
        } catch (java.io.IOException e) {
            // 对应Python版本的APIConnectionError
            String errorMsg = String.format("API connection failed: %s", e.getMessage());
            log.error("OpenAI API: {}", errorMsg);
            throw new RuntimeException(errorMsg, e);
        } catch (Exception e) {
            // 对应Python版本的APIError和其他异常
            String errorMsg = String.format("OpenAI API call failed: %s", e.getMessage());
            log.error("OpenAI API: {}", errorMsg, e);
            throw new RuntimeException(errorMsg, e);
        }
    }

    /**
     * 调用Anthropic API
     * 参考Python版本的_call_anthropic_api方法
     * 使用HTTP请求直接调用Anthropic的Claude API
     */
    private String callAnthropicApi(String apiUrl, String apiKey, String modelName, String prompt) throws Exception {
        long startTime = System.currentTimeMillis();
        try {
            // 规范化base_url，确保以/v1结尾
            String baseUrl = normalizeApiUrl(apiUrl);
            String url = baseUrl + "/messages";

            // 获取配置参数
            Map<String, Object> config = getStrategyConfig();
            Integer maxTokens = getConfigInteger(config, "strategy_max_tokens", 8192);
            // 确保max_tokens至少为1，使用数据库配置的值，不做上限限制
            maxTokens = Math.max(1, maxTokens);
            log.info("[Anthropic API] 使用配置参数: max_tokens={} (从数据库读取)", maxTokens);
            Double temperature = getConfigDouble(config, "strategy_temperature", 0.0);
            Double topP = getConfigDouble(config, "strategy_top_p", 0.9);
            
            String systemContent = "You are a professional cryptocurrency trading strategy code generator. Output ONLY the Python code, without any JSON wrapper, markdown code blocks, or explanations. The output must be pure Python code that can be directly executed.";
            
            // 构建请求体，参考Python版本的实现
            Map<String, Object> requestBody = new HashMap<>();
            requestBody.put("model", modelName);
            requestBody.put("max_tokens", maxTokens);
            requestBody.put("temperature", temperature);
            // Anthropic API 支持 top_p 参数
            if (topP != null) {
                requestBody.put("top_p", topP);
            }
            requestBody.put("system", systemContent);
            
            List<Map<String, String>> messages = new ArrayList<>();
            Map<String, String> userMessage = new HashMap<>();
            userMessage.put("role", "user");
            userMessage.put("content", prompt);
            messages.add(userMessage);
            requestBody.put("messages", messages);
            
            // 估算 token 数量
            int systemTokenCount = estimateTokenCount(systemContent);
            int promptTokenCount = estimateTokenCount(prompt);
            int totalInputTokenCount = systemTokenCount + promptTokenCount;
            
            String requestBodyJson = objectMapper.writeValueAsString(requestBody);
            int requestBodySize = requestBodyJson.length();
            
            // 记录请求详细信息
            log.info("[Anthropic API] 开始调用API: url={}, model={}, temperature={}, max_tokens={}, top_p={}, timeout=5分钟", 
                    url, modelName, temperature, maxTokens, topP);
            log.info("[Anthropic API] 输入Token估算: system_tokens={}, prompt_tokens={}, total_input_tokens={}, request_body_size={} bytes", 
                    systemTokenCount, promptTokenCount, totalInputTokenCount, requestBodySize);
            
            // 构建HTTP请求
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("x-api-key", apiKey)
                    .header("anthropic-version", "2023-06-01")
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(requestBodyJson))
                    .timeout(Duration.ofMinutes(5))  // 超时时间设置为5分钟
                    .build();
            
            // 发送请求
            HttpResponse<String> response = httpClient.send(request, 
                    HttpResponse.BodyHandlers.ofString());
            
            long elapsedTime = System.currentTimeMillis() - startTime;
            
            // 记录响应信息
            log.info("[Anthropic API] 收到响应: status_code={}, elapsed_time={}ms", response.statusCode(), elapsedTime);

            // 处理响应
            String responseBody = response.body();
            if (response.statusCode() == 200) {
                JsonNode jsonNode = objectMapper.readTree(responseBody);
                
                // 尝试提取 token 使用信息（如果 API 返回）
                try {
                    JsonNode usage = jsonNode.get("usage");
                    if (usage != null) {
                        int inputTokens = usage.has("input_tokens") ? usage.get("input_tokens").asInt() : 0;
                        int outputTokens = usage.has("output_tokens") ? usage.get("output_tokens").asInt() : 0;
                        log.info("[Anthropic API] Token使用情况: input_tokens={}, output_tokens={}", 
                                inputTokens, outputTokens);
                    }
                } catch (Exception e) {
                    log.debug("[Anthropic API] 无法解析token使用信息: {}", e.getMessage());
                }
                
                JsonNode content = jsonNode.get("content");
                if (content != null && content.isArray() && content.size() > 0) {
                    String text = content.get(0).get("text").asText();
                    int responseContentLength = text != null ? text.length() : 0;
                    int responseTokenEstimate = estimateTokenCount(text);
                    log.info("[Anthropic API] 响应内容长度: {} chars, 估算tokens: {}",
                            responseContentLength, responseTokenEstimate);

                    // 记录原始返回内容（用于调试）
                    log.info("[Anthropic API] 原始返回内容: {}", text);

                    // 提取代码
                    String extractedCode = extractCodeFromResponse(text);

                    // 记录提取后的代码（用于调试）
                    log.info("[Anthropic API] 提取的策略代码: {}", extractedCode);

                    return extractedCode;
                }
            }
            
            log.error("[Anthropic API] API调用失败: status_code={}, response_body={}", 
                    response.statusCode(), response.body());
            throw new RuntimeException("Failed to get response from Anthropic API: " + response.statusCode() + 
                    ", body: " + response.body());
            
        } catch (java.net.http.HttpTimeoutException e) {
            String errorMsg = String.format("Anthropic API connection timeout: %s", e.getMessage());
            log.error("Anthropic API: {}", errorMsg);
            throw new RuntimeException(errorMsg, e);
        } catch (java.io.IOException e) {
            String errorMsg = String.format("Anthropic API connection failed: %s", e.getMessage());
            log.error("Anthropic API: {}", errorMsg);
            throw new RuntimeException(errorMsg, e);
        } catch (Exception e) {
            String errorMsg = String.format("Anthropic API call failed: %s", e.getMessage());
            log.error("Anthropic API: {}", errorMsg, e);
            throw new RuntimeException(errorMsg, e);
        }
    }

    /**
     * 调用Gemini API
     * 参考Python版本的_call_gemini_api方法
     * 使用HTTP请求直接调用Google的Gemini API
     */
    private String callGeminiApi(String apiUrl, String apiKey, String modelName, String prompt) throws Exception {
        long startTime = System.currentTimeMillis();
        try {
            // 规范化base_url，确保以/v1结尾
            String baseUrl = normalizeApiUrl(apiUrl);
            String url = baseUrl + "/" + modelName + ":generateContent";
            
            String systemPrefix = "You are a professional cryptocurrency trader. Output JSON format only.\n\n";
            String fullPrompt = systemPrefix + prompt;
            
            // 构建请求体，参考Python版本的实现
            Map<String, Object> requestBody = new HashMap<>();
            List<Map<String, Object>> contents = new ArrayList<>();
            Map<String, Object> content = new HashMap<>();
            List<Map<String, String>> parts = new ArrayList<>();
            Map<String, String> part = new HashMap<>();
            part.put("text", fullPrompt);
            parts.add(part);
            content.put("parts", parts);
            contents.add(content);
            requestBody.put("contents", contents);

            // 获取配置参数
            Map<String, Object> config = getStrategyConfig();
            Double temperature = getConfigDouble(config, "strategy_temperature", 0.0);
            Integer maxTokens = getConfigInteger(config, "strategy_max_tokens", 8192);
            // 确保max_tokens至少为1，使用数据库配置的值，不做上限限制
            maxTokens = Math.max(1, maxTokens);
            log.info("[Gemini API] 使用配置参数: max_tokens={} (从数据库读取)", maxTokens);
            Double topP = getConfigDouble(config, "strategy_top_p", 0.9);
            Integer topK = getConfigInteger(config, "strategy_top_k", 50);
            
            Map<String, Object> generationConfig = new HashMap<>();
            generationConfig.put("temperature", temperature);
            generationConfig.put("maxOutputTokens", maxTokens);
            // Gemini API 支持 top_p 和 top_k 参数
            if (topP != null) {
                generationConfig.put("topP", topP);
            }
            if (topK != null) {
                generationConfig.put("topK", topK);
            }
            requestBody.put("generationConfig", generationConfig);
            
            // 估算 token 数量
            int systemTokenCount = estimateTokenCount(systemPrefix);
            int promptTokenCount = estimateTokenCount(prompt);
            int totalInputTokenCount = systemTokenCount + promptTokenCount;
            
            String requestBodyJson = objectMapper.writeValueAsString(requestBody);
            int requestBodySize = requestBodyJson.length();
            
            // 记录请求详细信息
            log.info("[Gemini API] 开始调用API: url={}, model={}, temperature={}, max_output_tokens={}, top_p={}, top_k={}, timeout=5分钟", 
                    url, modelName, temperature, maxTokens, topP, topK);
            log.info("[Gemini API] 输入Token估算: system_tokens={}, prompt_tokens={}, total_input_tokens={}, request_body_size={} bytes", 
                    systemTokenCount, promptTokenCount, totalInputTokenCount, requestBodySize);
            
            // 构建URL，添加API密钥作为查询参数
            String urlWithKey = url + "?key=" + java.net.URLEncoder.encode(apiKey, "UTF-8");
            
            // 构建HTTP请求
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(urlWithKey))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(requestBodyJson))
                    .timeout(Duration.ofMinutes(5))  // 超时时间设置为5分钟
                    .build();
            
            // 发送请求
            HttpResponse<String> response = httpClient.send(request, 
                    HttpResponse.BodyHandlers.ofString());
            
            long elapsedTime = System.currentTimeMillis() - startTime;
            
            // 记录响应信息
            log.info("[Gemini API] 收到响应: status_code={}, elapsed_time={}ms", response.statusCode(), elapsedTime);

            // 处理响应
            String responseBody = response.body();
            if (response.statusCode() == 200) {
                JsonNode jsonNode = objectMapper.readTree(responseBody);
                
                // 尝试提取 token 使用信息（如果 API 返回）
                try {
                    JsonNode usageMetadata = jsonNode.get("usageMetadata");
                    if (usageMetadata != null) {
                        int apiPromptTokenCount = usageMetadata.has("promptTokenCount") ? usageMetadata.get("promptTokenCount").asInt() : 0;
                        int candidatesTokenCount = usageMetadata.has("candidatesTokenCount") ? usageMetadata.get("candidatesTokenCount").asInt() : 0;
                        int totalTokenCount = usageMetadata.has("totalTokenCount") ? usageMetadata.get("totalTokenCount").asInt() : 0;
                        log.info("[Gemini API] Token使用情况: prompt_tokens={}, candidates_tokens={}, total_tokens={}", 
                                apiPromptTokenCount, candidatesTokenCount, totalTokenCount);
                    }
                } catch (Exception e) {
                    log.debug("[Gemini API] 无法解析token使用信息: {}", e.getMessage());
                }
                
                JsonNode candidates = jsonNode.get("candidates");
                if (candidates != null && candidates.isArray() && candidates.size() > 0) {
                    JsonNode candidate = candidates.get(0);
                    JsonNode candidateContent = candidate.get("content");
                    if (candidateContent != null) {
                        JsonNode candidateParts = candidateContent.get("parts");
                        if (candidateParts != null && candidateParts.isArray() && candidateParts.size() > 0) {
                            String text = candidateParts.get(0).get("text").asText();
                            int responseContentLength = text != null ? text.length() : 0;
                            int responseTokenEstimate = estimateTokenCount(text);
                            log.info("[Gemini API] 响应内容长度: {} chars, 估算tokens: {}",
                                    responseContentLength, responseTokenEstimate);

                            // 记录原始返回内容（用于调试）
                            log.info("[Gemini API] 原始返回内容: {}", text);

                            // 提取代码
                            String extractedCode = extractCodeFromResponse(text);

                            // 记录提取后的代码（用于调试）
                            log.info("[Gemini API] 提取的策略代码: {}", extractedCode);

                            return extractedCode;
                        }
                    }
                }
            }
            
            log.error("[Gemini API] API调用失败: status_code={}, response_body={}", 
                    response.statusCode(), response.body());
            throw new RuntimeException("Failed to get response from Gemini API: " + response.statusCode() + 
                    ", body: " + response.body());
            
        } catch (java.net.http.HttpTimeoutException e) {
            String errorMsg = String.format("Gemini API connection timeout: %s", e.getMessage());
            log.error("Gemini API: {}", errorMsg);
            throw new RuntimeException(errorMsg, e);
        } catch (java.io.IOException e) {
            String errorMsg = String.format("Gemini API connection failed: %s", e.getMessage());
            log.error("Gemini API: {}", errorMsg);
            throw new RuntimeException(errorMsg, e);
        } catch (Exception e) {
            String errorMsg = String.format("Gemini API call failed: %s", e.getMessage());
            log.error("Gemini API: {}", errorMsg, e);
            throw new RuntimeException(errorMsg, e);
        }
    }

    /**
     * 构建策略代码生成的Prompt
     */
    private String buildStrategyPrompt(String strategyContext, String strategyType) {
        try {
            // 从资源文件读取prompt模板
            String templateFile;
            if ("buy".equalsIgnoreCase(strategyType)) {
                templateFile = "prompts/strategy_buy_prompt.txt";
            } else {
                templateFile = "prompts/strategy_sell_prompt.txt";
            }
            
            java.io.InputStream inputStream = getClass().getClassLoader()
                    .getResourceAsStream(templateFile);
            
            if (inputStream != null) {
                String template = new String(inputStream.readAllBytes(), 
                        java.nio.charset.StandardCharsets.UTF_8);
                inputStream.close();
                return template.replace("{strategy_context}", strategyContext);
            } else {
                // 如果文件不存在，使用内置模板
                log.warn("Prompt template file not found: {}, using built-in template", templateFile);
                return getBuiltInPromptTemplate(strategyContext, strategyType);
            }
        } catch (Exception e) {
            log.error("Failed to load prompt template, using built-in template: {}", e.getMessage());
            return getBuiltInPromptTemplate(strategyContext, strategyType);
        }
    }
    
    /**
     * 获取内置的Prompt模板（备用方案）
     */
    private String getBuiltInPromptTemplate(String strategyContext, String strategyType) {
        String basePrompt;
        if ("buy".equalsIgnoreCase(strategyType)) {
            basePrompt = getBuyStrategyPromptTemplate();
        } else {
            basePrompt = getSellStrategyPromptTemplate();
        }
        return basePrompt.replace("{strategy_context}", strategyContext);
    }

    /**
     * 获取买入策略Prompt模板
     * 注意：这里应该从strategy_prompt_template_buy.py中读取完整模板
     * 当前使用简化版本，实际部署时需要读取完整模板
     */
    private String getBuyStrategyPromptTemplate() {
        // 读取完整的prompt模板（简化版，实际应该从文件读取）
        return "你是一个专业的量化交易买入策略代码生成专家。请根据提供的策略规则（strategy_context）生成符合标准的 Python 买入策略代码。\n\n" +
               "## 策略规则（strategy_context）：\n{strategy_context}\n\n" +
               "## 重要要求：\n\n" +
               "### 1. 必须继承 StrategyBaseBuy 类\n\n" +
               "生成的代码必须是一个继承自 `StrategyBaseBuy` 的类，并实现其抽象方法：\n\n" +
               "```python\n" +
               "from trade.strategy.strategy_template_buy import StrategyBaseBuy\n" +
               "from typing import Dict, List\n\n" +
               "class GeneratedBuyStrategy(StrategyBaseBuy):\n" +
               "    def execute_buy_decision(\n" +
               "        self,\n" +
               "        candidates: List[Dict],\n" +
               "        portfolio: Dict,\n" +
               "        account_info: Dict,\n" +
               "        market_state: Dict,\n" +
               "        symbol_source: str\n" +
               "    ) -> Dict[str, Dict]:\n" +
               "        # 实现买入决策逻辑\n" +
               "        decisions = {}\n" +
               "        \n" +
               "        # 遍历候选交易对\n" +
               "        for candidate in candidates:\n" +
               "            symbol = candidate.get('symbol', '').upper()\n" +
               "            if not symbol:\n" +
               "                continue\n" +
               "            \n" +
               "            # 获取当前价格\n" +
               "            current_price = candidate.get('price', 0)\n" +
               "            if current_price <= 0:\n" +
               "                symbol_state = market_state.get(symbol, {})\n" +
               "                current_price = symbol_state.get('price', 0)\n" +
               "            \n" +
               "            if current_price <= 0:\n" +
               "                continue\n" +
               "            \n" +
               "            # 根据策略规则实现决策逻辑\n" +
               "            # TODO: 根据策略规则实现\n" +
               "            \n" +
               "        return decisions\n" +
               "```\n\n" +
               "### 2. 代码要求\n\n" +
               "- 代码必须完整、可执行\n" +
               "- 必须正确导入 StrategyBaseBuy：`from trade.strategy.strategy_template_buy import StrategyBaseBuy`\n" +
               "- 必须实现 execute_buy_decision 方法\n" +
               "- 方法必须返回 Dict[str, Dict] 格式的决策字典\n" +
               "- 决策格式：{\"SYMBOL\": {\"signal\": \"buy_to_long\" | \"buy_to_short\", \"quantity\": 100, \"leverage\": 10, \"justification\": \"理由\"}}\n\n" +
               "### 3. 可用库\n\n" +
               "- talib: TA-Lib 技术指标库（如果可用）\n" +
               "- numpy: NumPy 数值计算库（如果可用）\n" +
               "- pandas: Pandas 数据分析库（如果可用）\n" +
               "- math: Python 数学函数库\n" +
               "- datetime: Python 日期时间库\n\n" +
               "请根据策略规则生成完整的、可执行的Python代码。代码必须可以直接运行，不需要额外的实例化代码（系统会自动实例化）。";
    }

    /**
     * 获取卖出策略Prompt模板
     * 注意：这里应该从strategy_prompt_template_sell.py中读取完整模板
     * 当前使用简化版本，实际部署时需要读取完整模板
     */
    private String getSellStrategyPromptTemplate() {
        // 读取完整的prompt模板（简化版，实际应该从文件读取）
        return "你是一个专业的量化交易卖出策略代码生成专家。请根据提供的策略规则（strategy_context）生成符合标准的 Python 卖出策略代码。\n\n" +
               "## 策略规则（strategy_context）：\n{strategy_context}\n\n" +
               "## 重要要求：\n\n" +
               "### 1. 必须继承 StrategyBaseSell 类\n\n" +
               "生成的代码必须是一个继承自 `StrategyBaseSell` 的类，并实现其抽象方法：\n\n" +
               "```python\n" +
               "from trade.strategy.strategy_template_sell import StrategyBaseSell\n" +
               "from typing import Dict\n\n" +
               "class GeneratedSellStrategy(StrategyBaseSell):\n" +
               "    def execute_sell_decision(\n" +
               "        self,\n" +
               "        portfolio: Dict,\n" +
               "        market_state: Dict,\n" +
               "        account_info: Dict\n" +
               "    ) -> Dict[str, Dict]:\n" +
               "        # 实现卖出决策逻辑\n" +
               "        decisions = {}\n" +
               "        \n" +
               "        # 获取当前持仓\n" +
               "        positions = portfolio.get('positions', [])\n" +
               "        if not positions:\n" +
               "            return decisions\n" +
               "        \n" +
               "        # 遍历持仓\n" +
               "        for position in positions:\n" +
               "            symbol = position.get('symbol', '').upper()\n" +
               "            if not symbol:\n" +
               "                continue\n" +
               "            \n" +
               "            # 获取当前价格\n" +
               "            symbol_state = market_state.get(symbol, {})\n" +
               "            current_price = symbol_state.get('price', 0)\n" +
               "            \n" +
               "            if current_price <= 0:\n" +
               "                continue\n" +
               "            \n" +
               "            # 根据策略规则实现决策逻辑\n" +
               "            # TODO: 根据策略规则实现\n" +
               "            \n" +
               "        return decisions\n" +
               "```\n\n" +
               "### 2. 代码要求\n\n" +
               "- 代码必须完整、可执行\n" +
               "- 必须正确导入 StrategyBaseSell：`from trade.strategy.strategy_template_sell import StrategyBaseSell`\n" +
               "- 必须实现 execute_sell_decision 方法\n" +
               "- 方法必须返回 Dict[str, Dict] 格式的决策字典\n" +
               "- 决策格式：{\"SYMBOL\": {\"signal\": \"close_position\" | \"stop_loss\" | \"take_profit\", \"quantity\": 100, \"stop_price\": 0.0325, \"justification\": \"理由\"}}\n\n" +
               "### 3. 可用库\n\n" +
               "- talib: TA-Lib 技术指标库（如果可用）\n" +
               "- numpy: NumPy 数值计算库（如果可用）\n" +
               "- pandas: Pandas 数据分析库（如果可用）\n" +
               "- math: Python 数学函数库\n" +
               "- datetime: Python 日期时间库\n\n" +
               "请根据策略规则生成完整的、可执行的Python代码。代码必须可以直接运行，不需要额外的实例化代码（系统会自动实例化）。";
    }

    /**
     * 规范化API URL
     */
    private String normalizeApiUrl(String apiUrl) {
        String url = apiUrl.trim();
        if (url.endsWith("/")) {
            url = url.substring(0, url.length() - 1);
        }
        if (!url.endsWith("/v1")) {
            if (url.contains("/v1")) {
                url = url.substring(0, url.indexOf("/v1")) + "/v1";
            } else {
                url = url + "/v1";
            }
        }
        return url;
    }

    /**
     * 判断是否应该包含该模型
     */
    private boolean shouldIncludeModel(String modelId, String providerType, String apiUrl) {
        String lowerModelId = modelId.toLowerCase();
        String lowerProviderType = providerType != null ? providerType.toLowerCase() : "";
        String lowerApiUrl = apiUrl.toLowerCase();
        
        if (lowerApiUrl.contains("openai") || lowerProviderType.equals("openai")) {
            return lowerModelId.contains("gpt");
        } else if (lowerApiUrl.contains("deepseek") || lowerProviderType.equals("deepseek")) {
            return lowerModelId.contains("deepseek");
        } else if (lowerProviderType.equals("anthropic")) {
            return lowerModelId.contains("claude");
        } else if (lowerProviderType.equals("gemini")) {
            return lowerModelId.contains("gemini");
        }
        return true; // 默认包含所有模型
    }

    /**
     * 获取默认模型列表
     */
    private List<String> getDefaultModels(String providerType) {
        if (providerType == null) {
            return List.of("gpt-3.5-turbo", "gpt-4", "gpt-4-turbo");
        }
        
        String lowerType = providerType.toLowerCase();
        if (lowerType.equals("openai") || lowerType.equals("azure_openai")) {
            return List.of("gpt-3.5-turbo", "gpt-4", "gpt-4-turbo");
        } else if (lowerType.equals("deepseek")) {
            return List.of("deepseek-chat", "deepseek-coder");
        } else if (lowerType.equals("anthropic")) {
            return List.of("claude-3-opus", "claude-3-sonnet", "claude-3-haiku");
        } else if (lowerType.equals("gemini")) {
            return List.of("gemini-pro", "gemini-pro-vision");
        }
        return List.of("gpt-3.5-turbo", "gpt-4", "gpt-4-turbo");
    }

    /**
     * 估算文本的 token 数量
     * 使用简单的估算方法：1 token ≈ 4 个字符（对于英文）
     * 对于中文，1 token ≈ 1.5 个字符
     * 这是一个粗略估算，实际 token 数量可能因模型而异
     * 
     * @param text 要估算的文本
     * @return 估算的 token 数量
     */
    private int estimateTokenCount(String text) {
        if (text == null || text.isEmpty()) {
            return 0;
        }
        // 简单估算：英文 1 token ≈ 4 字符，中文 1 token ≈ 1.5 字符
        // 混合文本使用折中方案：1 token ≈ 3 字符
        int charCount = text.length();
        // 计算中文字符数量（粗略估算）
        int chineseCharCount = 0;
        for (char c : text.toCharArray()) {
            if (c >= 0x4E00 && c <= 0x9FFF) {  // 中文字符范围
                chineseCharCount++;
            }
        }
        int nonChineseCharCount = charCount - chineseCharCount;
        // 中文字符按 1.5 字符/token，非中文字符按 4 字符/token 估算
        int estimatedTokens = (int) (chineseCharCount / 1.5 + nonChineseCharCount / 4.0);
        // 至少返回 1 个 token（如果文本不为空）
        return Math.max(1, estimatedTokens);
    }

    /**
     * 获取策略配置参数
     * @return 配置参数Map
     */
    private Map<String, Object> getStrategyConfig() {
        try {
            return settingsService.getSettings();
        } catch (Exception e) {
            log.warn("Failed to get settings, using default values: {}", e.getMessage());
            // 返回默认值
            Map<String, Object> defaultConfig = new HashMap<>();
            defaultConfig.put("strategy_temperature", 0.0);
            defaultConfig.put("strategy_max_tokens", 8192);  // OpenAI API 最大限制为 8192
            defaultConfig.put("strategy_top_p", 0.9);
            defaultConfig.put("strategy_top_k", 50);
            return defaultConfig;
        }
    }

    /**
     * 从配置中获取Double值，如果不存在则使用默认值
     */
    private Double getConfigDouble(Map<String, Object> config, String key, Double defaultValue) {
        Object value = config.get(key);
        if (value == null) {
            return defaultValue;
        }
        if (value instanceof Number) {
            return ((Number) value).doubleValue();
        }
        try {
            return Double.parseDouble(String.valueOf(value));
        } catch (NumberFormatException e) {
            log.warn("Invalid {} value: {}, using default: {}", key, value, defaultValue);
            return defaultValue;
        }
    }

    /**
     * 从配置中获取Integer值，如果不存在则使用默认值
     */
    private Integer getConfigInteger(Map<String, Object> config, String key, Integer defaultValue) {
        Object value = config.get(key);
        if (value == null) {
            return defaultValue;
        }
        if (value instanceof Number) {
            return ((Number) value).intValue();
        }
        try {
            return Integer.parseInt(String.valueOf(value));
        } catch (NumberFormatException e) {
            log.warn("Invalid {} value: {}, using default: {}", key, value, defaultValue);
            return defaultValue;
        }
    }
    
    /**
     * 从AI响应中提取代码
     * 支持以下格式：
     * 1. JSON格式：{"code": "..."} 或 {"strategy_code": "..."}
     * 2. Markdown代码块：```python ... ``` 或 ``` ... ```
     * 3. 纯代码：直接返回
     *
     * @param response AI返回的原始内容
     * @return 提取的Python代码（已处理转义字符）
     */
    private String extractCodeFromResponse(String response) {
        if (response == null || response.trim().isEmpty()) {
            log.warn("[代码提取] 响应内容为空");
            return response;
        }

        String trimmed = response.trim();
        String extractedCode = null;

        // 尝试解析JSON格式
        try {
            JsonNode jsonNode = objectMapper.readTree(trimmed);
            // 检查是否有code字段
            if (jsonNode.has("code")) {
                extractedCode = jsonNode.get("code").asText();
            }
            // 检查是否有strategy_code字段
            else if (jsonNode.has("strategy_code")) {
                extractedCode = jsonNode.get("strategy_code").asText();
            }
        } catch (Exception e) {
            // 不是JSON格式，继续处理
        }

        // 如果没有从JSON中提取到代码，尝试提取Markdown代码块
        if (extractedCode == null) {
            // 匹配 ```python ... ``` 或 ``` ... ```
            java.util.regex.Pattern markdownPattern = java.util.regex.Pattern.compile(
                "```(?:python)?\\s*\\n?(.*?)\\n?```",
                java.util.regex.Pattern.DOTALL
            );
            java.util.regex.Matcher matcher = markdownPattern.matcher(trimmed);
            if (matcher.find()) {
                extractedCode = matcher.group(1).trim();
            }
        }

        // 如果还是没有提取到代码，使用原始内容
        if (extractedCode == null) {
            extractedCode = trimmed;
        }

        // 处理转义字符：将字符串形式的转义字符转换为实际字符
        // 例如：将 "\n" 转换为实际的换行符
        String normalizedCode = normalizeEscapeCharacters(extractedCode);

        return normalizedCode;
    }
    
    /**
     * 规范化转义字符
     * 将字符串形式的转义字符（如 "\n", "\t", "\r"）转换为实际的字符
     * 
     * 注意：
     * - 如果代码是从JSON中提取的，Jackson的asText()已经处理了转义字符
     * - 但如果AI返回的是字符串字面量形式的转义字符（如 "import talib\\nfrom typing"），
     *   需要手动转换为实际的换行符
     * 
     * @param code 原始代码字符串
     * @return 规范化后的代码字符串
     */
    private String normalizeEscapeCharacters(String code) {
        if (code == null || code.isEmpty()) {
            return code;
        }
        
        // 使用StringEscapeUtils或手动处理转义字符
        // 由于我们使用的是Java 11，没有Apache Commons，所以手动处理
        
        // 创建一个StringBuilder来构建结果
        StringBuilder result = new StringBuilder();
        int length = code.length();
        
        for (int i = 0; i < length; i++) {
            char c = code.charAt(i);
            
            // 检查是否是转义序列的开始
            if (c == '\\' && i + 1 < length) {
                char next = code.charAt(i + 1);
                switch (next) {
                    case 'n':
                        result.append('\n');  // 换行符
                        i++; // 跳过下一个字符
                        continue;
                    case 't':
                        result.append('\t');  // 制表符
                        i++;
                        continue;
                    case 'r':
                        result.append('\r');  // 回车符
                        i++;
                        continue;
                    case '\\':
                        result.append('\\');  // 反斜杠本身
                        i++;
                        continue;
                    case '"':
                        result.append('"');   // 双引号
                        i++;
                        continue;
                    case '\'':
                        result.append('\'');   // 单引号
                        i++;
                        continue;
                    default:
                        // 如果不是已知的转义序列，保留原样
                        result.append(c);
                        break;
                }
            } else {
                result.append(c);
            }
        }
        
        return result.toString();
    }
}

