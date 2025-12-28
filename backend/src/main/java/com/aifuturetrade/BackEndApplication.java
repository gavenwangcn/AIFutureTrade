package com.aifuturetrade;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * AI Future Trade Java Backend Application
 * Spring Boot应用主入口类
 * 
 * 使用Undertow异步IO服务器，提供高性能接口服务
 */
@SpringBootApplication
@ComponentScan(basePackages = "com.aifuturetrade")
@EnableAsync  // 启用异步任务支持
@EnableScheduling  // 启用定时任务支持
public class BackEndApplication {

    public static void main(String[] args) {
        SpringApplication.run(BackEndApplication.class, args);
    }

}