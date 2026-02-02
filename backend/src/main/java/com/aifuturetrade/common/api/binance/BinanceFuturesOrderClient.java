package com.aifuturetrade.common.api.binance;

import com.binance.connector.client.common.ApiResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.ChangeInitialLeverageRequest;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.ChangeInitialLeverageResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.NewOrderRequest;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.NewOrderResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.TestOrderRequest;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.TestOrderResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.Side;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.PositionSide;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.TimeInForce;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.SymbolOrderBookTickerResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.SymbolOrderBookTickerResponse1;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.SymbolOrderBookTickerResponse2;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.SymbolOrderBookTickerResponse2Inner;
import lombok.extern.slf4j.Slf4j;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 币安期货订单客户端 - 专注于交易功能的客户端
 * 
 * 提供止损交易、止盈交易、跟踪止损单和平仓交易等高级交易功能，
 * 支持传入不同的api_key和api_secret进行操作。
 * 
 * 【持仓方向说明】
 * positionSide 持仓方向：
 * - 单向持仓模式下：非必填，默认且仅可填BOTH
 * - 双向持仓模式下：必填，且仅可选择 LONG(多) 或 SHORT（空）
 * 
 * 参考 Binance 官方示例：
 * https://github.com/binance/binance-connector-java/tree/master/clients/derivatives-trading-usds-futures
 */
@Slf4j
public class BinanceFuturesOrderClient extends BinanceFuturesBase {
    
    /**
     * 构造函数，初始化币安期货订单客户端
     * 
     * @param apiKey 币安API密钥
     * @param apiSecret 币安API密钥
     * @param quoteAsset 计价资产，默认为USDT
     * @param baseUrl 自定义REST API基础路径（可选）
     * @param testnet 是否使用测试网络，默认False
     * @param connectTimeout 连接超时时间（毫秒），默认10000ms
     * @param readTimeout 读取超时时间（毫秒），默认50000ms
     */
    public BinanceFuturesOrderClient(String apiKey, String apiSecret, String quoteAsset, 
                                    String baseUrl, Boolean testnet,
                                    Integer connectTimeout, Integer readTimeout) {
        this.quoteAsset = (quoteAsset != null ? quoteAsset : "USDT").toUpperCase();
        initRestApi(apiKey, apiSecret, null, null, baseUrl, connectTimeout, readTimeout);
    }
    
    /**
     * 构造函数，使用默认配置
     */
    public BinanceFuturesOrderClient(String apiKey, String apiSecret) {
        this(apiKey, apiSecret, "USDT", null, false, null, null);
    }
    
