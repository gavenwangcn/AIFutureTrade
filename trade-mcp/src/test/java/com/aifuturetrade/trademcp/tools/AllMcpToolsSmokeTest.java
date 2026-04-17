package com.aifuturetrade.trademcp.tools;

import com.aifuturetrade.trademcp.TradeMcpApplication;
import com.aifuturetrade.trademcp.client.BackendClient;
import com.aifuturetrade.trademcp.client.BinanceServiceClient;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.nullable;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.when;

/**
 * 对 {@code @McpTool} 对应 Java 方法各执行一次，确保 Spring 装配与调用链无异常。
 * 下游 {@link BackendClient}、{@link BinanceServiceClient} 已 Mock，不会请求真实 backend / 交易所。
 */
@SpringBootTest(classes = TradeMcpApplication.class)
class AllMcpToolsSmokeTest {

    private static final String MODEL_ID = "1";

    @MockitoBean
    private BackendClient backendClient;

    @MockitoBean
    private BinanceServiceClient binanceServiceClient;

    @Autowired
    private AccountTools accountTools;

    @Autowired
    private OrderTools orderTools;

    @Autowired
    private MarketTools marketTools;

    @Autowired
    private MarketTickersTools marketTickersTools;

    @Autowired
    private MarketLookTools marketLookTools;

    @Autowired
    private StrategyTools strategyTools;

