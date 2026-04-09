package com.aifuturetrade.service.mcp.impl;

import com.aifuturetrade.common.api.binance.BinanceConfig;
import com.aifuturetrade.common.api.binance.BinanceFuturesAccountClient;
import com.aifuturetrade.dao.entity.ModelDO;
import com.aifuturetrade.dao.mapper.ModelMapper;
import com.aifuturetrade.service.mcp.McpBinanceFuturesAccountService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.Collections;
import java.util.List;
import java.util.Map;

@Slf4j
@Service
public class McpBinanceFuturesAccountServiceImpl implements McpBinanceFuturesAccountService {

    @Autowired
    private ModelMapper modelMapper;

    @Autowired
    private BinanceConfig binanceConfig;

    private ModelDO requireModel(String modelId) {
        ModelDO model = modelMapper.selectById(modelId);
        if (model == null) {
            throw new IllegalArgumentException("未找到模型记录，modelId: " + modelId);
        }
        return model;
    }

    private BinanceFuturesAccountClient buildAccountClient(ModelDO model) {
        if (model.getApiKey() == null || model.getApiSecret() == null) {
            throw new IllegalArgumentException("模型缺少API密钥信息，modelId: " + model.getId());
        }
        return new BinanceFuturesAccountClient(
                model.getApiKey(),
                model.getApiSecret(),
                binanceConfig.getQuoteAsset(),
                binanceConfig.getBaseUrl(),
                binanceConfig.getTestnet(),
                binanceConfig.getConnectTimeout(),
                binanceConfig.getReadTimeout()
        );
    }

    @Override
    public List<Map<String, Object>> balance(String modelId) {
        ModelDO model = requireModel(modelId);
        BinanceFuturesAccountClient client = buildAccountClient(model);
        return client.getBalance();
    }

    @Override
    @SuppressWarnings("unchecked")
    public List<Map<String, Object>> positions(String modelId) {
        Map<String, Object> account = accountInfo(modelId);
        Object positions = account.get("positions");
        if (positions instanceof List) {
            return (List<Map<String, Object>>) positions;
        }
        return Collections.emptyList();
    }

    @Override
    public Map<String, Object> accountInfo(String modelId) {
        ModelDO model = requireModel(modelId);
        BinanceFuturesAccountClient client = buildAccountClient(model);
        return client.getAccount();
    }
}

