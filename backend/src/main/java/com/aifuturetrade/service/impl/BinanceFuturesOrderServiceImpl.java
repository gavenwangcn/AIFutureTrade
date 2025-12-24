package com.aifuturetrade.service.impl;

import com.aifuturetrade.common.api.binance.BinanceConfig;
import com.aifuturetrade.common.api.binance.BinanceFuturesOrderClient;
import com.aifuturetrade.dao.entity.BinanceTradeLogDO;
import com.aifuturetrade.dao.entity.ModelDO;
import com.aifuturetrade.dao.entity.PortfolioDO;
import com.aifuturetrade.dao.entity.TradeDO;
import com.aifuturetrade.dao.mapper.BinanceTradeLogMapper;
import com.aifuturetrade.dao.mapper.ModelMapper;
import com.aifuturetrade.dao.mapper.PortfolioMapper;
import com.aifuturetrade.dao.mapper.TradeMapper;
import com.aifuturetrade.service.BinanceFuturesOrderService;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
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
    private BinanceConfig binanceConfig;

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> sellPosition(String modelId, String symbol) {
        log.info("[BinanceFuturesOrderService] 开始一键卖出持仓合约，modelId: {}, symbol: {}", modelId, symbol);
        
        try {
            // 1. 查询持仓记录
            PortfolioDO portfolio = portfolioMapper.selectByModelIdAndSymbol(modelId, symbol, null);
            if (portfolio == null) {
                throw new RuntimeException("未找到持仓记录，modelId: " + modelId + ", symbol: " + symbol);
            }

            log.info("[BinanceFuturesOrderService] 找到持仓记录: positionSide={}, positionAmt={}", 
                    portfolio.getPositionSide(), portfolio.getPositionAmt());

            // 2. 查询模型信息以获取api_key和api_secret
            ModelDO model = modelMapper.selectById(modelId);
            if (model == null) {
                throw new RuntimeException("未找到模型记录，modelId: " + modelId);
            }
            if (model.getApiKey() == null || model.getApiSecret() == null) {
                throw new RuntimeException("模型缺少API密钥信息，modelId: " + modelId);
            }

            log.info("[BinanceFuturesOrderService] 获取模型API密钥信息成功");

            // 3. 获取实时价格（使用BinanceFuturesOrderClient的getOrderBookTicker方法）
            String formattedSymbol = symbol.toUpperCase();
            if (!formattedSymbol.endsWith(binanceConfig.getQuoteAsset())) {
                formattedSymbol = formattedSymbol + binanceConfig.getQuoteAsset();
            }
            
            BinanceFuturesOrderClient priceClient = new BinanceFuturesOrderClient(
                    model.getApiKey(),
                    model.getApiSecret(),
                    binanceConfig.getQuoteAsset(),
                    binanceConfig.getBaseUrl(),
                    binanceConfig.getTestnet()
            );
            
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

            // 4. 计算反方向的positionSide
            String oppositePositionSide = "LONG".equalsIgnoreCase(portfolio.getPositionSide()) ? "SHORT" : "LONG";
            String signal = "LONG".equalsIgnoreCase(portfolio.getPositionSide()) ? "sell_to_long" : "sell_to_short";

            log.info("[BinanceFuturesOrderService] 计算持仓方向: 原方向={}, 反方向={}, signal={}", 
                    portfolio.getPositionSide(), oppositePositionSide, signal);

            // 5. 插入trades表记录
            TradeDO trade = new TradeDO();
            trade.setModelId("system_user");
            trade.setFuture(symbol);
            trade.setSignal(signal);
            trade.setPrice(currentPrice);
            trade.setQuantity(Math.abs(portfolio.getPositionAmt()));
            trade.setTimestamp(LocalDateTime.now());
            tradeMapper.insert(trade);

            log.info("[BinanceFuturesOrderService] 插入trades表记录成功: tradeId={}", trade.getId());

            // 6. 删除portfolios表记录
            portfolioMapper.deleteById(portfolio.getId());

            log.info("[BinanceFuturesOrderService] 删除portfolios表记录成功: portfolioId={}", portfolio.getId());

            // 7. 调用SDK执行卖出
            BinanceFuturesOrderClient orderClient = new BinanceFuturesOrderClient(
                    model.getApiKey(),
                    model.getApiSecret(),
                    binanceConfig.getQuoteAsset(),
                    binanceConfig.getBaseUrl(),
                    binanceConfig.getTestnet()
            );

            Map<String, Object> orderParams = new HashMap<>();
            orderParams.put("symbol", formattedSymbol);
            orderParams.put("side", "SELL");
            orderParams.put("quantity", Math.abs(portfolio.getPositionAmt()));
            orderParams.put("orderType", "MARKET");
            orderParams.put("positionSide", oppositePositionSide);
            orderParams.put("testMode", true);

            log.info("[BinanceFuturesOrderService] 调用SDK执行卖出，参数: {}", orderParams);

            Map<String, Object> sdkResponse = null;
            String errorContext = null;
            String responseType = "200";
            
            try {
                sdkResponse = orderClient.marketTrade(
                        formattedSymbol,
                        "SELL",
                        Math.abs(portfolio.getPositionAmt()),
                        "MARKET",
                        oppositePositionSide,
                        true
                );
                log.info("[BinanceFuturesOrderService] SDK调用成功: {}", sdkResponse);
            } catch (Exception e) {
                log.error("[BinanceFuturesOrderService] SDK调用失败: {}", e.getMessage(), e);
                errorContext = e.getMessage();
                responseType = "500";
                throw e; // 抛出异常以触发事务回滚
            }

            // 8. 记录binance_trade_logs
            BinanceTradeLogDO tradeLog = new BinanceTradeLogDO();
            tradeLog.setModelId("system_user");
            tradeLog.setTradeId(trade.getId());
            tradeLog.setType("test");
            tradeLog.setMethodName("marketTrade");
            
            try {
                tradeLog.setParam(objectMapper.writeValueAsString(orderParams));
                if (sdkResponse != null) {
                    tradeLog.setResponseContext(objectMapper.writeValueAsString(sdkResponse));
                }
                tradeLog.setResponseType(responseType);
                if (errorContext != null) {
                    tradeLog.setErrorContext(errorContext);
                }
            } catch (Exception e) {
                log.warn("[BinanceFuturesOrderService] 序列化参数失败: {}", e.getMessage());
            }
            
            tradeLog.setCreatedAt(LocalDateTime.now());
            binanceTradeLogMapper.insert(tradeLog);

            log.info("[BinanceFuturesOrderService] 记录binance_trade_logs成功: logId={}", tradeLog.getId());

            // 9. 返回结果
            Map<String, Object> result = new HashMap<>();
            result.put("success", true);
            result.put("message", "卖出成功");
            result.put("tradeId", trade.getId());
            result.put("symbol", symbol);
            result.put("quantity", Math.abs(portfolio.getPositionAmt()));
            result.put("price", currentPrice);
            result.put("positionSide", portfolio.getPositionSide());
            
            log.info("[BinanceFuturesOrderService] 一键卖出完成，modelId: {}, symbol: {}", modelId, symbol);
            
            return result;
            
        } catch (Exception e) {
            log.error("[BinanceFuturesOrderService] 一键卖出失败，modelId: {}, symbol: {}, error: {}", 
                    modelId, symbol, e.getMessage(), e);
            throw new RuntimeException("一键卖出失败: " + e.getMessage(), e);
        }
    }
}