    @BeforeEach
    void stubDownstream() {
        Map<String, Object> okEmptyPage = new HashMap<>();
        okEmptyPage.put("success", true);
        okEmptyPage.put("data", List.of());
        okEmptyPage.put("total", 0L);
        okEmptyPage.put("page", 1);
        okEmptyPage.put("size", 20);
        okEmptyPage.put("pages", 0);

        Map<String, Object> okCount = new HashMap<>();
        okCount.put("success", true);
        okCount.put("total", 0L);

        Map<String, Object> okSymbols = new HashMap<>();
        okSymbols.put("success", true);
        okSymbols.put("data", List.of("BTCUSDT"));
        okSymbols.put("total", 1);

        Map<String, Object> okLatest = new HashMap<>();
        okLatest.put("success", true);
        okLatest.put("data", Map.of("symbol", "BTCUSDT", "last_price", 1.0));

        Map<String, Object> okSql = new HashMap<>();
        okSql.put("success", true);
        okSql.put("data", List.of());

        lenient().when(backendClient.accountInfo(anyString())).thenReturn(okEmptyPage);
        lenient().when(backendClient.balance(anyString())).thenReturn(okEmptyPage);
        lenient().when(backendClient.positions(anyString())).thenReturn(okEmptyPage);
        lenient().when(backendClient.sellPosition(anyString(), anyString())).thenReturn(okEmptyPage);
        lenient().when(backendClient.orderCreate(anyString(), anyMap())).thenReturn(okEmptyPage);
        lenient().when(backendClient.orderCancel(anyString(), anyMap())).thenReturn(okEmptyPage);
        lenient().when(backendClient.orderGet(anyString(), anyString(), nullable(Long.class), nullable(String.class)))
                .thenReturn(okEmptyPage);
        lenient().when(backendClient.openOrders(anyString(), nullable(String.class))).thenReturn(okEmptyPage);

        lenient().when(backendClient.marketTickersRows(
                nullable(Integer.class),
                nullable(Integer.class),
                nullable(String.class),
                nullable(List.class),
                nullable(String.class),
                nullable(String.class),
                nullable(Double.class),
                nullable(Double.class),
                nullable(Double.class),
                nullable(Double.class),
                nullable(Double.class),
                nullable(Double.class),
                nullable(String.class),
                nullable(Boolean.class)
        )).thenReturn(okEmptyPage);

        lenient().when(backendClient.marketTickersRowsCount(
                nullable(String.class),
                nullable(List.class),
                nullable(String.class),
                nullable(String.class),
                nullable(Double.class),
                nullable(Double.class),
                nullable(Double.class),
                nullable(Double.class),
                nullable(Double.class),
                nullable(Double.class)
        )).thenReturn(okCount);

        lenient().when(backendClient.marketTickersSnapshot(
                nullable(Integer.class),
                nullable(Integer.class),
                nullable(List.class),
                nullable(String.class)
        )).thenReturn(okEmptyPage);

        lenient().when(backendClient.marketTickersSnapshotCount(nullable(List.class), nullable(String.class)))
                .thenReturn(okCount);

        lenient().when(backendClient.marketTickersAllSymbols()).thenReturn(okSymbols);
        lenient().when(backendClient.marketTickersLatest(anyString())).thenReturn(okLatest);
        lenient().when(backendClient.marketTickersSql(anyMap())).thenReturn(okSql);

        Map<String, Object> okId = new HashMap<>();
        okId.put("id", "00000000-0000-0000-0000-000000000001");
        okId.put("message", "ok");
        lenient().when(backendClient.marketLookCreate(anyMap())).thenReturn(okId);
        lenient().when(backendClient.strategyCreate(anyMap())).thenReturn(okId);
        lenient().when(backendClient.strategyRegenerateCode(anyString(), anyMap())).thenReturn(okId);
        lenient().when(backendClient.strategyApplySubmittedCode(anyString(), anyMap())).thenReturn(okId);
        Map<String, Object> okStrategyDelete = new HashMap<>();
        okStrategyDelete.put("success", true);
        okStrategyDelete.put("message", "Strategy deleted successfully");
        lenient().when(backendClient.strategyDelete(anyString())).thenReturn(okStrategyDelete);
        lenient().when(backendClient.strategyGetById(anyString())).thenReturn(okId);
        lenient().when(backendClient.strategyPageByType(
                nullable(Integer.class),
                nullable(Integer.class),
                nullable(String.class),
                nullable(String.class)
        )).thenReturn(okEmptyPage);
        lenient().when(backendClient.marketLookPage(
                nullable(Integer.class),
                nullable(Integer.class),
                nullable(String.class),
                nullable(String.class),
                nullable(String.class),
                nullable(String.class),
                nullable(String.class),
                nullable(String.class),
                nullable(String.class),
                nullable(String.class)
        )).thenReturn(okEmptyPage);
        lenient().when(backendClient.marketLookGetById(anyString())).thenReturn(okId);
        Map<String, Object> okDelete = new HashMap<>();
        okDelete.put("success", true);
        okDelete.put("verifiedAbsent", true);
        okDelete.put("id", "00000000-0000-0000-0000-000000000001");
        okDelete.put("message", "deleted");
        lenient().when(backendClient.marketLookDelete(anyString())).thenReturn(okDelete);
        lenient().when(backendClient.marketLookSql(anyMap())).thenReturn(okSql);

        Map<String, Object> okLookLogs = new HashMap<>();
        okLookLogs.put("success", true);
        okLookLogs.put("containerName", "aifuturetrade-model-look-1");
        okLookLogs.put("tail", 1000);
        okLookLogs.put("lineCount", 1);
        okLookLogs.put("lines", List.of("smoke test log line"));
        lenient().when(backendClient.lookContainerLogs(nullable(Integer.class))).thenReturn(okLookLogs);

        Map<String, Object> pricesOk = new HashMap<>();
        pricesOk.put("success", true);
        pricesOk.put("data", List.of(Map.of("symbol", "BTCUSDT", "price", 1.0)));
        lenient().when(binanceServiceClient.symbolPrices(anyList())).thenReturn(pricesOk);

        Map<String, Object> klinesOk = new HashMap<>();
        klinesOk.put("success", true);
        klinesOk.put("data", fakeKlines(120));
        lenient().when(binanceServiceClient.klines(
                anyString(), anyString(), nullable(Integer.class), nullable(Long.class), nullable(Long.class)))
                .thenReturn(klinesOk);
    }

