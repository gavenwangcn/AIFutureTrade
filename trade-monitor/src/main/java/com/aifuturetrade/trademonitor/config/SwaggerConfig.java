package com.aifuturetrade.trademonitor.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.Contact;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Swagger配置类
 */
@Configuration
public class SwaggerConfig {

    @Bean
    public OpenAPI customOpenAPI() {
        return new OpenAPI()
                .info(new Info()
                        .title("Trade Monitor Service API")
                        .version("1.0.0")
                        .description("交易监控告警服务API文档")
                        .contact(new Contact()
                                .name("AIFutureTrade")
                                .email("support@aifuturetrade.com")));
    }
}
