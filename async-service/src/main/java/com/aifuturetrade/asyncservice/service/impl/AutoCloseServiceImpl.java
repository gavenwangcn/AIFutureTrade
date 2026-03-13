package com.aifuturetrade.asyncservice.service.impl;

import com.aifuturetrade.asyncservice.api.binance.BinanceFuturesBase;
import com.aifuturetrade.asyncservice.api.binance.BinanceFuturesClient;
import com.aifuturetrade.asyncservice.api.binance.BinanceFuturesOrderClient;
import com.aifuturetrade.asyncservice.dao.mapper.ModelMapper;
import com.aifuturetrade.asyncservice.dao.mapper.PortfolioMapper;
import com.aifuturetrade.asyncservice.dao.mapper.TradeMapper;
import com.aifuturetrade.asyncservice.dao.mapper.AlgoOrderMapper;
import com.aifuturetrade.asyncservice.entity.ModelDO;
import com.aifuturetrade.asyncservice.entity.AlgoOrderDO;
import com.aifuturetrade.asyncservice.entity.PortfolioDO;
import com.aifuturetrade.asyncservice.entity.PortfolioWithModelInfo;
import com.aifuturetrade.asyncservice.entity.TradeDO;
import com.aifuturetrade.asyncservice.service.AutoCloseResult;
import com.aifuturetrade.asyncservice.service.AutoCloseService;
import com.aifuturetrade.asyncservice.util.QuantityFormatUtil;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

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
 * 自动平仓服务实现
 * 
 * 功能：
 * 1. 定时检查所有持仓的损失百分比
 * 2. 当损失达到配置的阈值时，自动执行市场价卖出操作
 * 3. 使用 position_amt、当前价格（SDK获取）、avg_price 计算损失百分比
 */
@Slf4j
@Service
public class AutoCloseServiceImpl implements AutoCloseService {
    
    @Autowired
    private PortfolioMapper portfolioMapper;
    
    @Autowired
    private ModelMapper modelMapper;
    
    @Autowired
    private AlgoOrderMapper algoOrderMapper;

    @Autowired
    private TradeMapper tradeMapper;
    
    @Value("${async.auto-close.interval-seconds:3}")
    private int intervalSeconds;
    
    @Value("${binance.api-key}")
    private String defaultApiKey;
    
    @Value("${binance.secret-key}")
    private String defaultSecretKey;
    
    @Value("${binance.quote-asset:USDT}")
    private String quoteAsset;
    
    @Value("${async.auto-close.trade-mode:test}")
    private String tradeMode;

    private static final double TRADE_FEE_RATE = 0.001;
    
    private final AtomicBoolean schedulerRunning = new AtomicBoolean(false);
    
    // 缓存每个模型的 Binance 客户端（使用模型自己的 API Key）
    private final Map<String, BinanceFuturesBase> modelClients = new ConcurrentHashMap<>();

    // 缓存每个模型的 Binance 订单客户端（用于订单和交易操作）
    private final Map<String, BinanceFuturesOrderClient> modelOrderClients = new ConcurrentHashMap<>();
    
    @PostConstruct
    public void init() {
        log.info("[AutoCloseService] 🛠️ 自动平仓服务初始化完成");
        log.info("[AutoCloseService] ⏱️ 执行周期: {} 秒", intervalSeconds);
        log.info("[AutoCloseService] 💰 交易模式: {} ({})", 
                tradeMode, "test".equalsIgnoreCase(tradeMode) ? "测试接口，不会真实成交" : "真实交易接口");
    }
    
    @PreDestroy
    public void destroy() {
        log.info("[AutoCloseService] 🛑 收到服务销毁信号，停止调度器...");
        stopScheduler();
        // 清理客户端缓存
        modelClients.clear();
        modelOrderClients.clear();
        log.info("[AutoCloseService] 👋 自动平仓服务已销毁");
    }
    
