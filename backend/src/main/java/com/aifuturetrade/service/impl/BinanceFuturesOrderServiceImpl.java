package com.aifuturetrade.service.impl;

import com.aifuturetrade.common.api.binance.BinanceConfig;
import com.aifuturetrade.common.api.binance.BinanceFuturesOrderClient;
import com.aifuturetrade.common.util.QuantityFormatUtil;
import com.aifuturetrade.dao.entity.AlgoOrderDO;
import com.aifuturetrade.dao.entity.BinanceTradeLogDO;
import com.aifuturetrade.dao.entity.ModelDO;
import com.aifuturetrade.dao.entity.PortfolioDO;
import com.aifuturetrade.dao.entity.TradeDO;
import com.aifuturetrade.dao.mapper.AlgoOrderMapper;
import com.aifuturetrade.dao.mapper.BinanceTradeLogMapper;
import com.aifuturetrade.dao.mapper.ModelMapper;
import com.aifuturetrade.dao.mapper.PortfolioMapper;
import com.aifuturetrade.dao.mapper.TradeMapper;
import com.aifuturetrade.service.BinanceFuturesOrderService;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 币安期货订单服务实现类
 */
@Slf4j
@Service
public class BinanceFuturesOrderServiceImpl implements BinanceFuturesOrderService {

    @Autowired
    private PortfolioMapper portfolioMapper;

    @Autowired
    private TradeMapper tradeMapper;

    @Autowired
    private ModelMapper modelMapper;

    @Autowired
    private BinanceTradeLogMapper binanceTradeLogMapper;

    @Autowired
    private AlgoOrderMapper algoOrderMapper;

    @Autowired
    private BinanceConfig binanceConfig;

