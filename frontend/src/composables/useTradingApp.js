/**
 * Trading App Composable
 * 提供交易应用的主要业务逻辑和状态管理
 */

import { ref, computed, nextTick, onUnmounted } from 'vue'
import { createSocketConnection } from '../utils/websocket.js'
import { modelApi, marketApi, settingsApi } from '../services/api.js'
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
  // 市场行情价格刷新状态
  const isRefreshingMarketPrices = ref(false)
  // 涨幅榜状态
  const gainersStatus = ref('等待数据...')
  const gainersStatusType = ref('default') // 'updating' | 'success' | 'error' | 'default'
  const isRefreshingGainers = ref(false)
  // 跌幅榜状态
  const losersStatus = ref('等待数据...')
  const losersStatusType = ref('default') // 'updating' | 'success' | 'error' | 'default'
  const isRefreshingLosers = ref(false)
  // 兼容旧代码的状态（已废弃）
  const leaderboardStatus = ref('等待数据...')
  const leaderboardStatusType = ref('default')
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
  const allTrades = ref([])  // 存储所有从后端获取的交易记录
  const tradesDisplayCount = ref(5)  // 前端显示的交易记录数量（从配置读取，默认5条）
  const conversations = ref([])
  const modelPortfolioSymbols = ref([]) // 模型持仓合约列表
const lastPortfolioSymbolsRefreshTime = ref(null) // 持仓合约列表最后刷新时间
  
  // 系统设置状态
  const settings = ref({
    show_system_prompt: false  // 默认不显示系统提示词
  })
  
  // MySQL 涨幅榜同步状态
  const mysqlLeaderboardSyncRunning = ref(true)
  
  // UI 状态
  const loggerEnabled = ref(localStorage.getItem('frontendLoggingEnabled') !== 'false')
  const showSettingsModal = ref(false)
  const showStrategyModal = ref(false)
  const showFutureConfigModal = ref(false)
  const showApiProviderModal = ref(false)
  const showAccountModal = ref(false)
  const showAddModelModal = ref(false)
  const showLeverageModal = ref(false)
  const pendingLeverageModelId = ref(null)
  const leverageModelName = ref('')
  const showMaxPositionsModal = ref(false)
  const pendingMaxPositionsModelId = ref(null)
  const maxPositionsModelName = ref('')
  const tempMaxPositions = ref(3)
  const showModelSettingsModal = ref(false)
  const pendingModelSettingsId = ref(null)
  const modelSettingsName = ref('')
  const tempModelSettings = ref({
    leverage: 10,
    max_positions: 3
  })
  const loadingModelSettings = ref(false)
  const savingModelSettings = ref(false)
  const showDeleteModelConfirmModal = ref(false)
  const pendingDeleteModelId = ref(null)
  const pendingDeleteModelName = ref('')
  const deletingModel = ref(false)
  
  // 加载状态
  const loading = ref({
    models: false,
    marketPrices: false,
    leaderboard: false,
    gainers: false,
    losers: false,
    portfolio: false,
    positions: false,
    trades: false,
    conversations: false,
    portfolioSymbols: false
  })
  
  // 错误状态
  const errors = ref({})
  
  // WebSocket连接
  const socket = ref(null)
  let websocketMonitorInterval = null // WebSocket 监控定时器
