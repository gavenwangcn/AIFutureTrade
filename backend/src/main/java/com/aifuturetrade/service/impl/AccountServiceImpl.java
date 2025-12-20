package com.aifuturetrade.service.impl;

import com.aifuturetrade.common.api.binance.BinanceConfig;
import com.aifuturetrade.common.api.binance.BinanceFuturesAccountClient;
import com.aifuturetrade.dao.entity.AccountAssetDO;
import com.aifuturetrade.dao.mapper.AccountAssetMapper;
import com.aifuturetrade.service.AccountService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.security.MessageDigest;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 业务逻辑实现类：账户管理服务
 */
@Slf4j
@Service
public class AccountServiceImpl implements AccountService {

    @Autowired
    private AccountAssetMapper accountAssetMapper;

    @Autowired
    private BinanceConfig binanceConfig;

    @Override
    public List<Map<String, Object>> getAllAccounts() {
        log.info("[AccountService] 查询所有账户信息");
        try {
            List<Map<String, Object>> accounts = accountAssetMapper.selectAllAccounts();
            List<Map<String, Object>> result = new ArrayList<>();
            for (Map<String, Object> account : accounts) {
                Map<String, Object> formatted = new HashMap<>();
                formatted.put("account_alias", account.get("account_alias"));
                formatted.put("account_name", account.get("account_name"));
                formatted.put("balance", account.get("total_wallet_balance"));
                formatted.put("crossWalletBalance", account.get("total_cross_wallet_balance"));
                formatted.put("availableBalance", account.get("available_balance"));
                formatted.put("update_time", account.get("update_time"));
                formatted.put("created_at", account.get("created_at"));
                result.add(formatted);
            }
            return result;
        } catch (Exception e) {
            log.error("[AccountService] 查询所有账户信息失败: {}", e.getMessage(), e);
            throw new RuntimeException("查询账户信息失败: " + e.getMessage(), e);
        }
    }

