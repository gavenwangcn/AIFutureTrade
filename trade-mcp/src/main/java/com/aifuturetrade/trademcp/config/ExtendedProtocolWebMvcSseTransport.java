package com.aifuturetrade.trademcp.config;

import io.modelcontextprotocol.spec.McpServerSession;
import io.modelcontextprotocol.spec.McpServerTransportProvider;
import io.modelcontextprotocol.spec.ProtocolVersions;
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

    private static final List<String> DEFAULT_PROTOCOL_VERSIONS = List.of(
            ProtocolVersions.MCP_2024_11_05,
            ProtocolVersions.MCP_2025_03_26,
            ProtocolVersions.MCP_2025_06_18,
            ProtocolVersions.MCP_2025_11_25);

    /** 与 MCP SDK {@link ProtocolVersions} 一致的协商列表（不可变）。 */
    public static List<String> defaultProtocolVersions() {
        return DEFAULT_PROTOCOL_VERSIONS;
    }

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
    public List<String> protocolVersions() {
        return protocolVersions;
    }

    @Override
    public void setSessionFactory(McpServerSession.Factory sessionFactory) {
        delegate.setSessionFactory(sessionFactory);
    }

    @Override
    public Mono<Void> notifyClients(String method, Object params) {
        return delegate.notifyClients(method, params);
    }

    @Override
    public Mono<Void> notifyClient(String sessionId, String method, Object params) {
        return delegate.notifyClient(sessionId, method, params);
    }

    @Override
    public void close() {
        delegate.close();
    }

    @Override
    public Mono<Void> closeGracefully() {
        return delegate.closeGracefully();
    }
}
