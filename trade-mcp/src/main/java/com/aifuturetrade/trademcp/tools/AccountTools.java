package com.aifuturetrade.trademcp.tools;

import com.aifuturetrade.trademcp.client.BackendClient;
import org.springframework.stereotype.Component;

// Spring AI MCP annotations
import org.springframework.ai.mcp.annotation.McpTool;
import org.springframework.ai.mcp.annotation.McpToolParam;

import java.util.Map;

@Component
public class AccountTools {

    private final BackendClient backendClient;

    public AccountTools(BackendClient backendClient) {
        this.backendClient = backendClient;
    }

    @McpTool(name = "trade.account.balance", description = "期货账户余额（必须传modelId；调用backend controller）")
    public Map<String, Object> balance(
            @McpToolParam(description = "模型ID", required = true) String modelId) {
        return backendClient.balance(modelId);
    }

    @McpTool(name = "trade.account.positions", description = "期货账户持仓（必须传modelId；调用backend controller）")
    public Map<String, Object> positions(
            @McpToolParam(description = "模型ID", required = true) String modelId) {
        return backendClient.positions(modelId);
    }

    @McpTool(name = "trade.account.account_info", description = "期货账户信息（必须传modelId；调用backend controller）")
    public Map<String, Object> accountInfo(
            @McpToolParam(description = "模型ID", required = true) String modelId) {
        return backendClient.accountInfo(modelId);
    }
}

