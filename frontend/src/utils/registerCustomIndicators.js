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
        const sumCloseAs = []
        const sumCloseBs = []
        return dataList.map((kLineData, i) => {
          const rsi = {}
          const prevClose = (dataList[i - 1] ?? kLineData).close
          const tmp = kLineData.close - prevClose
          params.forEach((p, index) => {
            if (tmp > 0) {
              sumCloseAs[index] = (sumCloseAs[index] || 0) + tmp
            } else {
              sumCloseBs[index] = (sumCloseBs[index] || 0) + Math.abs(tmp)
            }
            if (i >= p - 1) {
              if (sumCloseBs[index] !== 0) {
                rsi[figures[index].key] = 100 - (100.0 / (1 + sumCloseAs[index] / sumCloseBs[index]))
              } else {
                rsi[figures[index].key] = 0
              }
              const agoData = dataList[i - (p - 1)]
              const agoPreData = dataList[i - p] ?? agoData
              const agoTmp = agoData.close - agoPreData.close
              if (agoTmp > 0) {
                sumCloseAs[index] -= agoTmp
              } else {
                sumCloseBs[index] -= Math.abs(agoTmp)
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
        
        // 为每个周期维护TR的累积和
        const trSums = []
        
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
            // 如果数据足够，先移除最旧的TR值（滑动窗口）
            if (i >= period) {
              const oldTrIndex = i - period
              const oldKLineData = dataList[oldTrIndex]
              const oldPrevClose = oldTrIndex > 0 ? dataList[oldTrIndex - 1].close : oldKLineData.close
              const oldTr1 = oldKLineData.high - oldKLineData.low
              const oldTr2 = Math.abs(oldKLineData.high - oldPrevClose)
              const oldTr3 = Math.abs(oldKLineData.low - oldPrevClose)
              const oldTr = Math.max(oldTr1, oldTr2, oldTr3)
              trSums[index] = (trSums[index] || 0) - oldTr
            }
            
            // 累积当前TR值
            trSums[index] = (trSums[index] || 0) + tr
            
            // 如果数据足够，计算ATR（SMA of TR）
            if (i >= period - 1) {
              // 计算TR的简单移动平均（SMA）
              const atrValue = trSums[index] / period
              atr[figures[index].key] = atrValue
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
 * 注册所有自定义指标
 * @param {object} klinecharts - KLineChart库对象（window.klinecharts）
 */
export function registerAllCustomIndicators(klinecharts) {
  registerRSIIndicator(klinecharts)
  registerATRIndicator(klinecharts)
}
