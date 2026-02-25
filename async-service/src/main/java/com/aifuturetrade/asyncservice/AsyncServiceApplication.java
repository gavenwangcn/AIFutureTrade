package com.aifuturetrade.asyncservice;

import com.aifuturetrade.asyncservice.config.WebSocketConfig;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * Async Service Application
 * 异步同步服务主入口类
 * 
 * 提供以下功能：
 * 1. 市场数据流：market_tickers服务，实时接收币安ticker数据
 * 2. 价格刷新：price_refresh服务，刷新24_market_tickers表的开盘价格
 * 3. Symbol下线：market_symbol_offline服务，处理下线的交易对
 */
@Slf4j
@SpringBootApplication
@ComponentScan(basePackages = "com.aifuturetrade")
@EnableAsync  // 启用异步任务支持
@EnableScheduling  // 启用定时任务支持
@EnableConfigurationProperties({WebSocketConfig.class})  // 启用配置属性支持
public class AsyncServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(AsyncServiceApplication.class, args);
    }
    
    /**
     * 应用启动后执行配置初始化
     */
    // @PostConstruct
    // public void initWebSocketConfig() {
    //     // WebSocketConfig Bean已经自动注入并初始化
    //     // 系统属性设置将在WebSocketClient创建时自动应用
    // }
}

