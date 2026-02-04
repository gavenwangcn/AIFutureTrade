package com.aifuturetrade.asyncservice.service.impl;

import com.aifuturetrade.asyncservice.api.binance.BinanceFuturesBase;
import com.aifuturetrade.asyncservice.api.binance.BinanceFuturesClient;
import com.aifuturetrade.asyncservice.api.binance.BinanceFuturesOrderClient;
import com.aifuturetrade.asyncservice.dao.mapper.*;
import com.aifuturetrade.asyncservice.entity.*;
import com.aifuturetrade.asyncservice.service.AlgoOrderProcessResult;
import com.aifuturetrade.asyncservice.service.AlgoOrderService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import com.aifuturetrade.asyncservice.dao.mapper.StrategyDecisionMapper;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 条件订单服务实现
 * 
 * 功能：
 * 1. 定时检查algo_order表中状态为"new"的条件订单
 * 2. 对于real类型的模型：
 *    a. 查询SDK接口的symbol条件单信息
 *    b. 如果状态不为"new"，则更新状态到数据库
 *    c. 如果状态为"new"：
 *       - LONG类型：当挂单价格高于市场价格时（triggerPrice > currentPrice），执行SDK市场价格卖出（如果返回200），回写trade记录（价格为市场价格），更新挂单信息
 *       - SHORT类型：当挂单价格低于市场价时（triggerPrice < currentPrice），执行SDK市场价格卖出（如果返回200），回写trade记录（价格为市场价格），更新挂单信息
 * 3. 对于virtual类型的模型：使用原有逻辑（基于市场价格判断）
 * 4. 如果触发，执行交易并更新相关表（trades、account_value_historys、account_values等）
 */
@Slf4j
@Service
public class AlgoOrderServiceImpl implements AlgoOrderService {
    
    @Autowired
    private AlgoOrderMapper algoOrderMapper;
    
    @Autowired
    private ModelMapper modelMapper;
    
    @Autowired
    private PortfolioMapper portfolioMapper;
    
    @Autowired
    private TradeMapper tradeMapper;
    
    @Autowired
    private AccountValueMapper accountValueMapper;
    
    @Autowired
    private AccountValueHistoryMapper accountValueHistoryMapper;
    
    @Autowired
    private StrategyDecisionMapper strategyDecisionMapper;
    
    @Value("${async.algo-order.interval-seconds:2}")
    private int intervalSeconds;
    
    @Value("${binance.api-key}")
    private String defaultApiKey;
    
    @Value("${binance.secret-key}")
    private String defaultSecretKey;
    
    @Value("${binance.quote-asset:USDT}")
    private String quoteAsset;
    
    @Value("${trade.fee-rate:0.001}")
    private Double tradeFeeRate;
    
    private final AtomicBoolean schedulerRunning = new AtomicBoolean(false);
    
    // 缓存每个模型的 Binance 客户端（使用模型自己的 API Key）
    private final Map<String, BinanceFuturesBase> modelClients = new ConcurrentHashMap<>();

    // 缓存每个模型的 Binance 订单客户端（用于订单和交易操作）
    private final Map<String, BinanceFuturesOrderClient> modelOrderClients = new ConcurrentHashMap<>();
    
    @PostConstruct
    public void init() {
        log.info("[AlgoOrderService] 🛠️ 条件订单服务初始化完成");
        log.info("[AlgoOrderService] ⏱️ 执行周期: {} 秒", intervalSeconds);
    }
    
    @PreDestroy
    public void destroy() {
        log.info("[AlgoOrderService] 🛑 收到服务销毁信号，停止调度器...");
        stopScheduler();
        // 清理客户端缓存
        modelClients.clear();
        modelOrderClients.clear();
        log.info("[AlgoOrderService] 👋 条件订单服务已销毁");
    }
    
    @Override
    @Scheduled(fixedDelayString = "${async.algo-order.interval-seconds:2}000", initialDelay = 5000)
    public void startScheduler() {
        if (schedulerRunning.get()) {
            return;
        }
        
        schedulerRunning.set(true);
        try {
            processAlgoOrders();
        } finally {
            schedulerRunning.set(false);
        }
    }
    
    @Override
    public void stopScheduler() {
        schedulerRunning.set(false);
    }
    
    @Override
    public boolean isSchedulerRunning() {
        return schedulerRunning.get();
    }
    
    @Override
    public AlgoOrderProcessResult processAlgoOrders() {
        log.info("=".repeat(80));
        log.info("[AlgoOrderService] ========== 开始执行条件订单检查 ==========");
        
        AlgoOrderProcessResult result = new AlgoOrderProcessResult();
        
        try {
            // 查询所有状态为"new"的条件订单
            List<AlgoOrderDO> newOrders = algoOrderMapper.selectNewAlgoOrders();
            result.setTotalChecked(newOrders.size());
            
            if (newOrders.isEmpty()) {
                log.debug("[AlgoOrderService] 没有待处理的条件订单");
                return result;
            }
            
            log.info("[AlgoOrderService] 找到 {} 个待处理的条件订单", newOrders.size());
            
            for (AlgoOrderDO order : newOrders) {
                try {
                    processAlgoOrder(order, result);
                } catch (Exception e) {
                    log.error("[AlgoOrderService] 处理条件订单失败: orderId={}, error={}", 
                            order.getId(), e.getMessage(), e);
                    result.setFailedCount(result.getFailedCount() + 1);
                }
            }
            
            log.info("[AlgoOrderService] ========== 条件订单检查完成 ==========");
            log.info("[AlgoOrderService] 总计: {}, 已触发: {}, 已执行: {}, 失败: {}, 跳过: {}", 
                    result.getTotalChecked(), result.getTriggeredCount(), 
                    result.getExecutedCount(), result.getFailedCount(), result.getSkippedCount());
            
        } catch (Exception e) {
            log.error("[AlgoOrderService] 执行条件订单检查异常: {}", e.getMessage(), e);
        }
        
        return result;
    }
    