    /**
     * 获取最优挂单价格（Order Book Ticker）
     * 
     * 参考 API: GET /fapi/v1/ticker/bookTicker
     * 
     * @param symbol 交易对符号，如 'BTC' 或 'BTCUSDT'（可选）。
     *               如果不提供，则返回所有交易对的最优挂单价格。
     * @return 最优挂单价格信息列表
     */
    public List<Map<String, Object>> getOrderBookTicker(String symbol) {
        try {
            String formattedSymbol = null;
            if (symbol != null && !symbol.isEmpty()) {
                formattedSymbol = formatSymbol(symbol);
                log.info("[Binance Futures] 获取最优挂单价格，交易对: {}", formattedSymbol);
            } else {
                log.info("[Binance Futures] 获取所有交易对的最优挂单价格");
            }
            
            // 调用REST API接口
            ApiResponse<SymbolOrderBookTickerResponse> response = restApi.symbolOrderBookTicker(formattedSymbol);
            
            // 直接使用SDK的getData()方法获取响应数据
            SymbolOrderBookTickerResponse responseData = response.getData();
            if (responseData == null) {
                log.warn("[Binance Futures] 无返回数据");
                return new ArrayList<>();
            }
            
            // SymbolOrderBookTickerResponse是oneOf类型，需要使用getActualInstance()获取实际实例
            Object actualInstance = responseData.getActualInstance();
            if (actualInstance == null) {
                log.warn("[Binance Futures] 响应数据实例为null");
                return new ArrayList<>();
            }
            
            // 处理响应数据
            List<Map<String, Object>> tickers = new ArrayList<>();
            
            if (actualInstance instanceof SymbolOrderBookTickerResponse1) {
                // Response1是单个对象
                SymbolOrderBookTickerResponse1 ticker = (SymbolOrderBookTickerResponse1) actualInstance;
                Map<String, Object> tickerMap = new HashMap<>();
                tickerMap.put("symbol", ticker.getSymbol());
                tickerMap.put("bidPrice", ticker.getBidPrice());
                tickerMap.put("bidQty", ticker.getBidQty());
                tickerMap.put("askPrice", ticker.getAskPrice());
                tickerMap.put("askQty", ticker.getAskQty());
                tickerMap.put("time", ticker.getTime());
                tickers.add(tickerMap);
            } else if (actualInstance instanceof SymbolOrderBookTickerResponse2) {
                // Response2继承自ArrayList，可以直接当作List使用
                SymbolOrderBookTickerResponse2 tickerList = (SymbolOrderBookTickerResponse2) actualInstance;
                for (SymbolOrderBookTickerResponse2Inner ticker : tickerList) {
                    Map<String, Object> tickerMap = new HashMap<>();
                    tickerMap.put("symbol", ticker.getSymbol());
                    tickerMap.put("bidPrice", ticker.getBidPrice());
                    tickerMap.put("bidQty", ticker.getBidQty());
                    tickerMap.put("askPrice", ticker.getAskPrice());
                    tickerMap.put("askQty", ticker.getAskQty());
                    tickerMap.put("time", ticker.getTime());
                    tickers.add(tickerMap);
                }
            }
            
            log.info("[Binance Futures] 成功获取最优挂单价格，返回 {} 条数据", tickers.size());
            return tickers;
            
        } catch (Exception e) {
            log.error("[Binance Futures] 获取最优挂单价格失败: {}", e.getMessage(), e);
            throw new RuntimeException("获取最优挂单价格失败: " + e.getMessage(), e);
        }
    }
    
    /**
     * 修改初始杠杆倍数
     * 
     * 参考 API: POST /fapi/v1/leverage
     * 
     * @param symbol 交易对符号，如 'BTC' 或 'BTCUSDT'
     * @param leverage 新的杠杆倍数（1-125）
     * @return 修改后的杠杆信息
     */
    public Map<String, Object> changeInitialLeverage(String symbol, Integer leverage) {
        try {
            // 验证参数
            if (symbol == null || symbol.isEmpty()) {
                throw new IllegalArgumentException("交易对不能为空");
            }
            
            if (leverage == null || leverage < 1 || leverage > 125) {
                throw new IllegalArgumentException("杠杆倍数必须是1-125之间的整数");
            }
            
            // 格式化交易对
            String formattedSymbol = formatSymbol(symbol);
            log.info("[Binance Futures] 修改初始杠杆，交易对: {}，杠杆倍数: {}", formattedSymbol, leverage);
            
            // 调用REST API接口 - 构建Request对象
            ChangeInitialLeverageRequest request = new ChangeInitialLeverageRequest();
            request.setSymbol(formattedSymbol);
            request.setLeverage(leverage.longValue()); // 转换为Long类型
            ApiResponse<ChangeInitialLeverageResponse> response = restApi.changeInitialLeverage(request);
            
            // 直接使用SDK的getData()方法获取响应数据
            ChangeInitialLeverageResponse responseData = response.getData();
            if (responseData == null) {
                throw new RuntimeException("API调用返回null，请检查API调用方式");
            }
            
            // 直接使用SDK对象的getter方法
            Map<String, Object> data = new HashMap<>();
            data.put("leverage", responseData.getLeverage());
            data.put("maxNotionalValue", responseData.getMaxNotionalValue());
            data.put("symbol", responseData.getSymbol());
            
            log.info("[Binance Futures] 成功修改初始杠杆，交易对: {}，新杠杆: {}", 
                    formattedSymbol, data.get("leverage"));
            return data;
            
        } catch (IllegalArgumentException e) {
            log.error("[Binance Futures] 修改初始杠杆参数错误: {}", e.getMessage());
            throw e;
        } catch (Exception e) {
            log.error("[Binance Futures] 修改初始杠杆失败: {}", e.getMessage(), e);
            throw new RuntimeException("修改初始杠杆失败: " + e.getMessage(), e);
        }
    }
    