    @Value("${app.sell-position-trade-mode:test}")
    private String sellPositionTradeMode;

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> sellPosition(String modelId, String symbol) {
        log.info("[BinanceFuturesOrderService] 开始一键卖出持仓合约，modelId: {}, symbol: {}", modelId, symbol);
        
        try {
            // 0. 查询模型信息以判断是否为虚拟模式
            ModelDO model = modelMapper.selectById(modelId);
            if (model == null) {
                throw new RuntimeException("未找到模型记录，modelId: " + modelId);
            }
            Boolean isVirtual = model.getIsVirtual();
            boolean useTestMode = (isVirtual != null && isVirtual);
            
            // 0.1. 取消已存在的条件单（状态为new）
            String formattedSymbol = symbol.toUpperCase();
            if (!formattedSymbol.endsWith(binanceConfig.getQuoteAsset())) {
                formattedSymbol = formattedSymbol + binanceConfig.getQuoteAsset();
            }
            
            List<AlgoOrderDO> existingOrders = algoOrderMapper.selectNewAlgoOrdersByModelAndSymbol(modelId, formattedSymbol);
            if (existingOrders != null && !existingOrders.isEmpty()) {
                log.info("[BinanceFuturesOrderService] 找到 {} 个待取消的条件单，开始取消", existingOrders.size());
                
                if (!useTestMode && model.getApiKey() != null && model.getApiSecret() != null) {
                    // real模式：调用SDK查询和取消
                    try {
                        BinanceFuturesOrderClient algoClient = new BinanceFuturesOrderClient(
                                model.getApiKey(),
                                model.getApiSecret(),
                                binanceConfig.getQuoteAsset(),
                                binanceConfig.getBaseUrl(),
                                binanceConfig.getTestnet(),
                                binanceConfig.getConnectTimeout(),
                                binanceConfig.getReadTimeout()
                        );
                        
                        // 查询SDK中的条件单
                        List<Map<String, Object>> sdkOrders = algoClient.queryAllAlgoOrders(
                                formattedSymbol, null, null, null, 0L, 100L, 5000L);
                        
                        // 检查SDK中是否有条件单
                        boolean hasSdkOrders = sdkOrders != null && !sdkOrders.isEmpty();
                        
                        if (hasSdkOrders) {
                            // SDK中有条件单，执行取消操作
                            Map<String, Object> cancelResult = algoClient.cancelAllAlgoOpenOrders(formattedSymbol, 5000L);
                            log.info("[BinanceFuturesOrderService] SDK取消条件单成功: {}", cancelResult);
                            
                            // SDK取消成功后，更新数据库状态
                            for (AlgoOrderDO order : existingOrders) {
                                algoOrderMapper.updateAlgoStatusToCancelled(order.getId());
                            }
                            log.info("[BinanceFuturesOrderService] 已更新数据库条件单状态为cancelled，数量: {}", existingOrders.size());
                        } else {
                            // SDK中未找到条件单，不执行取消操作
                            log.info("[BinanceFuturesOrderService] SDK中未找到条件单，不执行取消操作");
                            // 不更新数据库状态，直接继续后续流程
                        }
                    } catch (Exception sdkErr) {
                        log.error("[BinanceFuturesOrderService] real模式查询/取消条件单失败: {}", sdkErr.getMessage(), sdkErr);
                        // real模式失败时不更新数据库，避免数据不一致
                        throw new RuntimeException("取消条件单失败: " + sdkErr.getMessage(), sdkErr);
                    }
                } else {
                    // virtual模式：直接在数据库更新状态
                    for (AlgoOrderDO order : existingOrders) {
                        algoOrderMapper.updateAlgoStatusToCancelled(order.getId());
                    }
                    log.info("[BinanceFuturesOrderService] virtual模式已更新条件单状态为cancelled，数量: {}", existingOrders.size());
                }
            } else {
                log.debug("[BinanceFuturesOrderService] 未找到需要取消的条件单");
            }
            
            // 1. 查询持仓记录
            PortfolioDO portfolio = portfolioMapper.selectByModelIdAndSymbol(modelId, symbol, null);
            if (portfolio == null) {
                throw new RuntimeException("未找到持仓记录，modelId: " + modelId + ", symbol: " + symbol);
            }

            log.info("[BinanceFuturesOrderService] 找到持仓记录: positionSide={}, positionAmt={}", 
                    portfolio.getPositionSide(), portfolio.getPositionAmt());

            // 2. 验证模型API密钥信息（real模式需要）
            if (!useTestMode && (model.getApiKey() == null || model.getApiSecret() == null)) {
                throw new RuntimeException("模型缺少API密钥信息，modelId: " + modelId);
            }

            log.info("[BinanceFuturesOrderService] 模型信息验证成功，is_virtual: {}", isVirtual);

            // 3. 获取实时价格（使用BinanceFuturesOrderClient的getOrderBookTicker方法）
            // formattedSymbol已在前面定义，直接使用
            BinanceFuturesOrderClient priceClient = null;
            if (!useTestMode && model.getApiKey() != null && model.getApiSecret() != null) {
                // real模式：使用模型的API密钥
                priceClient = new BinanceFuturesOrderClient(
                        model.getApiKey(),
                        model.getApiSecret(),
                        binanceConfig.getQuoteAsset(),
                        binanceConfig.getBaseUrl(),
                        binanceConfig.getTestnet(),
                        binanceConfig.getConnectTimeout(),
                        binanceConfig.getReadTimeout()
                );
            } else if (binanceConfig.getApiKey() != null && binanceConfig.getSecretKey() != null) {
                // virtual模式或模型缺少API密钥：使用默认配置的API密钥
                priceClient = new BinanceFuturesOrderClient(
                        binanceConfig.getApiKey(),
                        binanceConfig.getSecretKey(),
                        binanceConfig.getQuoteAsset(),
                        binanceConfig.getBaseUrl(),
                        binanceConfig.getTestnet(),
                        binanceConfig.getConnectTimeout(),
                        binanceConfig.getReadTimeout()
                );
            } else {
                throw new RuntimeException("无法创建价格客户端：缺少API密钥配置");
            }
            
            List<Map<String, Object>> tickerData = priceClient.getOrderBookTicker(formattedSymbol);
            if (tickerData == null || tickerData.isEmpty()) {
                throw new RuntimeException("无法获取实时价格，symbol: " + formattedSymbol);
            }
            
            Map<String, Object> ticker = tickerData.get(0);
            Double currentPrice = null;
            if (ticker.get("askPrice") != null) {
                currentPrice = Double.parseDouble(ticker.get("askPrice").toString());
            } else if (ticker.get("bidPrice") != null) {
                currentPrice = Double.parseDouble(ticker.get("bidPrice").toString());
            } else {
                throw new RuntimeException("无法从ticker数据中获取价格");
            }

            log.info("[BinanceFuturesOrderService] 获取实时价格成功: {}", currentPrice);

            // 4. 确定 SDK 调用参数：持仓方向传实际方向，side 根据持仓方向确定
            // 平多(LONG): side=SELL, position_side=LONG
            // 平空(SHORT): side=BUY, position_side=SHORT
            String positionSide = portfolio.getPositionSide();
            boolean isLong = "LONG".equalsIgnoreCase(positionSide);
            String sdkSide = isLong ? "SELL" : "BUY";
            String sdkPositionSide = isLong ? "LONG" : "SHORT";
            String signal = isLong ? "sell_to_long" : "sell_to_short";

            log.info("[BinanceFuturesOrderService] 计算平仓参数: 持仓方向={}, side={}, position_side={}, signal={}",
                    positionSide, sdkSide, sdkPositionSide, signal);

            // 5. 计算盈亏和手续费
            Double entryPrice = portfolio.getAvgPrice();
            Double positionAmtRaw = Math.abs(portfolio.getPositionAmt());
            // 根据当前价格格式化数量小数位（用于SDK和落库）
            Double positionAmt = QuantityFormatUtil.formatQuantityForSdk(positionAmtRaw, currentPrice);
            if (positionAmt <= 0 && positionAmtRaw > 0) {
                positionAmt = positionAmtRaw;
            }
            
            // 计算毛盈亏
            Double grossPnl;
            if ("LONG".equalsIgnoreCase(positionSide)) {
                grossPnl = (currentPrice - entryPrice) * positionAmt;
            } else {
                grossPnl = (entryPrice - currentPrice) * positionAmt;
            }
            
            // 计算手续费（使用默认费率0.001，即0.1%）
            Double tradeFeeRate = 0.001;
            Double tradeAmount = positionAmt * currentPrice;
            Double fee = tradeAmount * tradeFeeRate;
            
            // 计算净盈亏
            Double netPnl = grossPnl - fee;
            
            log.info("[BinanceFuturesOrderService] 计算盈亏: 开仓价={}, 当前价={}, 数量={}, 方向={}, 毛盈亏={}, 手续费={}, 净盈亏={}", 
                    entryPrice, currentPrice, positionAmt, positionSide, grossPnl, fee, netPnl);

            // 6. 调用SDK执行卖出（在删除portfolios记录之前）
            BinanceFuturesOrderClient orderClient = null;
            if (!useTestMode && model.getApiKey() != null && model.getApiSecret() != null) {
                // real模式：使用模型的API密钥
                orderClient = new BinanceFuturesOrderClient(
                        model.getApiKey(),
                        model.getApiSecret(),
                        binanceConfig.getQuoteAsset(),
                        binanceConfig.getBaseUrl(),
                        binanceConfig.getTestnet(),
                        binanceConfig.getConnectTimeout(),
                        binanceConfig.getReadTimeout()
                );
            } else if (binanceConfig.getApiKey() != null && binanceConfig.getSecretKey() != null) {
                // virtual模式或模型缺少API密钥：使用默认配置的API密钥
                orderClient = new BinanceFuturesOrderClient(
                        binanceConfig.getApiKey(),
                        binanceConfig.getSecretKey(),
                        binanceConfig.getQuoteAsset(),
                        binanceConfig.getBaseUrl(),
                        binanceConfig.getTestnet(),
                        binanceConfig.getConnectTimeout(),
                        binanceConfig.getReadTimeout()
                );
            } else {
                throw new RuntimeException("无法创建订单客户端：缺少API密钥配置");
            }

            // 使用之前获取的isVirtual和useTestMode
            String modelTradeMode = useTestMode ? "test" : "real";
            
            Map<String, Object> orderParams = new HashMap<>();
            orderParams.put("symbol", formattedSymbol);
            orderParams.put("side", sdkSide);
            orderParams.put("quantity", positionAmt);
            orderParams.put("orderType", "MARKET");
            orderParams.put("positionSide", sdkPositionSide);
            orderParams.put("testMode", useTestMode);

            log.info("[BinanceFuturesOrderService] 调用SDK执行卖出，交易模式: {} (is_virtual={}, {})", 
                    modelTradeMode, isVirtual, useTestMode ? "测试接口，不会真实成交" : "真实交易接口");
            log.info("[BinanceFuturesOrderService] 调用SDK执行卖出，参数: {}", orderParams);

            Map<String, Object> sdkResponse = null;
            String responseType = "200";
            String sdkError = null;
            
            try {
                sdkResponse = orderClient.marketTrade(
                        formattedSymbol,
                        sdkSide,
                        positionAmt,
                        "MARKET",
                        sdkPositionSide,
                        useTestMode
                );
                log.info("[BinanceFuturesOrderService] SDK调用成功: {}", sdkResponse);
            } catch (Exception e) {
                sdkError = e.getMessage();
                log.error("[BinanceFuturesOrderService] SDK调用失败: {}", sdkError, e);
                responseType = "500";
                // real模式调用失败时，不抛出异常，继续执行数据库记录（quantity和price设置为0，error字段记录错误）
                // test模式失败时也不抛出异常，继续执行（保持一致性）
                log.warn("[BinanceFuturesOrderService] SDK调用失败，将继续记录到trades表（{}模式）", modelTradeMode);
            }

            // 8. 解析SDK返回数据（如果是real模式且调用成功）
            String finalSignal = signal;
            String finalPositionSide = positionSide;  // 持仓方向（LONG/SHORT）
            String finalSideDirection = "sell";  // 交易方向（buy/sell），默认sell
            Double finalQuantity = positionAmt;
            Double finalPrice = currentPrice;
            Long orderId = null;
            String orderType = null;
            String origType = null;
            String errorMsg = null;
            
            if (!useTestMode && sdkResponse != null) {
                // real模式且调用成功，解析SDK返回数据
                Object executedQtyObj = sdkResponse.get("executedQty");
                Object avgPriceObj = sdkResponse.get("avgPrice");
                Object sideObj = sdkResponse.get("side");
                Object positionSideObj = sdkResponse.get("positionSide");
                Object orderIdObj = sdkResponse.get("orderId");
                Object typeObj = sdkResponse.get("type");
                Object origTypeObj = sdkResponse.get("origType");
                
                // 提取executedQty（成交量）
                if (executedQtyObj != null) {
                    try {
                        finalQuantity = Double.parseDouble(executedQtyObj.toString());
                    } catch (Exception e) {
                        log.warn("[BinanceFuturesOrderService] 解析executedQty失败: {}", e.getMessage());
                    }
                }
                
                // 提取avgPrice（平均成交价）
                if (avgPriceObj != null) {
                    try {
                        finalPrice = Double.parseDouble(avgPriceObj.toString());
                    } catch (Exception e) {
                        log.warn("[BinanceFuturesOrderService] 解析avgPrice失败: {}", e.getMessage());
                    }
                }
                
                // 提取side（买卖方向），映射到signal和交易方向
                if (sideObj != null) {
                    String sideStr = sideObj.toString().toUpperCase();
                    if ("BUY".equals(sideStr)) {
                        finalSideDirection = "buy";
                        String posSide = positionSideObj != null ? positionSideObj.toString().toUpperCase() : "";
                        if ("SHORT".equals(posSide)) {
                            finalSignal = "buy_to_short";
                        } else {
                            finalSignal = "buy_to_long";
                        }
                    } else if ("SELL".equals(sideStr)) {
                        finalSideDirection = "sell";
                        String posSide = positionSideObj != null ? positionSideObj.toString().toUpperCase() : "";
                        if ("SHORT".equals(posSide)) {
                            finalSignal = "sell_to_short";
                        } else {
                            finalSignal = "sell_to_long";
                        }
                    }
                }
                
                // 提取positionSide（持仓方向），存储到position_side字段
                if (positionSideObj != null) {
                    String posSide = positionSideObj.toString().toUpperCase();
                    if ("LONG".equals(posSide) || "SHORT".equals(posSide)) {
                        finalPositionSide = posSide;
                    }
                }
                
                // 提取orderId
                if (orderIdObj != null) {
                    try {
                        orderId = Long.parseLong(orderIdObj.toString());
                    } catch (Exception e) {
                        log.warn("[BinanceFuturesOrderService] 解析orderId失败: {}", e.getMessage());
                    }
                }
                
                // 提取type
                if (typeObj != null) {
                    orderType = typeObj.toString();
                }
                
                // 提取origType
                if (origTypeObj != null) {
                    origType = origTypeObj.toString();
                }
            } else if (!useTestMode && sdkError != null) {
                // real模式调用失败，quantity和price设置为0，signal和side使用策略返回的值
                finalQuantity = 0.0;
                finalPrice = 0.0;
                errorMsg = sdkError;
                // 使用实际调用的 sdkSide 作为交易方向
                finalSideDirection = "BUY".equalsIgnoreCase(sdkSide) ? "buy" : "sell";
                log.warn("[BinanceFuturesOrderService] real模式调用失败，quantity和price设置为0，signal和side使用策略返回的值");
            } else {
                // test模式，使用实际调用的 sdkSide 作为交易方向
                finalSideDirection = "BUY".equalsIgnoreCase(sdkSide) ? "buy" : "sell";
            }
            
            // 9. 插入trades表记录（使用传入的modelId，而不是system_user）
            TradeDO trade = new TradeDO();
            trade.setModelId(modelId);  // 使用传入的modelId
            trade.setFuture(symbol);
            trade.setSignal(finalSignal);  // 使用解析后的signal
            trade.setPrice(finalPrice);  // 使用解析后的price
            trade.setQuantity(finalQuantity);  // 使用解析后的quantity
            trade.setSide(finalSideDirection);  // 交易方向（buy/sell）
            trade.setPositionSide(finalPositionSide);  // 持仓方向（LONG/SHORT）
            trade.setPnl(netPnl);  // 设置净盈亏
            trade.setFee(fee);      // 设置手续费
            // 设置原始保证金（从portfolio中获取，用于计算盈亏百分比）
            Double initialMargin = portfolio.getInitialMargin();
            trade.setInitialMargin(initialMargin != null ? initialMargin : 0.0);
            // 设置 portfolios_id（关联的持仓ID）
            trade.setPortfoliosId(portfolio.getId());
            // 设置新字段（如果real模式有值）
            if (orderId != null) {
                trade.setOrderId(orderId);
            }
            if (orderType != null) {
                trade.setType(orderType);
            }
            if (origType != null) {
                trade.setOrigType(origType);
            }
            if (errorMsg != null) {
                trade.setError(errorMsg);
            }
            // 使用UTC+8时区的时间（与Python代码保持一致）
            trade.setTimestamp(LocalDateTime.now(ZoneOffset.ofHours(8)));
            tradeMapper.insert(trade);

            log.info("[BinanceFuturesOrderService] 插入trades表记录成功: tradeId={}, modelId={}, signal={}, quantity={}, price={}, pnl={}, fee={}", 
                    trade.getId(), modelId, finalSignal, finalQuantity, finalPrice, netPnl, fee);

            // 9. 只有在real模式且SDK返回成功时才删除portfolios表记录
            if (!useTestMode && sdkResponse != null && sdkError == null) {
                // real模式且SDK返回成功，删除portfolios表记录
                try {
                    portfolioMapper.deleteById(portfolio.getId());
                    log.info("[BinanceFuturesOrderService] 删除portfolios表记录成功（real模式，SDK成功）: portfolioId={}", portfolio.getId());
                } catch (Exception dbErr) {
                    log.error("[BinanceFuturesOrderService] 删除portfolios表记录失败: {}", dbErr.getMessage(), dbErr);
                    // 不抛出异常，因为交易已经记录到trades表
                }
            } else if (useTestMode) {
                // test模式，删除portfolios表记录（测试模式始终更新）
                try {
                    portfolioMapper.deleteById(portfolio.getId());
                    log.info("[BinanceFuturesOrderService] 删除portfolios表记录成功（test模式）: portfolioId={}", portfolio.getId());
                } catch (Exception dbErr) {
                    log.error("[BinanceFuturesOrderService] 删除portfolios表记录失败: {}", dbErr.getMessage(), dbErr);
                }
            } else {
                // real模式但SDK调用失败，不删除portfolios表记录
                log.warn("[BinanceFuturesOrderService] 跳过删除portfolios表记录（real模式，SDK失败）: portfolioId={}, error={}", 
                        portfolio.getId(), sdkError);
            }

            // 10. 记录binance_trade_logs（model_id仍然使用system_user）
            BinanceTradeLogDO tradeLog = new BinanceTradeLogDO();
            tradeLog.setModelId("system_user");  // binance_trade_logs表仍然使用system_user
            tradeLog.setTradeId(trade.getId());
            tradeLog.setType(modelTradeMode);  // 根据is_virtual设置类型
            tradeLog.setMethodName("marketTrade");
            
            try {
                tradeLog.setParam(objectMapper.writeValueAsString(orderParams));
                if (sdkResponse != null) {
                    tradeLog.setResponseContext(objectMapper.writeValueAsString(sdkResponse));
                }
                tradeLog.setResponseType(responseType);
            } catch (Exception e) {
                log.warn("[BinanceFuturesOrderService] 序列化参数失败: {}", e.getMessage());
            }
            
            tradeLog.setCreatedAt(LocalDateTime.now());
            binanceTradeLogMapper.insert(tradeLog);

            log.info("[BinanceFuturesOrderService] 记录binance_trade_logs成功: logId={}", tradeLog.getId());

            // 12. 返回结果
            Map<String, Object> result = new HashMap<>();
            result.put("success", true);
            result.put("message", "卖出成功");
            result.put("tradeId", trade.getId());
            result.put("symbol", symbol);
            result.put("quantity", positionAmt);
            result.put("price", currentPrice);
            result.put("positionSide", portfolio.getPositionSide());
            result.put("pnl", netPnl);
            result.put("fee", fee);
            
            log.info("[BinanceFuturesOrderService] 一键卖出完成，modelId: {}, symbol: {}", modelId, symbol);
            
            return result;
            
        } catch (Exception e) {
            log.error("[BinanceFuturesOrderService] 一键卖出失败，modelId: {}, symbol: {}, error: {}", 
                    modelId, symbol, e.getMessage(), e);
            throw new RuntimeException("一键卖出失败: " + e.getMessage(), e);
        }
    }
}