    /**
     * 处理单个条件订单
     */
    private void processAlgoOrder(AlgoOrderDO order, AlgoOrderProcessResult result) {
        String orderId = order.getId();
        String symbol = order.getSymbol();
        String positionSide = order.getPositionSide();
        Double triggerPrice = order.getTriggerPrice();
        
        log.debug("[AlgoOrderService] 处理条件订单: orderId={}, symbol={}, positionSide={}, triggerPrice={}", 
                orderId, symbol, positionSide, triggerPrice);
        
        // 获取模型信息
        ModelDO model = modelMapper.selectById(order.getModelId());
        if (model == null) {
            log.warn("[AlgoOrderService] 模型不存在，跳过: modelId={}", order.getModelId());
            result.setSkippedCount(result.getSkippedCount() + 1);
            return;
        }
        
        // 判断是否为real类型模型
        boolean isVirtual = model.getIsVirtual() != null && model.getIsVirtual();
        
        if (!isVirtual) {
            // real类型模型：查询SDK接口的条件单信息
            processRealModelAlgoOrder(order, model, result);
        } else {
            // virtual类型模型：使用原有逻辑（基于市场价格判断）
            processVirtualModelAlgoOrder(order, model, result);
        }
    }
    
    /**
     * 处理real类型模型的条件订单
     * 1. 查询SDK接口的symbol条件单信息
     * 2. 如果状态不为"new"，则更新状态到数据库
     * 3. 如果状态为"new"，根据价格判断是否执行交易
     */
    private void processRealModelAlgoOrder(AlgoOrderDO order, ModelDO model, AlgoOrderProcessResult result) {
        String orderId = order.getId();
        String symbol = order.getSymbol();
        String positionSide = order.getPositionSide();
        Double triggerPrice = order.getTriggerPrice();
        Double quantity = order.getQuantity();

        log.debug("[AlgoOrderService] [real模式] 处理条件订单: orderId={}, symbol={}, positionSide={}, triggerPrice={}",
                orderId, symbol, positionSide, triggerPrice);
        
        // 获取Binance订单客户端
        BinanceFuturesOrderClient orderClient = getOrCreateOrderClient(model);
        if (orderClient == null) {
            log.warn("[AlgoOrderService] [real模式] 无法创建Binance订单客户端，跳过: orderId={}", orderId);
            result.setSkippedCount(result.getSkippedCount() + 1);
            return;
        }

        // 查询SDK接口的条件单信息（使用单个algoId查询）
        try {
            Long dbAlgoId = order.getAlgoId();
            if (dbAlgoId == null) {
                log.warn("[AlgoOrderService] [real模式] 订单缺少algoId，跳过: orderId={}", orderId);
                result.setSkippedCount(result.getSkippedCount() + 1);
                return;
            }

            // 使用单个algoId查询接口
            Map<String, Object> sdkOrderMap = orderClient.queryAlgoOrder(dbAlgoId, 5000L);

            if (sdkOrderMap == null) {
                log.debug("[AlgoOrderService] [real模式] SDK中未找到条件单: orderId={}, algoId={}", orderId, dbAlgoId);
                result.setSkippedCount(result.getSkippedCount() + 1);
                return;
            }

            // 获取SDK返回的状态
            String sdkStatus = (String) sdkOrderMap.get("algoStatus");
            if (sdkStatus == null) {
                sdkStatus = "";
            }

            log.debug("[AlgoOrderService] [real模式] SDK条件单状态: orderId={}, algoId={}, sdkStatus={}",
                    orderId, dbAlgoId, sdkStatus);
            
            // 如果状态不为"new"，说明条件单已在币安侧执行，需要构建trades记录
            if (!"new".equalsIgnoreCase(sdkStatus)) {
                try {
                    String dbStatus = mapSdkStatusToDbStatus(sdkStatus);

                    // 检查是否为已成交状态且尚未创建trades记录
                    boolean isExecutedStatus = "executed".equalsIgnoreCase(dbStatus) ||
                                              "triggered".equalsIgnoreCase(dbStatus);

                    if (isExecutedStatus && order.getTradeId() == null) {
                        log.info("[AlgoOrderService] [real模式] 检测到已成交订单，开始构建trades记录: orderId={}, sdkStatus={}",
                                orderId, sdkStatus);

                        // 从SDK返回的数据中获取成交信息
                        String actualPriceStr = (String) sdkOrderMap.get("actualPrice");
                        String quantityStr = (String) sdkOrderMap.get("quantity");
                        Object actualOrderIdObj = sdkOrderMap.get("actualOrderId");

                        if (actualPriceStr != null && !actualPriceStr.isEmpty()) {
                            try {
                                Double actualPrice = Double.parseDouble(actualPriceStr);
                                Double executedQuantity = quantity;
                                if (quantityStr != null && !quantityStr.isEmpty()) {
                                    executedQuantity = Double.parseDouble(quantityStr);
                                }
                                Long actualOrderId = null;
                                if (actualOrderIdObj != null) {
                                    if (actualOrderIdObj instanceof Long) {
                                        actualOrderId = (Long) actualOrderIdObj;
                                    } else if (actualOrderIdObj instanceof String) {
                                        actualOrderId = Long.parseLong((String) actualOrderIdObj);
                                    }
                                }

                                // 构建trades记录（不调用平仓接口）
                                String tradeId = buildTradeRecordFromSdkData(order, model, actualPrice, executedQuantity, actualOrderId);

                                // 更新algo_order表状态和trade_id
                                algoOrderMapper.updateTradeIdAndStatus(orderId, tradeId, dbStatus);
                                log.info("[AlgoOrderService] [real模式] ✅ 已构建trades记录并更新状态: orderId={}, tradeId={}, dbStatus={}",
                                        orderId, tradeId, dbStatus);

                                // 更新strategy_decisions表状态为EXECUTED
                                String strategyDecisionId = order.getStrategyDecisionId();
                                if (strategyDecisionId != null && !strategyDecisionId.isEmpty()) {
                                    strategyDecisionMapper.updateStrategyDecisionStatus(
                                            strategyDecisionId,
                                            "EXECUTED",
                                            tradeId,
                                            null
                                    );
                                    log.info("[AlgoOrderService] [real模式] ✅ 已更新strategy_decisions表状态为EXECUTED: decisionId={}, tradeId={}",
                                            strategyDecisionId, tradeId);
                                }

                                result.setExecutedCount(result.getExecutedCount() + 1);
                            } catch (NumberFormatException e) {
                                log.error("[AlgoOrderService] [real模式] 解析SDK返回的价格或数量失败: orderId={}, actualPrice={}, quantity={}, error={}",
                                        orderId, actualPriceStr, quantityStr, e.getMessage());
                                // 只更新状态，不构建trades记录
                                algoOrderMapper.updateAlgoStatus(orderId, dbStatus);
                                result.setSkippedCount(result.getSkippedCount() + 1);
                            } catch (Exception e) {
                                log.error("[AlgoOrderService] [real模式] 构建trades记录失败: orderId={}, error={}",
                                        orderId, e.getMessage(), e);

                                // 提取详细错误信息
                                String errorReason = extractErrorReason(e);

                                // 更新订单状态为"failed"并记录错误原因
                                algoOrderMapper.updateAlgoStatusWithError(orderId, "failed", errorReason);

                                // 更新strategy_decisions表状态为REJECTED
                                String strategyDecisionId = order.getStrategyDecisionId();
                                if (strategyDecisionId != null && !strategyDecisionId.isEmpty()) {
                                    strategyDecisionMapper.updateStrategyDecisionStatus(
                                            strategyDecisionId,
                                            "REJECTED",
                                            null,
                                            errorReason
                                    );
                                }

                                result.setFailedCount(result.getFailedCount() + 1);
                            }
                        } else {
                            // 没有实际成交价格，只更新状态
                            log.warn("[AlgoOrderService] [real模式] SDK未返回实际成交价格，只更新状态: orderId={}, sdkStatus={}",
                                    orderId, sdkStatus);
                            algoOrderMapper.updateAlgoStatus(orderId, dbStatus);
                            result.setSkippedCount(result.getSkippedCount() + 1);
                        }
                    } else {
                        // 非成交状态或已有trades记录，只更新状态
                        algoOrderMapper.updateAlgoStatus(orderId, dbStatus);
                        log.info("[AlgoOrderService] [real模式] 已更新数据库状态: orderId={}, sdkStatus={}, dbStatus={}",
                                orderId, sdkStatus, dbStatus);
                        result.setSkippedCount(result.getSkippedCount() + 1);
                    }
                } catch (Exception e) {
                    log.error("[AlgoOrderService] [real模式] 处理已成交订单失败: orderId={}, sdkStatus={}, error={}",
                            orderId, sdkStatus, e.getMessage(), e);
                    result.setFailedCount(result.getFailedCount() + 1);
                }
                return;
            }

            // 状态为"new"，条件单尚未触发，跳过处理
            log.debug("[AlgoOrderService] [real模式] 条件单状态为new，等待币安侧触发: orderId={}, symbol={}, triggerPrice={}",
                    orderId, symbol, triggerPrice);
            result.setSkippedCount(result.getSkippedCount() + 1);
            
        } catch (Exception e) {
            log.error("[AlgoOrderService] [real模式] 查询SDK条件单失败: orderId={}, symbol={}, error={}", 
                    orderId, symbol, e.getMessage(), e);
            result.setFailedCount(result.getFailedCount() + 1);
        }
    }
    
