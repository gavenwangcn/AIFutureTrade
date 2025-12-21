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
        try {
            // 规范化base_url，确保以/v1结尾，参考Python版本的逻辑
            String baseUrl = normalizeApiUrl(apiUrl);
            String url = baseUrl + "/chat/completions";
            
            // 获取配置参数
            Map<String, Object> config = getStrategyConfig();
            Double temperature = getConfigDouble(config, "strategy_temperature", 0.7);
            Integer maxTokens = getConfigInteger(config, "strategy_max_tokens", 20000);
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
            systemMessage.put("role", "system");
            systemMessage.put("content", "You are a professional cryptocurrency trader. Output JSON format only.");
            messages.add(systemMessage);
            
            Map<String, String> userMessage = new HashMap<>();
            userMessage.put("role", "user");
            userMessage.put("content", prompt);
            messages.add(userMessage);
            
            requestBody.put("messages", messages);
            
            String requestBodyJson = objectMapper.writeValueAsString(requestBody);
            
            // 构建HTTP请求
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("Authorization", "Bearer " + apiKey)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(requestBodyJson))
                    .timeout(Duration.ofSeconds(60))
                    .build();
            
            // 发送请求
            HttpResponse<String> response = httpClient.send(request, 
                    HttpResponse.BodyHandlers.ofString());
            
            // 处理响应
            if (response.statusCode() == 200) {
                JsonNode jsonNode = objectMapper.readTree(response.body());
                JsonNode choices = jsonNode.get("choices");
                if (choices != null && choices.isArray() && choices.size() > 0) {
                    JsonNode message = choices.get(0).get("message");
                    if (message != null) {
                        return message.get("content").asText();
                    }
                }
            }
            
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
        try {
            // 规范化base_url，确保以/v1结尾
            String baseUrl = normalizeApiUrl(apiUrl);
            String url = baseUrl + "/messages";
            
            // 获取配置参数
            Map<String, Object> config = getStrategyConfig();
            Integer maxTokens = getConfigInteger(config, "strategy_max_tokens", 20000);
            Double temperature = getConfigDouble(config, "strategy_temperature", 0.7);
            Double topP = getConfigDouble(config, "strategy_top_p", 0.9);
            
            // 构建请求体，参考Python版本的实现
            Map<String, Object> requestBody = new HashMap<>();
            requestBody.put("model", modelName);
            requestBody.put("max_tokens", maxTokens);
            requestBody.put("temperature", temperature);
            // Anthropic API 支持 top_p 参数
            if (topP != null) {
                requestBody.put("top_p", topP);
            }
            requestBody.put("system", "You are a professional cryptocurrency trader. Output JSON format only.");
            
            List<Map<String, String>> messages = new ArrayList<>();
            Map<String, String> userMessage = new HashMap<>();
            userMessage.put("role", "user");
            userMessage.put("content", prompt);
            messages.add(userMessage);
            requestBody.put("messages", messages);
            
            String requestBodyJson = objectMapper.writeValueAsString(requestBody);
            
            // 构建HTTP请求
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("x-api-key", apiKey)
                    .header("anthropic-version", "2023-06-01")
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(requestBodyJson))
                    .timeout(Duration.ofSeconds(60))
                    .build();
            
            // 发送请求
            HttpResponse<String> response = httpClient.send(request, 
                    HttpResponse.BodyHandlers.ofString());
            
            // 处理响应
            if (response.statusCode() == 200) {
                JsonNode jsonNode = objectMapper.readTree(response.body());
                JsonNode content = jsonNode.get("content");
                if (content != null && content.isArray() && content.size() > 0) {
                    return content.get(0).get("text").asText();
                }
            }
            
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
        try {
            // 规范化base_url，确保以/v1结尾
            String baseUrl = normalizeApiUrl(apiUrl);
            String url = baseUrl + "/" + modelName + ":generateContent";
            
            // 构建请求体，参考Python版本的实现
            Map<String, Object> requestBody = new HashMap<>();
            List<Map<String, Object>> contents = new ArrayList<>();
            Map<String, Object> content = new HashMap<>();
            List<Map<String, String>> parts = new ArrayList<>();
            Map<String, String> part = new HashMap<>();
            part.put("text", "You are a professional cryptocurrency trader. Output JSON format only.\n\n" + prompt);
            parts.add(part);
            content.put("parts", parts);
            contents.add(content);
            requestBody.put("contents", contents);
            
            // 获取配置参数
            Map<String, Object> config = getStrategyConfig();
            Double temperature = getConfigDouble(config, "strategy_temperature", 0.7);
            Integer maxTokens = getConfigInteger(config, "strategy_max_tokens", 20000);
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
            
            String requestBodyJson = objectMapper.writeValueAsString(requestBody);
            
            // 构建URL，添加API密钥作为查询参数
            String urlWithKey = url + "?key=" + java.net.URLEncoder.encode(apiKey, "UTF-8");
            
            // 构建HTTP请求
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(urlWithKey))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(requestBodyJson))
                    .timeout(Duration.ofSeconds(60))
                    .build();
            
            // 发送请求
            HttpResponse<String> response = httpClient.send(request, 
                    HttpResponse.BodyHandlers.ofString());
            
            // 处理响应
            if (response.statusCode() == 200) {
                JsonNode jsonNode = objectMapper.readTree(response.body());
                JsonNode candidates = jsonNode.get("candidates");
                if (candidates != null && candidates.isArray() && candidates.size() > 0) {
                    JsonNode candidate = candidates.get(0);
                    JsonNode candidateContent = candidate.get("content");
                    if (candidateContent != null) {
                        JsonNode candidateParts = candidateContent.get("parts");
                        if (candidateParts != null && candidateParts.isArray() && candidateParts.size() > 0) {
                            return candidateParts.get(0).get("text").asText();
                        }
                    }
                }
            }
            
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
               "- 决策格式：{\"SYMBOL\": {\"signal\": \"buy_to_enter\" | \"sell_to_enter\", \"quantity\": 100, \"leverage\": 10, \"justification\": \"理由\"}}\n\n" +
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
            defaultConfig.put("strategy_temperature", 0.7);
            defaultConfig.put("strategy_max_tokens", 20000);
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
}

