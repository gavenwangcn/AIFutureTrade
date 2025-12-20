package com.aifuturetrade.test;

import com.binance.connector.client.common.ApiException;
import com.binance.connector.client.common.ApiResponse;
import com.binance.connector.client.common.configuration.ClientConfiguration;
import com.binance.connector.client.common.configuration.SignatureConfiguration;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.DerivativesTradingUsdsFuturesRestApiUtil;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.api.DerivativesTradingUsdsFuturesRestApi;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.Interval;

import java.util.List;

/**
 * K线数据测试类
 * 用于测试Binance期货K线数据获取，排查1m间隔返回数据只有3条的问题
 * 
 * 使用方法：
 * 1. 通过环境变量设置API密钥：
 *    export API_KEY=your_api_key
 *    export API_SECRET=your_api_secret
 * 
 * 2. 通过命令行参数设置：
 *    java -jar test.jar BTCUSDT 1m 100
 * 
 * 3. 默认参数：
 *    symbol: BTCUSDT
 *    interval: 1m
 *    limit: 100
 */
public class KlineCandlestickDataTest {
    
    private DerivativesTradingUsdsFuturesRestApi api;
    
    /**
     * 初始化API客户端
     */
    private void initApi() {
        // 从环境变量获取API密钥
        String apiKey = System.getenv("API_KEY");
        String apiSecret = System.getenv("API_SECRET");
        
        // 如果环境变量未设置，使用默认值（仅用于测试，实际使用时必须设置）
        if (apiKey == null || apiKey.isEmpty()) {
            apiKey = "apiKey";
            System.out.println("警告: 未设置API_KEY环境变量，使用默认值（可能无法正常工作）");
        }
        if (apiSecret == null || apiSecret.isEmpty()) {
            apiSecret = "apiSecret";
            System.out.println("警告: 未设置API_SECRET环境变量，使用默认值（可能无法正常工作）");
        }
        
        try {
            ClientConfiguration clientConfiguration =
                    DerivativesTradingUsdsFuturesRestApiUtil.getClientConfiguration();
            SignatureConfiguration signatureConfiguration = new SignatureConfiguration();
            signatureConfiguration.setApiKey(apiKey);
            signatureConfiguration.setSecretKey(apiSecret);
            clientConfiguration.setSignatureConfiguration(signatureConfiguration);
            api = new DerivativesTradingUsdsFuturesRestApi(clientConfiguration);
            System.out.println("API客户端初始化成功");
        } catch (Exception e) {
            System.err.println("API客户端初始化失败: " + e.getMessage());
            e.printStackTrace();
            throw new RuntimeException("API客户端初始化失败", e);
        }
    }
    
    /**
     * 获取API客户端实例
     */
    private DerivativesTradingUsdsFuturesRestApi getApi() {
        if (api == null) {
            initApi();
        }
        return api;
    }
    