    /**
     * 处理virtual类型模型的条件订单（使用原有逻辑）
     */
    private void processVirtualModelAlgoOrder(AlgoOrderDO order, ModelDO model, AlgoOrderProcessResult result) {
        String orderId = order.getId();
        String symbol = order.getSymbol();
        String positionSide = order.getPositionSide();
        Double triggerPrice = order.getTriggerPrice();
        
        log.debug("[AlgoOrderService] [virtual模式] 处理条件订单: orderId={}, symbol={}, positionSide={}, triggerPrice={}", 
                orderId, symbol, positionSide, triggerPrice);
        
        // 获取当前市场价格
        Double currentPrice = getCurrentPrice(symbol, model);
        if (currentPrice == null || currentPrice <= 0) {
            log.warn("[AlgoOrderService] [virtual模式] 无法获取市场价格，跳过: symbol={}", symbol);
            result.setSkippedCount(result.getSkippedCount() + 1);
            return;
        }
        
        // 判断是否触发成交条件
        // LONG型：市场价格 <= 触发价格时触发（currentPrice <= triggerPrice），成交价为市场价
        // SHORT型：市场价格 >= 触发价格时触发（currentPrice >= triggerPrice），成交价为市场价
        boolean shouldTrigger = false;
        if ("LONG".equalsIgnoreCase(positionSide)) {
            // LONG持仓：市场价格 <= 触发价格 就触发，成交价为市场价
            shouldTrigger = currentPrice <= triggerPrice;
        } else if ("SHORT".equalsIgnoreCase(positionSide)) {
            // SHORT持仓：市场价格 >= 触发价格 就触发，成交价为市场价
            shouldTrigger = currentPrice >= triggerPrice;
        }
        
        if (!shouldTrigger) {
            log.debug("[AlgoOrderService] [virtual模式] 条件未触发: symbol={}, currentPrice={}, triggerPrice={}, positionSide={}", 
                    symbol, currentPrice, triggerPrice, positionSide);
            return;
        }
        
        log.info("[AlgoOrderService] [virtual模式] ✅ 条件订单触发: orderId={}, symbol={}, currentPrice={}, triggerPrice={}, positionSide={}", 
                orderId, symbol, currentPrice, triggerPrice, positionSide);
        
        result.setTriggeredCount(result.getTriggeredCount() + 1);
        
        // 更新订单状态为"triggered"
        try {
            algoOrderMapper.updateAlgoStatus(orderId, "triggered");
            log.info("[AlgoOrderService] [virtual模式] 订单状态已更新为triggered: orderId={}", orderId);
        } catch (Exception e) {
            log.error("[AlgoOrderService] [virtual模式] 更新订单状态失败: orderId={}, error={}", orderId, e.getMessage());
            result.setFailedCount(result.getFailedCount() + 1);
            return;
        }
        
        // 执行交易并构建相关记录
        String tradeId = null;
        try {
            tradeId = executeTradeAndBuildRecords(order, model, currentPrice);
            result.setExecutedCount(result.getExecutedCount() + 1);
            
            // 更新订单状态为"executed"并关联trade_id
            int updateCount = algoOrderMapper.updateTradeIdAndStatus(orderId, tradeId, "executed");
            if (updateCount > 0) {
                log.info("[AlgoOrderService] [virtual模式] ✅ 交易执行完成，订单状态已更新为executed: orderId={}, tradeId={}, symbol={}", 
                        orderId, tradeId, symbol);
            } else {
                log.warn("[AlgoOrderService] [virtual模式] ⚠️ 交易执行完成，但更新订单状态失败: orderId={}, tradeId={}", 
                        orderId, tradeId);
            }
            
            // 更新strategy_decisions表状态为EXECUTED（如果有strategy_decision_id）
            String strategyDecisionId = order.getStrategyDecisionId();
            if (strategyDecisionId != null && !strategyDecisionId.isEmpty()) {
                try {
                    strategyDecisionMapper.updateStrategyDecisionStatus(
                            strategyDecisionId,
                            "EXECUTED",
                            tradeId,
                            null  // error_reason = null，表示成功
                    );
                    log.info("[AlgoOrderService] [virtual模式] ✅ 已更新strategy_decisions表状态为EXECUTED: decisionId={}, tradeId={}", 
                            strategyDecisionId, tradeId);
                } catch (Exception updateErr) {
                    log.error("[AlgoOrderService] [virtual模式] ⚠️ 更新strategy_decisions表状态失败: decisionId={}, tradeId={}, error={}", 
                            strategyDecisionId, tradeId, updateErr.getMessage(), updateErr);
                }
            }
        } catch (Exception e) {
            log.error("[AlgoOrderService] [virtual模式] ❌ 交易执行失败: orderId={}, error={}", orderId, e.getMessage(), e);
            result.setFailedCount(result.getFailedCount() + 1);

            // 提取详细错误信息
            String errorReason = extractErrorReason(e);

            // 更新订单状态为"failed"并记录错误原因
            try {
                algoOrderMapper.updateAlgoStatusWithError(orderId, "failed", errorReason);
                log.info("[AlgoOrderService] [virtual模式] 订单状态已更新为failed: orderId={}, errorReason={}", orderId, errorReason);
            } catch (Exception updateEx) {
                log.error("[AlgoOrderService] [virtual模式] 更新订单状态为failed失败: orderId={}, error={}",
                        orderId, updateEx.getMessage());
            }
            
            // 更新strategy_decisions表状态为REJECTED（如果有strategy_decision_id）
            String strategyDecisionId = order.getStrategyDecisionId();
            if (strategyDecisionId != null && !strategyDecisionId.isEmpty()) {
                try {
                    strategyDecisionMapper.updateStrategyDecisionStatus(
                            strategyDecisionId,
                            "REJECTED",
                            tradeId,
                            errorReason
                    );
                    log.info("[AlgoOrderService] [virtual模式] ✅ 已更新strategy_decisions表状态为REJECTED: decisionId={}, tradeId={}, errorReason={}",
                            strategyDecisionId, tradeId, errorReason);
                } catch (Exception updateErr) {
                    log.error("[AlgoOrderService] [virtual模式] ⚠️ 更新strategy_decisions表状态失败: decisionId={}, error={}",
                            strategyDecisionId, updateErr.getMessage(), updateErr);
                }
            }
        }
    }
    
