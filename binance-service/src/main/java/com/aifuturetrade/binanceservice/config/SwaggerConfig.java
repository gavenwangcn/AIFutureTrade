package com.aifuturetrade.binanceservice.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * SpringDoc OpenAPI 配置类（替代 Springfox Swagger）
 * 用于生成API文档，兼容 Spring Boot 3.x
 * 
 * 访问地址：http://localhost:5004/swagger-ui/index.html
 */
@Configuration
public class SwaggerConfig {

    @Bean
    public OpenAPI customOpenAPI() {
        return new OpenAPI()
                .info(new Info()
                        .title("Binance Service API")
                        .description("Binance Service API Documentation")
                        .version("1.0.0")
                        .contact(new Contact()
                                .name("AI Future Trade Team")
                                .email("contact@aifuturetrade.com")));
    }
}

