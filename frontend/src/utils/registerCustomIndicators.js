/**
 * 自定义指标运行时注册
 * 由于使用UMD方式加载klinecharts.min.js，需要在运行时动态注册自定义指标
 * 参考：https://klinecharts.com/api/chart/registerIndicator
 * 
 * 注意：这是备用方案，优先使用构建时包含的方式
 * 如果构建时已包含自定义指标，此函数会检测到并跳过注册
 */

// RSI指标颜色配置
const RSI_COLORS = ['#FF9600', '#935EBD']

// ATR曲线颜色配置
const ATR_COLORS = ['#2DC08E', '#935EBD', '#FF9600']

// ADX曲线颜色配置
const ADX_COLORS = ['#FF6B6B', '#4ECDC4', '#45B7D1']

// KDJ曲线颜色配置
const KDJ_COLORS = ['#E6AC00', '#935EBD', '#2DC08E']

// VOL 红涨绿跌
const VOL_UP = 'rgba(249,40,85,0.7)'
const VOL_DOWN = 'rgba(45,192,142,0.7)'

// MACD 红涨绿跌
const MACD_UP = 'rgba(249,40,85,0.7)'
const MACD_DOWN = 'rgba(45,192,142,0.7)'

// EMA曲线颜色配置：EMA5、EMA20、EMA30、EMA99（已移除EMA60）
const EMA_COLORS = ['#2196F3', '#E91E63', '#FF9800', '#9C27B0']

/**
 * 注册EMA指标到KLineChart
 * 自定义EMA：EMA5、EMA20、EMA30、EMA99（已移除EMA60，覆盖默认的EMA6、EMA12、EMA20）
 * 构建方式与ATR指标一致，运行时注册覆盖默认
 * @param {object} klinecharts - KLineChart库对象（window.klinecharts）
 * @returns {boolean} 是否成功注册
 */
export function registerEMAIndicator(klinecharts) {
  if (!klinecharts || typeof klinecharts.registerIndicator !== 'function') {
    console.error('[EMA] klinecharts.registerIndicator is not available')
    return false
  }

  // EMA已存在时也需要覆盖（默认是6,12,20，我们使用5,20,30,99，已移除EMA60）
  try {
    const emaIndicator = {
      name: 'EMA',
      shortName: 'EMA',
      series: 'price',
      precision: 6,
      shouldOhlc: true,
      calcParams: [5, 20, 30, 99],
      figures: [
        { key: 'ema1', title: 'EMA5: ', type: 'line', styles: ({ indicator }) => ({ color: indicator?.styles?.lines?.[0]?.color || EMA_COLORS[0], size: 1.5 }) },
        { key: 'ema2', title: 'EMA20: ', type: 'line', styles: ({ indicator }) => ({ color: indicator?.styles?.lines?.[1]?.color || EMA_COLORS[1], size: 1.5 }) },
        { key: 'ema3', title: 'EMA30: ', type: 'line', styles: ({ indicator }) => ({ color: indicator?.styles?.lines?.[2]?.color || EMA_COLORS[2], size: 1.5 }) },
        { key: 'ema4', title: 'EMA99: ', type: 'line', styles: ({ indicator }) => ({ color: indicator?.styles?.lines?.[3]?.color || EMA_COLORS[3], size: 1.5 }) }
      ],
      regenerateFigures: (params) => params.map((p, index) => ({
        key: `ema${index + 1}`,
        title: `EMA${p}: `,
        type: 'line',
        styles: () => ({ color: EMA_COLORS[index % EMA_COLORS.length], size: 1.5 })
      })),
      calc: (dataList, indicator) => {
        const { calcParams: params, figures } = indicator
        const emaValues = []
        const closeSums = []

        return dataList.map((kLineData, i) => {
          const ema = {}
          const close = kLineData.close

          params.forEach((p, index) => {
            if (i === 0) {
              emaValues[index] = close
              closeSums[index] = close
            } else if (i < p - 1) {
              closeSums[index] = (closeSums[index] ?? 0) + close
              emaValues[index] = closeSums[index] / (i + 1)
            } else if (i === p - 1) {
              closeSums[index] = (closeSums[index] ?? 0) + close
              emaValues[index] = closeSums[index] / p
            } else {
              const alpha = 2 / (p + 1)
              emaValues[index] = close * alpha + emaValues[index] * (1 - alpha)
            }

            if (i >= p - 1) {
              ema[figures[index].key] = emaValues[index]
            }
          })

          return ema
        })
      }
    }

    klinecharts.registerIndicator(emaIndicator)
    console.log('[EMA] Custom EMA indicator registered (5,20,30,99) at runtime')
    return true
  } catch (error) {
    console.error('[EMA] Failed to register custom EMA indicator:', error)
    return false
  }
}