    /**
     * 将SDK返回的状态映射到数据库状态
     */
    private String mapSdkStatusToDbStatus(String sdkStatus) {
        if (sdkStatus == null) {
            return "new";
        }
        String statusLower = sdkStatus.toLowerCase();
        // SDK状态映射：triggered -> triggered, executed -> executed, cancelled -> cancelled, rejected -> failed
        if (statusLower.contains("triggered") || statusLower.contains("executed")) {
            return statusLower.contains("executed") ? "executed" : "triggered";
        } else if (statusLower.contains("cancelled") || statusLower.contains("canceled")) {
            return "cancelled";
        } else if (statusLower.contains("rejected") || statusLower.contains("failed")) {
            return "failed";
        }
        return "new";  // 默认返回new
    }
    
    /**
     * 格式化交易对符号
     */
    private String formatSymbol(String symbol) {
        if (symbol == null || symbol.isEmpty()) {
            return symbol;
        }
        String upperSymbol = symbol.toUpperCase();
        if (!upperSymbol.endsWith(quoteAsset)) {
            return upperSymbol + quoteAsset;
        }
        return upperSymbol;
    }
    
    /**
     * 获取当前价格
     */
    private Double getCurrentPrice(String symbol, ModelDO model) {
        try {
            BinanceFuturesBase client = getOrCreateClient(model);
            if (client == null) {
                return null;
            }
            
            // 使用 BinanceFuturesClient 获取价格
            if (client instanceof BinanceFuturesClient) {
                BinanceFuturesClient futuresClient = (BinanceFuturesClient) client;
                
                // 调用 getSymbolPrices 方法
                List<String> symbols = java.util.Collections.singletonList(symbol);
                Map<String, Map<String, Object>> prices = futuresClient.getSymbolPrices(symbols);
                
                if (prices != null && prices.containsKey(symbol.toUpperCase())) {
                    Map<String, Object> priceData = prices.get(symbol.toUpperCase());
                    if (priceData != null && priceData.containsKey("price")) {
                        Object priceObj = priceData.get("price");
                        if (priceObj instanceof Number) {
                            return ((Number) priceObj).doubleValue();
                        } else if (priceObj instanceof String) {
                            try {
                                return Double.parseDouble((String) priceObj);
                            } catch (NumberFormatException e) {
                                log.warn("[AlgoOrderService] 价格格式错误: {}", priceObj);
                            }
                        }
                    }
                }
            }
            
            return null;
        } catch (Exception e) {
            log.error("[AlgoOrderService] 获取 {} 当前价格失败: {}", symbol, e.getMessage());
            return null;
        }
    }
    
