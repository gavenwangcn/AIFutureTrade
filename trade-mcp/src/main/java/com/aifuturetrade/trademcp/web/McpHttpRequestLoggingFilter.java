package com.aifuturetrade.trademcp.web;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.lang.NonNull;
import org.springframework.stereotype.Component;
import org.springframework.util.AntPathMatcher;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * 对每个进入 MCP Server 的 HTTP 请求打印 INFO 日志：方法、URI、客户端 IP、结束时的状态码与耗时。
 * 经反向代理时优先使用 X-Forwarded-For / X-Real-IP。
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 20)
public class McpHttpRequestLoggingFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(McpHttpRequestLoggingFilter.class);

    private final AntPathMatcher pathMatcher = new AntPathMatcher();

    /** 默认跳过常见探活路径，避免刷屏；可按需扩展 */
    private static final String[] DEFAULT_EXCLUDED = {
            "/actuator/**",
            "/favicon.ico"
    };

    @Value("${trade-mcp.request-log.enabled:true}")
    private boolean enabled;

    @Override
    protected boolean shouldNotFilter(@NonNull HttpServletRequest request) {
        if (!enabled) {
            return true;
        }
        String uri = request.getRequestURI();
        for (String pattern : DEFAULT_EXCLUDED) {
            if (pathMatcher.match(pattern, uri)) {
                return true;
            }
        }
        return false;
    }

    @Override
    protected void doFilterInternal(@NonNull HttpServletRequest request, @NonNull HttpServletResponse response,
            @NonNull FilterChain filterChain) throws ServletException, IOException {
        long startNs = System.nanoTime();
        String method = request.getMethod();
        String uriWithQuery = buildUriWithQuery(request);
        String clientIp = resolveClientIp(request);

        log.info("[MCP-HTTP] --> method={} uri=\"{}\" clientIp={}", method, uriWithQuery, clientIp);

        try {
            filterChain.doFilter(request, response);
        } finally {
            long durationMs = (System.nanoTime() - startNs) / 1_000_000L;
            int status = response.getStatus();
            log.info("[MCP-HTTP] <-- method={} uri=\"{}\" status={} durationMs={} clientIp={}",
                    method, uriWithQuery, status, durationMs, clientIp);
        }
    }

    private static String buildUriWithQuery(HttpServletRequest request) {
        String uri = request.getRequestURI();
        String query = request.getQueryString();
        if (query != null && !query.isEmpty()) {
            return uri + "?" + query;
        }
        return uri;
    }

    /**
     * 与常见反向代理约定一致：X-Forwarded-For 取第一段；否则 X-Real-IP；否则 RemoteAddr。
     */
    private static String resolveClientIp(HttpServletRequest request) {
        String xff = request.getHeader("X-Forwarded-For");
        if (xff != null && !xff.isBlank()) {
            return xff.split(",")[0].trim();
        }
        String real = request.getHeader("X-Real-IP");
        if (real != null && !real.isBlank()) {
            return real.trim();
        }
        return request.getRemoteAddr();
    }
}