    @Override
    @Scheduled(fixedDelayString = "${async.auto-close.interval-seconds:3}000", initialDelay = 5000)
    public void startScheduler() {
        if (schedulerRunning.get()) {
            return;
        }
        
        schedulerRunning.set(true);
        try {
            checkAndClosePositions();
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
    public AutoCloseResult checkAndClosePositions() {
        log.info("=".repeat(80));
        log.info("[AutoClose] ========== 开始执行自动平仓检查 ==========");
        
        int totalChecked = 0;
        int closedCount = 0;
        int failedCount = 0;
        int skippedCount = 0;
        
        try {
            // 查询所有持仓记录（包含模型信息）
            List<PortfolioWithModelInfo> positions = portfolioMapper.selectAllActivePositions();
            
            if (positions == null || positions.isEmpty()) {
                log.info("[AutoClose] ⚠️  没有需要检查的持仓记录");
                log.info("=".repeat(80));
                return new AutoCloseResult(0, 0, 0, 0);
            }
            
            log.info("[AutoClose] 📊 查询到 {} 条持仓记录", positions.size());
            totalChecked = positions.size();
            
            // 按模型分组处理（避免重复查询模型信息）
            Map<String, ModelDO> modelCache = new ConcurrentHashMap<>();
            
            for (PortfolioWithModelInfo position : positions) {
                try {
                    String modelId = position.getModelId();
                    String symbol = position.getSymbol();
                    String positionSide = position.getPositionSide();
                    Double positionAmt = position.getPositionAmt();
                    Double avgPrice = position.getAvgPrice();
                    Double initialMargin = position.getInitialMargin();
                    Double autoClosePercent = position.getAutoClosePercent();
                    
                    // 获取模型信息（使用缓存）
                    ModelDO model = modelCache.computeIfAbsent(modelId, id -> {
                        ModelDO m = modelMapper.selectModelById(id);
                        if (m == null) {
                            log.warn("[AutoClose] ⚠️  模型不存在: {}", id);
                        }
                        return m;
                    });
                    
                    if (model == null) {
                        skippedCount++;
                        continue;
                    }
                    
                    // 根据is_virtual判断使用real还是test模式
                    // 如果is_virtual不为true（即非虚拟），使用real模式
                    // is_virtual在数据库中：0表示非虚拟，1表示虚拟
                    // 在Java中映射为Boolean：false表示非虚拟，true表示虚拟
                    Boolean isVirtual = model.getIsVirtual();
                    boolean useRealMode = (isVirtual == null || !isVirtual);
                    String modelTradeMode = useRealMode ? "real" : "test";
                    
                    // 检查配置
                    if (autoClosePercent == null || autoClosePercent <= 0) {
                        log.debug("[AutoClose] 跳过 {} (模型: {}): auto_close_percent 未配置或为0", 
                                symbol, modelId);
                        skippedCount++;
                        continue;
                    }
                    
                    // 获取当前价格
                    Double currentPrice = getCurrentPrice(symbol, model);
                    if (currentPrice == null || currentPrice <= 0) {
                        log.warn("[AutoClose] ⚠️  无法获取 {} 的当前价格", symbol);
                        skippedCount++;
                        continue;
                    }
                    
                    // 计算损失百分比
                    double lossPercent = calculateLossPercent(
                            avgPrice, currentPrice, positionAmt, positionSide, initialMargin);
                    
                    log.debug("[AutoClose] {} (模型: {}): 持仓价格={}, 当前价格={}, 损失百分比={}%, 阈值={}%",
                            symbol, modelId, avgPrice, currentPrice, String.format("%.2f", lossPercent), String.format("%.2f", autoClosePercent));
                    
                    // 检查是否达到阈值
                    if (lossPercent >= autoClosePercent) {
                        log.warn("[AutoClose] 🚨 {} (模型: {}) 触发自动平仓: 损失 {}% >= 阈值 {}%",
                                symbol, modelId, String.format("%.2f", lossPercent), String.format("%.2f", autoClosePercent));

                        log.info("[AutoClose] 📤 准备执行平仓 | symbol={}, positionSide={}, positionAmt={}, modelTradeMode={}",
                                symbol, positionSide, positionAmt, modelTradeMode);

                        // 根据当前价格格式化数量小数位后执行平仓
                        double formattedAmt = QuantityFormatUtil.formatQuantityForSdk(positionAmt, currentPrice);
                        if (formattedAmt <= 0 && positionAmt > 0) {
                            formattedAmt = positionAmt;
                        }
                        boolean success = executeClosePosition(model, symbol, positionSide, formattedAmt, modelTradeMode,
                                avgPrice, currentPrice, initialMargin);
                        if (success) {
                            closedCount++;
                            log.info("[AutoClose] ✅ {} (模型: {}) 自动平仓成功", symbol, modelId);
                        } else {
                            failedCount++;
                            log.error("[AutoClose] ❌ {} (模型: {}) 自动平仓失败", symbol, modelId);
                        }
                    } else {
                        skippedCount++;
                    }
                    
                } catch (Exception e) {
                    log.error("[AutoClose] ❌ 处理持仓记录失败", e);
                    failedCount++;
                }
            }
            
            log.info("[AutoClose] ========== 自动平仓检查完成 ==========");
            log.info("[AutoClose] 📊 统计: 总计={}, 平仓={}, 失败={}, 跳过={}", 
                    totalChecked, closedCount, failedCount, skippedCount);
            log.info("=".repeat(80));
            
            return new AutoCloseResult(totalChecked, closedCount, failedCount, skippedCount);
            
        } catch (Exception e) {
            log.error("[AutoClose] ========== 自动平仓检查执行失败 ==========", e);
            log.info("=".repeat(80));
            return new AutoCloseResult(totalChecked, closedCount, failedCount, skippedCount);
        }
    }
    
    /**
     * 计算损失百分比
     * 
     * @param avgPrice 持仓平均价格
     * @param currentPrice 当前价格
     * @param positionAmt 持仓数量
     * @param positionSide 持仓方向（LONG/SHORT）
     * @param initialMargin 初始保证金（本金）
     * @return 损失百分比（正数表示损失）
     */
    private double calculateLossPercent(
            Double avgPrice, Double currentPrice, Double positionAmt, 
            String positionSide, Double initialMargin) {
        
        if (avgPrice == null || currentPrice == null || positionAmt == null || initialMargin == null) {
            return 0.0;
        }
        
        if (initialMargin <= 0) {
            return 0.0;
        }
        
        // 计算当前持仓价值
        double currentValue = positionAmt * currentPrice;
        
        // 计算持仓成本
        double costValue = positionAmt * avgPrice;
        
        // 计算盈亏
        double pnl;
        if ("LONG".equalsIgnoreCase(positionSide)) {
            // 多头：价格上涨盈利，价格下跌亏损
            pnl = currentValue - costValue;
        } else {
            // 空头：价格下跌盈利，价格上涨亏损
            pnl = costValue - currentValue;
        }
        
        // 计算损失百分比（相对于本金）
        // 损失百分比 = (亏损金额 / 初始保证金) * 100
        double lossPercent = (pnl / initialMargin) * 100.0;
        
        // 只返回负数（损失），如果是盈利则返回0
        return Math.max(0, -lossPercent);
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
                BinanceFuturesClient futuresClient = 
                        (BinanceFuturesClient) client;
                
                // 调用 getSymbolPrices 方法
                java.util.List<String> symbols = java.util.Collections.singletonList(symbol);
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
                                log.warn("[AutoClose] 价格格式错误: {}", priceObj);
                            }
                        }
                    }
                }
            }
            
            return null;
        } catch (Exception e) {
            log.error("[AutoClose] 获取 {} 当前价格失败: {}", symbol, e.getMessage());
            return null;
        }
    }
    
    /**
     * 执行平仓操作
     * 
     * 根据model的is_virtual字段判断使用测试接口或真实交易接口
     * 平仓成功后插入trades表记录（model_id、side=sell、signal=auto_close）
     * 
     * @param model 模型信息
     * @param symbol 交易对符号
     * @param positionSide 持仓方向
     * @param positionAmt 持仓数量
     * @param modelTradeMode 模型交易模式（'real'或'test'），根据is_virtual判断
     * @param avgPrice 持仓均价（用于计算盈亏）
     * @param currentPrice 当前价格（用于计算盈亏和test模式记录）
     * @param initialMargin 初始保证金（用于trades表）
     */
    private boolean executeClosePosition(ModelDO model, String symbol, String positionSide, Double positionAmt,
            String modelTradeMode, Double avgPrice, Double currentPrice, Double initialMargin) {
        log.info("[AutoClose] 🔧 进入executeClosePosition | modelId={}, symbol={}, positionSide={}, positionAmt={}, modelTradeMode={}",
                model.getId(), symbol, positionSide, positionAmt, modelTradeMode);

        try {
            // 先查询持仓获取portfolios_id和leverage（插入trades前需要，删除后无法获取）
            PortfolioDO portfolio = portfolioMapper.selectPosition(model.getId(), symbol.toUpperCase(), positionSide);
            String portfoliosId = portfolio != null ? portfolio.getId() : null;
            Integer leverage = (portfolio != null && portfolio.getLeverage() != null)
                    ? portfolio.getLeverage()
                    : (model.getLeverage() != null ? model.getLeverage() : 10);
            if (initialMargin == null && portfolio != null) {
                initialMargin = portfolio.getInitialMargin();
            }
            if (avgPrice == null && portfolio != null) {
                avgPrice = portfolio.getAvgPrice();
            }

            // 先取消已存在的条件单
            String formattedSymbol = symbol.toUpperCase();
            if (!formattedSymbol.endsWith(quoteAsset)) {
                formattedSymbol = formattedSymbol + quoteAsset;
            }
            log.info("[AutoClose] 🔄 准备取消条件单 | formattedSymbol={}, modelTradeMode={}", formattedSymbol, modelTradeMode);
            cancelExistingAlgoOrders(model, formattedSymbol, modelTradeMode);
            log.info("[AutoClose] ✅ 条件单取消完成（或无需取消）");

            BinanceFuturesOrderClient orderClient = getOrCreateOrderClient(model);
            if (orderClient == null) {
                log.error("[AutoClose] 无法创建 Binance 订单客户端");
                return false;
            }

            // 判断是否使用测试模式（使用模型自己的trade_mode，而不是全局配置）
            boolean useTestMode = "test".equalsIgnoreCase(modelTradeMode);

            // 平多仓: side=SELL, position_side=LONG；平空仓: side=BUY, position_side=SHORT
            String sdkSide = "LONG".equalsIgnoreCase(positionSide) ? "SELL" : "BUY";
            log.info("[AutoClose] 执行平仓: symbol={}, positionSide={}, side={}, quantity={}, 模式={}",
                    symbol, positionSide, sdkSide, positionAmt, useTestMode ? "测试" : "真实");

            // 使用 BinanceFuturesOrderClient 的 marketTrade 方法
            Map<String, Object> tradeResult = null;
            String errorMsg = null;
            try {
                tradeResult = orderClient.marketTrade(
                        symbol, sdkSide, positionAmt, positionSide, useTestMode);
            } catch (Exception sdkErr) {
                errorMsg = sdkErr.getMessage();
                log.error("[AutoClose] ❌ SDK平仓调用失败: {}", errorMsg, sdkErr);
            }

            if (tradeResult != null) {
                log.info("[AutoClose] ✅ 平仓订单提交成功: {}", tradeResult);

                // 插入trades表记录（与backend/async-service平仓逻辑一致：side=sell）
                // 优先使用cumQty（累计成交数量），其次使用executedQty
                Double executedQuantity = positionAmt;
                Double executedPrice = currentPrice;
                Long orderId = null;
                String quantitySource = "default";

                Object cumQtyObj = tradeResult.get("cumQty");
                Object executedQtyObj = tradeResult.get("executedQty");
                Object quantityObj = (cumQtyObj != null && !"".equals(cumQtyObj.toString())) ? cumQtyObj : executedQtyObj;

                if (quantityObj != null && !"".equals(quantityObj.toString())) {
                    try {
                        executedQuantity = Double.parseDouble(quantityObj.toString());
                        quantitySource = cumQtyObj != null ? "cumQty" : "executedQty";
                        log.debug("[AutoClose] 从SDK响应获取成交数量: {} (字段: {})", executedQuantity, quantitySource);
                    } catch (NumberFormatException ignored) {}
                }

                if (tradeResult.get("avgPrice") != null && !"".equals(tradeResult.get("avgPrice").toString())) {
                    try {
                        executedPrice = Double.parseDouble(tradeResult.get("avgPrice").toString());
                        log.debug("[AutoClose] 从SDK响应获取成交价格: {} (字段: avgPrice)", executedPrice);
                    } catch (NumberFormatException ignored) {}
                }

                if (tradeResult.get("orderId") != null) {
                    try {
                        orderId = Long.parseLong(tradeResult.get("orderId").toString());
                    } catch (NumberFormatException ignored) {}
                }

                double tradeAmount = executedQuantity * executedPrice;
                double tradeFee = tradeAmount * TRADE_FEE_RATE;
                double grossPnl;
                if ("LONG".equalsIgnoreCase(positionSide)) {
                    grossPnl = (executedPrice - (avgPrice != null ? avgPrice : 0)) * executedQuantity;
                } else {
                    grossPnl = ((avgPrice != null ? avgPrice : 0) - executedPrice) * executedQuantity;
                }
                double netPnl = grossPnl - tradeFee;

                TradeDO trade = new TradeDO();
                trade.setId(UUID.randomUUID().toString());
                trade.setModelId(model.getId());  // 写入对应 model_id
                trade.setFuture(symbol.toUpperCase());
                trade.setSignal("close_position");
                trade.setQuantity(executedQuantity);
                trade.setPrice(executedPrice);
                trade.setLeverage(leverage);
                trade.setSide("sell");  // 平仓操作固定为 sell
                trade.setPositionSide(positionSide);
                trade.setPnl(netPnl);
                trade.setFee(tradeFee);
                trade.setInitialMargin(initialMargin != null ? initialMargin : 0.0);
                trade.setPortfoliosId(portfoliosId);
                trade.setOrderId(orderId);
                trade.setTimestamp(LocalDateTime.now(ZoneId.of("Asia/Shanghai")));
                try {
                    tradeMapper.insert(trade);
                    log.info("[AutoClose] ✅ 已插入trades表记录: tradeId={}, modelId={}, symbol={}, quantity={}, price={}",
                            trade.getId(), model.getId(), symbol, executedQuantity, executedPrice);
                } catch (Exception dbErr) {
                    log.error("[AutoClose] ❌ 插入trades表失败: {}", dbErr.getMessage(), dbErr);
                    // 不返回 false，订单已成功
                }

                // 无论real还是test模式，SDK成功后都删除持仓记录（与Python代码逻辑一致）
                // test模式也需要删除持仓，以同步数据库状态
                try {
                    int deleted = portfolioMapper.deletePosition(model.getId(), symbol.toUpperCase(), positionSide);
                    if (deleted > 0) {
                        log.info("[AutoClose] ✅ 已删除持仓记录: modelId={}, symbol={}, positionSide={}, mode={}",
                                model.getId(), symbol, positionSide, useTestMode ? "test" : "real");
                    } else {
                        log.warn("[AutoClose] ⚠️  未找到要删除的持仓记录: modelId={}, symbol={}, positionSide={}",
                                model.getId(), symbol, positionSide);
                    }
                } catch (Exception dbErr) {
                    log.error("[AutoClose] ❌ 删除持仓记录失败: {}", dbErr.getMessage(), dbErr);
                    // 不返回 false，因为订单已经提交成功
                }

                return true;
            } else {
                if (!useTestMode) {
                    // real模式失败：写入trades表错误记录
                    String finalError = errorMsg != null ? errorMsg : "SDK返回为空";
                    TradeDO trade = new TradeDO();
                    trade.setId(UUID.randomUUID().toString());
                    trade.setModelId(model.getId());
                    trade.setFuture(symbol.toUpperCase());
                    trade.setSignal("close_position");
                    trade.setQuantity(0.0);
                    trade.setPrice(0.0);
                    trade.setLeverage(leverage);
                    trade.setSide("sell");
                    trade.setPositionSide(positionSide);
                    trade.setPnl(0.0);
                    trade.setFee(0.0);
                    trade.setInitialMargin(initialMargin != null ? initialMargin : 0.0);
                    trade.setPortfoliosId(portfoliosId);
                    trade.setError(finalError);
                    trade.setTimestamp(LocalDateTime.now(ZoneId.of("Asia/Shanghai")));
                    try {
                        tradeMapper.insert(trade);
                        log.info("[AutoClose] ✅ 已插入trades失败记录: tradeId={}, modelId={}, symbol={}, error={}",
                                trade.getId(), model.getId(), symbol, finalError);
                    } catch (Exception dbErr) {
                        log.error("[AutoClose] ❌ 插入trades失败记录失败: {}", dbErr.getMessage(), dbErr);
                    }
                }
                log.error("[AutoClose] ❌ 平仓订单提交失败: {}", errorMsg != null ? errorMsg : "响应为空");
                return false;
            }
            
        } catch (Exception e) {
            log.error("[AutoClose] ❌ 执行平仓操作失败: {}", e.getMessage(), e);
            return false;
        }
    }
    
    /**
     * 取消已存在的条件单（状态为new的订单）
     * 
     * @param model 模型信息
     * @param symbol 交易对符号（已格式化）
     * @param modelTradeMode 模型交易模式（'real'或'test'）
     */
    private void cancelExistingAlgoOrders(ModelDO model, String symbol, String modelTradeMode) {
        try {
            // 查询数据库中状态为new的条件单
            List<AlgoOrderDO> existingOrders = 
                    algoOrderMapper.selectNewAlgoOrdersByModelAndSymbol(model.getId(), symbol);
            
            if (existingOrders == null || existingOrders.isEmpty()) {
                log.debug("[AutoClose] 未找到需要取消的条件单 | model={} symbol={}", model.getId(), symbol);
                return;
            }
            
            log.info("[AutoClose] 找到 {} 个待取消的条件单 | model={} symbol={}", 
                    existingOrders.size(), model.getId(), symbol);
            
            boolean useRealMode = "real".equalsIgnoreCase(modelTradeMode);
            
            if (useRealMode && model.getApiKey() != null && model.getApiSecret() != null) {
                // real模式：先查询SDK，只有在SDK中查询到条件单时才执行取消操作
                try {
                    BinanceFuturesOrderClient orderClient = getOrCreateOrderClient(model);
                    if (orderClient == null) {
                        log.warn("[AutoClose] 无法创建Binance订单客户端，跳过取消条件单操作");
                        return;
                    }

                    // 查询SDK中的条件单
                    List<Map<String, Object>> sdkOrders = orderClient.queryAllAlgoOrders(
                            symbol, null, null, null, 0L, 100L, 5000L);

                    boolean hasSdkOrders = sdkOrders != null && !sdkOrders.isEmpty();

                    if (hasSdkOrders) {
                        // SDK中有条件单，执行取消操作
                        Map<String, Object> cancelResult = orderClient.cancelAllAlgoOpenOrders(symbol, 5000L);

                        if (cancelResult != null) {
                            log.info("[AutoClose] SDK取消条件单成功 | model={} symbol={} response={}",
                                    model.getId(), symbol, cancelResult);
                        } else {
                            log.info("[AutoClose] SDK取消条件单成功（无返回数据）| model={} symbol={}",
                                    model.getId(), symbol);
                        }

                        // SDK取消成功后，更新数据库状态
                        for (AlgoOrderDO order : existingOrders) {
                            algoOrderMapper.updateAlgoStatusToCancelled(order.getId());
                        }
                        log.info("[AutoClose] 已更新数据库条件单状态为cancelled | model={} symbol={} count={}",
                                model.getId(), symbol, existingOrders.size());
                    } else {
                        // SDK中未找到条件单，不执行取消操作
                        log.info("[AutoClose] SDK中未找到条件单，不执行取消操作 | model={} symbol={}",
                                model.getId(), symbol);
                        // 不更新数据库状态，直接继续后续流程
                    }
                } catch (Exception sdkErr) {
                    log.error("[AutoClose] real模式查询/取消条件单失败 | model={} symbol={} error={}",
                            model.getId(), symbol, sdkErr.getMessage(), sdkErr);
                    // real模式失败时不更新数据库，避免数据不一致
                }
            } else {
                // virtual模式：只有在数据库中查询到条件单时才更新状态
                for (AlgoOrderDO order : existingOrders) {
                    algoOrderMapper.updateAlgoStatusToCancelled(order.getId());
                }
                log.info("[AutoClose] virtual模式已更新条件单状态为cancelled | model={} symbol={} count={}", 
                        model.getId(), symbol, existingOrders.size());
            }
        } catch (Exception e) {
            log.error("[AutoClose] 取消条件单失败 | model={} symbol={} error={}", 
                    model.getId(), symbol, e.getMessage(), e);
            // 不抛出异常，避免影响主流程
        }
    }
    
    /**
     * 获取或创建 Binance 客户端（使用模型自己的 API Key）
     */
    private BinanceFuturesBase getOrCreateClient(ModelDO model) {
        if (model == null || model.getId() == null) {
            return null;
        }

        return modelClients.computeIfAbsent(model.getId(), modelId -> {
            try {
                String apiKey = model.getApiKey();
                String apiSecret = model.getApiSecret();

                if (apiKey == null || apiKey.isEmpty() || apiSecret == null || apiSecret.isEmpty()) {
                    log.warn("[AutoClose] ⚠️  模型 {} 未配置 API Key，使用默认配置", modelId);
                    apiKey = defaultApiKey;
                    apiSecret = defaultSecretKey;
                }

                // 创建客户端（使用 BinanceFuturesClient）
                BinanceFuturesClient client =
                        new BinanceFuturesClient(apiKey, apiSecret, quoteAsset, null, false);

                log.info("[AutoClose] ✅ 为模型 {} 创建 Binance 客户端", modelId);
                return client;

            } catch (Exception e) {
                log.error("[AutoClose] ❌ 为模型 {} 创建 Binance 客户端失败: {}", modelId, e.getMessage());
                return null;
            }
        });
    }

    /**
     * 获取或创建 Binance 订单客户端（使用模型自己的 API Key）
     */
    private BinanceFuturesOrderClient getOrCreateOrderClient(ModelDO model) {
        if (model == null || model.getId() == null) {
            return null;
        }

        return modelOrderClients.computeIfAbsent(model.getId(), modelId -> {
            try {
                String apiKey = model.getApiKey();
                String apiSecret = model.getApiSecret();

                if (apiKey == null || apiKey.isEmpty() || apiSecret == null || apiSecret.isEmpty()) {
                    log.warn("[AutoClose] ⚠️  模型 {} 未配置 API Key，使用默认配置", modelId);
                    apiKey = defaultApiKey;
                    apiSecret = defaultSecretKey;
                }

                // 创建订单客户端
                BinanceFuturesOrderClient orderClient =
                        new BinanceFuturesOrderClient(apiKey, apiSecret, quoteAsset, null, false);

                log.info("[AutoClose] ✅ 为模型 {} 创建 Binance 订单客户端", modelId);
                return orderClient;

            } catch (Exception e) {
                log.error("[AutoClose] ❌ 为模型 {} 创建 Binance 订单客户端失败: {}", modelId, e.getMessage());
                return null;
            }
        });
    }
}

