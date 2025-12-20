package com.aifuturetrade.test;

import com.binance.connector.client.common.ApiException;
import com.binance.connector.client.common.ApiResponse;
import com.binance.connector.client.common.configuration.ClientConfiguration;
import com.binance.connector.client.common.configuration.SignatureConfiguration;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.DerivativesTradingUsdsFuturesRestApiUtil;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.api.DerivativesTradingUsdsFuturesRestApi;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.Interval;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.KlineCandlestickDataResponse;

import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
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
        // 使用 UTC+8 时区格式化时间
        ZoneId utcPlus8 = ZoneId.of("Asia/Shanghai");
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
        if (startTime != null) {
            ZonedDateTime startZoned = Instant.ofEpochMilli(startTime).atZone(utcPlus8);
            System.out.println("起始时间: " + startTime + " (UTC+8: " + startZoned.format(formatter) + ")");
        }
        if (endTime != null) {
            ZonedDateTime endZoned = Instant.ofEpochMilli(endTime).atZone(utcPlus8);
            System.out.println("结束时间: " + endTime + " (UTC+8: " + endZoned.format(formatter) + ")");
        }
        System.out.println("----------------------------------------");
        
        try {
            // 按照官方示例，使用Interval枚举值（如 Interval.INTERVAL_1m）
            Interval intervalEnum = convertStringToIntervalEnum(interval);
            if (intervalEnum == null) {
                System.err.println("错误: 不支持的时间间隔: " + interval);
                System.out.println("可用的Interval枚举值:");
                for (Interval iv : Interval.values()) {
                    System.out.println("  " + iv);
                }
                return;
            }
            
            System.out.println("调用API获取K线数据...");
            System.out.println("使用Interval枚举: " + intervalEnum);
            long startTimeMs = System.currentTimeMillis();
            
            // 按照官方示例调用API：klineCandlestickData(symbol, interval, startTime, endTime, limit)
            // 使用 ApiResponse<KlineCandlestickDataResponse> 类型
            ApiResponse<KlineCandlestickDataResponse> response = 
                    getApi().klineCandlestickData(symbol, intervalEnum, startTime, endTime, limit);
            
            long duration = System.currentTimeMillis() - startTimeMs;
            System.out.println("API调用完成，耗时: " + duration + " 毫秒");
            
            // 按照官方示例，使用 response.getData() 获取数据
            // 官方示例：System.out.println(response.getData());
            KlineCandlestickDataResponse responseData = response.getData();
            
            if (responseData == null) {
                System.err.println("错误: 响应数据为null");
                return;
            }
            
            // 处理响应数据 - 通过反射获取KlineCandlestickDataResponse内部的K线数据列表
            List<List<Object>> klines = null;
            
            try {
                // 尝试通过反射访问KlineCandlestickDataResponse的内部数据
                // 首先尝试getData()方法
                try {
                    java.lang.reflect.Method getDataMethod = responseData.getClass().getMethod("getData");
                    Object data = getDataMethod.invoke(responseData);
                    if (data instanceof List) {
                        @SuppressWarnings("unchecked")
                        List<Object> dataList = (List<Object>) data;
                        if (!dataList.isEmpty() && dataList.get(0) instanceof List) {
                            @SuppressWarnings("unchecked")
                            List<List<Object>> klinesList = (List<List<Object>>) (List<?>) dataList;
                            klines = klinesList;
                        }
                    }
                } catch (NoSuchMethodException e) {
                    // 如果getData()方法不存在，尝试访问字段
                    java.lang.reflect.Field[] fields = responseData.getClass().getDeclaredFields();
                    for (java.lang.reflect.Field field : fields) {
                        field.setAccessible(true);
                        Object value = field.get(responseData);
                        if (value instanceof List) {
                            @SuppressWarnings("unchecked")
                            List<Object> dataList = (List<Object>) value;
                            if (!dataList.isEmpty() && dataList.get(0) instanceof List) {
                                @SuppressWarnings("unchecked")
                                List<List<Object>> klinesList = (List<List<Object>>) (List<?>) dataList;
                                klines = klinesList;
                                break;
                            }
                        }
                    }
                }
            } catch (Exception e) {
                System.err.println("无法从KlineCandlestickDataResponse中提取数据: " + e.getMessage());
                e.printStackTrace();
            }
            
            if (klines == null) {
                System.err.println("错误: 无法从响应中提取K线数据");
                System.out.println("响应数据类型: " + responseData.getClass().getName());
                System.out.println("响应数据内容: " + responseData);
                // 按照官方示例，直接打印响应数据
                System.out.println("按照官方示例打印响应数据: " + response.getData());
                return;
            }
            
            // 打印结果
            System.out.println("----------------------------------------");
            System.out.println("返回的K线数量: " + klines.size());
            System.out.println("----------------------------------------");
            
            if (klines.isEmpty()) {
                System.out.println("警告: 返回的K线数据为空！");
            } else {
                // 打印前几条K线数据详情（使用之前定义的 utcPlus8 和 formatter）
                int printCount = Math.min(klines.size(), 5);
                System.out.println("前 " + printCount + " 条K线数据详情:");
                for (int i = 0; i < printCount; i++) {
                    List<Object> kline = klines.get(i);
                    if (kline != null && kline.size() >= 6) {
                        long openTime = Long.parseLong(kline.get(0).toString());
                        ZonedDateTime openTimeZoned = Instant.ofEpochMilli(openTime).atZone(utcPlus8);
                        System.out.println("  K线 #" + (i + 1) + ":");
                        System.out.println("    开盘时间: " + openTime + " (UTC+8: " + openTimeZoned.format(formatter) + ")");
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
                        long lastOpenTime = Long.parseLong(lastKline.get(0).toString());
                        ZonedDateTime lastOpenTimeZoned = Instant.ofEpochMilli(lastOpenTime).atZone(utcPlus8);
                        System.out.println("  最后一条K线:");
                        System.out.println("    开盘时间: " + lastOpenTime + " (UTC+8: " + lastOpenTimeZoned.format(formatter) + ")");
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
     * 将字符串interval转换为Interval枚举（按照官方示例使用枚举值）
     * 官方示例使用：Interval.INTERVAL_1m, Interval.INTERVAL_5m 等
     */
    private Interval convertStringToIntervalEnum(String intervalStr) {
        if (intervalStr == null || intervalStr.isEmpty()) {
            return null;
        }
        
        // 按照官方示例，枚举值格式为 INTERVAL_1m, INTERVAL_5m 等
        String upperInterval = intervalStr.toUpperCase();
        String enumName = "INTERVAL_" + upperInterval;
        
        try {
            // 直接使用枚举值，如 Interval.INTERVAL_1m
            return Interval.valueOf(enumName);
        } catch (IllegalArgumentException e) {
            // 如果失败，尝试查找所有枚举值进行匹配
            try {
                Interval[] values = Interval.values();
                for (Interval interval : values) {
                    String enumStr = interval.toString().toUpperCase();
                    // 匹配 INTERVAL_1M, INTERVAL_5M 等格式
                    if (enumStr.equals(enumName) || enumStr.endsWith("_" + upperInterval)) {
                        return interval;
                    }
                }
            } catch (Exception e2) {
                System.err.println("查找Interval枚举失败: " + e2.getMessage());
            }
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

