package com.aifuturetrade.common.api.binance;

import com.binance.connector.client.common.ApiResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.AccountInformationV2Response;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.AccountInformationV3Response;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.FuturesAccountBalanceV2Response;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.FuturesAccountBalanceV2ResponseInner;
import lombok.extern.slf4j.Slf4j;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 币安期货账户客户端 - 专注于账户功能的客户端
 * 
 * 提供获取账户信息、账户资产等功能，支持传入不同的api_key和api_secret进行操作。
 * 主要用于账户管理和资产查询。
 * 
 * 参考 Binance 官方示例：
 * https://github.com/binance/binance-connector-java/tree/master/clients/derivatives-trading-usds-futures
 */
@Slf4j
public class BinanceFuturesAccountClient extends BinanceFuturesBase {
    
    /**
     * 构造函数，初始化币安期货账户客户端
     * 
     * @param apiKey 币安API密钥
     * @param apiSecret 币安API密钥
     * @param quoteAsset 计价资产，默认为USDT
     * @param baseUrl 自定义REST API基础路径（可选）
     * @param testnet 是否使用测试网络，默认False
     * @param connectTimeout 连接超时时间（毫秒），默认10000ms
     * @param readTimeout 读取超时时间（毫秒），默认50000ms
     */
    public BinanceFuturesAccountClient(String apiKey, String apiSecret, String quoteAsset, 
                                       String baseUrl, Boolean testnet,
                                       Integer connectTimeout, Integer readTimeout) {
        this.quoteAsset = (quoteAsset != null ? quoteAsset : "USDT").toUpperCase();
        initRestApi(apiKey, apiSecret, null, null, baseUrl, connectTimeout, readTimeout);
    }
    
    /**
     * 构造函数，使用默认配置
     */
    public BinanceFuturesAccountClient(String apiKey, String apiSecret) {
        this(apiKey, apiSecret, "USDT", null, false, null, null);
    }
    
    /**
     * 获取账户信息
     * 
     * 参考 API: GET /fapi/v3/account
     * https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V3
     * 
     * @return 账户信息的Map对象
     */
    public Map<String, Object> getAccount() {
        try {
            log.info("[BinanceFuturesAccountClient] 开始获取账户信息");
            // 调用SDK API获取账户信息 - 使用null作为recvWindow参数（可选）
            ApiResponse<AccountInformationV3Response> response = restApi.accountInformationV3((Long) null);
            
            // 直接使用SDK的getData()方法获取响应数据
            AccountInformationV3Response accountData = response.getData();
            if (accountData == null) {
                throw new RuntimeException("API调用返回null，请检查API调用方式");
            }
            
            // 直接使用SDK对象的getter方法构建Map
            Map<String, Object> accountInfo = new HashMap<>();
            accountInfo.put("totalInitialMargin", accountData.getTotalInitialMargin());
            accountInfo.put("totalMaintMargin", accountData.getTotalMaintMargin());
            accountInfo.put("totalWalletBalance", accountData.getTotalWalletBalance());
            accountInfo.put("totalUnrealizedProfit", accountData.getTotalUnrealizedProfit());
            accountInfo.put("totalMarginBalance", accountData.getTotalMarginBalance());
            accountInfo.put("totalPositionInitialMargin", accountData.getTotalPositionInitialMargin());
            accountInfo.put("totalOpenOrderInitialMargin", accountData.getTotalOpenOrderInitialMargin());
            accountInfo.put("totalCrossWalletBalance", accountData.getTotalCrossWalletBalance());
            accountInfo.put("totalCrossUnPnl", accountData.getTotalCrossUnPnl());
            accountInfo.put("availableBalance", accountData.getAvailableBalance());
            accountInfo.put("maxWithdrawAmount", accountData.getMaxWithdrawAmount());
            accountInfo.put("assets", accountData.getAssets());
            accountInfo.put("positions", accountData.getPositions());
            
            log.info("[BinanceFuturesAccountClient] 账户信息获取成功");
            return accountInfo;
        } catch (Exception e) {
            log.error("[BinanceFuturesAccountClient] 获取账户信息失败: {}", e.getMessage(), e);
            throw new RuntimeException("获取账户信息失败: " + e.getMessage(), e);
        }
    }
    
