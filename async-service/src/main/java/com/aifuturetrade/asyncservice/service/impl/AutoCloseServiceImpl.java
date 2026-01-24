package com.aifuturetrade.asyncservice.service.impl;

import com.aifuturetrade.asyncservice.api.binance.BinanceFuturesBase;
import com.aifuturetrade.asyncservice.dao.mapper.ModelMapper;
import com.aifuturetrade.asyncservice.dao.mapper.PortfolioMapper;
import com.aifuturetrade.asyncservice.entity.ModelDO;
import com.aifuturetrade.asyncservice.entity.PortfolioWithModelInfo;
import com.aifuturetrade.asyncservice.service.AutoCloseResult;
import com.aifuturetrade.asyncservice.service.AutoCloseService;
import com.binance.connector.client.common.ApiResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.NewOrderRequest;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.NewOrderResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.TestOrderRequest;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.Side;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.PositionSide;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.util.List;
import java.util.Map;
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
    
    private final AtomicBoolean schedulerRunning = new AtomicBoolean(false);
    
    // 缓存每个模型的 Binance 客户端（使用模型自己的 API Key）
    private final Map<String, BinanceFuturesBase> modelClients = new ConcurrentHashMap<>();
    
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
                    
                    log.debug("[AutoClose] {} (模型: {}): 持仓价格={}, 当前价格={}, 损失百分比={:.2f}%, 阈值={:.2f}%", 
                            symbol, modelId, avgPrice, currentPrice, String.format("%.2f", lossPercent), String.format("%.2f", autoClosePercent));
                    
                    // 检查是否达到阈值
                    if (lossPercent >= autoClosePercent) {
                        log.warn("[AutoClose] 🚨 {} (模型: {}) 触发自动平仓: 损失 {:.2f}% >= 阈值 {:.2f}%", 
                                symbol, modelId, String.format("%.2f", lossPercent), String.format("%.2f", autoClosePercent));
                        
                        // 执行平仓（传递trade_mode）
                        boolean success = executeClosePosition(model, symbol, positionSide, positionAmt, modelTradeMode);
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
            if (client instanceof com.aifuturetrade.asyncservice.api.binance.BinanceFuturesClient) {
                com.aifuturetrade.asyncservice.api.binance.BinanceFuturesClient futuresClient = 
                        (com.aifuturetrade.asyncservice.api.binance.BinanceFuturesClient) client;
                
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
     * 
     * @param model 模型信息
     * @param symbol 交易对符号
     * @param positionSide 持仓方向
     * @param positionAmt 持仓数量
     * @param modelTradeMode 模型交易模式（'real'或'test'），根据is_virtual判断
     */
    private boolean executeClosePosition(ModelDO model, String symbol, String positionSide, Double positionAmt, String modelTradeMode) {
        try {
            BinanceFuturesBase client = getOrCreateClient(model);
            if (client == null) {
                log.error("[AutoClose] 无法创建 Binance 客户端");
                return false;
            }
            
            // 判断是否使用测试模式（使用模型自己的trade_mode，而不是全局配置）
            boolean useTestMode = "test".equalsIgnoreCase(modelTradeMode);
            
            if (useTestMode) {
                // 使用测试接口（不会真实成交）
                log.info("[AutoClose] 使用测试接口执行平仓（不会真实成交）: symbol={}, positionSide={}, quantity={}", 
                        symbol, positionSide, positionAmt);
                
                // 构建测试订单请求
                TestOrderRequest testRequest = new TestOrderRequest();
                testRequest.setSymbol(symbol.toUpperCase());
                testRequest.setSide(Side.SELL); // 平仓统一使用 SELL
                testRequest.setType("MARKET");
                testRequest.setQuantity(positionAmt);
                
                // 设置持仓方向
                if ("LONG".equalsIgnoreCase(positionSide)) {
                    testRequest.setPositionSide(PositionSide.LONG);
                } else if ("SHORT".equalsIgnoreCase(positionSide)) {
                    testRequest.setPositionSide(PositionSide.SHORT);
                }
                
                // 调用测试订单接口
                ApiResponse<?> response = client.getRestApi().testOrder(testRequest);
                
                if (response != null) {
                    log.info("[AutoClose] ✅ 测试平仓订单提交成功（未真实成交）: {}", response.getData());
                    
                    // 测试模式下不更新数据库，因为不是真实交易
                    log.info("[AutoClose] ℹ️  测试模式：跳过数据库更新（非真实交易）");
                    
                    return true;
                } else {
                    log.error("[AutoClose] ❌ 测试平仓订单提交失败: 响应为空");
                    return false;
                }
            } else {
                // 使用真实交易接口
                log.info("[AutoClose] 使用真实交易接口执行平仓: symbol={}, positionSide={}, quantity={}", 
                        symbol, positionSide, positionAmt);
                
                // 构建平仓订单
                NewOrderRequest orderRequest = new NewOrderRequest();
                orderRequest.setSymbol(symbol.toUpperCase());
                orderRequest.setSide(Side.SELL); // 平仓统一使用 SELL
                orderRequest.setType("MARKET");
                // quantity 需要是 Double 类型
                orderRequest.setQuantity(positionAmt);
                
                // 设置持仓方向
                if ("LONG".equalsIgnoreCase(positionSide)) {
                    orderRequest.setPositionSide(PositionSide.LONG);
                } else if ("SHORT".equalsIgnoreCase(positionSide)) {
                    orderRequest.setPositionSide(PositionSide.SHORT);
                }
                
                // 执行订单
                ApiResponse<NewOrderResponse> response = client.getRestApi().newOrder(orderRequest);
                
                if (response != null && response.getData() != null) {
                    log.info("[AutoClose] ✅ 平仓订单提交成功: {}", response.getData());
                    
                    // 更新 portfolios 表：删除持仓记录
                    try {
                        int deleted = portfolioMapper.deletePosition(model.getId(), symbol.toUpperCase(), positionSide);
                        if (deleted > 0) {
                            log.info("[AutoClose] ✅ 已更新 portfolios 表，删除持仓记录: modelId={}, symbol={}, positionSide={}", 
                                    model.getId(), symbol, positionSide);
                        } else {
                            log.warn("[AutoClose] ⚠️  未找到要删除的持仓记录: modelId={}, symbol={}, positionSide={}", 
                                    model.getId(), symbol, positionSide);
                        }
                    } catch (Exception dbErr) {
                        log.error("[AutoClose] ❌ 更新 portfolios 表失败: {}", dbErr.getMessage(), dbErr);
                        // 不返回 false，因为订单已经提交成功
                    }
                    
                    return true;
                } else {
                    log.error("[AutoClose] ❌ 平仓订单提交失败: 响应为空");
                    return false;
                }
            }
            
        } catch (Exception e) {
            log.error("[AutoClose] ❌ 执行平仓操作失败: {}", e.getMessage(), e);
            return false;
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
                com.aifuturetrade.asyncservice.api.binance.BinanceFuturesClient client = 
                        new com.aifuturetrade.asyncservice.api.binance.BinanceFuturesClient(
                                apiKey, apiSecret, quoteAsset, null, false);
                
                log.info("[AutoClose] ✅ 为模型 {} 创建 Binance 客户端", modelId);
                return client;
                
            } catch (Exception e) {
                log.error("[AutoClose] ❌ 为模型 {} 创建 Binance 客户端失败: {}", modelId, e.getMessage());
                return null;
            }
        });
    }
}