    @Override
    @Transactional
    public Map<String, Object> addAccount(Map<String, Object> accountData) {
        log.info("[AccountService] 添加新账户");
        try {
            String accountName = (String) accountData.get("account_name");
            String apiKey = (String) accountData.get("api_key");
            String apiSecret = (String) accountData.get("api_secret");

            if (accountName == null || accountName.trim().isEmpty()) {
                throw new IllegalArgumentException("account_name is required");
            }
            if (apiKey == null || apiKey.trim().isEmpty() || apiSecret == null || apiSecret.trim().isEmpty()) {
                throw new IllegalArgumentException("api_key and api_secret are required");
            }

            // 1. 创建 BinanceFuturesAccountClient 对象
            BinanceFuturesAccountClient client = new BinanceFuturesAccountClient(
                    apiKey,
                    apiSecret,
                    binanceConfig.getQuoteAsset(),
                    binanceConfig.getBaseUrl(),
                    binanceConfig.getTestnet()
            );

            // 2. 调用 getAccount 方法获取账户数据
            Map<String, Object> accountJson = client.getAccount();

            // 3. 从 account_data 中提取汇总信息
            Map<String, Object> accountAssetSummary = new HashMap<>();
            accountAssetSummary.put("totalInitialMargin", getDoubleValue(accountJson, "totalInitialMargin"));
            accountAssetSummary.put("totalMaintMargin", getDoubleValue(accountJson, "totalMaintMargin"));
            accountAssetSummary.put("totalWalletBalance", getDoubleValue(accountJson, "totalWalletBalance"));
            accountAssetSummary.put("totalUnrealizedProfit", getDoubleValue(accountJson, "totalUnrealizedProfit"));
            accountAssetSummary.put("totalMarginBalance", getDoubleValue(accountJson, "totalMarginBalance"));
            accountAssetSummary.put("totalPositionInitialMargin", getDoubleValue(accountJson, "totalPositionInitialMargin"));
            accountAssetSummary.put("totalOpenOrderInitialMargin", getDoubleValue(accountJson, "totalOpenOrderInitialMargin"));
            accountAssetSummary.put("totalCrossWalletBalance", getDoubleValue(accountJson, "totalCrossWalletBalance"));
            accountAssetSummary.put("totalCrossUnPnl", getDoubleValue(accountJson, "totalCrossUnPnl"));
            accountAssetSummary.put("availableBalance", getDoubleValue(accountJson, "availableBalance"));
            accountAssetSummary.put("maxWithdrawAmount", getDoubleValue(accountJson, "maxWithdrawAmount"));

            // 4. 从 account_data 中提取 assets 数组
            List<Map<String, Object>> assetList = new ArrayList<>();
            Object assetsObj = accountJson.get("assets");
            if (assetsObj instanceof List) {
                List<?> assets = (List<?>) assetsObj;
                for (Object assetItemObj : assets) {
                    Map<String, Object> assetInfo = new HashMap<>();
                    
                    // 处理 AccountInformationV3ResponseAssetsInner 对象
                    if (assetItemObj instanceof com.binance.connector.client.derivatives_trading_usds_futures.rest.model.AccountInformationV3ResponseAssetsInner) {
                        com.binance.connector.client.derivatives_trading_usds_futures.rest.model.AccountInformationV3ResponseAssetsInner assetItem = 
                            (com.binance.connector.client.derivatives_trading_usds_futures.rest.model.AccountInformationV3ResponseAssetsInner) assetItemObj;
                        assetInfo.put("asset", assetItem.getAsset());
                        assetInfo.put("walletBalance", getDoubleValueFromString(assetItem.getWalletBalance()));
                        assetInfo.put("unrealizedProfit", getDoubleValueFromString(assetItem.getUnrealizedProfit()));
                        assetInfo.put("marginBalance", getDoubleValueFromString(assetItem.getMarginBalance()));
                        assetInfo.put("maintMargin", getDoubleValueFromString(assetItem.getMaintMargin()));
                        assetInfo.put("initialMargin", getDoubleValueFromString(assetItem.getInitialMargin()));
                        assetInfo.put("positionInitialMargin", getDoubleValueFromString(assetItem.getPositionInitialMargin()));
                        assetInfo.put("openOrderInitialMargin", getDoubleValueFromString(assetItem.getOpenOrderInitialMargin()));
                        assetInfo.put("crossWalletBalance", getDoubleValueFromString(assetItem.getCrossWalletBalance()));
                        assetInfo.put("crossUnPnl", getDoubleValueFromString(assetItem.getCrossUnPnl()));
                        assetInfo.put("availableBalance", getDoubleValueFromString(assetItem.getAvailableBalance()));
                        assetInfo.put("maxWithdrawAmount", getDoubleValueFromString(assetItem.getMaxWithdrawAmount()));
                    } else if (assetItemObj instanceof Map) {
                        // 兼容处理：如果是Map类型，使用原有逻辑
                        @SuppressWarnings("unchecked")
                        Map<String, Object> assetItem = (Map<String, Object>) assetItemObj;
                        assetInfo.put("asset", assetItem.get("asset"));
                        assetInfo.put("walletBalance", getDoubleValue(assetItem, "walletBalance"));
                        assetInfo.put("unrealizedProfit", getDoubleValue(assetItem, "unrealizedProfit"));
                        assetInfo.put("marginBalance", getDoubleValue(assetItem, "marginBalance"));
                        assetInfo.put("maintMargin", getDoubleValue(assetItem, "maintMargin"));
                        assetInfo.put("initialMargin", getDoubleValue(assetItem, "initialMargin"));
                        assetInfo.put("positionInitialMargin", getDoubleValue(assetItem, "positionInitialMargin"));
                        assetInfo.put("openOrderInitialMargin", getDoubleValue(assetItem, "openOrderInitialMargin"));
                        assetInfo.put("crossWalletBalance", getDoubleValue(assetItem, "crossWalletBalance"));
                        assetInfo.put("crossUnPnl", getDoubleValue(assetItem, "crossUnPnl"));
                        assetInfo.put("availableBalance", getDoubleValue(assetItem, "availableBalance"));
                        assetInfo.put("maxWithdrawAmount", getDoubleValue(assetItem, "maxWithdrawAmount"));
                    }
                    assetList.add(assetInfo);
                }
            }

            // 5. 生成 account_alias
            String accountAlias = generateAccountAlias(apiKey);

            // 6. 保存到数据库
            AccountAssetDO accountAsset = new AccountAssetDO();
            accountAsset.setAccountAlias(accountAlias);
            accountAsset.setAccountName(accountName.trim());
            accountAsset.setApiKey(apiKey);
            accountAsset.setApiSecret(apiSecret);
            accountAsset.setTotalInitialMargin((Double) accountAssetSummary.get("totalInitialMargin"));
            accountAsset.setTotalMaintMargin((Double) accountAssetSummary.get("totalMaintMargin"));
            accountAsset.setTotalWalletBalance((Double) accountAssetSummary.get("totalWalletBalance"));
            accountAsset.setTotalUnrealizedProfit((Double) accountAssetSummary.get("totalUnrealizedProfit"));
            accountAsset.setTotalMarginBalance((Double) accountAssetSummary.get("totalMarginBalance"));
            accountAsset.setTotalPositionInitialMargin((Double) accountAssetSummary.get("totalPositionInitialMargin"));
            accountAsset.setTotalOpenOrderInitialMargin((Double) accountAssetSummary.get("totalOpenOrderInitialMargin"));
            accountAsset.setTotalCrossWalletBalance((Double) accountAssetSummary.get("totalCrossWalletBalance"));
            accountAsset.setTotalCrossUnPnl((Double) accountAssetSummary.get("totalCrossUnPnl"));
            accountAsset.setAvailableBalance((Double) accountAssetSummary.get("availableBalance"));
            accountAsset.setMaxWithdrawAmount((Double) accountAssetSummary.get("maxWithdrawAmount"));
            accountAsset.setUpdateTime(System.currentTimeMillis());
            accountAsset.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC));