    /**
     * 测试K线数据获取
     * 
     * @param symbol 交易对符号，如 "BTCUSDT"
     * @param interval 时间间隔，如 "1m"
     * @param limit 返回的K线数量
     * @param startTime 起始时间戳（毫秒），可选
     * @param endTime 结束时间戳（毫秒），可选
     */
    public void testKlineCandlestickData(String symbol, String interval, Long limit, 
                                         Long startTime, Long endTime) {
        System.out.println("========================================");
        System.out.println("K线数据测试开始");
        System.out.println("========================================");
        System.out.println("交易对: " + symbol);
        System.out.println("时间间隔: " + interval);
        System.out.println("限制数量: " + limit);
        if (startTime != null) {
            System.out.println("起始时间: " + startTime + " (" + new java.util.Date(startTime) + ")");
        }
        if (endTime != null) {
            System.out.println("结束时间: " + endTime + " (" + new java.util.Date(endTime) + ")");
        }
        System.out.println("----------------------------------------");
        
        try {
            // 转换interval字符串为Interval枚举
            Interval intervalEnum = convertStringToInterval(interval);
            if (intervalEnum == null) {
                System.err.println("错误: 不支持的时间间隔: " + interval);
                return;
            }
            
            System.out.println("调用API获取K线数据...");
            long startTimeMs = System.currentTimeMillis();
            
            // 调用API
            ApiResponse<?> response = 
                    getApi().klineCandlestickData(symbol, intervalEnum, startTime, endTime, limit);
            
            long duration = System.currentTimeMillis() - startTimeMs;
            System.out.println("API调用完成，耗时: " + duration + " 毫秒");
            
            // 获取响应数据
            Object responseData = getResponseData(response);
            
            if (responseData == null) {
                System.err.println("错误: 响应数据为null");
                return;
            }
            
            // 处理响应数据 - 可能是List<List<Object>>格式
            List<List<Object>> klines = null;
            
            if (responseData instanceof List) {
                @SuppressWarnings("unchecked")
                List<Object> dataList = (List<Object>) responseData;
                
                // 检查第一个元素是否是List（K线数据格式）
                if (!dataList.isEmpty() && dataList.get(0) instanceof List) {
                    @SuppressWarnings("unchecked")
                    List<List<Object>> klinesList = (List<List<Object>>) (List<?>) dataList;
                    klines = klinesList;
                } else {
                    System.err.println("错误: 响应数据格式不正确，期望List<List<Object>>");
                    System.out.println("响应数据类型: " + responseData.getClass().getName());
                    System.out.println("响应数据内容: " + responseData);
                    return;
                }
            } else {
                System.err.println("错误: 响应数据不是List类型");
                System.out.println("响应数据类型: " + responseData.getClass().getName());
                System.out.println("响应数据详情: " + responseData);
                return;
            }
            
            // 打印结果
            System.out.println("----------------------------------------");
            System.out.println("返回的K线数量: " + klines.size());
            System.out.println("----------------------------------------");
            
            if (klines.isEmpty()) {
                System.out.println("警告: 返回的K线数据为空！");
            } else {
                // 打印前几条K线数据详情
                int printCount = Math.min(klines.size(), 5);
                System.out.println("前 " + printCount + " 条K线数据详情:");
                for (int i = 0; i < printCount; i++) {
                    List<Object> kline = klines.get(i);
                    if (kline != null && kline.size() >= 6) {
                        System.out.println("  K线 #" + (i + 1) + ":");
                        System.out.println("    开盘时间: " + kline.get(0) + " (" + 
                                new java.util.Date(Long.parseLong(kline.get(0).toString())) + ")");
                        System.out.println("    开盘价: " + kline.get(1));
                        System.out.println("    最高价: " + kline.get(2));
                        System.out.println("    最低价: " + kline.get(3));
                        System.out.println("    收盘价: " + kline.get(4));
                        System.out.println("    成交量: " + kline.get(5));
                    }
                }
                
                if (klines.size() > printCount) {
                    System.out.println("  ... (还有 " + (klines.size() - printCount) + " 条数据)");
                }
                
                // 打印最后一条K线数据
                if (klines.size() > printCount) {
                    List<Object> lastKline = klines.get(klines.size() - 1);
                    if (lastKline != null && lastKline.size() >= 6) {
                        System.out.println("  最后一条K线:");
                        System.out.println("    开盘时间: " + lastKline.get(0) + " (" + 
                                new java.util.Date(Long.parseLong(lastKline.get(0).toString())) + ")");
                        System.out.println("    收盘价: " + lastKline.get(4));
                    }
                }
            }
            
            // 分析问题
            System.out.println("----------------------------------------");
            if (klines.size() < limit && klines.size() < 10) {
                System.out.println("警告: 返回的K线数量 (" + klines.size() + ") 远少于请求的数量 (" + limit + ")");
                System.out.println("可能的原因:");
                System.out.println("  1. 时间范围设置不当（startTime/endTime）");
                System.out.println("  2. 该交易对在该时间范围内数据不足");
                System.out.println("  3. SDK或API限制");
                System.out.println("  4. 网络或API响应问题");
            } else if (klines.size() == limit) {
                System.out.println("成功: 返回了请求的全部K线数据");
            } else {
                System.out.println("注意: 返回的K线数量 (" + klines.size() + ") 与请求的数量 (" + limit + ") 不同");
            }
            
            System.out.println("========================================");
            System.out.println("测试完成");
            System.out.println("========================================");
            
        } catch (ApiException e) {
            System.err.println("API调用失败:");
            System.err.println("  错误代码: " + e.getCode());
            System.err.println("  错误消息: " + e.getMessage());
            System.err.println("  响应体: " + e.getResponseBody());
            e.printStackTrace();
        } catch (Exception e) {
            System.err.println("测试失败: " + e.getMessage());
            e.printStackTrace();
        }
    }
    