    /**
     * 验证订单数量必须大于0
     */
    private void validateQuantity(Double quantity) {
        if (quantity == null || quantity <= 0) {
            throw new IllegalArgumentException("quantity参数必须大于0，当前值: " + quantity);
        }
    }
    
    /**
     * 验证并规范化position_side参数
     */
    private String validatePositionSide(String positionSide) {
        if (positionSide != null && !positionSide.isEmpty()) {
            String positionSideUpper = positionSide.toUpperCase();
            if (!"LONG".equals(positionSideUpper) && !"SHORT".equals(positionSideUpper)) {
                throw new IllegalArgumentException(
                        "position_side参数值必须是'LONG'或'SHORT'，当前值: " + positionSide);
            }
            return positionSideUpper;
        }
        return null;
    }
    
    /**
     * 验证条件订单参数（止损/止盈订单）
     */
    private void validateConditionalOrderParams(String orderType, Double price, 
                                                Double stopPrice, boolean requirePrice) {
        String orderTypeUpper = orderType.toUpperCase();
        if ("STOP".equals(orderTypeUpper) || "TAKE_PROFIT".equals(orderTypeUpper)) {
            if (requirePrice && price == null) {
                throw new IllegalArgumentException(orderTypeUpper + "订单必须提供price参数");
            }
            if (stopPrice == null) {
                throw new IllegalArgumentException(orderTypeUpper + "订单必须提供stop_price参数");
            }
        } else if ("STOP_MARKET".equals(orderTypeUpper) || "TAKE_PROFIT_MARKET".equals(orderTypeUpper)) {
            if (stopPrice == null) {
                throw new IllegalArgumentException(orderTypeUpper + "订单必须提供stop_price参数");
            }
        } else {
            throw new IllegalArgumentException("不支持的订单类型: " + orderType);
        }
    }
    
    /**
     * 构建订单参数字典
     */
    private Map<String, Object> buildOrderParams(String formattedSymbol, String side, String orderType,
                                                 Double quantity, Double price, Double stopPrice,
                                                 String positionSide, Boolean closePosition) {
        Map<String, Object> orderParams = new HashMap<>();
        orderParams.put("symbol", formattedSymbol);
        
        // 转换side参数为大写字符串
        orderParams.put("side", side.toUpperCase());
        
        orderParams.put("type", orderType.toUpperCase());
        
        if (quantity != null) {
            orderParams.put("quantity", quantity);
        }
        
        if (closePosition != null && closePosition) {
            orderParams.put("closePosition", true);
        }
        
        if (positionSide != null) {
            orderParams.put("positionSide", positionSide);
        }
        
        if (stopPrice != null) {
            orderParams.put("stopPrice", stopPrice);
        }
        
        if (price != null) {
            orderParams.put("price", price);
            orderParams.put("timeInForce", "GTC");
        }
        
        return orderParams;
    }
    
