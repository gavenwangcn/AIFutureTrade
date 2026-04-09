package com.aifuturetrade.trademcp.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
@EnableConfigurationProperties(DownstreamProperties.class)
public class TradeMcpConfig {

    @Bean
    public RestClient restClient() {
        return RestClient.builder().build();
    }
}