    private static List<Map<String, Object>> fakeKlines(int n) {
        List<Map<String, Object>> list = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("open", 100.0 + i * 0.01);
            m.put("high", 101.0 + i * 0.01);
            m.put("low", 99.0 + i * 0.01);
            m.put("close", 100.5 + i * 0.01);
            m.put("volume", 1000.0);
            m.put("taker_buy_base_volume", 500.0);
            list.add(m);
        }
        return list;
    }

    private static void assertSuccessMap(Map<String, Object> r) {
        assertNotNull(r);
        assertTrue(r.containsKey("success"), "response should contain 'success': " + r);
    }

    @Test
    void trade_account_tools() {
        assertSuccessMap(accountTools.balance(MODEL_ID));
        assertSuccessMap(accountTools.positions(MODEL_ID));
        assertSuccessMap(accountTools.accountInfo(MODEL_ID));
    }

    @Test
    void trade_order_tools() {
        assertSuccessMap(orderTools.sellPosition(MODEL_ID, "BTCUSDT"));
        assertSuccessMap(orderTools.create(MODEL_ID, "BTCUSDT", "BUY", "MARKET", 0.001, null, null, null));
        assertSuccessMap(orderTools.cancel(MODEL_ID, "BTCUSDT", 1L, null));
        assertSuccessMap(orderTools.get(MODEL_ID, "BTCUSDT", 1L, null));
        assertSuccessMap(orderTools.openOrders(MODEL_ID, "BTCUSDT"));
        assertSuccessMap(orderTools.openOrders(MODEL_ID, null));
    }

    @Test
    void trade_market_tools() {
        assertSuccessMap(marketTools.symbolPrices(List.of("BTCUSDT")));
        assertSuccessMap(marketTools.klines("BTCUSDT", "1h", 120, null, null));
        assertSuccessMap(marketTools.klinesWithIndicators("BTCUSDT", "1h", 120, null, null));
    }

    @Test
    void trade_market_tickers_tools() {
        assertSuccessMap(marketTickersTools.rows(
                1, 5, null, null, null, null,
                null, null, null, null, null, null,
                "event_time", false));
        assertSuccessMap(marketTickersTools.rowsCount(
                null, null, null, null, null, null, null, null, null, null));
        assertSuccessMap(marketTickersTools.snapshot(1, 10, null, null));
        assertSuccessMap(marketTickersTools.snapshotCount(null, null));
        assertSuccessMap(marketTickersTools.allSymbols());
        assertSuccessMap(marketTickersTools.latest("BTCUSDT"));
        assertSuccessMap(marketTickersTools.sql(
                "SELECT * FROM `24_market_tickers` WHERE symbol=? LIMIT 1",
                List.of("BTCUSDT")));
    }

    @Test
    void trade_strategy_tools() {
        assertNotNull(strategyTools.strategyRegenerateCode(
                "00000000-0000-0000-0000-000000000099", null, null, null, false));
        assertNotNull(strategyTools.strategyApplySubmittedCode(
                "00000000-0000-0000-0000-000000000099", "print(1)", null, null));
        Map<String, Object> del = strategyTools.strategyDelete("00000000-0000-0000-0000-000000000099");
        assertNotNull(del);
        assertTrue(Boolean.TRUE.equals(del.get("success")), "strategyDelete: " + del);
    }

    @Test
    void trade_look_tools() {
        assertNotNull(marketLookTools.marketLookCreate("BTC", "sid", "摘要", null, null, null, null));
        assertNotNull(marketLookTools.strategyCreateLook("测试盯盘", null, null));
        assertNotNull(marketLookTools.strategyGetById("sid"));
        assertNotNull(marketLookTools.strategySearchLook(1, 10, null));
        assertNotNull(marketLookTools.marketLookQueryPage(1, 10, null, null, null, null, null, null, null, null));
        assertNotNull(marketLookTools.marketLookGetById("mid"));
        assertSuccessMap(marketLookTools.marketLookDelete("00000000-0000-0000-0000-000000000099"));
        assertSuccessMap(marketLookTools.marketLookSql(
                "SELECT id FROM `market_look` WHERE execution_status=? LIMIT 1",
                List.of("RUNNING")));
        assertNotNull(marketLookTools.lookContainerLogs(1000));
    }
}
