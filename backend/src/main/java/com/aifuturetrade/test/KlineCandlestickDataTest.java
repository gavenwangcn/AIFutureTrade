package com.aifuturetrade.test;

import com.binance.connector.client.common.ApiException;
import com.binance.connector.client.common.ApiResponse;
import com.binance.connector.client.common.configuration.ClientConfiguration;
import com.binance.connector.client.common.configuration.SignatureConfiguration;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.DerivativesTradingUsdsFuturesRestApiUtil;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.api.DerivativesTradingUsdsFuturesRestApi;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.Interval;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.KlineCandlestickDataResponse;
import com.binance.connector.client.derivatives_trading_usds_futures.rest.model.KlineCandlestickDataResponseItem;

import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
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
            
            // 如果 startTime 和 endTime 为空，自动计算时间范围
            Long calculatedStartTime = startTime;
            Long calculatedEndTime = endTime;
            
            if (calculatedStartTime == null || calculatedEndTime == null) {
                // endTime 取当前时间
                calculatedEndTime = System.currentTimeMillis();
                
                // startTime 根据 limit 和 interval 计算
                // 例如：limit=100, interval=1m，则 startTime = endTime - 100分钟
                long intervalMinutes = getIntervalMinutes(interval);
                long totalMinutes = limit * intervalMinutes;
                calculatedStartTime = calculatedEndTime - (totalMinutes * 60 * 1000);
                
                System.out.println("自动计算时间范围:");
                System.out.println("  interval: " + interval + " = " + intervalMinutes + " 分钟/根");
                System.out.println("  limit: " + limit + " 根");
                System.out.println("  总时间跨度: " + totalMinutes + " 分钟");
                System.out.println("  计算的 startTime: " + calculatedStartTime + " (UTC+8: " + Instant.ofEpochMilli(calculatedStartTime).atZone(utcPlus8).format(formatter) + ")");
                System.out.println("  计算的 endTime: " + calculatedEndTime + " (UTC+8: " + Instant.ofEpochMilli(calculatedEndTime).atZone(utcPlus8).format(formatter) + ")");
            }
            
            System.out.println("调用API获取K线数据...");
            System.out.println("使用Interval枚举: " + intervalEnum);
            
            // 打印实际请求参数（用于排查）
            System.out.println("----------------------------------------");
            System.out.println("实际请求参数:");
            System.out.println("  symbol: " + symbol);
            System.out.println("  interval: " + intervalEnum);
            System.out.println("  startTime: " + calculatedStartTime + " (UTC+8: " + Instant.ofEpochMilli(calculatedStartTime).atZone(utcPlus8).format(formatter) + ")");
            System.out.println("  endTime: " + calculatedEndTime + " (UTC+8: " + Instant.ofEpochMilli(calculatedEndTime).atZone(utcPlus8).format(formatter) + ")");
            System.out.println("  limit: " + limit);
            if (startTime != null && endTime != null) {
                long timeDiff = endTime - startTime;
                long days = timeDiff / (1000L * 60 * 60 * 24);
                System.out.println("  时间跨度: " + days + " 天 (" + (timeDiff / (1000L * 60)) + " 分钟)");
                if (days > 200) {
                    System.out.println("  ⚠️ 警告: 时间跨度超过200天，API可能自动调整");
                }
            } else {
                System.out.println("  ⚠️ 注意: 未指定时间范围，将返回最新的K线数据");
            }
            System.out.println("----------------------------------------");
            
            long startTimeMs = System.currentTimeMillis();
            
            // 按照官方示例调用API：klineCandlestickData(symbol, interval, startTime, endTime, limit)
            // 使用计算后的时间范围
            // 使用 ApiResponse<KlineCandlestickDataResponse> 类型
            ApiResponse<KlineCandlestickDataResponse> response = 
                    getApi().klineCandlestickData(symbol, intervalEnum, calculatedStartTime, calculatedEndTime, limit);
            
            long duration = System.currentTimeMillis() - startTimeMs;
            System.out.println("API调用完成，耗时: " + duration + " 毫秒");
            
            // 按照官方示例，使用 response.getData() 获取数据
            KlineCandlestickDataResponse responseData = response.getData();
            
            if (responseData == null) {
                System.err.println("错误: 响应数据为null");
                return;
            }
            
            // 从KlineCandlestickDataResponse中获取KlineCandlestickDataResponseItem列表
            List<KlineCandlestickDataResponseItem> items = null;
            try {
                // 尝试通过反射获取items列表
                java.lang.reflect.Method[] methods = responseData.getClass().getMethods();
                for (java.lang.reflect.Method method : methods) {
                    String methodName = method.getName();
                    // 查找可能的getter方法，如getData(), getItems(), getKlines()等
                    if ((methodName.startsWith("get") || methodName.equals("data")) 
                            && method.getParameterCount() == 0) {
                        try {
                            Object result = method.invoke(responseData);
                            if (result instanceof List) {
                                @SuppressWarnings("unchecked")
                                List<Object> resultList = (List<Object>) result;
                                if (!resultList.isEmpty()) {
                                    // 检查第一个元素是否是KlineCandlestickDataResponseItem
                                    Object firstItem = resultList.get(0);
                                    if (firstItem instanceof KlineCandlestickDataResponseItem) {
                @SuppressWarnings("unchecked")
                                        List<KlineCandlestickDataResponseItem> itemsList = 
                                                (List<KlineCandlestickDataResponseItem>) (List<?>) resultList;
                                        items = itemsList;
                                        break;
                                    }
                                }
                            }
                        } catch (Exception e) {
                            // 继续尝试下一个方法
                            continue;
                        }
                    }
                }
                
                // 如果方法调用失败，尝试直接访问字段
                if (items == null) {
                    java.lang.reflect.Field[] fields = responseData.getClass().getDeclaredFields();
                    for (java.lang.reflect.Field field : fields) {
                        field.setAccessible(true);
                        Object value = field.get(responseData);
                        if (value instanceof List) {
                            @SuppressWarnings("unchecked")
                            List<Object> valueList = (List<Object>) value;
                            if (!valueList.isEmpty() && valueList.get(0) instanceof KlineCandlestickDataResponseItem) {
                    @SuppressWarnings("unchecked")
                                List<KlineCandlestickDataResponseItem> itemsList = 
                                        (List<KlineCandlestickDataResponseItem>) (List<?>) valueList;
                                items = itemsList;
                                break;
                            }
                        }
                    }
                }
            } catch (Exception e) {
                System.err.println("无法从KlineCandlestickDataResponse中提取数据: " + e.getMessage());
                e.printStackTrace();
            }
            
            if (items == null || items.isEmpty()) {
                System.err.println("错误: 无法从响应中提取K线数据或数据为空");
                System.out.println("响应数据类型: " + responseData.getClass().getName());
                System.out.println("响应数据内容: " + responseData);
                return;
            }
            
            // 转换KlineCandlestickDataResponseItem列表为List<List<Object>>格式
            List<List<Object>> klines = new ArrayList<>();
            for (KlineCandlestickDataResponseItem item : items) {
                List<Object> klineData = extractKlineDataFromItem(item);
                if (klineData != null && !klineData.isEmpty()) {
                    klines.add(klineData);
                }
            }
            
            // 打印结果
            System.out.println("----------------------------------------");
            System.out.println("总共返回的K线数量: " + klines.size() + " / 请求数量: " + limit);
            
            // 检查返回数量与请求是否一致
            if (klines.size() != limit) {
                System.out.println("⚠️ 返回数量与请求不一致！");
                System.out.println("差异: " + (limit - klines.size()) + " 条");
                System.out.println("可能原因:");
                if (calculatedStartTime != null && calculatedEndTime != null) {
                    long timeDiff = calculatedEndTime.longValue() - calculatedStartTime.longValue();
                    long days = timeDiff / (1000L * 60 * 60 * 24);
                    if (days > 200) {
                        System.out.println("  1. 时间跨度超过200天限制，API可能自动调整");
                    }
                    long expectedMinutes = timeDiff / (1000L * 60);
                    if (expectedMinutes < limit) {
                        System.out.println("  2. 时间范围内的数据不足: 时间跨度 " + expectedMinutes + " 分钟 < 请求数量 " + limit);
                    }
                }
                System.out.println("  3. API内部处理或限制");
            } else {
                System.out.println("✓ 返回数量与请求一致");
            }
            
            // 打印时间范围信息
            if (!klines.isEmpty()) {
                List<Object> firstKline = klines.get(0);
                List<Object> lastKline = klines.get(klines.size() - 1);
                if (firstKline != null && !firstKline.isEmpty() && lastKline != null && !lastKline.isEmpty()) {
                    try {
                        long firstTime = Long.parseLong(firstKline.get(0).toString());
                        long lastTime = Long.parseLong(lastKline.get(0).toString());
                        ZonedDateTime firstZoned = Instant.ofEpochMilli(firstTime).atZone(utcPlus8);
                        ZonedDateTime lastZoned = Instant.ofEpochMilli(lastTime).atZone(utcPlus8);
                        long actualMinutes = (lastTime - firstTime) / (1000L * 60);
                        System.out.println("返回数据时间范围:");
                        System.out.println("  第一条: " + firstTime + " (UTC+8: " + firstZoned.format(formatter) + ")");
                        System.out.println("  最后一条: " + lastTime + " (UTC+8: " + lastZoned.format(formatter) + ")");
                        System.out.println("  实际时间跨度: " + actualMinutes + " 分钟");
                        if (calculatedStartTime != null && calculatedEndTime != null) {
                            long expectedMinutes = (calculatedEndTime.longValue() - calculatedStartTime.longValue()) / (1000L * 60);
                            if (actualMinutes != expectedMinutes) {
                                System.out.println("  ⚠️ 实际时间跨度 (" + actualMinutes + ") 与请求时间跨度 (" + expectedMinutes + ") 不一致");
                            }
                        }
                    } catch (Exception e) {
                        // 忽略解析错误
                    }
                }
            }
            System.out.println("----------------------------------------");
            
            if (klines.isEmpty()) {
                System.out.println("警告: 返回的K线数据为空！");
            } else {
                // 打印前5条K线数据详情
                int printCount = Math.min(klines.size(), 5);
                System.out.println("前 " + printCount + " 条K线数据详情:");
                for (int i = 0; i < printCount; i++) {
                    List<Object> kline = klines.get(i);
                    printKlineDetail(i + 1, kline, utcPlus8, formatter);
                }
                
                // 打印后5条K线数据详情
                if (klines.size() > 10) {
                    System.out.println("  ... (中间还有 " + (klines.size() - 10) + " 条数据)");
                }
                
                int lastStartIndex = Math.max(printCount, klines.size() - 5);
                if (lastStartIndex < klines.size()) {
                    System.out.println("后 " + (klines.size() - lastStartIndex) + " 条K线数据详情:");
                    for (int i = lastStartIndex; i < klines.size(); i++) {
                        List<Object> kline = klines.get(i);
                        printKlineDetail(i + 1, kline, utcPlus8, formatter);
                    }
                } else if (klines.size() <= 10 && klines.size() > printCount) {
                    // 如果总数不超过10条，只打印剩余的
                    System.out.println("剩余 " + (klines.size() - printCount) + " 条K线数据详情:");
                    for (int i = printCount; i < klines.size(); i++) {
                        List<Object> kline = klines.get(i);
                        printKlineDetail(i + 1, kline, utcPlus8, formatter);
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
     * 从KlineCandlestickDataResponseItem中提取K线数据数组
     */
    private List<Object> extractKlineDataFromItem(KlineCandlestickDataResponseItem item) {
        List<Object> klineData = new ArrayList<>();
        try {
            // 尝试通过反射获取item中的数据数组
            // 通常KlineCandlestickDataResponseItem包含一个数组或列表
            java.lang.reflect.Method[] methods = item.getClass().getMethods();
            for (java.lang.reflect.Method method : methods) {
                String methodName = method.getName();
                // 查找可能的getter方法
                if ((methodName.startsWith("get") || methodName.equals("data") || methodName.equals("toArray"))
                        && method.getParameterCount() == 0) {
                    try {
                        Object result = method.invoke(item);
                        if (result instanceof List) {
                            @SuppressWarnings("unchecked")
                            List<Object> resultList = (List<Object>) result;
                            if (!resultList.isEmpty()) {
                                klineData = resultList;
                                break;
                            }
                        } else if (result != null && result.getClass().isArray()) {
                            // 如果是数组，转换为List
                            Object[] array = (Object[]) result;
                            for (Object obj : array) {
                                klineData.add(obj);
                            }
                            break;
                        }
                    } catch (Exception e) {
                        continue;
                    }
                }
            }
            
            // 如果方法调用失败，尝试直接访问字段
            if (klineData.isEmpty()) {
                java.lang.reflect.Field[] fields = item.getClass().getDeclaredFields();
                for (java.lang.reflect.Field field : fields) {
                    field.setAccessible(true);
                    Object value = field.get(item);
                    if (value instanceof List) {
                        @SuppressWarnings("unchecked")
                        List<Object> valueList = (List<Object>) value;
                        if (!valueList.isEmpty()) {
                            klineData = valueList;
                            break;
                        }
                    } else if (value != null && value.getClass().isArray()) {
                        Object[] array = (Object[]) value;
                        for (Object obj : array) {
                            klineData.add(obj);
                        }
                        break;
                    }
                }
            }
        } catch (Exception e) {
            System.err.println("无法从KlineCandlestickDataResponseItem中提取数据: " + e.getMessage());
        }
        return klineData;
    }
    
    /**
     * 打印单条K线数据的详细信息
     */
    private void printKlineDetail(int index, List<Object> kline, ZoneId utcPlus8, DateTimeFormatter formatter) {
        if (kline == null || kline.size() < 6) {
            System.out.println("  K线 #" + index + ": 数据格式错误");
            return;
        }
        
        try {
            long openTime = Long.parseLong(kline.get(0).toString());
            ZonedDateTime openTimeZoned = Instant.ofEpochMilli(openTime).atZone(utcPlus8);
            long closeTime = kline.size() > 6 ? Long.parseLong(kline.get(6).toString()) : 0;
            ZonedDateTime closeTimeZoned = closeTime > 0 ? Instant.ofEpochMilli(closeTime).atZone(utcPlus8) : null;
            
            System.out.println("  K线 #" + index + ":");
            System.out.println("    开盘时间: " + openTime + " (UTC+8: " + openTimeZoned.format(formatter) + ")");
            System.out.println("    开盘价: " + kline.get(1));
            System.out.println("    最高价: " + kline.get(2));
            System.out.println("    最低价: " + kline.get(3));
            System.out.println("    收盘价: " + kline.get(4));
            System.out.println("    成交量: " + kline.get(5));
            if (closeTime > 0 && closeTimeZoned != null) {
                System.out.println("    收盘时间: " + closeTime + " (UTC+8: " + closeTimeZoned.format(formatter) + ")");
            }
            if (kline.size() > 7) {
                System.out.println("    成交额: " + kline.get(7));
            }
            if (kline.size() > 8) {
                System.out.println("    成交笔数: " + kline.get(8));
            }
        } catch (Exception e) {
            System.out.println("  K线 #" + index + ": 解析数据失败 - " + e.getMessage());
        }
    }
    
    /**
     * 根据interval字符串获取对应的分钟数
     * @param intervalStr 时间间隔字符串，如 "1m", "5m", "1h", "1d" 等
     * @return 对应的分钟数
     */
    private long getIntervalMinutes(String intervalStr) {
        if (intervalStr == null || intervalStr.isEmpty()) {
            return 1; // 默认1分钟
        }
        
        String lowerInterval = intervalStr.toLowerCase();
        
        // 解析数字和单位
        if (lowerInterval.endsWith("m")) {
            // 分钟：1m, 3m, 5m, 15m, 30m
            String numStr = lowerInterval.substring(0, lowerInterval.length() - 1);
            try {
                return Long.parseLong(numStr);
            } catch (NumberFormatException e) {
                return 1;
            }
        } else if (lowerInterval.endsWith("h")) {
            // 小时：1h, 2h, 4h, 6h, 8h, 12h
            String numStr = lowerInterval.substring(0, lowerInterval.length() - 1);
            try {
                return Long.parseLong(numStr) * 60;
            } catch (NumberFormatException e) {
                return 60;
            }
        } else if (lowerInterval.endsWith("d")) {
            // 天：1d, 3d
            String numStr = lowerInterval.substring(0, lowerInterval.length() - 1);
            try {
                return Long.parseLong(numStr) * 24 * 60;
            } catch (NumberFormatException e) {
                return 24 * 60;
            }
        } else if (lowerInterval.endsWith("w")) {
            // 周：1w
            String numStr = lowerInterval.substring(0, lowerInterval.length() - 1);
            try {
                return Long.parseLong(numStr) * 7 * 24 * 60;
            } catch (NumberFormatException e) {
                return 7 * 24 * 60;
            }
        } else if (lowerInterval.endsWith("M")) {
            // 月：1M
            String numStr = lowerInterval.substring(0, lowerInterval.length() - 1);
            try {
                return Long.parseLong(numStr) * 30 * 24 * 60; // 近似30天
            } catch (NumberFormatException e) {
                return 30 * 24 * 60;
            }
        }
        
        // 默认返回1分钟
        return 1;
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

