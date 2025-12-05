/**
 * 自定义数据接入类
 * 实现 KLineChart Pro 版本的数据接入接口
 * 参考 klinecharts-pro/index.html 中的 AkshareDatafeed 实现方式
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
 * 自定义数据接入类
 * 实现 @klinecharts/pro 的 Datafeed 接口
 */
export class CustomDatafeed {
  constructor() {
    this.socket = null
    this.subscriptions = new Map() // 存储订阅信息: key = `${symbol.ticker}:${period.text}`, value = { callback, symbol, period }
    this.marketPrices = [] // 缓存市场行情数据
  }

  /**
   * 模糊搜索标的
   * 在搜索框输入的时候触发
   * 返回标的信息数组
   * 参考 klinecharts-pro/index.html 中的 searchSymbols 实现
   * @param {string} search - 搜索关键词
   * @returns {Promise<SymbolInfo[]>}
   */
  async searchSymbols(search = '') {
    try {
      console.log('[CustomDatafeed] Searching symbols:', search)
      
      // 获取市场行情数据（使用 fetch API，参考参考实现）
      if (this.marketPrices.length === 0) {
        const apiBaseUrl = getApiBaseUrl()
        const response = await fetch(`${apiBaseUrl}/api/market/prices`)
        
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`)
        }
        
        const prices = await response.json()
        this.marketPrices = Object.keys(prices).map(symbol => ({
          symbol,
          name: prices[symbol].name || `${symbol}永续合约`,
          contract_symbol: prices[symbol].contract_symbol || symbol
        }))
      }

      // 过滤匹配的标的（参考参考实现的过滤逻辑）
      const searchUpper = search.toUpperCase()
      const matched = this.marketPrices
        .filter(item => {
          const symbol = item.symbol.toUpperCase()
          const name = (item.name || '').toUpperCase()
          return symbol.includes(searchUpper) || name.includes(searchUpper)
        })
        .slice(0, 20) // 限制返回数量

      // 转换为 SymbolInfo 格式
      const symbols = matched.map(item => ({
        ticker: item.contract_symbol || item.symbol,
        shortName: item.symbol.replace('USDT', ''),
        name: item.name || `${item.symbol}永续合约`,
        exchange: 'BINANCE',
        market: 'futures',
        priceCurrency: 'usd',
        type: 'PERPETUAL'
      }))

      console.log('[CustomDatafeed] Found symbols:', symbols.length)
      return symbols
    } catch (error) {
      console.error('[CustomDatafeed] Error searching symbols:', error)
      return []
    }
  }

  /**
   * 获取历史K线数据
   * 当标的和周期发生变化的时候触发
   * @param {SymbolInfo} symbol - 标的信息
   * @param {Period} period - 周期信息
   * @param {number} from - 开始时间戳（毫秒）
   * @param {number} to - 结束时间戳（毫秒）
   * @returns {Promise<KLineData[]>}
   */
  async getHistoryKLineData(symbol, period, from, to) {
    try {
      console.log('[CustomDatafeed] Getting history K-line data:', {
        ticker: symbol?.ticker || symbol,
        period: period?.text || period,
        from: new Date(from).toISOString(),
        to: new Date(to).toISOString(),
        fromTimestamp: from,
        toTimestamp: to
      })

      // 将 period 转换为后端支持的 interval
      const interval = this.periodToInterval(period)
      if (!interval) {
        console.warn('[CustomDatafeed] Unsupported period:', period)
        return []
      }

      // 获取 ticker（支持 symbol 对象或字符串）
      const ticker = symbol?.ticker || symbol
      if (!ticker) {
        console.warn('[CustomDatafeed] Invalid symbol:', symbol)
        return []
      }

      // 计算需要的数据量（根据时间范围估算，但后端限制最多500条）
      // Pro 版本可能会请求较大的时间范围，我们需要获取足够的数据
      const limit = 500

      // 将时间戳转换为 ISO 格式字符串（后端期望的格式）
      // from 和 to 是毫秒时间戳，需要转换为 ISO 格式
      const startTimeISO = new Date(from).toISOString()
      const endTimeISO = new Date(to).toISOString()

      console.log('[CustomDatafeed] Requesting K-line data with time range:', {
        ticker,
        interval,
        limit,
        startTimeISO,
        endTimeISO,
        fromTimestamp: from,
        toTimestamp: to
      })

      // 调用后端 API 获取 K 线数据（使用 fetch API，参考参考实现）
      const apiBaseUrl = getApiBaseUrl()
      const params = new URLSearchParams({
        symbol: ticker,
        interval: interval,
        limit: limit.toString()
      })
      if (startTimeISO) {
        params.append('start_time', startTimeISO)
      }
      if (endTimeISO) {
        params.append('end_time', endTimeISO)
      }
      
      const response = await fetch(`${apiBaseUrl}/api/market/klines?${params.toString()}`)
      
      if (!response.ok) {
        const errorText = await response.text()
        console.error('[CustomDatafeed] HTTP错误详情:', errorText)
        throw new Error(`HTTP error! status: ${response.status}, details: ${errorText}`)
      }
      
      const result = await response.json()

      if (!result || !result.data || !Array.isArray(result.data)) {
        console.warn('[CustomDatafeed] Invalid response format:', result)
        return []
      }

      // 转换数据格式并过滤时间范围（参考参考实现的数据转换方式）
      const klines = result.data
        .map(kline => {
          // 处理时间戳：确保是数字类型（毫秒）
          let timestamp = kline.timestamp
          
          if (timestamp === null || timestamp === undefined) {
            // 如果没有 timestamp，尝试使用其他时间字段
            if (kline.kline_start_time) {
              timestamp = typeof kline.kline_start_time === 'number' 
                ? kline.kline_start_time 
                : new Date(kline.kline_start_time).getTime()
            } else if (kline.kline_end_time) {
              timestamp = typeof kline.kline_end_time === 'number'
                ? kline.kline_end_time
                : new Date(kline.kline_end_time).getTime()
            } else {
              return null // 无法确定时间戳，跳过
            }
          } else if (typeof timestamp === 'string') {
            // 字符串时间戳需要转换
            timestamp = new Date(timestamp).getTime()
            if (isNaN(timestamp)) {
              return null // 无效的时间戳
            }
          } else if (typeof timestamp !== 'number') {
            return null // 无效的时间戳类型
          }

          // 确保时间戳是毫秒（如果后端返回的是秒，需要乘以1000）
          // 通常时间戳大于 1e12 表示是毫秒，小于表示是秒
          if (timestamp < 1e12) {
            timestamp = timestamp * 1000
          }

          // 过滤时间范围：Pro 版本会传入 from 和 to，我们需要返回这个范围内的数据
          // 注意：Pro 版本可能会请求未来的数据，我们返回空数组即可
          if (timestamp < from || timestamp > to) {
            return null
          }

          // 转换价格和成交量数据，确保是数字类型
          const open = parseFloat(kline.open)
          const high = parseFloat(kline.high)
          const low = parseFloat(kline.low)
          const close = parseFloat(kline.close)
          const volume = parseFloat(kline.volume) || 0

          // 验证数据有效性
          if (isNaN(open) || isNaN(high) || isNaN(low) || isNaN(close) || close <= 0) {
            return null // 无效的价格数据
          }

          // 确保 high >= max(open, close) 和 low <= min(open, close)
          const maxPrice = Math.max(open, close)
          const minPrice = Math.min(open, close)
          const validHigh = Math.max(high, maxPrice)
          const validLow = Math.min(low, minPrice)

          return {
            timestamp: Math.floor(timestamp), // 确保是整数
            open: open,
            high: validHigh,
            low: validLow,
            close: close,
            volume: volume
          }
        })
        .filter(kline => kline !== null && kline.timestamp > 0)
        .sort((a, b) => a.timestamp - b.timestamp) // 按时间升序排序（Pro 版本要求）

      console.log('[CustomDatafeed] Loaded K-line data:', {
        total: klines.length,
        firstTimestamp: klines.length > 0 ? new Date(klines[0].timestamp).toISOString() : null,
        lastTimestamp: klines.length > 0 ? new Date(klines[klines.length - 1].timestamp).toISOString() : null,
        requestedFrom: new Date(from).toISOString(),
        requestedTo: new Date(to).toISOString()
      })

      return klines
    } catch (error) {
      console.error('[CustomDatafeed] Error getting history K-line data:', error)
      return []
    }
  }

  /**
   * 订阅标的在某个周期的实时数据
   * 当标的和周期发生变化的时候触发
   * 参考 klinecharts-pro/index.html 中的实现方式
   * @param {SymbolInfo} symbol - 标的信息
   * @param {Period} period - 周期信息
   * @param {Function} callback - 数据回调函数
   */
  subscribe(symbol, period, callback) {
    try {
      // 支持 symbol 对象或字符串
      const ticker = symbol?.ticker || symbol
      const periodText = period?.text || period
      
      console.log('[CustomDatafeed] Subscribing to real-time data:', {
        ticker,
        period: periodText,
        symbol,
        period
      })

      // 确保 WebSocket 连接已建立
      if (!this.socket || !this.socket.connected) {
        console.log('[CustomDatafeed] Initializing WebSocket connection...')
        this.socket = createSocketConnection()
        
        // 监听实时 K 线更新
        this.socket.on('klines:update', (data) => {
          try {
            const symbol = data.symbol || data.ticker
            const interval = data.interval || data.period
            const key = `${symbol}:${interval}`
            const subscription = this.subscriptions.get(key)
            
            if (subscription && subscription.callback) {
              // 获取 K 线数据（可能在不同的字段中）
              const kline = data.kline || data.data || data
              
              // 处理时间戳
              let timestamp = kline.timestamp
              if (typeof timestamp === 'string') {
                timestamp = new Date(timestamp).getTime()
              } else if (typeof timestamp !== 'number') {
                if (kline.kline_start_time) {
                  timestamp = typeof kline.kline_start_time === 'number'
                    ? kline.kline_start_time
                    : new Date(kline.kline_start_time).getTime()
                } else if (kline.kline_end_time) {
                  timestamp = typeof kline.kline_end_time === 'number'
                    ? kline.kline_end_time
                    : new Date(kline.kline_end_time).getTime()
                } else {
                  timestamp = Date.now() // 使用当前时间作为后备
                }
              }
              
              // 确保时间戳是毫秒
              if (timestamp < 1e12) {
                timestamp = timestamp * 1000
              }

              // 转换数据格式为 Pro 版本要求的格式
              const klineData = {
                timestamp: Math.floor(timestamp),
                open: parseFloat(kline.open) || 0,
                high: parseFloat(kline.high) || 0,
                low: parseFloat(kline.low) || 0,
                close: parseFloat(kline.close) || 0,
                volume: parseFloat(kline.volume) || 0
              }
              
              // 验证数据有效性
              if (klineData.timestamp > 0 && klineData.close > 0) {
                console.log('[CustomDatafeed] Received real-time K-line update:', {
                  key,
                  klineData,
                  timestamp: new Date(klineData.timestamp).toISOString()
                })
                
                // Pro 版本的 callback 期望单个 K 线数据对象
                subscription.callback(klineData)
              } else {
                console.warn('[CustomDatafeed] Invalid real-time K-line data:', klineData)
              }
            } else {
              console.debug('[CustomDatafeed] No subscription found for:', key)
            }
          } catch (error) {
            console.error('[CustomDatafeed] Error processing real-time K-line update:', error, data)
          }
        })
      }

      // 将 period 转换为后端支持的 interval
      const interval = this.periodToInterval(period)
      if (!interval) {
        console.warn('[CustomDatafeed] Unsupported period for subscription:', period)
        return
      }

      // 存储订阅信息
      const key = `${ticker}:${interval}`
      this.subscriptions.set(key, {
        callback,
        symbol,
        period,
        interval
      })

      // 向后端发送订阅请求
      if (this.socket && this.socket.connected) {
        this.socket.emit('klines:subscribe', {
          symbol: ticker,
          interval: interval
        })
        console.log('[CustomDatafeed] Subscription sent to backend:', { symbol: ticker, interval })
      } else {
        console.warn('[CustomDatafeed] WebSocket not connected, subscription will be sent when connected')
        // 等待连接后发送订阅
        this.socket.once('connect', () => {
          this.socket.emit('klines:subscribe', {
            symbol: ticker,
            interval: interval
          })
          console.log('[CustomDatafeed] Subscription sent after connection:', { symbol: ticker, interval })
        })
      }
    } catch (error) {
      console.error('[CustomDatafeed] Error subscribing:', error)
    }
  }

  /**
   * 取消订阅标的在某个周期的实时数据
   * 当标的和周期发生变化的时候触发
   * @param {SymbolInfo} symbol - 标的信息
   * @param {Period} period - 周期信息
   */
  unsubscribe(symbol, period) {
    try {
      // 支持 symbol 对象或字符串
      const ticker = symbol?.ticker || symbol
      const periodText = period?.text || period
      
      console.log('[CustomDatafeed] Unsubscribing from real-time data:', {
        ticker,
        period: periodText
      })

      // 将 period 转换为后端支持的 interval
      const interval = this.periodToInterval(period)
      if (!interval) {
        console.warn('[CustomDatafeed] Cannot unsubscribe: invalid interval for period:', period)
        return
      }

      // 移除订阅信息
      const key = `${ticker}:${interval}`
      const hadSubscription = this.subscriptions.has(key)
      this.subscriptions.delete(key)

      // 向后端发送取消订阅请求
      if (this.socket && this.socket.connected && hadSubscription) {
        this.socket.emit('klines:unsubscribe', {
          symbol: ticker,
          interval: interval
        })
        console.log('[CustomDatafeed] Unsubscription sent to backend:', { symbol: ticker, interval })
      }
    } catch (error) {
      console.error('[CustomDatafeed] Error unsubscribing:', error)
    }
  }

  /**
   * 将 Pro 版本的 Period 转换为后端支持的 interval
   * @param {Period} period - Pro 版本的周期对象，格式：{ multiplier: number, timespan: string, text: string }
   * @returns {string|null} - 后端支持的 interval 字符串
   */
  periodToInterval(period) {
    if (!period) {
      return null
    }

    // 如果 period 是字符串，直接返回
    if (typeof period === 'string') {
      return period
    }

    // 如果 period 有 text 属性，使用 text
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

    // 如果 period 有 multiplier 和 timespan，尝试构建
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

  /**
   * 清理资源
   */
  destroy() {
    // 取消所有订阅
    for (const [key, subscription] of this.subscriptions.entries()) {
      this.unsubscribe(subscription.symbol, subscription.period)
    }
    this.subscriptions.clear()

    // 断开 WebSocket 连接
    if (this.socket) {
      this.socket.disconnect()
      this.socket = null
    }
  }
}