/**
 * 注册RSI指标到KLineChart
 * 自定义RSI：支持RSI6、RSI9（与默认的RSI6、RSI12、RSI24不同）
 * @param {object} klinecharts - KLineChart库对象（window.klinecharts）
 * @returns {boolean} 是否成功注册
 */
export function registerRSIIndicator(klinecharts) {
  if (!klinecharts || typeof klinecharts.registerIndicator !== 'function') {
    console.error('[RSI] klinecharts.registerIndicator is not available')
    return false
  }

  // 检查是否已经注册（检查calcParams来区分自定义RSI和默认RSI）
  const supportedIndicators = klinecharts.getSupportedIndicators()
  if (!supportedIndicators.includes('RSI')) {
    console.warn('[RSI] RSI indicator not found, registering custom RSI...')
  } else {
    // RSI已存在，但可能是默认的RSI，我们需要覆盖它以确保使用自定义版本
    console.log('[RSI] RSI indicator exists, registering custom RSI to override default...')
  }

  try {
    // 自定义RSI指标定义（RSI6、RSI9）
    const rsiIndicator = {
      name: 'RSI',
      shortName: 'RSI',
      calcParams: [6, 9],  // 自定义参数：RSI6、RSI9（与默认的[6, 12, 24]不同）
      figures: [
        {
          key: 'rsi1',
          title: 'RSI1: ',
          type: 'line',
          styles: ({ indicator }) => {
            const color = indicator?.styles?.lines?.[0]?.color || RSI_COLORS[0]
            return {
              color,
              size: 1.5
            }
          }
        },
        {
          key: 'rsi2',
          title: 'RSI2: ',
          type: 'line',
          styles: ({ indicator }) => {
            const color = indicator?.styles?.lines?.[1]?.color || RSI_COLORS[1]
            return {
              color,
              size: 1.5
            }
          }
        }
      ],
      regenerateFigures: (params) => params.map((_, index) => {
        const num = index + 1
        return {
          key: `rsi${num}`,
          title: `RSI${num}: `,
          type: 'line',
          styles: () => {
            const color = RSI_COLORS[index % RSI_COLORS.length]
            return {
              color,
              size: 1.5
            }
          }
        }
      }),
      calc: (dataList, indicator) => {
        const { calcParams: params, figures } = indicator
        // 使用TradingView的计算逻辑（Wilder's Smoothing方法）
        // 为每个周期维护AvgGain和AvgLoss（使用Wilder's Smoothing）
        const avgGains = []
        const avgLosses = []
        
        return dataList.map((kLineData, i) => {
          const rsi = {}
          const prevClose = i > 0 ? dataList[i - 1].close : kLineData.close
          const change = kLineData.close - prevClose
          const gain = change > 0 ? change : 0
          const loss = change < 0 ? -change : 0
          
          params.forEach((period, index) => {
            if (i === 0) {
              // 第一根K线：初始化AvgGain和AvgLoss
              avgGains[index] = gain
              avgLosses[index] = loss
            } else if (i < period) {
              // 前period根K线：使用简单平均
              avgGains[index] = (avgGains[index] || 0) + gain
              avgLosses[index] = (avgLosses[index] || 0) + loss
              
              if (i === period - 1) {
                // 第period根K线：计算初始平均值
                avgGains[index] = avgGains[index] / period
                avgLosses[index] = avgLosses[index] / period
              }
            } else {
              // 第period+1根K线开始：使用Wilder's Smoothing
              // AvgGain = (PrevAvgGain * (period - 1) + CurrentGain) / period
              // AvgLoss = (PrevAvgLoss * (period - 1) + CurrentLoss) / period
              avgGains[index] = (avgGains[index] * (period - 1) + gain) / period
              avgLosses[index] = (avgLosses[index] * (period - 1) + loss) / period
            }
            
            // 计算RSI（需要至少period根K线）
            if (i >= period - 1) {
              if (avgLosses[index] !== 0) {
                const rs = avgGains[index] / avgLosses[index]
                rsi[figures[index].key] = 100 - (100 / (1 + rs))
              } else {
                // 如果AvgLoss为0，RSI为100（所有都是上涨）
                rsi[figures[index].key] = avgGains[index] > 0 ? 100 : 50
              }
            }
          })
          
          return rsi
        })
      }
    }

    // 注册指标（会覆盖默认的RSI）
    klinecharts.registerIndicator(rsiIndicator)
    console.log('[RSI] Custom RSI indicator registered successfully (runtime registration)')
    return true
  } catch (error) {
    console.error('[RSI] Failed to register custom RSI indicator:', error)
    return false
  }
}

