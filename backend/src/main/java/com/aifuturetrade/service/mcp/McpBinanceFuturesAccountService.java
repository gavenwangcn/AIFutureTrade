package com.aifuturetrade.service.mcp;

import java.util.List;
import java.util.Map;

public interface McpBinanceFuturesAccountService {

    List<Map<String, Object>> balance(String modelId);

    List<Map<String, Object>> positions(String modelId);

    Map<String, Object> accountInfo(String modelId);
}

