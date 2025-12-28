package com.aifuturetrade.binanceservice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;

/**
 * Binance Service Application
 * 币安API微服务主入口类
 */
@SpringBootApplication
@ComponentScan(basePackages = "com.aifuturetrade.binanceservice")
public class BinanceServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(BinanceServiceApplication.class, args);
    }

}

