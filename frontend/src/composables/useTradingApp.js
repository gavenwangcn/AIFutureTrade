import { ref } from 'vue'
// Socket.IO 客户端（通过 npm 安装）
import { io } from 'socket.io-client'

export function useTradingApp() {
  // 状态
  const currentModelId = ref(null)
  const models = ref([])
  const marketPrices = ref([])
  const leaderboardGainers = ref([])
  const leaderboardLosers = ref([])
  const leaderboardStatus = ref('等待数据...')
  const portfolio = ref({
    totalValue: 0,
    availableCash: 0,
    realizedPnl: 0,
    unrealizedPnl: 0
  })
  const positions = ref([])
  const trades = ref([])
  const conversations = ref([])
  const loggerEnabled = ref(true)
  
  // 模态框状态
  const showSettingsModal = ref(false)
  const showStrategyModal = ref(false)
  const showFutureConfigModal = ref(false)
  const showApiProviderModal = ref(false)
  const showAddModelModal = ref(false)
  
  // WebSocket连接
  const socket = ref(null)

  // 初始化应用
  const initApp = async () => {
    try {
      // 初始化WebSocket
      initWebSocket()
      
      // 加载初始数据
      await loadModels()
      await loadMarketPrices()
      await loadLeaderboard()
      await loadPortfolio()
      await loadPositions()
      await loadTrades()
      await loadConversations()
    } catch (error) {
      console.error('[TradingApp] Initialization error:', error)
    }
  }

  // 初始化WebSocket
  const initWebSocket = () => {
    try {
      // 获取后端 URL
      // 开发环境：使用相对路径（通过 Vite 代理）
      // 生产环境：使用环境变量或默认值
      const isDev = import.meta.env.DEV
      const backendUrl = isDev 
        ? undefined  // 使用相对路径，通过 Vite 代理
        : (import.meta.env.VITE_BACKEND_URL || 'http://localhost:5002')
      
      socket.value = io(backendUrl, {
        path: '/socket.io',
        transports: ['websocket', 'polling'],
        reconnection: true,
        reconnectionDelay: 1000,
        reconnectionAttempts: 5,
        // 跨域配置
        withCredentials: false,
        autoConnect: true
      })
      
      console.log('[WebSocket] Connecting to:', backendUrl || 'current origin (via proxy)')

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
    } catch (error) {
      console.error('[WebSocket] 初始化失败', error)
    }
  }

  // 加载模型列表
  const loadModels = async () => {
    try {
      const response = await fetch('/api/models')
      const data = await response.json()
      if (data.success) {
        models.value = data.models || []
      }
    } catch (error) {
      console.error('[TradingApp] Error loading models:', error)
    }
  }

  // 加载市场行情
  const loadMarketPrices = async () => {
    try {
      const response = await fetch('/api/market/prices')
      const data = await response.json()
      if (data.success) {
        marketPrices.value = data.prices || []
      }
    } catch (error) {
      console.error('[TradingApp] Error loading market prices:', error)
    }
  }

  // 加载涨跌幅榜
  const loadLeaderboard = async () => {
    try {
      const response = await fetch('/api/market/leaderboard?limit=10')
      const data = await response.json()
      if (data.success) {
        leaderboardGainers.value = data.gainers || []
        leaderboardLosers.value = data.losers || []
        leaderboardStatus.value = `最后更新: ${new Date().toLocaleTimeString()}`
      }
    } catch (error) {
      console.error('[TradingApp] Error loading leaderboard:', error)
    }
  }

  // 加载投资组合
  const loadPortfolio = async () => {
    try {
      if (!currentModelId.value) return
      const response = await fetch(`/api/portfolio/${currentModelId.value}`)
      const data = await response.json()
      if (data.success) {
        portfolio.value = data.portfolio || portfolio.value
      }
    } catch (error) {
      console.error('[TradingApp] Error loading portfolio:', error)
    }
  }

  // 加载持仓
  const loadPositions = async () => {
    try {
      if (!currentModelId.value) return
      const response = await fetch(`/api/positions/${currentModelId.value}`)
      const data = await response.json()
      if (data.success) {
        positions.value = data.positions || []
      }
    } catch (error) {
      console.error('[TradingApp] Error loading positions:', error)
    }
  }

  // 加载交易记录
  const loadTrades = async () => {
    try {
      if (!currentModelId.value) return
      const response = await fetch(`/api/trades/${currentModelId.value}`)
      const data = await response.json()
      if (data.success) {
        trades.value = data.trades || []
      }
    } catch (error) {
      console.error('[TradingApp] Error loading trades:', error)
    }
  }

  // 加载对话记录
  const loadConversations = async () => {
    try {
      if (!currentModelId.value) return
      const response = await fetch(`/api/conversations/${currentModelId.value}`)
      const data = await response.json()
      if (data.success) {
        conversations.value = data.conversations || []
      }
    } catch (error) {
      console.error('[TradingApp] Error loading conversations:', error)
    }
  }

  // 刷新
  const handleRefresh = () => {
    loadModels()
    loadMarketPrices()
    loadLeaderboard()
    if (currentModelId.value) {
      loadPortfolio()
      loadPositions()
      loadTrades()
      loadConversations()
    }
  }

  // 切换日志
  const toggleLogger = () => {
    loggerEnabled.value = !loggerEnabled.value
    localStorage.setItem('frontendLoggingEnabled', loggerEnabled.value.toString())
  }

  // 执行交易
  const handleExecute = async () => {
    if (!currentModelId.value) return
    try {
      const response = await fetch(`/api/models/${currentModelId.value}/execute`, { method: 'POST' })
      const data = await response.json()
      if (data.success) {
        console.log('[TradingApp] Execute success')
      }
    } catch (error) {
      console.error('[TradingApp] Error executing:', error)
    }
  }

  // 暂停自动交易
  const handlePauseAuto = async () => {
    if (!currentModelId.value) return
    try {
      const response = await fetch(`/api/models/${currentModelId.value}/pause`, { method: 'POST' })
      const data = await response.json()
      if (data.success) {
        console.log('[TradingApp] Pause success')
      }
    } catch (error) {
      console.error('[TradingApp] Error pausing:', error)
    }
  }

  // 刷新涨跌幅榜
  const refreshLeaderboard = () => {
    loadLeaderboard()
  }

  // 选择模型
  const selectModel = (modelId) => {
    currentModelId.value = modelId
    loadPortfolio()
    loadPositions()
    loadTrades()
    loadConversations()
  }

  // 获取模型显示名称
  const getModelDisplayName = (modelId) => {
    const model = models.value.find(m => m.id === modelId)
    return model ? model.name : `模型 #${modelId}`
  }

  // 格式化价格
  const formatPrice = (price) => {
    if (!price) return '0.00'
    return parseFloat(price).toFixed(2)
  }

  // 格式化货币
  const formatCurrency = (value) => {
    if (!value) return '0.00'
    return parseFloat(value).toFixed(2)
  }

  // 格式化时间
  const formatTime = (timestamp) => {
    if (!timestamp) return ''
    return new Date(timestamp).toLocaleString('zh-CN')
  }

  return {
    // 状态
    currentModelId,
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
    formatTime
  }
}