    /**
     * 执行交易并构建相关记录
     */
    private String executeTradeAndBuildRecords(AlgoOrderDO order, ModelDO model, Double currentPrice) {
        String orderId = order.getId();
        String modelId = order.getModelId();
        String symbol = order.getSymbol().toUpperCase();
        String positionSide = order.getPositionSide();
        Double quantity = order.getQuantity();
        String side = order.getSide(); // 'buy' or 'sell'
        String orderType = order.getOrderType();
        
        // 查询持仓信息
        PortfolioDO position = portfolioMapper.selectPosition(modelId, symbol, positionSide);
        if (position == null) {
            throw new RuntimeException("持仓不存在: modelId=" + modelId + ", symbol=" + symbol + ", positionSide=" + positionSide);
        }
        
        Double positionAmt = Math.abs(position.getPositionAmt());
        Double avgPrice = position.getAvgPrice();
        Double initialMargin = position.getInitialMargin();
        Integer leverage = position.getLeverage() != null ? position.getLeverage() : model.getLeverage() != null ? model.getLeverage() : 10;
        
        // 验证数量
        if (quantity > positionAmt) {
            quantity = positionAmt;
            log.warn("[AlgoOrderService] 订单数量超过持仓数量，使用持仓数量: orderId={}, quantity={}, positionAmt={}", 
                    orderId, order.getQuantity(), positionAmt);
        }
        
        // 判断交易模式
        boolean isVirtual = model.getIsVirtual() != null && model.getIsVirtual();
        boolean useTestMode = isVirtual;
        
        // 执行交易
        Long binanceOrderId = null;
        Double executedPrice = currentPrice;
        Double executedQuantity = quantity;
        
        if (!useTestMode) {
            // real模式：调用真实交易接口
            BinanceFuturesOrderClient orderClient = getOrCreateOrderClient(model);
            if (orderClient == null) {
                throw new RuntimeException("无法创建 Binance 订单客户端");
            }

            try {
                // 使用 BinanceFuturesOrderClient 的 marketTrade 方法
                Map<String, Object> tradeResult = orderClient.marketTrade(symbol, side, quantity, positionSide);

                // 从响应中获取订单信息
                if (tradeResult != null) {
                    Object orderIdObj = tradeResult.get("orderId");
                    if (orderIdObj != null) {
                        if (orderIdObj instanceof Long) {
                            binanceOrderId = (Long) orderIdObj;
                        } else if (orderIdObj instanceof String) {
                            binanceOrderId = Long.parseLong((String) orderIdObj);
                        }
                    }

                    // 从响应中获取实际成交价格和数量
                    String avgPriceStr = (String) tradeResult.get("avgPrice");
                    if (avgPriceStr != null && !avgPriceStr.isEmpty()) {
                        executedPrice = Double.parseDouble(avgPriceStr);
                    }

                    String executedQtyStr = (String) tradeResult.get("executedQty");
                    if (executedQtyStr != null && !executedQtyStr.isEmpty()) {
                        executedQuantity = Double.parseDouble(executedQtyStr);
                    }

                    log.info("[AlgoOrderService] ✅ 交易执行成功: orderId={}, binanceOrderId={}, executedPrice={}, executedQuantity={}",
                            orderId, binanceOrderId, executedPrice, executedQuantity);
                } else {
                    throw new RuntimeException("交易接口返回为空");
                }
            } catch (Exception e) {
                log.error("[AlgoOrderService] ❌ 交易执行失败: orderId={}, error={}", orderId, e.getMessage(), e);
                throw e;
            }
        } else {
            // virtual模式：不调用真实接口，直接使用当前价格
            log.info("[AlgoOrderService] ℹ️ 虚拟交易模式，跳过真实交易接口调用: orderId={}", orderId);
        }
        
        // 计算手续费和盈亏
        Double tradeAmount = executedQuantity * executedPrice;
        Double tradeFee = tradeAmount * tradeFeeRate;
        
        // 计算盈亏
        Double grossPnl;
        if ("LONG".equalsIgnoreCase(positionSide)) {
            grossPnl = (executedPrice - avgPrice) * executedQuantity;
        } else {
            grossPnl = (avgPrice - executedPrice) * executedQuantity;
        }
        Double netPnl = grossPnl - tradeFee;
        
        // 生成trade_id
        String tradeId = UUID.randomUUID().toString();
        LocalDateTime now = LocalDateTime.now(ZoneId.of("Asia/Shanghai"));
        
        // 1. 插入trades表记录
        TradeDO trade = new TradeDO();
        trade.setId(tradeId);
        trade.setModelId(modelId);
        trade.setFuture(symbol);
        trade.setSignal(orderType.toLowerCase().contains("stop") ? "stop_loss" : "take_profit");
        trade.setQuantity(executedQuantity);
        trade.setPrice(executedPrice);
        trade.setLeverage(leverage);
        trade.setSide(side);
        trade.setPositionSide(positionSide);
        trade.setPnl(netPnl);
        trade.setFee(tradeFee);
        trade.setInitialMargin(initialMargin);
        trade.setStrategyDecisionId(order.getStrategyDecisionId());
        trade.setOrderId(binanceOrderId);
        trade.setType(orderType);
        trade.setTimestamp(now);
        tradeMapper.insert(trade);
        log.info("[AlgoOrderService] ✅ 已插入trades表记录: tradeId={}", tradeId);
        
        // 2. 更新portfolios表（减少持仓数量）
        Double newPositionAmt = positionAmt - executedQuantity;
        if (newPositionAmt <= 0) {
            // 持仓数量为0，删除持仓记录
            portfolioMapper.deletePosition(modelId, symbol, positionSide);
            log.info("[AlgoOrderService] ✅ 已删除持仓记录: modelId={}, symbol={}, positionSide={}", 
                    modelId, symbol, positionSide);
        } else {
            // 更新持仓数量
            portfolioMapper.updatePositionAmt(modelId, symbol, positionSide, newPositionAmt);
            log.info("[AlgoOrderService] ✅ 已更新持仓数量: modelId={}, symbol={}, positionSide={}, newPositionAmt={}", 
                    modelId, symbol, positionSide, newPositionAmt);
        }
        
        // 3. 查询或创建account_values记录
        String accountAlias = model.getAccountAlias() != null ? model.getAccountAlias() : "";
        AccountValueDO accountValue = accountValueMapper.selectLatestByModelAndAlias(modelId, accountAlias);
        
        Double balance = model.getInitialCapital() != null ? model.getInitialCapital() : 10000.0;
        Double availableBalance = balance;
        Double crossWalletBalance = balance;
        Double crossPnl = 0.0;
        Double crossUnPnl = 0.0;
        
        if (accountValue != null) {
            balance = accountValue.getBalance() != null ? accountValue.getBalance() : balance;
            availableBalance = accountValue.getAvailableBalance() != null ? accountValue.getAvailableBalance() : availableBalance;
            crossWalletBalance = accountValue.getCrossWalletBalance() != null ? accountValue.getCrossWalletBalance() : crossWalletBalance;
            crossPnl = accountValue.getCrossPnl() != null ? accountValue.getCrossPnl() : 0.0;
            crossUnPnl = accountValue.getCrossUnPnl() != null ? accountValue.getCrossUnPnl() : 0.0;
        }
        
        // 更新账户价值
        // 根据 trade 模块的逻辑：
        // - balance = initial_capital + realized_pnl + unrealized_pnl (total_value)
        // - available_balance = initial_capital + realized_pnl - margin_used (cash)
        // - cross_pnl = realized_pnl (已实现盈亏)
        // - cross_un_pnl = unrealized_pnl (未实现盈亏)
        // 
        // 当前简化实现：累加本次交易的净盈亏
        // TODO: 后续可以优化为查询所有持仓计算未实现盈亏和已用保证金
        crossPnl = crossPnl + netPnl;  // 累加已实现盈亏
        balance = balance + netPnl;    // 总余额增加净盈亏
        availableBalance = availableBalance + netPnl;  // 可用余额增加净盈亏（简化：不考虑保证金释放）
        crossWalletBalance = balance;   // 全仓余额等于总余额
        
        // 更新或插入account_values表
        if (accountValue != null) {
            // 更新现有记录
            accountValueMapper.updateAccountValueById(accountValue.getId(), balance, availableBalance, 
                    crossWalletBalance, crossPnl, crossUnPnl, now);
        } else {
            // 插入新记录
            AccountValueDO newAccountValue = new AccountValueDO();
            newAccountValue.setId(UUID.randomUUID().toString());
            newAccountValue.setModelId(modelId);
            newAccountValue.setAccountAlias(accountAlias);
            newAccountValue.setBalance(balance);
            newAccountValue.setAvailableBalance(availableBalance);
            newAccountValue.setCrossWalletBalance(crossWalletBalance);
            newAccountValue.setCrossPnl(crossPnl);
            newAccountValue.setCrossUnPnl(crossUnPnl);
            newAccountValue.setTimestamp(now);
            accountValueMapper.insert(newAccountValue);
        }
        log.info("[AlgoOrderService] ✅ 已更新account_values表: modelId={}, balance={}, crossPnl={}", 
                modelId, balance, crossPnl);
        
        // 4. 插入account_value_historys表记录
        AccountValueHistoryDO history = new AccountValueHistoryDO();
        history.setId(UUID.randomUUID().toString());
        history.setModelId(modelId);
        history.setAccountAlias(accountAlias);
        history.setBalance(balance);
        history.setAvailableBalance(availableBalance);
        history.setCrossWalletBalance(crossWalletBalance);
        history.setCrossPnl(crossPnl);
        history.setCrossUnPnl(crossUnPnl);
        history.setTradeId(tradeId);
        history.setTimestamp(now);
        accountValueHistoryMapper.insert(history);
        log.info("[AlgoOrderService] ✅ 已插入account_value_historys表记录: historyId={}, tradeId={}", 
                history.getId(), tradeId);
        
        // 返回tradeId用于更新algo_order表和strategy_decisions表
        return tradeId;
    }