    /**
     * 执行订单（统一方法，支持测试模式和真实交易）
     */
    private Map<String, Object> executeOrder(Map<String, Object> orderParams, boolean testMode) {
        try {
            ApiResponse<?> response; // 可能是NewOrderResponse或TestOrderResponse，使用通配符因为两种类型都可能
            
            if (testMode) {
                // 使用测试接口
                log.info("[Binance Futures] 使用测试接口下单（不会真实成交）");
                
                // 构建测试参数
                Map<String, Object> testParams = new HashMap<>();
                testParams.put("symbol", orderParams.get("symbol"));
                
                // 转换side参数
                Object sideObj = orderParams.get("side");
                String sideStr = String.valueOf(sideObj).toUpperCase();
                testParams.put("side", sideStr);
                
                testParams.put("type", "MARKET"); // 测试订单统一使用MARKET类型
                
                if (orderParams.containsKey("quantity")) {
                    testParams.put("quantity", orderParams.get("quantity"));
                } else {
                    testParams.put("quantity", 100); // 默认数量
                }
                
                if (orderParams.containsKey("positionSide")) {
                    testParams.put("positionSide", orderParams.get("positionSide"));
                }
                
                // 调用测试订单接口 - 构建Request对象
                TestOrderRequest testRequest = new TestOrderRequest();
                testRequest.setSymbol((String) testParams.get("symbol"));
                // 直接使用SDK枚举类设置side
                Object testSideObj = testParams.get("side");
                if (testSideObj != null) {
                    testRequest.setSide(Side.fromValue(String.valueOf(testSideObj).toUpperCase()));
                }
                testRequest.setType((String) testParams.get("type"));
                if (testParams.get("quantity") != null) {
                    testRequest.setQuantity(((Number) testParams.get("quantity")).doubleValue());
                }
                if (testParams.get("positionSide") != null) {
                    String positionSideStr = (String) testParams.get("positionSide");
                    testRequest.setPositionSide(PositionSide.fromValue(positionSideStr.toUpperCase()));
                }
                response = restApi.testOrder(testRequest);
                
                log.info("[Binance Futures] 测试接口调用成功（未真实下单）");
            } else {
                // 使用真实交易接口
                log.info("[Binance Futures] 使用真实交易接口下单");
                
                // 调用真实订单接口 - 构建Request对象
                NewOrderRequest newOrderRequest = new NewOrderRequest();
                newOrderRequest.setSymbol((String) orderParams.get("symbol"));
                // 直接使用SDK枚举类设置字段
                String sideStr = String.valueOf(orderParams.get("side"));
                newOrderRequest.setSide(Side.fromValue(sideStr.toUpperCase()));
                newOrderRequest.setType((String) orderParams.get("type"));
                if (orderParams.get("quantity") != null) {
                    newOrderRequest.setQuantity(((Number) orderParams.get("quantity")).doubleValue());
                }
                if (orderParams.get("price") != null) {
                    newOrderRequest.setPrice(((Number) orderParams.get("price")).doubleValue());
                }
                if (orderParams.get("stopPrice") != null) {
                    newOrderRequest.setStopPrice(((Number) orderParams.get("stopPrice")).doubleValue());
                }
                if (orderParams.get("positionSide") != null) {
                    String positionSideStr = String.valueOf(orderParams.get("positionSide"));
                    newOrderRequest.setPositionSide(PositionSide.fromValue(positionSideStr.toUpperCase()));
                }
                if (orderParams.get("closePosition") != null) {
                    // closePosition是String类型，不是Boolean
                    Boolean closePos = (Boolean) orderParams.get("closePosition");
                    newOrderRequest.setClosePosition(closePos ? "true" : "false");
                }
                if (orderParams.get("timeInForce") != null) {
                    String timeInForceStr = String.valueOf(orderParams.get("timeInForce"));
                    newOrderRequest.setTimeInForce(TimeInForce.fromValue(timeInForceStr.toUpperCase()));
                }
                response = restApi.newOrder(newOrderRequest);
            }
            
            // 处理响应
            if (response == null) {
                throw new RuntimeException("API调用返回null，请检查API调用方式");
            }
            
            // 根据testMode判断响应类型
            Map<String, Object> responseDict = new HashMap<>();
            @SuppressWarnings("unchecked")
            ApiResponse<TestOrderResponse> testResponse = (ApiResponse<TestOrderResponse>) response;
            @SuppressWarnings("unchecked")
            ApiResponse<NewOrderResponse> newResponse = (ApiResponse<NewOrderResponse>) response;
            
            if (testMode) {
                // 测试订单返回TestOrderResponse
                TestOrderResponse testData = testResponse.getData();
                if (testData != null) {
                    responseDict.put("clientOrderId", testData.getClientOrderId());
                    responseDict.put("cumQty", testData.getCumQty());
                    responseDict.put("cumQuote", testData.getCumQuote());
                    responseDict.put("executedQty", testData.getExecutedQty());
                    responseDict.put("orderId", testData.getOrderId());
                    responseDict.put("avgPrice", testData.getAvgPrice());
                    responseDict.put("origQty", testData.getOrigQty());
                    responseDict.put("price", testData.getPrice());
                    responseDict.put("reduceOnly", testData.getReduceOnly());
                    responseDict.put("side", testData.getSide());
                    responseDict.put("positionSide", testData.getPositionSide());
                    responseDict.put("status", testData.getStatus());
                    responseDict.put("stopPrice", testData.getStopPrice());
                    responseDict.put("closePosition", testData.getClosePosition());
                    responseDict.put("symbol", testData.getSymbol());
                    responseDict.put("timeInForce", testData.getTimeInForce());
                    responseDict.put("type", testData.getType());
                    responseDict.put("origType", testData.getOrigType());
                    responseDict.put("activatePrice", testData.getActivatePrice());
                    responseDict.put("priceRate", testData.getPriceRate());
                    responseDict.put("updateTime", testData.getUpdateTime());
                    responseDict.put("workingType", testData.getWorkingType());
                    responseDict.put("priceProtect", testData.getPriceProtect());
                }
            } else {
                // 真实订单返回NewOrderResponse
                NewOrderResponse newData = newResponse.getData();
                if (newData != null) {
                    responseDict.put("clientOrderId", newData.getClientOrderId());
                    responseDict.put("cumQty", newData.getCumQty());
                    responseDict.put("cumQuote", newData.getCumQuote());
                    responseDict.put("executedQty", newData.getExecutedQty());
                    responseDict.put("orderId", newData.getOrderId());
                    responseDict.put("avgPrice", newData.getAvgPrice());
                    responseDict.put("origQty", newData.getOrigQty());
                    responseDict.put("price", newData.getPrice());
                    responseDict.put("reduceOnly", newData.getReduceOnly());
                    responseDict.put("side", newData.getSide());
                    responseDict.put("positionSide", newData.getPositionSide());
                    responseDict.put("status", newData.getStatus());
                    responseDict.put("stopPrice", newData.getStopPrice());
                    responseDict.put("closePosition", newData.getClosePosition());
                    responseDict.put("symbol", newData.getSymbol());
                    responseDict.put("timeInForce", newData.getTimeInForce());
                    responseDict.put("type", newData.getType());
                    responseDict.put("origType", newData.getOrigType());
                    responseDict.put("activatePrice", newData.getActivatePrice());
                    responseDict.put("priceRate", newData.getPriceRate());
                    responseDict.put("updateTime", newData.getUpdateTime());
                    responseDict.put("workingType", newData.getWorkingType());
                    responseDict.put("priceProtect", newData.getPriceProtect());
                }
            }
            
            log.info("[Binance Futures] 订单执行成功: {}", responseDict);
            
            return responseDict;
            
        } catch (Exception e) {
            log.error("[Binance Futures] 订单执行失败: {}", e.getMessage(), e);
            throw new RuntimeException("订单执行失败: " + e.getMessage(), e);
        }
    }
    
