<template>
  <div class="app-container">
    <!-- Header -->
    <header class="app-header">
      <div class="header-content">
        <div class="header-left">
          <div class="brand-unit">
            <div class="brand-logo">AI</div>
            <div class="brand-text">
              <h1 class="app-title">AIFuturesTrade</h1>
              <p class="brand-tagline">智能量化 · 沉浸式 3D 控制台</p>
            </div>
          </div>
          <div class="header-status">
            <span class="status-dot active"></span>
            <span class="status-text">运行中</span>
          </div>
        </div>
        <div class="header-right">
          <button 
            class="btn-icon" 
            :class="{ refreshing: isRefreshingAll }"
            @click="handleRefresh" 
            title="刷新"
            :disabled="isRefreshingAll"
          >
            <i class="bi bi-arrow-repeat" :class="{ spin: isRefreshingAll }"></i>
          </button>
          <button class="btn-icon" :class="{ active: loggerEnabled }" @click="toggleLogger" title="开启/关闭日志输出">
            <i class="bi" :class="loggerEnabled ? 'bi-play-fill' : 'bi-pause-fill'"></i>
          </button>
          <button class="btn-secondary" @click="handleExecute" title="执行当前模型" :disabled="!currentModelId">
            <i class="bi bi-play-circle"></i>
            执行交易
          </button>
          <button class="btn-secondary" @click="handlePauseAuto" title="关闭当前模型的自动化交易">
            <i class="bi bi-pause-circle"></i>
            关闭交易
          </button>
          <button class="btn-secondary" @click="showSettingsModal = true">
            <i class="bi bi-gear"></i>
            设置
          </button>
          <button class="btn-secondary" @click="showStrategyModal = true" title="配置当前模型的买卖提示词">
            <i class="bi bi-sliders"></i>
            策略配置
          </button>
          <button class="btn-secondary" @click="showApiProviderModal = true">
            <i class="bi bi-cloud-plus"></i>
            API提供方
          </button>
          <button class="btn-primary" @click="showAddModelModal = true">
            <i class="bi bi-plus-lg"></i>
            添加模型
          </button>
        </div>
      </div>
    </header>

    <div class="app-body">
      <!-- Sidebar -->
      <aside class="app-sidebar">
        <div class="sidebar-section">
          <div class="section-header">
            <span>交易模型</span>
          </div>
          <div class="model-list">
            <!-- 聚合视图选项 -->
            <div
              v-if="models.length > 0"
              :class="['model-item', { active: isAggregatedView }]"
              @click="showAggregatedView"
            >
              <div class="model-header">
                <div class="model-name"><i class="bi bi-bar-chart"></i> 聚合视图</div>
              </div>
              <div class="model-meta">
                <span>所有模型总览</span>
              </div>
            </div>
            
            <!-- 模型列表 -->
            <div
              v-for="model in models"
              :key="model.id"
              :class="['model-item', { active: currentModelId === model.id && !isAggregatedView }]"
              @click="selectModel(model.id)"
            >
              <div class="model-header">
                <div class="model-name">{{ model.name || `模型 #${model.id}` }}</div>
                <div class="model-actions" @click.stop>
                  <button class="model-action-btn" @click="handleOpenLeverageModal(model.id, model.name || `模型 #${model.id}`)" title="设置杠杆">
                    <i class="bi bi-sliders"></i>
                  </button>
                  <button class="model-action-btn" @click="deleteModel(model.id)" title="删除模型">
                    <i class="bi bi-trash"></i>
                  </button>
                </div>
              </div>
              <div class="model-meta">
                <span class="model-leverage">杠杆: {{ getLeverageText(model.id) }}</span>
                <span class="model-provider">{{ getProviderName(model.provider_id) }}</span>
              </div>
            </div>
            
            <div v-if="models.length === 0" class="empty-state">暂无模型，点击"添加模型"创建</div>
          </div>
        </div>
        <div class="sidebar-section">
          <div class="section-header">
            <span>市场行情</span>
            <i class="bi bi-graph-up-arrow"></i>
          </div>
          <div class="market-header-actions">
            <span class="market-count">{{ marketPrices.length }}个</span>
          </div>
          <div class="market-prices">
            <template v-if="marketPrices.length > 0">
              <div
                v-for="price in marketPrices"
                :key="price.symbol"
                class="price-item"
                @click="openKlineChartFromMarket(price.symbol, price.contract_symbol)"
                style="cursor: pointer;"
              >
                <div class="price-card">
                  <div class="price-left">
                    <div class="price-symbol-large">{{ price.symbol }}</div>
                    <div class="price-contract-name">{{ price.name || `${price.symbol}永续合约` }}</div>
                  </div>
                  <div class="price-right">
                    <div class="price-value-large">${{ formatPrice(price.price) }}</div>
                    <div class="price-change-with-arrow" :class="price.change_24h >= 0 ? 'positive' : 'negative'">
                      <span class="change-arrow">{{ price.change_24h >= 0 ? '▲' : '▼' }}</span>
                      <span class="change-value">{{ (Math.abs(price.change_24h) || 0).toFixed(2) }}%</span>
                    </div>
                    <div v-if="price.daily_volume" class="price-volume-chinese">
                      <span class="volume-label">当日成交额: </span>
                      <span class="volume-value">{{ formatVolumeChinese(price.daily_volume) }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </template>
            <div v-else class="empty-state">暂无市场行情数据</div>
          </div>
        </div>
      </aside>

      <!-- Main Content -->
      <main class="app-main">
        <section class="hero-banner glass-panel">
          <div class="hero-copy">
            <p class="hero-subtitle">实时 AI 交易驾驶舱</p>
            <h2>立体监控资金 · 沉浸式AI资产交易管理</h2>
            <p class="hero-text">
              通过多维度可视化，快速洞察行情动能、模型表现与风控指标，获得更具未来感的资产体验。
            </p>
            <div class="hero-badges">
              <span class="badge-pill"><i class="bi bi-lightning-charge"></i>秒级刷新</span>
              <span class="badge-pill"><i class="bi bi-shield-check"></i> 风控指令</span>
              <span class="badge-pill"><i class="bi bi-box"></i> AI资产管理</span>
            </div>
          </div>
          <div class="hero-visual">
            <div class="hero-orb orb-main"></div>
            <div class="hero-orb orb-secondary"></div>
            <div class="hero-plane plane-top"></div>
            <div class="hero-plane plane-bottom"></div>
            <div class="hero-metric metric-primary">
              <span>策略胜率</span>
              <strong>72%</strong>
            </div>
            <div class="hero-metric metric-secondary">
              <span>AI响应</span>
              <strong>500ms</strong>
            </div>
            <div class="hero-metric metric-tertiary">
              <span>资产热度</span>
              <strong>HIGH</strong>
            </div>
          </div>
        </section>

        <section class="leaderboard-section glass-panel">
          <div class="leaderboard-header">
            <div>
              <p class="section-subtitle">功能介绍 · 实时榜单</p>
              <h3>USDS-M 合约涨跌幅榜</h3>
              <p class="section-description">与市场行情模块保持一致的多维指标，横屏布局实时洞察强势与弱势合约。</p>
            </div>
            <div class="leaderboard-meta">
              <span 
                class="status-indicator" 
                :class="{
                  updating: leaderboardStatusType === 'updating',
                  success: leaderboardStatusType === 'success',
                  error: leaderboardStatusType === 'error'
                }"
              >
                {{ leaderboardStatus }}
              </span>
              <button 
                class="btn-secondary" 
                :class="{ refreshing: isRefreshingLeaderboard }"
                @click="refreshLeaderboard"
                :disabled="isRefreshingLeaderboard"
              >
                <i class="bi bi-lightning-charge" :class="{ spin: isRefreshingLeaderboard }"></i> 
                {{ isRefreshingLeaderboard ? '刷新中...' : '手动刷新' }}
              </button>
              <button 
                class="btn-secondary" 
                :class="{ 'btn-running': clickhouseLeaderboardSyncRunning, 'btn-paused': !clickhouseLeaderboardSyncRunning }"
                @click="toggleClickhouseLeaderboardSync"
                title="ClickHouse 涨幅榜同步"
              >
                <i :class="['bi', clickhouseLeaderboardSyncRunning ? 'bi-pause-circle' : 'bi-play-circle']"></i>
                <span>{{ clickhouseLeaderboardSyncRunning ? '执行中' : '已暂停' }}</span>
              </button>
            </div>
          </div>
          <div class="leaderboard-columns">
            <div class="leaderboard-column">
              <div class="column-title positive">涨幅榜 TOP</div>
              <div class="leaderboard-list">
                  <div v-for="(item, index) in leaderboardGainers" :key="item.symbol || index" class="leaderboard-item" @click="openKlineChartFromMarket(item.symbol, item.contract_symbol)">
                  <div class="leaderboard-rank">{{ index + 1 }}</div>
                  <div class="leaderboard-symbol">
                    <span class="leaderboard-symbol-name">{{ item.symbol }}</span>
                    <span v-if="item.name" class="leaderboard-symbol-desc">{{ item.name }}</span>
                  </div>
                  <div class="leaderboard-price">${{ formatLeaderboardPrice(item.price) }}</div>
                  <div class="leaderboard-change positive">+{{ (item.change_percent || item.change || 0).toFixed(2) }}%</div>
                  <div v-if="item.quote_volume" class="leaderboard-volume">
                    <span class="volume-label">成交额</span>
                    <span class="volume-value">${{ formatVolumeChinese(item.quote_volume) }}</span>
                  </div>
                </div>
                <div v-if="leaderboardGainers.length === 0" class="empty-state">正在等待实时涨幅数据...</div>
              </div>
            </div>
            <div class="leaderboard-column">
              <div class="column-title negative">跌幅榜 TOP</div>
              <div class="leaderboard-list">
                  <div v-for="(item, index) in leaderboardLosers" :key="item.symbol || index" class="leaderboard-item" @click="openKlineChartFromMarket(item.symbol, item.contract_symbol)">
                  <div class="leaderboard-rank">{{ index + 1 }}</div>
                  <div class="leaderboard-symbol">
                    <span class="leaderboard-symbol-name">{{ item.symbol }}</span>
                    <span v-if="item.name" class="leaderboard-symbol-desc">{{ item.name }}</span>
                  </div>
                  <div class="leaderboard-price">${{ formatLeaderboardPrice(item.price) }}</div>
                  <div class="leaderboard-change negative">{{ (item.change_percent || item.change || 0).toFixed(2) }}%</div>
                  <div v-if="item.quote_volume" class="leaderboard-volume">
                    <span class="volume-label">成交额</span>
                    <span class="volume-value">${{ formatVolumeChinese(item.quote_volume) }}</span>
                  </div>
                </div>
                <div v-if="leaderboardLosers.length === 0" class="empty-state">正在等待实时跌幅数据...</div>
              </div>
            </div>
          </div>
        </section>

        <!-- Stats Cards -->
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-header">
              <span class="stat-label">账户总值</span>
              <i class="bi bi-wallet2 text-primary"></i>
            </div>
            <div class="stat-value">${{ formatCurrency(portfolio.totalValue) }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
              <span class="stat-label">可用现金</span>
              <i class="bi bi-cash text-success"></i>
            </div>
            <div class="stat-value">${{ formatCurrency(portfolio.availableCash) }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
              <span class="stat-label">已实现盈亏</span>
              <i class="bi bi-graph-up text-info"></i>
            </div>
            <div class="stat-value" :class="getPnlClass(portfolio.realizedPnl, true)">{{ formatPnl(portfolio.realizedPnl, true) }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
              <span class="stat-label">未实现盈亏</span>
              <i class="bi bi-graph-down text-warning"></i>
            </div>
            <div class="stat-value" :class="getPnlClass(portfolio.unrealizedPnl, true)">{{ formatPnl(portfolio.unrealizedPnl, true) }}</div>
          </div>
        </div>

        <!-- Chart -->
        <div class="content-card">
          <div class="card-header">
            <h3 class="card-title">{{ isAggregatedView ? '聚合账户总览' : '账户价值走势' }}</h3>
          </div>
          <div class="card-body">
            <div id="accountChart" style="width: 100%; height: 300px;"></div>
          </div>
        </div>

        <!-- Tabs -->
        <div v-show="!isAggregatedView" class="content-card">
          <div class="card-tabs">
            <button :class="['tab-btn', { active: activeTab === 'positions' }]" @click="activeTab = 'positions'">持仓</button>
            <button :class="['tab-btn', { active: activeTab === 'trades' }]" @click="activeTab = 'trades'">交易记录</button>
            <button :class="['tab-btn', { active: activeTab === 'conversations' }]" @click="activeTab = 'conversations'">AI对话</button>
          </div>

          <div v-show="!isAggregatedView && activeTab === 'positions'" class="tab-content active">
            <div class="table-container">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>币种</th>
                    <th>方向</th>
                    <th>数量</th>
                    <th>开仓价</th>
                    <th>当前价</th>
                    <th>杠杆</th>
                    <th>盈亏</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="position in positions" :key="position.id">
                    <td><strong>{{ position.symbol || position.future }}</strong></td>
                    <td><span :class="['badge', position.side === 'long' ? 'badge-long' : 'badge-short']">
                      {{ position.side === 'long' ? '做多' : '做空' }}
                    </span></td>
                    <td>{{ (position.quantity || 0).toFixed(4) }}</td>
                    <td>${{ formatPrice(position.openPrice || position.avg_price) }}</td>
                    <td>${{ formatPrice(position.currentPrice || position.current_price) }}</td>
                    <td>{{ position.leverage }}x</td>
                    <td :class="getPnlClass(position.pnl || 0, true)">
                      <strong>{{ formatPnl(position.pnl || 0, true) }}</strong>
                    </td>
                  </tr>
                  <tr v-if="positions.length === 0">
                    <td colspan="7" class="empty-state">暂无持仓</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-show="!isAggregatedView && activeTab === 'trades'" class="tab-content active">
            <div class="table-container">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>时间</th>
                    <th>币种</th>
                    <th>操作</th>
                    <th>数量</th>
                    <th>价格</th>
                    <th>盈亏</th>
                    <th>费用</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="trade in trades" :key="trade.id">
                    <td>{{ formatTime(trade.time || trade.timestamp) }}</td>
                    <td><strong>{{ trade.symbol || trade.future }}</strong></td>
                    <td>
                      <span :class="['badge', 
                        trade.side === 'buy_to_enter' ? 'badge-buy' : 
                        trade.side === 'sell_to_enter' ? 'badge-sell' : 
                        'badge-close'
                      ]">
                        {{ trade.side === 'buy_to_enter' ? '开多' : 
                           trade.side === 'sell_to_enter' ? '开空' : 
                           trade.side === 'close_position' ? '平仓' : trade.side }}
                      </span>
                    </td>
                    <td>{{ (trade.quantity || 0).toFixed(4) }}</td>
                    <td>${{ formatPrice(trade.price) }}</td>
                    <td :class="getPnlClass(trade.pnl || 0, true)">{{ formatPnl(trade.pnl || 0, true) }}</td>
                    <td>${{ formatCurrency(trade.fee || 0) }}</td>
                  </tr>
                  <tr v-if="trades.length === 0">
                    <td colspan="7" class="empty-state">暂无交易记录</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-show="!isAggregatedView && activeTab === 'conversations'" class="tab-content active">
            <div class="conversations-list">
              <div v-for="conv in conversations" :key="conv.id" class="conversation-item">
                <div class="conversation-time">{{ formatTime(conv.time || conv.timestamp) }}</div>
                <div v-if="conv.user_prompt" class="conversation-bubble">
                  <div class="bubble-label">
                    <i class="bi bi-person"></i>
                    用户
                  </div>
                  <div class="conversation-text">{{ conv.user_prompt }}</div>
                </div>
                <div v-if="conv.ai_response" class="conversation-bubble conversation-ai">
                  <div class="bubble-label">
                    <i class="bi bi-robot"></i>
                    AI
                  </div>
                  <div class="conversation-text">{{ conv.ai_response }}</div>
                </div>
                <div v-if="conv.cot_trace" class="conversation-bubble conversation-system">
                  <div class="bubble-label">
                    <i class="bi bi-gear"></i>
                    思考过程
                  </div>
                  <div class="conversation-text">{{ conv.cot_trace }}</div>
                </div>
              </div>
              <div v-if="conversations.length === 0" class="empty-state">暂无对话记录</div>
            </div>
          </div>
        </div>
      </main>
    </div>

    <!-- K线图组件 -->
    <KLineChart
      :visible="showKlineChart"
      :symbol="klineChartSymbol"
      :interval="klineChartInterval"
      @close="showKlineChart = false"
      @interval-change="handleKlineIntervalChange"
    />

    <!-- 模态框组件 -->
    <SettingsModal
      :visible="showSettingsModal"
      @update:visible="showSettingsModal = $event"
      @close="showSettingsModal = false"
    />
    
    <StrategyModal
      :visible="showStrategyModal"
      :model-id="currentModelId"
      @update:visible="showStrategyModal = $event"
      @close="showStrategyModal = false"
    />
    
    <FutureConfigModal
      :visible="showFutureConfigModal"
      @update:visible="showFutureConfigModal = $event"
      @close="showFutureConfigModal = false"
      @refresh="handleRefresh"
    />
    
    <ApiProviderModal
      :visible="showApiProviderModal"
      @update:visible="showApiProviderModal = $event"
      @close="showApiProviderModal = false"
      @refresh="handleRefresh"
    />
    
    <AddModelModal
      :visible="showAddModelModal"
      @update:visible="showAddModelModal = $event"
      @close="showAddModelModal = false"
      @refresh="handleRefresh"
    />
    
    <!-- 杠杆设置模态框 -->
    <div v-if="showLeverageModal" class="modal show" @click.self="showLeverageModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3>设置杠杆 - {{ leverageModelName }}</h3>
          <button class="btn-close" @click="showLeverageModal = false">
            <i class="bi bi-x-lg"></i>
          </button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label for="leverageInput">杠杆倍数 (0-125)</label>
            <input 
              type="number" 
              id="leverageInput" 
              class="form-input" 
              min="0" 
              max="125" 
              v-model.number="tempLeverage"
            >
            <small class="form-help">输入0表示由AI自行决定杠杆。</small>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="showLeverageModal = false">取消</button>
          <button class="btn-primary" @click="handleSaveLeverage">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import KLineChart from './components/KLineChart.vue'
import SettingsModal from './components/SettingsModal.vue'
import StrategyModal from './components/StrategyModal.vue'
import FutureConfigModal from './components/FutureConfigModal.vue'
import ApiProviderModal from './components/ApiProviderModal.vue'
import AddModelModal from './components/AddModelModal.vue'
import { useTradingApp } from './composables/useTradingApp'

const {
  currentModelId,
  models,
  isAggregatedView,
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
  formatTime
} = useTradingApp()

const showKlineChart = ref(false)
const klineChartSymbol = ref('BTCUSDT')
const klineChartInterval = ref('5m')
const activeTab = ref('positions')
const tempLeverage = ref(10) // 临时杠杆值

const openKlineChart = (symbol) => {
  console.log('[App] Opening KLineChart for symbol:', symbol)
  // 确保符号格式正确（如果已经是完整格式则直接使用，否则添加USDT后缀）
  klineChartSymbol.value = symbol.includes('USDT') ? symbol : `${symbol}USDT`
  klineChartInterval.value = '5m'
  showKlineChart.value = true
  console.log('[App] showKlineChart set to:', showKlineChart.value, 'symbol:', klineChartSymbol.value)
}

const handleKlineIntervalChange = (interval) => {
  klineChartInterval.value = interval
}

const handleSaveLeverage = async () => {
  if (!pendingLeverageModelId.value) return
  if (isNaN(tempLeverage.value) || tempLeverage.value < 0 || tempLeverage.value > 125) {
    alert('请输入有效的杠杆（0-125，0 表示由 AI 自行决定）')
    return
  }
  await saveModelLeverage(tempLeverage.value)
}

const openKlineChartFromMarket = (symbol, contractSymbol) => {
  const finalSymbol = contractSymbol || symbol
  openKlineChart(finalSymbol)
}

onMounted(() => {
  initApp()
})
</script>

