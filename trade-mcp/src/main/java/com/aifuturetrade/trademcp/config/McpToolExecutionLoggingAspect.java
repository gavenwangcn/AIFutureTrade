package com.aifuturetrade.trademcp.config;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.mcp.annotation.McpTool;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

/**
 * 在 {@link McpTool} 标注的方法真正执行前打印 MCP 工具名（如 {@code trade.market.klines}）与入参摘要。
 * 不依赖 HTTP 体解析，比 Filter 更可靠（与 JSON-RPC / NDJSON 格式无关）。
 */
@Aspect
@Component
public class McpToolExecutionLoggingAspect {

    private static final Logger log = LoggerFactory.getLogger(McpToolExecutionLoggingAspect.class);

    private static final JsonMapper JSON = JsonMapper.builder().build();

    private static final int ARGS_LOG_MAX_CHARS = 4000;

    @Value("${trade-mcp.tool-invocation-log.enabled:true}")
    private boolean enabled;

    @Before("execution(public * com.aifuturetrade.trademcp.tools..*(..)) && @annotation(mcpTool)")
    public void logToolInvocation(JoinPoint joinPoint, McpTool mcpTool) {
        if (!enabled) {
            return;
        }
        String toolName = mcpTool.name();
        String javaMethod = joinPoint.getSignature().getName();
        String argsSummary = summarizeArgs(joinPoint.getArgs());
        log.info("[MCP-TOOL] tool={} javaMethod={} arguments={}", toolName, javaMethod, argsSummary);
    }

    private static String summarizeArgs(Object[] args) {
        if (args == null || args.length == 0) {
            return "[]";
        }
        try {
            String s = JSON.writeValueAsString(args);
            if (s.length() <= ARGS_LOG_MAX_CHARS) {
                return s;
            }
            return s.substring(0, ARGS_LOG_MAX_CHARS) + "...(truncated, totalChars=" + s.length() + ")";
        } catch (Exception e) {
            return String.valueOf(java.util.Arrays.deepToString(args));
        }
    }
}
