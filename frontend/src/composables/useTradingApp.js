/**
 * Trading App Composable
 * 提供交易应用的主要业务逻辑和状态管理
 */

import { ref, computed } from 'vue'
import { createSocketConnection } from '../utils/websocket.js'
import { modelApi, marketApi } from '../services/api.js'

export function useTradingApp() {
  // ============ 状态管理 ============
  
  // 模型相关状态
  const currentModelId = ref(null)
  const models = ref([])
  
  // 市场数据状态
  const marketPrices = ref([])
  const leaderboardGainers = ref([])
  const leaderboardLosers = ref([])
  const leaderboardStatus = ref('等待数据...')
  
  // 投资组合状态
  const portfolio = ref({
    totalValue: 0,
    availableCash: 0,
    realizedPnl: 0,
    unrealizedPnl: 0
  })
  const positions = ref([])
  const trades = ref([])
  const conversations = ref([])
  
  // UI 状态
  const loggerEnabled = ref(localStorage.getItem('frontendLoggingEnabled') !== 'false')
  const showSettingsModal = ref(false)
  const showStrategyModal = ref(false)
  const showFutureConfigModal = ref(false)
  const showApiProviderModal = ref(false)
  const showAddModelModal = ref(false)
  
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
      socket.value = createSocketConnection()

      socket.value.on('connect', () => {
        console.log('[WebSocket] 已连接到服务器')
      })

      socket.value.on('leaderboard:update', (data) => {
        if (data.gainers) leaderboardGainers.value = data.gainers
        if (data.losers) leaderboardLosers.value = data.losers
        leaderboardStatus.value = `最后更新: ${new Date().toLocaleTimeString()}`
      })

      socket.value.on('disconnect', () => {
        console.log('[WebSocket] 已断开连接')
      })

      socket.value.on('error', (error) => {
        console.error('[WebSocket] 连接错误:', error)
      })
    } catch (error) {
      console.error('[WebSocket] 初始化失败:', error)
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
      // 后端返回的是对象，格式：{ symbol: { price, change, ... }, ... }
      // 转换为数组格式
      marketPrices.value = Object.entries(data).map(([symbol, info]) => ({
        symbol,
        price: info.price || 0,
        change: info.change_24h || 0,
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
  const loadLeaderboard = async () => {
    loading.value.leaderboard = true
    errors.value.leaderboard = null
    try {
      const data = await marketApi.getLeaderboard(10)
      // 后端返回格式：{ success: true, gainers: [], losers: [] }
      if (data.success) {
        leaderboardGainers.value = data.gainers || []
        leaderboardLosers.value = data.losers || []
        leaderboardStatus.value = `最后更新: ${new Date().toLocaleTimeString()}`
      }
    } catch (error) {
      console.error('[TradingApp] Error loading leaderboard:', error)
      errors.value.leaderboard = error.message
    } finally {
      loading.value.leaderboard = false
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
      }
    } catch (error) {
      console.error('[TradingApp] Error loading portfolio:', error)
      errors.value.portfolio = error.message
    } finally {
      loading.value.portfolio = false
    }
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
        positions.value = data.portfolio.positions || []
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
      trades.value = Array.isArray(data) ? data : (data.trades || [])
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
      conversations.value = Array.isArray(data) ? data : (data.conversations || [])
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
        loadMarketPrices(),
        loadLeaderboard()
      ])
      
      // 如果有选中的模型，加载模型相关数据
      if (currentModelId.value) {
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
   * 刷新所有数据
   */
  const handleRefresh = async () => {
    await Promise.all([
      loadModels(),
      loadMarketPrices(),
      loadLeaderboard()
    ])
    
    if (currentModelId.value) {
      await Promise.all([
        loadPortfolio(),
        loadPositions(),
        loadTrades(),
        loadConversations()
      ])
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
  const refreshLeaderboard = () => {
    loadLeaderboard()
  }

  /**
   * 选择模型
   */
  const selectModel = async (modelId) => {
    currentModelId.value = modelId
    // 加载模型相关数据
    await Promise.all([
      loadPortfolio(),
      loadPositions(),
      loadTrades(),
      loadConversations()
    ])
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
   * 格式化时间
   */
  const formatTime = (timestamp) => {
    if (!timestamp) return ''
    return new Date(timestamp).toLocaleString('zh-CN')
  }

  // ============ 返回 API ============
  
  return {
    // 状态
    currentModelId,
    currentModel,
    models,
    marketPrices,
    leaderboardGainers,
    leaderboardLosers,
    leaderboardStatus,
    portfolio,
    positions,
    trades,
    conversations,
    loggerEnabled,
    showSettingsModal,
    showStrategyModal,
    showFutureConfigModal,
    showApiProviderModal,
    showAddModelModal,
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
    getModelDisplayName,
    formatPrice,
    formatCurrency,
    formatTime,
    
    // 数据加载方法（供外部调用）
    loadModels,
    loadMarketPrices,
    loadLeaderboard,
    loadPortfolio,
    loadPositions,
    loadTrades,
    loadConversations
  }
}
