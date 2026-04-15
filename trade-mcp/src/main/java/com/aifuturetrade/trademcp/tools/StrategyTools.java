package com.aifuturetrade.trademcp.tools;

import com.aifuturetrade.trademcp.client.BackendClient;
import org.springframework.ai.mcp.annotation.McpTool;
import org.springframework.ai.mcp.annotation.McpToolParam;
import org.springframework.stereotype.Component;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 策略通用 MCP：按 ID 重新生成策略代码（调用主库 backend AI 与测试）。
 */
@Component
public class StrategyTools {

    private final BackendClient backendClient;

    public StrategyTools(BackendClient backendClient) {
        this.backendClient = backendClient;
    }

    @McpTool(
            name = "trade_strategy_regenerate_code",
            description = "按 strategys.id 使用 AI **重新生成** strategy_code。可选覆盖 strategy_context、validate_symbol（盯盘）。"
                    + " 必填：strategyId、providerId、modelName。"
                    + " 可选：strategyContext（不传则用库中原文）、validateSymbol（盯盘；不传则用库中）、strategyName（测试展示名）、persist（默认 true；false 仅返回生成结果不保存）。"
                    + " **仅当代码测试通过时写入数据库**（与新建策略校验一致）；未通过时返回 strategyCode 与 testResult 供排查。"
                    + " 适用于 buy / sell / look 任意类型策略。")
    public Map<String, Object> strategyRegenerateCode(
            @McpToolParam(description = "strategys.id（UUID）", required = true) String strategyId,
            @McpToolParam(description = "AI 提供方 ID（与生成策略代码一致）", required = true) String providerId,
            @McpToolParam(description = "模型名称", required = true) String modelName,
            @McpToolParam(description = "策略规则正文；若省略则使用库中现有 strategy_context", required = false) String strategyContext,
            @McpToolParam(description = "盯盘校验合约；若省略则使用库中 validate_symbol", required = false) String validateSymbol,
            @McpToolParam(description = "测试用策略名称展示；省略则用库中 name", required = false) String strategyName,
            @McpToolParam(description = "是否落库，默认 true", required = false) Boolean persist) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("providerId", providerId);
        body.put("modelName", modelName);
        if (strategyContext != null && !strategyContext.isEmpty()) {
            body.put("strategyContext", strategyContext);
        }
        if (validateSymbol != null && !validateSymbol.isEmpty()) {
            body.put("validateSymbol", validateSymbol);
        }
        if (strategyName != null && !strategyName.isEmpty()) {
            body.put("strategyName", strategyName);
        }
        if (persist != null) {
            body.put("persist", persist);
        }
        return backendClient.strategyRegenerateCode(strategyId, body);
    }
}
