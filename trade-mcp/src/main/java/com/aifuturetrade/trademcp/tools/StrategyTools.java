package com.aifuturetrade.trademcp.tools;

import com.aifuturetrade.trademcp.client.BackendClient;
import org.springframework.ai.mcp.annotation.McpTool;
import org.springframework.ai.mcp.annotation.McpToolParam;
import org.springframework.stereotype.Component;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 策略通用 MCP：按 ID 重新生成策略代码、按 ID 删除策略（调用主库 backend）。
 */
@Component
public class StrategyTools {

    private final BackendClient backendClient;

    public StrategyTools(BackendClient backendClient) {
        this.backendClient = backendClient;
    }

    @McpTool(
            name = "trade_strategy_regenerate_code",
            description = "按 strategys.id 使用 AI **重新生成** strategy_code（与前端「获取代码」同源）。"
                    + " **提供方与模型使用系统设置「策略API提供方」**，无需传入 providerId/modelName。"
                    + " 必填：strategyId。"
                    + " 可选：strategyContext（不传则用库中原文）、validateSymbol（盯盘；不传则用库中）、strategyName（测试展示名）、persist（默认 true；false 仅返回生成结果不保存）。"
                    + " **响应含 `strategyCode`、`testPassed`、`testResult`**：模型须向用户**展示完整策略代码**，并对照用户业务需求判断逻辑是否达标；不达标则澄清需求后带修订后的 strategyContext 再调（可先 persist=false 试生成）。"
                    + " **仅当代码测试通过且 persist 未禁时写入数据库**；未通过时仍返回生成代码与 testResult 供排查。"
                    + " 适用于 buy / sell / look 任意类型策略。")
    public Map<String, Object> strategyRegenerateCode(
            @McpToolParam(description = "strategys.id（UUID）", required = true) String strategyId,
            @McpToolParam(description = "策略规则正文；若省略则使用库中现有 strategy_context", required = false) String strategyContext,
            @McpToolParam(description = "盯盘校验合约；若省略则使用库中 validate_symbol", required = false) String validateSymbol,
            @McpToolParam(description = "测试用策略名称展示；省略则用库中 name", required = false) String strategyName,
            @McpToolParam(description = "是否落库，默认 true", required = false) Boolean persist) {
        Map<String, Object> body = new LinkedHashMap<>();
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

    @McpTool(
            name = "trade_strategy_apply_submitted_code",
            description = "按 strategys.id **直接提交**用户或模型给出的 `strategy_code`，**不调用 AI 重新生成**。"
                    + " 服务端会调用 Trade 与「获取代码」相同的**完整测试执行**（含试跑）；**仅 `testPassed=true` 时写入数据库**。"
                    + " 必填：`strategyId`、`strategyCode`（完整 Python 策略类代码）。"
                    + " 可选：`strategyName`（测试展示名，默认库中 name）、`validateSymbol`（仅 type=look 时可覆盖库中合约）。"
                    + " 响应含 `strategyCode`、`testPassed`、`testResult`、`persisted`、`message`；未通过时 `persisted=false` 且库不变。"
                    + " 适用于 buy / sell / look；与 `trade_strategy_regenerate_code`（走模型生成）二选一。")
    public Map<String, Object> strategyApplySubmittedCode(
            @McpToolParam(description = "strategys.id（UUID）", required = true) String strategyId,
            @McpToolParam(description = "待保存的完整策略代码（须通过服务端测试）", required = true) String strategyCode,
            @McpToolParam(description = "测试展示名；省略则用库中 name", required = false) String strategyName,
            @McpToolParam(description = "盯盘策略测试用合约；省略则用库中 validate_symbol", required = false) String validateSymbol) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("strategyCode", strategyCode);
        if (strategyName != null && !strategyName.isEmpty()) {
            body.put("strategyName", strategyName);
        }
        if (validateSymbol != null && !validateSymbol.isEmpty()) {
            body.put("validateSymbol", validateSymbol);
        }
        return backendClient.strategyApplySubmittedCode(strategyId, body);
    }

    @McpTool(
            name = "trade_strategy_delete",
            description = "按 **strategys.id（UUID）** 删除一条策略记录，对应后端 `DELETE /api/strategies/{id}`。"
                    + " 必填：`strategyId`。"
                    + " 成功时响应通常含 `success=true` 与 `message`。"
                    + " **注意**：若数据库中仍有引用该策略的记录（例如未清理的盯盘任务 `market_look`、模型关联等），删除可能失败；应先处理关联数据或按报错排查。"
                    + " 适用于 buy / sell / look 任意类型；**删除不可恢复**，调用前请用户确认。")
    public Map<String, Object> strategyDelete(
            @McpToolParam(description = "strategys.id（UUID）", required = true) String strategyId) {
        return backendClient.strategyDelete(strategyId);
    }
}
