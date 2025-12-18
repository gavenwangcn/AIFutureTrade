package com.aifuturetrade;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;

/**
 * AI Future Trade Java Backend Application
 * Spring Boot应用主入口类
 */
@SpringBootApplication
@ComponentScan(basePackages = "com.aifuturetrade")
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

}