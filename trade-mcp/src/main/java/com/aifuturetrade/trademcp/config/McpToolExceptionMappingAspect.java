package com.aifuturetrade.trademcp.config;

import com.aifuturetrade.trademcp.client.ThrowableFormatter;
import java.util.LinkedHashMap;
import java.util.Map;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.mcp.annotation.McpTool;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

/**
 * MCP 工具方法若抛出未捕获异常，Spring AI 可能仅向客户端返回泛化错误；此处转为 {@code success=false} 的 Map，
 * 并把完整异常链写入 {@code error}，便于模型根据 Java 后端或本服务真实原因排查。
 */
@Aspect
@Component
@Order(0)
public class McpToolExceptionMappingAspect {

    private static final Logger log = LoggerFactory.getLogger(McpToolExceptionMappingAspect.class);

    @Around("execution(public java.util.Map com.aifuturetrade.trademcp.tools..*(..)) && @annotation(mcpTool)")
    public Object mapUncaughtToolExceptions(ProceedingJoinPoint pjp, McpTool mcpTool) throws Throwable {
        try {
            return pjp.proceed();
        } catch (Throwable t) {
            log.error("[MCP-TOOL] tool={} uncaught throwable", mcpTool != null ? mcpTool.name() : "?", t);
            Map<String, Object> err = new LinkedHashMap<>();
            err.put("success", false);
            err.put("error", ThrowableFormatter.formatForClient(t));
            err.put("errorSource", "trade-mcp: uncaught exception in @McpTool method");
            if (mcpTool != null) {
                err.put("toolName", mcpTool.name());
            }
            err.put("errorType", t.getClass().getName());
            Throwable root = ThrowableFormatter.getRootCause(t);
            if (root != null && root != t) {
                err.put("rootCauseType", root.getClass().getName());
            }
            return err;
        }
    }
}
