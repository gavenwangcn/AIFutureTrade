/**
 * Trading App Composable
 * 提供交易应用的主要业务逻辑和状态管理
 */

import { ref, computed, nextTick } from 'vue'
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
      if (socket.value && socket.value.connected) {
        console.log('[WebSocket] 断开现有连接')
        socket.value.disconnect()
      }

      socket.value = createSocketConnection()

      // 连接成功事件
      socket.value.on('connect', () => {
        console.log('[WebSocket] ✅ 已连接到服务器')
        leaderboardStatus.value = '已连接，等待数据...'
        
        // 连接成功后请求初始涨跌幅榜数据
        console.log('[WebSocket] 请求初始涨跌幅榜数据')
        socket.value.emit('leaderboard:request', { limit: 10 })
      })

      // 涨跌幅榜更新事件（后端自动推送）
      socket.value.on('leaderboard:update', async (data) => {
        console.log('[WebSocket] 📊 收到涨跌幅榜自动更新', data)
        
        if (data && (data.gainers || data.losers)) {
          // 更新涨幅榜和跌幅榜数据
          leaderboardGainers.value = Array.isArray(data.gainers) ? data.gainers : []
          leaderboardLosers.value = Array.isArray(data.losers) ? data.losers : []
          
          // 更新状态时间戳
          const updateTime = new Date()
          const timeStr = updateTime.toLocaleTimeString('zh-CN', { 
            hour12: false,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
          })
          leaderboardStatus.value = `最后更新: ${timeStr}`
          
          // 触发更新动画效果
          await nextTick()
          const statusEl = document.querySelector('.status-indicator')
          if (statusEl) {
            // 移除之前的动画类
            statusEl.classList.remove('updating', 'updated')
            // 添加更新动画
            statusEl.classList.add('updated')
            setTimeout(() => {
              statusEl.classList.remove('updated')
            }, 1000)
          }
          
          console.log(`[WebSocket] ✅ 涨跌幅榜已更新: 涨幅榜 ${leaderboardGainers.value.length} 条, 跌幅榜 ${leaderboardLosers.value.length} 条`)
        } else {
          console.warn('[WebSocket] ⚠️ 收到无效的涨跌幅榜数据:', data)
        }
      })

      // 涨跌幅榜错误事件
      socket.value.on('leaderboard:error', (error) => {
        console.error('[WebSocket] ❌ 涨跌幅榜更新错误', error)
        leaderboardStatus.value = '更新失败'
        
        // 更新错误状态指示器
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
      })

      // 重新连接事件
      socket.value.on('reconnect', (attemptNumber) => {
        console.log(`[WebSocket] 🔄 重新连接成功 (尝试 ${attemptNumber} 次)`)
        leaderboardStatus.value = '已重连，等待数据...'
        // 重新连接后请求数据
        socket.value.emit('leaderboard:request', { limit: 10 })
      })

      // 连接错误事件
      socket.value.on('connect_error', (error) => {
        console.error('[WebSocket] ❌ 连接错误:', error)
        leaderboardStatus.value = '连接失败'
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

    } catch (error) {
      console.error('[WebSocket] ❌ 初始化失败:', error)
      leaderboardStatus.value = 'WebSocket 初始化失败'
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
    
    // 更新状态为刷新中
    if (force) {
      leaderboardStatus.value = '正在刷新...'
    }
    
    try {
      const data = await marketApi.getLeaderboard(10, force)
      // 后端返回格式：{ success: true, gainers: [], losers: [] } 或直接返回 { gainers: [], losers: [] }
      if (data.success !== false) {
        leaderboardGainers.value = data.gainers || []
        leaderboardLosers.value = data.losers || []
        const updateTime = new Date().toLocaleTimeString('zh-CN')
        leaderboardStatus.value = `最后更新: ${updateTime}`
        
        // 触发更新动画
        await nextTick()
        const statusEl = document.querySelector('.status-indicator')
        if (statusEl) {
          statusEl.classList.remove('updating')
          statusEl.classList.add('updated')
          setTimeout(() => {
            statusEl.classList.remove('updated')
          }, 1000)
        }
      }
    } catch (error) {
      console.error('[TradingApp] Error loading leaderboard:', error)
      errors.value.leaderboard = error.message
      leaderboardStatus.value = '更新失败'
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
      // 初始化 WebSocket
      initWebSocket()
      
      // 并行加载初始数据
      await Promise.all([
        loadModels(),
        loadProviders(),
        loadMarketPrices(),
        loadLeaderboard()
      ])
      
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
    } catch (error) {
      console.error('[TradingApp] Initialization error:', error)
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
