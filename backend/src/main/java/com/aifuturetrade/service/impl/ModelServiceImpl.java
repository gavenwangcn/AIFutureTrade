package com.aifuturetrade.service.impl;

import com.aifuturetrade.dao.entity.*;
import com.aifuturetrade.dao.mapper.*;
import com.aifuturetrade.service.ModelService;
import com.aifuturetrade.service.MarketService;
import com.aifuturetrade.service.dto.ModelDTO;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.common.util.PageRequest;
import com.aifuturetrade.common.api.trade.TradeServiceClient;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.UpdateWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.BeanUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * 业务逻辑实现类：交易模型
 * 实现交易模型的业务逻辑
 */
@Slf4j
@Service
public class ModelServiceImpl implements ModelService {

    @Autowired
    private ModelMapper modelMapper;

    @Autowired
    private TradeMapper tradeMapper;

    @Autowired
    private ConversationMapper conversationMapper;

    @Autowired
    private PortfolioMapper portfolioMapper;

    @Autowired
    private ModelPromptMapper modelPromptMapper;

    @Autowired
    private ModelStrategyMapper modelStrategyMapper;

    @Autowired
    private AccountValueHistoryMapper accountValueHistoryMapper;

    @Autowired
    private AccountValuesMapper accountValuesMapper;

    @Autowired
    private MarketService marketService;

    @Autowired
    private ProviderMapper providerMapper;

    @Autowired
    private FutureMapper futureMapper;

    @Autowired
    private AccountAssetMapper accountAssetMapper;
    
    @Autowired
    private com.aifuturetrade.service.DockerContainerService dockerContainerService;
    
    @Value("${docker.image.buy:aifuturetrade-model-buy}")
    private String modelBuyImageName;
    
    @Value("${docker.image.sell:aifuturetrade-model-sell}")
    private String modelSellImageName;
    
    @Value("${mysql.host:154.89.148.172}")
    private String mysqlHost;
    
    @Value("${mysql.port:32123}")
    private String mysqlPort;
    
    @Value("${mysql.user:aifuturetrade}")
    private String mysqlUser;
    
    @Value("${mysql.password:aifuturetrade123}")
    private String mysqlPassword;
    
    @Value("${mysql.database:aifuturetrade}")
    private String mysqlDatabase;
    
    @Value("${binance.api.key:}")
    private String binanceApiKey;
    
    @Value("${binance.api.secret:}")
    private String binanceApiSecret;

    @Autowired
    private MarketTickerMapper marketTickerMapper;

    @Autowired
    private BinanceTradeLogMapper binanceTradeLogMapper;

    @Autowired
    private StrategyDecisionMapper strategyDecisionMapper;

    @Autowired
    private com.aifuturetrade.common.api.binance.BinanceConfig binanceConfig;

    @Value("${app.trades-query-limit:10}")
    private Integer defaultTradesQueryLimit;
    
    private com.aifuturetrade.common.api.binance.BinanceFuturesClient binanceFuturesClient;
    
    private com.aifuturetrade.common.api.binance.BinanceFuturesClient getBinanceFuturesClient() {
        if (binanceFuturesClient == null) {
            binanceFuturesClient = new com.aifuturetrade.common.api.binance.BinanceFuturesClient(
                    binanceConfig.getApiKey(),
                    binanceConfig.getSecretKey(),
                    binanceConfig.getQuoteAsset(),
                    binanceConfig.getBaseUrl(),
                    binanceConfig.getTestnet()
            );
        }
        return binanceFuturesClient;
    }

    private static final DateTimeFormatter DATETIME_FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    
    /**
     * 获取配置的合约symbol列表
     */
    private List<String> getTrackedSymbols() {
        List<com.aifuturetrade.dao.entity.FutureDO> futures = futureMapper.selectList(null);
        return futures.stream()
                .map(f -> f.getSymbol() != null ? f.getSymbol().toUpperCase() : "")
                .filter(s -> !s.isEmpty())
                .distinct()
                .collect(Collectors.toList());
    }

    @Override
    public List<ModelDTO> getAllModels() {
        List<ModelDO> modelDOList = modelMapper.selectAllModels();
        return modelDOList.stream()
                .map(this::convertToDTO)
                .collect(Collectors.toList());
    }

