package com.aifuturetrade.service.mcp.impl;

import com.aifuturetrade.common.api.binance.BinanceConfig;
import com.aifuturetrade.common.api.binance.BinanceFuturesOrderClient;
import com.aifuturetrade.dao.entity.BinanceTradeLogDO;
import com.aifuturetrade.dao.entity.ModelDO;
import com.aifuturetrade.dao.entity.TradeDO;
import com.aifuturetrade.dao.mapper.BinanceTradeLogMapper;
import com.aifuturetrade.dao.mapper.ModelMapper;
import com.aifuturetrade.dao.mapper.TradeMapper;
import com.aifuturetrade.service.BinanceFuturesOrderService;
import com.aifuturetrade.service.mcp.McpBinanceFuturesOrderService;
import com.aifuturetrade.service.mcp.dto.McpOrderCancelRequest;
import com.aifuturetrade.service.mcp.dto.McpOrderCreateRequest;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Slf4j
@Service
public class McpBinanceFuturesOrderServiceImpl implements McpBinanceFuturesOrderService {

    @Autowired
    private ModelMapper modelMapper;

    @Autowired
    private TradeMapper tradeMapper;

    @Autowired
    private BinanceTradeLogMapper binanceTradeLogMapper;

    @Autowired
    private BinanceConfig binanceConfig;

    @Autowired
    private BinanceFuturesOrderService binanceFuturesOrderService; // 复用 sellPosition 既有逻辑

    private final ObjectMapper objectMapper = new ObjectMapper();

    private ModelDO requireModel(String modelId) {
        ModelDO model = modelMapper.selectById(modelId);
        if (model == null) {
            throw new IllegalArgumentException("未找到模型记录，modelId: " + modelId);
        }
        return model;
    }

    private boolean isTestMode(ModelDO model) {
        Boolean isVirtual = model.getIsVirtual();
        return isVirtual != null && isVirtual;
    }

    private BinanceFuturesOrderClient buildOrderClient(ModelDO model) {
        // real 模式必须有 model 密钥；test 模式允许使用默认密钥（用于查询行情/测试下单）
        boolean testMode = isTestMode(model);
        if (!testMode && (model.getApiKey() == null || model.getApiSecret() == null)) {
            throw new IllegalArgumentException("模型缺少API密钥信息，modelId: " + model.getId());
        }

        String apiKey = !testMode ? model.getApiKey() : (model.getApiKey() != null ? model.getApiKey() : binanceConfig.getApiKey());
        String apiSecret = !testMode ? model.getApiSecret() : (model.getApiSecret() != null ? model.getApiSecret() : binanceConfig.getSecretKey());

        if (apiKey == null || apiSecret == null) {
            throw new IllegalArgumentException("无法创建订单客户端：缺少API密钥配置");
        }

        return new BinanceFuturesOrderClient(
                apiKey,
                apiSecret,
                binanceConfig.getQuoteAsset(),
                binanceConfig.getBaseUrl(),
                binanceConfig.getTestnet(),
                binanceConfig.getConnectTimeout(),
                binanceConfig.getReadTimeout()
        );
    }

    private static String normalizeSideDirection(String side) {
        String s = side == null ? "" : side.trim().toUpperCase();
        if ("BUY".equals(s)) return "buy";
        if ("SELL".equals(s)) return "sell";
        return s.toLowerCase();
    }

    private static String normalizePositionSide(String positionSide) {
        if (positionSide == null) return null;
        String ps = positionSide.trim().toUpperCase();
        if (ps.isEmpty()) return null;
        return ps;
    }

