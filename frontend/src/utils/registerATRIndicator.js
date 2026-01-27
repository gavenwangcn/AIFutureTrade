/**
 * ATR指标运行时注册
 * 由于使用UMD方式加载klinecharts.min.js，需要在运行时动态注册自定义指标
 * 参考：https://klinecharts.com/api/chart/registerIndicator
 */

// ATR曲线颜色配置
const ATR_COLORS = ['#2DC08E', '#935EBD', '#FF9600']

/**
 * 注册ATR指标到KLineChart
 * @param {object} klinecharts - KLineChart库对象（window.klinecharts）
 */
export function registerATRIndicator(klinecharts) {
  if (!klinecharts || typeof klinecharts.registerIndicator !== 'function') {
    console.error('[ATR] klinecharts.registerIndicator is not available')
    return false
  }

  // 检查是否已经注册
  const supportedIndicators = klinecharts.getSupportedIndicators()
  if (supportedIndicators.includes('ATR')) {
    console.log('[ATR] ATR indicator already registered')
    return true
  }

  try {
    // ATR指标定义
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
    console.log('[ATR] ATR indicator registered successfully')
    return true
  } catch (error) {
    console.error('[ATR] Failed to register ATR indicator:', error)
    return false
  }
}
