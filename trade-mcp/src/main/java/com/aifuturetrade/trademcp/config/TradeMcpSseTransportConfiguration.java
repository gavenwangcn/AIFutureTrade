package com.aifuturetrade.trademcp.config;

import io.modelcontextprotocol.json.jackson3.JacksonMcpJsonMapper;
import io.modelcontextprotocol.spec.ProtocolVersions;
import org.springframework.ai.mcp.server.common.autoconfigure.McpServerAutoConfiguration;
import org.springframework.ai.mcp.server.common.autoconfigure.properties.McpServerSseProperties;
import org.springframework.ai.mcp.server.webmvc.transport.WebMvcSseServerTransportProvider;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.AutoConfigureBefore;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import tools.jackson.databind.json.JsonMapper;
import org.springframework.web.servlet.function.RouterFunction;

import java.util.List;

/**
 * 使用 Spring AI 默认的 {@link WebMvcSseServerTransportProvider#builder()} 构建底层传输，
 * 再通过 {@link ExtendedProtocolWebMvcSseTransport} 扩展 MCP 协议协商列表（含 2025-11-25）。
 * <p>
 * 需关闭 {@link org.springframework.ai.mcp.server.webmvc.autoconfigure.McpServerSseWebMvcAutoConfiguration}，
 * 避免重复注册（见 {@code application.yml} {@code spring.autoconfigure.exclude}）。
 */
@Configuration(proxyBeanMethods = false)
@AutoConfigureBefore(McpServerAutoConfiguration.class)
@ConditionalOnClass(WebMvcSseServerTransportProvider.class)
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
        List<String> protocols = List.of(
                ProtocolVersions.MCP_2024_11_05,
                ProtocolVersions.MCP_2025_03_26,
                ProtocolVersions.MCP_2025_06_18,
                ProtocolVersions.MCP_2025_11_25);
        return new ExtendedProtocolWebMvcSseTransport(inner, protocols);
    }

    @Bean
    public RouterFunction<?> webMvcSseServerRouterFunction(ExtendedProtocolWebMvcSseTransport transport) {
        return transport.webMvcDelegate().getRouterFunction();
    }
}