    /**
     * 根据SDK返回的数据构建trades记录（real模式专用，不调用平仓接口）
     *
     * @param order 条件订单
     * @param model 模型信息
     * @param actualPrice SDK返回的实际成交价格
     * @param executedQuantity SDK返回的实际成交数量
     * @param actualOrderId SDK返回的实际订单ID
     * @return tradeId
     */
    private String buildTradeRecordFromSdkData(AlgoOrderDO order, ModelDO model, Double actualPrice,
                                                Double executedQuantity, Long actualOrderId) {
        String orderId = order.getId();
        String modelId = order.getModelId();
        String symbol = order.getSymbol().toUpperCase();
        String positionSide = order.getPositionSide();
        String orderType = order.getOrderType();

        // 查询持仓信息
        PortfolioDO position = portfolioMapper.selectPosition(modelId, symbol, positionSide);
        if (position == null) {
            log.warn("[AlgoOrderService] [real模式] 持仓不存在，使用订单信息: modelId={}, symbol={}, positionSide={}",
                    modelId, symbol, positionSide);
            // 持仓可能已经被清空，使用订单中的信息
        }

        Double avgPrice = position != null ? position.getAvgPrice() : order.getTriggerPrice();
        Double initialMargin = position != null ? position.getInitialMargin() : 0.0;
        Integer leverage = position != null && position.getLeverage() != null ? position.getLeverage() :
                          model.getLeverage() != null ? model.getLeverage() : 10;

        // 计算手续费和盈亏
        Double tradeAmount = executedQuantity * actualPrice;
        Double tradeFee = tradeAmount * tradeFeeRate;

        // 计算盈亏
        Double grossPnl;
        if ("LONG".equalsIgnoreCase(positionSide)) {
            grossPnl = (actualPrice - avgPrice) * executedQuantity;
        } else {
            grossPnl = (avgPrice - actualPrice) * executedQuantity;
        }
        Double netPnl = grossPnl - tradeFee;

        // 生成trade_id
        String tradeId = UUID.randomUUID().toString();
        LocalDateTime now = LocalDateTime.now(ZoneId.of("Asia/Shanghai"));

        // 1. 插入trades表记录
        TradeDO trade = new TradeDO();
        trade.setId(tradeId);
        trade.setModelId(modelId);
        trade.setFuture(symbol);
        trade.setSignal(orderType.toLowerCase().contains("stop") ? "stop_loss" : "take_profit");
        trade.setQuantity(executedQuantity);
        trade.setPrice(actualPrice);  // 使用SDK返回的实际成交价格
        trade.setLeverage(leverage);
        trade.setSide("sell");  // 条件单通常是平仓，所以是sell
        trade.setPositionSide(positionSide);
        trade.setPnl(netPnl);
        trade.setFee(tradeFee);
        trade.setInitialMargin(initialMargin);
        trade.setStrategyDecisionId(order.getStrategyDecisionId());
        trade.setOrderId(actualOrderId);
        trade.setType(orderType);
        trade.setTimestamp(now);
        tradeMapper.insert(trade);
        log.info("[AlgoOrderService] [real模式] ✅ 已插入trades表记录: tradeId={}, price={}, quantity={}",
                tradeId, actualPrice, executedQuantity);

        // 2. 更新portfolios表（减少持仓数量）
        if (position != null) {
            Double positionAmt = Math.abs(position.getPositionAmt());
            Double newPositionAmt = positionAmt - executedQuantity;
            if (newPositionAmt <= 0) {
                // 持仓数量为0，删除持仓记录
                portfolioMapper.deletePosition(modelId, symbol, positionSide);
                log.info("[AlgoOrderService] [real模式] ✅ 已删除持仓记录: modelId={}, symbol={}, positionSide={}",
                        modelId, symbol, positionSide);
            } else {
                // 更新持仓数量
                portfolioMapper.updatePositionAmt(modelId, symbol, positionSide, newPositionAmt);
                log.info("[AlgoOrderService] [real模式] ✅ 已更新持仓数量: modelId={}, symbol={}, positionSide={}, newPositionAmt={}",
                        modelId, symbol, positionSide, newPositionAmt);
            }
        }

        // 3. 查询或创建account_values记录
        String accountAlias = model.getAccountAlias() != null ? model.getAccountAlias() : "";
        AccountValueDO accountValue = accountValueMapper.selectLatestByModelAndAlias(modelId, accountAlias);

        Double balance = model.getInitialCapital() != null ? model.getInitialCapital() : 10000.0;
        Double availableBalance = balance;
        Double crossWalletBalance = balance;
        Double crossPnl = 0.0;
        Double crossUnPnl = 0.0;

        if (accountValue != null) {
            balance = accountValue.getBalance() != null ? accountValue.getBalance() : balance;
            availableBalance = accountValue.getAvailableBalance() != null ? accountValue.getAvailableBalance() : availableBalance;
            crossWalletBalance = accountValue.getCrossWalletBalance() != null ? accountValue.getCrossWalletBalance() : crossWalletBalance;
            crossPnl = accountValue.getCrossPnl() != null ? accountValue.getCrossPnl() : 0.0;
            crossUnPnl = accountValue.getCrossUnPnl() != null ? accountValue.getCrossUnPnl() : 0.0;
        }

        // 更新账户价值
        crossPnl = crossPnl + netPnl;  // 累加已实现盈亏
        balance = balance + netPnl;    // 总余额增加净盈亏
        availableBalance = availableBalance + netPnl;  // 可用余额增加净盈亏
        crossWalletBalance = balance;   // 全仓余额等于总余额

        // 更新或插入account_values表
        if (accountValue != null) {
            // 更新现有记录
            accountValueMapper.updateAccountValueById(accountValue.getId(), balance, availableBalance,
                    crossWalletBalance, crossPnl, crossUnPnl, now);
        } else {
            // 插入新记录
            AccountValueDO newAccountValue = new AccountValueDO();
            newAccountValue.setId(UUID.randomUUID().toString());
            newAccountValue.setModelId(modelId);
            newAccountValue.setAccountAlias(accountAlias);
            newAccountValue.setBalance(balance);
            newAccountValue.setAvailableBalance(availableBalance);
            newAccountValue.setCrossWalletBalance(crossWalletBalance);
            newAccountValue.setCrossPnl(crossPnl);
            newAccountValue.setCrossUnPnl(crossUnPnl);
            newAccountValue.setTimestamp(now);
            accountValueMapper.insert(newAccountValue);
        }
        log.info("[AlgoOrderService] [real模式] ✅ 已更新account_values表: modelId={}, balance={}, crossPnl={}",
                modelId, balance, crossPnl);

        // 4. 插入account_value_historys表记录
        AccountValueHistoryDO history = new AccountValueHistoryDO();
        history.setId(UUID.randomUUID().toString());
        history.setModelId(modelId);
        history.setAccountAlias(accountAlias);
        history.setBalance(balance);
        history.setAvailableBalance(availableBalance);
        history.setCrossWalletBalance(crossWalletBalance);
        history.setCrossPnl(crossPnl);
        history.setCrossUnPnl(crossUnPnl);
        history.setTradeId(tradeId);
        history.setTimestamp(now);
        accountValueHistoryMapper.insert(history);
        log.info("[AlgoOrderService] [real模式] ✅ 已插入account_value_historys表记录: historyId={}, tradeId={}",
                history.getId(), tradeId);

        // 返回tradeId用于更新algo_order表和strategy_decisions表
        return tradeId;
    }