            accountAssetMapper.insert(accountAsset);

            log.info("[AccountService] 账户添加成功: account_alias={}", accountAlias);
            Map<String, Object> result = new HashMap<>();
            result.put("account_alias", accountAlias);
            result.put("message", "Account added successfully");
            return result;
        } catch (Exception e) {
            log.error("[AccountService] 添加账户失败: {}", e.getMessage(), e);
            throw new RuntimeException("添加账户失败: " + e.getMessage(), e);
        }
    }

    @Override
    @Transactional
    public Map<String, Object> deleteAccount(String accountAlias) {
        log.info("[AccountService] 删除账户, account_alias={}", accountAlias);
        try {
            accountAssetMapper.deleteById(accountAlias);
            log.info("[AccountService] 账户删除成功: account_alias={}", accountAlias);
            Map<String, Object> result = new HashMap<>();
            result.put("success", true);
            result.put("message", "Account deleted successfully");
            return result;
        } catch (Exception e) {
            log.error("[AccountService] 删除账户失败: {}", e.getMessage(), e);
            Map<String, Object> result = new HashMap<>();
            result.put("success", false);
            result.put("error", e.getMessage());
            throw new RuntimeException("删除账户失败: " + e.getMessage(), e);
        }
    }

    private String generateAccountAlias(String apiKey) {
        try {
            MessageDigest md = MessageDigest.getInstance("MD5");
            byte[] hash = md.digest(apiKey.getBytes());
            StringBuilder hexString = new StringBuilder();
            for (byte b : hash) {
                String hex = Integer.toHexString(0xff & b);
                if (hex.length() == 1) {
                    hexString.append('0');
                }
                hexString.append(hex);
            }
            String apiKeyHash = hexString.toString().substring(0, 8);
            String timestampSuffix = String.valueOf(System.currentTimeMillis() / 1000).substring(Math.max(0, String.valueOf(System.currentTimeMillis() / 1000).length() - 6));
            return apiKeyHash + "_" + timestampSuffix;
        } catch (Exception e) {
            log.error("[AccountService] 生成 account_alias 失败: {}", e.getMessage());
            return "account_" + System.currentTimeMillis();
        }
    }

    /**
     * 从字符串值转换为Double
     * @param value 字符串值（可能为null）
     * @return Double值，如果转换失败则返回0.0
     */
    private Double getDoubleValueFromString(String value) {
        if (value == null || value.isEmpty()) {
            return 0.0;
        }
        try {
            return Double.parseDouble(value);
        } catch (NumberFormatException e) {
            log.warn("[AccountService] 无法将字符串转换为Double: {}", value);
            return 0.0;
        }
    }

    private Double getDoubleValue(Map<String, Object> map, String key) {
        Object value = map.get(key);
        if (value == null) {
            return 0.0;
        }
        if (value instanceof Number) {
            return ((Number) value).doubleValue();
        }
        try {
            return Double.parseDouble(value.toString());
        } catch (Exception e) {
            return 0.0;
        }
    }
}