    private static String deriveSignal(String side, String positionSide) {
        // trades.signal 语义：buy_to_long / buy_to_short / sell_to_long / sell_to_short
        String sd = side == null ? "" : side.trim().toUpperCase();
        String ps = positionSide == null ? "" : positionSide.trim().toUpperCase();
        if ("BUY".equals(sd) && "LONG".equals(ps)) return "buy_to_long";
        if ("BUY".equals(sd) && "SHORT".equals(ps)) return "buy_to_short";
        if ("SELL".equals(sd) && "LONG".equals(ps)) return "sell_to_long";
        if ("SELL".equals(sd) && "SHORT".equals(ps)) return "sell_to_short";
        // 降级：只用 buy/sell
        return normalizeSideDirection(sd);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> create(String modelId, McpOrderCreateRequest request) {
        ModelDO model = requireModel(modelId);
        boolean testMode = isTestMode(model);
        BinanceFuturesOrderClient client = buildOrderClient(model);

        String symbol = request.getSymbol();
        String side = request.getSide() != null ? request.getSide().trim().toUpperCase() : null;
        String type = request.getType() != null ? request.getType().trim().toUpperCase() : null;
        Double quantity = request.getQuantity();
        Double price = request.getPrice();
        Double stopPrice = request.getStopPrice();
        String positionSide = normalizePositionSide(request.getPositionSide());

        Map<String, Object> sdkResponse;
        String responseType = "200";
        String sdkError = null;

        Map<String, Object> paramForLog = new HashMap<>();
        paramForLog.put("symbol", symbol);
        paramForLog.put("side", side);
        paramForLog.put("type", type);
        paramForLog.put("quantity", quantity);
        paramForLog.put("price", price);
        paramForLog.put("stopPrice", stopPrice);
        paramForLog.put("positionSide", positionSide);
        paramForLog.put("testMode", testMode);

        try {
            // 只复用现有 client 暴露的方法（如需更多类型，后续可扩展）
            if ("MARKET".equals(type)) {
                sdkResponse = client.marketTrade(symbol, side, quantity, "MARKET", positionSide, testMode);
            } else if ("LIMIT".equals(type)) {
                sdkResponse = client.limitTrade(symbol, side, quantity, price, positionSide, testMode);
            } else if ("STOP".equals(type) || "STOP_MARKET".equals(type)) {
                sdkResponse = client.stopLossTrade(symbol, side, quantity, type, price, stopPrice, positionSide, testMode);
            } else if ("TAKE_PROFIT".equals(type) || "TAKE_PROFIT_MARKET".equals(type)) {
                sdkResponse = client.takeProfitTrade(symbol, side, quantity, type, price, stopPrice, positionSide, testMode);
            } else {
                throw new IllegalArgumentException("不支持的订单类型: " + type);
            }
        } catch (Exception e) {
            sdkError = e.getMessage();
            responseType = "500";
            log.error("[McpOrder] create failed: modelId={}, symbol={}, type={}, error={}", modelId, symbol, type, sdkError, e);
            sdkResponse = null;
        }

        // 写入 trades（满足“写入要落库”的约束；portfolio 更新由既有系统负责）
        TradeDO trade = new TradeDO();
        trade.setModelId(modelId);
        trade.setFuture(symbol);
        trade.setSignal(deriveSignal(side, positionSide));
        trade.setSide(normalizeSideDirection(side));
        trade.setPositionSide(positionSide);
        trade.setQuantity(quantity);
        trade.setPrice(price != null ? price : 0.0);
        trade.setPnl(0.0);
        trade.setFee(0.0);
        trade.setInitialMargin(0.0);
        trade.setTimestamp(LocalDateTime.now(ZoneOffset.ofHours(8)));

        if (sdkResponse != null) {
            Object orderIdObj = sdkResponse.get("orderId");
            if (orderIdObj != null) {
                try {
                    trade.setOrderId(Long.parseLong(orderIdObj.toString()));
                } catch (Exception ignore) {
                    // ignore
                }
            }
            Object typeObj = sdkResponse.get("type");
            if (typeObj != null) trade.setType(typeObj.toString());
            Object origTypeObj = sdkResponse.get("origType");
            if (origTypeObj != null) trade.setOrigType(origTypeObj.toString());
        } else {
            trade.setError(sdkError);
        }
        tradeMapper.insert(trade);

        // 写入 binance_trade_logs
        BinanceTradeLogDO tradeLog = new BinanceTradeLogDO();
        tradeLog.setModelId(modelId);
        tradeLog.setTradeId(trade.getId());
        tradeLog.setType(testMode ? "test" : "real");
        tradeLog.setMethodName("mcp_order_create");
        tradeLog.setCreatedAt(LocalDateTime.now());
        try {
            tradeLog.setParam(objectMapper.writeValueAsString(paramForLog));
            if (sdkResponse != null) {
                tradeLog.setResponseContext(objectMapper.writeValueAsString(sdkResponse));
            }
            tradeLog.setResponseType(responseType);
            if (sdkError != null) {
                tradeLog.setErrorContext(sdkError);
            }
        } catch (Exception e) {
            // ignore
        }
        binanceTradeLogMapper.insert(tradeLog);

        Map<String, Object> result = new HashMap<>();
        result.put("success", sdkError == null);
        result.put("tradeId", trade.getId());
        result.put("data", sdkResponse);
        if (sdkError != null) {
            result.put("error", sdkError);
        }
        return result;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> cancel(String modelId, McpOrderCancelRequest request) {
        ModelDO model = requireModel(modelId);
        boolean testMode = isTestMode(model);
        BinanceFuturesOrderClient client = buildOrderClient(model);

        Map<String, Object> paramForLog = new HashMap<>();
        paramForLog.put("symbol", request.getSymbol());
        paramForLog.put("orderId", request.getOrderId());
        paramForLog.put("origClientOrderId", request.getOrigClientOrderId());
        paramForLog.put("testMode", testMode);

        Map<String, Object> sdkResponse = null;
        String sdkError = null;
        String responseType = "200";

        try {
            if (request.getOrderId() == null
                    && (request.getOrigClientOrderId() == null || request.getOrigClientOrderId().isBlank())) {
                throw new IllegalArgumentException("orderId 与 origClientOrderId 至少填一个");
            }
            sdkResponse = client.cancelOrder(request.getSymbol(), request.getOrderId(), request.getOrigClientOrderId(), null);
        } catch (Exception e) {
            sdkError = e.getMessage();
            responseType = "500";
            log.error("[McpOrder] cancel failed: modelId={}, error={}", modelId, sdkError, e);
        }

        BinanceTradeLogDO tradeLog = new BinanceTradeLogDO();
        tradeLog.setModelId(modelId);
        tradeLog.setType(testMode ? "test" : "real");
        tradeLog.setMethodName("mcp_order_cancel");
        tradeLog.setCreatedAt(LocalDateTime.now());
        try {
            tradeLog.setParam(objectMapper.writeValueAsString(paramForLog));
            if (sdkResponse != null) {
                tradeLog.setResponseContext(objectMapper.writeValueAsString(sdkResponse));
            }
            tradeLog.setResponseType(responseType);
            if (sdkError != null) {
                tradeLog.setErrorContext(sdkError);
            }
        } catch (Exception ignored) {
            // ignore
        }
        binanceTradeLogMapper.insert(tradeLog);

        Map<String, Object> result = new HashMap<>();
        result.put("success", sdkError == null);
        result.put("data", sdkResponse);
        if (sdkError != null) {
            result.put("error", sdkError);
        }
        return result;
    }

    @Override
    public Map<String, Object> get(String modelId, String symbol, Long orderId, String origClientOrderId) {
        ModelDO model = requireModel(modelId);
        BinanceFuturesOrderClient client = buildOrderClient(model);
        Map<String, Object> result = new HashMap<>();
        try {
            if (symbol == null || symbol.isBlank()) {
                throw new IllegalArgumentException("symbol 不能为空");
            }
            if (orderId == null && (origClientOrderId == null || origClientOrderId.isBlank())) {
                throw new IllegalArgumentException("orderId 与 origClientOrderId 至少填一个");
            }
            Map<String, Object> data = client.queryOrder(symbol, orderId, origClientOrderId, null);
            result.put("success", true);
            result.put("data", data);
        } catch (Exception e) {
            result.put("success", false);
            result.put("error", e.getMessage());
        }
        return result;
    }

    @Override
    public List<Map<String, Object>> openOrders(String modelId, String symbol) {
        ModelDO model = requireModel(modelId);
        BinanceFuturesOrderClient client = buildOrderClient(model);
        String sym = (symbol != null && !symbol.isBlank()) ? symbol : null;
        return client.currentAllOpenOrders(sym, null);
    }

    @Override
    public Map<String, Object> sellPosition(String modelId, String symbol) {
        return binanceFuturesOrderService.sellPosition(modelId, symbol);
    }
}