    /**
     * 从ApiResponse中获取数据
     */
    private Object getResponseData(ApiResponse<?> response) {
        if (response == null) {
            return null;
        }
        try {
            // 尝试使用反射获取data字段或方法
            try {
                java.lang.reflect.Method dataMethod = response.getClass().getMethod("getData");
                return dataMethod.invoke(response);
            } catch (NoSuchMethodException e) {
                try {
                    java.lang.reflect.Method dataMethod = response.getClass().getMethod("data");
                    return dataMethod.invoke(response);
                } catch (NoSuchMethodException e2) {
                    // 尝试直接访问data字段
                    try {
                        java.lang.reflect.Field dataField = response.getClass().getField("data");
                        return dataField.get(response);
                    } catch (NoSuchFieldException e3) {
                        // 如果都失败，返回response本身
                        return response;
                    }
                }
            }
        } catch (Exception e) {
            System.err.println("获取响应数据失败: " + e.getMessage());
            return response;
        }
    }
    
    /**
     * 将字符串interval转换为Interval枚举
     */
    private Interval convertStringToInterval(String intervalStr) {
        if (intervalStr == null || intervalStr.isEmpty()) {
            return null;
        }
        
        String upperInterval = intervalStr.toUpperCase();
        
        // 尝试多种可能的枚举命名格式
        String[] possibleNames = {
            "INTERVAL_" + upperInterval,           // INTERVAL_1M, INTERVAL_5M
            "INTERVAL_" + upperInterval.replaceAll("[^A-Z0-9]", ""),  // INTERVAL_1M (移除特殊字符)
            upperInterval,                         // 直接使用 1M, 5M
            intervalStr                            // 保持原样 1m, 5m
        };
        
        for (String enumName : possibleNames) {
            try {
                return Interval.valueOf(enumName);
            } catch (IllegalArgumentException e) {
                // 继续尝试下一个
                continue;
            }
        }
        
        // 如果所有格式都失败，尝试使用反射查找所有枚举值
        try {
            Interval[] values = Interval.values();
            for (Interval interval : values) {
                // 检查枚举值的字符串表示是否匹配
                String enumStr = interval.toString().toUpperCase();
                if (enumStr.equals(upperInterval) || 
                    enumStr.endsWith(upperInterval) ||
                    enumStr.contains(upperInterval)) {
                    return interval;
                }
            }
        } catch (Exception e) {
            System.err.println("使用反射查找Interval枚举失败: " + e.getMessage());
        }
        
        System.err.println("不支持的interval格式: " + intervalStr);
        System.out.println("可用的Interval枚举值:");
        for (Interval interval : Interval.values()) {
            System.out.println("  " + interval);
        }
        return null;
    }
    
    /**
     * 主方法
     */
    public static void main(String[] args) {
        KlineCandlestickDataTest test = new KlineCandlestickDataTest();
        
        // 解析命令行参数
        String symbol = "BTCUSDT";
        String interval = "1m";
        Long limit = 100L;
        Long startTime = null;
        Long endTime = null;
        
        if (args.length > 0) {
            symbol = args[0];
        }
        if (args.length > 1) {
            interval = args[1];
        }
        if (args.length > 2) {
            try {
                limit = Long.parseLong(args[2]);
            } catch (NumberFormatException e) {
                System.err.println("错误: limit参数必须是数字: " + args[2]);
                return;
            }
        }
        if (args.length > 3) {
            try {
                startTime = Long.parseLong(args[3]);
            } catch (NumberFormatException e) {
                System.err.println("错误: startTime参数必须是数字: " + args[3]);
                return;
            }
        }
        if (args.length > 4) {
            try {
                endTime = Long.parseLong(args[4]);
            } catch (NumberFormatException e) {
                System.err.println("错误: endTime参数必须是数字: " + args[4]);
                return;
            }
        }
        
        // 如果没有设置时间范围，使用默认的最近时间范围
        if (startTime == null && endTime == null) {
            // 默认获取最近的数据，不设置时间范围
            System.out.println("未设置时间范围，将获取最近的K线数据");
        }
        
        // 执行测试
        test.testKlineCandlestickData(symbol, interval, limit, startTime, endTime);
    }
}

