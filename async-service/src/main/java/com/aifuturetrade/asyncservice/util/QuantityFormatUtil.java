package com.aifuturetrade.asyncservice.util;

/**
 * 数量格式化工具 - 根据价格数量级确定数量小数位数
 *
 * 规则（数量最多保留4位小数）：
 * - 价格 < 1（0.几）：数量必须为整数，0位小数
 * - 1 <= 价格 < 10（个位）：1位小数
 * - 10 <= 价格 < 1000（十、百）：2位小数
 * - 1000 <= 价格 < 10000（千）：3位小数
 * - 价格 >= 10000（万及以上）：4位小数（最多）
 */
public final class QuantityFormatUtil {

    private static final int MAX_DECIMALS = 4;

    private QuantityFormatUtil() {
    }

    /**
     * 根据参考价格格式化数量，用于SDK提交和落库
     */
    public static double formatQuantityForSdk(Double quantity, Double refPrice) {
        if (quantity == null || quantity <= 0) {
            return 0.0;
        }
        int decimals = getQuantityDecimalsByPrice(refPrice);
        double result = roundToDecimals(quantity, decimals);
        if (decimals == 0) {
            result = Math.round(result);
        }
        return result;
    }

    public static int getQuantityDecimalsByPrice(Double price) {
        if (price == null || price <= 0) {
            return MAX_DECIMALS;
        }
        if (price < 1) return 0;
        if (price < 10) return 1;
        if (price < 1000) return 2;
        if (price < 10000) return 3;
        return MAX_DECIMALS;
    }

    private static double roundToDecimals(double value, int decimals) {
        if (decimals <= 0) {
            return (double) Math.round(value);
        }
        double factor = Math.pow(10, decimals);
        return Math.round(value * factor) / factor;
    }
}