    /**
     * 市场价格交易 - 使用指定订单类型
     * 
     * 参考 API: POST /fapi/v1/order
     * 
     * @param symbol 交易对符号，如 'BTCUSDT'
     * @param side 交易方向，'BUY'或'SELL'
     * @param quantity 订单数量（必填，必须大于0）
     * @param orderType 订单类型，默认"MARKET"
     * @param positionSide 持仓方向，'LONG'（多）或'SHORT'（空），双向持仓模式下必填
     * @param testMode 是否使用测试模式
     * @return 订单响应数据
     */
    public Map<String, Object> marketTrade(String symbol, String side, Double quantity, 
                                           String orderType, String positionSide, boolean testMode) {
        validateQuantity(quantity);
        
        log.info("[Binance Futures] 开始市场交易，交易对: {}, 方向: {}, 数量: {}, 订单类型: {}, 持仓方向: {}", 
                symbol, side, quantity, orderType, positionSide);
        
        try {
            String formattedSymbol = formatSymbol(symbol);
            String validatedPositionSide = validatePositionSide(positionSide);
            
            Map<String, Object> orderParams = buildOrderParams(
                    formattedSymbol, side, orderType != null ? orderType : "MARKET", 
                    quantity, null, null, validatedPositionSide, false);
            
            return executeOrder(orderParams, testMode);
        } catch (Exception exc) {
            log.error("[Binance Futures] 市场交易失败: {}", exc.getMessage(), exc);
            throw exc;
        }
    }
    
