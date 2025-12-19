package com.aifuturetrade.common.api.binance;

import com.binance.connector.client.common.ApiResponse;
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
     */
    public BinanceFuturesOrderClient(String apiKey, String apiSecret, String quoteAsset, 
                                    String baseUrl, Boolean testnet) {
        this.quoteAsset = (quoteAsset != null ? quoteAsset : "USDT").toUpperCase();
        initRestApi(apiKey, apiSecret, null, null, baseUrl);
    }
    
    /**
     * 构造函数，使用默认配置
     */
    public BinanceFuturesOrderClient(String apiKey, String apiSecret) {
        this(apiKey, apiSecret, "USDT", null, false);
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
    @SuppressWarnings("unchecked")
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
            ApiResponse<?> response = restApi.symbolOrderBookTicker(formattedSymbol);
            
            // 获取响应数据
            Object data = getResponseData(response);
            
            // 处理响应数据
            List<Map<String, Object>> tickers = new ArrayList<>();
            if (data instanceof List) {
                List<Object> dataList = (List<Object>) data;
                for (Object item : dataList) {
                    tickers.add(toMap(item));
                }
            } else {
                tickers.add(toMap(data));
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
            
            // 调用REST API接口
            // TODO: 根据实际SDK API调整调用方式，可能需要使用Request对象
            // ApiResponse<?> response = restApi.changeInitialLeverage(...);
            // Map<String, Object> data = toMap(getResponseData(response));
            Map<String, Object> data = new HashMap<>(); // 临时占位符
            
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
            ApiResponse<?> response;
            
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
                
                // TODO: 根据实际SDK API调整调用方式，可能需要使用Request对象
                // response = restApi.testOrder(...);
                response = null; // 临时占位符
                
                log.info("[Binance Futures] 测试接口调用成功（未真实下单）");
            } else {
                // 使用真实交易接口
                log.info("[Binance Futures] 使用真实交易接口下单");
                
                // TODO: 根据实际SDK API调整调用方式，可能需要使用Request对象
                // response = restApi.newOrder(...);
                response = null; // 临时占位符
            }
            
            // 处理响应
            if (response == null) {
                throw new RuntimeException("API调用返回null，请检查API调用方式");
            }
            Object data = getResponseData(response);
            Map<String, Object> responseDict = toMap(data);
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
     * 从ApiResponse中获取数据
     */
    private Object getResponseData(ApiResponse<?> response) {
        if (response == null) {
            return null;
        }
        try {
            // 尝试使用反射获取data字段或方法
            try {
                java.lang.reflect.Method dataMethod = response.getClass().getMethod("data");
                return dataMethod.invoke(response);
            } catch (NoSuchMethodException e) {
                try {
                    java.lang.reflect.Method getDataMethod = response.getClass().getMethod("getData");
                    return getDataMethod.invoke(response);
                } catch (NoSuchMethodException e2) {
                    // 尝试直接访问data字段
                    try {
                        java.lang.reflect.Field dataField = response.getClass().getField("data");
                        return dataField.get(response);
                    } catch (NoSuchFieldException e3) {
                        // 如果都失败，返回response本身
                        return response;
                    }
                }
            }
        } catch (Exception e) {
            log.warn("获取响应数据失败: {}", e.getMessage());
            return response;
        }
    }
}