/**
 * 注册ATR指标到KLineChart
 * @param {object} klinecharts - KLineChart库对象（window.klinecharts）
 * @returns {boolean} 是否成功注册
 */
export function registerATRIndicator(klinecharts) {
  if (!klinecharts || typeof klinecharts.registerIndicator !== 'function') {
    console.error('[ATR] klinecharts.registerIndicator is not available')
    return false
  }

  // 检查是否已经注册
  const supportedIndicators = klinecharts.getSupportedIndicators()
  if (supportedIndicators.includes('ATR')) {
    console.log('[ATR] ATR indicator already registered (from build)')
    return true
  }

  try {
    // ATR指标定义
    // 参考：https://klinecharts.com/api/chart/registerIndicator
    const atrIndicator = {
      name: 'ATR',
      shortName: 'ATR',
      precision: 4,
      calcParams: [7, 14, 21],
      figures: [
        {
          key: 'atr1',
          title: 'ATR7: ',
          type: 'line',
          styles: ({ indicator }) => {
            const color = indicator?.styles?.lines?.[0]?.color || ATR_COLORS[0]
            return {
              color,
              size: 1.5
            }
          }
        },
        {
          key: 'atr2',
          title: 'ATR14: ',
          type: 'line',
          styles: ({ indicator }) => {
            const color = indicator?.styles?.lines?.[1]?.color || ATR_COLORS[1]
            return {
              color,
              size: 2
            }
          }
        },
        {
          key: 'atr3',
          title: 'ATR21: ',
          type: 'line',
          styles: ({ indicator }) => {
            const color = indicator?.styles?.lines?.[2]?.color || ATR_COLORS[2]
            return {
              color,
              size: 1.5
            }
          }
        }
      ],
      regenerateFigures: (params) => params.map((_, index) => {
        const num = index + 1
        const period = params[index]
        return {
          key: `atr${num}`,
          title: `ATR${period}: `,
          type: 'line',
          styles: () => {
            const color = ATR_COLORS[index % ATR_COLORS.length]
            return {
              color,
              size: index === 1 ? 2 : 1.5
            }
          }
        }
      }),
      calc: (dataList, indicator) => {
        const { calcParams: params, figures } = indicator
        
        // 为每个周期维护RMA值（使用Wilder's Smoothing）
        const rmaValues = []
        // 为每个周期维护TR值数组（用于计算第一个RMA值）
        const trArrays = []
        
        return dataList.map((kLineData, i) => {
          const atr = {}
          
          // 获取前一日收盘价
          const prevClose = i > 0 ? dataList[i - 1].close : kLineData.close
          
          // 计算真实波幅（TR）
          const tr1 = kLineData.high - kLineData.low  // 当日最高价 - 当日最低价
          const tr2 = Math.abs(kLineData.high - prevClose)  // |当日最高价 - 前日收盘价|
          const tr3 = Math.abs(kLineData.low - prevClose)   // |当日最低价 - 前日收盘价|
          const tr = Math.max(tr1, tr2, tr3)  // TR = max(三者)
          
          // 为每个周期计算ATR
          params.forEach((period, index) => {
            // 初始化TR数组
            if (!trArrays[index]) {
              trArrays[index] = []
            }
            
            // 添加当前TR值
            trArrays[index].push(tr)
            
            // 如果数据足够，计算ATR（使用RMA/Wilder's Smoothing）
            if (i >= period - 1) {
              if (i === period - 1) {
                // 第一个值：使用SMA计算初始RMA
                let sum = 0
                for (let j = 0; j < period; j++) {
                  sum += trArrays[index][j]
                }
                rmaValues[index] = sum / period
              } else {
                // 后续值：使用Wilder's Smoothing
                // RMA = (PrevRMA * (period - 1) + CurrentTR) / period
                rmaValues[index] = (rmaValues[index] * (period - 1) + tr) / period
              }
              
              atr[figures[index].key] = rmaValues[index]
            }
          })
          
          return atr
        })
      }
    }

    // 注册指标
    klinecharts.registerIndicator(atrIndicator)
    console.log('[ATR] ATR indicator registered successfully (runtime registration)')
    return true
  } catch (error) {
    console.error('[ATR] Failed to register ATR indicator:', error)
    return false
  }
}

