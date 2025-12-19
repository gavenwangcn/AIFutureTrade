package com.aifuturetrade.controller.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.filter.CorsFilter;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * CORS跨域配置类
 * 允许前端应用跨域访问后端API
 */
@Configuration
public class CorsConfig implements WebMvcConfigurer {

    /**
     * 配置CORS跨域访问
     * 允许所有来源、所有方法、所有请求头
     * 
     * 注意：当 allowCredentials(true) 时，不能使用 "*" 作为 allowedOriginPatterns
     * 如果需要发送凭证，请指定具体的域名列表
     */
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                // 允许所有来源（生产环境建议指定具体域名）
                // 注意：如果需要 allowCredentials(true)，必须指定具体域名，不能使用 "*"
                .allowedOriginPatterns("*")
                // 允许所有HTTP方法
                .allowedMethods("GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH")
                // 允许所有请求头
                .allowedHeaders("*")
                // 允许发送凭证（如Cookie）
                // 注意：当使用 "*" 作为 allowedOriginPatterns 时，allowCredentials 必须为 false
                .allowCredentials(false)
                // 预检请求的缓存时间（秒）
                .maxAge(3600);
    }

    /**
     * 使用CorsFilter来处理OPTIONS预检请求
     * 这是另一种配置方式，可以更细粒度地控制CORS
     * 
     * 注意：当 setAllowCredentials(true) 时，不能使用 "*" 作为 addAllowedOriginPattern
     * 如果需要发送凭证，请使用 addAllowedOrigin 并指定具体域名
     */
    @Bean
    public CorsFilter corsFilter() {
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        CorsConfiguration config = new CorsConfiguration();
        
        // 允许所有来源（生产环境建议指定具体域名）
        // 注意：如果需要 setAllowCredentials(true)，必须使用 addAllowedOrigin 并指定具体域名，不能使用 "*"
        config.addAllowedOriginPattern("*");
        
        // 允许所有HTTP方法
        config.addAllowedMethod("*");
        
        // 允许所有请求头
        config.addAllowedHeader("*");
        
        // 允许发送凭证
        // 注意：当使用 "*" 作为 allowedOriginPattern 时，allowCredentials 必须为 false
        config.setAllowCredentials(false);
        
        // 预检请求的缓存时间（秒）
        config.setMaxAge(3600L);
        
        // 对所有路径应用CORS配置
        source.registerCorsConfiguration("/**", config);
        
        return new CorsFilter(source);
    }
}

