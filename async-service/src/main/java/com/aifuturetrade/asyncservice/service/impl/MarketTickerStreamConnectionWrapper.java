package com.aifuturetrade.asyncservice.service.impl;

import com.binance.connector.client.common.websocket.adapter.stream.StreamConnectionWrapper;
import com.binance.connector.client.common.websocket.configuration.WebSocketClientConfiguration;
import java.util.function.Consumer;
import lombok.extern.slf4j.Slf4j;
import org.eclipse.jetty.websocket.client.WebSocketClient;

/**
 * 针对 MarketTicker 场景的 StreamConnectionWrapper 扩展：
 * 仅覆写 {@link #onWebSocketError(Throwable)}，在 SDK 收到断链/异常时触发外部重连逻辑，
 * 防止服务端异常断链导致流处理线程长期阻塞而中断同步。
 */
@Slf4j
public class MarketTickerStreamConnectionWrapper extends StreamConnectionWrapper {

    private final Consumer<Throwable> onWebSocketErrorCallback;

    public MarketTickerStreamConnectionWrapper(
            WebSocketClientConfiguration clientConfiguration,
            WebSocketClient webSocketClient,
            Consumer<Throwable> onWebSocketErrorCallback) {
        super(clientConfiguration, webSocketClient);
        this.onWebSocketErrorCallback = onWebSocketErrorCallback;
    }

    @Override
    public void onWebSocketError(Throwable cause) {
        // 保持 SDK 原有行为（日志/状态处理）
        super.onWebSocketError(cause);

        // 触发外部重连（避免在 SDK 内部无限重试/仅记录日志导致业务卡死）
        if (onWebSocketErrorCallback == null) {
            return;
        }
        try {
            onWebSocketErrorCallback.accept(cause);
        } catch (Exception callbackEx) {
            log.warn("[MarketTickerStreamConnectionWrapper] onWebSocketErrorCallback 执行失败", callbackEx);
        }
    }
}

