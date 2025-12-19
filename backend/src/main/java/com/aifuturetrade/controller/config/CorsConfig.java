package com.aifuturetrade.controller.config;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.filter.CorsFilter;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * CORS跨域配置类
 * 允许前端应用跨域访问后端API
 * 
 * 使用 CorsFilter 和 WebMvcConfigurer 双重配置，确保所有请求（包括预检请求）都能正确处理
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
        registry.addMapping("/**")
                // 允许所有来源（生产环境建议指定具体域名）
                // 注意：如果需要 allowCredentials(true)，必须指定具体域名，不能使用 "*"
                .allowedOriginPatterns("*")
                // 允许所有HTTP方法（包括 OPTIONS 预检请求）
                .allowedMethods("GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD")
                // 允许所有请求头
                .allowedHeaders("*")
                // 暴露响应头
                .exposedHeaders("*")
                // 允许发送凭证（如Cookie）
                // 注意：当使用 "*" 作为 allowedOriginPatterns 时，allowCredentials 必须为 false
                .allowCredentials(false)
                // 预检请求的缓存时间（秒）
                .maxAge(3600);
    }

    /**
     * 使用CorsFilter来处理OPTIONS预检请求
     * 设置最高优先级，确保在所有其他过滤器之前处理CORS请求
     * 
     * 注意：当 setAllowCredentials(true) 时，不能使用 "*" 作为 addAllowedOriginPattern
     * 如果需要发送凭证，请使用 addAllowedOrigin 并指定具体域名
     */
    @Bean
    public FilterRegistrationBean<CorsFilter> corsFilterRegistration() {
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        CorsConfiguration config = new CorsConfiguration();
        
        // 允许所有来源（生产环境建议指定具体域名）
        // 注意：如果需要 setAllowCredentials(true)，必须使用 addAllowedOrigin 并指定具体域名，不能使用 "*"
        config.addAllowedOriginPattern("*");
        
        // 允许所有HTTP方法（包括 OPTIONS 预检请求）
        config.addAllowedMethod("*");
        
        // 允许所有请求头
        config.addAllowedHeader("*");
        
        // 暴露所有响应头
        config.addExposedHeader("*");
        
        // 允许发送凭证
        // 注意：当使用 "*" 作为 allowedOriginPattern 时，allowCredentials 必须为 false
        config.setAllowCredentials(false);
        
        // 预检请求的缓存时间（秒）
        config.setMaxAge(3600L);
        
        // 对所有路径应用CORS配置
        source.registerCorsConfiguration("/**", config);
        
        FilterRegistrationBean<CorsFilter> bean = new FilterRegistrationBean<>(new CorsFilter(source));
        // 设置最高优先级，确保在所有其他过滤器之前处理CORS请求
        bean.setOrder(Ordered.HIGHEST_PRECEDENCE);
        return bean;
    }
}