/**
 * 注册ADX指标到KLineChart（TradingView计算逻辑）
 * @param {object} klinecharts - KLineChart库对象（window.klinecharts）
 * @returns {boolean} 是否成功注册
 */
export function registerADXIndicator(klinecharts) {
  if (!klinecharts || typeof klinecharts.registerIndicator !== 'function') {
    console.error('[ADX] klinecharts.registerIndicator is not available')
    return false
  }

  try {
    const adxIndicator = {
      name: 'ADX',
      shortName: 'ADX',
      precision: 2,
      calcParams: [14],
      figures: [
        {
          key: 'adx',
          title: 'ADX14: ',
          type: 'line',
          styles: ({ indicator }) => {
            const color = indicator?.styles?.lines?.[0]?.color || ADX_COLORS[0]
            return { color, size: 2 }
          }
        },
        {
          key: 'pdi',
          title: '+DI14: ',
          type: 'line',
          styles: ({ indicator }) => {
            const color = indicator?.styles?.lines?.[1]?.color || ADX_COLORS[1]
            return { color, size: 1.5 }
          }
        },
        {
          key: 'ndi',
          title: '-DI14: ',
          type: 'line',
          styles: ({ indicator }) => {
            const color = indicator?.styles?.lines?.[2]?.color || ADX_COLORS[2]
            return { color, size: 1.5 }
          }
        }
      ],
      calc: (dataList, indicator) => {
        const period = indicator.calcParams[0]
        const pdiValues = []
        const ndiValues = []
        const dxValues = []
        const trValues = []
        let adxValue = 0

        return dataList.map((kLineData, i) => {
          const adx = {}
          const prevClose = i > 0 ? dataList[i - 1].close : kLineData.close

          const tr1 = kLineData.high - kLineData.low
          const tr2 = Math.abs(kLineData.high - prevClose)
          const tr3 = Math.abs(kLineData.low - prevClose)
          const tr = Math.max(tr1, tr2, tr3)
          trValues.push(tr)

          const upMove = kLineData.high - (i > 0 ? dataList[i - 1].high : kLineData.high)
          const downMove = (i > 0 ? dataList[i - 1].low : kLineData.low) - kLineData.low
          let pDm = 0
          let nDm = 0

          if (upMove > downMove && upMove > 0) pDm = upMove
          if (downMove > upMove && downMove > 0) nDm = downMove

          if (i >= period - 1) {
            let trSum = 0, pDmSum = 0, nDmSum = 0
            for (let j = i - period + 1; j <= i; j++) {
              trSum += trValues[j]
              const upM = dataList[j].high - (j > 0 ? dataList[j - 1].high : dataList[j].high)
              const downM = (j > 0 ? dataList[j - 1].low : dataList[j].low) - dataList[j].low
              if (upM > downM && upM > 0) pDmSum += upM
              if (downM > upM && downM > 0) nDmSum += downM
            }

            const pDi = trSum !== 0 ? (pDmSum / trSum) * 100 : 0
            const nDi = trSum !== 0 ? (nDmSum / trSum) * 100 : 0
            pdiValues.push(pDi)
            ndiValues.push(nDi)

            const diSum = pDi + nDi
            const dx = diSum !== 0 ? Math.abs((pDi - nDi) / diSum) * 100 : 0
            dxValues.push(dx)

            if (dxValues.length === 1) {
              adxValue = dx
            } else if (dxValues.length <= period) {
              adxValue = (adxValue * (dxValues.length - 1) + dx) / dxValues.length
            } else {
              adxValue = (adxValue * (period - 1) + dx) / period
            }

            adx.adx = adxValue
            adx.pdi = pDi
            adx.ndi = nDi
          }

          return adx
        })
      }
    }

    klinecharts.registerIndicator(adxIndicator)
    console.log('[ADX] ADX indicator registered successfully')
    return true
  } catch (error) {
    console.error('[ADX] Failed to register ADX indicator:', error)
    return false
  }
}

/**
 * 注册KDJ指标到KLineChart（与后端一致：参数60,20,5，TradingView计算逻辑）
 * 运行时覆盖默认KDJ，确保页面显示(60,20,5)而非(9,3,3)
 * @param {object} klinecharts - KLineChart库对象（window.klinecharts）
 * @returns {boolean} 是否成功注册
 */