    /**
     * 获取账户信息（V2版本）
     * 
     * 参考 API: GET /fapi/v2/account
     * https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V2
     * 
     * @return 账户信息的Map对象
     */
    public Map<String, Object> getAccountV2() {
        try {
            log.info("[BinanceFuturesAccountClient] 开始获取账户信息（V2）");
            // 调用SDK API获取账户信息V2 - 使用null作为recvWindow参数（可选）
            ApiResponse<AccountInformationV2Response> response = restApi.accountInformationV2((Long) null);
            
            // 直接使用SDK的getData()方法获取响应数据
            AccountInformationV2Response accountData = response.getData();
            if (accountData == null) {
                throw new RuntimeException("API调用返回null，请检查API调用方式");
            }
            
            // 直接使用SDK对象的getter方法构建Map（AccountInformationV2Response有很多字段，这里只列出主要字段）
            Map<String, Object> accountInfo = new HashMap<>();
            accountInfo.put("feeTier", accountData.getFeeTier());
            accountInfo.put("feeBurn", accountData.getFeeBurn());
            accountInfo.put("canDeposit", accountData.getCanDeposit());
            accountInfo.put("canWithdraw", accountData.getCanWithdraw());
            accountInfo.put("updateTime", accountData.getUpdateTime());
            accountInfo.put("multiAssetsMargin", accountData.getMultiAssetsMargin());
            accountInfo.put("tradeGroupId", accountData.getTradeGroupId());
            accountInfo.put("totalInitialMargin", accountData.getTotalInitialMargin());
            accountInfo.put("totalMaintMargin", accountData.getTotalMaintMargin());
            accountInfo.put("totalWalletBalance", accountData.getTotalWalletBalance());
            accountInfo.put("totalUnrealizedProfit", accountData.getTotalUnrealizedProfit());
            accountInfo.put("totalMarginBalance", accountData.getTotalMarginBalance());
            accountInfo.put("totalPositionInitialMargin", accountData.getTotalPositionInitialMargin());
            accountInfo.put("totalOpenOrderInitialMargin", accountData.getTotalOpenOrderInitialMargin());
            accountInfo.put("totalCrossWalletBalance", accountData.getTotalCrossWalletBalance());
            accountInfo.put("totalCrossUnPnl", accountData.getTotalCrossUnPnl());
            accountInfo.put("availableBalance", accountData.getAvailableBalance());
            accountInfo.put("maxWithdrawAmount", accountData.getMaxWithdrawAmount());
            accountInfo.put("assets", accountData.getAssets());
            accountInfo.put("positions", accountData.getPositions());
            
            log.info("[BinanceFuturesAccountClient] 账户信息获取成功（V2）");
            return accountInfo;
        } catch (Exception e) {
            log.error("[BinanceFuturesAccountClient] 获取账户信息失败（V2）: {}", e.getMessage(), e);
            throw new RuntimeException("获取账户信息失败（V2）: " + e.getMessage(), e);
        }
    }
    
    /**
     * 获取账户余额
     * 
     * 参考 API: GET /fapi/v2/balance
     * https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V2
     * 
     * @return 账户余额列表
     */
    public List<Map<String, Object>> getBalance() {
        try {
            log.info("[BinanceFuturesAccountClient] 开始获取账户余额");
            // 调用SDK API获取账户余额 - 使用null作为recvWindow参数（可选）
            ApiResponse<FuturesAccountBalanceV2Response> response = restApi.futuresAccountBalanceV2((Long) null);
            
            // 直接使用SDK的getData()方法获取响应数据
            // FuturesAccountBalanceV2Response继承自ArrayList<FuturesAccountBalanceV2ResponseInner>
            FuturesAccountBalanceV2Response balanceList = response.getData();
            if (balanceList == null) {
                throw new RuntimeException("API调用返回null，请检查API调用方式");
            }
            
            // 直接使用SDK对象的getter方法构建Map列表
            List<Map<String, Object>> result = new ArrayList<>();
            for (FuturesAccountBalanceV2ResponseInner item : balanceList) {
                Map<String, Object> balanceMap = new HashMap<>();
                balanceMap.put("accountAlias", item.getAccountAlias());
                balanceMap.put("asset", item.getAsset());
                balanceMap.put("balance", item.getBalance());
                balanceMap.put("crossWalletBalance", item.getCrossWalletBalance());
                balanceMap.put("crossUnPnl", item.getCrossUnPnl());
                balanceMap.put("availableBalance", item.getAvailableBalance());
                balanceMap.put("maxWithdrawAmount", item.getMaxWithdrawAmount());
                balanceMap.put("marginAvailable", item.getMarginAvailable());
                balanceMap.put("updateTime", item.getUpdateTime());
                result.add(balanceMap);
            }
            
            log.info("[BinanceFuturesAccountClient] 账户余额获取成功，共 {} 条记录", result.size());
            return result;
        } catch (Exception e) {
            log.error("[BinanceFuturesAccountClient] 获取账户余额失败: {}", e.getMessage(), e);
            throw new RuntimeException("获取账户余额失败: " + e.getMessage(), e);
        }
    }
}

