package com.aifuturetrade.trademcp.config;

import io.modelcontextprotocol.spec.McpServerSession;
import io.modelcontextprotocol.spec.McpServerTransportProvider;
import org.springframework.ai.mcp.server.webmvc.transport.WebMvcSseServerTransportProvider;
import reactor.core.publisher.Mono;

import java.util.List;

/**
 * 将 {@link WebMvcSseServerTransportProvider} 委托为 {@link McpServerTransportProvider}，
 * 并扩展 {@link #protocolVersions()}，使服务端在 initialize 协商时承认含 2025-11-25 的协议列表。
 * <p>
 * Spring AI 默认 {@link WebMvcSseServerTransportProvider#protocolVersions()} 仅返回 2024-11-05，
 * 导致客户端请求 2025-11-25 时出现 WARN；本类在不复制 WebMVC 实现的前提下修正协商列表。
 */
public final class ExtendedProtocolWebMvcSseTransport implements McpServerTransportProvider {

    private final WebMvcSseServerTransportProvider delegate;
    private final List<String> protocolVersions;

    public ExtendedProtocolWebMvcSseTransport(WebMvcSseServerTransportProvider delegate,
            List<String> protocolVersions) {
        this.delegate = delegate;
        this.protocolVersions = List.copyOf(protocolVersions);
    }

    public WebMvcSseServerTransportProvider webMvcDelegate() {
        return delegate;
    }

    @Override
    @SuppressWarnings("rawtypes")
    public List protocolVersions() {
        return protocolVersions;
    }

    @Override
    public void setSessionFactory(McpServerSession.Factory sessionFactory) {
        delegate.setSessionFactory(sessionFactory);
    }

    @Override
    @SuppressWarnings("rawtypes")
    public Mono notifyClients(String method, Object params) {
        return delegate.notifyClients(method, params);
    }

    @Override
    @SuppressWarnings("rawtypes")
    public Mono notifyClient(String sessionId, String method, Object params) {
        return delegate.notifyClient(sessionId, method, params);
    }

    @Override
    public void close() {
        delegate.close();
    }

    @Override
    @SuppressWarnings("rawtypes")
    public Mono closeGracefully() {
        return delegate.closeGracefully();
    }
}
