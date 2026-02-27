package com.aifuturetrade.trademonitor;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Trade Monitor Service 主应用类
 * 交易监控告警服务
 */
@SpringBootApplication
@MapperScan("com.aifuturetrade.trademonitor.dao.mapper")
public class TradeMonitorApplication {

    public static void main(String[] args) {
        SpringApplication.run(TradeMonitorApplication.class, args);
    }
}