    /**
     * 止损交易 - 使用STOP或STOP_MARKET订单类型
     * 
     * 参考 API: POST /fapi/v1/order
     * 
     * @param symbol 交易对符号，如 'BTCUSDT'
     * @param side 交易方向，'BUY'或'SELL'
     * @param quantity 订单数量（必填，必须大于0）
     * @param orderType 订单类型，'STOP_MARKET'或'STOP'（默认）
     * @param price 订单价格（STOP订单必填，STOP_MARKET订单不需要）
     * @param stopPrice 止损触发价格（STOP和STOP_MARKET订单均必填）
     * @param positionSide 持仓方向，'LONG'（多）或'SHORT'（空），双向持仓模式下必填
     * @param testMode 是否使用测试模式
     * @return 订单响应数据
     */
    public Map<String, Object> stopLossTrade(String symbol, String side, Double quantity, 
                                            String orderType, Double price, Double stopPrice,
                                            String positionSide, boolean testMode) {
        validateQuantity(quantity);
        String orderTypeUpper = (orderType != null ? orderType : "STOP").toUpperCase();
        validateConditionalOrderParams(orderTypeUpper, price, stopPrice, 
                "STOP".equals(orderTypeUpper));
        
        log.info("[Binance Futures] 开始止损交易，交易对: {}, 方向: {}, 类型: {}, 持仓方向: {}", 
                symbol, side, orderTypeUpper, positionSide);
        
        try {
            String formattedSymbol = formatSymbol(symbol);
            String validatedPositionSide = validatePositionSide(positionSide);
            
            Map<String, Object> orderParams = buildOrderParams(
                    formattedSymbol, side, orderTypeUpper, quantity, price, stopPrice,
                    validatedPositionSide, false);
            
            return executeOrder(orderParams, testMode);
        } catch (Exception exc) {
            log.error("[Binance Futures] 止损交易失败: {}", exc.getMessage(), exc);
            throw exc;
        }
    }
    
    /**
     * 止盈交易 - 使用TAKE_PROFIT或TAKE_PROFIT_MARKET订单类型
     * 
     * 参考 API: POST /fapi/v1/order
     * 
     * @param symbol 交易对符号，如 'BTCUSDT'
     * @param side 交易方向，'BUY'或'SELL'
     * @param quantity 订单数量（必填）
     * @param orderType 订单类型，'TAKE_PROFIT_MARKET'或'TAKE_PROFIT'（默认）
     * @param price 订单价格（TAKE_PROFIT订单必填，TAKE_PROFIT_MARKET订单不需要）
     * @param stopPrice 止盈触发价格（TAKE_PROFIT和TAKE_PROFIT_MARKET订单均必填）
     * @param positionSide 持仓方向，'LONG'（多）或'SHORT'（空），双向持仓模式下必填
     * @param testMode 是否使用测试模式
     * @return 订单响应数据
     */
    public Map<String, Object> takeProfitTrade(String symbol, String side, Double quantity, 
                                               String orderType, Double price, Double stopPrice,
                                               String positionSide, boolean testMode) {
        validateQuantity(quantity);
        String orderTypeUpper = (orderType != null ? orderType : "TAKE_PROFIT").toUpperCase();
        validateConditionalOrderParams(orderTypeUpper, price, stopPrice, 
                "TAKE_PROFIT".equals(orderTypeUpper));
        
        log.info("[Binance Futures] 开始止盈交易，交易对: {}, 方向: {}, 类型: {}, 持仓方向: {}", 
                symbol, side, orderTypeUpper, positionSide);
        
        try {
            String formattedSymbol = formatSymbol(symbol);
            String validatedPositionSide = validatePositionSide(positionSide);
            
            Map<String, Object> orderParams = buildOrderParams(
                    formattedSymbol, side, orderTypeUpper, quantity, price, stopPrice,
                    validatedPositionSide, false);
            
            return executeOrder(orderParams, testMode);
        } catch (Exception exc) {
            log.error("[Binance Futures] 止盈交易失败: {}", exc.getMessage(), exc);
            throw exc;
        }
    }
    