    /**
     * 获取或创建 Binance 客户端（使用模型自己的 API Key）
     */
    private BinanceFuturesBase getOrCreateClient(ModelDO model) {
        String modelId = model.getId();

        // 从缓存中获取
        BinanceFuturesBase client = modelClients.get(modelId);
        if (client != null) {
            return client;
        }

        // 创建新的客户端
        try {
            String apiKey = model.getApiKey();
            String apiSecret = model.getApiSecret();

            if (apiKey == null || apiKey.isEmpty() || apiSecret == null || apiSecret.isEmpty()) {
                log.warn("[AlgoOrderService] 模型未配置API密钥，使用默认密钥: modelId={}", modelId);
                apiKey = defaultApiKey;
                apiSecret = defaultSecretKey;
            }

            client = new BinanceFuturesClient(apiKey, apiSecret, quoteAsset, null, false);
            modelClients.put(modelId, client);

            log.debug("[AlgoOrderService] 创建 Binance 客户端: modelId={}", modelId);
            return client;
        } catch (Exception e) {
            log.error("[AlgoOrderService] 创建 Binance 客户端失败: modelId={}, error={}",
                    modelId, e.getMessage());
            return null;
        }
    }

    /**
     * 获取或创建 Binance 订单客户端（使用模型自己的 API Key）
     */
    private BinanceFuturesOrderClient getOrCreateOrderClient(ModelDO model) {
        String modelId = model.getId();

        // 从缓存中获取
        BinanceFuturesOrderClient orderClient = modelOrderClients.get(modelId);
        if (orderClient != null) {
            return orderClient;
        }

        // 创建新的订单客户端
        try {
            String apiKey = model.getApiKey();
            String apiSecret = model.getApiSecret();

            if (apiKey == null || apiKey.isEmpty() || apiSecret == null || apiSecret.isEmpty()) {
                log.warn("[AlgoOrderService] 模型未配置API密钥，使用默认密钥: modelId={}", modelId);
                apiKey = defaultApiKey;
                apiSecret = defaultSecretKey;
            }

            orderClient = new BinanceFuturesOrderClient(apiKey, apiSecret, quoteAsset, null, false);
            modelOrderClients.put(modelId, orderClient);

            log.debug("[AlgoOrderService] 创建 Binance 订单客户端: modelId={}", modelId);
            return orderClient;
        } catch (Exception e) {
            log.error("[AlgoOrderService] 创建 Binance 订单客户端失败: modelId={}, error={}",
                    modelId, e.getMessage());
            return null;
        }
    }

