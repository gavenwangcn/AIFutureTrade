package com.aifuturetrade.trademcp.config;

import io.modelcontextprotocol.json.jackson3.JacksonMcpJsonMapper;
import org.springframework.ai.mcp.server.common.autoconfigure.McpServerAutoConfiguration;
import org.springframework.ai.mcp.server.common.autoconfigure.properties.McpServerSseProperties;
import org.springframework.ai.mcp.server.webmvc.transport.WebMvcSseServerTransportProvider;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.AutoConfigureBefore;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import tools.jackson.databind.json.JsonMapper;

/**
 * 使用 Spring AI 默认的 {@link WebMvcSseServerTransportProvider#builder()} 构建底层传输，
 * 再通过 {@link ExtendedProtocolWebMvcSseTransport} 扩展 MCP 协议协商列表（含 2025-11-25）。
 * <p>
 * 需关闭 {@link org.springframework.ai.mcp.server.webmvc.autoconfigure.McpServerSseWebMvcAutoConfiguration}，
 * 避免重复注册（见 {@code application.yml} {@code spring.autoconfigure.exclude}）。
 * <p>
 * 仅在 {@code spring.ai.mcp.server.protocol=SSE}（或未配置且使用默认 SSE）时生效，避免 STDIO 等模式下误注册 WebMvc SSE。
 */
@Configuration(proxyBeanMethods = false)
@AutoConfigureBefore(McpServerAutoConfiguration.class)
@ConditionalOnClass(WebMvcSseServerTransportProvider.class)
@ConditionalOnProperty(
        prefix = "spring.ai.mcp.server",
        name = "protocol",
        havingValue = "SSE",
        matchIfMissing = true)
@EnableConfigurationProperties(McpServerSseProperties.class)
public class TradeMcpSseTransportConfiguration {

    @Bean
    @Primary
    public ExtendedProtocolWebMvcSseTransport mcpServerTransportWebMvc(
            @Qualifier("mcpServerJsonMapper") JsonMapper jsonMapper,
            McpServerSseProperties serverProperties) {
        WebMvcSseServerTransportProvider inner = WebMvcSseServerTransportProvider.builder()
                .jsonMapper(new JacksonMcpJsonMapper(jsonMapper))
                .baseUrl(serverProperties.getBaseUrl())
                .sseEndpoint(serverProperties.getSseEndpoint())
                .messageEndpoint(serverProperties.getSseMessageEndpoint())
                .keepAliveInterval(serverProperties.getKeepAliveInterval())
                .build();
        return new ExtendedProtocolWebMvcSseTransport(inner, ExtendedProtocolWebMvcSseTransport.defaultProtocolVersions());
    }

    @Bean
    public org.springframework.web.servlet.function.RouterFunction<?> webMvcSseServerRouterFunction(
            ExtendedProtocolWebMvcSseTransport transport) {
        return transport.webMvcDelegate().getRouterFunction();
    }
}
