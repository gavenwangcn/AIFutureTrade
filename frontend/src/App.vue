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
          <button class="btn-secondary" @click="handleStrategyConfigClick" title="配置当前模型的买卖提示词">
            <i class="bi bi-sliders"></i>
            策略配置
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
        <section v-if="!currentModelId || isAggregatedView" class="hero-banner glass-panel">
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
                  <div v-if="item.quote_volume" class="leaderboard-volume">
                    <span class="volume-label">成交额</span>
                    <span class="volume-value">${{ formatVolumeChinese(item.quote_volume) }}</span>
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

        <!-- Model Portfolio Symbols -->
        <div v-show="!isAggregatedView" class="content-card">
          <div class="card-header">
            <h3 class="card-title" title="展示该模型持仓合约的实时数据走势">
              {{ getModelDisplayName(currentModelId) }} - 
              <span style="font-weight: bold;">
                <i class="bi bi-bar-chart-line"></i> 持仓合约实时行情
              </span>
            </h3>
            <span class="last-refresh-time" title="持仓合约数据最后刷新时间">
              最后刷新: {{ formatTime(lastPortfolioSymbolsRefreshTime) }}
            </span>
          </div>
          <div class="card-body">
            <div v-if="modelPortfolioSymbols.length > 0" class="model-portfolio-symbols-grid">
              <div 
                v-for="(item, index) in modelPortfolioSymbols" 
                :key="item.symbol"
                class="model-portfolio-symbol-item"
                @click="openKlineChartFromMarket(item.symbol)"
              >
                <div class="price-card">
                    <div class="price-left">
                      <div class="price-symbol-large">{{ item.symbol }}</div>
                      <div class="price-contract-name">{{ item.symbol }}永续合约</div>
                    </div>
                    <div class="price-right">
                      <div class="price-value-large">${{ formatPrice(item.price) }}</div>
                      <div class="price-change-with-arrow" :class="getSymbolChangeClass(item.symbol)">
                        <span class="change-arrow">{{ getSymbolChangeArrow(item.symbol) }}</span>
                        <span class="change-value">{{ item.changePercent.toFixed(2) }}%</span>
                      </div>
                      <div class="price-volume-chinese">
                        <span class="volume-label">当日成交额: </span>
                        <span class="volume-value">{{ formatVolumeChinese(item.quoteVolume) }}</span>
                      </div>
                    </div>
                  </div>
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
                    <td><strong>{{ position.symbol }}</strong></td>
                    <td><span :class="['badge', (position.position_side || '').toLowerCase() === 'long' ? 'badge-long' : 'badge-short']">
                      {{ (position.position_side || '').toLowerCase() === 'long' ? '做多' : '做空' }}
                    </span></td>
                    <td>{{ Math.abs(position.position_amt || 0).toFixed(4) }}</td>
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
                    <td><strong>{{ trade.future || trade.symbol }}</strong></td>
                    <td>
                      <span :class="['badge', getSignalBadgeClass(trade.signal || trade.side)]">
                        {{ formatSignal(trade.signal || trade.side) }}
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
                <div class="conversation-time">{{ formatTime(conv.timestamp || conv.time) }}</div>
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

    <!-- 模态框组件 -->
    <SettingsModal
      :visible="showSettingsModal"
      @update:visible="showSettingsModal = $event"
      @close="handleSettingsModalClose"
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
              <label for="settingsMaxPositionsInput">最大持仓数量 (>= 1)</label>
              <input 
                type="number" 
                id="settingsMaxPositionsInput" 
                class="form-input" 
                min="1" 
                v-model.number="tempModelSettings.max_positions"
              >
              <small class="form-help">设置该模型最多可以同时持有的合约数量，默认为3。</small>
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
import { ref, onMounted } from 'vue'
import KLineChart from './components/KLineChart.vue'
import SettingsModal from './components/SettingsModal.vue'
import StrategyModal from './components/StrategyModal.vue'
import FutureConfigModal from './components/FutureConfigModal.vue'
import ApiProviderModal from './components/ApiProviderModal.vue'
import AccountModal from './components/AccountModal.vue'
import AddModelModal from './components/AddModelModal.vue'
import { useTradingApp } from './composables/useTradingApp'

const {
  currentModelId,
  models,
  isAggregatedView,
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
  portfolio,
  accountValueHistory,
  aggregatedChartData,
  positions,
  trades,
  conversations,
  settings,
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
  initApp,
  handleRefresh,
  toggleLogger,
  handleExecute,
  handlePauseAuto,
  loadGainers,
  loadLosers,
  selectModel,
  showAggregatedView,
  deleteModel,
  handleStrategyConfigClick,
  openLeverageModal,
  saveModelLeverage,
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
  modelPortfolioSymbols,
  lastPortfolioSymbolsRefreshTime,
  loadSettings
} = useTradingApp()

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

