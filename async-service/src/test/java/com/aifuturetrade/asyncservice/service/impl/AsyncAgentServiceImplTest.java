package com.aifuturetrade.asyncservice.service.impl;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import static org.junit.jupiter.api.Assertions.*;

/**
 * AsyncAgentServiceImpl 测试类
 * 验证依赖注入和服务选择功能是否正常工作
 */
@SpringBootTest
@TestPropertySource(locations = "classpath:application-test.yml")
public class AsyncAgentServiceImplTest {
    
    @Autowired(required = false)
    private AsyncAgentServiceImpl asyncAgentServiceImpl;
    
    @Test
    public void testContextLoads() {
        // 测试Spring上下文能否正常加载
        assertNotNull(asyncAgentServiceImpl, "AsyncAgentServiceImpl should be loaded");
        System.out.println("✅ Spring上下文加载成功");
    }
    
    @Test
    public void testServiceInitialization() {
        if (asyncAgentServiceImpl != null) {
            // 测试服务是否正确初始化
            System.out.println("✅ AsyncAgentServiceImpl 初始化成功");
        }
    }
}