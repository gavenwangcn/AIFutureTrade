package com.aifuturetrade.controller.config;

import com.corundumstudio.socketio.SocketIOServer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import javax.annotation.PostConstruct;
import javax.annotation.PreDestroy;

/**
 * Socket.IO 服务器配置
 * 提供 WebSocket 连接支持，避免前端连接错误
 * 
 * 注意：当前实现为占位服务，不提供实际功能
 * 涨跌幅榜和K线数据已改为轮询方式，不再使用 WebSocket 推送
 * 
 * Socket.IO Java 服务器需要独立的端口，不能与 Spring Boot HTTP 服务器共用同一端口
 * 因此使用独立的端口（默认 5003），前端需要通过代理或直接连接此端口
 */
@Configuration
public class SocketIOConfig {

    private static final Logger logger = LoggerFactory.getLogger(SocketIOConfig.class);

    @Value("${server.port:5002}")
    private int serverPort;

    @Value("${socketio.port:5003}")
    private int socketioPort;

    private SocketIOServer server;

    @Bean
    public SocketIOServer socketIOServer() {
        // 使用完全限定名避免与 Spring 的 Configuration 冲突
        com.corundumstudio.socketio.Configuration config = new com.corundumstudio.socketio.Configuration();
        
        // 设置主机和端口
        // 注意：netty-socketio 使用独立的 Netty 服务器，不能与 Spring Boot 的 Tomcat 共用同一端口
        // 因此使用独立的端口（默认 5003），前端需要通过代理或直接连接此端口
        config.setHostname("0.0.0.0");
        config.setPort(socketioPort);
        
        // 允许跨域请求
        config.setOrigin("*");
        
        // 设置传输方式（支持 WebSocket 和长轮询）
        config.setTransports(com.corundumstudio.socketio.Transport.WEBSOCKET, 
                            com.corundumstudio.socketio.Transport.POLLING);
        
        // 设置心跳间隔（秒）
        config.setPingInterval(25);
        config.setPingTimeout(60);
        
        // 设置最大连接数
        config.setMaxHttpContentLength(1024 * 1024); // 1MB
        
        // 设置上下文路径（与前端配置保持一致）
        config.setContext("/socket.io");
        
        server = new SocketIOServer(config);
        
        // 添加连接事件监听
        server.addConnectListener(client -> {
            logger.info("Socket.IO client connected: {}", client.getSessionId());
        });
        
        // 添加断开连接事件监听
        server.addDisconnectListener(client -> {
            logger.info("Socket.IO client disconnected: {}", client.getSessionId());
        });
        
        // 注意：netty-socketio 2.0.3 版本可能不支持 addConnectErrorListener
        // 如果方法不存在，可以移除或使用其他方式处理错误
        try {
            // 尝试添加连接错误监听（如果 API 支持）
            // server.addConnectErrorListener((client, error) -> {
            //     logger.error("Socket.IO connection error for client {}: {}", 
            //                 client != null ? client.getSessionId() : "unknown", 
            //                 error.getMessage());
            // });
        } catch (Exception e) {
            logger.debug("addConnectErrorListener not available in this version of netty-socketio");
        }
        
        return server;
    }

    @PostConstruct
    public void startServer() {
        try {
            // server字段在@Bean方法中已经设置，直接使用即可
            if (server == null) {
                logger.warn("Socket.IO server is null, cannot start. This may be due to initialization order issue.");
                logger.warn("Socket.IO functionality will not be available, but application will continue to run.");
                return;
            }
            
            server.start();
            logger.info("Socket.IO server started on port {} (context: /socket.io)", socketioPort);
            logger.info("Note: Socket.IO uses a separate port from HTTP server. HTTP server: {}, Socket.IO: {}", 
                       serverPort, socketioPort);
        } catch (Exception e) {
            logger.error("Failed to start Socket.IO server", e);
            // 如果启动失败，记录错误但不阻止应用启动
            // 因为 WebSocket 功能当前不是必需的（涨跌幅榜和K线数据已改为轮询方式）
        }
    }

    @PreDestroy
    public void stopServer() {
        if (server != null) {
            server.stop();
            logger.info("Socket.IO server stopped");
        }
    }
}

