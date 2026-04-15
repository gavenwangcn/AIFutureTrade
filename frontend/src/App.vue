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
            <button 
              class="btn-icon" 
              @click="handleOpenTradeContainerLogsModal" 
              title="交易容器日志"
              style="margin-left: 8px;"
            >
              <i class="bi bi-file-text"></i>
            </button>
          </div>
        </div>
        <div class="header-right">
          <div class="header-status look-logs-header-status" title="盯盘容器日志（固定容器 trade-look，可随时打开）">
            <span class="status-dot active"></span>
            <span class="status-text">运行中</span>
            <button
              class="btn-icon"
              type="button"
              @click="handleOpenLookContainerLogsModal"
              title="盯盘容器日志"
              style="margin-left: 8px;"
            >
              <i class="bi bi-file-text"></i>
            </button>
          </div>
          <button
            class="btn-secondary"
            @click="handleExecuteMarketLook"
            title="启动盯盘循环（Docker 固定容器 trade-look，无需交易模型）"
            :disabled="isExecutingMarketLook"
          >
            <i class="bi bi-play-fill" :class="{ spin: isExecutingMarketLook }"></i>
            {{ isExecutingMarketLook ? '盯盘启动中...' : '执行盯盘' }}
          </button>
          <button
            class="btn-secondary"
            @click="handleStopMarketLook"
            title="删除盯盘容器 trade-look"
            :disabled="isStoppingMarketLook"
          >
            <i class="bi bi-stop-circle" :class="{ spin: isStoppingMarketLook }"></i>
            {{ isStoppingMarketLook ? '关闭中...' : '关闭盯盘' }}
          </button>
          <button class="btn-icon" :class="{ active: loggerEnabled }" @click="toggleLogger" title="开启/关闭日志输出">
            <i class="bi" :class="loggerEnabled ? 'bi-play-fill' : 'bi-pause-fill'"></i>
          </button>
          <button 
            class="btn-secondary" 
            @click="handleExecuteBuy" 
            title="执行买入交易" 
            :disabled="!currentModelId || isExecutingBuy"
          >
            <i class="bi bi-arrow-up-circle" :class="{ spin: isExecutingBuy }"></i>
            {{ isExecutingBuy ? '执行中...' : '执行买入' }}
          </button>
          <button 
            class="btn-secondary" 
            @click="handleExecuteSell" 
            title="执行卖出交易" 
            :disabled="!currentModelId || isExecutingSell"
          >
            <i class="bi bi-arrow-down-circle" :class="{ spin: isExecutingSell }"></i>
            {{ isExecutingSell ? '执行中...' : '执行卖出' }}
          </button>
          <button 
            class="btn-secondary" 
            @click="handleDisableBuy" 
            title="关闭买入交易"
            :disabled="!currentModelId || isDisablingBuy"
          >
            <i class="bi bi-pause-circle-fill" :class="{ spin: isDisablingBuy }"></i>
            {{ isDisablingBuy ? '处理中...' : '关闭买入' }}
          </button>
          <button 
            class="btn-secondary" 
            @click="handleDisableSell" 
            title="关闭卖出交易"
            :disabled="!currentModelId || isDisablingSell"
          >
            <i class="bi bi-pause-circle-fill" :class="{ spin: isDisablingSell }"></i>
            {{ isDisablingSell ? '处理中...' : '关闭卖出' }}
          </button>
          <button class="btn-secondary" @click="showSettingsModal = true">
            <i class="bi bi-gear"></i>
            设置
          </button>
          <button class="btn-secondary" @click="showApiProviderModal = true">
            <i class="bi bi-cloud-plus"></i>
            API提供方
          </button>
          <button class="btn-secondary" @click="showAccountModal = true">
            <i class="bi bi-person-plus"></i>
            添加账户
          </button>
          <button class="btn-secondary" @click="showFutureConfigModal = true">
            <i class="bi bi-file-earmark-plus"></i>
            添加合约
          </button>
          <button class="btn-secondary" @click="showStrategyManagementModal = true">
            <i class="bi bi-diagram-3"></i>
            策略管理
          </button>
          <button class="btn-secondary" @click="showWeChatGroupManagementModal = true">
            <i class="bi bi-wechat"></i>
            微信通知
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
            <button 
              class="section-header-btn" 
              @click="handleOpenAnalysisModal"
              title="交易模型数据分析"
            >
              <i class="bi bi-graph-up-arrow"></i>
            </button>
          </div>
          <div class="model-list">
            <!-- 模型列表 -->
            <div
              v-for="model in models"
              :key="model.id"
              :class="['model-item', { active: currentModelId === model.id }]"
              @click="selectModel(model.id)"
            >
              <div class="model-header">
                <div class="model-name">{{ model.name || `模型 #${model.id}` }}</div>
                <div class="model-actions" @click.stop>
                  <button 
                    v-if="model.auto_buy_enabled || model.autoBuyEnabled" 
                    class="model-action-btn" 
                    @click="handleOpenBuyLogsModal(model.id, model.name || `模型 #${model.id}`)" 
                    title="买执行日志"
                    style="color: #67c23a;"
                  >
                    <i class="bi bi-arrow-up-circle"></i>
                  </button>
                  <button 
                    v-if="model.auto_sell_enabled || model.autoSellEnabled" 
                    class="model-action-btn" 
                    @click="handleOpenSellLogsModal(model.id, model.name || `模型 #${model.id}`)" 
                    title="卖执行日志"
                    style="color: #f56c6c;"
                  >
                    <i class="bi bi-arrow-down-circle"></i>
                  </button>
                  <button class="model-action-btn" @click="handleOpenStrategyConfigModal(model.id, model.name || `模型 #${model.id}`)" title="策略配置">
                    <i class="bi bi-diagram-3"></i>
                  </button>
                  <button class="model-action-btn" @click="handleOpenModelSettingsModal(model.id, model.name || `模型 #${model.id}`)" title="模型设置">
                    <i class="bi bi-gear"></i>
                  </button>
                  <button class="model-action-btn" @click="handleDeleteModel(model.id, model.name || `模型 #${model.id}`)" title="删除模型">
                    <i class="bi bi-trash"></i>
                  </button>
                </div>
              </div>
              <div class="model-meta">
                <span class="model-leverage">杠杆: {{ getLeverageText(model.id) }}</span>
                <span class="model-max-positions">最大持仓: {{ model.max_positions || 3 }}</span>
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
                    <div class="price-value-large">${{ formatPrice5(price.price) }}</div>
                    <div class="price-change-with-arrow" :class="(price.change_24h || 0) >= 0 ? 'positive' : 'negative'">
                      <span class="change-arrow">{{ (price.change_24h || 0) >= 0 ? '▲' : '▼' }}</span>
                      <span class="change-value">{{ Math.abs(price.change_24h || 0).toFixed(2) }}%</span>
                    </div>
                    <div v-if="price.daily_volume && price.daily_volume > 0" class="price-volume-chinese">
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
        <section class="hero-banner hero-banner-split glass-panel">
          <div class="hero-intro-panel">
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
          </div>
          <MarketLookRunningPanel class="hero-look-aside" />
        </section>

        <section class="leaderboard-section glass-panel">
          <div class="leaderboard-header">
            <div>
              <p class="section-subtitle">功能介绍 · 实时榜单</p>
              <h3>USDS-M 合约涨跌幅榜</h3>
              <p class="section-description">与市场行情模块保持一致的多维指标，横屏布局实时洞察强势与弱势合约。</p>
            </div>
            <div class="leaderboard-meta">
              <span class="status-indicator info">数据实时更新中</span>
            </div>
          </div>
          <div class="leaderboard-columns">
            <div class="leaderboard-column">
              <div class="column-header">
                <div class="column-title positive">涨幅榜 TOP</div>
                <span 
                  class="status-indicator small" 
                  :class="{
                    updating: gainersStatusType === 'updating',
                    success: gainersStatusType === 'success',
                    error: gainersStatusType === 'error'
                  }"
                >
                  {{ gainersStatus }}
                </span>
                <button 
                  class="btn-secondary btn-small" 
                  :class="{ refreshing: isRefreshingGainers }"
                  @click="loadGainers"
                  :disabled="isRefreshingGainers"
                  title="手动刷新涨幅榜"
                >
                  <i class="bi bi-lightning-charge" :class="{ spin: isRefreshingGainers }"></i>
                </button>
              </div>
              <div class="leaderboard-list">
                  <div v-for="(item, index) in leaderboardGainers" :key="item.symbol || index" class="leaderboard-item" @click="openKlineChartFromMarket(item.symbol, item.contract_symbol)">
                  <div class="leaderboard-rank">{{ index + 1 }}</div>
                  <div class="leaderboard-symbol">
                    <span class="leaderboard-symbol-name">{{ item.symbol }}</span>
                    <span v-if="item.name" class="leaderboard-symbol-desc">{{ item.name }}</span>
                  </div>
                  <div class="leaderboard-price">${{ formatLeaderboardPrice(item.price) }}</div>
                  <div class="leaderboard-change positive">+{{ (item.change_percent || item.change || 0).toFixed(2) }}%</div>
                  <div v-if="item.base_volume" class="leaderboard-volume">
                    <span class="volume-label">当日成交量</span>
                    <span class="volume-value">{{ formatBaseVolume(item.base_volume) }}</span>
                  </div>
                  <div v-if="item.quote_volume" class="leaderboard-volume">
                    <span class="volume-label">当日成交额</span>
                    <span class="volume-value">{{ formatVolumeChinese(item.quote_volume) }}</span>
                  </div>
                </div>
                <div v-if="leaderboardGainers.length === 0" class="empty-state">正在等待实时涨幅数据...</div>
              </div>
            </div>
            <div class="leaderboard-column">
              <div class="column-header">
                <div class="column-title negative">跌幅榜 TOP</div>
                <span 
                  class="status-indicator small" 
                  :class="{
                    updating: losersStatusType === 'updating',
                    success: losersStatusType === 'success',
                    error: losersStatusType === 'error'
                  }"
                >
                  {{ losersStatus }}
                </span>
                <button 
                  class="btn-secondary btn-small" 
                  :class="{ refreshing: isRefreshingLosers }"
                  @click="loadLosers"
                  :disabled="isRefreshingLosers"
                  title="手动刷新跌幅榜"
                >
                  <i class="bi bi-lightning-charge" :class="{ spin: isRefreshingLosers }"></i>
                </button>
              </div>
              <div class="leaderboard-list">
                  <div v-for="(item, index) in leaderboardLosers" :key="item.symbol || index" class="leaderboard-item" @click="openKlineChartFromMarket(item.symbol, item.contract_symbol)">
                  <div class="leaderboard-rank">{{ index + 1 }}</div>
                  <div class="leaderboard-symbol">
                    <span class="leaderboard-symbol-name">{{ item.symbol }}</span>
                    <span v-if="item.name" class="leaderboard-symbol-desc">{{ item.name }}</span>
                  </div>
                  <div class="leaderboard-price">${{ formatLeaderboardPrice(item.price) }}</div>
                  <div class="leaderboard-change negative">{{ (item.change_percent || item.change || 0).toFixed(2) }}%</div>
                  <div v-if="item.base_volume" class="leaderboard-volume">
                    <span class="volume-label">当日成交量</span>
                    <span class="volume-value">{{ formatBaseVolume(item.base_volume) }}</span>
                  </div>
                  <div v-if="item.quote_volume" class="leaderboard-volume">
                    <span class="volume-label">当日成交额</span>
                    <span class="volume-value">{{ formatVolumeChinese(item.quote_volume) }}</span>
                  </div>
                </div>
                <div v-if="leaderboardLosers.length === 0" class="empty-state">正在等待实时跌幅数据...</div>
              </div>
            </div>
          </div>
        </section>

        <!-- Stats Cards -->
        <div v-if="currentModelId" class="stats-grid">
          <div class="stat-card">
            <div class="stat-header">
              <span class="stat-label">账户总值</span>
              <i class="bi bi-wallet2 text-primary"></i>
            </div>
            <div class="stat-value">${{ formatCurrency5(portfolio.totalValue) }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
              <span class="stat-label">可用现金</span>
              <i class="bi bi-cash text-success"></i>
            </div>
            <div class="stat-value">${{ formatCurrency5(portfolio.availableCash) }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
              <span class="stat-label">已实现盈亏</span>
              <i class="bi bi-graph-up text-info"></i>
            </div>
            <div class="stat-value" :class="getPnlClass(portfolio.realizedPnl, true)">{{ formatPnl5(portfolio.realizedPnl, true) }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
              <span class="stat-label">未实现盈亏</span>
              <i class="bi bi-graph-down text-warning"></i>
            </div>
            <div class="stat-value" :class="getPnlClass(portfolio.unrealizedPnl, true)">{{ formatPnl5(portfolio.unrealizedPnl, true) }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
              <span class="stat-label">每日收益率</span>
              <i class="bi bi-percent text-primary"></i>
            </div>
            <div class="stat-value" :class="getPnlClass(portfolio.dailyReturnRate, false)">
              {{ portfolio.dailyReturnRate !== null && portfolio.dailyReturnRate !== undefined ? formatPercentage(portfolio.dailyReturnRate) : '--' }}
            </div>
          </div>
        </div>

        <!-- Chart -->
        <div v-if="currentModelId" class="content-card">
          <div class="card-header" style="display: flex; justify-content: space-between; align-items: center;">
            <h3 class="card-title">账户价值走势</h3>
            <!-- 时间选择控件（仅单模型视图显示） -->
            <div v-if="currentModelId" style="display: flex; gap: 10px; align-items: center;">
              <!-- 快速选择下拉框 -->
              <select 
                v-model="timeRangePreset" 
                @change="handleTimeRangeChange"
                style="padding: 6px 12px; border: 1px solid #e5e6eb; border-radius: 4px; font-size: 14px; background: white; cursor: pointer;"
              >
                <option value="5days">最近5天</option>
                <option value="10days">最近10天</option>
                <option value="30days">最近30天</option>
                <option value="custom">自定义</option>
              </select>
              
              <!-- 自定义时间选择（当选择"自定义"时显示） -->
              <template v-if="timeRangePreset === 'custom'">
                <input 
                  type="datetime-local" 
                  v-model="customStartTime"
                  @change="handleTimeRangeChange"
                  style="padding: 6px 12px; border: 1px solid #e5e6eb; border-radius: 4px; font-size: 14px;"
                  placeholder="开始时间"
                />
                <span style="color: #86909c;">至</span>
                <input 
                  type="datetime-local" 
                  v-model="customEndTime"
                  @change="handleTimeRangeChange"
                  style="padding: 6px 12px; border: 1px solid #e5e6eb; border-radius: 4px; font-size: 14px;"
                  placeholder="结束时间"
                />
              </template>
            </div>
          </div>
          <div class="card-body" style="position: relative;">
            <!-- 加载动画 -->
            <div v-if="isLoadingAccountHistory" style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 10; display: flex; flex-direction: column; align-items: center; gap: 12px;">
              <div class="spinner" style="width: 40px; height: 40px; border: 4px solid #f3f3f3; border-top: 4px solid #3370ff; border-radius: 50%; animation: spin 1s linear infinite;"></div>
              <span style="color: #86909c; font-size: 14px;">加载中...</span>
            </div>
            <div id="accountChart" style="width: 100%; height: 300px;" :style="{ opacity: isLoadingAccountHistory ? 0.3 : 1 }"></div>
          </div>
        </div>

        <!-- Model Portfolio Symbols -->
        <div v-show="currentModelId" class="content-card">
          <div class="card-header">
            <h3 class="card-title" title="展示该模型持仓合约的实时数据走势">
              {{ getModelDisplayName(currentModelId) }} - 
              <span style="font-weight: bold;">
                <i class="bi bi-bar-chart-line" :class="{ spin: isRefreshingPortfolioSymbols }"></i> 持仓合约实时行情
                <i v-if="isRefreshingPortfolioSymbols" class="bi bi-arrow-repeat spin" style="margin-left: 8px; color: var(--primary-color);"></i>
              </span>
            </h3>
            <span class="last-refresh-time" title="持仓合约数据最后刷新时间">
              <i v-if="isRefreshingPortfolioSymbols" class="bi bi-arrow-repeat spin" style="margin-right: 4px;"></i>
              最后刷新: {{ formatTime(lastPortfolioSymbolsRefreshTime) }}
            </span>
          </div>
          <div class="card-body">
            <div v-if="modelPortfolioSymbols.length > 0" class="model-portfolio-symbols-grid">
              <div 
                v-for="(item, index) in modelPortfolioSymbols" 
                :key="item.symbol"
                class="model-portfolio-symbol-item"
              >
                <div class="price-card" @click="openKlineChartFromMarket(item.symbol)">
                    <div class="price-left">
                      <div class="price-symbol-large">{{ item.symbol }}</div>
                      <div class="price-contract-name">{{ item.symbol }}永续合约</div>
                    </div>
                    <div class="price-right">
                      <div class="price-value-large">${{ formatPrice6(item.price || 0) }}</div>
                      <div class="price-change-with-arrow" :class="getSymbolChangeClass(item.symbol)">
                        <span class="change-arrow">{{ getSymbolChangeArrow(item.symbol) }}</span>
                        <span class="change-value">{{ (item.changePercent || item.change || 0).toFixed(2) }}%</span>
                      </div>
                      <div class="price-volume-chinese">
                        <span class="volume-label">当日成交额: </span>
                        <span class="volume-value">{{ formatVolumeChinese(item.quoteVolume || item.volume || 0) }}</span>
                      </div>
                    </div>
                  </div>
                <!-- 卖出按钮 -->
                <button 
                  class="sell-button" 
                  @click.stop="handleSellPosition(item.symbol)"
                  :disabled="isSellingPosition"
                  title="一键市场价卖出"
                >
                  <span class="sell-icon">⚪</span>
                </button>
              </div>
            </div>
            <div v-else class="no-data-container">
              <div class="no-data-icon">📊</div>
              <div class="no-data-text">暂无持仓合约数据</div>
              <div class="no-data-subtext">该模型当前没有持仓合约或数据加载失败</div>
            </div>
          </div>
        </div>

        <!-- Tabs -->
        <div v-show="currentModelId" class="content-card">
          <div class="card-tabs">
            <button :class="['tab-btn', { active: activeTab === 'positions' }]" @click="activeTab = 'positions'">
              <i v-if="isRefreshingPositions" class="bi bi-arrow-repeat spin" style="margin-right: 4px;"></i>
              持仓
            </button>
            <button :class="['tab-btn', { active: activeTab === 'trades' }]" @click="activeTab = 'trades'">
              <i v-if="isRefreshingTrades" class="bi bi-arrow-repeat spin" style="margin-right: 4px;"></i>
              交易记录
            </button>
            <button :class="['tab-btn', { active: activeTab === 'algo-orders' }]" @click="activeTab = 'algo-orders'">
              <i v-if="isRefreshingAlgoOrders" class="bi bi-arrow-repeat spin" style="margin-right: 4px;"></i>
              市场委托单
            </button>
            <button 
              v-if="currentModel && (currentModel.trade_type || currentModel.tradeType) === 'strategy'"
              :class="['tab-btn', { active: activeTab === 'conversations' }]" 
              @click="activeTab = 'conversations'"
            >
              <i v-if="isRefreshingStrategyDecisions" class="bi bi-arrow-repeat spin" style="margin-right: 4px;"></i>
              触发交易策略
            </button>
            <button 
              v-else
              :class="['tab-btn', { active: activeTab === 'conversations' }]" 
              @click="activeTab = 'conversations'"
            >
              <i v-if="isRefreshingConversations" class="bi bi-arrow-repeat spin" style="margin-right: 4px;"></i>
              AI对话
            </button>
          </div>

          <div v-show="activeTab === 'positions'" class="tab-content active">
            <div v-if="loading.positions" class="loading-container">
              <i class="bi bi-arrow-repeat spin" style="font-size: 24px; color: var(--primary-color);"></i>
              <p style="margin-top: 12px; color: var(--text-secondary);">加载持仓数据中...</p>
            </div>
            <div v-else class="table-container">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>币种</th>
                    <th>方向</th>
                    <th>数量</th>
                    <th>开仓价</th>
                    <th>当前价</th>
                    <th>杠杆</th>
                    <th>开仓保证金</th>
                    <th>盈亏</th>
                    <th>盈亏百分比</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="position in positions" :key="position.id">
                    <td><strong>{{ position.symbol }}</strong></td>
                    <td><span :class="['badge', (position.side || position.position_side || '').toLowerCase() === 'long' ? 'badge-long' : 'badge-short']">
                      {{ (position.side || position.position_side || '').toLowerCase() === 'long' ? '做多' : '做空' }}
                    </span></td>
                    <td>{{ (position.quantity || Math.abs(position.position_amt || position.positionAmt || 0)).toFixed(4) }}</td>
                    <td>${{ formatPrice6(position.openPrice || position.avg_price || position.avgPrice || 0) }}</td>
                    <td>${{ formatPrice6(position.currentPrice || position.current_price || position.currentPrice || 0) }}</td>
                    <td>{{ position.leverage }}x</td>
                    <td>${{ formatCurrency5(position.initialMargin || position.initial_margin || 0) }}</td>
                    <td :class="getPnlClass(position.pnl || 0, true)">
                      <strong>{{ formatPnl(position.pnl || 0, true) }}</strong>
                    </td>
                    <td :class="getPnlClass(position.pnl || 0, true)">
                      <strong>{{ formatPnlPercent(position.pnl, position.initialMargin || position.initial_margin) }}</strong>
                    </td>
                  </tr>
                  <tr v-if="positions.length === 0">
                    <td colspan="9" class="empty-state">暂无持仓</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-show="activeTab === 'trades'" class="tab-content active">
            <div v-if="loading.trades" class="loading-container">
              <i class="bi bi-arrow-repeat spin" style="font-size: 24px; color: var(--primary-color);"></i>
              <p style="margin-top: 12px; color: var(--text-secondary);">加载交易记录中...</p>
            </div>
            <div v-else>
              <div
                v-if="errors && errors.conversations"
                style="margin-bottom: 12px; padding: 12px 14px; border-radius: 10px; border: 1px solid rgba(245, 34, 45, 0.25); background: rgba(245, 34, 45, 0.08); color: var(--danger); font-size: 14px;"
              >
                {{ errors.conversations }}
              </div>
              <div class="table-container">
                <table class="data-table">
                  <thead>
                    <tr>
                      <th>时间</th>
                      <th>币种</th>
                      <th>交易类型</th>
                      <th>操作</th>
                      <th>数量</th>
                      <th>价格</th>
                      <th>盈亏</th>
                      <th>盈亏百分比</th>
                      <th>费用</th>
                      <th>交易错误信息</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="trade in trades" :key="trade.id">
                      <td>{{ trade.timestamp || trade.time || '' }}</td>
                      <td><strong>{{ trade.future || trade.symbol }}</strong></td>
                      <td>
                        <span :class="['badge', formatTradeSideClass(trade.side)]">
                          {{ formatTradeSide(trade.side) }}
                        </span>
                      </td>
                      <td>
                        <span :class="['badge', getSignalBadgeClass(trade.signal || (trade.position_side || trade.positionSide || '').toLowerCase())]">
                          {{ formatSignal(trade.signal || (trade.position_side || trade.positionSide || '').toLowerCase()) }}
                        </span>
                      </td>
                      <td>{{ (trade.quantity || 0).toFixed(4) }}</td>
                      <td>${{ formatPrice6(trade.price) }}</td>
                      <td :class="trade.side === 'buy' ? '' : getPnlClass(trade.pnl || 0, true)">
                        {{ trade.side === 'buy' ? '--' : formatPnl(trade.pnl || 0, true) }}
                      </td>
                      <td :class="trade.side === 'buy' ? '' : getPnlClass(trade.pnl || 0, true)">
                        <strong>{{ trade.side === 'buy' ? '--' : formatPnlPercent(trade.pnl, trade.initialMargin || trade.initial_margin) }}</strong>
                      </td>
                      <td>${{ formatCurrency(trade.fee || 0) }}</td>
                      <td>
                        <span 
                          v-if="trade.error" 
                          :title="trade.error"
                          style="color: #f56c6c; cursor: help; max-width: 200px; display: inline-block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;"
                        >
                          {{ trade.error.length > 20 ? trade.error.substring(0, 20) + '...' : trade.error }}
                        </span>
                        <span v-else style="color: #c0c4cc;">--</span>
                      </td>
                    </tr>
                    <tr v-if="trades.length === 0">
                      <td colspan="10" class="empty-state">暂无交易记录</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <!-- 分页控件 -->
              <div v-if="tradesTotal > 0" class="pagination-container" style="margin-top: 16px; display: flex; justify-content: space-between; align-items: center;">
                <div class="pagination-info" style="color: var(--text-secondary); font-size: 14px;">
                  共 {{ tradesTotal }} 条记录，第 {{ tradesPage }} / {{ tradesTotalPages }} 页
                </div>
                <div class="pagination-controls" style="display: flex; gap: 8px;">
                  <button 
                    class="btn btn-sm" 
                    :disabled="tradesPage <= 1" 
                    @click="goToTradesPage(tradesPage - 1)"
                    style="padding: 4px 12px; border: 1px solid var(--border-color); background: var(--bg-secondary); color: var(--text-primary); border-radius: 4px; cursor: pointer;"
                    :style="{ opacity: tradesPage <= 1 ? 0.5 : 1, cursor: tradesPage <= 1 ? 'not-allowed' : 'pointer' }"
                  >
                    上一页
                  </button>
                  <button 
                    class="btn btn-sm" 
                    :disabled="tradesPage >= tradesTotalPages" 
                    @click="goToTradesPage(tradesPage + 1)"
                    style="padding: 4px 12px; border: 1px solid var(--border-color); background: var(--bg-secondary); color: var(--text-primary); border-radius: 4px; cursor: pointer;"
                    :style="{ opacity: tradesPage >= tradesTotalPages ? 0.5 : 1, cursor: tradesPage >= tradesTotalPages ? 'not-allowed' : 'pointer' }"
                  >
                    下一页
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- 市场委托单模块 -->
          <div v-show="activeTab === 'algo-orders'" class="tab-content active">
            <div v-if="loading.algoOrders" class="loading-container">
              <i class="bi bi-arrow-repeat spin" style="font-size: 24px; color: var(--primary-color);"></i>
              <p style="margin-top: 12px; color: var(--text-secondary);">加载挂单记录中...</p>
            </div>
            <div v-else>
              <div
                v-if="errors && errors.algoOrders"
                style="margin-bottom: 12px; padding: 12px 14px; border-radius: 10px; border: 1px solid rgba(245, 34, 45, 0.25); background: rgba(245, 34, 45, 0.08); color: var(--danger); font-size: 14px;"
              >
                {{ errors.algoOrders }}
              </div>
              <div class="table-container">
                <table class="data-table">
                  <thead>
                    <tr>
                      <th>时间</th>
                      <th>币种</th>
                      <th>交易类型</th>
                      <th>操作</th>
                      <th>数量</th>
                      <th>订单类型</th>
                      <th>触发价格</th>
                      <th>状态</th>
                      <th>失败原因</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="order in algoOrders" :key="order.id">
                      <td>{{ order.created_at || '' }}</td>
                      <td><strong>{{ order.symbol }}</strong></td>
                      <td>
                        <span :class="['badge', formatTradeSideClass(order.side)]">
                          {{ formatTradeSide(order.side) }}
                        </span>
                      </td>
                      <td>
                        <span :class="['badge', getSignalBadgeClass((order.positionSide || '').toLowerCase())]">
                          {{ formatPositionSide(order.positionSide) }}
                        </span>
                      </td>
                      <td>{{ (order.quantity || 0).toFixed(4) }}</td>
                      <td>{{ order.type || '' }}</td>
                      <td>${{ formatPrice6(order.triggerPrice) }}</td>
                      <td>
                        <span :class="['badge', getAlgoStatusBadgeClass(order.algoStatus)]">
                          {{ formatAlgoStatus(order.algoStatus) }}
                        </span>
                      </td>
                      <td>
                        <span
                          v-if="order.error_reason"
                          :title="order.error_reason"
                          style="color: var(--danger); font-size: 13px; cursor: help; display: inline-block; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;"
                        >
                          {{ order.error_reason.length > 50 ? order.error_reason.substring(0, 50) + '...' : order.error_reason }}
                        </span>
                        <span v-else style="color: var(--text-secondary);">--</span>
                      </td>
                    </tr>
                    <tr v-if="algoOrders.length === 0">
                      <td colspan="9" class="empty-state">暂无挂单记录</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <!-- 分页控件 -->
              <div v-if="algoOrdersTotal > 0" class="pagination-container" style="margin-top: 16px; display: flex; justify-content: space-between; align-items: center;">
                <div class="pagination-info" style="color: var(--text-secondary); font-size: 14px;">
                  共 {{ algoOrdersTotal }} 条记录，第 {{ algoOrdersPage }} / {{ algoOrdersTotalPages }} 页
                </div>
                <div class="pagination-controls" style="display: flex; gap: 8px;">
                  <button 
                    class="btn btn-sm" 
                    :disabled="algoOrdersPage <= 1" 
                    @click="goToAlgoOrdersPage(algoOrdersPage - 1)"
                    style="padding: 4px 12px; border: 1px solid var(--border-color); background: var(--bg-secondary); color: var(--text-primary); border-radius: 4px; cursor: pointer;"
                    :style="{ opacity: algoOrdersPage <= 1 ? 0.5 : 1, cursor: algoOrdersPage <= 1 ? 'not-allowed' : 'pointer' }"
                  >
                    上一页
                  </button>
                  <button 
                    class="btn btn-sm" 
                    :disabled="algoOrdersPage >= algoOrdersTotalPages" 
                    @click="goToAlgoOrdersPage(algoOrdersPage + 1)"
                    style="padding: 4px 12px; border: 1px solid var(--border-color); background: var(--bg-secondary); color: var(--text-primary); border-radius: 4px; cursor: pointer;"
                    :style="{ opacity: algoOrdersPage >= algoOrdersTotalPages ? 0.5 : 1, cursor: algoOrdersPage >= algoOrdersTotalPages ? 'not-allowed' : 'pointer' }"
                  >
                    下一页
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- 策略决策模块（当trade_type为strategy时显示） -->
          <div v-show="activeTab === 'conversations' && currentModel && (currentModel.trade_type || currentModel.tradeType) === 'strategy'" class="tab-content active">
            <div v-if="loading.conversations" class="loading-container">
              <i class="bi bi-arrow-repeat spin" style="font-size: 24px; color: var(--primary-color);"></i>
              <p style="margin-top: 12px; color: var(--text-secondary);">加载策略决策记录中...</p>
            </div>
            <div v-else>
              <div class="table-container">
                <table class="data-table">
                  <thead>
                    <tr>
                      <th>时间</th>
                      <th>策略名称</th>
                      <th>策略类型</th>
                      <th>状态</th>
                      <th>交易信号</th>
                      <th>合约名称</th>
                      <th>数量</th>
                      <th>杠杆</th>
                      <th>期望价格</th>
                      <th>触发价格</th>
                      <th>触发理由</th>
                      <th>交易ID</th>
                      <th>错误信息</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="decision in strategyDecisions" :key="decision.id">
                      <td>{{ decision.createdAt || decision.created_at || '' }}</td>
                      <td><strong>{{ decision.strategyName || decision.strategy_name }}</strong></td>
                      <td>
                        <span :class="['badge', (decision.strategyType || decision.strategy_type) === 'buy' ? 'badge-long' : 'badge-short']">
                          {{ (decision.strategyType || decision.strategy_type) === 'buy' ? '买入' : '卖出' }}
                        </span>
                      </td>
                      <td>
                        <span class="badge" :class="(String(decision.status || decision.status_code || '').toUpperCase() === 'EXECUTED' ? 'badge-long' : (String(decision.status || decision.status_code || '').toUpperCase() === 'REJECTED' ? 'badge-short' : ''))">
                          {{ formatStrategyDecisionStatus(decision.status || decision.status_code) }}
                        </span>
                      </td>
                      <td>
                        <span :class="['badge', getSignalBadgeClass(decision.signal)]">
                          {{ formatSignal(decision.signal) }}
                        </span>
                      </td>
                      <td><strong>{{ decision.symbol || '-' }}</strong></td>
                      <td>{{ decision.quantity != null ? formatQuantityTrimZeros(decision.quantity, 8) : '-' }}</td>
                      <td>{{ decision.leverage ? decision.leverage + 'x' : '-' }}</td>
                      <td>{{ decision.price ? '$' + formatPrice6(decision.price) : '-' }}</td>
                      <td>{{ decision.stopPrice || decision.stop_price ? '$' + formatPrice6(decision.stopPrice || decision.stop_price) : '-' }}</td>
                      <td style="max-width: 300px; word-break: break-word;">{{ decision.justification || '-' }}</td>
                      <td>
                        <span
                          :title="decision.tradeId || decision.trade_id || '--'"
                          style="max-width: 220px; display: inline-block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;"
                        >
                          {{ decision.tradeId || decision.trade_id || '--' }}
                        </span>
                      </td>
                      <td style="max-width: 240px; word-break: break-word;">
                        {{ decision.errorReason || decision.error_reason || '--' }}
                      </td>
                    </tr>
                    <tr v-if="strategyDecisions.length === 0">
                      <td colspan="13" class="empty-state">暂无策略决策记录</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <!-- 分页控件 -->
              <div v-if="strategyDecisionsDisplayTotal > 0" class="pagination-container" style="margin-top: 16px; display: flex; justify-content: space-between; align-items: center;">
                <div class="pagination-info" style="color: var(--text-secondary); font-size: 14px;">
                  共 {{ strategyDecisionsDisplayTotal }} 条记录，第 {{ strategyDecisionsPage }} / {{ strategyDecisionsDisplayTotalPages }} 页
                </div>
                <div class="pagination-controls" style="display: flex; gap: 8px;">
                  <button 
                    class="btn btn-sm" 
                    :disabled="!strategyDecisionsHasPrev" 
                    @click="goToStrategyDecisionsPage(strategyDecisionsPage - 1)"
                    style="padding: 4px 12px; border: 1px solid var(--border-color); background: var(--bg-secondary); color: var(--text-primary); border-radius: 4px; cursor: pointer;"
                    :style="{ opacity: !strategyDecisionsHasPrev ? 0.5 : 1, cursor: !strategyDecisionsHasPrev ? 'not-allowed' : 'pointer' }"
                  >
                    上一页
                  </button>
                  <button 
                    class="btn btn-sm" 
                    :disabled="!strategyDecisionsHasNext" 
                    @click="goToStrategyDecisionsPage(strategyDecisionsPage + 1)"
                    style="padding: 4px 12px; border: 1px solid var(--border-color); background: var(--bg-secondary); color: var(--text-primary); border-radius: 4px; cursor: pointer;"
                    :style="{ opacity: !strategyDecisionsHasNext ? 0.5 : 1, cursor: !strategyDecisionsHasNext ? 'not-allowed' : 'pointer' }"
                  >
                    下一页
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- AI对话模块（当trade_type为ai时显示） -->
          <div v-show="activeTab === 'conversations' && (!currentModel || (currentModel.trade_type || currentModel.tradeType) !== 'strategy')" class="tab-content active">
            <div v-if="loading.conversations" class="loading-container">
              <i class="bi bi-arrow-repeat spin" style="font-size: 24px; color: var(--primary-color);"></i>
              <p style="margin-top: 12px; color: var(--text-secondary);">加载AI对话数据中...</p>
            </div>
            <div v-else class="conversations-list">
              <div v-for="conv in conversations" :key="conv.id" class="conversation-item">
                <div class="conversation-header">
                  <div class="conversation-time-wrapper">
                    <span class="conversation-time">{{ conv.timestamp || conv.time || '' }}</span>
                    <span v-if="conv.type" :class="['conversation-type-badge', `badge-${conv.type}`]">
                      {{ conv.type === 'buy' ? '买入' : conv.type === 'sell' ? '卖出' : conv.type }}
                    </span>
                  </div>
                  <div class="conversation-tokens">
                    <i class="bi bi-cpu"></i>
                    <span class="tokens-label">Tokens:</span>
                    <span class="tokens-value">{{ conv.tokens || 0 }}</span>
                  </div>
                </div>
                <div v-if="conv.user_prompt && settings.show_system_prompt" class="conversation-bubble">
                  <div class="bubble-label">
                    <i class="bi bi-person"></i>
                    系统提示词
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

    <!-- Trade详情弹框 -->
    <Modal
      :visible="showTradeDetailModal"
      title="交易详情"
      @update:visible="showTradeDetailModal = $event"
      @close="showTradeDetailModal = false"
    >
      <div v-if="selectedTradeDetail" class="trade-detail-content">
        <div class="trade-detail-row">
          <div class="trade-detail-label">合约符号</div>
          <div class="trade-detail-value">{{ selectedTradeDetail.symbol }}</div>
        </div>
        <div class="trade-detail-row">
          <div class="trade-detail-label">交易信号</div>
          <div class="trade-detail-value">{{ selectedTradeDetail.translatedSignal }}</div>
        </div>
        <div class="trade-detail-row">
          <div class="trade-detail-label">交易数量</div>
          <div class="trade-detail-value">{{ selectedTradeDetail.quantity }}</div>
        </div>
        <div v-if="selectedTradeDetail.price !== null" class="trade-detail-row">
          <div class="trade-detail-label">交易价格</div>
          <div class="trade-detail-value">${{ selectedTradeDetail.price?.toFixed(2) || 'N/A' }}</div>
        </div>
        <div v-if="selectedTradeDetail.pnl !== null" class="trade-detail-row">
          <div class="trade-detail-label">盈亏</div>
          <div class="trade-detail-value" :class="{ 'profit': selectedTradeDetail.pnl > 0, 'loss': selectedTradeDetail.pnl < 0 }">
            ${{ selectedTradeDetail.pnl?.toFixed(2) || 'N/A' }}
          </div>
        </div>
        <div v-if="selectedTradeDetail.fee !== null" class="trade-detail-row">
          <div class="trade-detail-label">手续费</div>
          <div class="trade-detail-value">${{ selectedTradeDetail.fee?.toFixed(2) || 'N/A' }}</div>
        </div>
        <div class="trade-detail-row">
          <div class="trade-detail-label">账户价值</div>
          <div class="trade-detail-value">${{ selectedTradeDetail.accountValue?.toFixed(2) || 'N/A' }}</div>
        </div>
        <div class="trade-detail-row">
          <div class="trade-detail-label">交易时间</div>
          <div class="trade-detail-value">{{ selectedTradeDetail.timestamp ? new Date(selectedTradeDetail.timestamp).toLocaleString('zh-CN') : 'N/A' }}</div>
        </div>
      </div>
    </Modal>

    <!-- 模态框组件 -->
    <SettingsModal
      :visible="showSettingsModal"
      @update:visible="showSettingsModal = $event"
      @close="handleSettingsModalClose"
    />
    
    
    
    <StrategyManagementModal
      :visible="showStrategyManagementModal"
      @update:visible="showStrategyManagementModal = $event"
      @close="showStrategyManagementModal = false"
    />

    <WeChatGroupManagementModal
      :visible="showWeChatGroupManagementModal"
      @update:visible="showWeChatGroupManagementModal = $event"
      @close="showWeChatGroupManagementModal = false"
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
    
    <AccountModal
      :visible="showAccountModal"
      @update:visible="showAccountModal = $event"
      @close="showAccountModal = false"
      @refresh="handleRefresh"
    />
    
    <AddModelModal
      :visible="showAddModelModal"
      @update:visible="showAddModelModal = $event"
      @close="showAddModelModal = false"
      @refresh="handleRefresh"
    />

    <ModelStrategyConfigModal
      :visible="showStrategyConfigModal"
      :modelId="pendingStrategyConfigModelId"
      :modelName="strategyConfigModelName"
      @update:visible="showStrategyConfigModal = $event"
      @close="showStrategyConfigModal = false"
      @saved="handleRefresh"
    />

    <TradeLogsModal
      :visible="showTradeLogsModal"
      :modelId="pendingTradeLogsModelId"
      :modelName="tradeLogsModelName"
      @update:visible="showTradeLogsModal = $event"
      @close="showTradeLogsModal = false"
    />
    
    <BuyLogsModal
      :visible="showBuyLogsModal"
      :modelId="pendingBuyLogsModelId"
      :modelName="buyLogsModelName"
      @update:visible="showBuyLogsModal = $event"
      @close="showBuyLogsModal = false"
    />
    
    <SellLogsModal
      :visible="showSellLogsModal"
      :modelId="pendingSellLogsModelId"
      :modelName="sellLogsModelName"
      @update:visible="showSellLogsModal = $event"
      @close="showSellLogsModal = false"
    />
    <LookLogsModal
      :visible="showLookLogsModal"
      :modelId="pendingLookLogsModelId"
      :modelName="lookLogsModelName"
      @update:visible="showLookLogsModal = $event"
      @close="showLookLogsModal = false"
    />
    <ModelAnalysisModal
      :visible="showAnalysisModal"
      @update:visible="showAnalysisModal = $event"
      @close="showAnalysisModal = false"
    />
    
    <!-- 模型设置模态框（合并杠杆和最大持仓数量） -->
    <div v-if="showModelSettingsModal" class="modal show" @click.self="showModelSettingsModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3>模型设置 - {{ modelSettingsName }}</h3>
          <button class="btn-close" @click="showModelSettingsModal = false">
            <i class="bi bi-x-lg"></i>
          </button>
        </div>
        <div class="modal-body">
          <div v-if="loadingModelSettings" class="loading-message">
            正在加载模型配置...
          </div>
          <div v-else>
            <div class="form-group">
              <label for="settingsProviderInput">选择API提供方</label>
              <select 
                id="settingsProviderInput" 
                class="form-input" 
                v-model="tempModelSettings.provider_id"
                @change="handleProviderChangeInSettings"
              >
                <option value="">请选择API提供方</option>
                <option v-for="provider in providers" :key="provider.id" :value="provider.id">
                  {{ provider.name }}
                </option>
              </select>
              <small class="form-help">选择模型使用的API提供方。</small>
            </div>
            <div class="form-group">
              <label for="settingsModelNameInput">模型</label>
              <select 
                id="settingsModelNameInput" 
                class="form-input" 
                v-model="tempModelSettings.model_name"
              >
                <option value="">请先选择API提供方</option>
                <option v-for="model in availableModelsInSettings" :key="model" :value="model">
                  {{ model }}
                </option>
              </select>
              <small class="form-help">选择模型使用的AI模型名称。</small>
            </div>
            <div class="form-group">
              <label for="settingsLeverageInput">杠杆倍数 (0-125)</label>
              <input 
                type="number" 
                id="settingsLeverageInput" 
                class="form-input" 
                min="0" 
                max="125" 
                v-model.number="tempModelSettings.leverage"
              >
              <small class="form-help">输入0表示由AI自行决定杠杆。</small>
            </div>
            <div class="form-group">
              <label for="settingsMaxPositionsInput" title="设置该模型最多可以同时持有的合约数量，默认为3。">最大持仓数量 (>= 1)</label>
              <input 
                type="number" 
                id="settingsMaxPositionsInput" 
                class="form-input" 
                min="1" 
                v-model.number="tempModelSettings.max_positions"
              >
            </div>
            <div class="form-group">
              <label for="settingsAutoClosePercentInput" title="当损失本金达到此百分比时自动平仓（例如：10 表示损失10%本金时自动平仓）。留空或0表示不启用自动平仓。">自动平仓百分比</label>
              <input 
                type="number" 
                id="settingsAutoClosePercentInput" 
                class="form-input" 
                min="0" 
                max="100" 
                step="0.1"
                v-model.number="tempModelSettings.auto_close_percent"
              >
            </div>
            <div class="form-group">
              <label for="settingsBaseVolumeInput" title="只交易当日成交额大于此阈值的合约（以千万为单位，例如：10 表示1亿成交额）。留空或0表示不过滤。">当日成交额过滤阈值（千万单位）</label>
              <input 
                type="number" 
                id="settingsBaseVolumeInput" 
                class="form-input" 
                min="0" 
                step="0.1"
                v-model.number="tempModelSettings.base_volume"
              >
            </div>
            <div class="form-group">
              <label for="settingsDailyReturnInput" title="设置目标每日收益率（百分比，例如：5 表示5%）。当当日收益率达到此值时，将不再进行买入交易。留空或0表示不限制。">目标每日收益率（百分比）</label>
              <input 
                type="number" 
                id="settingsDailyReturnInput" 
                class="form-input" 
                min="0" 
                step="0.1"
                v-model.number="tempModelSettings.daily_return"
              >
            </div>
            <div class="form-group">
              <label for="settingsLossesNumInput" title="设置连续亏损次数阈值（例如：3 表示连续3笔亏损后暂停买入交易）。留空或0表示不限制。">连续亏损次数阈值</label>
              <input 
                type="number" 
                id="settingsLossesNumInput" 
                class="form-input" 
                min="1"
                v-model.number="tempModelSettings.losses_num"
              >
            </div>
            <div class="form-group">
              <label>禁止买入开始</label>
              <TimePicker v-model="tempModelSettings.forbid_buy_start" />
            </div>
            <div class="form-group">
              <label>禁止买入结束</label>
              <TimePicker v-model="tempModelSettings.forbid_buy_end" />
            </div>
            <div class="form-group">
              <label for="settingsSameSymbolIntervalInput" title="同一合约在指定分钟数内禁止再次买入。留空或0表示不过滤。">相同合约禁止买入间隔（分钟）</label>
              <input
                type="number"
                id="settingsSameSymbolIntervalInput"
                class="form-input"
                min="0"
                placeholder="留空不过滤"
                v-model.number="tempModelSettings.same_symbol_interval"
              >
              <small class="form-help">同一symbol在此时长内已有买入记录则不再买入</small>
            </div>
            <div class="form-group">
              <label style="font-weight: 600; margin-bottom: 12px; display: block;">买入批次配置</label>
              <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px;">
                <div>
                  <label style="font-size: 13px; color: var(--text-2);">批次大小</label>
                  <input v-model.number="tempModelSettings.buy_batch_size" type="number" class="form-input" min="1" />
                  <small class="form-help">每次提交给AI的symbol数量，默认1</small>
                </div>
                <div>
                  <label style="font-size: 13px; color: var(--text-2);">执行间隔（秒）</label>
                  <input v-model.number="tempModelSettings.buy_batch_execution_interval" type="number" class="form-input" min="0" />
                  <small class="form-help">批次执行间隔，默认60</small>
                </div>
                <div>
                  <label style="font-size: 13px; color: var(--text-2);">分组大小</label>
                  <input v-model.number="tempModelSettings.buy_batch_execution_group_size" type="number" class="form-input" min="1" />
                  <small class="form-help">每N个批次统一处理，默认1</small>
                </div>
              </div>
            </div>
            <div class="form-group">
              <label style="font-weight: 600; margin-bottom: 12px; display: block;">卖出批次配置</label>
              <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px;">
                <div>
                  <label style="font-size: 13px; color: var(--text-2);">批次大小</label>
                  <input v-model.number="tempModelSettings.sell_batch_size" type="number" class="form-input" min="1" />
                  <small class="form-help">每次提交给AI的symbol数量，默认1</small>
                </div>
                <div>
                  <label style="font-size: 13px; color: var(--text-2);">执行间隔（秒）</label>
                  <input v-model.number="tempModelSettings.sell_batch_execution_interval" type="number" class="form-input" min="0" />
                  <small class="form-help">批次执行间隔，默认60</small>
                </div>
                <div>
                  <label style="font-size: 13px; color: var(--text-2);">分组大小</label>
                  <input v-model.number="tempModelSettings.sell_batch_execution_group_size" type="number" class="form-input" min="1" />
                  <small class="form-help">每N个批次统一处理，默认1</small>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="showModelSettingsModal = false">取消</button>
          <button class="btn-primary" @click="handleSaveModelSettings" :disabled="loadingModelSettings || savingModelSettings">
            {{ savingModelSettings ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>
    
    <!-- 删除模型确认弹框 -->
    <div v-if="showDeleteModelConfirmModal" class="modal show" @click.self="cancelDeleteModel">
      <div class="modal-content">
        <div class="modal-header">
          <h3>确认删除模型</h3>
          <button class="btn-close" @click="cancelDeleteModel">
            <i class="bi bi-x-lg"></i>
          </button>
        </div>
        <div class="modal-body">
          <div class="delete-confirm-message">
            <p>你确认删除当前 <strong>{{ pendingDeleteModelName }}</strong> 模型吗？</p>
            <p style="color: #dc3545; margin-top: 15px; font-weight: bold;">
              <i class="bi bi-exclamation-triangle"></i>
              将会删除当前模型相关的所有数据，此操作不可恢复，请谨慎操作！
            </p>
            <p style="color: #e6a23c; margin-top: 10px; font-size: 14px;">
              <i class="bi bi-info-circle"></i>
              如果该模型有正在运行的买入或卖出容器，将会自动停止并删除。
            </p>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="cancelDeleteModel" :disabled="deletingModel">取消</button>
          <button class="btn-danger" @click="confirmDeleteModel" :disabled="deletingModel">
            {{ deletingModel ? '删除中...' : '确认删除' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import KLineChart from './components/KLineChart.vue'
import SettingsModal from './components/SettingsModal.vue'
import Modal from './components/Modal.vue'
import StrategyManagementModal from './components/StrategyManagementModal.vue'
import WeChatGroupManagementModal from './components/WeChatGroupManagementModal.vue'
import FutureConfigModal from './components/FutureConfigModal.vue'
import ApiProviderModal from './components/ApiProviderModal.vue'
import AccountModal from './components/AccountModal.vue'
import AddModelModal from './components/AddModelModal.vue'
import TimePicker from './components/TimePicker.vue'
import ModelStrategyConfigModal from './components/ModelStrategyConfigModal.vue'
import TradeLogsModal from './components/TradeLogsModal.vue'
import BuyLogsModal from './components/BuyLogsModal.vue'
import SellLogsModal from './components/SellLogsModal.vue'
import LookLogsModal from './components/LookLogsModal.vue'
import MarketLookRunningPanel from './components/MarketLookRunningPanel.vue'
import ModelAnalysisModal from './components/ModelAnalysisModal.vue'
import { useTradingApp } from './composables/useTradingApp'

const {
  currentModelId,
  currentModel,
  models,
  marketPrices,
  leaderboardGainers,
  leaderboardLosers,
  // 涨幅榜状态
  gainersStatus,
  gainersStatusType,
  isRefreshingGainers,
  // 跌幅榜状态
  losersStatus,
  losersStatusType,
  isRefreshingLosers,
  // 模块刷新状态
  isRefreshingPortfolioSymbols,
  isRefreshingPositions,
  isRefreshingTrades,
  isRefreshingConversations,
  isRefreshingAlgoOrders,
  portfolio,
  accountValueHistory,
  timeRangePreset,
  customStartTime,
  customEndTime,
  isLoadingAccountHistory,
  loadAccountValueHistory,
  positions,
  trades,
  tradesPage,
  tradesPageSize,
  tradesTotal,
  tradesTotalPages,
  goToTradesPage,
  conversations,
  strategyDecisions,
  isRefreshingStrategyDecisions,
  strategyDecisionsPage,
  strategyDecisionsPageSize,
  strategyDecisionsTotal,
  strategyDecisionsTotalPages,
  strategyDecisionsDisplayTotal,
  strategyDecisionsDisplayTotalPages,
  strategyDecisionsHasPrev,
  strategyDecisionsHasNext,
  goToStrategyDecisionsPage,
  // 挂单相关状态
  algoOrders,
  algoOrdersPage,
  algoOrdersPageSize,
  algoOrdersTotal,
  algoOrdersTotalPages,
  loadAlgoOrders,
  goToAlgoOrdersPage,
  loading,
  errors,
  loadPositions,
  loadTrades,
  loadConversations,
  loadStrategyDecisions,
  loadConversationsOrDecisions,
  settings,
  loggerEnabled,
  showSettingsModal,
  showStrategyManagementModal,
  showFutureConfigModal,
  showApiProviderModal,
  showAccountModal,
  showAddModelModal,
  showLeverageModal,
  pendingLeverageModelId,
  leverageModelName,
  showTradeDetailModal,
  selectedTradeDetail,
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
  providers,
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
  openStrategyConfigModal,
  initApp,
  handleRefresh,
  toggleLogger,
  handleExecuteBuy,
  handleExecuteSell,
  handleExecuteMarketLook,
  handleStopMarketLook,
  handleDisableBuy,
  handleDisableSell,
  isExecutingBuy,
  isExecutingSell,
  isExecutingMarketLook,
  isStoppingMarketLook,
  isDisablingBuy,
  isDisablingSell,
  loadGainers,
  loadLosers,
  selectModel,
  deleteModel,
  openLeverageModal,
  saveModelLeverage,
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
  modelPortfolioSymbols,
  lastPortfolioSymbolsRefreshTime,
  loadSettings,
  isSellingPosition,
  handleSellPosition
} = useTradingApp()

const TRADE_LOOK_CONTAINER_ID = 'trade-look'

const handleOpenLookContainerLogsModal = () => {
  pendingLookLogsModelId.value = TRADE_LOOK_CONTAINER_ID
  lookLogsModelName.value = '盯盘容器 (trade-look)'
  showLookLogsModal.value = true
}

// 处理设置模态框关闭事件
const handleSettingsModalClose = () => {
  showSettingsModal.value = false
  // 重新加载设置，确保显示状态更新
  loadSettings()
}

const showKlineChart = ref(false)
const klineChartSymbol = ref('BTCUSDT')
const klineChartInterval = ref('5m')
const activeTab = ref('positions')
const showTradeLogsModal = ref(false)
const pendingTradeLogsModelId = ref(null)
const tradeLogsModelName = ref('')
const showBuyLogsModal = ref(false)
const pendingBuyLogsModelId = ref(null)
const buyLogsModelName = ref('')
const showSellLogsModal = ref(false)
const pendingSellLogsModelId = ref(null)
const sellLogsModelName = ref('')
const showLookLogsModal = ref(false)
const pendingLookLogsModelId = ref(null)
const lookLogsModelName = ref('')
const showAnalysisModal = ref(false)
const tempLeverage = ref(10) // 临时杠杆值

// 监听模型切换，自动切换到持仓模块并重置分页
watch(currentModelId, async (newModelId, oldModelId) => {
  // 当模型切换时（从无模型到有模型，或从一个模型切换到另一个模型）
  if (newModelId && newModelId !== oldModelId) {
    console.log(`[App] Model changed: ${oldModelId} -> ${newModelId}, switching to positions tab`)
    // 自动切换到持仓模块
    activeTab.value = 'positions'
  }
})

// 格式化挂单状态
const formatAlgoStatus = (status) => {
  if (!status) return '未知'
  const statusMap = {
    'new': '新建',
    'triggered': '已触发',
    'executed': '已执行',
    'cancelled': '已取消',
    'failed': '失败'
  }
  return statusMap[status.toLowerCase()] || status
}

// 数量显示：最多保留 maxDecimals 位小数，并去掉末尾无意义的0（以及可能残留的小数点）
const formatQuantityTrimZeros = (value, maxDecimals = 8) => {
  if (value === null || value === undefined || value === '') return '-'
  const n = Number(value)
  if (!Number.isFinite(n)) return String(value)
  const fixed = n.toFixed(Math.max(0, Math.min(20, Number(maxDecimals) || 0)))
  return fixed.replace(/\.?0+$/, '')
}

// 格式化持仓方向（LONG -> 做多，SHORT -> 做空）
const formatPositionSide = (positionSide) => {
  if (!positionSide) return '--'
  const sideUpper = positionSide.toUpperCase()
  if (sideUpper === 'LONG') return '做多'
  if (sideUpper === 'SHORT') return '做空'
  return positionSide
}

// 获取挂单状态样式类
const getAlgoStatusBadgeClass = (status) => {
  if (!status) return 'badge-default'
  const statusLower = status.toLowerCase()
  if (statusLower === 'new') return 'badge-info'
  if (statusLower === 'triggered') return 'badge-warning'
  if (statusLower === 'executed') return 'badge-success'
  if (statusLower === 'cancelled') return 'badge-secondary'
  if (statusLower === 'failed') return 'badge-danger'
  return 'badge-default'
}

// 监听标签切换，动态重新加载数据
watch(activeTab, async (newTab, oldTab) => {
  // 只在选中模型时加载数据
  if (!currentModelId.value) {
    return
  }
  
  // 避免初始化时触发（oldTab 为 undefined 时是初始化）
  if (oldTab === undefined) {
    return
  }
  
  // 根据切换到的标签加载对应的数据
  try {
    console.log(`[App] activeTab changed: ${oldTab} -> ${newTab}`)
    if (newTab === 'positions') {
      console.log(`[App] Loading positions data...`)
      await loadPositions()
    } else if (newTab === 'trades') {
      console.log(`[App] Loading trades data...`)
      await loadTrades()
    } else if (newTab === 'algo-orders') {
      console.log(`[App] Loading algo orders data...`)
      await loadAlgoOrders()
    } else if (newTab === 'conversations') {
      // 根据模型的trade_type决定加载对话还是策略决策
      const currentModelData = currentModel.value
      const tradeType = currentModelData?.trade_type || currentModelData?.tradeType || 'ai'
      console.log(`[App] ========== 切换到conversations标签 ==========`)
      console.log(`[App] trade_type: ${tradeType}`)
      console.log(`[App] currentModelData:`, currentModelData)
      
      if (tradeType === 'strategy') {
        console.log(`[App] trade_type is 'strategy', calling loadStrategyDecisions()...`)
        await loadStrategyDecisions()
        console.log(`[App] loadStrategyDecisions() completed`)
      } else {
        console.log(`[App] trade_type is 'ai', calling loadConversations()...`)
        await loadConversations()
        console.log(`[App] loadConversations() completed`)
      }
    }
  } catch (error) {
    console.error(`[App] Error loading ${newTab} data:`, error)
  }
})

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

// 处理时间范围变化
const handleTimeRangeChange = async () => {
  if (currentModelId.value) {
    await loadAccountValueHistory()
  }
}

const handleSaveLeverage = async () => {
  if (!pendingLeverageModelId.value) return
  if (isNaN(tempLeverage.value) || tempLeverage.value < 0 || tempLeverage.value > 125) {
    alert('请输入有效的杠杆（0-125，0 表示由 AI 自行决定）')
    return
  }
  await saveModelLeverage(tempLeverage.value)
}

const handleOpenMaxPositionsModal = (modelId, modelName) => {
  openMaxPositionsModal(modelId, modelName)
}

const handleSaveMaxPositions = async () => {
  await saveModelMaxPositions()
}

const handleOpenModelSettingsModal = (modelId, modelName) => {
  openModelSettingsModal(modelId, modelName)
}

const handleSaveModelSettings = async () => {
  await saveModelSettings()
}

const handleDeleteModel = (modelId, modelName) => {
  openDeleteModelConfirm(modelId, modelName)
}

const handleOpenStrategyConfigModal = (modelId, modelName) => {
  openStrategyConfigModal(modelId, modelName)
}

const handleOpenTradeLogsModal = (modelId, modelName) => {
  showTradeLogsModal.value = true
  pendingTradeLogsModelId.value = modelId
  tradeLogsModelName.value = modelName
}

const handleOpenTradeContainerLogsModal = () => {
  showTradeLogsModal.value = true
  pendingTradeLogsModelId.value = null // null表示trade容器
  tradeLogsModelName.value = '交易容器'
}

const handleOpenBuyLogsModal = (modelId, modelName) => {
  showBuyLogsModal.value = true
  pendingBuyLogsModelId.value = modelId
  buyLogsModelName.value = modelName
}

const handleOpenSellLogsModal = (modelId, modelName) => {
  showSellLogsModal.value = true
  pendingSellLogsModelId.value = modelId
  sellLogsModelName.value = modelName
}

const handleOpenAnalysisModal = () => {
  showAnalysisModal.value = true
}

const openKlineChartFromMarket = (symbol, contractSymbol) => {
  const finalSymbol = contractSymbol || symbol
  openKlineChart(finalSymbol)
}

// 辅助函数：获取symbol的价格数据
const getSymbolPrice = (symbol) => {
  // 优先从模型持仓数据中获取价格
  const portfolioData = modelPortfolioSymbols.value.find(item => item.symbol === symbol)
  if (portfolioData) return portfolioData.price || 0
  
  // 如果模型持仓数据中没有，再从市场价格数据中获取
  const priceData = marketPrices.value.find(item => item.symbol === symbol)
  return priceData ? priceData.price : 0
}

// 辅助函数：获取symbol的涨跌幅百分比
const getSymbolChangePercent = (symbol) => {
  // 优先从模型持仓数据中获取涨跌幅
  const portfolioData = modelPortfolioSymbols.value.find(item => item.symbol === symbol)
  if (portfolioData) return portfolioData.changePercent || portfolioData.change || 0
  
  // 如果模型持仓数据中没有，再从市场价格数据中获取
  const priceData = marketPrices.value.find(item => item.symbol === symbol)
  return priceData ? (priceData.change_percent || priceData.change || 0) : 0
}

// 辅助函数：获取symbol的涨跌幅箭头
const getSymbolChangeArrow = (symbol) => {
  const changePercent = getSymbolChangePercent(symbol)
  return changePercent >= 0 ? '▲' : '▼'
}

// 辅助函数：获取symbol的涨跌幅样式类
const getSymbolChangeClass = (symbol) => {
  const changePercent = getSymbolChangePercent(symbol)
  return changePercent >= 0 ? 'positive' : 'negative'
}

// 辅助函数：获取symbol的成交量
const getSymbolVolume = (symbol) => {
  // 优先从模型持仓数据中获取成交量
  const portfolioData = modelPortfolioSymbols.value.find(item => item.symbol === symbol)
  if (portfolioData) return portfolioData.quoteVolume || portfolioData.volume || 0
  
  // 如果模型持仓数据中没有，再从市场价格数据中获取
  const priceData = marketPrices.value.find(item => item.symbol === symbol)
  return priceData ? (priceData.daily_volume || priceData.quote_volume || 0) : 0
}

onMounted(() => {
  initApp()
})
</script>