    /**
     * 平仓交易 - 使用STOP_MARKET或TAKE_PROFIT_MARKET订单类型配合closePosition=true
     * 
     * 参考 API: POST /fapi/v1/order
     * 
     * @param symbol 交易对符号，如 'BTCUSDT'
     * @param side 交易方向，'BUY'或'SELL'
     * @param quantity 订单数量（必填）
     * @param orderType 订单类型，'STOP_MARKET'(默认)或'TAKE_PROFIT_MARKET'
     * @param stopPrice 触发价格（可选，取决于order_type）
     * @param positionSide 持仓方向，'LONG'（多）或'SHORT'（空），双向持仓模式下必填
     * @param testMode 是否使用测试模式
     * @return 订单响应数据
     */
    public Map<String, Object> closePositionTrade(String symbol, String side, Double quantity, 
                                                  String orderType, Double stopPrice,
                                                  String positionSide, boolean testMode) {
        validateQuantity(quantity);
        
        log.info("[Binance Futures] 开始平仓交易，交易对: {}, 方向: {}, 类型: {}, 持仓方向: {}", 
                symbol, side, orderType, positionSide);
        
        try {
            String formattedSymbol = formatSymbol(symbol);
            String validatedPositionSide = validatePositionSide(positionSide);
            
            // 【双开模式校验】验证side和position_side的组合是否合法
            if (validatedPositionSide != null) {
                String sideUpper = side.toUpperCase();
                if ("LONG".equals(validatedPositionSide) && "BUY".equals(sideUpper)) {
                    throw new IllegalArgumentException(
                            "双开模式下，LONG方向上不支持BUY操作。平多仓应使用SELL，当前side=" + side + 
                            ", position_side=" + validatedPositionSide);
                }
                if ("SHORT".equals(validatedPositionSide) && "SELL".equals(sideUpper)) {
                    throw new IllegalArgumentException(
                            "双开模式下，SHORT方向上不支持SELL操作。平空仓应使用BUY，当前side=" + side + 
                            ", position_side=" + validatedPositionSide);
                }
            }
            
            String orderTypeUpper = (orderType != null ? orderType : "STOP_MARKET").toUpperCase();
            
            Map<String, Object> orderParams = buildOrderParams(
                    formattedSymbol, side, orderTypeUpper, quantity, null, stopPrice,
                    validatedPositionSide, true);
            
            return executeOrder(orderParams, testMode);
        } catch (Exception exc) {
            log.error("[Binance Futures] 平仓交易失败: {}", exc.getMessage(), exc);
            throw exc;
        }
    }
    