    @Override
    public ModelDTO getModelById(String id) {
        ModelDO modelDO = modelMapper.selectModelById(id);
        return modelDO != null ? convertToDTO(modelDO) : null;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public ModelDTO addModel(ModelDTO modelDTO) {
        ModelDO modelDO = convertToDO(modelDTO);
        modelDO.setCreatedAt(LocalDateTime.now());
        modelDO.setUpdatedAt(LocalDateTime.now());
        
        // 新建模型时，auto_buy_enabled和auto_sell_enabled默认为false（0）
        if (modelDO.getAutoBuyEnabled() == null) {
            modelDO.setAutoBuyEnabled(false);
        }
        if (modelDO.getAutoSellEnabled() == null) {
            modelDO.setAutoSellEnabled(false);
        }
        
        // 验证provider_id：必须由前端传入，不能为空
        if (modelDO.getProviderId() == null || modelDO.getProviderId().trim().isEmpty()) {
            log.error("[ModelService] provider_id不能为空，必须由前端传入");
            throw new IllegalArgumentException("provider_id不能为空，请在前端页面选择API提供方");
        }
        
        // 如果提供了accountAlias，从account_asset表中获取api_key和api_secret
        if (modelDO.getAccountAlias() != null && !modelDO.getAccountAlias().trim().isEmpty()) {
            try {
                AccountAssetDO accountAsset = accountAssetMapper.selectById(modelDO.getAccountAlias());
                if (accountAsset != null) {
                    // 从account_asset表中获取api_key和api_secret
                    if (accountAsset.getApiKey() != null && !accountAsset.getApiKey().trim().isEmpty()) {
                        modelDO.setApiKey(accountAsset.getApiKey());
                        log.debug("[ModelService] 从account_asset表获取api_key成功, accountAlias={}", modelDO.getAccountAlias());
                    }
                    if (accountAsset.getApiSecret() != null && !accountAsset.getApiSecret().trim().isEmpty()) {
                        modelDO.setApiSecret(accountAsset.getApiSecret());
                        log.debug("[ModelService] 从account_asset表获取api_secret成功, accountAlias={}", modelDO.getAccountAlias());
                    }
                } else {
                    log.warn("[ModelService] 未找到account_alias对应的账户信息, accountAlias={}", modelDO.getAccountAlias());
                }
            } catch (Exception e) {
                log.error("[ModelService] 从account_asset表获取api_key和api_secret失败, accountAlias={}, error={}", 
                        modelDO.getAccountAlias(), e.getMessage(), e);
                // 不抛出异常，允许模型创建继续，但记录警告
            }
        }
        
        // 设置默认trade_type为'strategy'（如果未提供）
        if (modelDO.getTradeType() == null || modelDO.getTradeType().trim().isEmpty()) {
            modelDO.setTradeType("strategy");
        } else {
            // 验证trade_type值
            String tradeType = modelDO.getTradeType().toLowerCase();
            if (!tradeType.equals("ai") && !tradeType.equals("strategy")) {
                log.warn("[ModelService] Invalid trade_type '{}', defaulting to 'strategy'", modelDO.getTradeType());
                modelDO.setTradeType("strategy");
            } else {
                modelDO.setTradeType(tradeType);
            }
        }
        modelMapper.insert(modelDO);
        
        // 初始化account_values表数据
        try {
            AccountValuesDO accountValues = new AccountValuesDO();
            accountValues.setId(UUID.randomUUID().toString());
            accountValues.setModelId(modelDO.getId());
            accountValues.setAccountAlias(modelDO.getAccountAlias() != null ? modelDO.getAccountAlias() : "");
            Double initialCapital = modelDO.getInitialCapital() != null ? modelDO.getInitialCapital() : 10000.0;
            accountValues.setBalance(initialCapital);
            accountValues.setAvailableBalance(initialCapital);
            accountValues.setCrossWalletBalance(initialCapital);
            accountValues.setCrossUnPnl(0.0);
            accountValues.setTimestamp(LocalDateTime.now());
            accountValuesMapper.insert(accountValues);
            log.debug("[ModelService] 初始化account_values数据成功, modelId={}, initialCapital={}", modelDO.getId(), initialCapital);
        } catch (Exception e) {
            log.error("[ModelService] 初始化account_values数据失败: {}", e.getMessage(), e);
            // 不抛出异常，允许模型创建继续
        }
        
        return convertToDTO(modelDO);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public ModelDTO updateModel(ModelDTO modelDTO) {
        ModelDO modelDO = convertToDO(modelDTO);
        modelDO.setUpdatedAt(LocalDateTime.now());
        
        // 如果提供了accountAlias，从account_asset表中获取api_key和api_secret
        if (modelDO.getAccountAlias() != null && !modelDO.getAccountAlias().trim().isEmpty()) {
            try {
                AccountAssetDO accountAsset = accountAssetMapper.selectById(modelDO.getAccountAlias());
                if (accountAsset != null) {
                    // 从account_asset表中获取api_key和api_secret
                    if (accountAsset.getApiKey() != null && !accountAsset.getApiKey().trim().isEmpty()) {
                        modelDO.setApiKey(accountAsset.getApiKey());
                        log.debug("[ModelService] 更新模型时从account_asset表获取api_key成功, accountAlias={}", modelDO.getAccountAlias());
                    }
                    if (accountAsset.getApiSecret() != null && !accountAsset.getApiSecret().trim().isEmpty()) {
                        modelDO.setApiSecret(accountAsset.getApiSecret());
                        log.debug("[ModelService] 更新模型时从account_asset表获取api_secret成功, accountAlias={}", modelDO.getAccountAlias());
                    }
                } else {
                    log.warn("[ModelService] 更新模型时未找到account_alias对应的账户信息, accountAlias={}", modelDO.getAccountAlias());
                }
            } catch (Exception e) {
                log.error("[ModelService] 更新模型时从account_asset表获取api_key和api_secret失败, accountAlias={}, error={}", 
                        modelDO.getAccountAlias(), e.getMessage(), e);
                // 不抛出异常，允许模型更新继续，但记录警告
            }
        }
        
        // 验证trade_type值（如果提供）
        if (modelDO.getTradeType() != null && !modelDO.getTradeType().trim().isEmpty()) {
            String tradeType = modelDO.getTradeType().toLowerCase();
            if (!tradeType.equals("ai") && !tradeType.equals("strategy")) {
                log.warn("[ModelService] Invalid trade_type '{}', keeping existing value", modelDO.getTradeType());
                // 如果值无效，从数据库获取现有值
                ModelDO existingModel = modelMapper.selectModelById(modelDO.getId());
                if (existingModel != null && existingModel.getTradeType() != null) {
                    modelDO.setTradeType(existingModel.getTradeType());
                } else {
                    modelDO.setTradeType("strategy");
                }
            } else {
                modelDO.setTradeType(tradeType);
            }
        }
        modelMapper.updateById(modelDO);
        return convertToDTO(modelDO);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Boolean deleteModel(String id) {
        log.debug("[ModelService] 开始删除模型及其关联数据, modelId: {}", id);
        
        // 0. 先删除相关的 Docker 容器（buy-{modelId} 和 sell-{modelId}）
        try {
            String buyContainerName = "buy-" + id;
            String sellContainerName = "sell-" + id;
            
            log.info("[ModelService] 开始删除模型相关的 Docker 容器: {} 和 {}", buyContainerName, sellContainerName);
            
            // 删除 buy 容器
            boolean buyContainerRemoved = dockerContainerService.removeContainer(buyContainerName);
            if (buyContainerRemoved) {
                log.info("[ModelService] 成功删除 buy 容器: {}", buyContainerName);
            } else {
                log.warn("[ModelService] 删除 buy 容器失败或容器不存在: {}", buyContainerName);
            }
            
            // 删除 sell 容器
            boolean sellContainerRemoved = dockerContainerService.removeContainer(sellContainerName);
            if (sellContainerRemoved) {
                log.info("[ModelService] 成功删除 sell 容器: {}", sellContainerName);
            } else {
                log.warn("[ModelService] 删除 sell 容器失败或容器不存在: {}", sellContainerName);
            }
        } catch (Exception e) {
            // 容器删除失败不应该阻止模型删除，只记录警告
            log.warn("[ModelService] 删除模型相关的 Docker 容器时出错，但继续删除模型数据: {}", e.getMessage(), e);
        }
        
        // 按顺序删除所有关联表的数据
        // 1. 删除账户价值历史记录
        try {
            int count = accountValueHistoryMapper.deleteByModelId(id);
            log.debug("[ModelService] Deleted {} account_value_historys records for model: {}", count, id);
        } catch (Exception e) {
            log.warn("[ModelService] Failed to delete account_value_historys for model {}: {}", id, e.getMessage());
        }
        
        // 2. 删除账户价值记录
        try {
            int count = accountValuesMapper.deleteByModelId(id);
            log.debug("[ModelService] Deleted {} account_values records for model: {}", count, id);
        } catch (Exception e) {
            log.warn("[ModelService] Failed to delete account_values for model {}: {}", id, e.getMessage());
        }
        
        // 3. 删除币安交易日志
        try {
            int count = binanceTradeLogMapper.deleteByModelId(id);
            log.debug("[ModelService] Deleted {} binance_trade_logs records for model: {}", count, id);
        } catch (Exception e) {
            log.warn("[ModelService] Failed to delete binance_trade_logs for model {}: {}", id, e.getMessage());
        }
        
        // 4. 删除对话记录
        try {
            int count = conversationMapper.deleteByModelId(id);
            log.debug("[ModelService] Deleted {} conversations records for model: {}", count, id);
        } catch (Exception e) {
            log.warn("[ModelService] Failed to delete conversations for model {}: {}", id, e.getMessage());
        }
        
        // 5. 删除模型提示词配置
        try {
            int count = modelPromptMapper.deleteByModelId(id);
            log.debug("[ModelService] Deleted {} model_prompts records for model: {}", count, id);
        } catch (Exception e) {
            log.warn("[ModelService] Failed to delete model_prompts for model {}: {}", id, e.getMessage());
        }
        
        // 6. 删除模型策略关联
        try {
            int count = modelStrategyMapper.deleteByModelId(id);
            log.debug("[ModelService] Deleted {} model_strategy records for model: {}", count, id);
        } catch (Exception e) {
            log.warn("[ModelService] Failed to delete model_strategy for model {}: {}", id, e.getMessage());
        }
        
        // 7. 删除持仓记录
        try {
            int count = portfolioMapper.deleteByModelId(id);
            log.debug("[ModelService] Deleted {} portfolios records for model: {}", count, id);
        } catch (Exception e) {
            log.warn("[ModelService] Failed to delete portfolios for model {}: {}", id, e.getMessage());
        }
        
        // 8. 删除交易记录
        try {
            int count = tradeMapper.deleteByModelId(id);
            log.debug("[ModelService] Deleted {} trades records for model: {}", count, id);
        } catch (Exception e) {
            log.warn("[ModelService] Failed to delete trades for model {}: {}", id, e.getMessage());
        }
        
        // 9. 删除策略决策记录
        try {
            int count = strategyDecisionMapper.deleteByModelId(id);
            log.debug("[ModelService] Deleted {} strategy_decisions records for model: {}", count, id);
        } catch (Exception e) {
            log.warn("[ModelService] Failed to delete strategy_decisions for model {}: {}", id, e.getMessage());
        }
        
        // 最后删除model记录本身
        int result = modelMapper.deleteById(id);
        if (result > 0) {
            log.debug("[ModelService] Successfully deleted model: {}", id);
        } else {
            log.warn("[ModelService] Failed to delete model record: {}", id);
        }
        
        return result > 0;
    }

    @Override
    public PageResult<ModelDTO> getModelsByPage(PageRequest pageRequest) {
        Page<ModelDO> page = new Page<>(pageRequest.getPageNum(), pageRequest.getPageSize());
        Page<ModelDO> modelDOPage = modelMapper.selectPage(page, null);
        List<ModelDTO> modelDTOList = modelDOPage.getRecords().stream()
                .map(this::convertToDTO)
                .collect(Collectors.toList());
        return PageResult.build(modelDTOList, modelDOPage.getTotal(), pageRequest.getPageNum(), pageRequest.getPageSize());
    }

    @Override
    public Boolean isModelAutoBuyEnabled(String modelId) {
        return modelMapper.isModelAutoBuyEnabled(modelId);
    }

    @Override
    public Boolean isModelAutoSellEnabled(String modelId) {
        return modelMapper.isModelAutoSellEnabled(modelId);
    }

    @Override
    public Map<String, Object> getPortfolio(String modelId) {
        log.debug("[ModelService] 获取投资组合数据, modelId={}", modelId);
        try {
            ModelDO model = modelMapper.selectModelById(modelId);
            if (model == null) {
                throw new RuntimeException("Model not found");
            }
            
            // 获取持仓数据
            QueryWrapper<PortfolioDO> portfolioQuery = new QueryWrapper<>();
            portfolioQuery.eq("model_id", modelId);
            portfolioQuery.ne("position_amt", 0);
            List<PortfolioDO> portfolioDOList = portfolioMapper.selectList(portfolioQuery);
            
            List<Map<String, Object>> positions = new ArrayList<>();
            List<String> heldSymbols = new ArrayList<>();
            
            log.debug("[ModelService] 查询到持仓记录数: {}", portfolioDOList.size());
            for (PortfolioDO portfolioDO : portfolioDOList) {
                log.debug("[ModelService] 处理持仓记录: symbol={}, positionAmt={}, avgPrice={}, positionSide={}, leverage={}, unrealizedProfit={}",
                        portfolioDO.getSymbol(), portfolioDO.getPositionAmt(), portfolioDO.getAvgPrice(),
                        portfolioDO.getPositionSide(), portfolioDO.getLeverage(), portfolioDO.getUnrealizedProfit());
                
                Map<String, Object> position = new HashMap<>();
                position.put("symbol", portfolioDO.getSymbol());
                // 同时支持驼峰和下划线命名，确保前端兼容
                position.put("positionSide", portfolioDO.getPositionSide());
                position.put("position_side", portfolioDO.getPositionSide());
                position.put("positionAmt", portfolioDO.getPositionAmt());
                position.put("position_amt", portfolioDO.getPositionAmt());
                position.put("avgPrice", portfolioDO.getAvgPrice());
                position.put("avg_price", portfolioDO.getAvgPrice());
                position.put("leverage", portfolioDO.getLeverage());
                position.put("unrealizedProfit", portfolioDO.getUnrealizedProfit());
                position.put("unrealized_profit", portfolioDO.getUnrealizedProfit());
                positions.add(position);
                
                if (portfolioDO.getSymbol() != null) {
                    heldSymbols.add(portfolioDO.getSymbol().toUpperCase());
                }
            }
            log.debug("[ModelService] 构建持仓列表完成，共 {} 条记录", positions.size());
            
            // 如果持仓为空，使用配置的合约列表作为备选
            if (heldSymbols.isEmpty()) {
                heldSymbols = getTrackedSymbols();
            } else {
                // 合并持仓symbol和配置的symbol，确保都能获取价格
                List<String> configuredSymbols = getTrackedSymbols();
                heldSymbols = new ArrayList<>(heldSymbols);
                heldSymbols.addAll(configuredSymbols);
                heldSymbols = heldSymbols.stream().distinct().collect(Collectors.toList());
            }
            
            // 获取实时价格数据（优先从SDK API获取，确保实时性）
            log.debug("[ModelService] 开始获取实时价格数据，持仓symbol列表: {}", heldSymbols);
            Map<String, Double> currentPrices = new HashMap<>();
            
            if (!heldSymbols.isEmpty()) {
                try {
                    // 构建contract_symbol列表（确保所有symbol都以USDT结尾）
                    List<String> contractSymbols = new ArrayList<>();
                    Map<String, String> symbolToContract = new HashMap<>();
                    for (String symbol : heldSymbols) {
                        String upperSymbol = symbol.toUpperCase();
                        String contractSymbol = upperSymbol;
                        // 如果symbol不带USDT，添加USDT后缀
                        if (!contractSymbol.endsWith("USDT")) {
                            contractSymbol = upperSymbol + "USDT";
                        }
                        contractSymbols.add(contractSymbol);
                        symbolToContract.put(upperSymbol, contractSymbol);
                        // 同时支持带USDT和不带USDT的映射
                        if (!upperSymbol.equals(contractSymbol)) {
                            symbolToContract.put(contractSymbol, contractSymbol);
                        }
                    }
                    
                    // 直接调用SDK获取实时价格
                    log.debug("[ModelService] 从SDK API获取实时价格，contractSymbols: {}", contractSymbols);
                    com.aifuturetrade.common.api.binance.BinanceFuturesClient binanceClient = getBinanceFuturesClient();
                    Map<String, Map<String, Object>> sdkPrices = binanceClient.getSymbolPrices(contractSymbols);
                    log.debug("[ModelService] SDK返回价格数据数量: {}", sdkPrices.size());
                    
                    // 处理SDK返回的价格数据，支持多种symbol格式匹配
                    for (Map.Entry<String, Map<String, Object>> entry : sdkPrices.entrySet()) {
                        String contractSymbol = entry.getKey().toUpperCase();
                        Map<String, Object> priceInfo = entry.getValue();
                        Object priceObj = priceInfo.get("price");
                        if (priceObj != null) {
                            Double priceValue = convertToDouble(priceObj);
                            if (priceValue != null && priceValue > 0) {
                                // 同时支持带USDT和不带USDT的symbol格式
                                currentPrices.put(contractSymbol, priceValue);
                                // 如果contractSymbol带USDT，也添加不带USDT的版本
                                if (contractSymbol.endsWith("USDT")) {
                                    String symbolWithoutUSDT = contractSymbol.substring(0, contractSymbol.length() - 4);
                                    currentPrices.put(symbolWithoutUSDT, priceValue);
                                }
                                log.debug("[ModelService] 从SDK获取到价格: {} = {}", contractSymbol, priceValue);
                            }
                        }
                    }
                    
                    // 如果SDK获取失败或数据不完整，回退到marketService
                    if (currentPrices.isEmpty() || currentPrices.size() < heldSymbols.size()) {
                        log.warn("[ModelService] SDK获取价格不完整，回退到marketService获取价格");
                        Map<String, Map<String, Object>> pricesData = marketService.getMarketPrices();
                        for (Map.Entry<String, Map<String, Object>> entry : pricesData.entrySet()) {
                            Object priceObj = entry.getValue().get("price");
                            if (priceObj != null) {
                                Double priceValue = convertToDouble(priceObj);
                                if (priceValue != null && priceValue > 0) {
                                    String symbol = entry.getKey().toUpperCase();
                                    if (!currentPrices.containsKey(symbol)) {
                                        currentPrices.put(symbol, priceValue);
                                        // 同时支持带USDT和不带USDT的格式
                                        if (symbol.endsWith("USDT")) {
                                            String symbolWithoutUSDT = symbol.substring(0, symbol.length() - 4);
                                            currentPrices.put(symbolWithoutUSDT, priceValue);
                                        } else {
                                            currentPrices.put(symbol + "USDT", priceValue);
                                        }
                                    }
                                }
                            }
                        }
                    }
                } catch (Exception e) {
                    log.error("[ModelService] 从SDK获取实时价格失败，回退到marketService: {}", e.getMessage(), e);
                    // 回退到marketService
                    Map<String, Map<String, Object>> pricesData = marketService.getMarketPrices();
                    for (Map.Entry<String, Map<String, Object>> entry : pricesData.entrySet()) {
                        Object priceObj = entry.getValue().get("price");
                        if (priceObj != null) {
                            Double priceValue = convertToDouble(priceObj);
                            if (priceValue != null && priceValue > 0) {
                                String symbol = entry.getKey().toUpperCase();
                                currentPrices.put(symbol, priceValue);
                                // 同时支持带USDT和不带USDT的格式
                                if (symbol.endsWith("USDT")) {
                                    String symbolWithoutUSDT = symbol.substring(0, symbol.length() - 4);
                                    currentPrices.put(symbolWithoutUSDT, priceValue);
                                } else {
                                    currentPrices.put(symbol + "USDT", priceValue);
                                }
                            }
                        }
                    }
                }
            }
            
            log.debug("[ModelService] 获取实时价格完成，共 {} 个价格数据: {}", currentPrices.size(), currentPrices.keySet());
            
            // 计算已实现盈亏（从交易记录中汇总）
            QueryWrapper<TradeDO> tradeQuery = new QueryWrapper<>();
            tradeQuery.eq("model_id", modelId);
            List<TradeDO> allTrades = tradeMapper.selectList(tradeQuery);
            Double realizedPnl = allTrades.stream()
                    .filter(t -> t.getPnl() != null)
                    .mapToDouble(TradeDO::getPnl)
                    .sum();
            
            // 计算未实现盈亏和更新持仓信息
            Double unrealizedPnl = 0.0;
            Double marginUsed = 0.0;
            Double positionsValue = 0.0;
            
            // 创建symbol到PortfolioDO的映射
            Map<String, PortfolioDO> symbolToPortfolio = new HashMap<>();
            for (PortfolioDO pdo : portfolioDOList) {
                if (pdo.getSymbol() != null) {
                    symbolToPortfolio.put(pdo.getSymbol().toUpperCase(), pdo);
                }
            }
            
            log.debug("[ModelService] 开始计算持仓盈亏和更新价格信息，持仓数: {}", positions.size());
            for (Map<String, Object> pos : positions) {
                String symbol = (String) pos.get("symbol");
                // 支持两种字段名
                Double avgPrice = convertToDouble(pos.get("avgPrice"));
                if (avgPrice == null) avgPrice = convertToDouble(pos.get("avg_price"));
                Double positionAmt = convertToDouble(pos.get("positionAmt"));
                if (positionAmt == null) positionAmt = convertToDouble(pos.get("position_amt"));
                positionAmt = Math.abs(positionAmt != null ? positionAmt : 0.0);
                if (avgPrice == null) avgPrice = 0.0;
                String positionSide = (String) pos.get("positionSide");
                if (positionSide == null) positionSide = (String) pos.get("position_side");
                Integer leverage = (Integer) pos.get("leverage");
                
                log.debug("[ModelService] 处理持仓: symbol={}, positionAmt={}, avgPrice={}, positionSide={}, leverage={}",
                        symbol, positionAmt, avgPrice, positionSide, leverage);
                
                PortfolioDO portfolioDO = symbolToPortfolio.get(symbol != null ? symbol.toUpperCase() : "");
                
                // 获取当前价格（尝试多种可能的symbol格式，支持带/不带USDT后缀）
                Double currentPrice = null;
                if (symbol != null) {
                    String upperSymbol = symbol.toUpperCase();
                    // 尝试多种格式匹配
                    currentPrice = currentPrices.get(upperSymbol);
                    if (currentPrice == null) {
                        // 如果symbol不带USDT，尝试添加USDT后缀
                        if (!upperSymbol.endsWith("USDT")) {
                            currentPrice = currentPrices.get(upperSymbol + "USDT");
                        } else {
                            // 如果symbol带USDT，尝试去掉USDT后缀
                            String symbolWithoutUSDT = upperSymbol.substring(0, upperSymbol.length() - 4);
                            currentPrice = currentPrices.get(symbolWithoutUSDT);
                        }
                    }
                }
                
                log.debug("[ModelService] 持仓 {} 的当前价格: {}", symbol, currentPrice);
                
                if (currentPrice != null && currentPrice > 0) {
                    // 同时设置两种字段名
                    pos.put("currentPrice", currentPrice);
                    pos.put("current_price", currentPrice);
                    
                    // 使用实时价格计算未实现盈亏（覆盖数据库中的值，确保实时性）
                    Double posPnl;
                    if ("LONG".equals(positionSide)) {
                        posPnl = (currentPrice - avgPrice) * positionAmt;
                    } else {
                        posPnl = (avgPrice - currentPrice) * positionAmt;
                    }
                    pos.put("pnl", posPnl);
                    unrealizedPnl += posPnl;
                    log.debug("[ModelService] 持仓 {} {} 计算未实现盈亏: {} (当前价={}, 开仓价={}, 数量={})",
                            symbol, positionSide, posPnl, currentPrice, avgPrice, positionAmt);
                } else {
                    // 没有实时价格，使用数据库中的unrealized_profit字段
                    pos.put("currentPrice", 0.0);
                    pos.put("current_price", 0.0);
                    Double storedPnl = (portfolioDO != null && portfolioDO.getUnrealizedProfit() != null) ? portfolioDO.getUnrealizedProfit() : 0.0;
                    pos.put("pnl", storedPnl);
                    unrealizedPnl += storedPnl;
                    log.warn("[ModelService] 持仓 {} 未获取到实时价格，使用存储的盈亏: {}", symbol, storedPnl);
                }
                
                // 计算已用保证金
                if (leverage != null && leverage > 0) {
                    marginUsed += (positionAmt * avgPrice) / leverage;
                }
                
                // 计算持仓价值
                positionsValue += positionAmt * avgPrice;
                
                log.debug("[ModelService] 持仓 {} 最终数据: positionAmt={}, avgPrice={}, currentPrice={}, pnl={}",
                        symbol, pos.get("position_amt"), pos.get("avg_price"), pos.get("current_price"), pos.get("pnl"));
            }
            log.debug("[ModelService] 持仓计算完成: 未实现盈亏={}, 已用保证金={}, 持仓价值={}", unrealizedPnl, marginUsed, positionsValue);
            
            Double initialCapital = model.getInitialCapital() != null ? model.getInitialCapital() : 10000.0;
            Double cash = initialCapital + realizedPnl - marginUsed;
            Double totalValue = initialCapital + realizedPnl + unrealizedPnl;
            
            Map<String, Object> portfolio = new LinkedHashMap<>();
            portfolio.put("model_id", modelId);
            portfolio.put("initial_capital", initialCapital);
            portfolio.put("cash", cash);
            portfolio.put("available_cash", cash);  // 兼容字段名
            portfolio.put("positions", positions);
            portfolio.put("positions_value", positionsValue);
            portfolio.put("margin_used", marginUsed);
            portfolio.put("total_value", totalValue);
            portfolio.put("realized_pnl", realizedPnl);
            portfolio.put("unrealized_pnl", unrealizedPnl);
            
            // 获取账户价值历史
            List<Map<String, Object>> accountValueHistory = accountValueHistoryMapper.selectHistoryByModelId(modelId, 100);
            
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("portfolio", portfolio);
            result.put("account_value_history", accountValueHistory);
            result.put("autoBuyEnabled", model.getAutoBuyEnabled() != null ? model.getAutoBuyEnabled() : true);
            result.put("autoSellEnabled", model.getAutoSellEnabled() != null ? model.getAutoSellEnabled() : true);
            result.put("leverage", model.getLeverage() != null ? model.getLeverage() : 10);
            
            // 添加详细日志，输出返回的数据结构
            log.debug("[ModelService] ========== 返回投资组合数据 ==========");
            log.debug("[ModelService] portfolio.positions数量: {}", portfolio.get("positions") != null ? ((List<?>) portfolio.get("positions")).size() : 0);
            if (portfolio.get("positions") != null) {
                @SuppressWarnings("unchecked")
                List<Map<String, Object>> posList = (List<Map<String, Object>>) portfolio.get("positions");
                for (int i = 0; i < posList.size(); i++) {
                    Map<String, Object> pos = posList.get(i);
                    log.debug("[ModelService] 持仓[{}]: symbol={}, position_amt={}, avg_price={}, current_price={}, pnl={}, position_side={}, leverage={}",
                            i + 1, pos.get("symbol"), pos.get("position_amt"), pos.get("avg_price"),
                            pos.get("current_price"), pos.get("pnl"), pos.get("position_side"), pos.get("leverage"));
                    log.debug("[ModelService] 持仓[{}] 完整数据: {}", i + 1, pos);
                }
            }
            log.debug("[ModelService] ========================================");
            
            return result;
        } catch (Exception e) {
            log.error("[ModelService] 获取投资组合数据失败: {}", e.getMessage(), e);
            throw new RuntimeException("获取投资组合数据失败: " + e.getMessage(), e);
        }
    }

    @Override
    public Map<String, Object> getModelPortfolioSymbols(String modelId) {
        log.debug("[ModelService] ========== 开始获取持仓合约symbol列表 ==========");
        log.debug("[ModelService] modelId: {}", modelId);
        try {
            ModelDO model = modelMapper.selectModelById(modelId);
            if (model == null) {
                log.error("[ModelService] 模型不存在: {}", modelId);
                throw new RuntimeException("Model not found");
            }
            
            // 获取持仓数据
            QueryWrapper<PortfolioDO> portfolioQuery = new QueryWrapper<>();
            portfolioQuery.eq("model_id", modelId);
            portfolioQuery.ne("position_amt", 0);
            List<PortfolioDO> portfolioDOList = portfolioMapper.selectList(portfolioQuery);
            log.debug("[ModelService] 查询到持仓记录数: {}", portfolioDOList.size());
            
            // 从持仓数据中提取去重的 symbol 列表（持仓的symbol是完整格式，如BTCUSDT）
            List<String> symbols = portfolioDOList.stream()
                    .map(PortfolioDO::getSymbol)
                    .filter(s -> s != null && !s.isEmpty())
                    .map(String::toUpperCase)
                    .distinct()
                    .sorted()
                    .collect(Collectors.toList());
            
            log.debug("[ModelService] 提取的持仓symbol列表: {}", symbols);
            
            if (symbols.isEmpty()) {
                log.warn("[ModelService] 持仓symbol列表为空，返回空数据");
                Map<String, Object> result = new HashMap<>();
                result.put("data", new ArrayList<>());
                return result;
            }
            
            // 从SDK实时获取价格（使用持仓的完整symbol格式，如BTCUSDT）
            log.debug("[ModelService] 开始从SDK实时获取价格，symbol列表: {}", symbols);
            Map<String, Map<String, Object>> sdkPrices = new HashMap<>();
            try {
                // 使用BinanceFuturesClient直接获取实时价格
                com.aifuturetrade.common.api.binance.BinanceFuturesClient binanceClient = getBinanceFuturesClient();
                sdkPrices = binanceClient.getSymbolPrices(symbols);
                log.debug("[ModelService] SDK返回价格数据数量: {}", sdkPrices.size());
                for (Map.Entry<String, Map<String, Object>> entry : sdkPrices.entrySet()) {
                    log.debug("[ModelService] SDK价格数据: {} = {}", entry.getKey(), entry.getValue());
                }
            } catch (Exception e) {
                log.error("[ModelService] 从SDK获取实时价格失败: {}", e.getMessage(), e);
            }
            
            // 从24_market_tickers表获取涨跌百分比和成交额
            log.debug("[ModelService] 开始从24_market_tickers表获取涨跌百分比和成交额");
            Map<String, Map<String, Object>> tickerDataMap = new HashMap<>();
            try {
                List<Map<String, Object>> tickerDataList = marketTickerMapper.selectTickersBySymbols(symbols);
                log.debug("[ModelService] 从24_market_tickers表查询到 {} 条记录", tickerDataList.size());
                for (Map<String, Object> ticker : tickerDataList) {
                    String tickerSymbol = (String) ticker.get("symbol");
                    if (tickerSymbol != null) {
                        tickerDataMap.put(tickerSymbol.toUpperCase(), ticker);
                        log.debug("[ModelService] Ticker数据: {} = price_change_percent={}, quote_volume={}", 
                                tickerSymbol, ticker.get("price_change_percent"), ticker.get("quote_volume"));
                    }
                }
            } catch (Exception e) {
                log.error("[ModelService] 从24_market_tickers表获取数据失败: {}", e.getMessage(), e);
            }
            
            // 构建响应数据：合并SDK实时价格和数据库ticker数据
            log.debug("[ModelService] 开始构建响应数据");
            List<Map<String, Object>> result = new ArrayList<>();
            for (String symbol : symbols) {
                log.debug("[ModelService] 处理symbol: {}", symbol);
                
                // 从SDK获取实时价格
                Map<String, Object> sdkPriceInfo = sdkPrices.get(symbol);
                Double realTimePrice = 0.0;
                if (sdkPriceInfo != null) {
                    Object priceObj = sdkPriceInfo.get("price");
                    if (priceObj != null) {
                        realTimePrice = convertToDouble(priceObj);
                        log.debug("[ModelService] symbol {} 的SDK实时价格: {}", symbol, realTimePrice);
                    }
                } else {
                    log.warn("[ModelService] symbol {} 未从SDK获取到价格", symbol);
                }
                
                // 从24_market_tickers表获取涨跌百分比和成交额
                Map<String, Object> tickerData = tickerDataMap.get(symbol);
                Double changePercent = 0.0;
                Double quoteVolume = 0.0;
                if (tickerData != null) {
                    Object changePercentObj = tickerData.get("price_change_percent");
                    if (changePercentObj != null) {
                        changePercent = convertToDouble(changePercentObj);
                        log.debug("[ModelService] symbol {} 的涨跌百分比: {}%", symbol, changePercent);
                    }
                    Object quoteVolumeObj = tickerData.get("quote_volume");
                    if (quoteVolumeObj != null) {
                        quoteVolume = convertToDouble(quoteVolumeObj);
                        log.debug("[ModelService] symbol {} 的成交额: {}", symbol, quoteVolume);
                    }
                } else {
                    log.warn("[ModelService] symbol {} 未从24_market_tickers表获取到数据", symbol);
                }
                
                Map<String, Object> symbolData = new HashMap<>();
                symbolData.put("symbol", symbol);
                symbolData.put("price", realTimePrice);
                symbolData.put("change", changePercent);
                symbolData.put("changePercent", changePercent);  // 前端期望的字段名
                symbolData.put("volume", 0.0);  // 暂时不提供
                symbolData.put("quoteVolume", quoteVolume);  // 前端期望的字段名
                symbolData.put("high", 0.0);  // 暂时不提供
                symbolData.put("low", 0.0);  // 暂时不提供
                
                log.debug("[ModelService] symbol {} 最终数据: price={}, changePercent={}, quoteVolume={}", 
                        symbol, realTimePrice, changePercent, quoteVolume);
                
                result.add(symbolData);
            }
            
            log.debug("[ModelService] 构建响应数据完成，共 {} 条记录", result.size());
            
            Map<String, Object> response = new HashMap<>();
            response.put("data", result);
            
            log.debug("[ModelService] ========== 获取持仓合约symbol列表完成 ==========");
            return response;
        } catch (Exception e) {
            log.error("[ModelService] 获取持仓合约symbol列表失败: {}", e.getMessage(), e);
            Map<String, Object> result = new HashMap<>();
            result.put("data", new ArrayList<>());
            return result;
        }
    }

    @Override
    public PageResult<Map<String, Object>> getTradesByPage(String modelId, PageRequest pageRequest) {
        log.debug("[ModelService] ========== 开始获取交易历史记录（分页） ==========");
        log.debug("[ModelService] modelId: {}, pageNum: {}, pageSize: {}", modelId, pageRequest.getPageNum(), pageRequest.getPageSize());
        try {
            // 设置默认值
            Integer pageNum = pageRequest.getPageNum() != null && pageRequest.getPageNum() > 0 ? pageRequest.getPageNum() : 1;
            Integer pageSize = pageRequest.getPageSize() != null && pageRequest.getPageSize() > 0 ? pageRequest.getPageSize() : 10;
            
            // 查询总数
            Long total = tradeMapper.countTradesByModelId(modelId);
            log.debug("[ModelService] 交易记录总数: {}", total);
            
            // 使用MyBatis-Plus的Page进行分页查询
            Page<TradeDO> page = new Page<>(pageNum, pageSize);
            QueryWrapper<TradeDO> queryWrapper = new QueryWrapper<>();
            queryWrapper.eq("model_id", modelId);
            queryWrapper.orderByDesc("timestamp");
            Page<TradeDO> tradeDOPage = tradeMapper.selectPage(page, queryWrapper);
            
            List<TradeDO> tradeDOList = tradeDOPage.getRecords();
            log.debug("[ModelService] 从数据库查询到 {} 条交易记录（第{}页，每页{}条）", tradeDOList.size(), pageNum, pageSize);
            
            List<Map<String, Object>> trades = convertTradesToMapList(tradeDOList);
            
            log.debug("[ModelService] 转换完成，共 {} 条交易记录", trades.size());
            log.debug("[ModelService] ========== 获取交易历史记录（分页）完成 ==========");
            
            return PageResult.build(trades, total, pageNum, pageSize);
        } catch (Exception e) {
            log.error("[ModelService] 获取交易历史记录（分页）失败: {}", e.getMessage(), e);
            return PageResult.build(new ArrayList<>(), 0L, pageRequest.getPageNum() != null ? pageRequest.getPageNum() : 1, pageRequest.getPageSize() != null ? pageRequest.getPageSize() : 10);
        }
    }
    
    /**
     * 将交易记录DO列表转换为Map列表（提取公共逻辑）
     */
    private List<Map<String, Object>> convertTradesToMapList(List<TradeDO> tradeDOList) {
        List<Map<String, Object>> trades = new ArrayList<>();
        
        // 获取交易记录中涉及的symbol列表
        List<String> symbols = tradeDOList.stream()
                .map(trade -> trade.getFuture() != null ? trade.getFuture().toUpperCase() : "")
                .filter(s -> !s.isEmpty())
                .distinct()
                .collect(Collectors.toList());
        
        log.debug("[ModelService] 提取的symbol列表: {}", symbols);
        
        // 获取实时价格
        Map<String, Map<String, Object>> pricesData = new HashMap<>();
        if (!symbols.isEmpty()) {
            pricesData = marketService.getMarketPrices();
        }
        
        // 转换并格式化交易记录
        log.debug("[ModelService] 开始转换交易记录数据");
        for (int i = 0; i < tradeDOList.size(); i++) {
            TradeDO tradeDO = tradeDOList.get(i);
            log.debug("[ModelService] 处理交易记录[{}]: id={}, future={}, signal={}, price={}, quantity={}, pnl={}, fee={}",
                    i + 1, tradeDO.getId(), tradeDO.getFuture(), tradeDO.getSignal(),
                    tradeDO.getPrice(), tradeDO.getQuantity(), tradeDO.getPnl(), tradeDO.getFee());
            
            Map<String, Object> trade = new HashMap<>();
            trade.put("id", tradeDO.getId());
            trade.put("modelId", tradeDO.getModelId());
            trade.put("future", tradeDO.getFuture());
            trade.put("symbol", tradeDO.getFuture()); // 兼容字段
            trade.put("signal", tradeDO.getSignal());
            trade.put("price", tradeDO.getPrice());
            trade.put("quantity", tradeDO.getQuantity());
            trade.put("pnl", tradeDO.getPnl() != null ? tradeDO.getPnl() : 0.0);
            trade.put("fee", tradeDO.getFee() != null ? tradeDO.getFee() : 0.0);  // 添加fee字段
            trade.put("status", tradeDO.getStatus());
            
            // 格式化timestamp字段为字符串（北京时间）
            if (tradeDO.getTimestamp() != null) {
                trade.put("timestamp", tradeDO.getTimestamp().format(DATETIME_FORMATTER));
            } else {
                trade.put("timestamp", "");
            }
            
            // 如果是开仓交易，使用实时价格计算未实现盈亏
            String signal = tradeDO.getSignal();
            String symbol = tradeDO.getFuture();
            if (symbol != null && (signal != null && (signal.equals("buy_to_long") || signal.equals("buy_to_short")))) {
                if (tradeDO.getPnl() == null || tradeDO.getPnl() == 0) {
                    // 如果数据库中的pnl为0，说明可能还没有平仓，使用实时价格计算
                    String contractSymbol = symbol.toUpperCase();
                    if (!contractSymbol.endsWith("USDT")) {
                        contractSymbol = contractSymbol + "USDT";
                    }
                    Map<String, Object> priceInfo = pricesData.get(symbol.toUpperCase());
                    if (priceInfo != null && priceInfo.get("price") != null) {
                        Double currentPrice = convertToDouble(priceInfo.get("price"));
                        if (currentPrice != null && currentPrice > 0) {
                            trade.put("current_price", currentPrice);
                            
                            if (tradeDO.getPrice() != null && tradeDO.getPrice() > 0) {
                                Double quantity = Math.abs(tradeDO.getQuantity() != null ? tradeDO.getQuantity() : 0.0);
                                Double calculatedPnl;
                                if (signal.equals("buy_to_long")) {
                                    // 开多：盈亏 = (当前价 - 开仓价) * 数量
                                    calculatedPnl = (currentPrice - tradeDO.getPrice()) * quantity;
                                } else {
                                    // 开空：盈亏 = (开仓价 - 当前价) * 数量
                                    calculatedPnl = (tradeDO.getPrice() - currentPrice) * quantity;
                                }
                                trade.put("pnl", calculatedPnl);
                            }
                        }
                    }
                } else {
                    // 如果存储的pnl不为0，说明已经平仓，使用数据库中的pnl（已实现盈亏）
                    trade.put("pnl", tradeDO.getPnl());
                }
            } else {
                // 如果是平仓交易，使用数据库中的pnl（已实现盈亏）
                trade.put("pnl", tradeDO.getPnl() != null ? tradeDO.getPnl() : 0.0);
            }
            
            log.debug("[ModelService] 交易记录[{}] 最终数据: id={}, symbol={}, price={}, quantity={}, pnl={}, fee={}",
                    i + 1, trade.get("id"), trade.get("symbol"), trade.get("price"),
                    trade.get("quantity"), trade.get("pnl"), trade.get("fee"));
            
            trades.add(trade);
        }
        
        return trades;
    }

    @Override
    public List<Map<String, Object>> getTrades(String modelId, Integer limit) {
        log.debug("[ModelService] ========== 开始获取交易历史记录 ==========");
        log.debug("[ModelService] modelId: {}, limit: {}", modelId, limit);
        try {
            if (limit == null) {
                limit = defaultTradesQueryLimit;
            }
            
            List<TradeDO> tradeDOList = tradeMapper.selectTradesByModelId(modelId, limit);
            log.debug("[ModelService] 从数据库查询到 {} 条交易记录", tradeDOList.size());
            
            List<Map<String, Object>> trades = convertTradesToMapList(tradeDOList);
            
            log.debug("[ModelService] 转换完成，共 {} 条交易记录", trades.size());
            log.debug("[ModelService] ========== 获取交易历史记录完成 ==========");
            
            return trades;
        } catch (Exception e) {
            log.error("[ModelService] 获取交易历史记录失败: {}", e.getMessage(), e);
            return new ArrayList<>();
        }
    }

    @Override
    public List<Map<String, Object>> getConversations(String modelId, Integer limit) {
        log.debug("[ModelService] 获取对话历史记录, modelId={}, limit={}", modelId, limit);
        try {
            // 默认limit为20，与前端保持一致
            if (limit == null) {
                limit = 20;
            }
            // 移除限制，允许前端传递更大的limit值
            
            List<ConversationDO> conversationDOList = conversationMapper.selectConversationsByModelId(modelId, limit);
            List<Map<String, Object>> conversations = new ArrayList<>();
            
            for (ConversationDO conversationDO : conversationDOList) {
                Map<String, Object> conversation = new HashMap<>();
                conversation.put("id", conversationDO.getId());
                conversation.put("modelId", conversationDO.getModelId());
                
                // 同时提供camelCase和snake_case格式，确保前端兼容性
                String userPrompt = conversationDO.getUserPrompt();
                String aiResponse = conversationDO.getAiResponse();
                String cotTrace = conversationDO.getCotTrace();
                
                // camelCase格式（Java标准）
                conversation.put("userPrompt", userPrompt);
                conversation.put("aiResponse", aiResponse);
                conversation.put("cotTrace", cotTrace);
                
                // snake_case格式（前端期望的格式）
                conversation.put("user_prompt", userPrompt);
                conversation.put("ai_response", aiResponse);
                conversation.put("cot_trace", cotTrace);
                
                // 使用type字段（数据库字段为type）
                String conversationType = conversationDO.getType();
                conversation.put("conversationType", conversationType);
                conversation.put("conversation_type", conversationType); // snake_case格式
                conversation.put("type", conversationType); // 直接使用type字段
                conversation.put("tokens", conversationDO.getTokens());
                
                // 格式化timestamp字段为字符串（北京时间）
                if (conversationDO.getTimestamp() != null) {
                    String timestamp = conversationDO.getTimestamp().format(DATETIME_FORMATTER);
                    conversation.put("timestamp", timestamp);
                } else {
                    conversation.put("timestamp", "");
                }
                
                conversations.add(conversation);
            }
            
            return conversations;
        } catch (Exception e) {
            log.error("[ModelService] 获取对话历史记录失败: {}", e.getMessage(), e);
            return new ArrayList<>();
        }
    }

    @Override
    public Map<String, Object> getModelPrompts(String modelId) {
        log.debug("[ModelService] 获取模型提示词配置, modelId={}", modelId);
        try {
            ModelDO model = modelMapper.selectModelById(modelId);
            if (model == null) {
                throw new RuntimeException("Model not found");
            }
            
            // 查询提示词配置
            QueryWrapper<ModelPromptDO> queryWrapper = new QueryWrapper<>();
            queryWrapper.eq("model_id", modelId);
            ModelPromptDO promptDO = modelPromptMapper.selectOne(queryWrapper);
            
            // 默认提示词（从配置或常量读取）
            String defaultBuyPrompt = "请分析以下行情并给出买入建议";
            String defaultSellPrompt = "请分析以下行情并给出卖出建议";
            
            String buyPrompt = defaultBuyPrompt;
            String sellPrompt = defaultSellPrompt;
            boolean hasCustom = false;
            LocalDateTime updatedAt = null;
            
            if (promptDO != null) {
                if (promptDO.getBuyPrompt() != null && !promptDO.getBuyPrompt().isEmpty()) {
                    buyPrompt = promptDO.getBuyPrompt();
                }
                if (promptDO.getSellPrompt() != null && !promptDO.getSellPrompt().isEmpty()) {
                    sellPrompt = promptDO.getSellPrompt();
                }
                hasCustom = true;
                updatedAt = promptDO.getUpdatedAt();
            }
            
            // 移除JSON输出要求结尾句（如果存在）
            buyPrompt = removeJsonOutputSuffix(buyPrompt);
            sellPrompt = removeJsonOutputSuffix(sellPrompt);
            
            Map<String, Object> prompts = new HashMap<>();
            prompts.put("modelId", modelId);
            prompts.put("modelName", model.getName());
            prompts.put("buyPrompt", buyPrompt);
            prompts.put("sellPrompt", sellPrompt);
            prompts.put("hasCustom", hasCustom);
            if (updatedAt != null) {
                prompts.put("updatedAt", updatedAt.format(DATETIME_FORMATTER));
            }
            
            return prompts;
        } catch (Exception e) {
            log.error("[ModelService] 获取模型提示词配置失败: {}", e.getMessage(), e);
            throw new RuntimeException("获取模型提示词配置失败: " + e.getMessage(), e);
        }
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> updateModelPrompts(String modelId, String buyPrompt, String sellPrompt) {
        log.debug("[ModelService] 更新模型提示词配置, modelId={}", modelId);
        try {
            ModelDO model = modelMapper.selectModelById(modelId);
            if (model == null) {
                throw new RuntimeException("Model not found");
            }
            
            // 移除JSON输出要求结尾句
            String buyPromptClean = removeJsonOutputSuffix(buyPrompt);
            String sellPromptClean = removeJsonOutputSuffix(sellPrompt);
            
            // 使用 INSERT ... ON DUPLICATE KEY UPDATE
            QueryWrapper<ModelPromptDO> queryWrapper = new QueryWrapper<>();
            queryWrapper.eq("model_id", modelId);
            ModelPromptDO existingPrompt = modelPromptMapper.selectOne(queryWrapper);
            
            if (existingPrompt != null) {
                // 更新
                existingPrompt.setBuyPrompt(buyPromptClean);
                existingPrompt.setSellPrompt(sellPromptClean);
                existingPrompt.setUpdatedAt(LocalDateTime.now());
                modelPromptMapper.updateById(existingPrompt);
            } else {
                // 插入
                ModelPromptDO newPrompt = new ModelPromptDO();
                newPrompt.setModelId(modelId);
                newPrompt.setBuyPrompt(buyPromptClean);
                newPrompt.setSellPrompt(sellPromptClean);
                newPrompt.setUpdatedAt(LocalDateTime.now());
                modelPromptMapper.insert(newPrompt);
            }
            
            Map<String, Object> result = new HashMap<>();
            result.put("success", true);
            result.put("message", "Prompts updated successfully");
            return result;
        } catch (Exception e) {
            log.error("[ModelService] 更新模型提示词配置失败: {}", e.getMessage(), e);
            throw new RuntimeException("更新模型提示词配置失败: " + e.getMessage(), e);
        }
    }
    
    /**
     * 移除JSON输出要求结尾句
     */
    private String removeJsonOutputSuffix(String promptText) {
        if (promptText == null || promptText.isEmpty()) {
            return promptText;
        }
        
        String text = promptText.trim();
        String suffix = "请以JSON格式输出，包含signal和reason字段。";
        
        if (text.endsWith(suffix)) {
            text = text.substring(0, text.length() - suffix.length()).trim();
        }
        
        // 移除可能的句号
        text = text.replaceAll("[。.]$", "").trim();
        
        return text;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> updateModelBatchConfig(String modelId, Map<String, Object> batchConfig) {
        log.debug("[ModelService] 更新模型批次配置, modelId={}", modelId);
        try {
            ModelDO model = modelMapper.selectModelById(modelId);
            if (model == null) {
                throw new RuntimeException("Model not found");
            }
            
            UpdateWrapper<ModelDO> updateWrapper = new UpdateWrapper<>();
            updateWrapper.eq("id", modelId);
            
            if (batchConfig.containsKey("buy_batch_size")) {
                Integer buyBatchSize = Math.max(1, ((Number) batchConfig.get("buy_batch_size")).intValue());
                updateWrapper.set("buy_batch_size", buyBatchSize);
            }
            if (batchConfig.containsKey("buy_batch_execution_interval")) {
                Integer interval = Math.max(0, ((Number) batchConfig.get("buy_batch_execution_interval")).intValue());
                updateWrapper.set("buy_batch_execution_interval", interval);
            }
            if (batchConfig.containsKey("buy_batch_execution_group_size")) {
                Integer groupSize = Math.max(1, ((Number) batchConfig.get("buy_batch_execution_group_size")).intValue());
                updateWrapper.set("buy_batch_execution_group_size", groupSize);
            }
            if (batchConfig.containsKey("sell_batch_size")) {
                Integer sellBatchSize = Math.max(1, ((Number) batchConfig.get("sell_batch_size")).intValue());
                updateWrapper.set("sell_batch_size", sellBatchSize);
            }
            if (batchConfig.containsKey("sell_batch_execution_interval")) {
                Integer interval = Math.max(0, ((Number) batchConfig.get("sell_batch_execution_interval")).intValue());
                updateWrapper.set("sell_batch_execution_interval", interval);
            }
            if (batchConfig.containsKey("sell_batch_execution_group_size")) {
                Integer groupSize = Math.max(1, ((Number) batchConfig.get("sell_batch_execution_group_size")).intValue());
                updateWrapper.set("sell_batch_execution_group_size", groupSize);
            }
            
            modelMapper.update(null, updateWrapper);
            
            Map<String, Object> result = new HashMap<>();
            result.put("success", true);
            result.put("message", "批次配置更新成功");
            return result;
        } catch (Exception e) {
            log.error("[ModelService] 更新模型批次配置失败: {}", e.getMessage(), e);
            throw new RuntimeException("更新模型批次配置失败: " + e.getMessage(), e);
        }
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> updateModelMaxPositions(String modelId, Integer maxPositions) {
        log.debug("[ModelService] 更新模型最大持仓数量, modelId={}, maxPositions={}", modelId, maxPositions);
        try {
            if (maxPositions == null || maxPositions < 1) {
                throw new IllegalArgumentException("max_positions must be >= 1");
            }
            
            ModelDO model = modelMapper.selectModelById(modelId);
            if (model == null) {
                throw new RuntimeException("Model not found");
            }
            
            UpdateWrapper<ModelDO> updateWrapper = new UpdateWrapper<>();
            updateWrapper.eq("id", modelId);
            updateWrapper.set("max_positions", maxPositions);
            modelMapper.update(null, updateWrapper);
            
            Map<String, Object> result = new HashMap<>();
            result.put("success", true);
            result.put("max_positions", maxPositions);
            return result;
        } catch (Exception e) {
            log.error("[ModelService] 更新模型最大持仓数量失败: {}", e.getMessage(), e);
            throw new RuntimeException("更新模型最大持仓数量失败: " + e.getMessage(), e);
        }
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> updateModelLeverage(String modelId, Integer leverage) {
        log.debug("[ModelService] 更新模型杠杆倍数, modelId={}, leverage={}", modelId, leverage);
        try {
            if (leverage == null || leverage < 1) {
                leverage = Math.max(1, leverage != null ? leverage : 1);
            }
            
            ModelDO model = modelMapper.selectModelById(modelId);
            if (model == null) {
                throw new RuntimeException("Model not found");
            }
            
            UpdateWrapper<ModelDO> updateWrapper = new UpdateWrapper<>();
            updateWrapper.eq("id", modelId);
            updateWrapper.set("leverage", leverage);
            modelMapper.update(null, updateWrapper);
            
            Map<String, Object> result = new HashMap<>();
            result.put("model_id", modelId);
            result.put("leverage", leverage);
            return result;
        } catch (Exception e) {
            log.error("[ModelService] 更新模型杠杆倍数失败: {}", e.getMessage(), e);
            throw new RuntimeException("更新模型杠杆倍数失败: " + e.getMessage(), e);
        }
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> updateModelProvider(String modelId, String providerId, String modelName) {
        log.debug("[ModelService] 更新模型提供方和模型名称, modelId={}, providerId={}, modelName={}", modelId, providerId, modelName);
        try {
            if (modelName == null || modelName.trim().isEmpty()) {
                throw new IllegalArgumentException("model_name cannot be empty");
            }
            
            ModelDO model = modelMapper.selectModelById(modelId);
            if (model == null) {
                throw new RuntimeException("Model not found");
            }
            
            ProviderDO provider = providerMapper.selectProviderById(providerId);
            if (provider == null) {
                throw new RuntimeException("Provider not found");
            }
            
            UpdateWrapper<ModelDO> updateWrapper = new UpdateWrapper<>();
            updateWrapper.eq("id", modelId);
            updateWrapper.set("provider_id", providerId);
            updateWrapper.set("model_name", modelName.trim());
            modelMapper.update(null, updateWrapper);
            
            Map<String, Object> result = new HashMap<>();
            result.put("success", true);
            result.put("model_id", modelId);
            result.put("provider_id", providerId);
            result.put("model_name", modelName.trim());
            return result;
        } catch (Exception e) {
            log.error("[ModelService] 更新模型提供方和模型名称失败: {}", e.getMessage(), e);
            throw new RuntimeException("更新模型提供方和模型名称失败: " + e.getMessage(), e);
        }
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> setModelAutoTrading(String modelId, Boolean autoBuyEnabled, Boolean autoSellEnabled) {
        log.debug("[ModelService] 设置模型自动交易开关, modelId={}, autoBuyEnabled={}, autoSellEnabled={}", 
                modelId, autoBuyEnabled, autoSellEnabled);
        try {
            ModelDO model = modelMapper.selectModelById(modelId);
            if (model == null) {
                throw new RuntimeException("Model not found");
            }
            
            UpdateWrapper<ModelDO> updateWrapper = new UpdateWrapper<>();
            updateWrapper.eq("id", modelId);
            if (autoBuyEnabled != null) {
                updateWrapper.set("auto_buy_enabled", autoBuyEnabled);
            }
            if (autoSellEnabled != null) {
                updateWrapper.set("auto_sell_enabled", autoSellEnabled);
            }
            modelMapper.update(null, updateWrapper);
            
            Map<String, Object> result = new HashMap<>();
            result.put("success", true);
            result.put("model_id", modelId);
            result.put("auto_buy_enabled", autoBuyEnabled);
            result.put("auto_sell_enabled", autoSellEnabled);
            return result;
        } catch (Exception e) {
            log.error("[ModelService] 设置模型自动交易开关失败: {}", e.getMessage(), e);
            throw new RuntimeException("设置模型自动交易开关失败: " + e.getMessage(), e);
        }
    }

    @Override
    public Map<String, Object> getAggregatedPortfolio() {
        log.debug("[ModelService] 获取聚合投资组合数据");
        try {
            Map<String, Map<String, Object>> pricesData = marketService.getMarketPrices();
            Map<String, Double> currentPrices = new HashMap<>();
            for (Map.Entry<String, Map<String, Object>> entry : pricesData.entrySet()) {
                Object priceObj = entry.getValue().get("price");
                if (priceObj != null) {
                    Double priceValue = convertToDouble(priceObj);
                    if (priceValue != null) {
                        currentPrices.put(entry.getKey(), priceValue);
                    }
                }
            }
            
            List<ModelDO> models = modelMapper.selectAllModels();
            Map<String, Object> totalPortfolio = new LinkedHashMap<>();
            totalPortfolio.put("total_value", 0.0);
            totalPortfolio.put("cash", 0.0);
            totalPortfolio.put("positions_value", 0.0);
            totalPortfolio.put("realized_pnl", 0.0);
            totalPortfolio.put("unrealized_pnl", 0.0);
            totalPortfolio.put("initial_capital", 0.0);
            totalPortfolio.put("positions", new ArrayList<>());
            
            Map<String, Map<String, Object>> allPositions = new HashMap<>();
            
            for (ModelDO model : models) {
                Map<String, Object> portfolio = getPortfolio(model.getId());
                if (portfolio != null && portfolio.containsKey("portfolio")) {
                    @SuppressWarnings("unchecked")
                    Map<String, Object> portfolioData = (Map<String, Object>) portfolio.get("portfolio");
                    
                    // 安全地累加数值，处理String和Number类型
                    Double totalValue = convertToDouble(totalPortfolio.get("total_value"));
                    Double portfolioTotalValue = convertToDouble(portfolioData.getOrDefault("total_value", 0.0));
                    totalPortfolio.put("total_value", (totalValue != null ? totalValue : 0.0) + (portfolioTotalValue != null ? portfolioTotalValue : 0.0));
                    
                    Double cash = convertToDouble(totalPortfolio.get("cash"));
                    Double portfolioCash = convertToDouble(portfolioData.getOrDefault("cash", 0.0));
                    totalPortfolio.put("cash", (cash != null ? cash : 0.0) + (portfolioCash != null ? portfolioCash : 0.0));
                    
                    Double positionsValue = convertToDouble(totalPortfolio.get("positions_value"));
                    Double portfolioPositionsValue = convertToDouble(portfolioData.getOrDefault("positions_value", 0.0));
                    totalPortfolio.put("positions_value", (positionsValue != null ? positionsValue : 0.0) + (portfolioPositionsValue != null ? portfolioPositionsValue : 0.0));
                    
                    Double realizedPnl = convertToDouble(totalPortfolio.get("realized_pnl"));
                    Double portfolioRealizedPnl = convertToDouble(portfolioData.getOrDefault("realized_pnl", 0.0));
                    totalPortfolio.put("realized_pnl", (realizedPnl != null ? realizedPnl : 0.0) + (portfolioRealizedPnl != null ? portfolioRealizedPnl : 0.0));
                    
                    Double unrealizedPnl = convertToDouble(totalPortfolio.get("unrealized_pnl"));
                    Double portfolioUnrealizedPnl = convertToDouble(portfolioData.getOrDefault("unrealized_pnl", 0.0));
                    totalPortfolio.put("unrealized_pnl", (unrealizedPnl != null ? unrealizedPnl : 0.0) + (portfolioUnrealizedPnl != null ? portfolioUnrealizedPnl : 0.0));
                    
                    Double initialCapital = convertToDouble(totalPortfolio.get("initial_capital"));
                    Double portfolioInitialCapital = convertToDouble(portfolioData.getOrDefault("initial_capital", 0.0));
                    totalPortfolio.put("initial_capital", (initialCapital != null ? initialCapital : 0.0) + (portfolioInitialCapital != null ? portfolioInitialCapital : 0.0));
                    
                    @SuppressWarnings("unchecked")
                    List<Map<String, Object>> positions = (List<Map<String, Object>>) portfolioData.get("positions");
                    if (positions != null) {
                        for (Map<String, Object> pos : positions) {
                            String symbol = (String) pos.get("symbol");
                            String positionSide = (String) pos.get("positionSide");
                            String key = symbol + "_" + positionSide;
                            
                            if (!allPositions.containsKey(key)) {
                                allPositions.put(key, new HashMap<>(pos));
                                allPositions.get(key).put("positionAmt", 0.0);
                                allPositions.get(key).put("avgPrice", 0.0);
                                allPositions.get(key).put("totalCost", 0.0);
                            }
                            
                            Map<String, Object> currentPos = allPositions.get(key);
                            Double currentAmt = convertToDouble(currentPos.get("positionAmt"));
                            Double currentAvgPrice = convertToDouble(currentPos.get("avgPrice"));
                            Double newAmtRaw = convertToDouble(pos.get("positionAmt"));
                            Double newAmt = Math.abs(newAmtRaw != null ? newAmtRaw : 0.0);
                            Double newAvgPrice = convertToDouble(pos.get("avgPrice"));
                            
                            // 处理null值
                            if (currentAmt == null) currentAmt = 0.0;
                            if (currentAvgPrice == null) currentAvgPrice = 0.0;
                            if (newAvgPrice == null) newAvgPrice = 0.0;
                            
                            Double currentCost = currentAmt * currentAvgPrice;
                            Double newCost = newAmt * newAvgPrice;
                            Double totalAmt = currentAmt + newAmt;
                            
                            if (totalAmt > 0) {
                                currentPos.put("avgPrice", (currentCost + newCost) / totalAmt);
                                currentPos.put("positionAmt", totalAmt);
                                currentPos.put("totalCost", currentCost + newCost);
                                
                                Double currentPrice = currentPrices.get(symbol);
                                if (currentPrice == null) {
                                    currentPrice = convertToDouble(pos.getOrDefault("currentPrice", 0.0));
                                    if (currentPrice == null) currentPrice = 0.0;
                                }
                                if (currentPrice > 0) {
                                    currentPos.put("currentPrice", currentPrice);
                                    Double avgPriceForPnl = convertToDouble(currentPos.get("avgPrice"));
                                    if (avgPriceForPnl == null) avgPriceForPnl = 0.0;
                                    currentPos.put("pnl", (currentPrice - avgPriceForPnl) * totalAmt);
                                }
                            }
                        }
                    }
                }
            }
            
            totalPortfolio.put("positions", new ArrayList<>(allPositions.values()));
            
            // 获取多模型图表数据
            List<Map<String, Object>> chartData = accountValueHistoryMapper.selectMultiModelChartData(100);
            
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("portfolio", totalPortfolio);
            result.put("chartData", chartData);
            result.put("modelCount", models.size());
            
            return result;
        } catch (Exception e) {
            log.error("[ModelService] 获取聚合投资组合数据失败: {}", e.getMessage(), e);
            throw new RuntimeException("获取聚合投资组合数据失败: " + e.getMessage(), e);
        }
    }

    /**
     * 将DO转换为DTO
     * @param modelDO 数据对象
     * @return 数据传输对象
     */
    private ModelDTO convertToDTO(ModelDO modelDO) {
        ModelDTO modelDTO = new ModelDTO();
        BeanUtils.copyProperties(modelDO, modelDTO);
        return modelDTO;
    }

    /**
     * 将DTO转换为DO
     * @param modelDTO 数据传输对象
     * @return 数据对象
     */
    private ModelDO convertToDO(ModelDTO modelDTO) {
        ModelDO modelDO = new ModelDO();
        BeanUtils.copyProperties(modelDTO, modelDO);
        return modelDO;
    }

    @Override
    public Map<String, Object> executeTrading(String modelId) {
        log.debug("[ModelService] 执行交易周期（同时执行买入和卖出）, modelId={}", modelId);
        Map<String, Object> result = new HashMap<>();
        try {
            // 检查模型是否存在
            ModelDTO model = getModelById(modelId);
            if (model == null) {
                result.put("success", false);
                result.put("error", "Model not found");
                return result;
            }

            // 启用自动交易（同时启用买入和卖出）
            setModelAutoTrading(modelId, true, true);

            // 调用更新后的方法（只更新数据库字段）
            Map<String, Object> buyResult = executeBuyTrading(modelId);
            Map<String, Object> sellResult = executeSellTrading(modelId);

            // 合并结果
            result.put("success", true);
            result.put("buy_result", buyResult);
            result.put("sell_result", sellResult);
            result.put("message", "Auto trading enabled for model");
            
            return result;
        } catch (Exception e) {
            log.error("[ModelService] 执行交易失败: {}", e.getMessage(), e);
            result.put("success", false);
            result.put("error", e.getMessage());
            return result;
        }
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> executeBuyTrading(String modelId) {
        log.debug("[ModelService] 启用模型自动买入, modelId={}", modelId);
        try {
            // 检查模型是否存在
            ModelDTO model = getModelById(modelId);
            if (model == null) {
                Map<String, Object> errorResult = new HashMap<>();
                errorResult.put("success", false);
                errorResult.put("error", "Model not found");
                return errorResult;
            }

            // 设置 auto_buy_enabled = true
            Map<String, Object> result = setModelAutoTrading(modelId, true, null);
            
            // 构建容器名称：buy-{modelId}
            String containerName = "buy-" + modelId;
            
            // 检查容器是否已存在且运行中
            if (dockerContainerService.isContainerRunning(containerName)) {
                log.info("容器已存在且运行中: {}", containerName);
                result.put("containerName", containerName);
                result.put("containerStatus", "already_running");
                result.put("message", "Auto buy enabled for model, container already running");
                return result;
            }
            
            // 如果容器存在但未运行，删除它
            if (!dockerContainerService.removeContainer(containerName)) {
                log.warn("删除旧容器失败，但继续创建新容器: {}", containerName);
            }
            
            // 准备环境变量
            Map<String, String> envVars = new HashMap<>();
            envVars.put("MODEL_ID", modelId);
            envVars.put("MYSQL_HOST", mysqlHost);
            envVars.put("MYSQL_PORT", mysqlPort);
            envVars.put("MYSQL_USER", mysqlUser);
            envVars.put("MYSQL_PASSWORD", mysqlPassword);
            envVars.put("MYSQL_DATABASE", mysqlDatabase);
            if (binanceApiKey != null && !binanceApiKey.isEmpty()) {
                envVars.put("BINANCE_API_KEY", binanceApiKey);
            }
            if (binanceApiSecret != null && !binanceApiSecret.isEmpty()) {
                envVars.put("BINANCE_SECRET_KEY", binanceApiSecret);
            }
            
            // 打印详细的数据库配置信息（用于调试）
            log.info("=== Container Database Configuration (Buy) ===");
            log.info("MODEL_ID: {}", modelId);
            log.info("MYSQL_HOST: {}", mysqlHost);
            log.info("MYSQL_PORT: {}", mysqlPort);
            log.info("MYSQL_USER: {}", mysqlUser);
            log.info("MYSQL_DATABASE: {}", mysqlDatabase);
            log.info("Database Connection: mysql://{}@{}:{}/{}", mysqlUser, mysqlHost, mysqlPort, mysqlDatabase);
            log.info("================================================");
            
            // 启动模型买入容器
            Map<String, Object> containerResult = dockerContainerService.startModelBuyContainer(
                    modelId, modelBuyImageName, envVars);
            
            // 合并结果
            result.putAll(containerResult);
            if (containerResult.get("success") != null && (Boolean) containerResult.get("success")) {
                result.put("message", "Auto buy enabled for model, container started successfully");
            } else {
                result.put("message", "Auto buy enabled for model, but container start failed: " + 
                           containerResult.get("error"));
            }
            
            return result;
        } catch (Exception e) {
            log.error("[ModelService] 启用模型自动买入失败: {}", e.getMessage(), e);
            Map<String, Object> errorResult = new HashMap<>();
            errorResult.put("success", false);
            errorResult.put("error", e.getMessage());
            return errorResult;
        }
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> executeSellTrading(String modelId) {
        log.debug("[ModelService] 启用模型自动卖出, modelId={}", modelId);
        try {
            // 检查模型是否存在
            ModelDTO model = getModelById(modelId);
            if (model == null) {
                Map<String, Object> errorResult = new HashMap<>();
                errorResult.put("success", false);
                errorResult.put("error", "Model not found");
                return errorResult;
            }

            // 设置 auto_sell_enabled = true
            Map<String, Object> result = setModelAutoTrading(modelId, null, true);
            
            // 构建容器名称：sell-{modelId}
            String containerName = "sell-" + modelId;
            
            // 检查容器是否已存在且运行中
            if (dockerContainerService.isContainerRunning(containerName)) {
                log.info("容器已存在且运行中: {}", containerName);
                result.put("containerName", containerName);
                result.put("containerStatus", "already_running");
                result.put("message", "Auto sell enabled for model, container already running");
                return result;
            }
            
            // 如果容器存在但未运行，删除它
            if (!dockerContainerService.removeContainer(containerName)) {
                log.warn("删除旧容器失败，但继续创建新容器: {}", containerName);
            }
            
            // 准备环境变量
            Map<String, String> envVars = new HashMap<>();
            envVars.put("MODEL_ID", modelId);
            envVars.put("MYSQL_HOST", mysqlHost);
            envVars.put("MYSQL_PORT", mysqlPort);
            envVars.put("MYSQL_USER", mysqlUser);
            envVars.put("MYSQL_PASSWORD", mysqlPassword);
            envVars.put("MYSQL_DATABASE", mysqlDatabase);
            if (binanceApiKey != null && !binanceApiKey.isEmpty()) {
                envVars.put("BINANCE_API_KEY", binanceApiKey);
            }
            if (binanceApiSecret != null && !binanceApiSecret.isEmpty()) {
                envVars.put("BINANCE_SECRET_KEY", binanceApiSecret);
            }
            
            // 打印详细的数据库配置信息（用于调试）
            log.info("=== Container Database Configuration (Sell) ===");
            log.info("MODEL_ID: {}", modelId);
            log.info("MYSQL_HOST: {}", mysqlHost);
            log.info("MYSQL_PORT: {}", mysqlPort);
            log.info("MYSQL_USER: {}", mysqlUser);
            log.info("MYSQL_DATABASE: {}", mysqlDatabase);
            log.info("Database Connection: mysql://{}@{}:{}/{}", mysqlUser, mysqlHost, mysqlPort, mysqlDatabase);
            log.info("================================================");
            
            // 启动模型卖出容器
            Map<String, Object> containerResult = dockerContainerService.startModelSellContainer(
                    modelId, modelSellImageName, envVars);
            
            // 合并结果
            result.putAll(containerResult);
            if (containerResult.get("success") != null && (Boolean) containerResult.get("success")) {
                result.put("message", "Auto sell enabled for model, container started successfully");
            } else {
                result.put("message", "Auto sell enabled for model, but container start failed: " + 
                           containerResult.get("error"));
            }
            
            return result;
        } catch (Exception e) {
            log.error("[ModelService] 启用模型自动卖出失败: {}", e.getMessage(), e);
            Map<String, Object> errorResult = new HashMap<>();
            errorResult.put("success", false);
            errorResult.put("error", e.getMessage());
            return errorResult;
        }
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> disableBuyTrading(String modelId) {
        log.debug("[ModelService] 禁用模型自动买入, modelId={}", modelId);
        try {
            // 检查模型是否存在
            ModelDTO model = getModelById(modelId);
            if (model == null) {
                Map<String, Object> errorResult = new HashMap<>();
                errorResult.put("success", false);
                errorResult.put("error", "Model not found");
                return errorResult;
            }

            // 设置 auto_buy_enabled = false
            Map<String, Object> result = setModelAutoTrading(modelId, false, null);
            result.put("message", "Auto buy disabled for model");
            return result;
        } catch (Exception e) {
            log.error("[ModelService] 禁用模型自动买入失败: {}", e.getMessage(), e);
            Map<String, Object> errorResult = new HashMap<>();
            errorResult.put("success", false);
            errorResult.put("error", e.getMessage());
            return errorResult;
        }
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> disableSellTrading(String modelId) {
        log.debug("[ModelService] 禁用模型自动卖出, modelId={}", modelId);
        try {
            // 检查模型是否存在
            ModelDTO model = getModelById(modelId);
            if (model == null) {
                Map<String, Object> errorResult = new HashMap<>();
                errorResult.put("success", false);
                errorResult.put("error", "Model not found");
                return errorResult;
            }

            // 设置 auto_sell_enabled = false
            Map<String, Object> result = setModelAutoTrading(modelId, null, false);
            result.put("message", "Auto sell disabled for model");
            return result;
        } catch (Exception e) {
            log.error("[ModelService] 禁用模型自动卖出失败: {}", e.getMessage(), e);
            Map<String, Object> errorResult = new HashMap<>();
            errorResult.put("success", false);
            errorResult.put("error", e.getMessage());
            return errorResult;
        }
    }

    /**
     * 安全地将对象转换为Double值
     * 支持Number类型和String类型的转换
     * @param value 待转换的值
     * @return Double值，如果转换失败返回null
     */
    private Double convertToDouble(Object value) {
        if (value == null) {
            return null;
        }
        
        if (value instanceof Number) {
            return ((Number) value).doubleValue();
        }
        
        if (value instanceof String) {
            try {
                return Double.parseDouble((String) value);
            } catch (NumberFormatException e) {
                log.warn("[ModelService] 无法将字符串转换为Double: {}", value);
                return null;
            }
        }
        
        log.warn("[ModelService] 不支持的类型转换: {} ({})", value, value.getClass().getName());
        return null;
    }

}