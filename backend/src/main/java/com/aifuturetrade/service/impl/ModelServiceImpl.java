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
    private AccountValueHistoryMapper accountValueHistoryMapper;

    @Autowired
    private MarketService marketService;

    @Autowired
    private ProviderMapper providerMapper;

    @Autowired
    private FutureMapper futureMapper;

    @Autowired
    private TradeServiceClient tradeServiceClient;

    @Value("${app.trades-query-limit:10}")
    private Integer defaultTradesQueryLimit;

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
        modelDO.setAutoBuyEnabled(true);
        modelDO.setAutoSellEnabled(true);
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
        return convertToDTO(modelDO);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public ModelDTO updateModel(ModelDTO modelDTO) {
        ModelDO modelDO = convertToDO(modelDTO);
        modelDO.setUpdatedAt(LocalDateTime.now());
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
        int result = modelMapper.deleteById(id);
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
        log.info("[ModelService] 获取投资组合数据, modelId={}", modelId);
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
            
            for (PortfolioDO portfolioDO : portfolioDOList) {
                Map<String, Object> position = new HashMap<>();
                position.put("symbol", portfolioDO.getSymbol());
                position.put("positionSide", portfolioDO.getPositionSide());
                position.put("positionAmt", portfolioDO.getPositionAmt());
                position.put("avgPrice", portfolioDO.getAvgPrice());
                position.put("leverage", portfolioDO.getLeverage());
                position.put("unrealizedProfit", portfolioDO.getUnrealizedProfit());
                positions.add(position);
                
                if (portfolioDO.getSymbol() != null) {
                    heldSymbols.add(portfolioDO.getSymbol().toUpperCase());
                }
            }
            
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
            
            // 获取实时价格数据
            Map<String, Map<String, Object>> pricesData = marketService.getMarketPrices();
            Map<String, Double> currentPrices = new HashMap<>();
            for (Map.Entry<String, Map<String, Object>> entry : pricesData.entrySet()) {
                Object priceObj = entry.getValue().get("price");
                if (priceObj != null) {
                    currentPrices.put(entry.getKey(), ((Number) priceObj).doubleValue());
                }
            }
            
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
            
            for (Map<String, Object> pos : positions) {
                String symbol = (String) pos.get("symbol");
                Double avgPrice = ((Number) pos.get("avgPrice")).doubleValue();
                Double positionAmt = Math.abs(((Number) pos.get("positionAmt")).doubleValue());
                String positionSide = (String) pos.get("positionSide");
                Integer leverage = (Integer) pos.get("leverage");
                
                PortfolioDO portfolioDO = symbolToPortfolio.get(symbol != null ? symbol.toUpperCase() : "");
                
                // 获取当前价格
                Double currentPrice = currentPrices.get(symbol);
                if (currentPrice != null && currentPrice > 0) {
                    pos.put("currentPrice", currentPrice);
                    
                    // 计算未实现盈亏
                    Double posPnl;
                    if (portfolioDO != null && portfolioDO.getUnrealizedProfit() != null && portfolioDO.getUnrealizedProfit() != 0) {
                        posPnl = portfolioDO.getUnrealizedProfit();
                    } else {
                        if ("LONG".equals(positionSide)) {
                            posPnl = (currentPrice - avgPrice) * positionAmt;
                        } else {
                            posPnl = (avgPrice - currentPrice) * positionAmt;
                        }
                    }
                    pos.put("pnl", posPnl);
                    unrealizedPnl += posPnl;
                } else {
                    pos.put("currentPrice", null);
                    Double storedPnl = (portfolioDO != null && portfolioDO.getUnrealizedProfit() != null) ? portfolioDO.getUnrealizedProfit() : 0.0;
                    pos.put("pnl", storedPnl);
                    unrealizedPnl += storedPnl;
                }
                
                // 计算已用保证金
                if (leverage != null && leverage > 0) {
                    marginUsed += (positionAmt * avgPrice) / leverage;
                }
                
                // 计算持仓价值
                positionsValue += positionAmt * avgPrice;
            }
            
            Double initialCapital = model.getInitialCapital() != null ? model.getInitialCapital() : 10000.0;
            Double cash = initialCapital + realizedPnl - marginUsed;
            Double totalValue = initialCapital + realizedPnl + unrealizedPnl;
            
            Map<String, Object> portfolio = new LinkedHashMap<>();
            portfolio.put("modelId", modelId);
            portfolio.put("initialCapital", initialCapital);
            portfolio.put("cash", cash);
            portfolio.put("positions", positions);
            portfolio.put("positionsValue", positionsValue);
            portfolio.put("marginUsed", marginUsed);
            portfolio.put("totalValue", totalValue);
            portfolio.put("realizedPnl", realizedPnl);
            portfolio.put("unrealizedPnl", unrealizedPnl);
            
            // 获取账户价值历史
            List<Map<String, Object>> accountValueHistory = accountValueHistoryMapper.selectHistoryByModelId(modelId, 100);
            
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("portfolio", portfolio);
            result.put("accountValueHistory", accountValueHistory);
            result.put("autoBuyEnabled", model.getAutoBuyEnabled() != null ? model.getAutoBuyEnabled() : true);
            result.put("autoSellEnabled", model.getAutoSellEnabled() != null ? model.getAutoSellEnabled() : true);
            result.put("leverage", model.getLeverage() != null ? model.getLeverage() : 10);
            
            return result;
        } catch (Exception e) {
            log.error("[ModelService] 获取投资组合数据失败: {}", e.getMessage(), e);
            throw new RuntimeException("获取投资组合数据失败: " + e.getMessage(), e);
        }
    }

    @Override
    public Map<String, Object> getModelPortfolioSymbols(String modelId) {
        log.info("[ModelService] 获取持仓合约symbol列表, modelId={}", modelId);
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
            
            // 从持仓数据中提取去重的 symbol 列表
            List<String> symbols = portfolioDOList.stream()
                    .map(PortfolioDO::getSymbol)
                    .filter(s -> s != null && !s.isEmpty())
                    .map(String::toUpperCase)
                    .distinct()
                    .sorted()
                    .collect(Collectors.toList());
            
            if (symbols.isEmpty()) {
                Map<String, Object> result = new HashMap<>();
                result.put("data", new ArrayList<>());
                return result;
            }
            
            // 从MarketService获取完整的市场数据（包括涨跌幅和成交量）
            Map<String, Map<String, Object>> marketData = marketService.getMarketPrices();
            
            // 构建响应数据
            List<Map<String, Object>> result = new ArrayList<>();
            for (String symbol : symbols) {
                Map<String, Object> dbInfo = marketData.get(symbol);
                if (dbInfo == null) {
                    dbInfo = new HashMap<>();
                }
                
                Map<String, Object> symbolData = new HashMap<>();
                symbolData.put("symbol", symbol);
                symbolData.put("price", dbInfo.getOrDefault("price", 0.0));
                symbolData.put("change", dbInfo.getOrDefault("change_24h", dbInfo.getOrDefault("change", 0.0)));
                symbolData.put("changePercent", dbInfo.getOrDefault("change_24h", dbInfo.getOrDefault("changePercent", 0.0)));
                symbolData.put("volume", dbInfo.getOrDefault("daily_volume", dbInfo.getOrDefault("volume", 0.0)));
                symbolData.put("quoteVolume", dbInfo.getOrDefault("daily_volume", dbInfo.getOrDefault("quote_volume", dbInfo.getOrDefault("quoteVolume", 0.0))));
                symbolData.put("high", dbInfo.getOrDefault("high", 0.0));
                symbolData.put("low", dbInfo.getOrDefault("low", 0.0));
                result.add(symbolData);
            }
            
            Map<String, Object> response = new HashMap<>();
            response.put("data", result);
            return response;
        } catch (Exception e) {
            log.error("[ModelService] 获取持仓合约symbol列表失败: {}", e.getMessage(), e);
            Map<String, Object> result = new HashMap<>();
            result.put("data", new ArrayList<>());
            return result;
        }
    }

    @Override
    public List<Map<String, Object>> getTrades(String modelId, Integer limit) {
        log.info("[ModelService] 获取交易历史记录, modelId={}, limit={}", modelId, limit);
        try {
            if (limit == null) {
                limit = defaultTradesQueryLimit;
            }
            
            List<TradeDO> tradeDOList = tradeMapper.selectTradesByModelId(modelId, limit);
            List<Map<String, Object>> trades = new ArrayList<>();
            
            // 获取交易记录中涉及的symbol列表
            List<String> symbols = tradeDOList.stream()
                    .map(trade -> trade.getFuture() != null ? trade.getFuture().toUpperCase() : "")
                    .filter(s -> !s.isEmpty())
                    .distinct()
                    .collect(Collectors.toList());
            
            // 获取实时价格
            Map<String, Map<String, Object>> pricesData = new HashMap<>();
            if (!symbols.isEmpty()) {
                pricesData = marketService.getMarketPrices();
            }
            
            // 转换并格式化交易记录
            for (TradeDO tradeDO : tradeDOList) {
                Map<String, Object> trade = new HashMap<>();
                trade.put("id", tradeDO.getId());
                trade.put("modelId", tradeDO.getModelId());
                trade.put("future", tradeDO.getFuture());
                trade.put("symbol", tradeDO.getFuture()); // 兼容字段
                trade.put("signal", tradeDO.getSignal());
                trade.put("price", tradeDO.getPrice());
                trade.put("quantity", tradeDO.getQuantity());
                trade.put("pnl", tradeDO.getPnl() != null ? tradeDO.getPnl() : 0.0);
                trade.put("message", tradeDO.getMessage());
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
                if (symbol != null && (signal != null && (signal.equals("buy_to_enter") || signal.equals("sell_to_enter")))) {
                    if (tradeDO.getPnl() == null || tradeDO.getPnl() == 0) {
                        // 如果数据库中的pnl为0，说明可能还没有平仓，使用实时价格计算
                        String contractSymbol = symbol.toUpperCase();
                        if (!contractSymbol.endsWith("USDT")) {
                            contractSymbol = contractSymbol + "USDT";
                        }
                        Map<String, Object> priceInfo = pricesData.get(symbol.toUpperCase());
                        if (priceInfo != null && priceInfo.get("price") != null) {
                            Double currentPrice = ((Number) priceInfo.get("price")).doubleValue();
                            trade.put("current_price", currentPrice);
                            
                            if (currentPrice > 0 && tradeDO.getPrice() != null && tradeDO.getPrice() > 0) {
                                Double quantity = Math.abs(tradeDO.getQuantity() != null ? tradeDO.getQuantity() : 0.0);
                                Double calculatedPnl;
                                if (signal.equals("buy_to_enter")) {
                                    // 开多：盈亏 = (当前价 - 开仓价) * 数量
                                    calculatedPnl = (currentPrice - tradeDO.getPrice()) * quantity;
                                } else {
                                    // 开空：盈亏 = (开仓价 - 当前价) * 数量
                                    calculatedPnl = (tradeDO.getPrice() - currentPrice) * quantity;
                                }
                                trade.put("pnl", calculatedPnl);
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
                
                trades.add(trade);
            }
            
            return trades;
        } catch (Exception e) {
            log.error("[ModelService] 获取交易历史记录失败: {}", e.getMessage(), e);
            return new ArrayList<>();
        }
    }

    @Override
    public List<Map<String, Object>> getConversations(String modelId, Integer limit) {
        log.info("[ModelService] 获取对话历史记录, modelId={}, limit={}", modelId, limit);
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
                
                conversation.put("conversationType", conversationDO.getConversationType());
                conversation.put("conversation_type", conversationDO.getConversationType()); // snake_case格式
                conversation.put("tokens", conversationDO.getTokens());
                
                // 格式化timestamp字段为字符串（北京时间）
                if (conversationDO.getCreatedAt() != null) {
                    String timestamp = conversationDO.getCreatedAt().format(DATETIME_FORMATTER);
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
        log.info("[ModelService] 获取模型提示词配置, modelId={}", modelId);
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
        log.info("[ModelService] 更新模型提示词配置, modelId={}", modelId);
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
        log.info("[ModelService] 更新模型批次配置, modelId={}", modelId);
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
            
            updateWrapper.set("updated_at", LocalDateTime.now());
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
        log.info("[ModelService] 更新模型最大持仓数量, modelId={}, maxPositions={}", modelId, maxPositions);
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
            updateWrapper.set("updated_at", LocalDateTime.now());
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
        log.info("[ModelService] 更新模型杠杆倍数, modelId={}, leverage={}", modelId, leverage);
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
            updateWrapper.set("updated_at", LocalDateTime.now());
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
        log.info("[ModelService] 更新模型提供方和模型名称, modelId={}, providerId={}, modelName={}", modelId, providerId, modelName);
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
            updateWrapper.set("updated_at", LocalDateTime.now());
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
        log.info("[ModelService] 设置模型自动交易开关, modelId={}, autoBuyEnabled={}, autoSellEnabled={}", 
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
            updateWrapper.set("updated_at", LocalDateTime.now());
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
        log.info("[ModelService] 获取聚合投资组合数据");
        try {
            Map<String, Map<String, Object>> pricesData = marketService.getMarketPrices();
            Map<String, Double> currentPrices = new HashMap<>();
            for (Map.Entry<String, Map<String, Object>> entry : pricesData.entrySet()) {
                Object priceObj = entry.getValue().get("price");
                if (priceObj != null) {
                    currentPrices.put(entry.getKey(), ((Number) priceObj).doubleValue());
                }
            }
            
            List<ModelDO> models = modelMapper.selectAllModels();
            Map<String, Object> totalPortfolio = new LinkedHashMap<>();
            totalPortfolio.put("totalValue", 0.0);
            totalPortfolio.put("cash", 0.0);
            totalPortfolio.put("positionsValue", 0.0);
            totalPortfolio.put("realizedPnl", 0.0);
            totalPortfolio.put("unrealizedPnl", 0.0);
            totalPortfolio.put("initialCapital", 0.0);
            totalPortfolio.put("positions", new ArrayList<>());
            
            Map<String, Map<String, Object>> allPositions = new HashMap<>();
            
            for (ModelDO model : models) {
                Map<String, Object> portfolio = getPortfolio(model.getId());
                if (portfolio != null && portfolio.containsKey("portfolio")) {
                    @SuppressWarnings("unchecked")
                    Map<String, Object> portfolioData = (Map<String, Object>) portfolio.get("portfolio");
                    
                    totalPortfolio.put("totalValue", ((Number) totalPortfolio.get("totalValue")).doubleValue() + 
                            ((Number) portfolioData.getOrDefault("totalValue", 0.0)).doubleValue());
                    totalPortfolio.put("cash", ((Number) totalPortfolio.get("cash")).doubleValue() + 
                            ((Number) portfolioData.getOrDefault("cash", 0.0)).doubleValue());
                    totalPortfolio.put("positionsValue", ((Number) totalPortfolio.get("positionsValue")).doubleValue() + 
                            ((Number) portfolioData.getOrDefault("positionsValue", 0.0)).doubleValue());
                    totalPortfolio.put("realizedPnl", ((Number) totalPortfolio.get("realizedPnl")).doubleValue() + 
                            ((Number) portfolioData.getOrDefault("realizedPnl", 0.0)).doubleValue());
                    totalPortfolio.put("unrealizedPnl", ((Number) totalPortfolio.get("unrealizedPnl")).doubleValue() + 
                            ((Number) portfolioData.getOrDefault("unrealizedPnl", 0.0)).doubleValue());
                    totalPortfolio.put("initialCapital", ((Number) totalPortfolio.get("initialCapital")).doubleValue() + 
                            ((Number) portfolioData.getOrDefault("initialCapital", 0.0)).doubleValue());
                    
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
                            Double currentAmt = ((Number) currentPos.get("positionAmt")).doubleValue();
                            Double currentAvgPrice = ((Number) currentPos.get("avgPrice")).doubleValue();
                            Double newAmt = Math.abs(((Number) pos.get("positionAmt")).doubleValue());
                            Double newAvgPrice = ((Number) pos.get("avgPrice")).doubleValue();
                            
                            Double currentCost = currentAmt * currentAvgPrice;
                            Double newCost = newAmt * newAvgPrice;
                            Double totalAmt = currentAmt + newAmt;
                            
                            if (totalAmt > 0) {
                                currentPos.put("avgPrice", (currentCost + newCost) / totalAmt);
                                currentPos.put("positionAmt", totalAmt);
                                currentPos.put("totalCost", currentCost + newCost);
                                
                                Double currentPrice = currentPrices.get(symbol);
                                if (currentPrice == null) {
                                    currentPrice = ((Number) pos.getOrDefault("currentPrice", 0.0)).doubleValue();
                                }
                                if (currentPrice > 0) {
                                    currentPos.put("currentPrice", currentPrice);
                                    currentPos.put("pnl", (currentPrice - ((Number) currentPos.get("avgPrice")).doubleValue()) * totalAmt);
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
        log.info("[ModelService] 执行交易周期（同时执行买入和卖出）, modelId={}", modelId);
        Map<String, Object> result = new HashMap<>();
        try {
            // 检查模型是否存在
            ModelDTO model = getModelById(modelId);
            if (model == null) {
                result.put("success", false);
                result.put("error", "Model not found");
                return result;
            }

            // 启用自动交易
            setModelAutoTrading(modelId, true, true);

            // 调用trade服务执行买入和卖出
            Map<String, Object> buyResult = tradeServiceClient.executeBuyTrading(modelId);
            Map<String, Object> sellResult = tradeServiceClient.executeSellTrading(modelId);

            // 合并结果
            result.put("success", true);
            result.put("buy_result", buyResult);
            result.put("sell_result", sellResult);
            result.put("message", "Trading execution completed");
            
            return result;
        } catch (Exception e) {
            log.error("[ModelService] 执行交易失败: {}", e.getMessage(), e);
            result.put("success", false);
            result.put("error", e.getMessage());
            return result;
        }
    }

    @Override
    public Map<String, Object> executeBuyTrading(String modelId) {
        log.info("[ModelService] 执行买入交易周期, modelId={}", modelId);
        try {
            // 检查模型是否存在
            ModelDTO model = getModelById(modelId);
            if (model == null) {
                Map<String, Object> errorResult = new HashMap<>();
                errorResult.put("success", false);
                errorResult.put("error", "Model not found");
                return errorResult;
            }

            // 调用trade服务执行买入
            return tradeServiceClient.executeBuyTrading(modelId);
        } catch (Exception e) {
            log.error("[ModelService] 执行买入交易失败: {}", e.getMessage(), e);
            Map<String, Object> errorResult = new HashMap<>();
            errorResult.put("success", false);
            errorResult.put("error", e.getMessage());
            return errorResult;
        }
    }

    @Override
    public Map<String, Object> executeSellTrading(String modelId) {
        log.info("[ModelService] 执行卖出交易周期, modelId={}", modelId);
        try {
            // 检查模型是否存在
            ModelDTO model = getModelById(modelId);
            if (model == null) {
                Map<String, Object> errorResult = new HashMap<>();
                errorResult.put("success", false);
                errorResult.put("error", "Model not found");
                return errorResult;
            }

            // 调用trade服务执行卖出
            return tradeServiceClient.executeSellTrading(modelId);
        } catch (Exception e) {
            log.error("[ModelService] 执行卖出交易失败: {}", e.getMessage(), e);
            Map<String, Object> errorResult = new HashMap<>();
            errorResult.put("success", false);
            errorResult.put("error", e.getMessage());
            return errorResult;
        }
    }

    @Override
    public Map<String, Object> disableBuyTrading(String modelId) {
        log.info("[ModelService] 禁用自动买入, modelId={}", modelId);
        try {
            // 检查模型是否存在
            ModelDTO model = getModelById(modelId);
            if (model == null) {
                Map<String, Object> errorResult = new HashMap<>();
                errorResult.put("success", false);
                errorResult.put("error", "Model not found");
                return errorResult;
            }

            // 调用trade服务禁用自动买入
            return tradeServiceClient.disableBuyTrading(modelId);
        } catch (Exception e) {
            log.error("[ModelService] 禁用自动买入失败: {}", e.getMessage(), e);
            Map<String, Object> errorResult = new HashMap<>();
            errorResult.put("success", false);
            errorResult.put("error", e.getMessage());
            return errorResult;
        }
    }

    @Override
    public Map<String, Object> disableSellTrading(String modelId) {
        log.info("[ModelService] 禁用自动卖出, modelId={}", modelId);
        try {
            // 检查模型是否存在
            ModelDTO model = getModelById(modelId);
            if (model == null) {
                Map<String, Object> errorResult = new HashMap<>();
                errorResult.put("success", false);
                errorResult.put("error", "Model not found");
                return errorResult;
            }

            // 调用trade服务禁用自动卖出
            return tradeServiceClient.disableSellTrading(modelId);
        } catch (Exception e) {
            log.error("[ModelService] 禁用自动卖出失败: {}", e.getMessage(), e);
            Map<String, Object> errorResult = new HashMap<>();
            errorResult.put("success", false);
            errorResult.put("error", e.getMessage());
            return errorResult;
        }
    }

}