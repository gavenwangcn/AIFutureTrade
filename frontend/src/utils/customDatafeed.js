/**
 * 自定义数据加载器
 * 实现 KLineChart 10.0.0 版本的 DataLoader 接口
 * 参考 https://klinecharts.com/guide/quick-start
 * 使用 fetch API 直接调用后端接口，避免 ES6 模块依赖
 */

import { createSocketConnection } from './websocket.js'

// 获取 API 基础 URL（与 api.js 保持一致）
function getApiBaseUrl() {
  const isDev = import.meta.env.DEV
  if (import.meta.env.VITE_BACKEND_URL) {
    return import.meta.env.VITE_BACKEND_URL
  } else if (isDev) {
    // 开发环境：使用相对路径，通过 Vite 代理
    return ''
  } else {
    // 生产环境：使用当前域名+配置的端口
    const backendPort = import.meta.env.VITE_BACKEND_PORT || '5002'
    const protocol = window.location.protocol
    const hostname = window.location.hostname
    return `${protocol}//${hostname}:${backendPort}`
  }
}

/**
 * 创建数据加载器
 * 实现 KLineChart 10.0.0 的 DataLoader 接口
 * @returns {DataLoader} 数据加载器对象
 */
export function createDataLoader() {
  const subscriptions = new Map() // 存储订阅信息: key = `${symbol.ticker}:${period.text}`, value = { callback, symbol, period }
  const marketPrices = [] // 缓存市场行情数据

  /**
   * 获取历史K线数据
   * 当标的和周期发生变化或图表拖动到边界时触发
   * @param {DataLoaderGetBarsParams} params - 参数对象
   * @param {DataLoadType} params.type - 加载类型: 'init' | 'forward' | 'backward' | 'update'
   * @param {number|null} params.timestamp - 时间戳（毫秒），用于向前或向后加载
   * @param {SymbolInfo} params.symbol - 标的信息
   * @param {Period} params.period - 周期信息
   * @param {Function} params.callback - 回调函数，用于返回数据
   */
  async function getBars(params) {
    try {
      const { type, timestamp, symbol, period, callback } = params
      
      console.log('[DataLoader] Getting K-line data:', {
        type,
        timestamp: timestamp ? new Date(timestamp).toISOString() : null,
        ticker: symbol?.ticker || symbol,
        period: period?.text || period
      })

      // 将 period 转换为后端支持的 interval
      const interval = periodToInterval(period)
      if (!interval) {
        console.warn('[DataLoader] Unsupported period:', period)
        callback([])
        return
      }

      // 获取 ticker
      const ticker = symbol?.ticker || symbol
      if (!ticker) {
        console.warn('[DataLoader] Invalid symbol:', symbol)
        callback([])
        return
      }

      // 计算需要的数据量（后端限制最多500条）
      const limit = 500

      // 构建请求参数
      const apiBaseUrl = getApiBaseUrl()
      const urlParams = new URLSearchParams({
        symbol: ticker,
        interval: interval,
        limit: limit.toString()
      })

      // 根据加载类型设置时间范围
      if (timestamp) {
        const timeISO = new Date(timestamp).toISOString()
        if (type === 'backward') {
          // 向后加载：使用 timestamp 作为结束时间
          urlParams.append('end_time', timeISO)
        } else if (type === 'forward') {
          // 向前加载：使用 timestamp 作为开始时间
          urlParams.append('start_time', timeISO)
        }
      }
      
      const response = await fetch(`${apiBaseUrl}/api/market/klines?${urlParams.toString()}`)
      
      if (!response.ok) {
        const errorText = await response.text()
        console.error('[DataLoader] HTTP错误详情:', errorText)
        callback([])
        return
      }
      
      const result = await response.json()

      if (!result || !result.data || !Array.isArray(result.data)) {
        console.warn('[DataLoader] Invalid response format:', result)
        callback([])
        return
      }

      // 转换数据格式
      const klines = result.data
        .map(kline => {
          // 处理时间戳：确保是数字类型（毫秒）
          let ts = kline.timestamp
          
          if (ts === null || ts === undefined) {
            if (kline.kline_start_time) {
              ts = typeof kline.kline_start_time === 'number' 
                ? kline.kline_start_time 
                : new Date(kline.kline_start_time).getTime()
            } else if (kline.kline_end_time) {
              ts = typeof kline.kline_end_time === 'number'
                ? kline.kline_end_time
                : new Date(kline.kline_end_time).getTime()
            } else {
              return null
            }
          } else if (typeof ts === 'string') {
            ts = new Date(ts).getTime()
            if (isNaN(ts)) {
              return null
            }
          } else if (typeof ts !== 'number') {
            return null
          }

          // 确保时间戳是毫秒
          if (ts < 1e12) {
            ts = ts * 1000
          }

          // 转换价格和成交量数据
          const open = parseFloat(kline.open)
          const high = parseFloat(kline.high)
          const low = parseFloat(kline.low)
          const close = parseFloat(kline.close)
          const volume = parseFloat(kline.volume) || 0

          // 验证数据有效性
          if (isNaN(open) || isNaN(high) || isNaN(low) || isNaN(close) || close <= 0) {
            return null
          }

          // 确保 high >= max(open, close) 和 low <= min(open, close)
          const maxPrice = Math.max(open, close)
          const minPrice = Math.min(open, close)
          const validHigh = Math.max(high, maxPrice)
          const validLow = Math.min(low, minPrice)

          return {
            timestamp: Math.floor(ts),
            open: open,
            high: validHigh,
            low: validLow,
            close: close,
            volume: volume
          }
        })
        .filter(kline => kline !== null && kline.timestamp > 0)
        .sort((a, b) => a.timestamp - b.timestamp) // 按时间升序排序

      console.log('[DataLoader] Loaded K-line data:', {
        total: klines.length,
        type,
        firstTimestamp: klines.length > 0 ? new Date(klines[0].timestamp).toISOString() : null,
        lastTimestamp: klines.length > 0 ? new Date(klines[klines.length - 1].timestamp).toISOString() : null
      })

      // 根据加载类型决定是否还有更多数据
      const hasMore = klines.length >= limit
      callback(klines, hasMore)
    } catch (error) {
      console.error('[DataLoader] Error getting K-line data:', error)
      callback([])
    }
  }

  /**
   * 订阅实时K线数据（可选）
   * 当设置标的和周期后，getBars 完成之后触发
   * @param {DataLoaderSubscribeBarParams} params - 参数对象
   * @param {SymbolInfo} params.symbol - 标的信息
   * @param {Period} params.period - 周期信息
   * @param {Function} params.callback - 数据回调函数
   */
  function subscribeBar(params) {
    // K线页面已改为仅使用历史数据，不再订阅实时K线更新
    // 此方法保留空实现以兼容 KLineChart 库的接口要求
    console.log('[DataLoader] subscribeBar called but real-time subscription is disabled (using history data only)')
  }

  /**
   * 取消订阅实时K线数据（可选）
   * 当设置标的和周期后触发
   * @param {DataLoaderUnsubscribeBarParams} params - 参数对象
   * @param {SymbolInfo} params.symbol - 标的信息
   * @param {Period} params.period - 周期信息
   */
  function unsubscribeBar(params) {
    // K线页面已改为仅使用历史数据，不再订阅实时K线更新
    // 此方法保留空实现以兼容 KLineChart 库的接口要求
    console.log('[DataLoader] unsubscribeBar called but real-time subscription is disabled (using history data only)')
  }

  /**
   * 将 Period 转换为后端支持的 interval
   * @param {Period} period - 周期对象，格式：{ span: number, type: string } 或 { multiplier: number, timespan: string, text: string }
   * @returns {string|null} - 后端支持的 interval 字符串
   */
  function periodToInterval(period) {
    if (!period) {
      return null
    }

    // 如果 period 是字符串，直接返回
    if (typeof period === 'string') {
      return period
    }

    // KLineChart 10.0.0 使用 { span: number, type: string } 格式
    if (period.span && period.type) {
      const typeMap = {
        'minute': 'm',
        'hour': 'h',
        'day': 'd',
        'week': 'w'
      }
      const suffix = typeMap[period.type]
      if (suffix) {
        return `${period.span}${suffix}`
      }
    }

    // 兼容旧格式：如果 period 有 text 属性，使用 text
    if (period.text) {
      const periodMap = {
        '1m': '1m',
        '3m': '3m',
        '5m': '5m',
        '15m': '15m',
        '30m': '30m',
        '1h': '1h',
        '2h': '2h',
        '4h': '4h',
        '6h': '6h',
        '12h': '12h',
        '1d': '1d',
        '1w': '1w'
      }
      return periodMap[period.text] || null
    }

    // 兼容旧格式：如果 period 有 multiplier 和 timespan，尝试构建
    if (period.multiplier && period.timespan) {
      const timespanMap = {
        'minute': 'm',
        'hour': 'h',
        'day': 'd',
        'week': 'w'
      }
      const suffix = timespanMap[period.timespan]
      if (suffix) {
        return `${period.multiplier}${suffix}`
      }
    }

    return null
  }

  // 返回 DataLoader 对象
  return {
    getBars,
    subscribeBar,
    unsubscribeBar
  }
}

