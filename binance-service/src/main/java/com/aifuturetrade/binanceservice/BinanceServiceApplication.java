package com.aifuturetrade.binanceservice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.scheduling.annotation.EnableAsync;

/**
 * Binance Service Application
 * 币安API微服务主入口类
 * 
 * 使用Undertow异步IO服务器，提供高性能接口服务
 */
@SpringBootApplication
@ComponentScan(basePackages = "com.aifuturetrade.binanceservice")
@EnableAsync  // 启用异步支持
public class BinanceServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(BinanceServiceApplication.class, args);
    }

}