export function registerKDJIndicator(klinecharts) {
  if (!klinecharts || typeof klinecharts.registerIndicator !== 'function') {
    console.error('[KDJ] klinecharts.registerIndicator is not available')
    return false
  }

  try {
    const kdjIndicator = {
      name: 'KDJ',
      shortName: 'KDJ',
      calcParams: [60, 20, 5],
      figures: [
        { key: 'k', title: 'K: ', type: 'line', styles: ({ indicator }) => ({ color: indicator?.styles?.lines?.[0]?.color || KDJ_COLORS[0], size: 1.5 }) },
        { key: 'd', title: 'D: ', type: 'line', styles: ({ indicator }) => ({ color: indicator?.styles?.lines?.[1]?.color || KDJ_COLORS[1], size: 1.5 }) },
        { key: 'j', title: 'J: ', type: 'line', styles: ({ indicator }) => ({ color: indicator?.styles?.lines?.[2]?.color || KDJ_COLORS[2], size: 1.5 }) }
      ],
      regenerateFigures: () => [
        { key: 'k', title: 'K: ', type: 'line' },
        { key: 'd', title: 'D: ', type: 'line' },
        { key: 'j', title: 'J: ', type: 'line' }
      ],
      calc: (dataList, indicator) => {
        const params = indicator.calcParams
        const rsvPeriod = params[0]
        const smoothK = params[1]
        const smoothD = params[2]
        const rawKValues = []
        const kValues = []
        const dValues = []

        return dataList.map((kLineData, i) => {
          const kdj = {}
          if (i >= rsvPeriod - 1) {
            let highest = kLineData.high
            let lowest = kLineData.low
            for (let j = i - rsvPeriod + 1; j <= i; j++) {
              if (dataList[j].high > highest) highest = dataList[j].high
              if (dataList[j].low < lowest) lowest = dataList[j].low
            }
            const rsv = highest !== lowest ? ((kLineData.close - lowest) / (highest - lowest)) * 100 : 50
            rawKValues.push(rsv)

            if (rawKValues.length >= smoothK) {
              let sum = 0
              for (let j = rawKValues.length - smoothK; j < rawKValues.length; j++) sum += rawKValues[j]
              const k = sum / smoothK
              kValues.push(k)

              if (kValues.length >= smoothD) {
                let dSum = 0
                for (let j = kValues.length - smoothD; j < kValues.length; j++) dSum += kValues[j]
                const d = dSum / smoothD
                dValues.push(d)
                kdj.k = k
                kdj.d = d
                kdj.j = 3 * k - 2 * d
              }
            }
          }
          return kdj
        })
      }
    }

    klinecharts.registerIndicator(kdjIndicator)
    console.log('[KDJ] KDJ indicator registered (60,20,5) at runtime')
    return true
  } catch (error) {
    console.error('[KDJ] Failed to register KDJ indicator:', error)
    return false
  }
}

/**
 * 注册VOL指标到KLineChart（与 indicators/vol.ts 一致：MA5、MA10，红涨绿跌）
 * @param {object} klinecharts - KLineChart库对象（window.klinecharts）
 * @returns {boolean} 是否成功注册
 */
export function registerVOLIndicator(klinecharts) {
  if (!klinecharts || typeof klinecharts.registerIndicator !== 'function') {
    console.error('[VOL] klinecharts.registerIndicator is not available')
    return false
  }

  try {
    const volIndicator = {
      name: 'VOL',
      shortName: 'VOL',
      series: 'volume',
      calcParams: [5, 10],
      shouldFormatBigNumber: true,
      precision: 0,
      minValue: 0,
      figures: [
        { key: 'ma1', title: 'MA5: ', type: 'line' },
        { key: 'ma2', title: 'MA10: ', type: 'line' },
        {
          key: 'volume',
          title: 'VOLUME: ',
          type: 'bar',
          baseValue: 0,
          styles: ({ data }) => {
            const c = data?.current
            if (!c) return { color: VOL_DOWN }
            return { color: c.close > c.open ? VOL_UP : VOL_DOWN }
          }
        }
      ],
      regenerateFigures: (params) => {
        const figs = params.map((p, i) => ({ key: `ma${i + 1}`, title: `MA${p}: `, type: 'line' }))
        figs.push({ key: 'volume', title: 'VOLUME: ', type: 'bar', baseValue: 0, styles: ({ data }) => ({ color: data?.current?.close > data?.current?.open ? VOL_UP : VOL_DOWN }) })
        return figs
      },
      calc: (dataList, indicator) => {
        const params = indicator.calcParams
        const figures = indicator.figures
        const volSums = []
        return dataList.map((kLineData, i) => {
          const volume = kLineData.volume ?? 0
          const vol = { volume, open: kLineData.open, close: kLineData.close }
          params.forEach((p, index) => {
            volSums[index] = (volSums[index] ?? 0) + volume
            if (i >= p - 1) {
              vol[figures[index].key] = volSums[index] / p
              volSums[index] -= (dataList[i - (p - 1)].volume ?? 0)
            }
          })
          return vol
        })
      }
    }
    klinecharts.registerIndicator(volIndicator)
    console.log('[VOL] VOL indicator registered at runtime')
    return true
  } catch (error) {
    console.error('[VOL] Failed to register VOL indicator:', error)
    return false
  }
}

