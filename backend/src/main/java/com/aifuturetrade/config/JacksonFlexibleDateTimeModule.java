package com.aifuturetrade.config;

import com.aifuturetrade.common.jackson.FlexibleLocalDateTimeDeserializer;
import com.fasterxml.jackson.databind.module.SimpleModule;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.LocalDateTime;

/**
 * 通过 {@link Jackson2ObjectMapperBuilderCustomizer} 注册 {@link LocalDateTime} 反序列化器，
 * 确保 WebMvc 使用的 {@link com.fasterxml.jackson.databind.ObjectMapper} 一定应用（仅注册 {@code Module}
 * Bean 在部分环境下可能未合并到 MVC MessageConverter）。
 */
@Configuration
public class JacksonFlexibleDateTimeModule {

    @Bean
    public Jackson2ObjectMapperBuilderCustomizer flexibleLocalDateTimeCustomizer() {
        return builder -> {
            SimpleModule m = new SimpleModule("flexible-local-date-time");
            m.addDeserializer(LocalDateTime.class, new FlexibleLocalDateTimeDeserializer());
            builder.modules(m);
        };
    }
}
