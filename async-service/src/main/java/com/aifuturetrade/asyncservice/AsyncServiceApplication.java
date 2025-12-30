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
        // 注意：需要设置多个可能的属性名，因为不同版本的 Jetty 可能使用不同的属性名
        int maxMessageSize = 200 * 1024; // 200KB
        System.setProperty("org.eclipse.jetty.websocket.maxTextMessageSize", String.valueOf(maxMessageSize));
        System.setProperty("jetty.websocket.maxTextMessageSize", String.valueOf(maxMessageSize));
        System.setProperty("websocket.maxTextMessageSize", String.valueOf(maxMessageSize));
        
        // 同时设置 JVM 参数（如果通过命令行启动，也可以通过 -D 参数设置）
        // -Dorg.eclipse.jetty.websocket.maxTextMessageSize=204800
        
        SpringApplication.run(AsyncServiceApplication.class, args);
    }

}

