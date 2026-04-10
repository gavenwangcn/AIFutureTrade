package com.aifuturetrade.trademcp.indicators;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 与 {@code trade/market/market_data.py} 中 {@code _calculate_indicators_for_klines} 对齐的 K 线指标计算。
 * <p>
 * 返回的 K 线序列按时间从旧到新排列时，索引 {@code i} 处只能使用 {@code [0,i]} 的历史；
 * MA99、RSI14 等需要足够根数后才有值，故序列前段多数字段为 {@code null} 属预期，非计算错误。
 * </p>
 * <p>
 * 写入每根 K 线 {@code indicators} 的数值统一保留至多小数点后 4 位（HALF_UP）。
 * </p>
 */
public final class KlineIndicatorCalculator {

    private static final int KDJ_K_PERIOD = 9;
    private static final int KDJ_SMOOTH_K = 3;
    private static final int KDJ_SMOOTH_D = 3;
    /** 与 Python {@code kdj_ready_index} 一致 */
    private static final int KDJ_READY_INDEX =
            (KDJ_K_PERIOD - 1) + (KDJ_SMOOTH_K - 1) + (KDJ_SMOOTH_D - 1);

    private KlineIndicatorCalculator() {
    }

    public static List<Map<String, Object>> enrich(List<Map<String, Object>> klines) {
        if (klines == null || klines.isEmpty()) {
            return List.of();
        }
        int n = klines.size();
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
            volumes[i] = num(k.get("volume"));
            Object tb = k.get("taker_buy_base_volume");
            if (tb == null) {
                tb = k.get("takerBuyBaseVolume");
            }
            takerBuy[i] = num(tb);
        }

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

        AdxResult adx = computeAdx(highs, lows, closes, 14);
        double[] adx14 = adx != null ? adx.adx : zeros(n);
        double[] plusDi14 = adx != null ? adx.plusDi : zeros(n);
        double[] minusDi14 = adx != null ? adx.minusDi : zeros(n);

        double[] mavol5 = sma(volumes, 5);
        double[] mavol10 = sma(volumes, 10);
        double[] mavol60 = sma(volumes, 60);

        List<Map<String, Object>> out = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            Map<String, Object> row = new LinkedHashMap<>(klines.get(i));
            Map<String, Object> indicators = buildIndicatorsRow(
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
                    mavol60);
            row.put("indicators", indicators);
            out.add(row);
        }
        return out;
    }

    private static Map<String, Object> buildIndicatorsRow(
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
            double[] mavol60) {
        double vol = volumes[i];
        double buyV = takerBuy[i];
        Map<String, Object> ma = new LinkedHashMap<>();
        ma.put("ma5", i >= 4 && !nan(ma5[i]) ? roundIndicator(ma5[i]) : null);
        ma.put("ma20", i >= 19 && !nan(ma20[i]) ? roundIndicator(ma20[i]) : null);
        ma.put("ma60", i >= 59 && !nan(ma60[i]) ? roundIndicator(ma60[i]) : null);
        ma.put("ma99", i >= 98 && !nan(ma99[i]) ? roundIndicator(ma99[i]) : null);

        Map<String, Object> ema = new LinkedHashMap<>();
        ema.put("ema5", i >= 4 && !nan(ema5[i]) ? roundIndicator(ema5[i]) : null);
        ema.put("ema20", i >= 19 && !nan(ema20[i]) ? roundIndicator(ema20[i]) : null);
        ema.put("ema30", i >= 29 && !nan(ema30[i]) ? roundIndicator(ema30[i]) : null);
        ema.put("ema60", i >= 59 && !nan(ema60[i]) ? roundIndicator(ema60[i]) : null);
        ema.put("ema99", i >= 98 && !nan(ema99[i]) ? roundIndicator(ema99[i]) : null);

        Map<String, Object> rsi = new LinkedHashMap<>();
        rsi.put("rsi6", i >= 6 && !nan(rsi6[i]) ? roundIndicator(rsi6[i]) : null);
        rsi.put("rsi9", i >= 9 && !nan(rsi9[i]) ? roundIndicator(rsi9[i]) : null);
        rsi.put("rsi14", i >= 14 && !nan(rsi14[i]) ? roundIndicator(rsi14[i]) : null);

        Map<String, Object> macdMap = new LinkedHashMap<>();
        macdMap.put("dif", i >= 25 && !nan(macd.dif[i]) ? roundIndicator(macd.dif[i]) : null);
        macdMap.put("dea", i >= 25 && !nan(macd.dea[i]) ? roundIndicator(macd.dea[i]) : null);
        macdMap.put("bar", i >= 25 && !nan(macd.bar[i]) ? roundIndicator(macd.bar[i]) : null);

        Map<String, Object> kdj = new LinkedHashMap<>();
        kdj.put("k", i >= KDJ_READY_INDEX && !nan(kdjK[i]) ? roundIndicator(kdjK[i]) : null);
        kdj.put("d", i >= KDJ_READY_INDEX && !nan(kdjD[i]) ? roundIndicator(kdjD[i]) : null);
        kdj.put("j", i >= KDJ_READY_INDEX && !nan(kdjJ[i]) ? roundIndicator(kdjJ[i]) : null);

        Map<String, Object> atr = new LinkedHashMap<>();
        atr.put("atr7", i >= 6 && !nan(atr7[i]) ? roundIndicator(atr7[i]) : null);
        atr.put("atr14", i >= 13 && !nan(atr14[i]) ? roundIndicator(atr14[i]) : null);
        atr.put("atr21", i >= 20 && !nan(atr21[i]) ? roundIndicator(atr21[i]) : null);

        Map<String, Object> adx = new LinkedHashMap<>();
        adx.put("adx14", i >= 13 && !nan(adx14[i]) ? roundIndicator(adx14[i]) : null);
        adx.put("+di14", i >= 13 && !nan(plusDi14[i]) ? roundIndicator(plusDi14[i]) : null);
        adx.put("-di14", i >= 13 && !nan(minusDi14[i]) ? roundIndicator(minusDi14[i]) : null);

        Map<String, Object> volMap = new LinkedHashMap<>();
        volMap.put("vol", !nan(vol) ? roundIndicator(vol) : null);
        volMap.put("buy_vol", !nan(buyV) ? roundIndicator(buyV) : null);
        volMap.put("sell_vol", !nan(vol) && !nan(buyV) ? roundIndicator(vol - buyV) : null);
        volMap.put("mavol5", i >= 4 && !nan(mavol5[i]) ? roundIndicator(mavol5[i]) : null);
        volMap.put("mavol10", i >= 9 && !nan(mavol10[i]) ? roundIndicator(mavol10[i]) : null);
        volMap.put("mavol60", i >= 59 && !nan(mavol60[i]) ? roundIndicator(mavol60[i]) : null);

        Map<String, Object> root = new LinkedHashMap<>();
        root.put("ma", ma);
        root.put("ema", ema);
        root.put("rsi", rsi);
        root.put("macd", macdMap);
        root.put("kdj", kdj);
        root.put("atr", atr);
        root.put("adx", adx);
        root.put("vol", volMap);
        return root;
    }

    private static double[] zeros(int n) {
        return new double[n];
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