/**
 * 注册MACD指标到KLineChart（与 indicators/macd.ts 一致：12,26,9，红涨绿跌）
 * @param {object} klinecharts - KLineChart库对象（window.klinecharts）
 * @returns {boolean} 是否成功注册
 */
export function registerMACDIndicator(klinecharts) {
  if (!klinecharts || typeof klinecharts.registerIndicator !== 'function') {
    console.error('[MACD] klinecharts.registerIndicator is not available')
    return false
  }

  try {
    const macdIndicator = {
      name: 'MACD',
      shortName: 'MACD',
      calcParams: [12, 26, 9],
      figures: [
        { key: 'dif', title: 'DIF: ', type: 'line' },
        { key: 'dea', title: 'DEA: ', type: 'line' },
        {
          key: 'macd',
          title: 'MACD: ',
          type: 'bar',
          baseValue: 0,
          styles: ({ data }) => {
            const prevMacd = data?.prev?.macd ?? Number.MIN_SAFE_INTEGER
            const currentMacd = data?.current?.macd ?? Number.MIN_SAFE_INTEGER
            const color = currentMacd > 0 ? MACD_UP : (currentMacd < 0 ? MACD_DOWN : '#888')
            const style = prevMacd < currentMacd ? 'stroke' : 'fill'
            return { style, color, borderColor: color }
          }
        }
      ],
      calc: (dataList, indicator) => {
        const params = indicator.calcParams
        let closeSum = 0
        let emaShort = 0
        let emaLong = 0
        let dif = 0
        let difSum = 0
        let dea = 0
        const maxPeriod = Math.max(params[0], params[1])
        return dataList.map((kLineData, i) => {
          const macd = {}
          const close = kLineData.close
          closeSum += close
          if (i >= params[0] - 1) {
            if (i > params[0] - 1) {
              emaShort = (2 * close + (params[0] - 1) * emaShort) / (params[0] + 1)
            } else {
              emaShort = closeSum / params[0]
            }
          }
          if (i >= params[1] - 1) {
            if (i > params[1] - 1) {
              emaLong = (2 * close + (params[1] - 1) * emaLong) / (params[1] + 1)
            } else {
              emaLong = closeSum / params[1]
            }
          }
          if (i >= maxPeriod - 1) {
            dif = emaShort - emaLong
            macd.dif = dif
            difSum += dif
            if (i >= maxPeriod + params[2] - 2) {
              if (i > maxPeriod + params[2] - 2) {
                dea = (dif * 2 + dea * (params[2] - 1)) / (params[2] + 1)
              } else {
                dea = difSum / params[2]
              }
              macd.macd = (dif - dea) * 2
              macd.dea = dea
            }
          }
          return macd
        })
      }
    }
    klinecharts.registerIndicator(macdIndicator)
    console.log('[MACD] MACD indicator registered at runtime')
    return true
  } catch (error) {
    console.error('[MACD] Failed to register MACD indicator:', error)
    return false
  }
}

/**
 * 注册所有自定义指标
 * @param {object} klinecharts - KLineChart库对象（window.klinecharts）
 */
export function registerAllCustomIndicators(klinecharts) {
  registerEMAIndicator(klinecharts)
  registerRSIIndicator(klinecharts)
  registerATRIndicator(klinecharts)
  registerADXIndicator(klinecharts)
  registerKDJIndicator(klinecharts)
  registerVOLIndicator(klinecharts)
  registerMACDIndicator(klinecharts)
}