    /**
     * 查询所有条件单
     * 
     * 参考 API: GET /fapi/v1/algo/orders
     * 参考示例: QueryAllAlgoOrdersExample.java
     * 
     * @param symbol 交易对符号（必填）
     * @param algoId 算法订单ID（可选）
     * @param startTime 开始时间（可选，时间戳）
     * @param endTime 结束时间（可选，时间戳）
     * @param page 页码（可选，默认0）
     * @param limit 每页数量（可选，默认100，最大1000）
     * @param recvWindow 接收窗口（可选，默认5000）
     * @return 条件单列表
     */
    public List<Map<String, Object>> queryAllAlgoOrders(String symbol, Long algoId, 
                                                       Long startTime, Long endTime,
                                                       Long page, Long limit, Long recvWindow) {
        try {
            String formattedSymbol = formatSymbol(symbol);
            log.info("[Binance Futures] 查询所有条件单，交易对: {}", formattedSymbol);
            
            // 调用REST API接口
            com.binance.connector.client.common.ApiResponse<
                com.binance.connector.client.derivatives_trading_usds_futures.rest.model.QueryAllAlgoOrdersResponse> response = 
                restApi.queryAllAlgoOrders(formattedSymbol, algoId, startTime, endTime, page, limit, recvWindow);
            
            // 处理响应
            com.binance.connector.client.derivatives_trading_usds_futures.rest.model.QueryAllAlgoOrdersResponse responseData = response.getData();
            if (responseData == null || responseData.isEmpty()) {
                log.info("[Binance Futures] 查询条件单无返回数据");
                return new ArrayList<>();
            }
            
            // QueryAllAlgoOrdersResponse是ArrayList<QueryAllAlgoOrdersResponseInner>
            // 转换为Map列表
            List<Map<String, Object>> result = new ArrayList<>();
            for (com.binance.connector.client.derivatives_trading_usds_futures.rest.model.QueryAllAlgoOrdersResponseInner order : responseData) {
                Map<String, Object> orderMap = new HashMap<>();
                orderMap.put("algoId", order.getAlgoId());
                orderMap.put("clientAlgoId", order.getClientAlgoId());
                orderMap.put("algoType", order.getAlgoType());
                orderMap.put("orderType", order.getOrderType());
                orderMap.put("symbol", order.getSymbol());
                orderMap.put("side", order.getSide());
                orderMap.put("positionSide", order.getPositionSide());
                orderMap.put("quantity", order.getQuantity());
                orderMap.put("algoStatus", order.getAlgoStatus());
                orderMap.put("triggerPrice", order.getTriggerPrice());
                orderMap.put("price", order.getPrice());
                result.add(orderMap);
            }
            
            log.info("[Binance Futures] 查询所有条件单成功，找到 {} 个条件单", result.size());
            
            return result;
        } catch (Exception exc) {
            log.error("[Binance Futures] 查询所有条件单失败: {}", exc.getMessage(), exc);
            throw new RuntimeException("查询条件单失败: " + exc.getMessage(), exc);
        }
    }
    
    /**
     * 取消所有条件单
     * 
     * 参考 API: DELETE /fapi/v1/algo/allOpenOrders
     * 参考示例: CancelAllAlgoOpenOrdersExample.java
     * 
     * @param symbol 交易对符号（必填）
     * @param recvWindow 接收窗口（可选，默认5000）
     * @return 取消结果
     */
    public Map<String, Object> cancelAllAlgoOpenOrders(String symbol, Long recvWindow) {
        try {
            String formattedSymbol = formatSymbol(symbol);
            log.info("[Binance Futures] 取消所有条件单，交易对: {}", formattedSymbol);
            
            // 调用REST API接口
            com.binance.connector.client.common.ApiResponse<
                com.binance.connector.client.derivatives_trading_usds_futures.rest.model.CancelAllAlgoOpenOrdersResponse> response = 
                restApi.cancelAllAlgoOpenOrders(formattedSymbol, recvWindow);
            
            // 处理响应
            com.binance.connector.client.derivatives_trading_usds_futures.rest.model.CancelAllAlgoOpenOrdersResponse responseData = response.getData();
            if (responseData == null) {
                log.warn("[Binance Futures] 取消条件单无返回数据");
                return new HashMap<>();
            }
            
            log.info("[Binance Futures] 取消所有条件单成功: {}", responseData);
            
            // 转换为Map
            Map<String, Object> result = new HashMap<>();
            result.put("success", true);
            result.put("data", responseData);
            
            return result;
        } catch (Exception exc) {
            log.error("[Binance Futures] 取消所有条件单失败: {}", exc.getMessage(), exc);
            throw new RuntimeException("取消条件单失败: " + exc.getMessage(), exc);
        }
    }
}

