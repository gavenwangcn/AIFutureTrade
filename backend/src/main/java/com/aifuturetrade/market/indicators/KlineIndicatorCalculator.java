package com.aifuturetrade.market.indicators;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * K 线技术指标聚合（与 Python / 前端 K 线指标对齐）。
 * <p>
 * 返回的 K 线序列按时间从旧到新排列时，索引 {@code i} 处只能使用 {@code [0,i]} 的历史。
 * 任一时间点若存在任一指标无法给出有效值，则<strong>整根 K 线不加入结果</strong>（不从单根里删除字段）。
 * 一般从第 99 根起（下标 ≥98）才可能全部指标齐全；{@code limit=298} 时约返回 200 根。
 * 性能：先校验根数，{@code n < 99} 时不做任何指标计算；{@code n ≥ 99} 时只对下标 {@code 98..n-1} 组装结果。
 * </p>
 * <p>
 * 写入每根 K 线 {@code indicators} 的数值统一保留至多小数点后 4 位（HALF_UP）。
 * </p>
 * <h2>算法来源（与 binance-service 中同名类保持一致）</h2>
 * <ul>
 * <li><b>RSI</b>：{@code trade/market/market_data.py} {@code _calculate_rsi_tradingview}；完备性见 {@link #finRsiSeries(double[], int, int)}。</li>
 * <li><b>EMA</b>：{@code frontend/KLineChart/indicators/ema.ts}（与 {@link #emaFrontend} 相同）。</li>
 * <li><b>MACD</b>：{@code frontend/KLineChart/indicators/macd.ts}（与 {@link #macdFrontend} 相同）。</li>
 * <li><b>KDJ</b>：{@code frontend/KLineChart/indicators/kdj.ts}（与 {@link #kdjTradingView} 等价）。</li>
 * <li><b>ATR</b>：{@code frontend/KLineChart/indicators/atr.ts} RMA(TR)（与 {@link #atrTradingView} 相同）。</li>
 * <li><b>ADX</b>：{@code trade/market/market_index.py} {@code MarketIndexCalculator#compute_adx}（与 {@link #computeAdx} 相同）。</li>
 * <li><b>Supertrend</b>：{@code trade/market/supertrend_tradingview.py}；{@code trend} 初值须为 0（勿用 NaN）。</li>
 * </ul>
 */
public final class KlineIndicatorCalculator {

    private static final int KDJ_K_PERIOD = 9;
    private static final int KDJ_SMOOTH_K = 3;
    private static final int KDJ_SMOOTH_D = 3;
    /** 与 Python {@code kdj_ready_index} 一致 */
    private static final int KDJ_READY_INDEX =
            (KDJ_K_PERIOD - 1) + (KDJ_SMOOTH_K - 1) + (KDJ_SMOOTH_D - 1);

    /** MA99/EMA99 等全部就绪的最小下标（含）；更小的下标整根丢弃 */
    private static final int FULL_BAR_MIN_INDEX = 98;

    /**
     * 计算完整指标集（含 MA99/EMA99、KDJ 全窗口等）所需的最少 K 线条数；
     * 少于该条数时 {@link #enrich(List)} 直接返回空列表（与 Python 侧一致）。
     */
    public static final int MIN_KLINES_FOR_FULL_INDICATORS = 99;

    /** 上述指标所需最少 K 线根数 */
    private static final int FULL_BAR_MIN_BARS = MIN_KLINES_FOR_FULL_INDICATORS;

    /** Supertrend：与 Pine ta.supertrend(3, 10) 一致 */
    private static final int SUPERTREND_ATR_PERIOD = 10;
    private static final double SUPERTREND_MULTIPLIER = 3.0;

    private KlineIndicatorCalculator() {
    }

    public static List<Map<String, Object>> enrich(List<Map<String, Object>> klines) {
        if (klines == null || klines.isEmpty()) {
            return List.of();
        }
        int n = klines.size();
        if (n < FULL_BAR_MIN_BARS) {
            return List.of();
        }

        double[] highs = new double[n];
        double[] lows = new double[n];
        double[] closes = new double[n];
        double[] volumes = new double[n];
        double[] takerBuy = new double[n];
        for (int i = 0; i < n; i++) {
            Map<String, Object> k = klines.get(i);
            highs[i] = num(k.get("high"));
            lows[i] = num(k.get("low"));
            closes[i] = num(k.get("close"));
            volumes[i] = numVolumeLike(k.get("volume"));
            Object tb = k.get("taker_buy_base_volume");
            if (tb == null) {
                tb = k.get("takerBuyBaseVolume");
            }
            takerBuy[i] = numVolumeLike(tb);
        }

        // n ≥ 99：以下计算与输出下标 98..n-1 所需；不再对 n 做分段短路
        double[] ma5 = sma(closes, 5);
        double[] ma20 = sma(closes, 20);
        double[] ma60 = sma(closes, 60);
        double[] ma99 = sma(closes, 99);

        double[] ema5 = emaFrontend(closes, 5);
        double[] ema20 = emaFrontend(closes, 20);
        double[] ema30 = emaFrontend(closes, 30);
        double[] ema60 = emaFrontend(closes, 60);
        double[] ema99 = emaFrontend(closes, 99);

        double[] rsi6 = rsiTradingView(closes, 6);
        double[] rsi9 = rsiTradingView(closes, 9);
        double[] rsi14 = rsiTradingView(closes, 14);

        Macd macd = macdFrontend(closes, 12, 26, 9);

        double[][] kdj = kdjTradingView(highs, lows, closes, KDJ_K_PERIOD, KDJ_SMOOTH_K, KDJ_SMOOTH_D);
        double[] kdjK = kdj[0];
        double[] kdjD = kdj[1];
        double[] kdjJ = kdj[2];

        double[] atr7 = atrTradingView(highs, lows, closes, 7);
        double[] atr14 = atrTradingView(highs, lows, closes, 14);
        double[] atr21 = atrTradingView(highs, lows, closes, 21);
        double[] atr10St = atrTradingView(highs, lows, closes, SUPERTREND_ATR_PERIOD);
        SupertrendResult supertrend = supertrendTradingView(highs, lows, closes, atr10St, SUPERTREND_MULTIPLIER);

        AdxResult adx = computeAdx(highs, lows, closes, 14);
        double[] adx14 = adx != null ? adx.adx : null;
        double[] plusDi14 = adx != null ? adx.plusDi : null;
        double[] minusDi14 = adx != null ? adx.minusDi : null;

        double[] mavol5 = sma(volumes, 5);
        double[] mavol10 = sma(volumes, 10);
        double[] mavol60 = sma(volumes, 60);

        List<Map<String, Object>> out = new ArrayList<>(Math.max(0, n - FULL_BAR_MIN_INDEX));
        for (int i = FULL_BAR_MIN_INDEX; i < n; i++) {
            if (!isFiniteFullBarAt(
                    i,
                    volumes,
                    takerBuy,
                    ma5,
                    ma20,
                    ma60,
                    ma99,
                    ema5,
                    ema20,
                    ema30,
                    ema60,
                    ema99,
                    rsi6,
                    rsi9,
                    rsi14,
                    macd,
                    kdjK,
                    kdjD,
                    kdjJ,
                    atr7,
                    atr14,
                    atr21,
                    adx14,
                    plusDi14,
                    minusDi14,
                    mavol5,
                    mavol10,
                    mavol60,
                    supertrend)) {
                continue;
            }
            Map<String, Object> row = new LinkedHashMap<>(klines.get(i));
            row.put(
                    "indicators",
                    buildDenseIndicatorsRow(
                            i,
                            volumes,
                            takerBuy,
                            ma5,
                            ma20,
                            ma60,
                            ma99,
                            ema5,
                            ema20,
                            ema30,
                            ema60,
                            ema99,
                            rsi6,
                            rsi9,
                            rsi14,
                            macd,
                            kdjK,
                            kdjD,
                            kdjJ,
                            atr7,
                            atr14,
                            atr21,
                            adx14,
                            plusDi14,
                            minusDi14,
                            mavol5,
                            mavol10,
                            mavol60,
                            supertrend));
            out.add(row);
        }
        return out;
    }

    /**
     * 输出下标已保证 ≥ {@link #FULL_BAR_MIN_INDEX} 且 n≥{@link #FULL_BAR_MIN_BARS}；
     * 仅校验该根上各序列是否为有限数（脏数据时跳过该根）。
     */
    private static boolean isFiniteFullBarAt(
            int i,
            double[] volumes,
            double[] takerBuy,
            double[] ma5,
            double[] ma20,
            double[] ma60,
            double[] ma99,
            double[] ema5,
            double[] ema20,
            double[] ema30,
            double[] ema60,
            double[] ema99,
            double[] rsi6,
            double[] rsi9,
            double[] rsi14,
            Macd macd,
            double[] kdjK,
            double[] kdjD,
            double[] kdjJ,
            double[] atr7,
            double[] atr14,
            double[] atr21,
            double[] adx14,
            double[] plusDi14,
            double[] minusDi14,
            double[] mavol5,
            double[] mavol10,
            double[] mavol60,
            SupertrendResult supertrend) {
        double vol = volumes[i];
        double buyV = takerBuy[i];
        if (nan(vol) || nan(buyV)) {
            return false;
        }
        if (!fin(ma5, i, 4)
                || !fin(ma20, i, 19)
                || !fin(ma60, i, 59)
                || !fin(ma99, i, 98)) {
            return false;
        }
        if (!fin(ema5, i, 4)
                || !fin(ema20, i, 19)
                || !fin(ema30, i, 29)
                || !fin(ema60, i, 59)
                || !fin(ema99, i, 98)) {
            return false;
        }
        if (!finRsiSeries(rsi6, i, 6)
                || !finRsiSeries(rsi9, i, 9)
                || !finRsiSeries(rsi14, i, 14)) {
            return false;
        }
        if (macd == null
                || nan(macd.dif[i])
                || nan(macd.dea[i])
                || nan(macd.bar[i])) {
            return false;
        }
        if (!fin(kdjK, i, KDJ_READY_INDEX)
                || !fin(kdjD, i, KDJ_READY_INDEX)
                || !fin(kdjJ, i, KDJ_READY_INDEX)) {
            return false;
        }
        if (!fin(atr7, i, 6) || !fin(atr14, i, 13) || !fin(atr21, i, 20)) {
            return false;
        }
        if (!fin(adx14, i, 13) || !fin(plusDi14, i, 13) || !fin(minusDi14, i, 13)) {
            return false;
        }
        if (!finSupertrend(supertrend, i)) {
            return false;
        }
        return fin(mavol5, i, 4)
                && fin(mavol10, i, 9)
                && fin(mavol60, i, 59);
    }

    private static boolean finSupertrend(SupertrendResult st, int i) {
        if (st == null || st.line == null || st.trend == null || st.finalUpper == null || st.finalLower == null) {
            return false;
        }
        return i < st.line.length
                && !nan(st.line[i])
                && !nan(st.trend[i])
                && !nan(st.finalUpper[i])
                && !nan(st.finalLower[i]);
    }

    private static boolean fin(double[] arr, int i, int minInclusive) {
        return arr != null && i >= minInclusive && !nan(arr[i]);
    }

    /** RSI：首根有效值在下标 {@code period - 1}，与 {@code _calculate_rsi_tradingview} 一致。 */
    private static boolean finRsiSeries(double[] rsi, int i, int period) {
        return fin(rsi, i, period - 1);
    }

    /** 成交量类字段：null/空串/非数字按 0，与 binance-service 行为一致。 */
    private static double numVolumeLike(Object o) {
        if (o == null) {
            return 0.0;
        }
        if (o instanceof String && ((String) o).trim().isEmpty()) {
            return 0.0;
        }
        double v = num(o);
        return nan(v) ? 0.0 : v;
    }

    /** 仅当 isFullIndicatorBar 为真时调用；输出完整指标嵌套结构（无 null 叶子） */
    private static Map<String, Object> buildDenseIndicatorsRow(
            int i,
            double[] volumes,
            double[] takerBuy,
            double[] ma5,
            double[] ma20,
            double[] ma60,
            double[] ma99,
            double[] ema5,
            double[] ema20,
            double[] ema30,
            double[] ema60,
            double[] ema99,
            double[] rsi6,
            double[] rsi9,
            double[] rsi14,
            Macd macd,
            double[] kdjK,
            double[] kdjD,
            double[] kdjJ,
            double[] atr7,
            double[] atr14,
            double[] atr21,
            double[] adx14,
            double[] plusDi14,
            double[] minusDi14,
            double[] mavol5,
            double[] mavol10,
            double[] mavol60,
            SupertrendResult supertrend) {
        double vol = volumes[i];
        double buyV = takerBuy[i];
        Map<String, Object> ma = new LinkedHashMap<>();
        ma.put("ma5", roundIndicator(ma5[i]));
        ma.put("ma20", roundIndicator(ma20[i]));
        ma.put("ma60", roundIndicator(ma60[i]));
        ma.put("ma99", roundIndicator(ma99[i]));

        Map<String, Object> ema = new LinkedHashMap<>();
        ema.put("ema5", roundIndicator(ema5[i]));
        ema.put("ema20", roundIndicator(ema20[i]));
        ema.put("ema30", roundIndicator(ema30[i]));
        ema.put("ema60", roundIndicator(ema60[i]));
        ema.put("ema99", roundIndicator(ema99[i]));

        Map<String, Object> rsi = new LinkedHashMap<>();
        rsi.put("rsi6", roundIndicator(rsi6[i]));
        rsi.put("rsi9", roundIndicator(rsi9[i]));
        rsi.put("rsi14", roundIndicator(rsi14[i]));

        Map<String, Object> macdMap = new LinkedHashMap<>();
        macdMap.put("dif", roundIndicator(macd.dif[i]));
        macdMap.put("dea", roundIndicator(macd.dea[i]));
        macdMap.put("bar", roundIndicator(macd.bar[i]));

        Map<String, Object> kdj = new LinkedHashMap<>();
        kdj.put("k", roundIndicator(kdjK[i]));
        kdj.put("d", roundIndicator(kdjD[i]));
        kdj.put("j", roundIndicator(kdjJ[i]));

        Map<String, Object> atr = new LinkedHashMap<>();
        atr.put("atr7", roundIndicator(atr7[i]));
        atr.put("atr14", roundIndicator(atr14[i]));
        atr.put("atr21", roundIndicator(atr21[i]));

        Map<String, Object> adx = new LinkedHashMap<>();
        adx.put("adx14", roundIndicator(adx14[i]));
        adx.put("+di14", roundIndicator(plusDi14[i]));
        adx.put("-di14", roundIndicator(minusDi14[i]));

        Map<String, Object> volMap = new LinkedHashMap<>();
        volMap.put("vol", roundIndicator(vol));
        volMap.put("buy_vol", roundIndicator(buyV));
        volMap.put("sell_vol", roundIndicator(vol - buyV));
        volMap.put("mavol5", roundIndicator(mavol5[i]));
        volMap.put("mavol10", roundIndicator(mavol10[i]));
        volMap.put("mavol60", roundIndicator(mavol60[i]));

        Map<String, Object> stMap = new LinkedHashMap<>();
        stMap.put("line", roundIndicator(supertrend.line[i]));
        stMap.put("trend", supertrend.trend[i] >= 0.0 ? 1 : -1);
        stMap.put("upper", roundIndicator(supertrend.finalUpper[i]));
        stMap.put("lower", roundIndicator(supertrend.finalLower[i]));
        stMap.put("atr_period", SUPERTREND_ATR_PERIOD);
        stMap.put("multiplier", SUPERTREND_MULTIPLIER);

        Map<String, Object> root = new LinkedHashMap<>();
        root.put("ma", ma);
        root.put("ema", ema);
        root.put("rsi", rsi);
        root.put("macd", macdMap);
        root.put("kdj", kdj);
        root.put("atr", atr);
        root.put("adx", adx);
        root.put("vol", volMap);
        root.put("supertrend", stMap);
        return root;
    }

    private static final class SupertrendResult {
        final double[] line;
        final double[] trend;
        final double[] finalUpper;
        final double[] finalLower;

        SupertrendResult(double[] line, double[] trend, double[] finalUpper, final double[] finalLower) {
            this.line = line;
            this.trend = trend;
            this.finalUpper = finalUpper;
            this.finalLower = finalLower;
        }
    }

    /**
     * Supertrend（TradingView），与 {@code trade/market/supertrend_tradingview.py} 一致。
     */
    private static SupertrendResult supertrendTradingView(
            double[] high, double[] low, double[] close, double[] atr, double mult) {
        int n = close.length;
        double[] line = new double[n];
        double[] trend = new double[n];
        double[] finalUpper = new double[n];
        double[] finalLower = new double[n];
        Arrays.fill(line, Double.NaN);
        // 与 Python trend = np.zeros(n) 一致：ATR 未就绪的 bar 会 continue，若此处用 NaN，
        // 则 trend[i-1] 长期为 NaN，else 分支 trend[i]=trend[i-1] 会把 NaN 永久传下去，导致整段 Supertrend 无效。
        Arrays.fill(trend, 0.0);
        Arrays.fill(finalUpper, Double.NaN);
        Arrays.fill(finalLower, Double.NaN);

        for (int i = 0; i < n; i++) {
            if (nan(atr[i])) {
                continue;
            }
            double hl2 = (high[i] + low[i]) / 2.0;
            double ub = hl2 + mult * atr[i];
            double lb = hl2 - mult * atr[i];

            if (i == 0) {
                finalUpper[i] = ub;
                finalLower[i] = lb;
                trend[i] = close[i] > finalUpper[i] ? 1.0 : -1.0;
                line[i] = trend[i] == 1.0 ? finalLower[i] : finalUpper[i];
                continue;
            }

            double fuPrev = finalUpper[i - 1];
            double flPrev = finalLower[i - 1];

            if (!nan(lb) && !nan(flPrev)) {
                if (lb > flPrev || close[i - 1] <= flPrev) {
                    finalLower[i] = lb;
                } else {
                    finalLower[i] = flPrev;
                }
            } else {
                finalLower[i] = lb;
            }

            if (!nan(ub) && !nan(fuPrev)) {
                if (ub < fuPrev || close[i - 1] >= fuPrev) {
                    finalUpper[i] = ub;
                } else {
                    finalUpper[i] = fuPrev;
                }
            } else {
                finalUpper[i] = ub;
            }

            if (trend[i - 1] == 1.0 && close[i] < finalLower[i]) {
                trend[i] = -1.0;
            } else if (trend[i - 1] == -1.0 && close[i] > finalUpper[i]) {
                trend[i] = 1.0;
            } else {
                trend[i] = trend[i - 1];
            }

            line[i] = trend[i] == 1.0 ? finalLower[i] : finalUpper[i];
        }
        return new SupertrendResult(line, trend, finalUpper, finalLower);
    }

    private static boolean nan(double v) {
        return Double.isNaN(v);
    }

    /** 指标对外输出：最多保留小数点后 4 位（HALF_UP） */
    private static Double roundIndicator(double v) {
        if (Double.isNaN(v) || Double.isInfinite(v)) {
            return null;
        }
        return BigDecimal.valueOf(v).setScale(4, RoundingMode.HALF_UP).doubleValue();
    }

    static double num(Object o) {
        if (o == null) {
            return Double.NaN;
        }
        if (o instanceof Number) {
            return ((Number) o).doubleValue();
        }
        if (o instanceof String) {
            try {
                return Double.parseDouble(((String) o).trim());
            } catch (NumberFormatException e) {
                return Double.NaN;
            }
        }
        return Double.NaN;
    }

    /** TA-Lib SMA */
    private static double[] sma(double[] in, int period) {
        int n = in.length;
        double[] out = new double[n];
        Arrays.fill(out, Double.NaN);
        if (period <= 0 || n < period) {
            return out;
        }
        for (int i = period - 1; i < n; i++) {
            double s = 0;
            for (int k = 0; k < period; k++) {
                s += in[i - period + 1 + k];
            }
            out[i] = s / period;
        }
        return out;
    }

    /** 与 Python {@code _ema_frontend} 一致 */
    private static double[] emaFrontend(double[] values, int period) {
        int n = values.length;
        double[] emaArr = new double[n];
        double closeSum = 0.0;
        double alpha = 2.0 / (period + 1.0);
        for (int i = 0; i < n; i++) {
            double close = values[i];
            if (i == 0) {
                emaArr[i] = close;
                closeSum = close;
            } else if (i < period - 1) {
                closeSum += close;
                emaArr[i] = closeSum / (i + 1);
            } else if (i == period - 1) {
                closeSum += close;
                emaArr[i] = closeSum / period;
            } else {
                emaArr[i] = close * alpha + emaArr[i - 1] * (1 - alpha);
            }
        }
        return emaArr;
    }

    /** 与 {@code _calculate_rsi_tradingview} 一致 */
    private static double[] rsiTradingView(double[] closes, int period) {
        int n = closes.length;
        double[] rsi = new double[n];
        Arrays.fill(rsi, Double.NaN);
        double avgGain = 0.0;
        double avgLoss = 0.0;
        for (int i = 0; i < n; i++) {
            double prevClose = i > 0 ? closes[i - 1] : closes[i];
            double change = closes[i] - prevClose;
            double gain = change > 0 ? change : 0.0;
            double loss = change < 0 ? -change : 0.0;
            if (i == 0) {
                avgGain = gain;
                avgLoss = loss;
            } else if (i < period) {
                avgGain += gain;
                avgLoss += loss;
                if (i == period - 1) {
                    avgGain /= period;
                    avgLoss /= period;
                }
            } else {
                avgGain = (avgGain * (period - 1) + gain) / period;
                avgLoss = (avgLoss * (period - 1) + loss) / period;
            }
            if (i >= period - 1) {
                if (avgLoss != 0) {
                    double rs = avgGain / avgLoss;
                    rsi[i] = 100 - (100 / (1 + rs));
                } else {
                    rsi[i] = avgGain > 0 ? 100.0 : 50.0;
                }
            }
        }
        return rsi;
    }

    private static final class Macd {
        final double[] dif;
        final double[] dea;
        final double[] bar;

        Macd(double[] dif, double[] dea, double[] bar) {
            this.dif = dif;
            this.dea = dea;
            this.bar = bar;
        }
    }

    /** 与 Python {@code _macd_frontend} 一致 */
    private static Macd macdFrontend(double[] values, int fast, int slow, int signal) {
        int n = values.length;
        double[] difArr = new double[n];
        double[] deaArr = new double[n];
        double[] barArr = new double[n];
        Arrays.fill(difArr, Double.NaN);
        Arrays.fill(deaArr, Double.NaN);
        Arrays.fill(barArr, Double.NaN);
        double emaShort = 0.0;
        double emaLong = 0.0;
        double closeSum = 0.0;
        double difSum = 0.0;
        double dea = 0.0;
        int maxPeriod = Math.max(fast, slow);
        for (int i = 0; i < n; i++) {
            double close = values[i];
            closeSum += close;
            if (i >= fast - 1) {
                if (i > fast - 1) {
                    emaShort = (2 * close + (fast - 1) * emaShort) / (fast + 1);
                } else {
                    emaShort = closeSum / fast;
                }
            }
            if (i >= slow - 1) {
                if (i > slow - 1) {
                    emaLong = (2 * close + (slow - 1) * emaLong) / (slow + 1);
                } else {
                    emaLong = closeSum / slow;
                }
            }
            if (i >= maxPeriod - 1) {
                double dif = emaShort - emaLong;
                difArr[i] = dif;
                difSum += dif;
                if (i >= maxPeriod + signal - 2) {
                    if (i > maxPeriod + signal - 2) {
                        dea = (dif * 2 + dea * (signal - 1)) / (signal + 1);
                    } else {
                        dea = difSum / signal;
                    }
                    deaArr[i] = dea;
                    barArr[i] = (dif - dea) * 2;
                }
            }
        }
        return new Macd(difArr, deaArr, barArr);
    }

    /** TA-Lib MIN */
    private static double[] rollingMin(double[] in, int period) {
        int n = in.length;
        double[] out = new double[n];
        Arrays.fill(out, Double.NaN);
        for (int i = period - 1; i < n; i++) {
            double minv = Double.POSITIVE_INFINITY;
            for (int j = i - period + 1; j <= i; j++) {
                minv = Math.min(minv, in[j]);
            }
            out[i] = minv;
        }
        return out;
    }

    /** TA-Lib MAX */
    private static double[] rollingMax(double[] in, int period) {
        int n = in.length;
        double[] out = new double[n];
        Arrays.fill(out, Double.NaN);
        for (int i = period - 1; i < n; i++) {
            double maxv = Double.NEGATIVE_INFINITY;
            for (int j = i - period + 1; j <= i; j++) {
                maxv = Math.max(maxv, in[j]);
            }
            out[i] = maxv;
        }
        return out;
    }

    /**
     * np.where(highest_high != lowest_low, formula, 50)，与 NumPy 元素比较一致：
     * nan 与 nan 比较为 false；否则按公式。
     */
    private static double rawKValue(double hh, double ll, double close, double lowestLow) {
        boolean neq;
        if (Double.isNaN(hh) && Double.isNaN(ll)) {
            neq = false;
        } else if (!Double.isNaN(hh) && !Double.isNaN(ll)) {
            neq = hh != ll;
        } else {
            neq = true;
        }
        if (!neq) {
            return 50.0;
        }
        return 100.0 * (close - lowestLow) / (hh - ll);
    }

    private static double[][] kdjTradingView(
            double[] high, double[] low, double[] close, int kPeriod, int smoothK, int smoothD) {
        int n = close.length;
        double[] lowestLow = rollingMin(low, kPeriod);
        double[] highestHigh = rollingMax(high, kPeriod);
        double[] rawK = new double[n];
        for (int i = 0; i < n; i++) {
            rawK[i] = rawKValue(highestHigh[i], lowestLow[i], close[i], lowestLow[i]);
        }
        double[] kLine = sma(rawK, smoothK);
        double[] dLine = sma(kLine, smoothD);
        double[] jLine = new double[n];
        for (int i = 0; i < n; i++) {
            jLine[i] = 3 * kLine[i] - 2 * dLine[i];
        }
        return new double[][] {kLine, dLine, jLine};
    }

    /** 与 {@code _calculate_atr_tradingview} 一致 */
    private static double[] atrTradingView(double[] high, double[] low, double[] close, int period) {
        int n = close.length;
        double[] atr = new double[n];
        Arrays.fill(atr, Double.NaN);
        if (n < period) {
            return atr;
        }
        List<Double> trList = new ArrayList<>(n);
        double rma = Double.NaN;
        for (int i = 0; i < n; i++) {
            double prevClose = i > 0 ? close[i - 1] : close[i];
            double tr1 = high[i] - low[i];
            double tr2 = Math.abs(high[i] - prevClose);
            double tr3 = Math.abs(low[i] - prevClose);
            double tr = Math.max(tr1, Math.max(tr2, tr3));
            trList.add(tr);
            if (i >= period - 1) {
                if (i == period - 1) {
                    double trSum = 0;
                    for (int t = 0; t < period; t++) {
                        trSum += trList.get(t);
                    }
                    rma = trSum / period;
                    atr[i] = rma;
                } else {
                    rma = (rma * (period - 1) + tr) / period;
                    atr[i] = rma;
                }
            }
        }
        return atr;
    }

    private static final class AdxResult {
        final double[] adx;
        final double[] plusDi;
        final double[] minusDi;

        AdxResult(double[] adx, double[] plusDi, double[] minusDi) {
            this.adx = adx;
            this.plusDi = plusDi;
            this.minusDi = minusDi;
        }
    }

    /** 与 {@code MarketIndexCalculator.compute_adx} 一致 */
    private static AdxResult computeAdx(double[] high, double[] low, double[] close, int period) {
        int n = high.length;
        if (n < period || low.length < n || close.length < n) {
            return null;
        }
        double[] trValues = new double[n];
        double[] pdiValues = new double[n];
        double[] ndiValues = new double[n];
        double[] dxValues = new double[n];
        double[] adxValues = new double[n];
        for (int i = 0; i < n; i++) {
            double prevClose = i > 0 ? close[i - 1] : close[i];
            double tr1 = high[i] - low[i];
            double tr2 = Math.abs(high[i] - prevClose);
            double tr3 = Math.abs(low[i] - prevClose);
            trValues[i] = Math.max(tr1, Math.max(tr2, tr3));
        }
        for (int i = 0; i < n; i++) {
            if (i >= period - 1) {
                double trSum = 0;
                for (int k = i - period + 1; k <= i; k++) {
                    trSum += trValues[k];
                }
                double pDmSum = 0;
                double nDmSum = 0;
                for (int j = i - period + 1; j <= i; j++) {
                    double prevH = j > 0 ? high[j - 1] : high[j];
                    double prevL = j > 0 ? low[j - 1] : low[j];
                    double upM = high[j] - prevH;
                    double downM = prevL - low[j];
                    if (upM > downM && upM > 0) {
                        pDmSum += upM;
                    }
                    if (downM > upM && downM > 0) {
                        nDmSum += downM;
                    }
                }
                pdiValues[i] = trSum > 0 ? (pDmSum / trSum * 100) : 0;
                ndiValues[i] = trSum > 0 ? (nDmSum / trSum * 100) : 0;
                double diSum = pdiValues[i] + ndiValues[i];
                double dx = diSum > 0 ? (Math.abs(pdiValues[i] - ndiValues[i]) / diSum * 100) : 0;
                dxValues[i] = dx;
                if (i == period - 1) {
                    adxValues[i] = dx;
                } else if (i < 2 * period - 1) {
                    adxValues[i] = (adxValues[i - 1] * (i - period + 1) + dx) / (i - period + 2);
                } else {
                    adxValues[i] = (adxValues[i - 1] * (period - 1) + dx) / period;
                }
            }
        }
        return new AdxResult(adxValues, pdiValues, ndiValues);
    }
}