    /**
     * 提取详细错误原因
     */
    private String extractErrorReason(Exception e) {
        if (e == null) {
            return "未知错误";
        }

        String errorMessage = e.getMessage();
        if (errorMessage == null || errorMessage.isEmpty()) {
            errorMessage = e.getClass().getSimpleName();
        }

        // 分类错误类型
        String errorType = "未知错误";

        // 持仓相关错误
        if (errorMessage.contains("持仓不存在")) {
            errorType = "持仓不存在";
        }
        // Binance客户端错误
        else if (errorMessage.contains("无法创建 Binance 客户端")) {
            errorType = "Binance客户端创建失败";
        }
        // 交易接口错误
        else if (errorMessage.contains("交易接口返回为空")) {
            errorType = "交易接口返回为空";
        }
        // Binance API错误
        else if (errorMessage.contains("Insufficient balance") || errorMessage.contains("余额不足")) {
            errorType = "账户余额不足";
        } else if (errorMessage.contains("Invalid quantity") || errorMessage.contains("数量") || errorMessage.contains("precision")) {
            errorType = "订单数量或精度错误";
        } else if (errorMessage.contains("Invalid price") || errorMessage.contains("价格")) {
            errorType = "订单价格错误";
        } else if (errorMessage.contains("MIN_NOTIONAL") || errorMessage.contains("最小订单")) {
            errorType = "订单金额低于最小限制";
        } else if (errorMessage.contains("Rate limit") || errorMessage.contains("限流") || errorMessage.contains("Too many requests")) {
            errorType = "API请求频率限制";
        } else if (errorMessage.contains("API key") || errorMessage.contains("权限") || errorMessage.contains("Permission")) {
            errorType = "API Key权限不足";
        } else if (errorMessage.contains("timeout") || errorMessage.contains("超时") || errorMessage.contains("timed out")) {
            errorType = "网络超时";
        } else if (errorMessage.contains("connection") || errorMessage.contains("连接") || errorMessage.contains("网络")) {
            errorType = "网络连接失败";
        } else if (errorMessage.contains("Symbol") || errorMessage.contains("交易对")) {
            errorType = "交易对不存在或已下架";
        } else if (errorMessage.contains("Position") || errorMessage.contains("持仓模式")) {
            errorType = "持仓模式错误";
        }
        // 数据库错误
        else if (errorMessage.contains("Duplicate") || errorMessage.contains("重复")) {
            errorType = "数据库主键冲突";
        } else if (errorMessage.contains("database") || errorMessage.contains("数据库") || errorMessage.contains("SQL")) {
            errorType = "数据库操作失败";
        }

        // 限制错误信息长度（最多500字符）
        String fullError = errorType + ": " + errorMessage;
        if (fullError.length() > 500) {
            fullError = fullError.substring(0, 497) + "...";
        }

        return fullError;
    }
}
