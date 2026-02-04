package com.aifuturetrade.asyncservice.api.binance;

import com.binance.connector.client.common.ApiResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.NewOrderRequest;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.NewOrderResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.TestOrderRequest;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.TestOrderResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.QueryAlgoOrderResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.QueryAllAlgoOrdersResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.QueryAllAlgoOrdersResponseInner;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.CancelAllAlgoOpenOrdersResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.Side;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.PositionSide;
import lombok.extern.slf4j.Slf4j;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 币安期货订单客户端 - 专注于交易和订单查询功能
 *
 * 提供条件单查询、市场价交易等功能，
 * 支持传入不同的api_key和api_secret进行操作。
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
     * 查询单个条件单状态（根据algoId）
     *
     * 参考 API: GET /fapi/v1/algo/order
     * 参考示例: QueryAlgoOrderExample.java
     *
     * @param algoId 算法订单ID（必填）
     * @param recvWindow 接收窗口（可选，默认5000ms）
     * @return 条件单详情，如果查询失败返回null
     */
    public Map<String, Object> queryAlgoOrder(Long algoId, Long recvWindow) {
        try {
            if (algoId == null) {
                throw new IllegalArgumentException("algoId不能为空");
            }

            log.debug("[BinanceFuturesOrderClient] 查询单个条件单，algoId: {}", algoId);

            // 调用REST API接口 - 使用单个algoId查询
            ApiResponse<QueryAlgoOrderResponse> response =
                    restApi.queryAlgoOrder(algoId, null, recvWindow != null ? recvWindow : 5000L);

            // 检查HTTP状态码
            if (response == null) {
                log.warn("[BinanceFuturesOrderClient] SDK查询条件单返回为空: algoId={}", algoId);
                return null;
            }

            int httpStatusCode = response.getStatusCode();
            if (httpStatusCode != 200) {
                log.warn("[BinanceFuturesOrderClient] SDK查询条件单返回非200状态码: algoId={}, statusCode={}",
                        algoId, httpStatusCode);
                return null;
            }

            // 处理响应数据
            QueryAlgoOrderResponse responseData = response.getData();
            if (responseData == null) {
                log.debug("[BinanceFuturesOrderClient] SDK中未找到条件单: algoId={}", algoId);
                return null;
            }

            // 转换为Map
            Map<String, Object> orderMap = new HashMap<>();
            orderMap.put("algoId", responseData.getAlgoId());
            orderMap.put("clientAlgoId", responseData.getClientAlgoId());
            orderMap.put("algoType", responseData.getAlgoType());
            orderMap.put("orderType", responseData.getOrderType());
            orderMap.put("symbol", responseData.getSymbol());
            orderMap.put("side", responseData.getSide());
            orderMap.put("positionSide", responseData.getPositionSide());
            orderMap.put("quantity", responseData.getQuantity());
            orderMap.put("algoStatus", responseData.getAlgoStatus());
            orderMap.put("triggerPrice", responseData.getTriggerPrice());
            orderMap.put("price", responseData.getPrice());
            orderMap.put("actualPrice", responseData.getActualPrice());
            orderMap.put("actualOrderId", responseData.getActualOrderId());
            orderMap.put("createTime", responseData.getCreateTime());
            orderMap.put("updateTime", responseData.getUpdateTime());

            log.debug("[BinanceFuturesOrderClient] 查询单个条件单成功: algoId={}, status={}",
                    algoId, responseData.getAlgoStatus());

            return orderMap;

        } catch (IllegalArgumentException e) {
            log.error("[BinanceFuturesOrderClient] 查询单个条件单参数错误: {}", e.getMessage());
            throw e;
        } catch (Exception e) {
            log.error("[BinanceFuturesOrderClient] 查询单个条件单失败: algoId={}, error={}",
                    algoId, e.getMessage(), e);
            return null;
        }
    }

    /**
     * 市场价格交易（支持测试模式）
     *
     * 参考 API: POST /fapi/v1/order
     *
     * @param symbol 交易对符号，如 'BTCUSDT'
     * @param side 交易方向，'BUY'或'SELL'
     * @param quantity 订单数量（必填，必须大于0）
     * @param positionSide 持仓方向，'LONG'（多）或'SHORT'（空），双向持仓模式下必填
     * @param testMode 是否使用测试模式（true=测试接口，不会真实成交；false=真实交易）
     * @return 订单响应数据
     */
    public Map<String, Object> marketTrade(String symbol, String side, Double quantity, String positionSide, boolean testMode) {
        try {
            if (quantity == null || quantity <= 0) {
                throw new IllegalArgumentException("quantity参数必须大于0，当前值: " + quantity);
            }

            String formattedSymbol = formatSymbol(symbol);
            log.info("[BinanceFuturesOrderClient] 开始市场交易，交易对: {}, 方向: {}, 数量: {}, 持仓方向: {}, 测试模式: {}",
                    formattedSymbol, side, quantity, positionSide, testMode);

            if (testMode) {
                // 使用测试接口
                TestOrderRequest testRequest = new TestOrderRequest();
                testRequest.setSymbol(formattedSymbol);
                testRequest.setSide(Side.fromValue(side.toUpperCase()));
                testRequest.setType("MARKET");
                testRequest.setQuantity(quantity);

                if (positionSide != null && !positionSide.isEmpty()) {
                    testRequest.setPositionSide(PositionSide.fromValue(positionSide.toUpperCase()));
                }

                // 调用测试订单接口
                ApiResponse<TestOrderResponse> response = restApi.testOrder(testRequest);

                if (response == null || response.getData() == null) {
                    throw new RuntimeException("测试接口返回为空");
                }

                // 处理测试响应
                TestOrderResponse testResponse = response.getData();
                Map<String, Object> responseDict = new HashMap<>();
                responseDict.put("orderId", testResponse.getOrderId());
                responseDict.put("clientOrderId", testResponse.getClientOrderId());
                responseDict.put("symbol", testResponse.getSymbol());
                responseDict.put("side", testResponse.getSide());
                responseDict.put("positionSide", testResponse.getPositionSide());
                responseDict.put("type", testResponse.getType());
                responseDict.put("status", testResponse.getStatus());
                responseDict.put("testMode", true);

                log.info("[BinanceFuturesOrderClient] 测试交易成功（未真实成交）: orderId={}",
                        testResponse.getOrderId());

                return responseDict;
            } else {
                // 使用真实交易接口
                NewOrderRequest orderRequest = new NewOrderRequest();
                orderRequest.setSymbol(formattedSymbol);
                orderRequest.setSide(Side.fromValue(side.toUpperCase()));
                orderRequest.setType("MARKET");
                orderRequest.setQuantity(quantity);

                if (positionSide != null && !positionSide.isEmpty()) {
                    orderRequest.setPositionSide(PositionSide.fromValue(positionSide.toUpperCase()));
                }

                // 调用REST API接口
                ApiResponse<NewOrderResponse> response = restApi.newOrder(orderRequest);

                if (response == null || response.getData() == null) {
                    throw new RuntimeException("交易接口返回为空");
                }

                // 处理响应
                NewOrderResponse orderResponse = response.getData();
                Map<String, Object> responseDict = new HashMap<>();
                responseDict.put("orderId", orderResponse.getOrderId());
                responseDict.put("clientOrderId", orderResponse.getClientOrderId());
                responseDict.put("symbol", orderResponse.getSymbol());
                responseDict.put("side", orderResponse.getSide());
                responseDict.put("positionSide", orderResponse.getPositionSide());
                responseDict.put("type", orderResponse.getType());
                responseDict.put("status", orderResponse.getStatus());
                responseDict.put("executedQty", orderResponse.getExecutedQty());
                responseDict.put("avgPrice", orderResponse.getAvgPrice());
                responseDict.put("cumQuote", orderResponse.getCumQuote());
                responseDict.put("testMode", false);

                log.info("[BinanceFuturesOrderClient] 市场交易成功: orderId={}, executedQty={}, avgPrice={}",
                        orderResponse.getOrderId(), orderResponse.getExecutedQty(), orderResponse.getAvgPrice());

                return responseDict;
            }

        } catch (Exception e) {
            log.error("[BinanceFuturesOrderClient] 市场交易失败: symbol={}, error={}",
                    symbol, e.getMessage(), e);
            throw new RuntimeException("市场交易失败: " + e.getMessage(), e);
        }
    }

    /**
     * 市场价格交易（默认真实交易模式）
     *
     * @param symbol 交易对符号，如 'BTCUSDT'
     * @param side 交易方向，'BUY'或'SELL'
     * @param quantity 订单数量（必填，必须大于0）
     * @param positionSide 持仓方向，'LONG'（多）或'SHORT'（空），双向持仓模式下必填
     * @return 订单响应数据
     */
    public Map<String, Object> marketTrade(String symbol, String side, Double quantity, String positionSide) {
        return marketTrade(symbol, side, quantity, positionSide, false);
    }

    /**
     * 查询所有条件单
     *
     * 参考 API: GET /fapi/v1/algo/orders
     *
     * @param symbol 交易对符号（必填）
     * @param algoId 算法订单ID（可选）
     * @param startTime 开始时间（可选，时间戳）
     * @param endTime 结束时间（可选，时间戳）
     * @param page 页码（可选，默认0）
     * @param limit 每页数量（可选，默认100，最大1000）
     * @param recvWindow 接收窗口（可选，默认5000）
     * @return 条件单列表，如果查询失败返回空列表
     */
    public List<Map<String, Object>> queryAllAlgoOrders(String symbol, Long algoId,
                                                        Long startTime, Long endTime,
                                                        Long page, Long limit, Long recvWindow) {
        try {
            String formattedSymbol = formatSymbol(symbol);
            log.debug("[BinanceFuturesOrderClient] 查询所有条件单，交易对: {}", formattedSymbol);

            // 调用REST API接口
            ApiResponse<QueryAllAlgoOrdersResponse> response =
                    restApi.queryAllAlgoOrders(formattedSymbol, algoId, startTime, endTime, page, limit, recvWindow);

            // 处理响应
            QueryAllAlgoOrdersResponse responseData = response != null ? response.getData() : null;
            if (responseData == null || responseData.isEmpty()) {
                log.debug("[BinanceFuturesOrderClient] 查询条件单无返回数据");
                return new ArrayList<>();
            }

            // 转换为Map列表
            List<Map<String, Object>> result = new ArrayList<>();
            for (QueryAllAlgoOrdersResponseInner order : responseData) {
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

            log.debug("[BinanceFuturesOrderClient] 查询所有条件单成功，找到 {} 个条件单", result.size());

            return result;
        } catch (Exception e) {
            log.error("[BinanceFuturesOrderClient] 查询所有条件单失败: symbol={}, error={}",
                    symbol, e.getMessage(), e);
            return new ArrayList<>();
        }
    }

    /**
     * 取消所有条件单
     *
     * 参考 API: DELETE /fapi/v1/algo/allOpenOrders
     *
     * @param symbol 交易对符号（必填）
     * @param recvWindow 接收窗口（可选，默认5000）
     * @return 取消结果，如果失败返回null
     */
    public Map<String, Object> cancelAllAlgoOpenOrders(String symbol, Long recvWindow) {
        try {
            String formattedSymbol = formatSymbol(symbol);
            log.info("[BinanceFuturesOrderClient] 取消所有条件单，交易对: {}", formattedSymbol);

            // 调用REST API接口
            ApiResponse<CancelAllAlgoOpenOrdersResponse> response =
                    restApi.cancelAllAlgoOpenOrders(formattedSymbol, recvWindow);

            // 处理响应
            CancelAllAlgoOpenOrdersResponse responseData = response != null ? response.getData() : null;
            if (responseData == null) {
                log.warn("[BinanceFuturesOrderClient] 取消条件单无返回数据");
                return null;
            }

            log.info("[BinanceFuturesOrderClient] 取消所有条件单成功: {}", responseData);

            // 转换为Map
            Map<String, Object> result = new HashMap<>();
            result.put("success", true);
            result.put("data", responseData);

            return result;
        } catch (Exception e) {
            log.error("[BinanceFuturesOrderClient] 取消所有条件单失败: symbol={}, error={}",
                    symbol, e.getMessage(), e);
            return null;
        }
    }
}
