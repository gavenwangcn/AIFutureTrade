/**
 * Supertrend（TradingView ta.supertrend 对齐）
 * 与 trade/market/supertrend_tradingview.py、trade-mcp KlineIndicatorCalculator 一致。
 * 默认 ATR 周期 10、乘数 3。
 */

function atrTradingView (highs, lows, closes, period) {
  const n = closes.length
  const atr = new Array(n).fill(NaN)
  if (n < period) return atr
  const trList = []
  let rma = NaN
  for (let i = 0; i < n; i++) {
    const prevClose = i > 0 ? closes[i - 1] : closes[i]
    const tr1 = highs[i] - lows[i]
    const tr2 = Math.abs(highs[i] - prevClose)
    const tr3 = Math.abs(lows[i] - prevClose)
    const tr = Math.max(tr1, tr2, tr3)
    trList.push(tr)
    if (i >= period - 1) {
      if (i === period - 1) {
        let trSum = 0
        for (let t = 0; t < period; t++) trSum += trList[t]
        rma = trSum / period
        atr[i] = rma
      } else {
        rma = (rma * (period - 1) + tr) / period
        atr[i] = rma
      }
    }
  }
  return atr
}

/**
 * @param {number[]} highs
 * @param {number[]} lows
 * @param {number[]} closes
 * @param {number} [atrPeriod=10]
 * @param {number} [multiplier=3]
 * @returns {{ line: number[], trend: number[], finalUpper: number[], finalLower: number[] }}
 */
export function computeSupertrendTradingView (highs, lows, closes, atrPeriod = 10, multiplier = 3) {
  const n = closes.length
  const atr = atrTradingView(highs, lows, closes, atrPeriod)
  const line = new Array(n).fill(NaN)
  const trend = new Array(n).fill(NaN)
  const finalUpper = new Array(n).fill(NaN)
  const finalLower = new Array(n).fill(NaN)

  for (let i = 0; i < n; i++) {
    if (Number.isNaN(atr[i])) continue

    const hl2 = (highs[i] + lows[i]) / 2
    const ub = hl2 + multiplier * atr[i]
    const lb = hl2 - multiplier * atr[i]

    if (i === 0) {
      finalUpper[i] = ub
      finalLower[i] = lb
      trend[i] = closes[i] > finalUpper[i] ? 1 : -1
      line[i] = trend[i] === 1 ? finalLower[i] : finalUpper[i]
      continue
    }

    const fuPrev = finalUpper[i - 1]
    const flPrev = finalLower[i - 1]

    if (!Number.isNaN(lb) && !Number.isNaN(flPrev)) {
      finalLower[i] = (lb > flPrev || closes[i - 1] <= flPrev) ? lb : flPrev
    } else {
      finalLower[i] = lb
    }

    if (!Number.isNaN(ub) && !Number.isNaN(fuPrev)) {
      finalUpper[i] = (ub < fuPrev || closes[i - 1] >= fuPrev) ? ub : fuPrev
    } else {
      finalUpper[i] = ub
    }

    if (trend[i - 1] === 1 && closes[i] < finalLower[i]) {
      trend[i] = -1
    } else if (trend[i - 1] === -1 && closes[i] > finalUpper[i]) {
      trend[i] = 1
    } else {
      trend[i] = trend[i - 1]
    }

    line[i] = trend[i] === 1 ? finalLower[i] : finalUpper[i]
  }

  return { line, trend, finalUpper, finalLower }
}