let marketPricesRefreshInterval = null // 市场行情价格自动刷新定时器（轮询方式，默认10秒）
let gainersRefreshInterval = null // 涨幅榜自动刷新定时器（轮询方式，默认5秒）
let losersRefreshInterval = null // 跌幅榜自动刷新定时器（轮询方式，默认5秒）
let portfolioSymbolsRefreshInterval = null // 模型持仓合约列表自动刷新定时器（轮询方式，默认10秒）
  let leaderboardRefreshInterval = null // 涨跌榜自动刷新定时器（已废弃，保留以兼容旧代码）
  
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
      //   const statusEl = document.querySelector('.status-indicator')
      //   if (statusEl) {
      //     statusEl.classList.add('error')
      //     setTimeout(() => {
      //       statusEl.classList.remove('error')
      //     }, 3000)
      //   }
      // })

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
   * 启动市场行情价格自动刷新（轮询方式）
   * 使用配置的刷新时间（FUTURES_MARKET_PRICES_REFRESH，默认10秒）
   */
  const startMarketPricesAutoRefresh = () => {
    // 清除已有定时器
    if (marketPricesRefreshInterval) {
      clearInterval(marketPricesRefreshInterval)
      marketPricesRefreshInterval = null
    }

    // 立即获取一次数据
    loadMarketPrices()

    // 使用配置的刷新时间（默认10秒，与后端FUTURES_MARKET_PRICES_REFRESH配置一致）
    // 注意：前端暂时硬编码为10秒，后续可通过API获取配置
    const refreshInterval = 10000 // 10秒
    
    marketPricesRefreshInterval = setInterval(() => {
      console.log(`[TradingApp] 轮询刷新市场行情价格数据（${refreshInterval/1000}秒间隔）`)
      loadMarketPrices()
    }, refreshInterval)

    console.log(`[TradingApp] ✅ 市场行情价格自动刷新已启动（轮询方式，${refreshInterval/1000}秒间隔）`)
  }

  /**
   * 停止市场行情价格自动刷新
   */
  const stopMarketPricesAutoRefresh = () => {
    if (marketPricesRefreshInterval) {
      clearInterval(marketPricesRefreshInterval)
      marketPricesRefreshInterval = null
      console.log('[TradingApp] 市场行情价格自动刷新已停止')
    }
  }

  /**
   * 启动涨幅榜自动刷新（轮询方式）
   * 使用配置的刷新时间（FUTURES_LEADERBOARD_REFRESH，默认5秒）
   */
  const startGainersAutoRefresh = () => {
    // 清除已有定时器
    if (gainersRefreshInterval) {
      clearInterval(gainersRefreshInterval)
      gainersRefreshInterval = null
    }

    // 立即获取一次数据
    loadGainers()

    // 使用配置的刷新时间（默认5秒，与后端FUTURES_LEADERBOARD_REFRESH配置一致）
    const refreshInterval = 5000 // 5秒
    
    gainersRefreshInterval = setInterval(() => {
      console.log(`[TradingApp] 轮询刷新涨幅榜数据（${refreshInterval/1000}秒间隔）`)
      loadGainers()
    }, refreshInterval)

    console.log(`[TradingApp] ✅ 涨幅榜自动刷新已启动（轮询方式，${refreshInterval/1000}秒间隔）`)
  }

  /**
   * 停止涨幅榜自动刷新
   */
  const stopGainersAutoRefresh = () => {
    if (gainersRefreshInterval) {
      clearInterval(gainersRefreshInterval)
      gainersRefreshInterval = null
      console.log('[TradingApp] 涨幅榜自动刷新已停止')
    }
  }

  /**
   * 启动跌幅榜自动刷新（轮询方式）
   * 使用配置的刷新时间（FUTURES_LEADERBOARD_REFRESH，默认5秒）
   */
  const startLosersAutoRefresh = () => {
    // 清除已有定时器
    if (losersRefreshInterval) {
      clearInterval(losersRefreshInterval)
      losersRefreshInterval = null
    }

    // 立即获取一次数据
    loadLosers()

    // 使用配置的刷新时间（默认5秒，与后端FUTURES_LEADERBOARD_REFRESH配置一致）
    const refreshInterval = 5000 // 5秒
    
    losersRefreshInterval = setInterval(() => {
      console.log(`[TradingApp] 轮询刷新跌幅榜数据（${refreshInterval/1000}秒间隔）`)
      loadLosers()
    }, refreshInterval)

    console.log(`[TradingApp] ✅ 跌幅榜自动刷新已启动（轮询方式，${refreshInterval/1000}秒间隔）`)
  }

  /**
   * 停止跌幅榜自动刷新
   */
  const stopLosersAutoRefresh = () => {
    if (losersRefreshInterval) {
      clearInterval(losersRefreshInterval)
      losersRefreshInterval = null
      console.log('[TradingApp] 跌幅榜自动刷新已停止')
    }
  }

  /**
   * 启动模型持仓合约列表自动刷新（轮询方式）
   * 使用配置的刷新时间（默认10秒）
   */
  const startPortfolioSymbolsAutoRefresh = () => {
    // 清除已有定时器
    if (portfolioSymbolsRefreshInterval) {
      clearInterval(portfolioSymbolsRefreshInterval)
      portfolioSymbolsRefreshInterval = null
    }

    // 立即获取一次数据
    loadModelPortfolioSymbols()

    // 使用配置的刷新时间（默认5秒，可配置）
    const refreshInterval = 5000 // 5秒
    
    portfolioSymbolsRefreshInterval = setInterval(() => {
      console.log(`[TradingApp] 轮询刷新模型持仓合约列表数据（${refreshInterval/1000}秒间隔）`)
      loadModelPortfolioSymbols()
    }, refreshInterval)

    console.log(`[TradingApp] ✅ 模型持仓合约列表自动刷新已启动（轮询方式，${refreshInterval/1000}秒间隔）`)
  }

  /**
   * 停止模型持仓合约列表自动刷新
   */
  const stopPortfolioSymbolsAutoRefresh = () => {
    if (portfolioSymbolsRefreshInterval) {
      clearInterval(portfolioSymbolsRefreshInterval)
      portfolioSymbolsRefreshInterval = null
      console.log('[TradingApp] 模型持仓合约列表自动刷新已停止')
    }
  }

  /**
   * 启动涨跌榜自动刷新（已废弃，保留以兼容旧代码）
   */
  const startLeaderboardAutoRefresh = () => {
    startGainersAutoRefresh()
    startLosersAutoRefresh()
  }

  /**
   * 停止涨跌榜自动刷新（已废弃，保留以兼容旧代码）
   */
  const stopLeaderboardAutoRefresh = () => {
    stopGainersAutoRefresh()
    stopLosersAutoRefresh()
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
    isRefreshingMarketPrices.value = true
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
      isRefreshingMarketPrices.value = false
    }
  }

  /**
   * 加载涨幅榜
   */
  const loadGainers = async () => {
    loading.value.gainers = true
    isRefreshingGainers.value = true
    errors.value.gainers = null
    
    // 更新状态为刷新中
    gainersStatus.value = '正在更新...'
    gainersStatusType.value = 'updating'
    
    try {
      const data = await marketApi.getGainers(10)
      const gainers = data.gainers || []
      
      // 检查是否有数据
      if (gainers.length > 0) {
        // 整体刷新渲染：直接替换整个数组
        leaderboardGainers.value = gainers
        
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
        gainersStatus.value = `最后更新: ${dateStr} ${timeStr}`
        gainersStatusType.value = 'success'
      } else {
        // 没有数据：显示更新失败
        gainersStatus.value = '更新失败'
        gainersStatusType.value = 'error'
      }
    } catch (error) {
      console.error('[TradingApp] Error loading gainers:', error)
      errors.value.gainers = error.message
      gainersStatus.value = '更新失败'
      gainersStatusType.value = 'error'
    } finally {
      loading.value.gainers = false
      isRefreshingGainers.value = false
    }
  }

  /**
   * 加载跌幅榜
   */
  const loadLosers = async () => {
    loading.value.losers = true
    isRefreshingLosers.value = true
    errors.value.losers = null
    
    // 更新状态为刷新中
    losersStatus.value = '正在更新...'
    losersStatusType.value = 'updating'
    
    try {
      const data = await marketApi.getLosers(10)
      const losers = data.losers || []
      
      // 检查是否有数据
      if (losers.length > 0) {
        // 整体刷新渲染：直接替换整个数组
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
        losersStatus.value = `最后更新: ${dateStr} ${timeStr}`
        losersStatusType.value = 'success'
      } else {
        // 没有数据：显示更新失败
        losersStatus.value = '更新失败'
        losersStatusType.value = 'error'
      }
    } catch (error) {
      console.error('[TradingApp] Error loading losers:', error)
      errors.value.losers = error.message
      losersStatus.value = '更新失败'
      losersStatusType.value = 'error'
    } finally {
      loading.value.losers = false
      isRefreshingLosers.value = false
    }
  }

  /**
   * 加载涨跌幅榜（已废弃，保留以兼容旧代码）
   */
  const loadLeaderboard = async (force = false) => {
    await Promise.all([loadGainers(), loadLosers()])
  }

  /**
   * 加载模型持仓合约列表
   */
  const loadModelPortfolioSymbols = async () => {
    if (!currentModelId.value) {
      modelPortfolioSymbols.value = []
      return
    }
    
    loading.value.portfolioSymbols = true
    errors.value.portfolioSymbols = null
    try {
      const response = await modelApi.getPortfolioSymbols(currentModelId.value)
      modelPortfolioSymbols.value = response.data || []
    lastPortfolioSymbolsRefreshTime.value = new Date()
    } catch (error) {
      console.error('[TradingApp] Error loading model portfolio symbols:', error)
      errors.value.portfolioSymbols = error.message
      modelPortfolioSymbols.value = []
    } finally {
      loading.value.portfolioSymbols = false
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
      // 加载模型持仓合约列表
      await loadModelPortfolioSymbols()
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
    // 切换到聚合视图时停止模型持仓合约列表自动刷新
    stopPortfolioSymbolsAutoRefresh()
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
      
      // 处理时间轴：account_values表存储的是UTC时间，需要转换为本地时间
      const timeAxis = Array.from(allTimestamps).sort((a, b) => {
        // account_values表存储的是UTC时间，添加Z表示UTC
        const timeA = new Date(a.replace(' ', 'T') + 'Z').getTime()
        const timeB = new Date(b.replace(' ', 'T') + 'Z').getTime()
        return timeA - timeB
      })
      
      const formattedTimeAxis = timeAxis.map(timestamp => {
        // account_values表存储的是UTC时间，转换为本地时间（北京时间）
        const utcDate = new Date(timestamp.replace(' ', 'T') + 'Z')
        return utcDate.toLocaleTimeString('zh-CN', {
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
      
      // account_values表存储的是UTC时间，需要转换为本地时间（北京时间）
      const data = history.reverse().map(h => {
        const utcDate = new Date(h.timestamp.replace(' ', 'T') + 'Z')
        return {
          time: utcDate.toLocaleTimeString('zh-CN', {
            timeZone: 'Asia/Shanghai',
            hour: '2-digit',
            minute: '2-digit'
          }),
          value: h.balance || h.total_value || 0  // 使用新字段名balance，兼容旧字段名total_value
        }
      })
      
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
          id: pos.id || `${pos.symbol}_${pos.position_side}`,
          symbol: pos.symbol || '',
          side: pos.position_side || '',
          quantity: Math.abs(pos.position_amt || 0),
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
   * 后端查询10条，前端只显示前5条（可配置）
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
      // 注意：trades表仍使用future和quantity字段，这里需要兼容
      allTrades.value = tradesList.map(trade => ({
        id: trade.id || `${trade.timestamp}_${trade.future || trade.symbol || ''}`,
        time: trade.timestamp || '',
        symbol: trade.future || trade.symbol || '',  // trades表使用future字段
        signal: trade.signal || '',  // 使用signal字段
        side: trade.signal || '',  // 兼容旧代码，保留side字段
        quantity: trade.quantity || 0,  // trades表使用quantity字段
        price: trade.price || 0,
        current_price: trade.current_price || 0,  // 实时价格（如果有）
        pnl: trade.pnl || 0,  // 盈亏（已根据实时价格计算）
        fee: trade.fee || 0,
        // 保留原始数据
        ...trade
      }))
      
      // 只显示前N条（从配置读取，默认5条）
      trades.value = allTrades.value.slice(0, tradesDisplayCount.value)
    } catch (error) {
      console.error('[TradingApp] Error loading trades:', error)
      errors.value.trades = error.message
      trades.value = []
      allTrades.value = []
    } finally {
      loading.value.trades = false
    }
  }

  /**
   * 加载系统设置
   */
  const loadSettings = async () => {
    try {
      const data = await settingsApi.get()
      settings.value = {
        show_system_prompt: Boolean(data.show_system_prompt || false),
        conversation_limit: parseInt(data.conversation_limit || 5)
      }
      // 从配置读取交易记录显示数量
      if (data.trades_display_count !== undefined) {
        tradesDisplayCount.value = parseInt(data.trades_display_count) || 5
      }
      console.log('[TradingApp] Settings loaded:', settings.value, 'tradesDisplayCount:', tradesDisplayCount.value)
    } catch (error) {
      console.error('[TradingApp] Error loading settings:', error)
      // 使用默认值
      settings.value = {
        show_system_prompt: false,
        conversation_limit: 5
      }
      tradesDisplayCount.value = 5
    }
  }

  /**
   * 加载对话记录
   * 只加载当前选中模型（currentModelId）的对话记录
   * 使用settings中的conversation_limit作为查询限制
   */
  const loadConversations = async () => {
    if (!currentModelId.value) {
      // 如果没有选中模型，清空对话列表
      conversations.value = []
      return
    }
    
    loading.value.conversations = true
    errors.value.conversations = null
    
    // 记录当前请求的 model_id，防止异步请求返回时 model_id 已切换
    const requestedModelId = currentModelId.value
    
    try {
      // 从已加载的settings获取conversation_limit，如果没有则使用默认值5
      const conversationLimit = settings.value.conversation_limit || 5
      
      const data = await modelApi.getConversations(requestedModelId, conversationLimit)
      
      // 检查在请求期间 model_id 是否已切换
      if (currentModelId.value !== requestedModelId) {
        console.log(`[TradingApp] Model changed during conversation load (${requestedModelId} -> ${currentModelId.value}), ignoring response`)
        return
      }
      
      // 后端直接返回数组格式，且只包含当前 model_id 的对话记录
      const convList = Array.isArray(data) ? data : (data.conversations || [])
      
      // 额外验证：确保所有对话记录都属于当前 model_id（前端双重保险）
      const filteredConvList = convList.filter(conv => {
        // 如果后端返回的数据中包含 model_id 字段，进行验证
        if (conv.model_id !== undefined) {
          // 注意：后端返回的是 UUID，前端使用的是整数 ID，这里只做基本验证
          return true // 后端已经过滤，这里信任后端
        }
        return true
      })
      
      // 映射数据格式以匹配前端显示
      const mappedConversations = filteredConvList.map(conv => ({
        id: conv.id || `${conv.timestamp || Date.now()}_${Math.random()}`,
        time: conv.timestamp || null,
        timestamp: conv.timestamp || null, // 确保 timestamp 字段存在
        role: 'AI',
        content: conv.ai_response || conv.user_prompt || '',
        user_prompt: conv.user_prompt || '',
        ai_response: conv.ai_response || '',
        cot_trace: conv.cot_trace || '',
        // 保留原始数据
        ...conv
      }))
      
      // 按 timestamp 降序排序，确保最新的对话显示在最前面（双重保险）
      mappedConversations.sort((a, b) => {
        const timeA = a.timestamp || a.time || ''
        const timeB = b.timestamp || b.time || ''
        // 降序排序：最新的在前
        if (timeA > timeB) return -1
        if (timeA < timeB) return 1
        return 0
      })
      
      conversations.value = mappedConversations
      
      console.log(`[TradingApp] Loaded ${conversations.value.length} conversations for model ${requestedModelId}, sorted by timestamp DESC`)
    } catch (error) {
      console.error(`[TradingApp] Error loading conversations for model ${requestedModelId}:`, error)
      errors.value.conversations = error.message
      // 发生错误时清空对话列表
      conversations.value = []
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
      
      // 先加载系统设置
      console.log('[TradingApp] 加载系统设置...')
      await loadSettings()
      
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
      
      // 启动市场行情价格自动刷新（10秒轮询）
      startMarketPricesAutoRefresh()
      
      // 启动涨跌榜自动刷新（5秒轮询）
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
    // 切换模型时，立即清空旧的对话数据，避免显示错误的数据
    conversations.value = []
    
    currentModelId.value = modelId
    isAggregatedView.value = false
    // 加载模型相关数据
    await Promise.all([
      loadPortfolio(),
      loadPositions(),
      loadTrades(),
      loadConversations(), // 加载新模型的对话数据
      loadModelPortfolioSymbols() // 立即加载一次模型持仓合约数据
    ])
    // 选择模型后启动模型持仓合约列表自动刷新
    startPortfolioSymbolsAutoRefresh()
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
  const handleStrategyConfigClick = () => {
    if (!currentModelId.value) {
      alert('请选择对应模型，或初始化模型')
      return
    }
    showStrategyModal.value = true
  }
  
  /**
   * 打开删除模型确认弹框
   */
  const openDeleteModelConfirm = (modelId, modelName) => {
    pendingDeleteModelId.value = modelId
    pendingDeleteModelName.value = modelName || `模型 #${modelId}`
    showDeleteModelConfirmModal.value = true
  }
  
  /**
   * 确认删除模型
   */
  const confirmDeleteModel = async () => {
    if (!pendingDeleteModelId.value) return
    
    deletingModel.value = true
    try {
      await modelApi.delete(pendingDeleteModelId.value)
      
      const deletedModelId = pendingDeleteModelId.value
      pendingDeleteModelId.value = null
      showDeleteModelConfirmModal.value = false
      
      // 如果删除的是当前选中的模型，切换到聚合视图
      if (currentModelId.value === deletedModelId) {
        await showAggregatedView()
      } else {
        await loadModels()
      }
      
      alert('模型删除成功')
    } catch (error) {
      console.error('[TradingApp] Error deleting model:', error)
      alert('删除模型失败: ' + (error.message || '未知错误'))
    } finally {
      deletingModel.value = false
    }
  }
  
  /**
   * 取消删除模型
   */
  const cancelDeleteModel = () => {
    pendingDeleteModelId.value = null
    pendingDeleteModelName.value = ''
    showDeleteModelConfirmModal.value = false
  }
  
  /**
   * 删除模型（保留向后兼容，现在会打开确认弹框）
   */
  const deleteModel = (modelId, modelName) => {
    openDeleteModelConfirm(modelId, modelName)
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
   * 打开最大持仓数量设置模态框
   */
  const openMaxPositionsModal = (modelId, modelName) => {
    const model = models.value.find(m => m.id === modelId)
    pendingMaxPositionsModelId.value = modelId
    maxPositionsModelName.value = modelName || `模型 #${modelId}`
    tempMaxPositions.value = model?.max_positions || 3
    showMaxPositionsModal.value = true
  }
  
  /**
   * 打开模型设置模态框（合并杠杆和最大持仓数量）
   */
  const openModelSettingsModal = async (modelId, modelName) => {
    pendingModelSettingsId.value = modelId
    modelSettingsName.value = modelName || `模型 #${modelId}`
    loadingModelSettings.value = true
    showModelSettingsModal.value = true
    
    try {
      // 从后端获取模型信息
      const model = await modelApi.getById(modelId)
      tempModelSettings.value = {
        leverage: model.leverage || 10,
        max_positions: model.max_positions || 3
      }
    } catch (error) {
      console.error('[TradingApp] Error loading model settings:', error)
      // 如果获取失败，使用本地缓存的数据
      const localModel = models.value.find(m => m.id === modelId)
      if (localModel) {
        tempModelSettings.value = {
          leverage: localModel.leverage || 10,
          max_positions: localModel.max_positions || 3
        }
      }
      alert('加载模型配置失败，使用缓存数据')
    } finally {
      loadingModelSettings.value = false
    }
  }
  
  /**
   * 保存模型设置（杠杆和最大持仓数量）
   */
  const saveModelSettings = async () => {
    if (!pendingModelSettingsId.value) return
    
    const leverageValue = tempModelSettings.value.leverage
    const maxPositionsValue = tempModelSettings.value.max_positions
    
    // 验证杠杆
    if (isNaN(leverageValue) || leverageValue < 0 || leverageValue > 125) {
      alert('请输入有效的杠杆（0-125，0 表示由 AI 自行决定）')
      return
    }
    
    // 验证最大持仓数量
    if (!maxPositionsValue || maxPositionsValue < 1 || !Number.isInteger(maxPositionsValue)) {
      alert('请输入有效的最大持仓数量（必须 >= 1 的整数）')
      return
    }
    
    savingModelSettings.value = true
    try {
      // 同时保存两个配置
      await Promise.all([
        modelApi.setLeverage(pendingModelSettingsId.value, leverageValue),
        modelApi.setMaxPositions(pendingModelSettingsId.value, maxPositionsValue)
      ])
      
      // 更新本地缓存
      modelLeverageMap.value[pendingModelSettingsId.value] = leverageValue
      
      const savedModelId = pendingModelSettingsId.value
      pendingModelSettingsId.value = null
      showModelSettingsModal.value = false
      
      // 刷新模型列表
      await loadModels()
      if (currentModelId.value === savedModelId) {
        await loadPortfolio()
      }
      
      alert('模型设置已保存')
    } catch (error) {
      console.error('[TradingApp] Error saving model settings:', error)
      alert('保存模型设置失败')
    } finally {
      savingModelSettings.value = false
    }
  }
  
  /**
   * 保存最大持仓数量设置
   */
  const saveModelMaxPositions = async () => {
    if (!pendingMaxPositionsModelId.value) return
    
    const maxPositionsValue = tempMaxPositions.value
    if (!maxPositionsValue || maxPositionsValue < 1 || !Number.isInteger(maxPositionsValue)) {
      alert('请输入有效的最大持仓数量（必须 >= 1 的整数）')
      return
    }
    
    try {
      await modelApi.setMaxPositions(pendingMaxPositionsModelId.value, maxPositionsValue)
      showMaxPositionsModal.value = false
      const savedModelId = pendingMaxPositionsModelId.value
      pendingMaxPositionsModelId.value = null
      await loadModels()
      if (currentModelId.value === savedModelId) {
        await loadPortfolio()
      }
      alert('最大持仓数量设置已保存')
    } catch (error) {
      console.error('[TradingApp] Error saving max_positions:', error)
      alert('更新最大持仓数量失败')
    }
  }
  
  /**
   * 切换 MySQL 涨幅榜同步
   */
  const toggleMysqlLeaderboardSync = async () => {
    const action = mysqlLeaderboardSyncRunning.value ? 'stop' : 'start'
    
    try {
      const { apiPost } = await import('../utils/api.js')
      const data = await apiPost('/api/mysql/leaderboard/control', { action })
      mysqlLeaderboardSyncRunning.value = data.running || false
    } catch (error) {
      console.error('[TradingApp] Error toggling MySQL sync:', error)
      alert('操作失败')
    }
  }
  
  /**
   * 更新 MySQL 涨幅榜同步状态
   */
  const updateMysqlLeaderboardSyncStatus = async () => {
    try {
      const { apiGet } = await import('../utils/api.js')
      const data = await apiGet('/api/mysql/leaderboard/status')
      mysqlLeaderboardSyncRunning.value = data.running || false
    } catch (error) {
      console.error('[TradingApp] Error getting MySQL status:', error)
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
   * 格式化交易信号（翻译成中文）
   */
  const formatSignal = (signal) => {
    if (!signal) return '未知'
    const signalMap = {
      'buy_to_enter': '开多',
      'sell_to_enter': '开空',
      'close_position': '平仓',
      'stop_loss': '止损',
      'take_profit': '止盈'
    }
    return signalMap[signal] || signal
  }
  
  /**
   * 获取交易信号的样式类
   */
  const getSignalBadgeClass = (signal) => {
    if (!signal) return 'badge-close'
    const classMap = {
      'buy_to_enter': 'badge-buy',
      'sell_to_enter': 'badge-sell',
      'close_position': 'badge-close',
      'stop_loss': 'badge-stop',
      'take_profit': 'badge-profit'
    }
    return classMap[signal] || 'badge-close'
  }

  /**
   * 格式化时间
   * 注意：数据库存储的是UTC+8时区（北京时间）的naive datetime
   * 前端应该将其当作本地时间（北京时间）处理，不需要再进行时区转换
   */
  const formatTime = (timestamp) => {
    if (!timestamp) return ''
    
    // 处理不同的时间戳格式
    let date
    
    try {
      if (typeof timestamp === 'string') {
        // 处理 MySQL DATETIME 格式 "2024-01-01 12:00:00"
        // 数据库存储的是UTC+8时区的naive datetime，应该当作本地时间处理
        if (timestamp.match(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/)) {
          // MySQL DATETIME 格式，数据库存储的是北京时间（UTC+8），直接解析为本地时间
          // 不添加时区偏移，因为数据库已经存储的是北京时间
          const [datePart, timePart] = timestamp.split(' ')
          const [year, month, day] = datePart.split('-').map(Number)
          const [hour, minute, second] = timePart.split(':').map(Number)
          // 使用本地时间创建Date对象（不进行UTC转换）
          date = new Date(year, month - 1, day, hour, minute, second || 0)
        } else if (timestamp.includes('T')) {
          // ISO 格式，检查是否包含时区信息
          if (timestamp.includes('+') || timestamp.includes('Z') || timestamp.match(/[+-]\d{2}:\d{2}$/)) {
            // 包含时区信息，直接解析
            date = new Date(timestamp)
          } else {
            // 不包含时区信息，当作本地时间处理
            date = new Date(timestamp)
          }
        } else {
          // 尝试直接解析
          date = new Date(timestamp)
        }
      } else if (typeof timestamp === 'number') {
        // 数字时间戳（可能是秒或毫秒）
        date = new Date(timestamp > 1e12 ? timestamp : timestamp * 1000)
      } else {
        date = new Date(timestamp)
      }
      
      // 验证日期是否有效
      if (isNaN(date.getTime())) {
        console.warn('[formatTime] Invalid date:', timestamp)
        return ''
      }
      
      // 直接格式化为本地时间字符串，不进行时区转换
      // 因为数据库存储的就是北京时间，前端显示也应该显示为北京时间
      return date.toLocaleString('zh-CN', { 
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      })
    } catch (error) {
      console.error('[formatTime] Error formatting time:', error, timestamp)
      return ''
    }
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
    // 停止市场行情价格自动刷新
    stopMarketPricesAutoRefresh()
    
    // 停止涨跌榜自动刷新
    stopGainersAutoRefresh()
    stopLosersAutoRefresh()
    
    // 停止模型持仓合约列表自动刷新
    stopPortfolioSymbolsAutoRefresh()
    
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
    // 市场行情价格刷新状态
    isRefreshingMarketPrices,
    // 涨幅榜状态
    gainersStatus,
    gainersStatusType,
    isRefreshingGainers,
    // 跌幅榜状态
    losersStatus,
    losersStatusType,
    isRefreshingLosers,
    // 兼容旧代码的状态（已废弃）
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
    settings,
    modelPortfolioSymbols,
    lastPortfolioSymbolsRefreshTime,
    loggerEnabled,
    showSettingsModal,
    showStrategyModal,
    showFutureConfigModal,
    showApiProviderModal,
    showAccountModal,
    showAddModelModal,
    showLeverageModal,
    pendingLeverageModelId,
    leverageModelName,
    mysqlLeaderboardSyncRunning,
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
    handleStrategyConfigClick,
    openLeverageModal,
    saveModelLeverage,
    showMaxPositionsModal,
    pendingMaxPositionsModelId,
    maxPositionsModelName,
    tempMaxPositions,
    openMaxPositionsModal,
    saveModelMaxPositions,
    showModelSettingsModal,
    pendingModelSettingsId,
    modelSettingsName,
    tempModelSettings,
    loadingModelSettings,
    savingModelSettings,
    openModelSettingsModal,
    saveModelSettings,
    showDeleteModelConfirmModal,
    pendingDeleteModelId,
    pendingDeleteModelName,
    deletingModel,
    openDeleteModelConfirm,
    confirmDeleteModel,
    cancelDeleteModel,
    toggleMysqlLeaderboardSync,
    updateMysqlLeaderboardSyncStatus,
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
    formatSignal,
    getSignalBadgeClass,
    
    // 数据加载方法（供外部调用）
    loadModels,
    loadProviders,
    loadMarketPrices,
    loadGainers,
    loadLosers,
    loadLeaderboard, // 已废弃，保留以兼容旧代码
    loadPortfolio,
    loadAggregatedData,
    loadPositions,
    loadTrades,
    loadConversations,
    loadModelPortfolioSymbols,
    loadSettings,
    
    // 市场行情价格自动刷新方法
    startMarketPricesAutoRefresh,
    stopMarketPricesAutoRefresh,
    // 涨跌榜自动刷新方法
    startGainersAutoRefresh,
    stopGainersAutoRefresh,
    startLosersAutoRefresh,
    stopLosersAutoRefresh,
    startLeaderboardAutoRefresh, // 已废弃，保留以兼容旧代码
    stopLeaderboardAutoRefresh, // 已废弃，保留以兼容旧代码
    
    // 图表更新方法
    updateAccountChart
  }
}
