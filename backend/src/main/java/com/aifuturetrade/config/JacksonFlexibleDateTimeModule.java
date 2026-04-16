package com.aifuturetrade.config;

import com.aifuturetrade.common.jackson.FlexibleLocalDateTimeDeserializer;
import com.fasterxml.jackson.databind.module.SimpleModule;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;

import java.time.LocalDateTime;

/**
 * 通过 {@link Jackson2ObjectMapperBuilderCustomizer} 注册：
 * <ul>
 *   <li>{@link JavaTimeModule}：序列化/反序列化 {@code java.time.*}（Jackson 2.19+ 在
 *       {@code REQUIRE_HANDLERS_FOR_JAVA8_TIMES} 下必须存在，否则 Map 中含 {@link LocalDateTime} 会报
 *       UnsupportedTypeSerializer，如 leaderboard {@code gainers[].event_time}）</li>
 *   <li>自定义 {@link LocalDateTime} 反序列化（空格 / 带偏移等宽松格式）</li>
 * </ul>
 */
@Configuration
public class JacksonFlexibleDateTimeModule {

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    public Jackson2ObjectMapperBuilderCustomizer flexibleLocalDateTimeCustomizer() {
        return builder -> {
            builder.modules(new JavaTimeModule());
            SimpleModule m = new SimpleModule("flexible-local-date-time");
            m.addDeserializer(LocalDateTime.class, new FlexibleLocalDateTimeDeserializer());
            builder.modules(m);
        };
    }
}
