package com.aifuturetrade.asyncservice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
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
@SpringBootApplication
@ComponentScan(basePackages = "com.aifuturetrade")
@EnableAsync  // 启用异步任务支持
@EnableScheduling  // 启用定时任务支持
public class AsyncServiceApplication {

    public static void main(String[] args) {
        // 设置 Jetty WebSocket 最大文本消息大小为 200KB
        // 币安全市场ticker数据可能较大（实际约 68KB），默认限制 65KB 不够
        // 通过系统属性设置，确保在创建 WebSocket 客户端之前生效
        System.setProperty("org.eclipse.jetty.websocket.maxTextMessageSize", String.valueOf(200 * 1024));
        
        SpringApplication.run(AsyncServiceApplication.class, args);
    }

}

