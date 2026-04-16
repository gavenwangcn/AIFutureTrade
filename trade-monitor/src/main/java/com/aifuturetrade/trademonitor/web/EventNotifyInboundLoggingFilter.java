package com.aifuturetrade.trademonitor.web;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * 在 Controller 解析 JSON 之前记录入站请求，便于排查「未打到服务 / 地址错误 / 负载均衡未转发」等问题。
 */
@Slf4j
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class EventNotifyInboundLoggingFilter extends OncePerRequestFilter {

    private static final String NOTIFY_PATH = "/api/events/notify";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {
        String method = request.getMethod();
        String uri = request.getRequestURI();
        if ("POST".equalsIgnoreCase(method) && NOTIFY_PATH.equals(uri)) {
            long len = request.getContentLengthLong();
            log.info(
                    "[trade-monitor][EventNotify] 入站 HTTP | method={} uri={} | remoteAddr={} | X-Forwarded-For={} | X-Real-IP={} | "
                            + "Content-Type={} | Content-Length={} | User-Agent={}",
                    method,
                    uri,
                    request.getRemoteAddr(),
                    headerOrDash(request, "X-Forwarded-For"),
                    headerOrDash(request, "X-Real-IP"),
                    headerOrDash(request, "Content-Type"),
                    len >= 0 ? len : -1,
                    headerOrDash(request, "User-Agent"));
        }
        filterChain.doFilter(request, response);
    }

    private static String headerOrDash(HttpServletRequest request, String name) {
        String v = request.getHeader(name);
        return v != null && !v.isEmpty() ? v : "-";
    }
}
