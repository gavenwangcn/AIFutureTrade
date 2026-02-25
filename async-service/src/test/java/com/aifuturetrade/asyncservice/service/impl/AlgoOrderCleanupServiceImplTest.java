package com.aifuturetrade.asyncservice.service.impl;

import com.aifuturetrade.asyncservice.dao.mapper.AlgoOrderMapper;
import com.aifuturetrade.asyncservice.service.AlgoOrderCleanupService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;

import java.time.LocalDateTime;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

/**
 * 条件订单清理服务测试
 */
@ExtendWith(MockitoExtension.class)
class AlgoOrderCleanupServiceImplTest {

    @Mock
    private AlgoOrderMapper algoOrderMapper;

    @InjectMocks
    private AlgoOrderCleanupServiceImpl algoOrderCleanupService;

    @BeforeEach
    void setUp() {
        // 设置配置值
        ReflectionTestUtils.setField(algoOrderCleanupService, "retentionHours", 1);
        ReflectionTestUtils.setField(algoOrderCleanupService, "cronExpression", "0 */10 * * * *");
    }

    @Test
    void testCleanupCancelledOrders_Success() {
        // 模拟删除操作返回5条记录
        when(algoOrderMapper.deleteCancelledOrdersBeforeTime(any(LocalDateTime.class)))
                .thenReturn(5);

        // 执行清理
        AlgoOrderCleanupService.CleanupResult result = algoOrderCleanupService.cleanupCancelledOrders();

        // 验证结果
        assertTrue(result.isSuccess());
        assertEquals(5, result.getDeletedCount());
        assertTrue(result.getMessage().contains("5"));

        // 验证mapper方法被调用
        verify(algoOrderMapper, times(1)).deleteCancelledOrdersBeforeTime(any(LocalDateTime.class));
    }

    @Test
    void testCleanupCancelledOrders_NoRecords() {
        // 模拟删除操作返回0条记录
        when(algoOrderMapper.deleteCancelledOrdersBeforeTime(any(LocalDateTime.class)))
                .thenReturn(0);

        // 执行清理
        AlgoOrderCleanupService.CleanupResult result = algoOrderCleanupService.cleanupCancelledOrders();

        // 验证结果
        assertTrue(result.isSuccess());
        assertEquals(0, result.getDeletedCount());

        // 验证mapper方法被调用
        verify(algoOrderMapper, times(1)).deleteCancelledOrdersBeforeTime(any(LocalDateTime.class));
    }

    @Test
    void testCleanupCancelledOrders_Exception() {
        // 模拟删除操作抛出异常
        when(algoOrderMapper.deleteCancelledOrdersBeforeTime(any(LocalDateTime.class)))
                .thenThrow(new RuntimeException("Database error"));

        // 执行清理
        AlgoOrderCleanupService.CleanupResult result = algoOrderCleanupService.cleanupCancelledOrders();

        // 验证结果
        assertFalse(result.isSuccess());
        assertEquals(0, result.getDeletedCount());
        assertTrue(result.getMessage().contains("失败"));

        // 验证mapper方法被调用
        verify(algoOrderMapper, times(1)).deleteCancelledOrdersBeforeTime(any(LocalDateTime.class));
    }
}
