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
          <button class="btn-icon" @click="handleRefresh" title="刷新">
            <i class="bi bi-arrow-repeat"></i>
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
          <button class="btn-secondary" @click="showFutureConfigModal = true">
            <i class="bi bi-list-check"></i>
            合约配置
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
            <div
              v-for="model in models"
              :key="model.id"
              :class="['model-item', { active: currentModelId === model.id }]"
              @click="selectModel(model.id)"
            >
              <div class="model-info">
                <div class="model-name">{{ model.name }}</div>
                <div class="model-meta">{{ getModelDisplayName(model.id) }}</div>
              </div>
            </div>
          </div>
        </div>
        <div class="sidebar-section">
          <div class="section-header">
            <span>市场行情</span>
            <i class="bi bi-graph-up-arrow"></i>
          </div>
          <div class="market-prices">
            <div
              v-for="price in marketPrices"
              :key="price.symbol"
              class="price-item"
              @click="openKlineChart(price.symbol)"
            >
              <div class="price-symbol">{{ price.symbol }}</div>
              <div class="price-value" :class="price.change >= 0 ? 'positive' : 'negative'">
                {{ formatPrice(price.price) }}
              </div>
              <div class="price-change" :class="price.change >= 0 ? 'positive' : 'negative'">
                {{ price.change >= 0 ? '+' : '' }}{{ price.change.toFixed(2) }}%
              </div>
            </div>
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
              <span class="status-indicator">{{ leaderboardStatus }}</span>
              <button class="btn-secondary" @click="refreshLeaderboard">
                <i class="bi bi-lightning-charge"></i> 手动刷新
              </button>
            </div>
          </div>
          <div class="leaderboard-columns">
            <div class="leaderboard-column">
              <div class="column-title positive">涨幅榜 TOP</div>
              <div class="leaderboard-list">
                <div v-for="item in leaderboardGainers" :key="item.symbol" class="leaderboard-item" @click="openKlineChart(item.symbol)">
                  <div class="item-symbol">{{ item.symbol }}</div>
                  <div class="item-change positive">+{{ item.change.toFixed(2) }}%</div>
                </div>
                <div v-if="leaderboardGainers.length === 0" class="empty-state">正在等待实时涨幅数据...</div>
              </div>
            </div>
            <div class="leaderboard-column">
              <div class="column-title negative">跌幅榜 TOP</div>
              <div class="leaderboard-list">
                <div v-for="item in leaderboardLosers" :key="item.symbol" class="leaderboard-item" @click="openKlineChart(item.symbol)">
                  <div class="item-symbol">{{ item.symbol }}</div>
                  <div class="item-change negative">{{ item.change.toFixed(2) }}%</div>
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
            <div class="stat-value">${{ formatCurrency(portfolio.realizedPnl) }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
              <span class="stat-label">未实现盈亏</span>
              <i class="bi bi-graph-down text-warning"></i>
            </div>
            <div class="stat-value">${{ formatCurrency(portfolio.unrealizedPnl) }}</div>
          </div>
        </div>

        <!-- Chart -->
        <!-- TODO: 账户价值走势图表功能待实现 -->
        <div class="content-card">
          <div class="card-header">
            <h3 class="card-title">账户价值走势</h3>
          </div>
          <div class="card-body">
            <div style="width: 100%; height: 300px; display: flex; align-items: center; justify-content: center; color: #666;">
              图表功能开发中...
            </div>
          </div>
        </div>

        <!-- Tabs -->
        <div class="content-card">
          <div class="card-tabs">
            <button :class="['tab-btn', { active: activeTab === 'positions' }]" @click="activeTab = 'positions'">持仓</button>
            <button :class="['tab-btn', { active: activeTab === 'trades' }]" @click="activeTab = 'trades'">交易记录</button>
            <button :class="['tab-btn', { active: activeTab === 'conversations' }]" @click="activeTab = 'conversations'">AI对话</button>
          </div>

          <div v-show="activeTab === 'positions'" class="tab-content">
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
                    <td>{{ position.symbol }}</td>
                    <td>{{ position.side }}</td>
                    <td>{{ position.quantity }}</td>
                    <td>${{ formatPrice(position.openPrice) }}</td>
                    <td>${{ formatPrice(position.currentPrice) }}</td>
                    <td>{{ position.leverage }}x</td>
                    <td :class="position.pnl >= 0 ? 'positive' : 'negative'">${{ formatCurrency(position.pnl) }}</td>
                  </tr>
                  <tr v-if="positions.length === 0">
                    <td colspan="7" class="empty-state">暂无持仓</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-show="activeTab === 'trades'" class="tab-content">
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
                    <td>{{ formatTime(trade.time) }}</td>
                    <td>{{ trade.symbol }}</td>
                    <td>{{ trade.side }}</td>
                    <td>{{ trade.quantity }}</td>
                    <td>${{ formatPrice(trade.price) }}</td>
                    <td :class="trade.pnl >= 0 ? 'positive' : 'negative'">${{ formatCurrency(trade.pnl) }}</td>
                    <td>${{ formatCurrency(trade.fee) }}</td>
                  </tr>
                  <tr v-if="trades.length === 0">
                    <td colspan="7" class="empty-state">暂无交易记录</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-show="activeTab === 'conversations'" class="tab-content">
            <div class="conversations-list">
              <div v-for="conv in conversations" :key="conv.id" class="conversation-item">
                <div class="conv-header">
                  <span class="conv-time">{{ formatTime(conv.time) }}</span>
                  <span class="conv-role">{{ conv.role }}</span>
                </div>
                <div class="conv-content">{{ conv.content }}</div>
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

    <!-- 其他模态框组件可以在这里添加 -->
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import KLineChart from './components/KLineChart.vue'
import { useTradingApp } from './composables/useTradingApp'

const {
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
} = useTradingApp()

const showKlineChart = ref(false)
const klineChartSymbol = ref('BTCUSDT')
const klineChartInterval = ref('5m')
const activeTab = ref('positions')

const openKlineChart = (symbol) => {
  console.log('[App] Opening KLineChart for symbol:', symbol)
  klineChartSymbol.value = symbol
  klineChartInterval.value = '5m'
  showKlineChart.value = true
  console.log('[App] showKlineChart set to:', showKlineChart.value)
}

const handleKlineIntervalChange = (interval) => {
  klineChartInterval.value = interval
}

onMounted(() => {
  initApp()
})
</script>

