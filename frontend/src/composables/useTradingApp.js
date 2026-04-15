/**
 * Trading App Composable
 * 提供交易应用的主要业务逻辑和状态管理
 */

import { ref, computed, nextTick, onUnmounted } from 'vue'
import { createSocketConnection } from '../utils/websocket.js'
import { modelApi, marketApi, settingsApi, binanceFuturesOrderApi, algoOrderApi } from '../services/api.js'
import * as echarts from 'echarts'

export function useTradingApp() {
  // ============ 状态管理 ============
  
  // 模型相关状态
  const currentModelId = ref(null)
  const models = ref([])
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
  
  // 模块刷新状态（用于刷新按钮）
  const isRefreshingPortfolioSymbols = ref(false)  // 持仓合约实时行情刷新状态
  const isRefreshingPositions = ref(false)          // 持仓模块刷新状态
  const isRefreshingTrades = ref(false)             // 交易记录模块刷新状态
  const isRefreshingConversations = ref(false)      // AI对话模块刷新状态
  const isRefreshingAlgoOrders = ref(false)        // 挂单模块刷新状态
  
  // 投资组合状态
  const portfolio = ref({
    totalValue: 0,
    availableCash: 0,
    realizedPnl: 0,
    unrealizedPnl: 0,
    dailyReturnRate: null  // 每日收益率（百分比）
  })
  const accountValueHistory = ref([]) // 账户价值历史数据（用于图表）
  // 时间选择相关状态
  const timeRangePreset = ref('5days') // 快速选择：'5days', '10days', '30days', 'custom'
  const customStartTime = ref('') // 自定义开始时间
  const customEndTime = ref('') // 自定义结束时间
  const isLoadingAccountHistory = ref(false) // 账户价值历史加载状态
  const tradeMarkers = ref(new Map()) // 存储交易标记信息，key为trade_id，value为交易详情
  const positions = ref([])
  const trades = ref([])
  const allTrades = ref([])  // 存储所有从后端获取的交易记录
  const tradesDisplayCount = ref(5)  // 前端显示的交易记录数量（从配置读取，默认5条）
  
  // 分页相关状态
  const tradesPage = ref(1)  // 当前页码
  const tradesPageSize = ref(10)  // 每页记录数
  const tradesTotal = ref(0)  // 总记录数
  const tradesTotalPages = ref(0)  // 总页数
  const conversations = ref([])
  const strategyDecisions = ref([]) // 策略决策列表
  const isRefreshingStrategyDecisions = ref(false) // 策略决策模块刷新状态
  // 策略决策分页相关状态
  const strategyDecisionsPage = ref(1)  // 当前页码
  const strategyDecisionsPageSize = ref(10)  // 每页记录数
  const strategyDecisionsTotal = ref(0)  // 总记录数
  const strategyDecisionsTotalPages = ref(0)  // 总页数
  
  // 挂单相关状态
  const algoOrders = ref([])  // 挂单列表
  const algoOrdersPage = ref(1)  // 当前页码
  const algoOrdersPageSize = ref(10)  // 每页记录数
  const algoOrdersTotal = ref(0)  // 总记录数
  const algoOrdersTotalPages = ref(0)  // 总页数
  
  /**
   * 策略决策分页展示（兼容后端未返回 total/totalPages 的情况）
   * - total/totalPages 正常情况下应由后端返回 PageResult 提供
   * - 若缺失，则基于当前页数据给出“下界展示值”，并尽量保证按钮可用性
   */
  const strategyDecisionsDisplayTotal = computed(() => {
    if (Number(strategyDecisionsTotal.value) > 0) return Number(strategyDecisionsTotal.value)
    if (strategyDecisions.value.length > 0) {
      const pageNum = Number(strategyDecisionsPage.value) || 1
      const size = Number(strategyDecisionsPageSize.value) || 10
      const lowerBound = (pageNum - 1) * size + strategyDecisions.value.length
      return Math.max(lowerBound, strategyDecisions.value.length)
    }
    return 0
  })
  
  const strategyDecisionsDisplayTotalPages = computed(() => {
    const totalPages = Number(strategyDecisionsTotalPages.value) || 0
    if (totalPages > 0) return totalPages
    
    const total = Number(strategyDecisionsTotal.value) || 0
    const size = Number(strategyDecisionsPageSize.value) || 10
    if (total > 0) return Math.max(1, Math.ceil(total / size))
    
    return strategyDecisions.value.length > 0 ? 1 : 0
  })
  
  const strategyDecisionsHasPrev = computed(() => (Number(strategyDecisionsPage.value) || 1) > 1)
  
  const strategyDecisionsHasNext = computed(() => {
    const pageNum = Number(strategyDecisionsPage.value) || 1
    const pages = strategyDecisionsDisplayTotalPages.value
    if (pages > 0) return pageNum < pages
    
    // totalPages 未知时：如果本页返回满页数据，允许继续翻页尝试
    const size = Number(strategyDecisionsPageSize.value) || 10
    return strategyDecisions.value.length === size
  })
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
  const showStrategyManagementModal = ref(false)
  const showWeChatGroupManagementModal = ref(false)
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
    provider_id: null,
    model_name: '',
    leverage: 10,
    max_positions: 3,
    auto_close_percent: null,
    base_volume: null,
    daily_return: null,
    losses_num: null,
    forbid_buy_start: null,
    forbid_buy_end: null,
    same_symbol_interval: null,
    buy_batch_size: 1,
    buy_batch_execution_interval: 60,
    buy_batch_execution_group_size: 1,
    sell_batch_size: 1,
    sell_batch_execution_interval: 60,
    sell_batch_execution_group_size: 1
  })
  const availableModelsInSettings = ref([]) // 模型设置中可用的模型列表
  const loadingModelSettings = ref(false)
  const savingModelSettings = ref(false)
  const showDeleteModelConfirmModal = ref(false)
  const pendingDeleteModelId = ref(null)
  const pendingDeleteModelName = ref('')
  const deletingModel = ref(false)
  const showStrategyConfigModal = ref(false)
  const pendingStrategyConfigModelId = ref(null)
  const strategyConfigModelName = ref('')
  const loadingStrategyConfig = ref(false)
  const savingStrategyConfig = ref(false)
  
  // Trade详情弹框
  const showTradeDetailModal = ref(false)
  const selectedTradeDetail = ref(null)
  
  // 加载状态
  const loading = ref({
    algoOrders: false,
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
  const errors = ref({ algoOrders: null })
  
  // WebSocket连接
  const socket = ref(null)
  let websocketMonitorInterval = null // WebSocket 监控定时器
let marketPricesRefreshInterval = null // 市场行情价格自动刷新定时器（轮询方式，默认10秒）
let gainersRefreshInterval = null // 涨幅榜自动刷新定时器（轮询方式，15秒）
let losersRefreshInterval = null // 跌幅榜自动刷新定时器（轮询方式，15秒）
let portfolioSymbolsRefreshInterval = null // 模型持仓合约列表自动刷新定时器（轮询方式，默认10秒）
let portfolioRefreshInterval = null // 投资组合数据自动刷新定时器（轮询方式，默认5秒，包含账户总值、可用现金、已实现盈亏、未实现盈亏、每日收益率）
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
      loadMarketPrices()
    }, refreshInterval)

  }

  /**
   * 停止市场行情价格自动刷新
   */
  const stopMarketPricesAutoRefresh = () => {
    if (marketPricesRefreshInterval) {
      clearInterval(marketPricesRefreshInterval)
      marketPricesRefreshInterval = null
    }
  }

  /**
   * 启动涨幅榜自动刷新（轮询方式）
   * 前端轮询间隔 15 秒
   */
  const startGainersAutoRefresh = () => {
    // 清除已有定时器
    if (gainersRefreshInterval) {
      clearInterval(gainersRefreshInterval)
      gainersRefreshInterval = null
    }

    // 立即获取一次数据
    loadGainers()

    const refreshInterval = 15000 // 15秒

    gainersRefreshInterval = setInterval(() => {
      loadGainers()
    }, refreshInterval)

  }

  /**
   * 停止涨幅榜自动刷新
   */
  const stopGainersAutoRefresh = () => {
    if (gainersRefreshInterval) {
      clearInterval(gainersRefreshInterval)
      gainersRefreshInterval = null
    }
  }

  /**
   * 启动跌幅榜自动刷新（轮询方式）
   * 前端轮询间隔 15 秒
   */
  const startLosersAutoRefresh = () => {
    // 清除已有定时器
    if (losersRefreshInterval) {
      clearInterval(losersRefreshInterval)
      losersRefreshInterval = null
    }

    // 立即获取一次数据
    loadLosers()

    const refreshInterval = 15000 // 15秒

    losersRefreshInterval = setInterval(() => {
      loadLosers()
    }, refreshInterval)

  }

  /**
   * 停止跌幅榜自动刷新
   */
  const stopLosersAutoRefresh = () => {
    if (losersRefreshInterval) {
      clearInterval(losersRefreshInterval)
      losersRefreshInterval = null
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
      loadModelPortfolioSymbols()
    }, refreshInterval)

  }

  /**
   * 停止模型持仓合约列表自动刷新
   */
  const stopPortfolioSymbolsAutoRefresh = () => {
    if (portfolioSymbolsRefreshInterval) {
      clearInterval(portfolioSymbolsRefreshInterval)
      portfolioSymbolsRefreshInterval = null
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

  /**
   * 启动投资组合数据自动刷新（轮询方式）
   * 刷新账户总值、可用现金、已实现盈亏、未实现盈亏、每日收益率等数据
   */
  const startPortfolioAutoRefresh = () => {
    // 清除已有定时器
    if (portfolioRefreshInterval) {
      clearInterval(portfolioRefreshInterval)
      portfolioRefreshInterval = null
    }

    // 立即获取一次数据
    loadPortfolio()

    // 使用配置的刷新时间（默认5秒，与其他模块保持一致）
    const refreshInterval = 5000 // 5秒
    
    portfolioRefreshInterval = setInterval(() => {
      loadPortfolio()
    }, refreshInterval)

  }

  /**
   * 停止投资组合数据自动刷新
   */
  const stopPortfolioAutoRefresh = () => {
    if (portfolioRefreshInterval) {
      clearInterval(portfolioRefreshInterval)
      portfolioRefreshInterval = null
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
      // 调试日志：检查字段是否正确加载
      console.log('[TradingApp] 模型列表已加载，数量:', models.value.length)
      models.value.forEach(model => {
        if (model.id) {
          console.log(`[TradingApp] 模型 ${model.id}: max_positions=${model.max_positions}, maxPositions=${model.maxPositions}, auto_close_percent=${model.auto_close_percent}, autoClosePercent=${model.autoClosePercent}`)
        }
      })
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
      
      if (response.data && Array.isArray(response.data)) {
        
        // 处理数据，确保字段名正确
        modelPortfolioSymbols.value = response.data.map((item, index) => {
          // 确保字段名正确
          const mappedItem = {
            symbol: item.symbol || '',
            price: item.price || 0,
            change: item.change !== undefined ? item.change : (item.changePercent !== undefined ? item.changePercent : 0),
            changePercent: item.changePercent !== undefined ? item.changePercent : (item.change !== undefined ? item.change : 0),
            quoteVolume: item.quoteVolume !== undefined ? item.quoteVolume : (item.volume !== undefined ? item.volume : 0),
            volume: item.volume || 0,
            high: item.high || 0,
            low: item.low || 0,
            ...item  // 保留所有原始字段
          }
          
          return mappedItem
        })
        
      } else {
        console.warn('[TradingApp] 持仓合约实时行情数据格式不正确:', response)
        modelPortfolioSymbols.value = []
      }
      
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
   * 获取时间范围（根据快速选择或自定义时间）
   */
  const getTimeRange = () => {
    if (timeRangePreset.value === 'custom') {
      return {
        startTime: customStartTime.value || null,
        endTime: customEndTime.value || null
      }
    }
    
    // 计算快速选择的时间范围
    const endTime = new Date()
    const startTime = new Date()
    
    if (timeRangePreset.value === '5days') {
      startTime.setDate(endTime.getDate() - 5)
    } else if (timeRangePreset.value === '10days') {
      startTime.setDate(endTime.getDate() - 10)
    } else if (timeRangePreset.value === '30days') {
      startTime.setDate(endTime.getDate() - 30)
    }
    
    // 格式化为ISO字符串（本地时间，不包含时区）
    const formatDateTime = (date) => {
      const year = date.getFullYear()
      const month = String(date.getMonth() + 1).padStart(2, '0')
      const day = String(date.getDate()).padStart(2, '0')
      const hours = String(date.getHours()).padStart(2, '0')
      const minutes = String(date.getMinutes()).padStart(2, '0')
      const seconds = String(date.getSeconds()).padStart(2, '0')
      return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}`
    }
    
    return {
      startTime: formatDateTime(startTime),
      endTime: formatDateTime(endTime)
    }
  }

  /**
   * 加载账户价值历史数据（支持时间范围）
   */
  const loadAccountValueHistory = async () => {
    if (!currentModelId.value) return
    
    // 设置加载状态
    isLoadingAccountHistory.value = true
    
    try {
      const timeRange = getTimeRange()
      console.log('[TradingApp] Loading account value history with time range:', timeRange)
      
      // 先销毁旧图表，确保重新创建
      if (accountChart.value) {
        try {
          accountChart.value.dispose()
          accountChart.value = null
          console.log('[TradingApp] 已销毁旧图表，准备重新创建')
        } catch (e) {
          console.warn('[TradingApp] 销毁旧图表时出错:', e)
        }
      }
      
      const history = await modelApi.getAccountValueHistory(
        currentModelId.value,
        timeRange.startTime,
        timeRange.endTime
      )
      
      console.log('[TradingApp] Loaded account value history:', history.length, 'records')
      
      // 提取有trade_id的记录，用于后续查询交易详情
      const tradeIds = history
        .filter(h => h.trade_id)
        .map(h => h.trade_id)
      
      // 如果有trade_id，尝试加载trades数据以获取交易详情
      if (tradeIds.length > 0) {
        // 如果trades未加载或数据较少，尝试加载更多trades数据
        // 为了获取所有相关交易，我们加载第一页的trades（通常包含最近的交易）
        if (allTrades.value.length === 0) {
          try {
            await loadTrades()  // 加载第一页的trades
          } catch (e) {
            console.warn('[TradingApp] Failed to load trades for trade markers:', e)
          }
        }
        
        // 更新tradeMarkers映射，将trade_id映射到交易详情
        tradeIds.forEach(tradeId => {
          const trade = allTrades.value.find(t => t.id === tradeId)
          if (trade) {
            tradeMarkers.value.set(tradeId, trade)
          }
        })
      }
      
      accountValueHistory.value = history
      await nextTick()
      
      // 重新创建并渲染图表
      updateAccountChart(history, portfolio.value.totalValue, false)
      console.log('[TradingApp] 图表已重新创建并渲染')
    } catch (error) {
      console.error('[TradingApp] Error loading account value history:', error)
      errors.value.portfolio = error.message
    } finally {
      // 无论成功或失败，都要关闭加载状态
      isLoadingAccountHistory.value = false
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
          availableCash: data.portfolio.cash || data.portfolio.available_cash || 0,  // 兼容两种字段名
          realizedPnl: data.portfolio.realized_pnl || 0,
          unrealizedPnl: data.portfolio.unrealized_pnl || 0,
          dailyReturnRate: data.portfolio.daily_return_rate !== undefined ? data.portfolio.daily_return_rate : null
        }
      }
      
      // 注意：账户价值历史数据不再在这里加载
      // 只有在切换日期选项框时（handleTimeRangeChange）或选择模型时（selectModel）才加载
      
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
      try {
        accountChart.value = echarts.init(chartDom)
        
        // 监听窗口大小变化
        window.addEventListener('resize', () => {
          if (accountChart.value) {
            try {
              accountChart.value.resize()
            } catch (error) {
              console.warn('[TradingApp] Error resizing chart:', error)
            }
          }
        })
      } catch (error) {
        console.error('[TradingApp] Error initializing chart:', error)
        return
      }
    }
    
    // 确保图表实例有效
    if (!accountChart.value || typeof accountChart.value.setOption !== 'function') {
      console.warn('[TradingApp] Chart instance is invalid, reinitializing...')
      try {
        accountChart.value = echarts.init(chartDom)
      } catch (error) {
        console.error('[TradingApp] Error reinitializing chart:', error)
        return
      }
    }
    
    if (isMultiModel) {
      // 多模型图表 - 参考官方示例，简化配置
      if (!history || history.length === 0) {
        try {
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
          }, true)
        } catch (error) {
          console.error('[TradingApp] Error setting chart option (multi-model empty):', error)
        }
        return
      }
      
      console.log('[TradingApp] 多模型图表数据:', history.length, '个模型')
      
      const colors = [
        '#3370ff', '#ff6b35', '#00b96b', '#722ed1', '#fa8c16',
        '#eb2f96', '#13c2c2', '#faad14', '#f5222d', '#52c41a'
      ]
      
      // 收集所有时间点
      const allTimestamps = new Set()
      history.forEach(model => {
        if (model.data && Array.isArray(model.data)) {
          model.data.forEach(point => {
            if (point && point.timestamp) {
              allTimestamps.add(point.timestamp)
            }
          })
        }
      })
      
      // 处理时间轴
      const timeAxis = Array.from(allTimestamps).sort((a, b) => {
        const timeA = new Date(a).getTime()
        const timeB = new Date(b).getTime()
        if (isNaN(timeA) || isNaN(timeB)) {
          return 0
        }
        return timeA - timeB
      })
      
      const formattedTimeAxis = timeAxis.map(timestamp => {
        const date = new Date(timestamp)
        if (isNaN(date.getTime())) {
          return timestamp
        }
        return date.toLocaleTimeString('zh-CN', {
          hour: '2-digit',
          minute: '2-digit'
        })
      })
      
      console.log('[TradingApp] 时间轴数量:', formattedTimeAxis.length)
      
      // 为每个模型创建series
      const series = history.map((model, index) => {
        const color = colors[index % colors.length]
        const modelName = model.model_name || model.name || `模型 ${index + 1}`
        
        // 为每个时间点创建数据点
        const dataPoints = timeAxis.map(time => {
          const point = model.data?.find(p => p && p.timestamp === time)
          if (!point || point.value === null || point.value === undefined) {
            return null
          }
          return point.value
        })
        
        console.log(`[TradingApp] 模型 ${modelName} 数据点数量:`, dataPoints.filter(d => d !== null).length)
        
        return {
          name: modelName,
          type: 'line',
          data: dataPoints,
          smooth: true,
          symbol: 'circle',
          symbolSize: 0,
          lineStyle: { 
            color: color, 
            width: 2 
          },
          itemStyle: { 
            color: color 
          },
          connectNulls: true
        }
      })
      
      console.log('[TradingApp] 创建的series数量:', series.length)
      
      // 参考官方示例构建option
      const option = {
        tooltip: {
          trigger: 'axis'
        },
        legend: {
          data: series.map(s => s.name),
          bottom: 10
        },
        grid: {
          left: '3%',
          right: '4%',
          bottom: '15%',
          top: '10%',
          containLabel: true
        },
        xAxis: {
          type: 'category',
          boundaryGap: false,
          data: formattedTimeAxis
        },
        yAxis: {
          type: 'value'
        },
        series: series
      }
      
      try {
        if (accountChart.value && typeof accountChart.value.setOption === 'function') {
          accountChart.value.setOption(option, true)
          // 确保图表尺寸正确
          setTimeout(() => {
            if (accountChart.value && typeof accountChart.value.resize === 'function') {
              accountChart.value.resize()
            }
          }, 100)
        }
      } catch (error) {
        console.error('[TradingApp] Error setting chart option (multi-model):', error)
      }
    } else {
      // 单模型图表
      if (!history || history.length === 0) {
        try {
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
          }, true) // 第二个参数 true 表示不合并，完全替换
        } catch (error) {
          console.error('[TradingApp] Error setting chart option (single-model empty):', error)
        }
        return
      }
      
      // 后端已返回UTC+8时区的ISO格式字符串，直接解析并格式化显示
      // 注意：history需要按时间正序排列（从早到晚），所以先reverse
      const sortedHistory = [...history].reverse()  // 创建副本并反转，避免修改原数组
      const data = sortedHistory.map((h, index) => {
        // 后端返回的是ISO格式字符串（如 '2024-01-01T12:00:00+08:00'），直接解析
        const date = new Date(h.timestamp)
        let timeStr = ''
        if (isNaN(date.getTime())) {
          console.warn('[TradingApp] Invalid timestamp:', h.timestamp)
          timeStr = h.timestamp || '' // 如果解析失败，使用原始字符串
        } else {
          // 格式化为本地时间显示（后端已经是UTC+8，所以直接显示即可）
          timeStr = date.toLocaleTimeString('zh-CN', {
            hour: '2-digit',
            minute: '2-digit'
          })
        }
        return {
          time: timeStr,
          value: h.balance || h.total_value || 0,  // 使用新字段名balance，兼容旧字段名total_value
          tradeId: h.trade_id || null,  // 保存trade_id用于标记
          timestamp: h.timestamp,  // 保存原始时间戳
          originalIndex: index,  // 保存原始索引
          // 后端已关联查询trades表，直接保存trade信息
          tradeFuture: h.future || null,  // 合约符号
          tradeSignal: h.signal || null,  // 交易信号
          tradeQuantity: h.quantity || null  // 交易数量
        }
      })
      
      // Signal中文翻译映射（提前定义，供后续使用）
      const signalMapForChart = {
        'buy_to_long': '开多',
        'buy_to_short': '开空',
        'sell_to_long': '平多',
        'sell_to_short': '平空',
        'close_position': '平仓',
        'stop_loss': '止损',
        'take_profit': '止盈',
        'hold': '观望'
      }
      const translateSignalForChart = (signal) => {
        return signalMapForChart[signal] || signal || '未知'
      }
      
      // 收集有trade_id的数据点，用于显示交易标记（在添加当前值之前）
      const tradeMarkers = []
      data.forEach((d, index) => {
        if (d.tradeId) {
          tradeMarkers.push({
            name: '交易',
            coord: [index, d.value],
            tradeId: d.tradeId,
            timestamp: d.timestamp
          })
        }
      })
      
      // 添加当前值（如果有）
      if (currentValue !== undefined && currentValue !== null) {
        const now = new Date()
        const currentTime = now.toLocaleTimeString('zh-CN', {
          timeZone: 'Asia/Shanghai',
          hour: '2-digit',
          minute: '2-digit'
        })
        data.push({
          time: currentTime,
          value: currentValue,
          tradeId: null,  // 当前值没有trade_id
          timestamp: null,
          originalIndex: -1
        })
      }
      
      // 确保数据有效
      if (!data || data.length === 0) {
        console.warn('[TradingApp] No data for single-model chart')
        return
      }
      
      // 计算数据的最小值和最大值，用于设置Y轴范围
      const values = data.map(d => d.value).filter(v => v !== null && v !== undefined && !isNaN(v))
      let minValue = values.length > 0 ? Math.min(...values) : 0
      let maxValue = values.length > 0 ? Math.max(...values) : 0
      
      // 如果最小值和最大值相同，设置一个合理的范围
      if (minValue === maxValue && minValue > 0) {
        minValue = minValue * 0.99  // 向下扩展1%
        maxValue = maxValue * 1.01  // 向上扩展1%
      } else if (minValue !== maxValue) {
        // 如果值不同，扩展一点范围以便显示
        const range = maxValue - minValue
        minValue = minValue - range * 0.05  // 向下扩展5%
        maxValue = maxValue + range * 0.05  // 向上扩展5%
      }
      
      // 参考官方示例，简化配置
      // 准备数据：保存trade信息映射（用于tooltip显示和点击事件）
      const tradeInfoMap = new Map()  // 用于tooltip显示
      const tradeDetailMap = new Map()  // 用于点击事件，保存完整信息
      data.forEach((d, index) => {
        if (d.tradeId) {
          let symbol = '未知'
          let signal = '未知'
          let quantity = 0
          let price = null
          let pnl = null
          let fee = null
          let timestamp = d.timestamp
          
          // 优先使用后端返回的trade信息
          if (d.tradeFuture || d.tradeSignal !== null || d.tradeQuantity !== null) {
            symbol = d.tradeFuture || '未知'
            signal = d.tradeSignal || '未知'
            quantity = d.tradeQuantity || 0
            price = d.tradePrice || null
            pnl = d.tradePnl || null
            fee = d.tradeFee || null
          } else {
            // 如果没有，则从allTrades中查找
            const trade = allTrades.value.find(t => t.id === d.tradeId)
            if (trade) {
              symbol = trade.future || trade.symbol || '未知'
              signal = trade.signal || '未知'
              quantity = trade.quantity || 0
              price = trade.price || null
              pnl = trade.pnl || null
              fee = trade.fee || null
              timestamp = trade.timestamp || d.timestamp
            }
          }
          
          const translatedSignal = translateSignalForChart(signal)
          tradeInfoMap.set(index, `${symbol} | ${translatedSignal} | ${quantity}`)
          
          // 保存完整的trade信息用于弹框显示
          tradeDetailMap.set(index, {
            tradeId: d.tradeId,
            symbol: symbol,
            signal: signal,
            translatedSignal: translatedSignal,
            quantity: quantity,
            price: price,
            pnl: pnl,
            fee: fee,
            timestamp: timestamp,
            accountValue: d.value
          })
        }
      })
      
      // 参考官方示例构建option
      const option = {
        tooltip: {
          trigger: 'axis',
          formatter: function(params) {
            if (!params || !Array.isArray(params) || params.length === 0 || !params[0]) {
              return ''
            }
            
            const firstParam = params[0]
            const date = firstParam.axisValue || firstParam.name || ''
            const dataIndex = firstParam.dataIndex
            
            let result = date + '<br/>'
            
            // 遍历所有系列数据
            params.forEach((item) => {
              const value = item.value
              const valueStr = typeof value === 'number' ? '$' + value.toFixed(2) : (value || 'N/A')
              result += item.marker + ' ' + (item.seriesName || '账户价值') + ': ' + valueStr + '<br/>'
            })
            
            // 添加trade信息
            if (dataIndex !== undefined && dataIndex !== null && tradeInfoMap.has(dataIndex)) {
              result += '<br/>交易信息: ' + tradeInfoMap.get(dataIndex)
            }
            
            return result
          }
        },
        grid: {
          left: '10px',
          right: '10px',
          bottom: '30px',
          top: '10px',
          containLabel: false
        },
        xAxis: {
          type: 'category',
          boundaryGap: false,
          data: data.map(d => d.time || '')
        },
        yAxis: {
          type: 'value'
        },
        series: [{
          name: '账户价值',
          type: 'line',
          data: data.map(d => d.value || null),
          symbol: 'circle',
          symbolSize: (value, params) => {
            // 如果有trade信息，显示标记点（增大以便点击）
            return tradeInfoMap.has(params.dataIndex) ? 10 : 0
          },
          itemStyle: {
            color: (params) => {
              // 有trade信息的点显示为黄色，其他为蓝色
              return tradeInfoMap.has(params.dataIndex) ? '#ffd700' : '#3370ff'
            }
          },
          lineStyle: {
            color: '#3370ff',
            width: 2
          },
          // 确保有trade信息的点可以点击
          emphasis: {
            itemStyle: {
              borderWidth: 2,
              borderColor: '#3370ff',
              shadowBlur: 10,
              shadowColor: 'rgba(51, 112, 255, 0.3)'
            }
          }
        }]
      }
      try {
        // 如果图表实例不存在，重新创建
        if (!accountChart.value) {
          accountChart.value = echarts.init(chartDom)
        }
        
        if (accountChart.value && typeof accountChart.value.setOption === 'function') {
          accountChart.value.setOption(option, true)
          
          // 移除旧的点击事件监听
          accountChart.value.off('click')
          
          // 添加点击事件监听
          accountChart.value.on('click', (params) => {
            if (params && params.dataIndex !== undefined && tradeDetailMap.has(params.dataIndex)) {
              const tradeDetail = tradeDetailMap.get(params.dataIndex)
              selectedTradeDetail.value = tradeDetail
              showTradeDetailModal.value = true
            }
          })
          
          // 确保图表尺寸正确，填充整个容器
          setTimeout(() => {
            if (accountChart.value && typeof accountChart.value.resize === 'function') {
              accountChart.value.resize()
            }
          }, 100)
        }
      } catch (error) {
        console.error('[TradingApp] Error setting chart option (single-model):', error)
      }
    }
    
    // 延迟调整大小以确保渲染完成
    setTimeout(() => {
      if (accountChart.value && typeof accountChart.value.resize === 'function') {
        try {
          accountChart.value.resize()
        } catch (error) {
          console.warn('[TradingApp] Error resizing chart:', error)
        }
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
      console.log('[TradingApp] 开始加载持仓数据, modelId:', currentModelId.value)
      const data = await modelApi.getPortfolio(currentModelId.value)
      console.log('[TradingApp] 收到持仓API响应:', data)
      
      if (data.portfolio && data.portfolio.positions) {
        console.log('[TradingApp] 原始持仓数据数量:', data.portfolio.positions.length)
        console.log('[TradingApp] 原始持仓数据:', JSON.stringify(data.portfolio.positions, null, 2))
        
        // 映射数据格式以匹配前端显示
        // 支持两种字段命名方式：下划线命名和驼峰命名
        positions.value = (data.portfolio.positions || []).map((pos, index) => {
          // 尝试读取两种命名方式的字段
          const positionAmt = pos.position_amt !== undefined ? pos.position_amt : (pos.positionAmt !== undefined ? pos.positionAmt : 0)
          const avgPrice = pos.avg_price !== undefined ? pos.avg_price : (pos.avgPrice !== undefined ? pos.avgPrice : 0)
          const currentPrice = pos.current_price !== undefined ? pos.current_price : (pos.currentPrice !== undefined ? pos.currentPrice : 0)
          const positionSide = pos.position_side !== undefined ? pos.position_side : (pos.positionSide !== undefined ? pos.positionSide : '')
          const pnl = pos.pnl !== undefined ? pos.pnl : 0
          const leverage = pos.leverage !== undefined ? pos.leverage : 1
          const initialMargin = pos.initial_margin !== undefined ? pos.initial_margin : (pos.initialMargin !== undefined ? pos.initialMargin : 0)
          
          console.log(`[TradingApp] 持仓[${index + 1}] 原始数据:`, {
            symbol: pos.symbol,
            position_amt: pos.position_amt,
            positionAmt: pos.positionAmt,
            avg_price: pos.avg_price,
            avgPrice: pos.avgPrice,
            current_price: pos.current_price,
            currentPrice: pos.currentPrice,
            position_side: pos.position_side,
            positionSide: pos.positionSide,
            pnl: pos.pnl,
            leverage: pos.leverage,
            initial_margin: pos.initial_margin,
            initialMargin: pos.initialMargin
          })
          
          const mappedPos = {
            id: pos.id || `${pos.symbol}_${positionSide}`,
            symbol: pos.symbol || '',
            side: positionSide,
            quantity: Math.abs(positionAmt || 0),
            openPrice: avgPrice || 0,
            currentPrice: currentPrice || 0,
            leverage: leverage || 1,
            pnl: pnl || 0,
            initialMargin: initialMargin || 0,
            // 保留原始数据
            ...pos
          }
          
          console.log(`[TradingApp] 持仓[${index + 1}] 映射后数据:`, {
            symbol: mappedPos.symbol,
            quantity: mappedPos.quantity,
            openPrice: mappedPos.openPrice,
            currentPrice: mappedPos.currentPrice,
            pnl: mappedPos.pnl,
            side: mappedPos.side
          })
          
          return mappedPos
        })
        
        console.log('[TradingApp] 映射完成，最终持仓数据数量:', positions.value.length)
        console.log('[TradingApp] 最终持仓数据:', JSON.stringify(positions.value, null, 2))
      } else {
        console.warn('[TradingApp] 持仓数据为空或格式不正确:', data)
        positions.value = []
      }
    } catch (error) {
      console.error('[TradingApp] Error loading positions:', error)
      errors.value.positions = error.message
    } finally {
      loading.value.positions = false
    }
  }

  /**
   * 加载交易记录（分页）
   * @param {number} page - 页码，从1开始，默认为当前页
   * @param {number} pageSize - 每页记录数，默认为10
   */
  const loadTrades = async (page = null, pageSize = null) => {
    if (!currentModelId.value) return
    
    // 使用传入的参数或当前状态
    const targetPage = page !== null ? page : tradesPage.value
    const targetPageSize = pageSize !== null ? pageSize : tradesPageSize.value
    
    loading.value.trades = true
    errors.value.trades = null
    try {
      console.log('[TradingApp] 开始加载交易记录（分页）, modelId:', currentModelId.value, 'page:', targetPage, 'pageSize:', targetPageSize)
      const data = await modelApi.getTrades(currentModelId.value, targetPage, targetPageSize)
      console.log('[TradingApp] 收到交易记录API响应:', data)
      
      // 后端返回分页格式：{ data: [], pageNum: 1, pageSize: 10, total: 100, totalPages: 10 }
      let tradesList = []
      if (data && typeof data === 'object') {
        if (Array.isArray(data)) {
          // 兼容旧格式：直接返回数组
          tradesList = data
        } else if (data.data && Array.isArray(data.data)) {
          // 新格式：分页数据
          tradesList = data.data
          tradesPage.value = data.pageNum || targetPage
          tradesPageSize.value = data.pageSize || targetPageSize
          tradesTotal.value = data.total || 0
          tradesTotalPages.value = data.totalPages || 0
          console.log('[TradingApp] 分页信息: page=', tradesPage.value, 'pageSize=', tradesPageSize.value, 'total=', tradesTotal.value, 'totalPages=', tradesTotalPages.value)
        } else if (data.trades && Array.isArray(data.trades)) {
          // 兼容格式：{ trades: [] }
          tradesList = data.trades
        }
      }
      
      console.log('[TradingApp] 交易记录数据数量:', tradesList.length)
      console.log('[TradingApp] 交易记录原始数据:', JSON.stringify(tradesList, null, 2))
      
      // 映射数据格式以匹配前端显示
      // 注意：trades表仍使用future和quantity字段，这里需要兼容
      allTrades.value = tradesList.map((trade, index) => {
        console.log(`[TradingApp] 交易记录[${index + 1}] 原始数据:`, {
          id: trade.id,
          future: trade.future,
          symbol: trade.symbol,
          signal: trade.signal,
          price: trade.price,
          quantity: trade.quantity,
          pnl: trade.pnl,
          fee: trade.fee,
          timestamp: trade.timestamp
        })
        
        const mappedTrade = {
          id: trade.id || `${trade.timestamp}_${trade.future || trade.symbol || ''}`,
          time: trade.timestamp || '',  // 后端已转换为字符串，直接使用
          timestamp: trade.timestamp || '',  // 确保timestamp字段存在
          symbol: trade.future || trade.symbol || '',  // trades表使用future字段
          signal: trade.signal || '',  // 使用signal字段
          side: trade.side || '',  // 交易类型（buy/sell），对应trades表的side字段
          position_side: trade.position_side || trade.positionSide || '',  // 持仓方向（LONG/SHORT）
          quantity: trade.quantity || 0,  // trades表使用quantity字段
          price: trade.price || 0,
          current_price: trade.current_price || 0,  // 实时价格（如果有）
          pnl: trade.pnl || 0,  // 盈亏（已根据实时价格计算）
          fee: trade.fee !== undefined ? trade.fee : 0,  // 确保fee字段存在
          // 保留原始数据
          ...trade
        }
        
        console.log(`[TradingApp] 交易记录[${index + 1}] 映射后数据:`, {
          id: mappedTrade.id,
          symbol: mappedTrade.symbol,
          price: mappedTrade.price,
          quantity: mappedTrade.quantity,
          pnl: mappedTrade.pnl,
          fee: mappedTrade.fee
        })
        
        return mappedTrade
      })
      
      console.log('[TradingApp] 映射完成，最终交易记录数据数量:', allTrades.value.length)
      console.log('[TradingApp] 最终交易记录数据:', JSON.stringify(allTrades.value, null, 2))
      
      // 显示当前页的所有记录
      trades.value = allTrades.value
      console.log('[TradingApp] 显示的交易记录数量:', trades.value.length)
    } catch (error) {
      console.error('[TradingApp] Error loading trades:', error)
      errors.value.trades = error.message
      trades.value = []
      allTrades.value = []
      tradesTotal.value = 0
      tradesTotalPages.value = 0
    } finally {
      loading.value.trades = false
    }
  }
  
  /**
   * 切换到指定页码
   */
  const goToTradesPage = async (page) => {
    if (page < 1 || (tradesTotalPages.value > 0 && page > tradesTotalPages.value)) {
      return
    }
    tradesPage.value = page
    await loadTrades(page, tradesPageSize.value)
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
   * 加载策略决策记录（分页）
   * 完全参照交易记录模块的实现方式
   * @param {number} page - 页码，从1开始，默认为当前页
   * @param {number} pageSize - 每页记录数，默认为10
   */
  const loadStrategyDecisions = async (page = null, pageSize = null) => {
    if (!currentModelId.value) return
    
    // 使用传入的参数或当前状态
    const targetPage = page !== null ? page : strategyDecisionsPage.value
    const targetPageSize = pageSize !== null ? pageSize : strategyDecisionsPageSize.value
    
    loading.value.conversations = true
    isRefreshingStrategyDecisions.value = true
    errors.value.conversations = null
    try {
      console.log('[TradingApp] 开始加载策略决策记录（分页）, modelId:', currentModelId.value, 'page:', targetPage, 'pageSize:', targetPageSize)
      const { strategyDecisionApi } = await import('../services/api.js')
      // 按“模型ID + 分页”查询全部策略决策记录（包含 trade_id 为空的记录）
      // 如需过滤状态，可在此传入 status 参数（TRIGGERED/EXECUTED/REJECTED）
      const data = await strategyDecisionApi.getByModelId(currentModelId.value, targetPage, targetPageSize)
      console.log('[TradingApp] 收到策略决策API响应:', data)
      console.log('[TradingApp] API响应数据类型:', typeof data, '是否为数组:', Array.isArray(data), '包含data字段:', data && data.data !== undefined, '包含total字段:', data && data.total !== undefined)
      
      // 后端返回分页格式：{ data: [], pageNum: 1, pageSize: 10, total: 100, totalPages: 10 }
      let decisionsList = []
      if (data && typeof data === 'object') {
        if (Array.isArray(data)) {
          // 兼容旧格式：直接返回数组
          decisionsList = data
          // 即使旧格式，也设置分页信息（使用数据长度作为总数）
          strategyDecisionsTotal.value = decisionsList.length
          strategyDecisionsTotalPages.value = Math.ceil(decisionsList.length / targetPageSize) || 1
          strategyDecisionsPage.value = targetPage
          strategyDecisionsPageSize.value = targetPageSize
        } else if (data.data && Array.isArray(data.data)) {
          // 新格式：分页数据
          decisionsList = data.data
          const safePageNum = Number(data.pageNum ?? targetPage) || 1
          const safePageSize = Number(data.pageSize ?? targetPageSize) || 10
          const safeTotal = Number(data.total ?? 0) || 0
          const safeTotalPages =
            Number(data.totalPages ?? 0) ||
            (safeTotal > 0 ? Math.max(1, Math.ceil(safeTotal / safePageSize)) : 0)

          strategyDecisionsPage.value = safePageNum
          strategyDecisionsPageSize.value = safePageSize
          strategyDecisionsTotal.value = safeTotal
          strategyDecisionsTotalPages.value = safeTotalPages
          console.log('[TradingApp] 分页信息: page=', strategyDecisionsPage.value, 'pageSize=', strategyDecisionsPageSize.value, 'total=', strategyDecisionsTotal.value, 'totalPages=', strategyDecisionsTotalPages.value)
        } else if (data.decisions && Array.isArray(data.decisions)) {
          // 兼容格式：{ decisions: [] }
          decisionsList = data.decisions
          // 尝试从 data 中获取分页信息，如果没有则使用数据长度
          strategyDecisionsTotal.value = data.total !== undefined && data.total !== null ? data.total : decisionsList.length
          strategyDecisionsTotalPages.value = data.totalPages !== undefined && data.totalPages !== null ? data.totalPages : (strategyDecisionsTotal.value > 0 ? Math.ceil(strategyDecisionsTotal.value / targetPageSize) : 0)
          strategyDecisionsPage.value = data.pageNum || targetPage
          strategyDecisionsPageSize.value = data.pageSize || targetPageSize
        } else if (data.total !== undefined || data.pageNum !== undefined) {
          // 如果数据对象包含分页字段，即使没有 data 数组，也尝试设置分页信息
          const safePageNum = Number(data.pageNum ?? targetPage) || 1
          const safePageSize = Number(data.pageSize ?? targetPageSize) || 10
          const safeTotal = Number(data.total ?? 0) || 0
          const safeTotalPages =
            Number(data.totalPages ?? 0) ||
            (safeTotal > 0 ? Math.max(1, Math.ceil(safeTotal / safePageSize)) : 0)

          strategyDecisionsTotal.value = safeTotal
          strategyDecisionsTotalPages.value = safeTotalPages
          strategyDecisionsPage.value = safePageNum
          strategyDecisionsPageSize.value = safePageSize
          console.log('[TradingApp] 从数据对象中提取分页信息: total=', strategyDecisionsTotal.value, 'totalPages=', strategyDecisionsTotalPages.value)
        }
      }
      
      // 如果仍然没有设置分页信息，但有数据，则使用数据长度作为总数
      if (decisionsList.length > 0 && strategyDecisionsTotal.value === 0) {
        strategyDecisionsTotal.value = decisionsList.length
        strategyDecisionsTotalPages.value = Math.ceil(decisionsList.length / targetPageSize) || 1
        strategyDecisionsPage.value = targetPage
        strategyDecisionsPageSize.value = targetPageSize
        console.log('[TradingApp] 使用数据长度作为分页信息: total=', strategyDecisionsTotal.value, 'totalPages=', strategyDecisionsTotalPages.value)
      }
      
      console.log('[TradingApp] 策略决策数据数量:', decisionsList.length)
      console.log('[TradingApp] 策略决策原始数据:', JSON.stringify(decisionsList, null, 2))
      console.log('[TradingApp] 当前分页状态: total=', strategyDecisionsTotal.value, 'totalPages=', strategyDecisionsTotalPages.value, 'page=', strategyDecisionsPage.value, 'pageSize=', strategyDecisionsPageSize.value)
      
      // 映射数据格式以匹配前端显示
      strategyDecisions.value = decisionsList.map((decision, index) => {
        console.log(`[TradingApp] 策略决策[${index + 1}] 原始数据:`, {
          id: decision.id,
          strategyName: decision.strategyName || decision.strategy_name,
          strategyType: decision.strategyType || decision.strategy_type,
          signal: decision.signal,
          symbol: decision.symbol,
          quantity: decision.quantity,
          leverage: decision.leverage,
          price: decision.price,
          stopPrice: decision.stopPrice || decision.stop_price,
          createdAt: decision.createdAt || decision.created_at
        })
        
        const mapped = {
          id: decision.id || `${decision.createdAt || decision.created_at}_${decision.symbol || ''}`,
          createdAt: decision.createdAt || decision.created_at || '',
          strategyName: decision.strategyName || decision.strategy_name || '',
          strategyType: decision.strategyType || decision.strategy_type || '',
          signal: decision.signal || '',
          symbol: decision.symbol || '',
          quantity: decision.quantity || 0,
          leverage: decision.leverage || 0,
          price: decision.price || 0,
          stopPrice: decision.stopPrice || decision.stop_price || 0,
          justification: decision.justification || '',
          // 保留原始数据
          ...decision
        }
        
        console.log(`[TradingApp] 策略决策[${index + 1}] 映射后数据:`, {
          id: mapped.id,
          strategyName: mapped.strategyName,
          symbol: mapped.symbol,
          signal: mapped.signal,
          quantity: mapped.quantity,
          price: mapped.price
        })
        
        return mapped
      })
      
      console.log('[TradingApp] 映射完成，最终策略决策数据数量:', strategyDecisions.value.length)
      console.log('[TradingApp] 最终策略决策数据:', JSON.stringify(strategyDecisions.value, null, 2))
      
      // 最终检查：确保分页信息已正确设置
      if (strategyDecisionsTotal.value === 0 && strategyDecisions.value.length > 0) {
        // 如果仍然没有设置总数，但有数据，使用数据长度作为总数
        strategyDecisionsTotal.value = strategyDecisions.value.length
        strategyDecisionsTotalPages.value = Math.ceil(strategyDecisions.value.length / strategyDecisionsPageSize.value) || 1
        console.log('[TradingApp] 最终检查：使用数据长度设置分页信息: total=', strategyDecisionsTotal.value, 'totalPages=', strategyDecisionsTotalPages.value)
      }
      
      console.log('[TradingApp] 最终分页状态: total=', strategyDecisionsTotal.value, 'totalPages=', strategyDecisionsTotalPages.value, 'page=', strategyDecisionsPage.value, 'pageSize=', strategyDecisionsPageSize.value)
      
      // 显示当前页的所有记录
      console.log('[TradingApp] 显示的策略决策数量:', strategyDecisions.value.length)
    } catch (error) {
      console.error('[TradingApp] Error loading strategy decisions:', error)
      errors.value.conversations = error.message
      strategyDecisions.value = []
      strategyDecisionsTotal.value = 0
      strategyDecisionsTotalPages.value = 0
    } finally {
      loading.value.conversations = false
      isRefreshingStrategyDecisions.value = false
    }
  }

  /**
   * 切换到策略决策指定页码
   */
  const goToStrategyDecisionsPage = async (page) => {
    // 注意：优先使用展示页数（策略决策接口在异常情况下可能不返回 totalPages）
    const pages = strategyDecisionsDisplayTotalPages.value
    if (page < 1 || (pages > 0 && page > pages)) {
      return
    }
    strategyDecisionsPage.value = page
    await loadStrategyDecisions(page, strategyDecisionsPageSize.value)
  }

  /**
   * 加载挂单记录（分页）
   * @param {number} page - 页码，从1开始，默认为当前页
   * @param {number} pageSize - 每页记录数，默认为10
   */
  const loadAlgoOrders = async (page = null, pageSize = null) => {
    if (!currentModelId.value) return
    
    // 使用传入的参数或当前状态
    const targetPage = page !== null ? page : algoOrdersPage.value
    const targetPageSize = pageSize !== null ? pageSize : algoOrdersPageSize.value
    
    loading.value.algoOrders = true
    errors.value.algoOrders = null
    isRefreshingAlgoOrders.value = true
    try {
      console.log('[TradingApp] 开始加载挂单记录（分页）, modelId:', currentModelId.value, 'page:', targetPage, 'pageSize:', targetPageSize)
      const data = await algoOrderApi.getByModelId(currentModelId.value, targetPage, targetPageSize)
      console.log('[TradingApp] 收到挂单API响应:', data)
      
      // 后端返回分页格式：{ data: [], pageNum: 1, pageSize: 10, total: 100, totalPages: 10 }
      let algoOrdersList = []
      if (data && typeof data === 'object') {
        if (Array.isArray(data)) {
          // 兼容旧格式：直接返回数组
          algoOrdersList = data
        } else if (data.data && Array.isArray(data.data)) {
          // 新格式：分页数据
          algoOrdersList = data.data
          algoOrdersPage.value = data.pageNum || targetPage
          algoOrdersPageSize.value = data.pageSize || targetPageSize
          algoOrdersTotal.value = data.total || 0
          algoOrdersTotalPages.value = data.totalPages || 0
          console.log('[TradingApp] 分页信息: page=', algoOrdersPage.value, 'pageSize=', algoOrdersPageSize.value, 'total=', algoOrdersTotal.value, 'totalPages=', algoOrdersTotalPages.value)
        }
      }
      
      console.log('[TradingApp] 挂单数据数量:', algoOrdersList.length)
      console.log('[TradingApp] 挂单原始数据:', JSON.stringify(algoOrdersList, null, 2))
      
      // 映射数据格式以匹配前端显示
      algoOrders.value = algoOrdersList.map((order, index) => {
        console.log(`[TradingApp] 挂单[${index + 1}] 原始数据:`, {
          id: order.id,
          symbol: order.symbol,
          side: order.side,
          positionSide: order.positionSide,
          quantity: order.quantity,
          type: order.type,
          algoStatus: order.algoStatus,
          price: order.price,
          created_at: order.created_at
        })
        
        const mapped = {
          id: order.id || `${order.created_at}_${order.symbol || ''}`,
          symbol: order.symbol || '',
          side: order.side || '',
          positionSide: order.positionSide || '',
          quantity: order.quantity || 0,
          type: order.type || '',
          algoStatus: order.algoStatus || '',
          price: order.price || 0,
          created_at: order.created_at || '',
          // 保留原始数据
          ...order
        }
        
        console.log(`[TradingApp] 挂单[${index + 1}] 映射后数据:`, {
          id: mapped.id,
          symbol: mapped.symbol,
          side: mapped.side,
          positionSide: mapped.positionSide,
          quantity: mapped.quantity,
          type: mapped.type,
          algoStatus: mapped.algoStatus,
          price: mapped.price,
          created_at: mapped.created_at
        })
        
        return mapped
      })
      
      console.log('[TradingApp] 映射完成，最终挂单数据数量:', algoOrders.value.length)
    } catch (error) {
      console.error('[TradingApp] Error loading algo orders:', error)
      errors.value.algoOrders = error.message
      algoOrders.value = []
      algoOrdersTotal.value = 0
      algoOrdersTotalPages.value = 0
    } finally {
      loading.value.algoOrders = false
      isRefreshingAlgoOrders.value = false
    }
  }
  
  /**
   * 切换到挂单指定页码
   */
  const goToAlgoOrdersPage = async (page) => {
    if (page < 1 || (algoOrdersTotalPages.value > 0 && page > algoOrdersTotalPages.value)) {
      return
    }
    algoOrdersPage.value = page
    await loadAlgoOrders(page, algoOrdersPageSize.value)
  }

  /**
   * 根据模型trade_type加载对话或策略决策
   */
  const loadConversationsOrDecisions = async () => {
    const currentModelData = currentModel.value
    const tradeType = currentModelData?.trade_type || currentModelData?.tradeType || 'ai'
    
    if (tradeType === 'strategy') {
      // 加载策略决策时，确保从第一页开始，每页10条
      await loadStrategyDecisions(1, 10)
    } else {
      await loadConversations()
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
        time: conv.timestamp || '',  // 后端已转换为字符串，直接使用
        timestamp: conv.timestamp || '', // 确保 timestamp 字段存在，后端已转换为字符串
        tokens: conv.tokens || 0, // tokens数量，用于显示
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
      
      // WebSocket 功能已禁用（涨跌幅榜和K线数据已改为轮询方式）
      // 如果需要启用 WebSocket，请取消下面的注释
      // console.log('[TradingApp] 初始化 WebSocket 连接...')
      // initWebSocket()
      
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
      
      // 没有选中模型时：默认选中第一个模型（已移除“聚合账户总览”模块）
      if (!currentModelId.value && models.value.length > 0) {
        await selectModel(models.value[0].id)
      } else if (currentModelId.value) {
        await Promise.all([
          loadPortfolio(),
          loadPositions(),
          loadTrades(),
          loadConversationsOrDecisions()
        ])
        // 启动投资组合数据自动刷新（包含账户总值、可用现金、已实现盈亏、未实现盈亏、每日收益率）
        startPortfolioAutoRefresh()
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

  // 执行交易状态
  // 执行交易状态
  const isExecutingBuy = ref(false)
  const isExecutingSell = ref(false)
  const isExecutingMarketLook = ref(false)
  const isStoppingMarketLook = ref(false)
  const isDisablingBuy = ref(false)
  const isDisablingSell = ref(false)
  const isSellingPosition = ref(false) // 一键卖出持仓状态
  
  /**
   * 显示消息提示
   */
  const showMessage = (message, type = 'info') => {
    // 创建消息元素
    const messageEl = document.createElement('div')
    messageEl.className = `message-toast message-${type}`
    messageEl.textContent = message
    
    // 添加到页面
    document.body.appendChild(messageEl)
    
    // 显示动画
    setTimeout(() => {
      messageEl.classList.add('show')
    }, 10)
    
    // 3秒后自动移除
    setTimeout(() => {
      messageEl.classList.remove('show')
      setTimeout(() => {
        document.body.removeChild(messageEl)
      }, 300)
    }, 3000)
  }
  
  /**
   * 执行买入交易
   */
  const handleExecuteBuy = async () => {
    if (!currentModelId.value) {
      showMessage('请先选择模型', 'error')
      return
    }
    
    if (isExecutingBuy.value) {
      return // 防止重复点击
    }
    
    isExecutingBuy.value = true
    try {
      const result = await modelApi.executeBuy(currentModelId.value)
      console.log('[TradingApp] Execute buy success:', result)
      
      if (result && (result.success !== false)) {
        showMessage('买入交易执行成功', 'success')
      } else {
        const errorMsg = result?.error || '执行失败'
        showMessage(`买入交易执行失败: ${errorMsg}`, 'error')
      }
      
      await Promise.all([
        loadModels(),
        loadPortfolio(),
        loadPositions(),
        loadTrades()
      ])
      return result
    } catch (error) {
      console.error('[TradingApp] Error executing buy:', error)
      const errorMsg = error.message || '执行失败，请检查网络连接'
      showMessage(`买入交易执行失败: ${errorMsg}`, 'error')
      throw error
    } finally {
      isExecutingBuy.value = false
    }
  }

  /**
   * 执行卖出交易
   */
  const handleExecuteSell = async () => {
    if (!currentModelId.value) {
      showMessage('请先选择模型', 'error')
      return
    }
    
    if (isExecutingSell.value) {
      return // 防止重复点击
    }
    
    isExecutingSell.value = true
    try {
      const result = await modelApi.executeSell(currentModelId.value)
      console.log('[TradingApp] Execute sell success:', result)
      
      if (result && (result.success !== false)) {
        showMessage('卖出交易执行成功', 'success')
      } else {
        const errorMsg = result?.error || '执行失败'
        showMessage(`卖出交易执行失败: ${errorMsg}`, 'error')
      }
      
      await Promise.all([
        loadModels(),
        loadPortfolio(),
        loadPositions(),
        loadTrades()
      ])
      return result
    } catch (error) {
      console.error('[TradingApp] Error executing sell:', error)
      const errorMsg = error.message || '执行失败，请检查网络连接'
      showMessage(`卖出交易执行失败: ${errorMsg}`, 'error')
      throw error
    } finally {
      isExecutingSell.value = false
    }
  }

  /**
   * 解析盯盘所用模型 ID：优先当前选中，否则使用列表中的第一个模型
   */
  const resolveMarketLookModelId = () => {
    if (currentModelId.value != null && currentModelId.value !== '') {
      return String(currentModelId.value)
    }
    const first = models.value && models.value[0]
    return first != null && first.id != null ? String(first.id) : null
  }

  /**
   * 执行盯盘：由后端创建容器 look-{modelId} 并运行 start_market_look
   */
  const handleExecuteMarketLook = async () => {
    const modelId = resolveMarketLookModelId()
    if (!modelId) {
      showMessage('请先添加交易模型', 'error')
      return
    }
    if (isExecutingMarketLook.value) {
      return
    }
    isExecutingMarketLook.value = true
    try {
      const result = await modelApi.executeMarketLook(modelId)
      console.log('[TradingApp] Execute market look:', result)
      if (result && (result.success !== false)) {
        const cn = result.containerName || result.containerId || ''
        const msg = result.containerStatus === 'already_running'
          ? '盯盘容器已在运行'
          : '盯盘服务已启动'
        showMessage(cn ? `${msg}（${cn}）` : msg, 'success')
      } else {
        const errorMsg = result?.error || '执行失败'
        showMessage(`盯盘启动失败: ${errorMsg}`, 'error')
      }
      await loadModels()
      return result
    } catch (error) {
      console.error('[TradingApp] Error executing market look:', error)
      const errorMsg = error.message || '执行失败，请检查网络连接'
      showMessage(`盯盘启动失败: ${errorMsg}`, 'error')
      throw error
    } finally {
      isExecutingMarketLook.value = false
    }
  }

  /**
   * 关闭盯盘：删除对应 look-{modelId} 容器
   */
  const handleStopMarketLook = async () => {
    const modelId = resolveMarketLookModelId()
    if (!modelId) {
      showMessage('请先添加交易模型', 'error')
      return
    }
    if (isStoppingMarketLook.value) {
      return
    }
    isStoppingMarketLook.value = true
    try {
      const result = await modelApi.stopMarketLook(modelId)
      console.log('[TradingApp] Stop market look:', result)
      if (result && (result.success !== false)) {
        const cn = result.containerName || ''
        showMessage(cn ? `盯盘已关闭（已删除 ${cn}）` : '盯盘已关闭', 'success')
      } else {
        const errorMsg = result?.error || '操作失败'
        showMessage(`关闭盯盘失败: ${errorMsg}`, 'error')
      }
      await loadModels()
      return result
    } catch (error) {
      console.error('[TradingApp] Error stopping market look:', error)
      const errorMsg = error.message || '关闭失败，请检查网络连接'
      showMessage(`关闭盯盘失败: ${errorMsg}`, 'error')
      throw error
    } finally {
      isStoppingMarketLook.value = false
    }
  }

  /**
   * 关闭买入交易
   */
  const handleDisableBuy = async () => {
    if (!currentModelId.value) {
      showMessage('请先选择模型', 'error')
      return
    }
    
    if (isDisablingBuy.value) {
      return // 防止重复点击
    }
    
    // 如果正在执行买入，重置执行状态
    if (isExecutingBuy.value) {
      isExecutingBuy.value = false
    }
    
    isDisablingBuy.value = true
    try {
      const result = await modelApi.disableBuy(currentModelId.value)
      console.log('[TradingApp] Disable buy success:', result)
      
      if (result && !result.error) {
        showMessage('买入交易已关闭', 'success')
      } else {
        const errorMsg = result?.error || '操作失败'
        showMessage(`关闭买入交易失败: ${errorMsg}`, 'error')
      }
      
      await Promise.all([
        loadModels(),
        loadPortfolio()
      ])
      return result
    } catch (error) {
      console.error('[TradingApp] Error disabling buy:', error)
      const errorMsg = error.message || '关闭失败，请检查网络连接'
      showMessage(`关闭买入交易失败: ${errorMsg}`, 'error')
      throw error
    } finally {
      isDisablingBuy.value = false
    }
  }

  /**
   * 关闭卖出交易
   */
  const handleDisableSell = async () => {
    if (!currentModelId.value) {
      showMessage('请先选择模型', 'error')
      return
    }
    
    if (isDisablingSell.value) {
      return // 防止重复点击
    }
    
    // 如果正在执行卖出，重置执行状态
    if (isExecutingSell.value) {
      isExecutingSell.value = false
    }
    
    isDisablingSell.value = true
    try {
      const result = await modelApi.disableSell(currentModelId.value)
      console.log('[TradingApp] Disable sell success:', result)
      
      if (result && !result.error) {
        showMessage('卖出交易已关闭', 'success')
      } else {
        const errorMsg = result?.error || '操作失败'
        showMessage(`关闭卖出交易失败: ${errorMsg}`, 'error')
      }
      
      await Promise.all([
        loadModels(),
        loadPortfolio()
      ])
      return result
    } catch (error) {
      console.error('[TradingApp] Error disabling sell:', error)
      const errorMsg = error.message || '关闭失败，请检查网络连接'
      showMessage(`关闭卖出交易失败: ${errorMsg}`, 'error')
      throw error
    } finally {
      isDisablingSell.value = false
    }
  }

  /**
   * 一键卖出持仓合约
   */
  const handleSellPosition = async (symbol) => {
    if (!currentModelId.value) {
      showMessage('请先选择模型', 'error')
      return
    }
    
    if (isSellingPosition.value) {
      return // 防止重复点击
    }
    
    // 确认操作
    if (!confirm(`确认要一键市场价卖出 ${symbol} 吗？`)) {
      return
    }
    
    isSellingPosition.value = true
    try {
      console.log('[TradingApp] 开始一键卖出持仓合约，modelId:', currentModelId.value, 'symbol:', symbol)
      
      const result = await binanceFuturesOrderApi.sellPosition(currentModelId.value, symbol)
      console.log('[TradingApp] 一键卖出成功:', result)
      
      if (result && result.success) {
        showMessage(`卖出成功: ${symbol}`, 'success')
        
        // 刷新相关数据
        await Promise.all([
          loadPortfolio(),
          loadPositions(),
          loadModelPortfolioSymbols(),
          loadTrades()
        ])
      } else {
        const errorMsg = result?.error || '操作失败'
        showMessage(`卖出失败: ${errorMsg}`, 'error')
      }
      
      return result
    } catch (error) {
      console.error('[TradingApp] 一键卖出失败:', error)
      const errorMsg = error.message || '卖出失败，请检查网络连接'
      showMessage(`卖出失败: ${errorMsg}`, 'error')
      throw error
    } finally {
      isSellingPosition.value = false
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
   * 刷新当前模块的数据：
   * 1. 持仓合约实时行情模块 - loadModelPortfolioSymbols()
   * 2. 持仓模块 - loadPositions()
   * 3. 交易记录模块 - loadTrades()
   * 4. AI对话模块 - loadConversations()
   * 5. 账户价值走势模块 - loadPortfolio() (包含账户价值历史数据，无定时刷新)
   */
  const handleRefresh = async () => {
    isRefreshingAll.value = true
    try {
      // 刷新基础数据（模型列表、市场行情、涨跌幅榜）
      await Promise.all([
        loadModels(),
        loadMarketPrices(),
        loadLeaderboard(true) // 强制刷新涨跌幅榜
      ])
      
      // 如果选中了模型，刷新该模型的所有模块数据
      if (currentModelId.value) {
        // 设置各模块的刷新状态
        isRefreshingPortfolioSymbols.value = true
        isRefreshingPositions.value = true
        isRefreshingTrades.value = true
        isRefreshingConversations.value = true
        isRefreshingAlgoOrders.value = true
        
        try {
          await Promise.all([
            loadPortfolio(), // 投资组合数据 + 账户价值走势模块（包含账户价值历史数据，无定时刷新）
            (async () => {
              // 持仓合约实时行情模块
              try {
                await loadModelPortfolioSymbols()
              } finally {
                isRefreshingPortfolioSymbols.value = false
              }
            })(),
            (async () => {
              // 持仓模块
              try {
                await loadPositions()
              } finally {
                isRefreshingPositions.value = false
              }
            })(),
            (async () => {
              // 交易记录模块
              try {
                await loadTrades()
              } finally {
                isRefreshingTrades.value = false
              }
            })(),
            (async () => {
              // AI对话模块或策略决策模块
              try {
                await loadConversationsOrDecisions()
              } finally {
                isRefreshingConversations.value = false
              }
            })(),
            (async () => {
              // 挂单模块
              try {
                await loadAlgoOrders()
              } finally {
                isRefreshingAlgoOrders.value = false
              }
            })()
          ])
        } catch (error) {
          // 确保即使出错也清除刷新状态
          isRefreshingPortfolioSymbols.value = false
          isRefreshingPositions.value = false
          isRefreshingTrades.value = false
          isRefreshingConversations.value = false
          isRefreshingAlgoOrders.value = false
          throw error
        }
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
    
    // 重置所有分页到第一页
    strategyDecisions.value = []
    strategyDecisionsPage.value = 1
    strategyDecisionsTotal.value = 0
    strategyDecisionsTotalPages.value = 0
    
    // 重置交易记录分页到第一页
    trades.value = []
    tradesPage.value = 1
    tradesTotal.value = 0
    tradesTotalPages.value = 0
    
    // 清空持仓数据，确保重新加载
    positions.value = []
    
    currentModelId.value = modelId
    // 加载模型相关数据（从第一页开始加载）
    await Promise.all([
      loadPortfolio(),
      loadPositions(), // 刷新持仓数据
      loadTrades(1, tradesPageSize.value), // 从第一页开始加载交易记录
      loadConversationsOrDecisions(), // 根据trade_type加载对话或策略决策数据
      loadAlgoOrders(1, algoOrdersPageSize.value), // 从第一页开始加载挂单记录
      loadModelPortfolioSymbols(), // 立即加载一次模型持仓合约数据
      loadAccountValueHistory() // 只在选择模型时加载一次账户价值历史（使用默认时间范围）
    ])
    // 选择模型后启动模型持仓合约列表自动刷新
    startPortfolioSymbolsAutoRefresh()
    
    // 启动投资组合数据自动刷新（包含账户总值、可用现金、已实现盈亏、未实现盈亏、每日收益率）
    // 先停止之前的刷新（如果存在），再启动新的刷新
    stopPortfolioAutoRefresh()
    startPortfolioAutoRefresh()
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
      
      // 先刷新模型列表
      await loadModels()
      
      // 如果删除的是当前选中的模型：自动切到剩余的第一个模型；若已无模型则清空页面数据
      if (currentModelId.value === deletedModelId) {
        if (models.value.length > 0) {
          await selectModel(models.value[0].id)
        } else {
          stopPortfolioAutoRefresh()
          stopPortfolioSymbolsAutoRefresh()
          currentModelId.value = null
          accountValueHistory.value = []
          positions.value = []
          trades.value = []
          conversations.value = []
          strategyDecisions.value = []
        }
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
    // 优先使用 max_positions，如果没有则使用 maxPositions（兼容两种命名方式）
    tempMaxPositions.value = model?.max_positions ?? model?.maxPositions ?? 3
    console.log('[TradingApp] 打开最大持仓数量设置模态框, modelId=', modelId, 'max_positions=', tempMaxPositions.value)
    showMaxPositionsModal.value = true
  }
  
  /**
   * 打开策略配置模态框
   */
  const openStrategyConfigModal = async (modelId, modelName) => {
    pendingStrategyConfigModelId.value = modelId
    strategyConfigModelName.value = modelName || `模型 #${modelId}`
    showStrategyConfigModal.value = true
  }

  /**
   * 打开模型设置模态框（合并杠杆和最大持仓数量）
   */
  const openModelSettingsModal = async (modelId, modelName) => {
    pendingModelSettingsId.value = modelId
    modelSettingsName.value = modelName || `模型 #${modelId}`
    loadingModelSettings.value = true
    showModelSettingsModal.value = true
    
    // 确保提供方列表已加载
    if (providers.value.length === 0) {
      await loadProviders()
    }
    
    try {
      // 从后端获取模型信息
      const model = await modelApi.getById(modelId)
      console.log('[TradingApp] 加载模型信息, modelId=', modelId, 'model=', model)
      console.log('[TradingApp] 模型字段值: max_positions=', model.max_positions, 'maxPositions=', model.maxPositions, 'auto_close_percent=', model.auto_close_percent, 'autoClosePercent=', model.autoClosePercent)
      console.log('[TradingApp] 批次配置字段值: buy_batch_size=', model.buy_batch_size, 'buyBatchSize=', model.buyBatchSize, 'sell_batch_size=', model.sell_batch_size, 'sellBatchSize=', model.sellBatchSize)
      
      // 确保 provider_id 是字符串类型（如果是 null 或 undefined，则设为空字符串）
      const providerId = model.provider_id ? String(model.provider_id) : ''
      const modelName = model.model_name || ''
      
      // 优先使用 max_positions，如果没有则使用 maxPositions（兼容两种命名方式）
      const maxPositionsValue = model.max_positions ?? model.maxPositions ?? 3
      console.log('[TradingApp] 解析后的 max_positions 值:', maxPositionsValue)
      
      // 优先使用 auto_close_percent，如果没有则使用 autoClosePercent（兼容两种命名方式）
      const autoClosePercentValue = model.auto_close_percent ?? model.autoClosePercent ?? null
      console.log('[TradingApp] 解析后的 auto_close_percent 值:', autoClosePercentValue)
      
      // 优先使用 base_volume，兼容旧字段名 quote_volume
      const baseVolumeValue = model.base_volume ?? model.baseVolume ?? model.quote_volume ?? model.quoteVolume ?? null
      console.log('[TradingApp] 解析后的 base_volume 值:', baseVolumeValue)
      
      // 优先使用 daily_return，如果没有则使用 dailyReturn（兼容两种命名方式）
      const dailyReturnValue = model.daily_return ?? model.dailyReturn ?? null
      console.log('[TradingApp] 解析后的 daily_return 值:', dailyReturnValue)
      
      // 优先使用 losses_num，如果没有则使用 lossesNum（兼容两种命名方式）
      const lossesNumValue = model.losses_num ?? model.lossesNum ?? null
      console.log('[TradingApp] 解析后的 losses_num 值:', lossesNumValue)

      // 禁止买入时间段（兼容两种命名方式）
      const forbidBuyStartValue = model.forbid_buy_start ?? model.forbidBuyStart ?? null
      const forbidBuyEndValue = model.forbid_buy_end ?? model.forbidBuyEnd ?? null

      // 相同合约禁止买入间隔（兼容两种命名方式）
      const sameSymbolIntervalValue = model.same_symbol_interval ?? model.sameSymbolInterval ?? null

      // 解析批次配置字段（兼容两种命名方式）
      const buyBatchSizeValue = model.buy_batch_size ?? model.buyBatchSize ?? 1
      const buyBatchExecutionIntervalValue = model.buy_batch_execution_interval ?? model.buyBatchExecutionInterval ?? 60
      const buyBatchExecutionGroupSizeValue = model.buy_batch_execution_group_size ?? model.buyBatchExecutionGroupSize ?? 1
      const sellBatchSizeValue = model.sell_batch_size ?? model.sellBatchSize ?? 1
      const sellBatchExecutionIntervalValue = model.sell_batch_execution_interval ?? model.sellBatchExecutionInterval ?? 60
      const sellBatchExecutionGroupSizeValue = model.sell_batch_execution_group_size ?? model.sellBatchExecutionGroupSize ?? 1
      
      console.log('[TradingApp] 解析后的批次配置值: buy_batch_size=', buyBatchSizeValue, 'buy_batch_execution_interval=', buyBatchExecutionIntervalValue, 'buy_batch_execution_group_size=', buyBatchExecutionGroupSizeValue)
      console.log('[TradingApp] 解析后的批次配置值: sell_batch_size=', sellBatchSizeValue, 'sell_batch_execution_interval=', sellBatchExecutionIntervalValue, 'sell_batch_execution_group_size=', sellBatchExecutionGroupSizeValue)
      
      console.log('[TradingApp] 设置模型配置, providerId=', providerId, 'modelName=', modelName, 'max_positions=', maxPositionsValue, 'auto_close_percent=', autoClosePercentValue, 'base_volume=', baseVolumeValue, 'daily_return=', dailyReturnValue, 'losses_num=', lossesNumValue)
      
      tempModelSettings.value = {
        provider_id: providerId,
        model_name: modelName,
        leverage: model.leverage || 10,
        max_positions: maxPositionsValue,
        auto_close_percent: autoClosePercentValue,
        base_volume: baseVolumeValue,
        daily_return: dailyReturnValue,
        losses_num: lossesNumValue,
        forbid_buy_start: forbidBuyStartValue,
        forbid_buy_end: forbidBuyEndValue,
        same_symbol_interval: sameSymbolIntervalValue,
        // 使用解析后的批次配置值
        buy_batch_size: buyBatchSizeValue,
        buy_batch_execution_interval: buyBatchExecutionIntervalValue,
        buy_batch_execution_group_size: buyBatchExecutionGroupSizeValue,
        sell_batch_size: sellBatchSizeValue,
        sell_batch_execution_interval: sellBatchExecutionIntervalValue,
        sell_batch_execution_group_size: sellBatchExecutionGroupSizeValue
      }
      
      console.log('[TradingApp] tempModelSettings 已设置:', tempModelSettings.value)
      console.log('[TradingApp] 可用提供方列表:', providers.value.map(p => ({ id: p.id, name: p.name })))
      
      // 加载当前提供方的可用模型列表（使用 nextTick 确保 DOM 更新后再执行）
      if (providerId) {
        // 使用 nextTick 确保在下一个事件循环中执行，让 Vue 先完成响应式更新
        await nextTick()
        console.log('[TradingApp] 调用 handleProviderChangeInSettings, providerId=', providerId)
        handleProviderChangeInSettings()
      } else {
        console.log('[TradingApp] providerId 为空，清空可用模型列表')
        availableModelsInSettings.value = []
      }
    } catch (error) {
      console.error('[TradingApp] Error loading model settings:', error)
      // 如果获取失败，使用本地缓存的数据
      const localModel = models.value.find(m => m.id === modelId)
      if (localModel) {
        // 确保 provider_id 是字符串类型（如果是 null 或 undefined，则设为空字符串）
        const providerId = localModel.provider_id ? String(localModel.provider_id) : ''
        
        // 优先使用 max_positions，如果没有则使用 maxPositions（兼容两种命名方式）
        const maxPositionsValue = localModel.max_positions ?? localModel.maxPositions ?? 3
        
        // 优先使用 auto_close_percent，如果没有则使用 autoClosePercent（兼容两种命名方式）
        const autoClosePercentValue = localModel.auto_close_percent ?? localModel.autoClosePercent ?? null
        
        // 优先使用 base_volume，兼容旧字段名 quote_volume
        const baseVolumeValue = localModel.base_volume ?? localModel.baseVolume ?? localModel.quote_volume ?? localModel.quoteVolume ?? null
        
        // 优先使用 daily_return，如果没有则使用 dailyReturn（兼容两种命名方式）
        const dailyReturnValue = localModel.daily_return ?? localModel.dailyReturn ?? null
        
        // 优先使用 losses_num，如果没有则使用 lossesNum（兼容两种命名方式）
        const lossesNumValue = localModel.losses_num ?? localModel.lossesNum ?? null
        
        // 解析批次配置字段（兼容两种命名方式）
        const buyBatchSizeValue = localModel.buy_batch_size ?? localModel.buyBatchSize ?? 1
        const buyBatchExecutionIntervalValue = localModel.buy_batch_execution_interval ?? localModel.buyBatchExecutionInterval ?? 60
        const buyBatchExecutionGroupSizeValue = localModel.buy_batch_execution_group_size ?? localModel.buyBatchExecutionGroupSize ?? 1
        const sellBatchSizeValue = localModel.sell_batch_size ?? localModel.sellBatchSize ?? 1
        const sellBatchExecutionIntervalValue = localModel.sell_batch_execution_interval ?? localModel.sellBatchExecutionInterval ?? 60
        const sellBatchExecutionGroupSizeValue = localModel.sell_batch_execution_group_size ?? localModel.sellBatchExecutionGroupSize ?? 1
        
        tempModelSettings.value = {
          provider_id: providerId,
          model_name: localModel.model_name || '',
          leverage: localModel.leverage || 10,
          max_positions: maxPositionsValue,
          auto_close_percent: autoClosePercentValue,
          base_volume: baseVolumeValue,
          daily_return: dailyReturnValue,
          losses_num: lossesNumValue,
          forbid_buy_start: localModel.forbid_buy_start ?? localModel.forbidBuyStart ?? null,
          forbid_buy_end: localModel.forbid_buy_end ?? localModel.forbidBuyEnd ?? null,
          same_symbol_interval: localModel.same_symbol_interval ?? localModel.sameSymbolInterval ?? null,
          // 使用解析后的批次配置值
          buy_batch_size: buyBatchSizeValue,
          buy_batch_execution_interval: buyBatchExecutionIntervalValue,
          buy_batch_execution_group_size: buyBatchExecutionGroupSizeValue,
          sell_batch_size: sellBatchSizeValue,
          sell_batch_execution_interval: sellBatchExecutionIntervalValue,
          sell_batch_execution_group_size: sellBatchExecutionGroupSizeValue
        }
        
        // 加载当前提供方的可用模型列表（使用 nextTick 确保在下一个事件循环中执行）
        if (providerId) {
          await nextTick()
          handleProviderChangeInSettings()
        } else {
          availableModelsInSettings.value = []
        }
      }
      alert('加载模型配置失败，使用缓存数据')
    } finally {
      loadingModelSettings.value = false
    }
  }
  
  /**
   * 处理模型设置中提供方变化
   */
  const handleProviderChangeInSettings = () => {
    const providerId = tempModelSettings.value.provider_id
    console.log('[TradingApp] handleProviderChangeInSettings 被调用, providerId=', providerId)
    if (!providerId || providerId === '') {
      console.log('[TradingApp] providerId 为空，清空可用模型列表和模型选择')
      availableModelsInSettings.value = []
      // 如果提供方被清空，也清空模型选择
      tempModelSettings.value.model_name = ''
      return
    }
    
    // 确保 providerId 是字符串类型，用于正确匹配
    const providerIdStr = String(providerId)
    const provider = providers.value.find(p => String(p.id) === providerIdStr)
    if (provider && provider.models) {
      availableModelsInSettings.value = provider.models.split(',').map(m => m.trim()).filter(m => m)
      console.log('[TradingApp] 加载可用模型列表成功, providerId=', providerIdStr, 'models=', availableModelsInSettings.value)
    } else {
      availableModelsInSettings.value = []
      console.warn('[TradingApp] 未找到提供方或提供方没有可用模型, providerId=', providerIdStr)
    }
    
    // 如果当前选择的模型不在新提供方的模型列表中，清空选择
    if (tempModelSettings.value.model_name && !availableModelsInSettings.value.includes(tempModelSettings.value.model_name)) {
      console.warn('[TradingApp] 当前选择的模型不在新提供方的模型列表中，清空选择, model_name=', tempModelSettings.value.model_name)
      tempModelSettings.value.model_name = ''
    } else {
      console.log('[TradingApp] 保持当前模型选择, model_name=', tempModelSettings.value.model_name)
    }
  }
  
  /**
   * 保存模型设置（API提供方、模型名称、杠杆和最大持仓数量）
   */
  const saveModelSettings = async () => {
    if (!pendingModelSettingsId.value) return
    
    const providerId = tempModelSettings.value.provider_id
    const modelName = tempModelSettings.value.model_name
    const leverageValue = tempModelSettings.value.leverage
    const maxPositionsValue = tempModelSettings.value.max_positions
    
    // 验证API提供方和模型名称
    if (!providerId) {
      alert('请选择API提供方')
      return
    }
    
    if (!modelName || !modelName.trim()) {
      alert('请选择模型')
      return
    }
    
    // 验证杠杆
    if (isNaN(leverageValue) || leverageValue < 0 || leverageValue > 125) {
      alert('请输入有效的杠杆（0-125，0 表示由 AI 自行决定）')
      return
    }
    
    // 验证最大持仓数量
    if (maxPositionsValue === null || maxPositionsValue === undefined || maxPositionsValue < 1 || !Number.isInteger(maxPositionsValue)) {
      alert('请输入有效的最大持仓数量（必须 >= 1 的整数）')
      return
    }
    
    savingModelSettings.value = true
    try {
      // 获取当前模型信息，检查是否需要更新提供方和模型名称
      const currentModel = models.value.find(m => m.id === pendingModelSettingsId.value)
      const needUpdateProvider = !currentModel || currentModel.provider_id !== providerId || currentModel.model_name !== modelName
      
      // 保存所有配置
      const promises = []
      
      // 如果需要更新提供方和模型名称
      if (needUpdateProvider) {
        promises.push(modelApi.updateProvider(pendingModelSettingsId.value, providerId, modelName))
      }
      
      // 更新杠杆、最大持仓数量、自动平仓百分比、当日成交额过滤阈值、目标每日收益率和连续亏损次数阈值
      const autoClosePercentValue = tempModelSettings.value.auto_close_percent
      const baseVolumeValue = tempModelSettings.value.base_volume
      const dailyReturnValue = tempModelSettings.value.daily_return
      const lossesNumValue = tempModelSettings.value.losses_num
      const forbidBuyStartValue = tempModelSettings.value.forbid_buy_start
      const forbidBuyEndValue = tempModelSettings.value.forbid_buy_end
      const sameSymbolIntervalValue = tempModelSettings.value.same_symbol_interval

      // 禁止买入时间段必须成对设置
      if ((forbidBuyStartValue && !forbidBuyEndValue) || (!forbidBuyStartValue && forbidBuyEndValue)) {
        alert('禁止买入开始/结束必须同时设置（或同时清空）')
        return
      }
      // 确保 maxPositionsValue 是有效的整数
      const validMaxPositions = Number.isInteger(maxPositionsValue) ? maxPositionsValue : Math.floor(maxPositionsValue)
      promises.push(
        modelApi.setLeverage(pendingModelSettingsId.value, leverageValue),
        modelApi.setMaxPositions(pendingModelSettingsId.value, validMaxPositions),
        modelApi.setAutoClosePercent(pendingModelSettingsId.value, autoClosePercentValue || null),
        modelApi.setBaseVolume(pendingModelSettingsId.value, baseVolumeValue || null),
        modelApi.setDailyReturn(pendingModelSettingsId.value, dailyReturnValue || null),
        modelApi.setLossesNum(pendingModelSettingsId.value, lossesNumValue || null),
        modelApi.setForbidBuyTime(pendingModelSettingsId.value, forbidBuyStartValue || null, forbidBuyEndValue || null),
        modelApi.setSameSymbolInterval(pendingModelSettingsId.value, sameSymbolIntervalValue && sameSymbolIntervalValue > 0 ? sameSymbolIntervalValue : null)
      )
      
      // 更新批次配置
      promises.push(
        modelApi.setBatchConfig(
          pendingModelSettingsId.value,
          tempModelSettings.value.buy_batch_size,
          tempModelSettings.value.buy_batch_execution_interval,
          tempModelSettings.value.buy_batch_execution_group_size,
          tempModelSettings.value.sell_batch_size,
          tempModelSettings.value.sell_batch_execution_interval,
          tempModelSettings.value.sell_batch_execution_group_size
        )
      )
      
      await Promise.all(promises)
      
      // 更新本地缓存
      modelLeverageMap.value[pendingModelSettingsId.value] = leverageValue
      
      // 如果更新了提供方和模型名称，刷新模型列表
      if (needUpdateProvider) {
        await loadModels()
      }
      
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
      const errorMessage = error?.response?.data?.message || error?.message || '保存模型设置失败'
      alert(`保存模型设置失败: ${errorMessage}`)
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
    const model = models.value.find(m => String(m.id) === String(modelId))
    return model ? model.name : `模型 #${modelId}`
  }

  // ============ 工具方法 ============
  
  /**
   * 格式化价格（去除尾部0）
   * 统一的价格格式化函数，用于所有symbol价格显示
   * @param {number|string} price - 价格值
   * @param {number} maxDecimals - 最大小数位数（默认6位）
   * @returns {string} 格式化后的价格字符串，去除尾部0
   */
  const formatPrice = (price, maxDecimals = 6) => {
    if (price === null || price === undefined || price === '') return '0'
    
    const numPrice = parseFloat(price)
    if (isNaN(numPrice)) return '0'
    
    // 先格式化为最大小数位数
    const formatted = numPrice.toFixed(maxDecimals)
    
    // 去除尾部0和小数点
    return formatted.replace(/\.?0+$/, '') || '0'
  }

  /**
   * 格式化价格（保留5位小数，去除尾部0，用于市场行情模块）
   */
  const formatPrice5 = (price) => {
    return formatPrice(price, 5)
  }

  /**
   * 格式化价格（保留6位小数，去除尾部0，用于持仓合约实时行情、持仓模块、交易记录等）
   */
  const formatPrice6 = (price) => {
    return formatPrice(price, 6)
  }

  /**
   * 策略决策状态中文映射
   */
  const formatStrategyDecisionStatus = (status) => {
    const s = String(status || '').toUpperCase()
    if (s === 'TRIGGERED') return '已触发'
    if (s === 'EXECUTED') return '已执行'
    if (s === 'REJECTED') return '已拒绝'
    return status || '--'
  }

  /**
   * 格式化涨跌榜价格（保留6位小数，去除尾部0）
   */
  const formatLeaderboardPrice = (price) => {
    return formatPrice(price, 6)
  }

  /**
   * 格式化货币（保留2位小数，用于通用场景）
   */
  const formatCurrency = (value) => {
    if (value === null || value === undefined) return '0.00'
    return parseFloat(value).toFixed(2)
  }

  /**
   * 格式化货币（保留5位小数，用于账户总值、可用现金等）
   */
  const formatCurrency5 = (value) => {
    if (value === null || value === undefined) return '0.00000'
    return parseFloat(value).toFixed(5)
  }
  
  /**
   * 格式化盈亏（带符号，保留2位小数）
   * 当值为0（如0.00）时显示"--"
   */
  const formatPnl = (value, isPnl = false) => {
    if (value === null || value === undefined) return '--'
    const num = parseFloat(value)
    if (isNaN(num)) return '--'
    if (num === 0) return '--'
    const sign = isPnl && num >= 0 ? '+' : ''
    return `${sign}$${num.toFixed(2)}`
  }

  /**
   * 格式化盈亏（带符号，保留5位小数，用于账户已实现盈亏、未实现盈亏等）
   */
  const formatPnl5 = (value, isPnl = false) => {
    if (value === null || value === undefined) return '$0.00000'
    const num = parseFloat(value)
    if (isNaN(num)) return '$0.00000'
    const sign = isPnl && num >= 0 ? '+' : ''
    return `${sign}$${num.toFixed(5)}`
  }
  
  /**
   * 获取盈亏样式类
   * 当盈亏为0（如0.00）时不加任何颜色，仅正数绿色、负数红色
   */
  const getPnlClass = (value, isPnl = false) => {
    if (!isPnl) return ''
    const num = parseFloat(value)
    if (isNaN(num)) return ''
    if (num === 0) return ''  // 0 不显示颜色
    return num > 0 ? 'positive' : 'negative'
  }
  
  /**
   * 格式化盈亏百分比（当前盈亏值占原始保证金的比例）
   * @param {number} pnl - 当前盈亏值
   * @param {number} initialMargin - 原始保证金
   * @returns {string} 格式化后的盈亏百分比（带符号，保留2位小数），如果数据不正常则返回"--"
   */
  const formatPnlPercent = (pnl, initialMargin) => {
    // 检查 initialMargin 是否为无效值（null, undefined, 0, 空字符串, NaN）
    if (initialMargin === null || initialMargin === undefined || initialMargin === '' || 
        initialMargin === 0 || isNaN(parseFloat(initialMargin)) || parseFloat(initialMargin) <= 0) {
      return '--'  // 如果原始保证金为0、不存在或无效，显示"--"
    }
    
    // 检查 pnl 是否为无效值
    if (pnl === null || pnl === undefined || pnl === '' || isNaN(parseFloat(pnl))) {
      return '--'  // 如果盈亏值为无效，也显示"--"
    }
    
    const pnlNum = parseFloat(pnl)
    const marginNum = parseFloat(initialMargin)
    
    // 再次检查解析后的值
    if (isNaN(pnlNum) || isNaN(marginNum) || marginNum <= 0) {
      return '--'
    }
    
    // 计算盈亏百分比：(盈亏值 / 原始保证金) * 100
    const percent = (pnlNum / marginNum) * 100
    if (percent === 0) return '--'  // 0.00% 显示"--"
    const sign = percent >= 0 ? '+' : ''
    return `${sign}${percent.toFixed(2)}%`
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
   * 格式化基础成交量（以千万为单位）
   * @param {number} value - 成交量值
   * @returns {string} 格式化后的字符串，例如：1.23千万
   */
  const formatBaseVolume = (value) => {
    if (!value && value !== 0) return '--'
    const num = parseFloat(value)
    if (isNaN(num)) return '--'
    
    // 转换为千万单位
    const volumeInTenMillion = num / 10000000
    
    // 如果小于0.01千万，显示原始值（保留2位小数）
    if (volumeInTenMillion < 0.01) {
      return num.toFixed(2)
    }
    
    // 大于等于0.01千万，显示千万单位
    return `${volumeInTenMillion.toFixed(2)}千万`
  }

  /**
   * 格式化百分比（用于每日收益率等）
   */
  const formatPercentage = (value) => {
    if (value === null || value === undefined || isNaN(value)) return '--'
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
  }

  /**
   * 格式化交易信号（翻译成中文）
   */
  const formatSignal = (signal) => {
    if (!signal) return '未知'
    const signalMap = {
      'buy_to_long': '开多',
      'buy_to_short': '开空',
      'sell_to_long': '平多',
      'sell_to_short': '平空',
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
      'buy_to_long': 'badge-buy',
      'buy_to_short': 'badge-sell',
      'sell_to_long': 'badge-close',
      'sell_to_short': 'badge-close',
      'close_position': 'badge-close',
      'stop_loss': 'badge-stop',
      'take_profit': 'badge-profit'
    }
    return classMap[signal] || 'badge-close'
  }

  /**
   * 格式化交易类型（side字段：buy/sell）
   */
  const formatTradeSide = (side) => {
    if (!side) return '未知'
    const sideLower = side.toLowerCase()
    if (sideLower === 'buy') return '买入'
    if (sideLower === 'sell') return '卖出'
    return side
  }

  /**
   * 获取交易类型的样式类
   */
  const formatTradeSideClass = (side) => {
    if (!side) return 'badge-close'
    const sideLower = side.toLowerCase()
    if (sideLower === 'buy') return 'badge-buy'
    if (sideLower === 'sell') return 'badge-sell'
    return 'badge-close'
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
    
    // 停止投资组合数据自动刷新
    stopPortfolioAutoRefresh()
    
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
    // 模块刷新状态
    isRefreshingPortfolioSymbols,
    isRefreshingPositions,
    isRefreshingTrades,
    isRefreshingConversations,
    isRefreshingAlgoOrders,
    portfolio,
    accountValueHistory,
    // 时间选择相关
    timeRangePreset,
    customStartTime,
    customEndTime,
    isLoadingAccountHistory,
    loadAccountValueHistory,
    positions,
    trades,
    // 分页相关状态
    tradesPage,
    tradesPageSize,
    tradesTotal,
    tradesTotalPages,
    goToTradesPage,
    conversations,
    strategyDecisions,
    // 策略决策分页相关状态（供 App.vue 分页展示/按钮状态使用）
    strategyDecisionsPage,
    strategyDecisionsPageSize,
    strategyDecisionsTotal,
    strategyDecisionsTotalPages,
    // 策略决策分页展示计算值
    strategyDecisionsDisplayTotal,
    strategyDecisionsDisplayTotalPages,
    strategyDecisionsHasPrev,
    strategyDecisionsHasNext,
    isRefreshingStrategyDecisions,
    // 挂单相关状态
    algoOrders,
    algoOrdersPage,
    algoOrdersPageSize,
    algoOrdersTotal,
    algoOrdersTotalPages,
    settings,
    modelPortfolioSymbols,
    lastPortfolioSymbolsRefreshTime,
    loggerEnabled,
    showSettingsModal,
    showStrategyManagementModal,
    showWeChatGroupManagementModal,
    showFutureConfigModal,
    showApiProviderModal,
    showAccountModal,
    showAddModelModal,
    showLeverageModal,
    pendingLeverageModelId,
    leverageModelName,
    showTradeDetailModal,
    selectedTradeDetail,
    mysqlLeaderboardSyncRunning,
    loading,
    isLoading,
    errors,
    
    // 方法
    initApp,
    handleRefresh,
    toggleLogger,
    isExecutingBuy,
    isExecutingSell,
    isExecutingMarketLook,
    isStoppingMarketLook,
    isDisablingBuy,
    isDisablingSell,
    isSellingPosition,
    handleExecuteBuy,
    handleExecuteSell,
    handleExecuteMarketLook,
    handleStopMarketLook,
    resolveMarketLookModelId,
    handleDisableBuy,
    handleDisableSell,
    handleSellPosition,
    refreshLeaderboard,
    selectModel,
    deleteModel,
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
    handleProviderChangeInSettings,
    availableModelsInSettings,
    showDeleteModelConfirmModal,
    pendingDeleteModelId,
    pendingDeleteModelName,
    deletingModel,
    openDeleteModelConfirm,
    confirmDeleteModel,
    cancelDeleteModel,
    showStrategyConfigModal,
    pendingStrategyConfigModelId,
    strategyConfigModelName,
    loadingStrategyConfig,
    savingStrategyConfig,
    openStrategyConfigModal,
    toggleMysqlLeaderboardSync,
    updateMysqlLeaderboardSyncStatus,
    getModelDisplayName,
    getProviderName,
    getLeverageText,
    formatPrice,
    formatPrice5,
    formatPrice6,
    formatStrategyDecisionStatus,
    formatLeaderboardPrice,
    formatCurrency,
    formatCurrency5,
    formatPnl,
    formatPnl5,
    formatPnlPercent,
    getPnlClass,
    formatVolumeChinese,
    formatBaseVolume,
    formatTime,
    formatPercentage,
    formatSignal,
    getSignalBadgeClass,
    formatTradeSide,
    formatTradeSideClass,
    
    // 数据加载方法（供外部调用）
    loadModels,
    loadProviders,
    loadMarketPrices,
    loadGainers,
    loadLosers,
    loadLeaderboard, // 已废弃，保留以兼容旧代码
    loadPortfolio,
    loadPositions,
    loadTrades,
    loadConversations,
    loadStrategyDecisions,
    loadConversationsOrDecisions,
    goToStrategyDecisionsPage,
    loadAlgoOrders,
    goToAlgoOrdersPage,
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
    // 投资组合数据自动刷新方法
    startPortfolioAutoRefresh,
    stopPortfolioAutoRefresh,
    
    // 图表更新方法
    updateAccountChart
  }
}
