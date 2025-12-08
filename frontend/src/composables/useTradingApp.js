/**
 * Trading App Composable
 * 提供交易应用的主要业务逻辑和状态管理
 */

import { ref, computed, nextTick, onUnmounted } from 'vue'
import { createSocketConnection } from '../utils/websocket.js'
import { modelApi, marketApi } from '../services/api.js'
import * as echarts from 'echarts'

export function useTradingApp() {
  // ============ 状态管理 ============
  
  // 模型相关状态
  const currentModelId = ref(null)
  const models = ref([])
  const isAggregatedView = ref(false)
  const modelLeverageMap = ref({})
  const providers = ref([]) // 用于获取提供方名称
  
  // 市场数据状态
  const marketPrices = ref([])
  const leaderboardGainers = ref([])
  const leaderboardLosers = ref([])
  const leaderboardStatus = ref('等待数据...')
  const leaderboardStatusType = ref('default') // 'updating' | 'success' | 'error' | 'default'
  const isRefreshingLeaderboard = ref(false)
  const isRefreshingAll = ref(false)
  
  // 投资组合状态
  const portfolio = ref({
    totalValue: 0,
    availableCash: 0,
    realizedPnl: 0,
    unrealizedPnl: 0
  })
  const accountValueHistory = ref([]) // 账户价值历史数据（用于图表）
  const aggregatedChartData = ref([]) // 聚合视图图表数据
  const positions = ref([])
  const trades = ref([])
  const conversations = ref([])
  
  // ClickHouse 涨幅榜同步状态
  const clickhouseLeaderboardSyncRunning = ref(true)
  
  // UI 状态
  const loggerEnabled = ref(localStorage.getItem('frontendLoggingEnabled') !== 'false')
  const showSettingsModal = ref(false)
  const showStrategyModal = ref(false)
  const showFutureConfigModal = ref(false)
  const showApiProviderModal = ref(false)
  const showAddModelModal = ref(false)
  const showLeverageModal = ref(false)
  const pendingLeverageModelId = ref(null)
  const leverageModelName = ref('')
  
  // 加载状态
  const loading = ref({
    models: false,
    marketPrices: false,
    leaderboard: false,
    portfolio: false,
    positions: false,
    trades: false,
    conversations: false
  })
  
  // 错误状态
  const errors = ref({})
  
  // WebSocket连接
  const socket = ref(null)
  let websocketMonitorInterval = null // WebSocket 监控定时器
  let leaderboardRefreshInterval = null // 涨跌榜自动刷新定时器（轮询方式，默认5秒）
  
  // ECharts 实例
  const accountChart = ref(null)

  // ============ 计算属性 ============
  
  /**
   * 当前选中的模型
   */
  const currentModel = computed(() => {
    return models.value.find(m => m.id === currentModelId.value) || null
  })

  /**
   * 是否有加载中的请求
   */
  const isLoading = computed(() => {
    return Object.values(loading.value).some(v => v === true)
  })

  // ============ WebSocket 初始化 ============
  
  /**
   * 初始化 WebSocket 连接
   */
  const initWebSocket = () => {
    try {
      // 如果已经存在连接，先断开
      if (socket.value) {
        if (socket.value.connected) {
          console.log('[WebSocket] 断开现有连接')
          socket.value.disconnect()
        }
        // 移除所有事件监听器
        socket.value.removeAllListeners()
      }

      socket.value = createSocketConnection()

      // 连接成功事件
      socket.value.on('connect', () => {
        console.log('[WebSocket] ✅ ========== 已连接到服务器 ==========')
        console.log('[WebSocket] Socket ID:', socket.value.id)
        console.log('[WebSocket] 连接状态:', {
          connected: socket.value.connected,
          disconnected: socket.value.disconnected,
          id: socket.value.id
        })
        leaderboardStatus.value = '已连接，等待数据...'
        leaderboardStatusType.value = 'default'
        
        // 涨跌幅榜已改为轮询方式，不再使用WebSocket推送
        // 以下代码已移除（仅保留其他WebSocket功能的检查）：
        // - leaderboard:update 监听器检查
        // 注意：Socket.IO 客户端可能不支持 eventNames() 方法，使用 hasListeners() 检查
        try {
          // 尝试获取已注册的事件（如果支持）
          if (typeof socket.value.eventNames === 'function') {
            const registeredEvents = socket.value.eventNames()
            console.log('[WebSocket] 已注册的事件监听器:', Array.from(registeredEvents))
          } else {
            console.log('[WebSocket] eventNames() 方法不可用，跳过事件列表检查')
          }
        } catch (e) {
          console.warn('[WebSocket] 检查事件监听器时出错:', e)
        }
        
        // 涨跌幅榜已改为轮询方式，不再通过WebSocket获取
        // 连接成功后不再请求初始涨跌幅榜数据（由轮询机制处理）
        console.log('[WebSocket] ✅ WebSocket连接成功（涨跌幅榜已改为轮询方式，不再通过WebSocket获取）')
      })

      // 涨跌幅榜已改为轮询方式，不再监听WebSocket推送事件
      // 以下代码已移除：
      // - leaderboard:update 事件监听
      // - leaderboard:error 事件监听
      // - leaderboard:request 事件发送
      
      // 涨跌幅榜错误事件（已移除，改为轮询方式）
      // socket.value.on('leaderboard:error', (error) => {
      //   console.error('[WebSocket] ❌ 涨跌幅榜更新错误', error)
      //   leaderboardStatus.value = '更新失败'
      //   
      //   // 更新错误状态指示器
        const statusEl = document.querySelector('.status-indicator')
        if (statusEl) {
          statusEl.classList.add('error')
          setTimeout(() => {
            statusEl.classList.remove('error')
          }, 3000)
        }
      })

      // 连接断开事件
      socket.value.on('disconnect', (reason) => {
        console.warn('[WebSocket] ⚠️ 已断开连接:', reason)
        leaderboardStatus.value = '连接断开'
        leaderboardStatusType.value = 'error'
      })

      // 重新连接事件
      socket.value.on('reconnect', (attemptNumber) => {
        console.log(`[WebSocket] 🔄 重新连接成功 (尝试 ${attemptNumber} 次)`)
        // 涨跌幅榜已改为轮询方式，不再通过WebSocket请求数据
        // 轮询机制会自动刷新数据，无需在重连后手动请求
      })

      // 连接错误事件
      socket.value.on('connect_error', (error) => {
        console.error('[WebSocket] ❌ 连接错误:', error)
        console.error('[WebSocket] 错误详情:', {
          message: error.message,
          description: error.description,
          context: error.context,
          type: error.type
        })
        leaderboardStatus.value = '连接失败'
        leaderboardStatusType.value = 'error'
      })

      // 重连尝试事件
      socket.value.on('reconnect_attempt', (attemptNumber) => {
        console.log(`[WebSocket] 🔄 尝试重新连接 (第 ${attemptNumber} 次)...`)
        leaderboardStatus.value = `重连中 (${attemptNumber})...`
      })

      // 重连失败事件
      socket.value.on('reconnect_failed', () => {
        console.error('[WebSocket] ❌ 重新连接失败')
        leaderboardStatus.value = '重连失败'
      })

      // 添加连接状态检查（定期检查连接状态）
      const checkConnection = () => {
        if (socket.value) {
          const isConnected = socket.value.connected
          if (!isConnected && socket.value.disconnected) {
            console.warn('[WebSocket] ⚠️ 检测到连接断开，尝试重新连接...')
            try {
              socket.value.connect()
            } catch (e) {
              console.error('[WebSocket] 重新连接失败:', e)
            }
          }
        }
      }
      
      // 每30秒检查一次连接状态
      websocketMonitorInterval = setInterval(checkConnection, 30000)
      
      // 在连接断开时清理定时器
      socket.value.on('disconnect', () => {
        if (websocketMonitorInterval) {
          clearInterval(websocketMonitorInterval)
          websocketMonitorInterval = null
        }
      })

    } catch (error) {
      console.error('[WebSocket] ❌ 初始化失败:', error)
      leaderboardStatus.value = 'WebSocket 初始化失败'
    }
  }

  /**
   * 启动涨跌榜自动刷新（轮询方式）
   * 使用配置的刷新时间（FUTURES_LEADERBOARD_REFRESH，默认5秒）
   * 整体刷新渲染，不是一条一条刷新
   */
  const startLeaderboardAutoRefresh = () => {
    // 清除已有定时器
    if (leaderboardRefreshInterval) {
      clearInterval(leaderboardRefreshInterval)
      leaderboardRefreshInterval = null
    }

    // 立即获取一次数据
    loadLeaderboard(false)

    // 使用配置的刷新时间（默认5秒，与后端FUTURES_LEADERBOARD_REFRESH配置一致）
    // 前端轮询时间应该与后端同步间隔一致，确保数据实时性
    const refreshInterval = 5000 // 5秒，与后端FUTURES_LEADERBOARD_REFRESH=5一致
    
    leaderboardRefreshInterval = setInterval(() => {
      console.log(`[TradingApp] 轮询刷新涨跌榜数据（${refreshInterval/1000}秒间隔）`)
      loadLeaderboard(false) // 整体刷新，不是一条一条刷新
    }, refreshInterval)

    console.log(`[TradingApp] ✅ 涨跌榜自动刷新已启动（轮询方式，${refreshInterval/1000}秒间隔）`)
  }

  /**
   * 停止涨跌榜自动刷新
   */
  const stopLeaderboardAutoRefresh = () => {
    if (leaderboardRefreshInterval) {
      clearInterval(leaderboardRefreshInterval)
      leaderboardRefreshInterval = null
      console.log('[TradingApp] 涨跌榜自动刷新已停止')
    }
  }

  // ============ 数据加载方法 ============
  
  /**
   * 加载模型列表
   */
  const loadModels = async () => {
    loading.value.models = true
    errors.value.models = null
    try {
      const data = await modelApi.getAll()
      // 后端直接返回数组格式
      models.value = Array.isArray(data) ? data : []
    } catch (error) {
      console.error('[TradingApp] Error loading models:', error)
      errors.value.models = error.message
    } finally {
      loading.value.models = false
    }
  }

  /**
   * 加载市场行情价格
   */
  const loadMarketPrices = async () => {
    loading.value.marketPrices = true
    errors.value.marketPrices = null
    try {
      const data = await marketApi.getPrices()
      // 后端返回的是对象，格式：{ symbol: { price, change_24h, name, contract_symbol, ... }, ... }
      // 转换为数组格式，保持原始数据结构
      marketPrices.value = Object.entries(data).map(([symbol, info]) => ({
        symbol,
        price: info.price || 0,
        change: info.change_24h || 0,
        change_24h: info.change_24h || 0,
        name: info.name || '',
        contract_symbol: info.contract_symbol || symbol,
        daily_volume: info.daily_volume || 0,
        source: info.source || 'configured',
        ...info
      }))
    } catch (error) {
      console.error('[TradingApp] Error loading market prices:', error)
      errors.value.marketPrices = error.message
    } finally {
      loading.value.marketPrices = false
    }
  }

  /**
   * 加载涨跌幅榜
   */
  const loadLeaderboard = async (force = false) => {
    loading.value.leaderboard = true
    isRefreshingLeaderboard.value = true
    errors.value.leaderboard = null
    
    // 更新状态为刷新中（黄色）
    leaderboardStatus.value = '正在更新...'
    leaderboardStatusType.value = 'updating'
    
    try {
      const data = await marketApi.getLeaderboard(10, force)
      // 后端返回格式：{ success: true, gainers: [], losers: [] } 或直接返回 { gainers: [], losers: [] }
      if (data.success !== false) {
        const gainers = data.gainers || []
        const losers = data.losers || []
        
      // 检查是否有数据
      if (gainers.length > 0 || losers.length > 0) {
        // 整体刷新渲染：直接替换整个数组（不是一条一条刷新）
        leaderboardGainers.value = gainers
        leaderboardLosers.value = losers
          
          // 更新成功：显示日期时间格式（绿色）
          const updateTime = new Date()
          const dateStr = updateTime.toLocaleDateString('zh-CN', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit'
          })
          const timeStr = updateTime.toLocaleTimeString('zh-CN', {
            hour12: false,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
          })
          leaderboardStatus.value = `最后更新: ${dateStr} ${timeStr}`
          leaderboardStatusType.value = 'success'
        } else {
          // 没有数据：显示更新失败（白色）
          leaderboardStatus.value = '更新失败'
          leaderboardStatusType.value = 'error'
        }
      } else {
        // 更新失败：显示更新失败（白色）
        leaderboardStatus.value = '更新失败'
        leaderboardStatusType.value = 'error'
      }
    } catch (error) {
      console.error('[TradingApp] Error loading leaderboard:', error)
      errors.value.leaderboard = error.message
      // 更新失败：显示更新失败（白色）
      leaderboardStatus.value = '更新失败'
      leaderboardStatusType.value = 'error'
    } finally {
      loading.value.leaderboard = false
      isRefreshingLeaderboard.value = false
    }
  }

  /**
   * 加载投资组合数据
   */
  const loadPortfolio = async () => {
    if (!currentModelId.value) return
    
    loading.value.portfolio = true
    errors.value.portfolio = null
    try {
      const data = await modelApi.getPortfolio(currentModelId.value)
      if (data.portfolio) {
        portfolio.value = {
          totalValue: data.portfolio.total_value || 0,
          availableCash: data.portfolio.available_cash || 0,
          realizedPnl: data.portfolio.realized_pnl || 0,
          unrealizedPnl: data.portfolio.unrealized_pnl || 0
        }
        // 保存账户价值历史数据
        if (data.account_value_history) {
          accountValueHistory.value = data.account_value_history
          await nextTick()
          updateAccountChart(data.account_value_history, portfolio.value.totalValue, false)
        }
      }
    } catch (error) {
      console.error('[TradingApp] Error loading portfolio:', error)
      errors.value.portfolio = error.message
    } finally {
      loading.value.portfolio = false
    }
  }
  
  /**
   * 加载聚合数据
   */
  const loadAggregatedData = async () => {
    loading.value.portfolio = true
    errors.value.portfolio = null
    try {
      const data = await modelApi.getAggregatedPortfolio()
      if (data.portfolio) {
        portfolio.value = {
          totalValue: data.portfolio.total_value || 0,
          availableCash: data.portfolio.cash || 0,
          realizedPnl: data.portfolio.realized_pnl || 0,
          unrealizedPnl: data.portfolio.unrealized_pnl || 0
        }
        positions.value = data.portfolio.positions || []
      }
      // 保存聚合图表数据
      if (data.chart_data) {
        aggregatedChartData.value = data.chart_data
        await nextTick()
        updateAccountChart(data.chart_data, null, true)
      }
    } catch (error) {
      console.error('[TradingApp] Error loading aggregated data:', error)
      errors.value.portfolio = error.message
    } finally {
      loading.value.portfolio = false
    }
  }
  
  /**
   * 显示聚合视图
   */
  const showAggregatedView = async () => {
    currentModelId.value = null
    isAggregatedView.value = true
    await loadAggregatedData()
  }
  
  /**
   * 更新账户价值图表
   */
  const updateAccountChart = (history, currentValue, isMultiModel = false) => {
    const chartDom = document.getElementById('accountChart')
    if (!chartDom) {
      console.warn('[TradingApp] Chart DOM element not found')
      return
    }
    
    // 初始化或重用图表实例
    if (!accountChart.value) {
      accountChart.value = echarts.init(chartDom)
      
      // 监听窗口大小变化
      window.addEventListener('resize', () => {
        if (accountChart.value) {
          accountChart.value.resize()
        }
      })
    }
    
    if (isMultiModel) {
      // 多模型图表
      if (!history || history.length === 0) {
        accountChart.value.setOption({
          title: {
            text: '暂无模型数据',
            left: 'center',
            top: 'center',
            textStyle: { color: '#86909c', fontSize: 14 }
          },
          xAxis: { show: false },
          yAxis: { show: false },
          series: []
        })
        return
      }
      
      const colors = [
        '#3370ff', '#ff6b35', '#00b96b', '#722ed1', '#fa8c16',
        '#eb2f96', '#13c2c2', '#faad14', '#f5222d', '#52c41a'
      ]
      
      // 收集所有时间点
      const allTimestamps = new Set()
      history.forEach(model => {
        if (model.data) {
          model.data.forEach(point => {
            allTimestamps.add(point.timestamp)
          })
        }
      })
      
      const timeAxis = Array.from(allTimestamps).sort((a, b) => {
        const timeA = new Date(a.replace(' ', 'T') + 'Z').getTime()
        const timeB = new Date(b.replace(' ', 'T') + 'Z').getTime()
        return timeA - timeB
      })
      
      const formattedTimeAxis = timeAxis.map(timestamp => {
        return new Date(timestamp.replace(' ', 'T') + 'Z').toLocaleTimeString('zh-CN', {
          timeZone: 'Asia/Shanghai',
          hour: '2-digit',
          minute: '2-digit'
        })
      })
      
      const series = history.map((model, index) => {
        const color = colors[index % colors.length]
        const dataPoints = timeAxis.map(time => {
          const point = model.data?.find(p => p.timestamp === time)
          return point ? point.value : null
        })
        
        return {
          name: model.model_name || `模型 ${index + 1}`,
          type: 'line',
          data: dataPoints,
          smooth: true,
          symbol: 'circle',
          symbolSize: 4,
          lineStyle: { color: color, width: 2 },
          itemStyle: { color: color },
          connectNulls: true
        }
      })
      
      const option = {
        title: {
          text: '模型表现对比',
          left: 'center',
          top: 10,
          textStyle: { color: '#1d2129', fontSize: 16, fontWeight: 'normal' }
        },
        grid: {
          left: '60',
          right: '20',
          bottom: '80',
          top: '50',
          containLabel: false
        },
        xAxis: {
          type: 'category',
          boundaryGap: false,
          data: formattedTimeAxis,
          axisLine: { lineStyle: { color: '#e5e6eb' } },
          axisLabel: { color: '#86909c', fontSize: 11, rotate: 45 }
        },
        yAxis: {
          type: 'value',
          scale: true,
          axisLine: { lineStyle: { color: '#e5e6eb' } },
          axisLabel: {
            color: '#86909c',
            fontSize: 11,
            formatter: (value) => `$${value.toLocaleString()}`
          },
          splitLine: { lineStyle: { color: '#f2f3f5' } }
        },
        legend: {
          data: history.map(model => model.model_name || '模型'),
          bottom: 10,
          itemGap: 20,
          textStyle: { color: '#1d2129', fontSize: 12 }
        },
        series: series,
        tooltip: {
          trigger: 'axis',
          backgroundColor: 'rgba(255, 255, 255, 0.95)',
          borderColor: '#e5e6eb',
          borderWidth: 1,
          textStyle: { color: '#1d2129' },
          formatter: (params) => {
            let result = `${params[0].axisValue}<br/>`
            params.forEach(param => {
              if (param.value !== null) {
                result += `${param.marker}${param.seriesName}: $${param.value.toFixed(2)}<br/>`
              }
            })
            return result
          }
        }
      }
      accountChart.value.setOption(option)
    } else {
      // 单模型图表
      if (!history || history.length === 0) {
        accountChart.value.setOption({
          title: {
            text: '暂无数据',
            left: 'center',
            top: 'center',
            textStyle: { color: '#86909c', fontSize: 14 }
          },
          xAxis: { show: false },
          yAxis: { show: false },
          series: []
        })
        return
      }
      
      const data = history.reverse().map(h => ({
        time: new Date(h.timestamp.replace(' ', 'T') + 'Z').toLocaleTimeString('zh-CN', {
          timeZone: 'Asia/Shanghai',
          hour: '2-digit',
          minute: '2-digit'
        }),
        value: h.total_value
      }))
      
      if (currentValue !== undefined && currentValue !== null) {
        const now = new Date()
        const currentTime = now.toLocaleTimeString('zh-CN', {
          timeZone: 'Asia/Shanghai',
          hour: '2-digit',
          minute: '2-digit'
        })
        data.push({
          time: currentTime,
          value: currentValue
        })
      }
      
      const option = {
        grid: {
          left: '60',
          right: '20',
          bottom: '40',
          top: '20',
          containLabel: false
        },
        xAxis: {
          type: 'category',
          boundaryGap: false,
          data: data.map(d => d.time),
          axisLine: { lineStyle: { color: '#e5e6eb' } },
          axisLabel: { color: '#86909c', fontSize: 11 }
        },
        yAxis: {
          type: 'value',
          scale: true,
          axisLine: { lineStyle: { color: '#e5e6eb' } },
          axisLabel: {
            color: '#86909c',
            fontSize: 11,
            formatter: (value) => `$${value.toLocaleString()}`
          },
          splitLine: { lineStyle: { color: '#f2f3f5' } }
        },
        series: [{
          type: 'line',
          data: data.map(d => d.value),
          smooth: true,
          symbol: 'none',
          lineStyle: { color: '#3370ff', width: 2 },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(51, 112, 255, 0.2)' },
                { offset: 1, color: 'rgba(51, 112, 255, 0)' }
              ]
            }
          }
        }],
        tooltip: {
          trigger: 'axis',
          backgroundColor: 'rgba(255, 255, 255, 0.95)',
          borderColor: '#e5e6eb',
          borderWidth: 1,
          textStyle: { color: '#1d2129' },
          formatter: (params) => {
            const value = params[0].value
            return `${params[0].axisValue}<br/>账户价值: $${value.toFixed(2)}`
          }
        }
      }
      accountChart.value.setOption(option)
    }
    
    // 延迟调整大小以确保渲染完成
    setTimeout(() => {
      if (accountChart.value) {
        accountChart.value.resize()
      }
    }, 100)
  }

  /**
   * 加载持仓数据
   */
  const loadPositions = async () => {
    if (!currentModelId.value) return
    
    loading.value.positions = true
    errors.value.positions = null
    try {
      const data = await modelApi.getPortfolio(currentModelId.value)
      if (data.portfolio && data.portfolio.positions) {
        // 映射数据格式以匹配前端显示
        positions.value = (data.portfolio.positions || []).map(pos => ({
          id: pos.id || `${pos.future}_${pos.side}`,
          symbol: pos.future || '',
          side: pos.side || '',
          quantity: pos.quantity || 0,
          openPrice: pos.avg_price || 0,
          currentPrice: pos.current_price || 0,
          leverage: pos.leverage || 1,
          pnl: pos.pnl || 0,
          // 保留原始数据
          ...pos
        }))
      }
    } catch (error) {
      console.error('[TradingApp] Error loading positions:', error)
      errors.value.positions = error.message
    } finally {
      loading.value.positions = false
    }
  }

  /**
   * 加载交易记录
   */
  const loadTrades = async () => {
    if (!currentModelId.value) return
    
    loading.value.trades = true
    errors.value.trades = null
    try {
      const data = await modelApi.getTrades(currentModelId.value)
      // 后端直接返回数组格式
      const tradesList = Array.isArray(data) ? data : (data.trades || [])
      // 映射数据格式以匹配前端显示
      trades.value = tradesList.map(trade => ({
        id: trade.id || `${trade.timestamp}_${trade.future}`,
        time: trade.timestamp || '',
        symbol: trade.future || '',
        side: trade.signal || '',
        quantity: trade.quantity || 0,
        price: trade.price || 0,
        pnl: trade.pnl || 0,
        fee: trade.fee || 0,
        // 保留原始数据
        ...trade
      }))
    } catch (error) {
      console.error('[TradingApp] Error loading trades:', error)
      errors.value.trades = error.message
    } finally {
      loading.value.trades = false
    }
  }

  /**
   * 加载对话记录
   */
  const loadConversations = async () => {
    if (!currentModelId.value) return
    
    loading.value.conversations = true
    errors.value.conversations = null
    try {
      const data = await modelApi.getConversations(currentModelId.value)
      // 后端直接返回数组格式
      const convList = Array.isArray(data) ? data : (data.conversations || [])
      // 映射数据格式以匹配前端显示
      conversations.value = convList.map(conv => ({
        id: conv.id || `${conv.timestamp}_${Math.random()}`,
        time: conv.timestamp || '',
        role: 'AI',
        content: conv.ai_response || conv.user_prompt || '',
        user_prompt: conv.user_prompt || '',
        ai_response: conv.ai_response || '',
        cot_trace: conv.cot_trace || '',
        // 保留原始数据
        ...conv
      }))
    } catch (error) {
      console.error('[TradingApp] Error loading conversations:', error)
      errors.value.conversations = error.message
    } finally {
      loading.value.conversations = false
    }
  }

  // ============ 业务操作方法 ============
  
  /**
   * 初始化应用
   */
  const initApp = async () => {
    try {
      console.log('[TradingApp] 🚀 开始初始化应用...')
      
      // 先初始化 WebSocket（确保连接建立）
      console.log('[TradingApp] 初始化 WebSocket 连接...')
      initWebSocket()
      
      // 等待一小段时间确保 WebSocket 连接建立
      await new Promise(resolve => setTimeout(resolve, 500))
      
      // 涨跌幅榜已改为轮询方式，不再通过WebSocket请求初始数据
      // WebSocket连接状态检查（用于其他功能，如K线数据推送）
      if (socket.value) {
        console.log('[TradingApp] WebSocket 连接状态:', {
          connected: socket.value.connected,
          disconnected: socket.value.disconnected,
          id: socket.value.id
        })
      }
      
      // 并行加载初始数据
      console.log('[TradingApp] 加载初始数据...')
      await Promise.all([
        loadModels(),
        loadProviders(),
        loadMarketPrices(),
        loadLeaderboard()
      ])
      
      // 启动涨跌榜自动刷新（30秒轮询备用方案）
      startLeaderboardAutoRefresh()
      
      console.log('[TradingApp] ✅ 初始数据加载完成')
      
      // 如果没有选中的模型，默认显示聚合视图
      if (!currentModelId.value && models.value.length > 0) {
        await showAggregatedView()
      } else if (currentModelId.value) {
        await Promise.all([
          loadPortfolio(),
          loadPositions(),
          loadTrades(),
          loadConversations()
        ])
      }
      
      console.log('[TradingApp] ✅ 应用初始化完成')
    } catch (error) {
      console.error('[TradingApp] ❌ 初始化错误:', error)
    }
  }

  /**
   * 切换日志开关
   */
  const toggleLogger = () => {
    loggerEnabled.value = !loggerEnabled.value
    localStorage.setItem('frontendLoggingEnabled', loggerEnabled.value.toString())
  }

  /**
   * 执行交易
   */
  const handleExecute = async () => {
    if (!currentModelId.value) return
    try {
      const result = await modelApi.execute(currentModelId.value)
      console.log('[TradingApp] Execute success:', result)
      // 执行后刷新数据
      await Promise.all([
        loadPortfolio(),
        loadPositions(),
        loadTrades()
      ])
      return result
    } catch (error) {
      console.error('[TradingApp] Error executing:', error)
      throw error
    }
  }

  /**
   * 暂停/恢复自动交易
   */
  const handlePauseAuto = async () => {
    if (!currentModelId.value) return
    try {
      // 获取当前状态并切换
      const currentModel = models.value.find(m => m.id === currentModelId.value)
      const enabled = !currentModel?.auto_trading_enabled
      
      const result = await modelApi.setAutoTrading(currentModelId.value, enabled)
      console.log('[TradingApp] Auto trading', enabled ? 'enabled' : 'disabled', result)
      
      // 刷新模型列表和投资组合
      await Promise.all([
        loadModels(),
        loadPortfolio()
      ])
      return result
    } catch (error) {
      console.error('[TradingApp] Error toggling auto trading:', error)
      throw error
    }
  }

  /**
   * 刷新涨跌幅榜
   */
  const refreshLeaderboard = async () => {
    // 添加刷新中状态
    const statusEl = document.querySelector('.status-indicator')
    if (statusEl) {
      statusEl.classList.add('updating')
    }
    await loadLeaderboard(true) // 强制刷新
  }
  
  /**
   * 刷新所有数据
   */
  const handleRefresh = async () => {
    isRefreshingAll.value = true
    try {
      await Promise.all([
        loadModels(),
        loadMarketPrices(),
        loadLeaderboard(true) // 强制刷新涨跌幅榜
      ])
      
      if (currentModelId.value) {
        await Promise.all([
          loadPortfolio(),
          loadPositions(),
          loadTrades(),
          loadConversations()
        ])
      } else if (isAggregatedView.value) {
        await loadAggregatedData()
      }
    } finally {
      isRefreshingAll.value = false
    }
  }

  /**
   * 选择模型
   */
  const selectModel = async (modelId) => {
    currentModelId.value = modelId
    isAggregatedView.value = false
    // 加载模型相关数据
    await Promise.all([
      loadPortfolio(),
      loadPositions(),
      loadTrades(),
      loadConversations()
    ])
  }
  
  /**
   * 加载提供方列表（用于显示提供方名称）
   */
  const loadProviders = async () => {
    try {
      const { providerApi } = await import('../services/api.js')
      providers.value = await providerApi.getAll()
    } catch (error) {
      console.error('[TradingApp] Error loading providers:', error)
    }
  }
  
  /**
   * 删除模型
   */
  const deleteModel = async (modelId) => {
    if (!confirm('确定要删除这个模型吗？')) return
    
    try {
      await modelApi.delete(modelId)
      alert('模型删除成功')
      
      // 如果删除的是当前选中的模型，切换到聚合视图
      if (currentModelId.value === modelId) {
        await showAggregatedView()
      } else {
        await loadModels()
      }
    } catch (error) {
      console.error('[TradingApp] Error deleting model:', error)
      alert('删除模型失败')
    }
  }
  
  /**
   * 打开杠杆设置模态框
   */
  const openLeverageModal = (modelId, modelName) => {
    pendingLeverageModelId.value = modelId
    leverageModelName.value = modelName || `模型 #${modelId}`
    showLeverageModal.value = true
  }
  
  /**
   * 保存杠杆设置
   */
  const saveModelLeverage = async (leverage) => {
    if (!pendingLeverageModelId.value) return
    
    const leverageValue = leverage !== undefined ? leverage : parseInt(document.getElementById('leverageInput')?.value || '10', 10)
    if (isNaN(leverageValue) || leverageValue < 0 || leverageValue > 125) {
      alert('请输入有效的杠杆（0-125，0 表示由 AI 自行决定）')
      return
    }
    
    try {
      await modelApi.setLeverage(pendingLeverageModelId.value, leverageValue)
      modelLeverageMap.value[pendingLeverageModelId.value] = leverageValue
      showLeverageModal.value = false
      const savedModelId = pendingLeverageModelId.value
      pendingLeverageModelId.value = null
      await loadModels()
      if (currentModelId.value === savedModelId) {
        await loadPortfolio()
      }
      alert('杠杆设置已保存')
    } catch (error) {
      console.error('[TradingApp] Error saving leverage:', error)
      alert('更新杠杆失败')
    }
  }
  
  /**
   * 切换 ClickHouse 涨幅榜同步
   */
  const toggleClickhouseLeaderboardSync = async () => {
    const action = clickhouseLeaderboardSyncRunning.value ? 'stop' : 'start'
    
    try {
      const { apiPost } = await import('../utils/api.js')
      const data = await apiPost('/api/clickhouse/leaderboard/control', { action })
      clickhouseLeaderboardSyncRunning.value = data.running || false
    } catch (error) {
      console.error('[TradingApp] Error toggling ClickHouse sync:', error)
      alert('操作失败')
    }
  }
  
  /**
   * 更新 ClickHouse 涨幅榜同步状态
   */
  const updateClickhouseLeaderboardSyncStatus = async () => {
    try {
      const { apiGet } = await import('../utils/api.js')
      const data = await apiGet('/api/clickhouse/leaderboard/status')
      clickhouseLeaderboardSyncRunning.value = data.running || false
    } catch (error) {
      console.error('[TradingApp] Error getting ClickHouse status:', error)
    }
  }

  /**
   * 获取模型显示名称
   */
  const getModelDisplayName = (modelId) => {
    const model = models.value.find(m => m.id === modelId)
    return model ? model.name : `模型 #${modelId}`
  }

  // ============ 工具方法 ============
  
  /**
   * 格式化价格
   */
  const formatPrice = (price) => {
    if (price === null || price === undefined) return '0.00'
    return parseFloat(price).toFixed(2)
  }

  /**
   * 格式化涨跌榜价格（保留6位小数）
   */
  const formatLeaderboardPrice = (price) => {
    if (price === null || price === undefined) return '0.000000'
    return parseFloat(price).toFixed(6)
  }

  /**
   * 格式化货币
   */
  const formatCurrency = (value) => {
    if (value === null || value === undefined) return '0.00'
    return parseFloat(value).toFixed(2)
  }
  
  /**
   * 格式化盈亏（带符号）
   */
  const formatPnl = (value, isPnl = false) => {
    if (value === null || value === undefined) return '$0.00'
    const num = parseFloat(value)
    if (isNaN(num)) return '$0.00'
    const sign = isPnl && num >= 0 ? '+' : ''
    return `${sign}$${num.toFixed(2)}`
  }
  
  /**
   * 获取盈亏样式类
   */
  const getPnlClass = (value, isPnl = false) => {
    if (!isPnl) return ''
    const num = parseFloat(value)
    if (isNaN(num)) return ''
    return num >= 0 ? 'positive' : 'negative'
  }
  
  /**
   * 格式化成交量（中文单位：亿、万）
   */
  const formatVolumeChinese = (value) => {
    if (!value && value !== 0) return '--'
    const num = parseFloat(value)
    if (isNaN(num)) return '--'
    
    // 大于等于1亿
    if (num >= 100000000) {
      return `${(num / 100000000).toFixed(2)}亿`
    }
    
    // 大于等于1万
    if (num >= 10000) {
      return `${(num / 10000).toFixed(2)}万`
    }
    
    // 小于1万
    return num.toFixed(2)
  }

  /**
   * 格式化时间
   */
  const formatTime = (timestamp) => {
    if (!timestamp) return ''
    // 处理不同的时间戳格式
    let date
    if (typeof timestamp === 'string') {
      // 处理 "2024-01-01 12:00:00" 格式
      date = new Date(timestamp.replace(' ', 'T') + 'Z')
    } else {
      date = new Date(timestamp)
    }
    return date.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })
  }
  
  /**
   * 获取模型提供方名称
   */
  const getProviderName = (providerId) => {
    const provider = providers.value.find(p => p.id === providerId)
    return provider ? provider.name : '未知'
  }
  
  /**
   * 获取模型杠杆显示文本
   */
  const getLeverageText = (modelId) => {
    const leverage = modelLeverageMap.value[modelId] ?? models.value.find(m => m.id === modelId)?.leverage ?? 10
    return leverage === 0 ? 'AI' : `${leverage}x`
  }

  // ============ 生命周期钩子 ============
  
  // 组件卸载时清理资源
  onUnmounted(() => {
    // 停止涨跌榜自动刷新
    stopLeaderboardAutoRefresh()
    
    // 清理 WebSocket 连接
    if (socket.value) {
      console.log('[WebSocket] 组件卸载，断开 WebSocket 连接')
      socket.value.disconnect()
    }
    if (websocketMonitorInterval) {
      clearInterval(websocketMonitorInterval)
      console.log('[WebSocket Monitor] 停止监控定时器')
    }
  })

  // ============ 返回 API ============
  
  return {
    // 状态
    currentModelId,
    currentModel,
    models,
    isAggregatedView,
    modelLeverageMap,
    providers,
    marketPrices,
    leaderboardGainers,
    leaderboardLosers,
    leaderboardStatus,
    leaderboardStatusType,
    isRefreshingLeaderboard,
    isRefreshingAll,
    portfolio,
    accountValueHistory,
    aggregatedChartData,
    positions,
    trades,
    conversations,
    loggerEnabled,
    showSettingsModal,
    showStrategyModal,
    showFutureConfigModal,
    showApiProviderModal,
    showAddModelModal,
    showLeverageModal,
    pendingLeverageModelId,
    leverageModelName,
    clickhouseLeaderboardSyncRunning,
    loading,
    isLoading,
    errors,
    
    // 方法
    initApp,
    handleRefresh,
    toggleLogger,
    handleExecute,
    handlePauseAuto,
    refreshLeaderboard,
    selectModel,
    showAggregatedView,
    deleteModel,
    openLeverageModal,
    saveModelLeverage,
    toggleClickhouseLeaderboardSync,
    updateClickhouseLeaderboardSyncStatus,
    getModelDisplayName,
    getProviderName,
    getLeverageText,
    formatPrice,
    formatLeaderboardPrice,
    formatCurrency,
    formatPnl,
    getPnlClass,
    formatVolumeChinese,
    formatTime,
    
    // 数据加载方法（供外部调用）
    loadModels,
    loadProviders,
    loadMarketPrices,
    loadLeaderboard,
    loadPortfolio,
    loadAggregatedData,
    loadPositions,
    loadTrades,
    loadConversations,
    
    // 图表更新方法
    updateAccountChart
  }
}
