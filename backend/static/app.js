// 前端日志工具类 - 仅输出到浏览器console
class FrontendLogger {
    constructor() {
        // 从localStorage读取日志开关状态，默认为开启
        this.enabled = localStorage.getItem('frontendLoggingEnabled') !== 'false';
        this.updateButtonState();
    }

    /**
     * 开启日志
     */
    enable() {
        this.enabled = true;
        localStorage.setItem('frontendLoggingEnabled', 'true');
        this.updateButtonState();
        console.log('[日志系统] 日志输出已开启');
    }

    /**
     * 关闭日志
     */
    disable() {
        this.enabled = false;
        localStorage.setItem('frontendLoggingEnabled', 'false');
        this.updateButtonState();
        console.log('[日志系统] 日志输出已关闭');
    }

    /**
     * 切换日志状态
     */
    toggle() {
        if (this.enabled) {
            this.disable();
        } else {
            this.enable();
        }
    }

    /**
     * 检查日志是否启用
     * @returns {boolean}
     */
    isEnabled() {
        return this.enabled;
    }

    /**
     * 更新按钮状态
     */
    updateButtonState() {
        const btn = document.getElementById('logToggleBtn');
        const icon = document.getElementById('logToggleIcon');
        if (btn && icon) {
            if (this.enabled) {
                btn.classList.add('active');
                btn.title = '点击关闭日志输出';
                icon.className = 'bi bi-play-fill'; // 开启状态：前进图标
            } else {
                btn.classList.remove('active');
                btn.title = '点击开启日志输出';
                icon.className = 'bi bi-pause-fill'; // 关闭状态：暂停图标
            }
        }
    }

    /**
     * 格式化时间戳
     */
    formatTimestamp() {
        const now = new Date();
        return now.toLocaleString('zh-CN', { 
            year: 'numeric', 
            month: '2-digit', 
            day: '2-digit',
            hour: '2-digit', 
            minute: '2-digit', 
            second: '2-digit',
            hour12: false 
        });
    }

    /**
     * 记录API调用
     * @param {string} method - HTTP方法
     * @param {string} url - API URL
     * @param {object} options - 请求选项（可选）
     */
    logApiCall(method, url, options = {}) {
        if (!this.enabled) return;
        const timestamp = this.formatTimestamp();
        console.log(`[${timestamp}] [API调用] ${method} ${url}`, options.body ? { body: options.body } : '');
    }

    /**
     * 记录API成功响应
     * @param {string} method - HTTP方法
     * @param {string} url - API URL
     * @param {Response} response - 响应对象
     * @param {object} data - 响应数据（可选）
     */
    logApiSuccess(method, url, response, data = null) {
        if (!this.enabled) return;
        const timestamp = this.formatTimestamp();
        const logData = {
            status: response.status,
            statusText: response.statusText
        };
        if (data) {
            logData.dataSize = JSON.stringify(data).length;
        }
        console.log(`[${timestamp}] [API成功] ${method} ${url}`, logData);
    }

    /**
     * 记录API错误
     * @param {string} method - HTTP方法
     * @param {string} url - API URL
     * @param {Error|object} error - 错误对象
     * @param {Response} response - 响应对象（如果有）
     * @param {object} errorData - 错误响应数据（如果有）
     */
    logApiError(method, url, error, response = null, errorData = null) {
        if (!this.enabled) return;
        const timestamp = this.formatTimestamp();
        const errorInfo = {
            method: method,
            url: url,
            errorType: error.constructor?.name || 'Error',
            errorMessage: error.message || String(error)
        };

        if (response) {
            errorInfo.status = response.status;
            errorInfo.statusText = response.statusText;
        }

        if (errorData) {
            errorInfo.errorData = errorData;
        }

        if (error.stack) {
            errorInfo.stack = error.stack;
        }

        console.error(`[${timestamp}] [API错误] ${method} ${url}`, errorInfo);
    }

    /**
     * 记录数据加载错误
     * @param {string} dataType - 数据类型
     * @param {Error} error - 错误对象
     * @param {string} url - API URL（可选）
     */
    logDataLoadError(dataType, error, url = null) {
        if (!this.enabled) return;
        const timestamp = this.formatTimestamp();
        const errorInfo = {
            dataType: dataType,
            errorMessage: error.message || String(error),
            errorType: error.constructor?.name || 'Error'
        };
        if (url) {
            errorInfo.url = url;
        }
        if (error.stack) {
            errorInfo.stack = error.stack;
        }
        console.error(`[${timestamp}] [数据加载错误] ${dataType}`, errorInfo);
    }

    /**
     * 记录一般信息
     * @param {string} category - 日志分类
     * @param {string} message - 消息
     * @param {object} details - 详细信息（可选）
     */
    logInfo(category, message, details = null) {
        if (!this.enabled) return;
        const timestamp = this.formatTimestamp();
        if (details) {
            console.log(`[${timestamp}] [${category}] ${message}`, details);
        } else {
            console.log(`[${timestamp}] [${category}] ${message}`);
        }
    }

    /**
     * 记录警告信息
     * @param {string} category - 日志分类
     * @param {string} message - 消息
     * @param {object} details - 详细信息（可选）
     */
    logWarn(category, message, details = null) {
        if (!this.enabled) return;
        const timestamp = this.formatTimestamp();
        if (details) {
            console.warn(`[${timestamp}] [${category}] ${message}`, details);
        } else {
            console.warn(`[${timestamp}] [${category}] ${message}`);
        }
    }
}

// 创建全局日志实例
const frontendLogger = new FrontendLogger();

class TradingApp {
    constructor() {
        this.currentModelId = null;
        this.isAggregatedView = false;
        this.currentModelAutoTradingEnabled = true;
        this.currentModelName = '';
        this.modelsCache = [];
        this.currentModelPrompts = null;
        this.chart = null;
        this.refreshIntervals = {
            market: null,
            portfolio: null,
            trades: null
        };
        this.isChinese = this.detectLanguage();
        this.showSystemPrompt = false;
        this.settingsCache = null;
        this.latestConversations = [];
        this.leaderboardLimit = 10;
        this.leaderboardData = { gainers: [], losers: [] };
        this.leaderboardLastUpdated = null;
        this.logger = frontendLogger; // 使用全局日志实例
        this.modelLeverageMap = {};
        this.socket = null; // WebSocket连接
        this.leaderboardRefreshInterval = null; // 定期刷新定时器
        this.clickhouseLeaderboardSyncRunning = true; // ClickHouse 涨幅榜同步状态，默认执行
        this.init();
    }

    init() {
        // 等待DOM加载完成
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                this.setupEventListeners();
                this.initWebSocket();
                this.startLeaderboardAutoRefresh();
            });
        } else {
            this.setupEventListeners();
            this.initWebSocket();
            this.startLeaderboardAutoRefresh();
        }
    }

    initWebSocket() {
        // 检查是否支持WebSocket（通过检查是否有socket.io库）
        if (typeof io === 'undefined') {
            console.warn('[WebSocket] socket.io 未加载，使用轮询方式更新涨跌幅榜');
            return;
        }

        try {
            // 连接到WebSocket服务器
            this.socket = io();
            
            // 监听涨跌幅榜更新事件
            this.socket.on('leaderboard:update', (data) => {
                console.log('[WebSocket] 收到涨跌幅榜更新', data);
                if (data && (data.gainers || data.losers)) {
                    this.leaderboardData = {
                        gainers: Array.isArray(data.gainers) ? data.gainers : [],
                        losers: Array.isArray(data.losers) ? data.losers : []
                    };
                    this.leaderboardLastUpdated = new Date();
                    this.renderLeaderboard();
                    
                    // 更新状态指示器
                    const statusElement = document.getElementById('leaderboardStatus');
                    if (statusElement) {
                        statusElement.textContent = '实时更新';
                        statusElement.className = 'status-indicator success';
                    }
                }
            });

            // 监听错误事件
            this.socket.on('leaderboard:error', (error) => {
                console.error('[WebSocket] 涨跌幅榜更新错误', error);
                const statusElement = document.getElementById('leaderboardStatus');
                if (statusElement) {
                    statusElement.textContent = '更新失败';
                    statusElement.className = 'status-indicator error';
                }
            });

            // 连接成功后请求初始数据
            this.socket.on('connect', () => {
                console.log('[WebSocket] 已连接到服务器');
                this.socket.emit('leaderboard:request', { limit: this.leaderboardLimit });
            });

            // 连接断开时重连
            this.socket.on('disconnect', () => {
                console.warn('[WebSocket] 连接断开，尝试重新连接...');
            });
        } catch (error) {
            console.error('[WebSocket] 初始化失败', error);
        }
    }

    startLeaderboardAutoRefresh() {
        // 清除已有定时器
        if (this.leaderboardRefreshInterval) {
            clearInterval(this.leaderboardRefreshInterval);
        }

        // 立即获取一次数据
        this.fetchLeaderboardSnapshot();

        // 每30秒自动刷新一次（作为WebSocket的备用方案）
        this.leaderboardRefreshInterval = setInterval(() => {
            this.fetchLeaderboardSnapshot();
        }, 30000);

        // 初始化 ClickHouse 涨幅榜同步状态
        this.updateClickhouseLeaderboardSyncStatus();
        // 定期更新状态（每10秒）
        setInterval(() => {
            this.updateClickhouseLeaderboardSyncStatus();
        }, 10000);
    }

    async updateClickhouseLeaderboardSyncStatus() {
        try {
            const response = await fetch('/api/clickhouse/leaderboard/status');
            if (response.ok) {
                const data = await response.json();
                this.clickhouseLeaderboardSyncRunning = data.running || false;
                this.renderClickhouseLeaderboardSyncButton();
            }
        } catch (error) {
            console.error('[ClickHouse Leaderboard] Failed to get sync status:', error);
        }
    }

    async toggleClickhouseLeaderboardSync() {
        const action = this.clickhouseLeaderboardSyncRunning ? 'stop' : 'start';
        
        try {
            const response = await fetch('/api/clickhouse/leaderboard/control', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ action })
            });

            if (response.ok) {
                const data = await response.json();
                this.clickhouseLeaderboardSyncRunning = data.running;
                this.renderClickhouseLeaderboardSyncButton();
                this.logger.logInfo(
                    'ClickHouse 涨幅榜同步',
                    `已${this.clickhouseLeaderboardSyncRunning ? '启动' : '暂停'}同步`
                );
            } else {
                const error = await response.json();
                this.logger.logApiError('POST', '/api/clickhouse/leaderboard/control', new Error(error.error || '操作失败'), response);
            }
        } catch (error) {
            this.logger.logApiError('POST', '/api/clickhouse/leaderboard/control', error, null);
        }
    }

    renderClickhouseLeaderboardSyncButton() {
        const btn = document.getElementById('clickhouseLeaderboardSyncBtn');
        const icon = document.getElementById('clickhouseLeaderboardSyncIcon');
        const text = document.getElementById('clickhouseLeaderboardSyncText');
        
        if (!btn || !icon || !text) return;

        if (this.clickhouseLeaderboardSyncRunning) {
            // 执行中状态
            icon.className = 'bi bi-pause-circle';
            text.textContent = '执行中';
            btn.title = '点击暂停 ClickHouse 涨幅榜同步';
            btn.classList.remove('btn-paused');
            btn.classList.add('btn-running');
        } else {
            // 暂停状态
            icon.className = 'bi bi-play-circle';
            text.textContent = '已暂停';
            btn.title = '点击启动 ClickHouse 涨幅榜同步';
            btn.classList.remove('btn-running');
            btn.classList.add('btn-paused');
        }
    }

    setupEventListeners() {
        // 刷新按钮
        const refreshBtn = document.getElementById('refreshBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.refresh());
        }

        // 日志切换按钮
        const logToggleBtn = document.getElementById('logToggleBtn');
        if (logToggleBtn) {
            logToggleBtn.addEventListener('click', () => frontendLogger.toggle());
        }

        // 执行交易按钮
        const executeBtn = document.getElementById('executeBtn');
        if (executeBtn) {
            executeBtn.addEventListener('click', () => this.executeTrading());
        }

        // 暂停自动交易按钮
        const pauseAutoBtn = document.getElementById('pauseAutoBtn');
        if (pauseAutoBtn) {
            pauseAutoBtn.addEventListener('click', () => this.toggleAutoTrading());
        }

        // 设置按钮
        const settingsBtn = document.getElementById('settingsBtn');
        if (settingsBtn) {
            settingsBtn.addEventListener('click', () => this.showSettingsModal());
        }

        // 策略配置按钮
        const strategyBtn = document.getElementById('strategyBtn');
        if (strategyBtn) {
            strategyBtn.addEventListener('click', () => this.showStrategyModal());
        }

        // 合约配置按钮
        const futureConfigBtn = document.getElementById('futureConfigBtn');
        if (futureConfigBtn) {
            futureConfigBtn.addEventListener('click', () => this.showFuturesModal());
        }

        // API提供方按钮
        const addApiProviderBtn = document.getElementById('addApiProviderBtn');
        if (addApiProviderBtn) {
            addApiProviderBtn.addEventListener('click', () => this.showApiProviderModal());
        }

        // 添加模型按钮
        const addModelBtn = document.getElementById('addModelBtn');
        if (addModelBtn) {
            addModelBtn.addEventListener('click', () => this.showModal());
        }

        // 涨跌幅榜刷新按钮
        const refreshLeaderboardBtn = document.getElementById('refreshLeaderboardBtn');
        if (refreshLeaderboardBtn) {
            refreshLeaderboardBtn.addEventListener('click', () => this.fetchLeaderboardSnapshot(true));
        }

        // ClickHouse 涨幅榜同步控制按钮
        const clickhouseLeaderboardSyncBtn = document.getElementById('clickhouseLeaderboardSyncBtn');
        if (clickhouseLeaderboardSyncBtn) {
            clickhouseLeaderboardSyncBtn.addEventListener('click', () => this.toggleClickhouseLeaderboardSync());
        }

        // Tab切换
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const tabName = e.target.getAttribute('data-tab');
                if (tabName) {
                    this.switchTab(tabName);
                }
            });
        });

        // 模态框关闭按钮
        const closeModalBtn = document.getElementById('closeModalBtn');
        if (closeModalBtn) {
            closeModalBtn.addEventListener('click', () => this.hideModal());
        }

        const cancelBtn = document.getElementById('cancelBtn');
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => this.hideModal());
        }

        const submitBtn = document.getElementById('submitBtn');
        if (submitBtn) {
            submitBtn.addEventListener('click', () => this.submitModel());
        }

        // 设置模态框
        const closeSettingsModalBtn = document.getElementById('closeSettingsModalBtn');
        if (closeSettingsModalBtn) {
            closeSettingsModalBtn.addEventListener('click', () => this.hideSettingsModal());
        }

        const cancelSettingsBtn = document.getElementById('cancelSettingsBtn');
        if (cancelSettingsBtn) {
            cancelSettingsBtn.addEventListener('click', () => this.hideSettingsModal());
        }

        const saveSettingsBtn = document.getElementById('saveSettingsBtn');
        if (saveSettingsBtn) {
            saveSettingsBtn.addEventListener('click', () => this.saveSettings());
        }

        // 策略模态框
        const closeStrategyModalBtn = document.getElementById('closeStrategyModalBtn');
        if (closeStrategyModalBtn) {
            closeStrategyModalBtn.addEventListener('click', () => this.hideStrategyModal());
        }

        const cancelStrategyBtn = document.getElementById('cancelStrategyBtn');
        if (cancelStrategyBtn) {
            cancelStrategyBtn.addEventListener('click', () => this.hideStrategyModal());
        }

        const saveStrategyBtn = document.getElementById('saveStrategyBtn');
        if (saveStrategyBtn) {
            saveStrategyBtn.addEventListener('click', () => this.saveStrategy());
        }

        // 合约配置模态框
        const closeFutureModalBtn = document.getElementById('closeFutureModalBtn');
        if (closeFutureModalBtn) {
            closeFutureModalBtn.addEventListener('click', () => this.hideFuturesModal());
        }

        const cancelFutureBtn = document.getElementById('cancelFutureBtn');
        if (cancelFutureBtn) {
            cancelFutureBtn.addEventListener('click', () => this.hideFuturesModal());
        }

        const saveFutureBtn = document.getElementById('saveFutureBtn');
        if (saveFutureBtn) {
            saveFutureBtn.addEventListener('click', () => this.saveFuture());
        }

        // API提供方模态框
        const closeApiProviderModalBtn = document.getElementById('closeApiProviderModalBtn');
        if (closeApiProviderModalBtn) {
            closeApiProviderModalBtn.addEventListener('click', () => this.hideApiProviderModal());
        }

        const cancelApiProviderBtn = document.getElementById('cancelApiProviderBtn');
        if (cancelApiProviderBtn) {
            cancelApiProviderBtn.addEventListener('click', () => this.hideApiProviderModal());
        }

        const saveApiProviderBtn = document.getElementById('saveApiProviderBtn');
        if (saveApiProviderBtn) {
            saveApiProviderBtn.addEventListener('click', () => this.saveApiProvider());
        }

        const fetchModelsBtn = document.getElementById('fetchModelsBtn');
        if (fetchModelsBtn) {
            fetchModelsBtn.addEventListener('click', () => this.fetchModels());
        }

        // 模型提供方选择变化
        const modelProvider = document.getElementById('modelProvider');
        if (modelProvider) {
            modelProvider.addEventListener('change', (e) => {
                this.updateModelOptions(e.target.value);
            });
        }

        // 更新模态框
        const closeUpdateModalBtn = document.getElementById('closeUpdateModalBtn');
        if (closeUpdateModalBtn) {
            closeUpdateModalBtn.addEventListener('click', () => this.hideUpdateModal());
        }

        const dismissUpdateBtn = document.getElementById('dismissUpdateBtn');
        if (dismissUpdateBtn) {
            dismissUpdateBtn.addEventListener('click', () => this.dismissUpdate());
        }

        // 点击模态框外部关闭
        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    modal.classList.remove('show');
                }
            });
        });

        // 初始化数据加载
        this.loadModels();
        this.loadMarketPrices();
        this.loadProviders();
        this.startRefreshCycles();
        this.fetchLeaderboardSnapshot();
        this.checkForUpdates(true);
    }

    updateExecuteButtonState() {
        const executeBtn = document.getElementById('executeBtn');
        if (!executeBtn) return;

        if (this.isAggregatedView || !this.currentModelId) {
            executeBtn.disabled = true;
            executeBtn.title = '请选择某个模型后执行';
        } else {
            executeBtn.disabled = false;
            executeBtn.title = '执行当前模型的交易周期';
        }

        this.updateAutoTradingButtonState();
        this.updateStrategyButtonState();
    }

    updateAutoTradingButtonState() {
        const pauseBtn = document.getElementById('pauseAutoBtn');
        if (!pauseBtn) return;

        if (this.isAggregatedView || !this.currentModelId) {
            pauseBtn.disabled = true;
            pauseBtn.title = '请选择对应的交易模型';
            pauseBtn.innerHTML = '<i class="bi bi-pause-circle"></i> 关闭交易';
        } else {
            pauseBtn.disabled = false;
            pauseBtn.title = '暂停该模型的自动化交易';
            pauseBtn.innerHTML = '<i class="bi bi-pause-circle"></i> 关闭交易';
        }
    }

    updateStrategyButtonState() {
        const strategyBtn = document.getElementById('strategyBtn');
        if (!strategyBtn) return;

        if (this.isAggregatedView || !this.currentModelId) {
            strategyBtn.title = '请选择具体模型后配置策略';
        } else {
            strategyBtn.title = '配置当前模型的买入/卖出提示词';
        }
    }

    async loadModels() {
        const url = '/api/models';
        this.logger.logApiCall('GET', url);

        try {
            const response = await fetch(url);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            let models;
            try {
                models = await response.json();
            } catch (parseError) {
                this.logger.logApiError('GET', url, new Error('响应解析失败'), response);
                return;
            }

            this.logger.logApiSuccess('GET', url, response);
            
            this.modelsCache = Array.isArray(models) ? models : [];
            this.modelsCache.forEach(model => {
                this.modelLeverageMap[model.id] = model.leverage ?? 10;
            });
            this.renderModels(models);
            this.updateStrategyButtonState();

            // Initialize with aggregated view if no model is selected
            if (models.length > 0 && !this.currentModelId && !this.isAggregatedView) {
                this.showAggregatedView();
            }
        } catch (error) {
            this.logger.logDataLoadError('模型列表', error, url);
        }
    }

    async selectModel(modelId) {
        this.currentModelId = modelId;
        this.isAggregatedView = false;
        this.currentModelName = this.getModelDisplayName(modelId);
        this.updateStrategyButtonState();
        this.loadModels();
        await this.loadModelData();
        this.showTabsInSingleModelView();
        this.updateExecuteButtonState();
    }

    async loadModelData() {
        if (!this.currentModelId) return;

        const portfolioUrl = `/api/models/${this.currentModelId}/portfolio`;
        const tradesUrl = `/api/models/${this.currentModelId}/trades?limit=50`;
        const conversationsUrl = `/api/models/${this.currentModelId}/conversations?limit=20`;

        this.logger.logApiCall('GET', portfolioUrl);
        this.logger.logApiCall('GET', tradesUrl);
        this.logger.logApiCall('GET', conversationsUrl);

        try {
            const [portfolioResponse, tradesResponse, conversationsResponse] = await Promise.all([
                fetch(portfolioUrl),
                fetch(tradesUrl),
                fetch(conversationsUrl)
            ]);

            // Parse responses with error handling
            let portfolioPayload, trades, conversations;

            try {
                if (portfolioResponse.ok) {
                    portfolioPayload = await portfolioResponse.json();
                    this.logger.logApiSuccess('GET', portfolioUrl, portfolioResponse);
                } else {
                    const errorData = await portfolioResponse.json().catch(() => ({ error: `HTTP ${portfolioResponse.status}` }));
                    this.logger.logApiError('GET', portfolioUrl, new Error(errorData.error || '加载持仓失败'), portfolioResponse, errorData);
                    portfolioPayload = { error: errorData.error || 'Failed to load portfolio' };
                }
            } catch (error) {
                this.logger.logApiError('GET', portfolioUrl, error, portfolioResponse);
                portfolioPayload = { error: error.message };
            }

            try {
                if (tradesResponse.ok) {
                    trades = await tradesResponse.json();
                    this.logger.logApiSuccess('GET', tradesUrl, tradesResponse);
                } else {
                    this.logger.logApiError('GET', tradesUrl, new Error(`HTTP ${tradesResponse.status}`), tradesResponse);
                    trades = [];
                }
            } catch (error) {
                this.logger.logApiError('GET', tradesUrl, error, tradesResponse);
                trades = [];
            }

            try {
                if (conversationsResponse.ok) {
                    conversations = await conversationsResponse.json();
                    this.logger.logApiSuccess('GET', conversationsUrl, conversationsResponse);
                } else {
                    this.logger.logApiError('GET', conversationsUrl, new Error(`HTTP ${conversationsResponse.status}`), conversationsResponse);
                    conversations = [];
                }
            } catch (error) {
                this.logger.logApiError('GET', conversationsUrl, error, conversationsResponse);
                conversations = [];
            }

            // Check for errors in portfolio
            if (portfolioPayload.error) {
                this.logger.logDataLoadError('持仓数据', new Error(portfolioPayload.error), portfolioUrl);
                return;
            }

            const { portfolio, account_value_history, auto_trading_enabled, leverage } = portfolioPayload;

            this.currentModelAutoTradingEnabled = Boolean(auto_trading_enabled);
            this.updateAutoTradingButtonState();

            if (typeof leverage === 'number') {
                this.modelLeverageMap[this.currentModelId] = leverage;
                this.updateModelLeverageDisplay(this.currentModelId, leverage);
            }

            // Check if portfolio data exists
            if (!portfolio) {
                this.logger.logDataLoadError('持仓数据', new Error('持仓数据为空'), portfolioUrl);
                return;
            }

            this.logger.logInfo('数据加载', '成功加载模型数据', {
                modelId: this.currentModelId,
                positionsCount: (portfolio.positions || []).length,
                tradesCount: (trades || []).length,
                conversationsCount: (conversations || []).length
            });

            // 更新模型名称缓存（如果接口返回）
            if (portfolio.model_name) {
                this.currentModelName = portfolio.model_name;
            }

            this.updateStats(portfolio, false);
            this.updateSingleModelChart(account_value_history, portfolio.total_value);
            this.updatePositions(portfolio.positions || [], false);
            this.updateTrades(trades || []);
            this.updateConversations(conversations || []);
        } catch (error) {
            this.logger.logDataLoadError('模型数据', error);
            this.updateAutoTradingButtonState();
        }
    }

    async loadAggregatedData() {
        const url = '/api/aggregated/portfolio';
        this.logger.logApiCall('GET', url);

        try {
            const response = await fetch(url);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            let data;
            try {
                data = await response.json();
            } catch (parseError) {
                this.logger.logApiError('GET', url, new Error('响应解析失败'), response);
                return;
            }

            this.logger.logApiSuccess('GET', url, response, data);
            this.logger.logInfo('数据加载', '成功加载聚合数据', {
                modelCount: data.model_count || 0,
                chartDataPoints: (data.chart_data || []).length
            });

            this.updateStats(data.portfolio, true);
            this.updateMultiModelChart(data.chart_data);
            // Skip positions, trades, and conversations in aggregated view
            this.hideTabsInAggregatedView();
            this.updateAutoTradingButtonState();
        } catch (error) {
            this.logger.logDataLoadError('聚合数据', error, url);
            this.updateAutoTradingButtonState();
        }
    }

    hideTabsInAggregatedView() {
        // Hide the entire tabbed content section in aggregated view
        const contentCard = document.querySelector('.content-card .card-tabs').parentElement;
        if (contentCard) {
            contentCard.style.display = 'none';
        }
    }

    showTabsInSingleModelView() {
        // Show the tabbed content section in single model view
        const contentCard = document.querySelector('.content-card .card-tabs').parentElement;
        if (contentCard) {
            contentCard.style.display = 'block';
        }
    }

    updateStats(portfolio, isAggregated = false) {
        const stats = [
            { value: portfolio.total_value || 0, isPnl: false },
            { value: portfolio.cash || 0, isPnl: false },
            { value: portfolio.realized_pnl || 0, isPnl: true },
            { value: portfolio.unrealized_pnl || 0, isPnl: true }
        ];

        document.querySelectorAll('.stat-value').forEach((el, index) => {
            if (stats[index]) {
                el.textContent = this.formatPnl(stats[index].value, stats[index].isPnl);
                el.className = `stat-value ${this.getPnlClass(stats[index].value, stats[index].isPnl)}`;
            }
        });

        // Update title for aggregated view
        const titleElement = document.querySelector('.account-info h2');
        if (titleElement) {
            if (isAggregated) {
                titleElement.innerHTML = '<i class="bi bi-bar-chart-fill"></i> 聚合账户总览';
            } else {
                titleElement.innerHTML = '<i class="bi bi-wallet2"></i> 账户信息';
            }
        }
    }

    updateSingleModelChart(history, currentValue) {
        const chartDom = document.getElementById('accountChart');

        // Dispose existing chart to avoid state pollution
        if (this.chart) {
            this.chart.dispose();
        }

        this.chart = echarts.init(chartDom);
        window.addEventListener('resize', () => {
            if (this.chart) {
                this.chart.resize();
            }
        });

        const data = history.reverse().map(h => ({
            time: new Date(h.timestamp.replace(' ', 'T') + 'Z').toLocaleTimeString('zh-CN', {
                timeZone: 'Asia/Shanghai',
                hour: '2-digit',
                minute: '2-digit'
            }),
            value: h.total_value
        }));

        if (currentValue !== undefined && currentValue !== null) {
            const now = new Date();
            const currentTime = now.toLocaleTimeString('zh-CN', {
                timeZone: 'Asia/Shanghai',
                hour: '2-digit',
                minute: '2-digit'
            });
            data.push({
                time: currentTime,
                value: currentValue
            });
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
                    const value = params[0].value;
                    return `${params[0].axisValue}<br/>账户价值: $${value.toFixed(2)}`;
                }
            }
        };

        this.chart.setOption(option);

        setTimeout(() => {
            if (this.chart) {
                this.chart.resize();
            }
        }, 100);
    }

    updateMultiModelChart(chartData) {
        const chartDom = document.getElementById('accountChart');

        // Dispose existing chart to avoid state pollution
        if (this.chart) {
            this.chart.dispose();
        }

        this.chart = echarts.init(chartDom);
        window.addEventListener('resize', () => {
            if (this.chart) {
                this.chart.resize();
            }
        });

        if (!chartData || chartData.length === 0) {
            // Show empty state for multi-model chart
            this.chart.setOption({
                title: {
                    text: '暂无模型数据',
                    left: 'center',
                    top: 'center',
                    textStyle: { color: '#86909c', fontSize: 14 }
                },
                xAxis: { show: false },
                yAxis: { show: false },
                series: []
            });
            return;
        }

        // Colors for different models
        const colors = [
            '#3370ff', '#ff6b35', '#00b96b', '#722ed1', '#fa8c16',
            '#eb2f96', '#13c2c2', '#faad14', '#f5222d', '#52c41a'
        ];

        // Prepare time axis - get all timestamps and sort them chronologically
        const allTimestamps = new Set();
        chartData.forEach(model => {
            model.data.forEach(point => {
                allTimestamps.add(point.timestamp);
            });
        });

        // Convert to array and sort by timestamp (not string sort)
        const timeAxis = Array.from(allTimestamps).sort((a, b) => {
            const timeA = new Date(a.replace(' ', 'T') + 'Z').getTime();
            const timeB = new Date(b.replace(' ', 'T') + 'Z').getTime();
            return timeA - timeB;
        });

        // Format time labels for display
        const formattedTimeAxis = timeAxis.map(timestamp => {
            return new Date(timestamp.replace(' ', 'T') + 'Z').toLocaleTimeString('zh-CN', {
                timeZone: 'Asia/Shanghai',
                hour: '2-digit',
                minute: '2-digit'
            });
        });

        // Prepare series data for each model
        const series = chartData.map((model, index) => {
            const color = colors[index % colors.length];

            // Create data points aligned with time axis
            const dataPoints = timeAxis.map(time => {
                const point = model.data.find(p => p.timestamp === time);
                return point ? point.value : null;
            });

            return {
                name: model.model_name,
                type: 'line',
                data: dataPoints,
                smooth: true,
                symbol: 'circle',
                symbolSize: 4,
                lineStyle: { color: color, width: 2 },
                itemStyle: { color: color },
                connectNulls: true  // Connect points even with null values
            };
        });

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
                data: chartData.map(model => model.model_name),
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
                    let result = `${params[0].axisValue}<br/>`;
                    params.forEach(param => {
                        if (param.value !== null) {
                            result += `${param.marker}${param.seriesName}: $${param.value.toFixed(2)}<br/>`;
                        }
                    });
                    return result;
                }
            }
        };

        this.chart.setOption(option);

        setTimeout(() => {
            if (this.chart) {
                this.chart.resize();
            }
        }, 100);
    }

    updatePositions(positions, isAggregated = false) {
        const tbody = document.getElementById('positionsBody');

        if (!Array.isArray(positions) || positions.length === 0) {
            if (isAggregated) {
                tbody.innerHTML = '<tr><td colspan="7" class="empty-state">聚合视图暂无持仓</td></tr>';
            } else {
                tbody.innerHTML = '<tr><td colspan="7" class="empty-state">暂无持仓</td></tr>';
            }
            return;
        }

        tbody.innerHTML = positions.map(pos => {
            const sideClass = pos.side === 'long' ? 'badge-long' : 'badge-short';
            const sideText = pos.side === 'long' ? '做多' : '做空';

            const currentPrice = pos.current_price !== null && pos.current_price !== undefined
                ? `$${pos.current_price.toFixed(2)}`
                : '-';

            let pnlDisplay = '-';
            let pnlClass = '';
            if (pos.pnl !== undefined && pos.pnl !== 0) {
                pnlDisplay = this.formatPnl(pos.pnl, true);
                pnlClass = this.getPnlClass(pos.pnl, true);
            }

            return `
                <tr>
                    <td><strong>${pos.future}</strong></td>
                    <td><span class="badge ${sideClass}">${sideText}</span></td>
                    <td>${pos.quantity.toFixed(4)}</td>
                    <td>$${pos.avg_price.toFixed(2)}</td>
                    <td>${currentPrice}</td>
                    <td>${pos.leverage}x</td>
                    <td class="${pnlClass}"><strong>${pnlDisplay}</strong></td>
                </tr>
            `;
        }).join('');

        // Update positions title for aggregated view
        const positionsTitle = document.querySelector('#positionsTab .card-header h3');
        if (positionsTitle) {
            if (isAggregated) {
                positionsTitle.innerHTML = '<i class="bi bi-collection"></i> 聚合持仓';
            } else {
                positionsTitle.innerHTML = '<i class="bi bi-briefcase"></i> 当前持仓';
            }
        }
    }

    updateTrades(trades) {
        const tbody = document.getElementById('tradesBody');

        if (!Array.isArray(trades) || trades.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">暂无交易记录</td></tr>';
            return;
        }

        tbody.innerHTML = trades.map(trade => {
            const signalMap = {
                'buy_to_enter': { badge: 'badge-buy', text: '开多' },
                'sell_to_enter': { badge: 'badge-sell', text: '开空' },
                'close_position': { badge: 'badge-close', text: '平仓' }
            };
            const signal = signalMap[trade.signal] || { badge: '', text: trade.signal };
            const pnlDisplay = this.formatPnl(trade.pnl, true);
            const pnlClass = this.getPnlClass(trade.pnl, true);

            return `
                <tr>
                    <td>${new Date(trade.timestamp.replace(' ', 'T') + 'Z').toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}</td>
                    <td><strong>${trade.future}</strong></td>
                    <td><span class="badge ${signal.badge}">${signal.text}</span></td>
                    <td>${trade.quantity.toFixed(4)}</td>
                    <td>$${trade.price.toFixed(2)}</td>
                    <td class="${pnlClass}">${pnlDisplay}</td>
                    <td>$${trade.fee.toFixed(2)}</td>
                </tr>
            `;
        }).join('');
    }

    async loadMarketPrices() {
        const url = '/api/market/prices';
        this.logger.logApiCall('GET', url);

        try {
            const response = await fetch(url);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            let prices;
            try {
                prices = await response.json();
            } catch (parseError) {
                this.logger.logApiError('GET', url, new Error('响应解析失败'), response);
                return;
            }

            this.logger.logApiSuccess('GET', url, response, prices);
            this.logger.logInfo('数据加载', `成功加载市场价格，共${Object.keys(prices).length}个合约`, {
                futureCount: Object.keys(prices).length
            });
            
            this.renderMarketPrices(prices);
        } catch (error) {
            this.logger.logDataLoadError('市场价格', error, url);
        }
    }

    renderMarketPrices(prices) {
        const container = document.getElementById('marketPrices');
        
        if (!prices || Object.keys(prices).length === 0) {
            container.innerHTML = '<div class="empty-state">暂无市场行情数据</div>';
            return;
        }

        // 分离配置的合约和持仓的合约
        const configuredItems = [];
        const positionItems = [];
        
        Object.entries(prices).forEach(([symbol, data]) => {
            const item = { symbol, data };
            if (data.source === 'position') {
                positionItems.push(item);
            } else {
                configuredItems.push(item);
            }
        });
        
        // 先渲染价格数据

        // 构建HTML
        let html = '';
        
        // 配置的合约部分
        if (configuredItems.length > 0) {
            html += `
                <div class="market-section">
                    <div class="market-section-header">
                        <span class="section-badge configured">配置合约</span>
                        <span class="section-count">${configuredItems.length} 个</span>
                    </div>
                    ${configuredItems.map(({symbol, data}) => this.buildPriceItem(symbol, data)).join('')}
                </div>
            `;
        }
        
        // 持仓的合约部分
        if (positionItems.length > 0) {
            html += `
                <div class="market-section">
                    <div class="market-section-header">
                        <span class="section-badge position">持仓合约</span>
                        <span class="section-count">${positionItems.length} 个</span>
                    </div>
                    ${positionItems.map(({symbol, data}) => this.buildPriceItem(symbol, data)).join('')}
                </div>
            `;
        }
        
        if (!html) {
            html = '<div class="empty-state">暂无市场行情数据</div>';
        }
        
        container.innerHTML = html;
    }

    buildPriceItem(symbol, data) {
        const changeClass = data.change_24h >= 0 ? 'positive' : 'negative';
        const changeIcon = data.change_24h >= 0 ? '▲' : '▼';

        // 使用中文单位格式化成交额（亿、万），不添加$符号
        const volumeText = data.daily_volume ? this.formatVolumeChinese(data.daily_volume) : '--';

        return `
            <div class="price-item" data-symbol="${symbol}" onclick="app.openKlineChart('${symbol}', '${data.contract_symbol || symbol}USDT')" style="cursor: pointer;">
                <div class="price-head">
                    <div class="price-info">
                        <div class="price-symbol">${symbol}</div>
                        <div class="price-name">${data.name || ''}</div>
                    </div>
                    <div class="price-metrics">
                        <div class="price-value">$${(data.price || 0).toFixed(4)}</div>
                        <div class="price-change ${changeClass}">${changeIcon} ${
                            data.change_24h !== undefined && data.change_24h !== null
                                ? data.change_24h.toFixed(2)
                                : '0.00'
                        }%</div>
                        <div class="price-volume">
                            <span class="volume-label">当日成交额：</span>
                            <span class="volume-value">${volumeText}</span>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    switchTab(tabName) {
        document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

        document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
        document.getElementById(`${tabName}Tab`).classList.add('active');
    }

    // ============ API Provider Management Methods ============
    async showApiProviderModal() {
        this.loadProviders();
        document.getElementById('apiProviderModal').classList.add('show');
    }

    hideApiProviderModal() {
        document.getElementById('apiProviderModal').classList.remove('show');
        this.clearApiProviderForm();
    }

    clearApiProviderForm() {
        document.getElementById('providerName').value = '';
        document.getElementById('providerApiUrl').value = '';
        document.getElementById('providerApiKey').value = '';
        document.getElementById('availableModels').value = '';
    }

    async saveApiProvider() {
        const data = {
            name: document.getElementById('providerName').value.trim(),
            api_url: document.getElementById('providerApiUrl').value.trim(),
            api_key: document.getElementById('providerApiKey').value,
            models: document.getElementById('availableModels').value.trim()
        };

        if (!data.name || !data.api_url || !data.api_key) {
            alert('请填写所有必填字段');
            return;
        }

        const url = '/api/providers';
        this.logger.logApiCall('POST', url, { body: data });

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            let result;
            try {
                result = await response.json();
            } catch (parseError) {
                this.logger.logApiError('POST', url, new Error('响应解析失败'), response);
                alert('响应解析失败，请稍后再试');
                return;
            }

            if (!response.ok) {
                this.logger.logApiError('POST', url, new Error(result.error || `HTTP ${response.status}`), response, result);
                alert(result.error || '保存API提供方失败');
                return;
            }

            this.logger.logApiSuccess('POST', url, response, result);
            this.logger.logInfo('API提供方', 'API提供方保存成功', { providerName: data.name });
            
            this.hideApiProviderModal();
            this.loadProviders();
            alert('API提供方保存成功');
        } catch (error) {
            this.logger.logApiError('POST', url, error);
            alert('保存API提供方失败');
        }
    }

    async fetchModels() {
        const apiUrl = document.getElementById('providerApiUrl').value.trim();
        const apiKey = document.getElementById('providerApiKey').value;

        if (!apiUrl || !apiKey) {
            alert('请先填写API地址和密钥');
            return;
        }

        const fetchBtn = document.getElementById('fetchModelsBtn');
        const originalText = fetchBtn.innerHTML;
        fetchBtn.innerHTML = '<i class="bi bi-arrow-clockwise spin"></i> 获取中...';
        fetchBtn.disabled = true;

        const url = '/api/providers/models';
        this.logger.logApiCall('POST', url, { body: { api_url: apiUrl } });

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ api_url: apiUrl, api_key: apiKey })
            });

            let data;
            try {
                data = await response.json();
            } catch (parseError) {
                this.logger.logApiError('POST', url, new Error('响应解析失败'), response);
                alert('响应解析失败，请稍后再试');
                return;
            }

            if (!response.ok) {
                this.logger.logApiError('POST', url, new Error(data.error || `HTTP ${response.status}`), response, data);
                alert(data.error || '获取模型列表失败，请检查API地址和密钥');
                return;
            }

            this.logger.logApiSuccess('POST', url, response, data);

            if (data.models && data.models.length > 0) {
                this.logger.logInfo('模型获取', `成功获取${data.models.length}个模型`, { 
                    modelCount: data.models.length,
                    apiUrl: apiUrl 
                });
                document.getElementById('availableModels').value = data.models.join(', ');
                alert(`成功获取 ${data.models.length} 个模型`);
            } else {
                this.logger.logWarn('模型获取', '未获取到模型列表', { apiUrl: apiUrl });
                alert('未获取到模型列表，请手动输入');
            }
        } catch (error) {
            this.logger.logApiError('POST', url, error);
            alert('获取模型列表失败');
        } finally {
            fetchBtn.innerHTML = originalText;
            fetchBtn.disabled = false;
        }
    }

    async loadProviders() {
        const url = '/api/providers';
        this.logger.logApiCall('GET', url);

        try {
            const response = await fetch(url);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            let providers;
            try {
                providers = await response.json();
            } catch (parseError) {
                this.logger.logApiError('GET', url, new Error('响应解析失败'), response);
                return;
            }

            this.logger.logApiSuccess('GET', url, response, providers);
            this.logger.logInfo('数据加载', `成功加载${providers.length}个API提供方`, { count: providers.length });
            
            this.providers = providers;
            this.renderProviders(providers);
            this.updateModelProviderSelect(providers);
        } catch (error) {
            this.logger.logDataLoadError('API提供方列表', error, url);
        }
    }

    renderProviders(providers) {
        const container = document.getElementById('providerList');

        if (providers.length === 0) {
            container.innerHTML = '<div class="empty-state">暂无API提供方</div>';
            return;
        }

        container.innerHTML = providers.map(provider => {
            const models = provider.models ? provider.models.split(',').map(m => m.trim()) : [];
            const modelsHtml = models.map(model => `<span class="model-tag">${model}</span>`).join('');

            return `
                <div class="provider-item">
                    <div class="provider-info">
                        <div class="provider-name">${provider.name}</div>
                        <div class="provider-url">${provider.api_url}</div>
                        <div class="provider-models">${modelsHtml}</div>
                    </div>
                    <div class="provider-actions">
                        <span class="provider-delete" onclick="app.deleteProvider(${provider.id})" title="删除">
                            <i class="bi bi-trash"></i>
                        </span>
                    </div>
                </div>
            `;
        }).join('');
    }

    updateModelProviderSelect(providers) {
        const select = document.getElementById('modelProvider');
        const currentValue = select.value;

        select.innerHTML = '<option value="">请选择API提供方</option>';
        providers.forEach(provider => {
            const option = document.createElement('option');
            option.value = provider.id;
            option.textContent = provider.name;
            select.appendChild(option);
        });

        // Restore previous selection if still exists
        if (currentValue && providers.find(p => p.id == currentValue)) {
            select.value = currentValue;
            this.updateModelOptions(currentValue);
        }
    }

    updateModelOptions(providerId) {
        const modelSelect = document.getElementById('modelIdentifier');
        const providerSelect = document.getElementById('modelProvider');

        if (!providerId) {
            modelSelect.innerHTML = '<option value="">请选择API提供方</option>';
            return;
        }

        // Find the selected provider
        const provider = this.providers?.find(p => p.id == providerId);
        if (!provider || !provider.models) {
            modelSelect.innerHTML = '<option value="">该提供方暂无模型</option>';
            return;
        }

        const models = provider.models.split(',').map(m => m.trim()).filter(m => m);
        modelSelect.innerHTML = '<option value="">请选择模型</option>';
        models.forEach(model => {
            const option = document.createElement('option');
            option.value = model;
            option.textContent = model;
            modelSelect.appendChild(option);
        });
    }

    async deleteProvider(providerId) {
        if (!confirm('确定要删除这个API提供方吗？')) return;

        const url = `/api/providers/${providerId}`;
        this.logger.logApiCall('DELETE', url);

        try {
            const response = await fetch(url, {
                method: 'DELETE'
            });

            let result;
            try {
                result = await response.json().catch(() => ({}));
            } catch (parseError) {
                // DELETE可能没有响应体，忽略解析错误
            }

            if (!response.ok) {
                this.logger.logApiError('DELETE', url, new Error(result.error || `HTTP ${response.status}`), response, result);
                alert(result.error || '删除API提供方失败');
                return;
            }

            this.logger.logApiSuccess('DELETE', url, response);
            this.logger.logInfo('API提供方', 'API提供方删除成功', { providerId: providerId });

            if (this.currentModelId === providerId) {
                this.currentModelId = null;
                this.showAggregatedView();
            } else {
                this.loadProviders();
            }
        } catch (error) {
            this.logger.logApiError('DELETE', url, error);
            alert('删除API提供方失败');
        }
    }

    // ============ Model Management Methods ============

    showModal() {
        this.loadProviders().then(() => {
            document.getElementById('addModelModal').classList.add('show');
        });
    }

    hideModal() {
        document.getElementById('addModelModal').classList.remove('show');
    }

    async submitModel() {
        const providerId = document.getElementById('modelProvider').value;
        const modelName = document.getElementById('modelIdentifier').value;
        const displayName = document.getElementById('modelName').value.trim();
        const initialCapital = parseFloat(document.getElementById('initialCapital').value);
        // 杠杆字段可能不存在，使用默认值10
        const leverageInput = document.getElementById('modelLeverage');
        const leverage = leverageInput ? parseInt(leverageInput.value, 10) : 10;

        if (!providerId || !modelName || !displayName || Number.isNaN(initialCapital)) {
            alert('请填写所有必填字段');
            return;
        }

        if (Number.isNaN(leverage) || leverage < 0 || leverage > 125) {
            alert('请输入有效的杠杆（0-125，0 表示由 AI 自行决定）');
            return;
        }

        const url = '/api/models';
        const requestData = {
            provider_id: providerId,
            model_name: modelName,
            name: displayName,
            initial_capital: initialCapital,
            leverage: leverage
        };
        this.logger.logApiCall('POST', url, { body: requestData });

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestData)
            });

            let result;
            try {
                result = await response.json();
            } catch (parseError) {
                this.logger.logApiError('POST', url, new Error('响应解析失败'), response);
                alert('响应解析失败，请稍后再试');
                return;
            }

            if (!response.ok) {
                this.logger.logApiError('POST', url, new Error(result.error || `HTTP ${response.status}`), response, result);
                alert(result.error || '添加模型失败');
                return;
            }

            this.logger.logApiSuccess('POST', url, response, result);
            this.logger.logInfo('模型管理', '模型添加成功', { 
                modelId: result.id,
                modelName: displayName 
            });

            this.hideModal();
            this.loadModels();
            this.clearForm();
        } catch (error) {
            this.logger.logApiError('POST', url, error);
            alert('添加模型失败');
        }
    }

    openLeverageModal(modelId, modelName) {
        this.pendingLeverageModelId = modelId;
        document.getElementById('leverageModelName').textContent = modelName || `模型 #${modelId}`;
        const leverageInput = document.getElementById('leverageInput');
        leverageInput.value = this.modelLeverageMap[modelId] ?? 10;
        document.getElementById('leverageModal').classList.add('show');
    }

    closeLeverageModal() {
        this.pendingLeverageModelId = null;
        document.getElementById('leverageModal').classList.remove('show');
    }

    async saveModelLeverage() {
        if (!this.pendingLeverageModelId) return;
        const leverageInput = document.getElementById('leverageInput');
        const leverage = parseInt(leverageInput.value, 10);
        if (Number.isNaN(leverage) || leverage < 0 || leverage > 125) {
            alert('请输入有效的杠杆（0-125，0 表示由 AI 自行决定）');
            return;
        }

        const modelId = this.pendingLeverageModelId;
        const url = `/api/models/${modelId}/leverage`;
        const payload = { leverage };
        this.logger.logApiCall('POST', url, { body: payload });

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const result = await response.json();
            if (!response.ok) {
                this.logger.logApiError('POST', url, new Error(result.error || `HTTP ${response.status}`), response, result);
                alert(result.error || '更新杠杆失败');
                return;
            }

            this.logger.logApiSuccess('POST', url, response, result);
            this.modelLeverageMap[modelId] = leverage;
            this.updateModelLeverageDisplay(modelId, leverage);
            this.closeLeverageModal();
            alert('杠杆设置已保存');
        } catch (error) {
            this.logger.logApiError('POST', url, error);
            alert('更新杠杆失败');
        }
    }

    updateModelLeverageDisplay(modelId, leverage) {
        const badge = document.querySelector(`[data-model-id="${modelId}"] .model-leverage`);
        if (badge) {
            badge.textContent = leverage === 0 ? '杠杆: AI' : `杠杆: ${leverage}x`;
        }
    }

    async deleteModel(modelId) {
        if (!confirm('确定要删除这个模型吗？')) return;

        const url = `/api/models/${modelId}`;
        this.logger.logApiCall('DELETE', url);

        try {
            const response = await fetch(url, {
                method: 'DELETE'
            });

            let result;
            try {
                result = await response.json().catch(() => ({}));
            } catch (parseError) {
                // DELETE可能没有响应体，忽略解析错误
            }

            if (!response.ok) {
                this.logger.logApiError('DELETE', url, new Error(result.error || `HTTP ${response.status}`), response, result);
                alert(result.error || '删除模型失败');
                return;
            }

            this.logger.logApiSuccess('DELETE', url, response);
            this.logger.logInfo('模型管理', '模型删除成功', { modelId: modelId });

            if (this.currentModelId === modelId) {
                this.currentModelId = null;
                this.showAggregatedView();
            } else {
                this.loadModels();
            }
        } catch (error) {
            this.logger.logApiError('DELETE', url, error);
            alert('删除模型失败');
        }
    }

    clearForm() {
        document.getElementById('modelProvider').value = '';
        document.getElementById('modelIdentifier').value = '';
        document.getElementById('modelName').value = '';
        document.getElementById('initialCapital').value = '100000';
        const leverageInput = document.getElementById('modelLeverage');
        if (leverageInput) {
            leverageInput.value = '10';
        }
    }

    async refresh() {
        // 添加旋转动画
        const refreshIcon = document.getElementById('refreshIcon');
        if (refreshIcon) {
            refreshIcon.style.animation = 'spin 0.6s ease-in-out';
            setTimeout(() => {
                refreshIcon.style.animation = '';
            }, 600);
        }

        await Promise.all([
            this.loadModels(),
            this.loadMarketPrices(),
            this.isAggregatedView ? this.loadAggregatedData() : this.loadModelData(),
            this.fetchLeaderboardSnapshot(true)
        ]);
    }

    startRefreshCycles() {
        this.refreshIntervals.market = setInterval(() => {
            this.loadMarketPrices();
        }, 5000);

        this.refreshIntervals.portfolio = setInterval(() => {
            if (this.isAggregatedView || this.currentModelId) {
                if (this.isAggregatedView) {
                    this.loadAggregatedData();
                } else {
                    this.loadModelData();
                }
            }
        }, 10000);
    }


    // ============ Settings Management Methods ============

    async showSettingsModal() {
        const url = '/api/settings';
        this.logger.logApiCall('GET', url);

        try {
            const response = await fetch(url);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            let settings;
            try {
                settings = await response.json();
            } catch (parseError) {
                this.logger.logApiError('GET', url, new Error('响应解析失败'), response);
                alert('响应解析失败，请稍后再试');
                return;
            }

            this.logger.logApiSuccess('GET', url, response);

            document.getElementById('tradingFrequency').value = settings.trading_frequency_minutes;
            document.getElementById('tradingFeeRate').value = settings.trading_fee_rate;
            const toggle = document.getElementById('showSystemPrompt');
            if (toggle) {
                toggle.checked = Boolean(settings.show_system_prompt);
            }

            document.getElementById('settingsModal').classList.add('show');
        } catch (error) {
            this.logger.logDataLoadError('设置', error, url);
            alert('加载设置失败');
        }
    }
    hideSettingsModal() {
        document.getElementById('settingsModal').classList.remove('show');
    }

    // ============ Futures Configuration Methods ============

    showFuturesModal() {
        this.hideFutureError();
        this.loadFutures();
        document.getElementById('futureConfigModal').classList.add('show');
    }

    hideFuturesModal() {
        document.getElementById('futureConfigModal').classList.remove('show');
        this.clearFutureForm();
    }

    clearFutureForm() {
        this.hideFutureError();
        document.getElementById('futureSymbol').value = '';
        document.getElementById('futureContractSymbol').value = '';
        document.getElementById('futureName').value = '';
        document.getElementById('futureExchange').value = 'BINANCE_FUTURES';
        document.getElementById('futureLink').value = '';
        document.getElementById('futureSortOrder').value = '';
    }

    showFutureError(message) {
        const errorBox = document.getElementById('futureError');
        if (!errorBox) return;
        errorBox.textContent = message;
        errorBox.style.display = 'block';
    }

    hideFutureError() {
        const errorBox = document.getElementById('futureError');
        if (!errorBox) return;
        errorBox.textContent = '';
        errorBox.style.display = 'none';
    }

    async loadFutures() {
        const url = '/api/futures';
        this.logger.logApiCall('GET', url);

        try {
            const response = await fetch(url);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            let futures;
            try {
                futures = await response.json();
            } catch (parseError) {
                this.logger.logApiError('GET', url, new Error('响应解析失败'), response);
                this.showFutureError('响应解析失败，请稍后再试');
                return;
            }

            this.logger.logApiSuccess('GET', url, response, futures);
            this.logger.logInfo('数据加载', `成功加载${futures.length}个合约配置`, { count: futures.length });
            
            this.renderFutures(futures);
        } catch (error) {
            this.logger.logDataLoadError('合约配置', error, url);
            this.showFutureError('加载合约配置失败，请稍后再试');
        }
    }

    renderFutures(futures) {
        const container = document.getElementById('futureList');
        if (!futures || futures.length === 0) {
            container.innerHTML = '<div class="empty-state">暂无合约配置</div>';
            return;
        }

        container.innerHTML = futures.map(future => `
            <div class="provider-item">
                <div class="provider-info">
                    <div class="provider-name">${future.symbol} / ${future.contract_symbol} - ${future.name}</div>
                    <div class="provider-url">${future.exchange}${future.link ? ` · <a href="${future.link}" target="_blank">合约介绍</a>` : ''}</div>
                    <div class="provider-meta">排序: ${future.sort_order || 0}</div>
                </div>
                <div class="provider-actions">
                    <span class="provider-delete" onclick="app.deleteFuture(${future.id})" title="删除">
                        <i class="bi bi-trash"></i>
                    </span>
                </div>
            </div>
        `).join('');
    }

    async saveFuture() {
        this.hideFutureError();
        const data = {
            symbol: document.getElementById('futureSymbol').value.trim().toUpperCase(),
            contract_symbol: document.getElementById('futureContractSymbol').value.trim().toUpperCase(),
            name: document.getElementById('futureName').value.trim(),
            exchange: document.getElementById('futureExchange').value.trim().toUpperCase() || 'BINANCE_FUTURES',
            link: document.getElementById('futureLink').value.trim(),
            sort_order: document.getElementById('futureSortOrder').value.trim()
        };

        if (!data.symbol || !data.contract_symbol || !data.name) {
            this.showFutureError('请填写币种简称、合约代码与名称');
            return;
        }

        if (data.sort_order) {
            const parsed = parseInt(data.sort_order, 10);
            if (Number.isNaN(parsed)) {
                this.showFutureError('排序No需要为数字');
                return;
            }
            data.sort_order = parsed;
        } else {
            delete data.sort_order;
        }

        const url = '/api/futures';
        this.logger.logApiCall('POST', url, { body: data });

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            let result;
            try {
                result = await response.json();
            } catch (parseError) {
                this.logger.logApiError('POST', url, new Error('响应解析失败'), response);
                this.showFutureError('响应解析失败，请稍后再试');
                return;
            }

            if (!response.ok) {
                this.logger.logApiError('POST', url, new Error(result.error || `HTTP ${response.status}`), response, result);
                this.showFutureError(result.error || '保存合约失败');
                return;
            }

            this.logger.logApiSuccess('POST', url, response, result);
            this.logger.logInfo('合约配置', '合约保存成功', { 
                futureId: result.id,
                symbol: data.symbol 
            });

            this.clearFutureForm();
            this.loadFutures();
            this.refresh();
            this.hideFuturesModal();
            alert('合约保存成功');
        } catch (error) {
            this.logger.logApiError('POST', url, error);
            this.showFutureError(error.message || '保存合约失败');
        }
    }

    async deleteFuture(futureId) {
        if (!confirm('确定要删除该合约吗？')) return;

        const url = `/api/futures/${futureId}`;
        this.logger.logApiCall('DELETE', url);

        try {
            const response = await fetch(url, {
                method: 'DELETE'
            });

            let result;
            try {
                result = await response.json().catch(() => ({}));
            } catch (parseError) {
                // DELETE可能没有响应体，忽略解析错误
            }

            if (!response.ok) {
                this.logger.logApiError('DELETE', url, new Error(result.error || `HTTP ${response.status}`), response, result);
                alert(result.error || '删除合约失败');
                return;
            }

            this.logger.logApiSuccess('DELETE', url, response);
            this.logger.logInfo('合约配置', '合约删除成功', { futureId: futureId });

            this.loadFutures();
            this.refresh();
        } catch (error) {
            this.logger.logApiError('DELETE', url, error);
            alert('删除合约失败');
        }
    }

    async saveSettings() {
        const tradingFrequency = parseInt(document.getElementById('tradingFrequency').value);
        const tradingFeeRate = parseFloat(document.getElementById('tradingFeeRate').value);
        const showSystemPrompt = document.getElementById('showSystemPrompt').checked;

        if (!tradingFrequency || tradingFrequency < 1 || tradingFrequency > 1440) {
            alert('请输入有效的交易频率（1-1440分钟）');
            return;
        }

        if (tradingFeeRate < 0 || tradingFeeRate > 0.01) {
            alert('请输入有效的交易费率（0-0.01）');
            return;
        }

        const url = '/api/settings';
        const requestData = {
            trading_frequency_minutes: tradingFrequency,
            trading_fee_rate: tradingFeeRate,
            show_system_prompt: showSystemPrompt
        };
        this.logger.logApiCall('PUT', url, { body: requestData });

        try {
            const response = await fetch(url, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestData)
            });

            let result;
            try {
                result = await response.json();
            } catch (parseError) {
                this.logger.logApiError('PUT', url, new Error('响应解析失败'), response);
                alert('响应解析失败，请稍后再试');
                return;
            }

            if (!response.ok) {
                this.logger.logApiError('PUT', url, new Error(result.error || `HTTP ${response.status}`), response, result);
                alert(result.error || '保存设置失败');
                return;
            }

            this.logger.logApiSuccess('PUT', url, response, result);
            this.logger.logInfo('设置', '设置保存成功', requestData);

            this.hideSettingsModal();
            this.showSystemPrompt = showSystemPrompt;
            this.loadSettingsCache();
            alert('设置保存成功');
        } catch (error) {
            this.logger.logApiError('PUT', url, error);
            alert('保存设置失败');
        }
    }

    // ============ Update Check Methods ============

    async checkForUpdates(silent = false) {
        const url = '/api/check-update';
        this.logger.logApiCall('GET', url);

        try {
            const response = await fetch(url);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            let data;
            try {
                data = await response.json();
            } catch (parseError) {
                this.logger.logApiError('GET', url, new Error('响应解析失败'), response);
                if (!silent) {
                    alert('检查更新失败，请稍后重试');
                }
                return;
            }

            this.logger.logApiSuccess('GET', url, response, data);

            if (data.update_available) {
                this.logger.logInfo('更新检查', '发现新版本', { 
                    currentVersion: data.current_version,
                    latestVersion: data.latest_version 
                });
                this.showUpdateModal(data);
                this.showUpdateIndicator();
            } else if (!silent) {
                if (data.error) {
                    this.logger.logWarn('更新检查', `更新检查失败: ${data.error}`);
                } else {
                    this.logger.logInfo('更新检查', '已是最新版本');
                    // Already on latest version
                    this.showUpdateIndicator(true);
                    setTimeout(() => this.hideUpdateIndicator(), 2000);
                }
            }
        } catch (error) {
            this.logger.logApiError('GET', url, error);
            if (!silent) {
                alert('检查更新失败，请稍后重试');
            }
        }
    }

    showUpdateModal(data) {
        const modal = document.getElementById('updateModal');
        const currentVersion = document.getElementById('currentVersion');
        const latestVersion = document.getElementById('latestVersion');
        const releaseNotes = document.getElementById('releaseNotes');
        const githubLink = document.getElementById('githubLink');

        if (currentVersion) currentVersion.textContent = `v${data.current_version}`;
        if (latestVersion) latestVersion.textContent = `v${data.latest_version}`;
        if (githubLink) githubLink.href = data.release_url || data.repo_url;

        // Format release notes
        if (data.release_notes) {
            releaseNotes.innerHTML = this.formatReleaseNotes(data.release_notes);
        } else {
            releaseNotes.innerHTML = '<p>暂无更新说明</p>';
        }

        modal.classList.add('show');
    }

    hideUpdateModal() {
        document.getElementById('updateModal').classList.remove('show');
    }

    dismissUpdate() {
        this.hideUpdateModal();
        // Hide indicator temporarily, check again in 24 hours
        this.hideUpdateIndicator();

        // Store dismissal timestamp in localStorage
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        localStorage.setItem('updateDismissedUntil', tomorrow.getTime().toString());
    }

    formatReleaseNotes(notes) {
        // Simple markdown-like formatting
        let formatted = notes
            .replace(/### (.*)/g, '<h3>$1</h3>')
            .replace(/## (.*)/g, '<h2>$1</h2>')
            .replace(/# (.*)/g, '<h1>$1</h1>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
            .replace(/^-\s+(.*)/gm, '<li>$1</li>')
            .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
            .replace(/\n\n/g, '</p><p>')
            .replace(/^(.*)/, '<p>$1')
            .replace(/(.*)$/, '$1</p>');

        // Clean up extra <p> tags around block elements
        formatted = formatted.replace(/<p>(<h\d+>.*<\/h\d+>)<\/p>/g, '$1');
        formatted = formatted.replace(/<p>(<ul>.*<\/ul>)<\/p>/g, '$1');

        return formatted;
    }

    showUpdateIndicator() {
        const indicator = document.getElementById('updateIndicator');
        // Check if dismissed recently
        const dismissedUntil = localStorage.getItem('updateDismissedUntil');
        if (dismissedUntil && Date.now() < parseInt(dismissedUntil)) {
            return;
        }
        indicator.style.display = 'block';
    }

    hideUpdateIndicator() {
        const indicator = document.getElementById('updateIndicator');
        indicator.style.display = 'none';
    }

    // ============ Trading Execution Methods ============

    async executeTrading() {
        if (!this.currentModelId || this.isAggregatedView) {
            alert('请先选择一个模型');
            return;
        }

        const url = `/api/models/${this.currentModelId}/execute`;
        this.logger.logApiCall('POST', url);

        const executeBtn = document.getElementById('executeBtn');
        const originalText = executeBtn.innerHTML;
        executeBtn.disabled = true;
        executeBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> 执行中...';

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            let result;
            try {
                result = await response.json();
            } catch (parseError) {
                this.logger.logApiError('POST', url, new Error('响应解析失败'), response);
                alert('响应解析失败，请稍后再试');
                return;
            }

            if (!response.ok) {
                this.logger.logApiError('POST', url, new Error(result.error || `HTTP ${response.status}`), response, result);
                alert(result.error || '执行交易失败');
                return;
            }

            this.logger.logApiSuccess('POST', url, response, result);
            this.logger.logInfo('交易执行', '交易周期执行成功', { modelId: this.currentModelId });

            await this.loadModelData();
            alert('交易周期执行完成');
        } catch (error) {
            this.logger.logApiError('POST', url, error);
            alert('执行交易失败');
        } finally {
            executeBtn.innerHTML = originalText;
            executeBtn.disabled = false;
        }
    }

    async toggleAutoTrading() {
        if (!this.currentModelId || this.isAggregatedView) {
            alert('请先选择一个模型');
            return;
        }

        const newState = !this.currentModelAutoTradingEnabled;
        const url = `/api/models/${this.currentModelId}/auto-trading`;
        this.logger.logApiCall('POST', url, { body: { enabled: newState } });

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: newState })
            });

            let result;
            try {
                result = await response.json();
            } catch (parseError) {
                this.logger.logApiError('POST', url, new Error('响应解析失败'), response);
                alert('响应解析失败，请稍后再试');
                return;
            }

            if (!response.ok) {
                this.logger.logApiError('POST', url, new Error(result.error || `HTTP ${response.status}`), response, result);
                alert(result.error || '切换自动交易状态失败');
                return;
            }

            this.logger.logApiSuccess('POST', url, response, result);
            this.currentModelAutoTradingEnabled = newState;
            this.updateAutoTradingButtonState();
            await this.loadModelData();
            alert(newState ? '自动交易已开启' : '自动交易已关闭');
        } catch (error) {
            this.logger.logApiError('POST', url, error);
            alert('切换自动交易状态失败');
        }
    }

    async showStrategyModal() {
        if (!this.currentModelId || this.isAggregatedView) {
            alert('请先选择一个模型');
            return;
        }

        const url = `/api/models/${this.currentModelId}/prompts`;
        this.logger.logApiCall('GET', url);

        try {
            const response = await fetch(url);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            let prompts;
            try {
                prompts = await response.json();
            } catch (parseError) {
                this.logger.logApiError('GET', url, new Error('响应解析失败'), response);
                prompts = { buy_prompt: '', sell_prompt: '' };
            }

            this.logger.logApiSuccess('GET', url, response);

            document.getElementById('buyPromptInput').value = prompts.buy_prompt || '';
            document.getElementById('sellPromptInput').value = prompts.sell_prompt || '';
            document.getElementById('strategyModalSubtitle').textContent = `配置模型 "${this.currentModelName}" 的买入/卖出提示词`;

            document.getElementById('strategyModal').classList.add('show');
        } catch (error) {
            this.logger.logDataLoadError('策略提示词', error, url);
            alert('加载策略配置失败');
        }
    }

    hideStrategyModal() {
        document.getElementById('strategyModal').classList.remove('show');
    }

    async saveStrategy() {
        if (!this.currentModelId) return;

        const buyPrompt = document.getElementById('buyPromptInput').value.trim();
        const sellPrompt = document.getElementById('sellPromptInput').value.trim();

        const url = `/api/models/${this.currentModelId}/prompts`;
        const requestData = {
            buy_prompt: buyPrompt,
            sell_prompt: sellPrompt
        };
        this.logger.logApiCall('PUT', url, { body: requestData });

        try {
            const response = await fetch(url, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestData)
            });

            let result;
            try {
                result = await response.json();
            } catch (parseError) {
                this.logger.logApiError('PUT', url, new Error('响应解析失败'), response);
                alert('响应解析失败，请稍后再试');
                return;
            }

            if (!response.ok) {
                this.logger.logApiError('PUT', url, new Error(result.error || `HTTP ${response.status}`), response, result);
                alert(result.error || '保存策略失败');
                return;
            }

            this.logger.logApiSuccess('PUT', url, response, result);
            this.logger.logInfo('策略配置', '策略保存成功', { modelId: this.currentModelId });

            this.hideStrategyModal();
            alert('策略配置已保存');
        } catch (error) {
            this.logger.logApiError('PUT', url, error);
            alert('保存策略失败');
        }
    }

    // ============ View Management Methods ============

    detectLanguage() {
        return navigator.language.startsWith('zh') || document.documentElement.lang === 'zh-CN';
    }

    showAggregatedView() {
        this.currentModelId = null;
        this.isAggregatedView = true;
        this.loadModels();
        this.loadAggregatedData();
        this.hideTabsInAggregatedView();
        this.updateExecuteButtonState();
        this.updateStrategyButtonState();
    }

    renderModels(models) {
        const container = document.getElementById('modelList');
        if (!container) return;

        if (!models || models.length === 0) {
            container.innerHTML = '<div class="empty-state">暂无模型，点击"添加模型"创建</div>';
            return;
        }

        container.innerHTML = models.map(model => {
            const isActive = this.currentModelId === model.id && !this.isAggregatedView;
            const leverage = this.modelLeverageMap[model.id] ?? model.leverage ?? 10;
            const leverageText = leverage === 0 ? 'AI' : `${leverage}x`;

            return `
                <div class="model-item ${isActive ? 'active' : ''}" data-model-id="${model.id}" onclick="app.selectModel(${model.id})">
                    <div class="model-header">
                        <div class="model-name">${model.name || `模型 #${model.id}`}</div>
                        <div class="model-actions">
                            <button class="model-action-btn" onclick="event.stopPropagation(); app.openLeverageModal(${model.id}, '${(model.name || `模型 #${model.id}`).replace(/'/g, "\\'")}')" title="设置杠杆">
                                <i class="bi bi-sliders"></i>
                            </button>
                            <button class="model-action-btn" onclick="event.stopPropagation(); app.deleteModel(${model.id})" title="删除模型">
                                <i class="bi bi-trash"></i>
                            </button>
                        </div>
                    </div>
                    <div class="model-meta">
                        <span class="model-leverage">杠杆: ${leverageText}</span>
                        <span class="model-provider">${model.provider_name || '未知'}</span>
                    </div>
                </div>
            `;
        }).join('');

        // 添加聚合视图选项
        if (models.length > 0) {
            const aggregatedItem = `
                <div class="model-item ${this.isAggregatedView ? 'active' : ''}" onclick="app.showAggregatedView()">
                    <div class="model-header">
                        <div class="model-name"><i class="bi bi-bar-chart"></i> 聚合视图</div>
                    </div>
                    <div class="model-meta">
                        <span>所有模型总览</span>
                    </div>
                </div>
            `;
            container.insertAdjacentHTML('afterbegin', aggregatedItem);
        }
    }

    // ============ Leaderboard Methods ============

    async fetchLeaderboardSnapshot(manual = false) {
        const url = '/api/market/leaderboard';
        this.logger.logApiCall('GET', url);

        // 更新状态指示器
        const statusElement = document.getElementById('leaderboardStatus');
        if (statusElement) {
            statusElement.textContent = '正在加载...';
            statusElement.className = 'status-indicator loading';
        }

        try {
            const response = await fetch(url);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            let data;
            try {
                data = await response.json();
            } catch (parseError) {
                this.logger.logApiError('GET', url, new Error('响应解析失败'), response);
                if (statusElement) {
                    statusElement.textContent = '数据解析失败';
                    statusElement.className = 'status-indicator error';
                }
                return;
            }

            // 检查返回数据格式
            if (!data || typeof data !== 'object') {
                throw new Error('返回数据格式错误');
            }

            // 确保 gainers 和 losers 是数组
            const gainers = Array.isArray(data.gainers) ? data.gainers : [];
            const losers = Array.isArray(data.losers) ? data.losers : [];

            this.leaderboardData = { gainers, losers };
            this.leaderboardLastUpdated = new Date();
            
            // 更新状态指示器
            if (statusElement) {
                statusElement.textContent = '数据已更新';
                statusElement.className = 'status-indicator success';
            }

            this.logger.logApiSuccess('GET', url, response, data);
            this.renderLeaderboard();
        } catch (error) {
            this.logger.logDataLoadError('涨跌幅榜', error, url);
            
            // 更新状态指示器为错误状态
            const statusElement = document.getElementById('leaderboardStatus');
            if (statusElement) {
                statusElement.textContent = '加载失败';
                statusElement.className = 'status-indicator error';
            }
        }
    }

    renderLeaderboard() {
        const gainersContainer = document.getElementById('leaderboardGainers');
        const losersContainer = document.getElementById('leaderboardLosers');
        const statusElement = document.getElementById('leaderboardStatus');

        // 更新状态时间
        if (statusElement && this.leaderboardLastUpdated) {
            const timeStr = this.leaderboardLastUpdated.toLocaleTimeString('zh-CN');
            const dateStr = this.leaderboardLastUpdated.toLocaleDateString('zh-CN');
            statusElement.textContent = `最后更新: ${dateStr} ${timeStr}`;
        }

        // 渲染涨幅榜
        if (gainersContainer) {
            if (this.leaderboardData.gainers && this.leaderboardData.gainers.length > 0) {
                gainersContainer.innerHTML = this.leaderboardData.gainers.map((item) => {
                    // 安全获取数据字段，兼容不同的字段名
                    const rank = item.rank || 0;
                    const symbol = item.symbol || item.contract_symbol || 'N/A';
                    const contractSymbol = item.contract_symbol || symbol;
                    const price = this.formatNumber(item.price || 0, 4);
                    const changePercent = item.change_percent !== undefined 
                        ? item.change_percent 
                        : (item.priceChangePercent !== undefined ? item.priceChangePercent : 0);
                    const quoteVolume = this.formatVolumeChinese(item.quote_volume || item.quoteVolume || 0);
                    
                    // 确保涨跌幅为正数（涨幅榜）
                    const changeValue = Math.abs(changePercent);
                    const changeDisplay = changeValue >= 0 ? `+${changeValue.toFixed(2)}%` : `${changeValue.toFixed(2)}%`;
                    
                    return `
                        <div class="leaderboard-item" onclick="app.openKlineChart('${symbol}', '${contractSymbol}')" style="cursor: pointer;">
                            <span class="leaderboard-rank">${rank}</span>
                            <div class="leaderboard-symbol">
                                <strong>${symbol}</strong>
                                <span>${contractSymbol}</span>
                            </div>
                            <span class="leaderboard-price">$${price}</span>
                            <span class="leaderboard-change positive">${changeDisplay}</span>
                            <span class="leaderboard-volume">
                                <span class="volume-label">成交额</span>
                                <span class="volume-value">${quoteVolume}</span>
                            </span>
                        </div>
                    `;
                }).join('');
            } else {
                gainersContainer.innerHTML = '<div class="empty-state">暂无涨幅数据</div>';
            }
        }

        // 渲染跌幅榜
        if (losersContainer) {
            if (this.leaderboardData.losers && this.leaderboardData.losers.length > 0) {
                losersContainer.innerHTML = this.leaderboardData.losers.map((item) => {
                    // 安全获取数据字段，兼容不同的字段名
                    const rank = item.rank || 0;
                    const symbol = item.symbol || item.contract_symbol || 'N/A';
                    const contractSymbol = item.contract_symbol || symbol;
                    const price = this.formatNumber(item.price || 0, 4);
                    const changePercent = item.change_percent !== undefined 
                        ? item.change_percent 
                        : (item.priceChangePercent !== undefined ? item.priceChangePercent : 0);
                    const quoteVolume = this.formatVolumeChinese(item.quote_volume || item.quoteVolume || 0);
                    
                    // 确保涨跌幅为负数（跌幅榜）
                    const changeValue = changePercent <= 0 ? changePercent : -changePercent;
                    const changeDisplay = `${changeValue.toFixed(2)}%`;
                    
                    return `
                        <div class="leaderboard-item" onclick="app.openKlineChart('${symbol}', '${contractSymbol}')" style="cursor: pointer;">
                            <span class="leaderboard-rank">${rank}</span>
                            <div class="leaderboard-symbol">
                                <strong>${symbol}</strong>
                                <span>${contractSymbol}</span>
                            </div>
                            <span class="leaderboard-price">$${price}</span>
                            <span class="leaderboard-change negative">${changeDisplay}</span>
                            <span class="leaderboard-volume">
                                <span class="volume-label">成交额</span>
                                <span class="volume-value">${quoteVolume}</span>
                            </span>
                        </div>
                    `;
                }).join('');
            } else {
                losersContainer.innerHTML = '<div class="empty-state">暂无跌幅数据</div>';
            }
        }
    }

    formatNumber(value, decimals = 2) {
        if (value === null || value === undefined || isNaN(value)) return '0.00';
        return parseFloat(value).toFixed(decimals);
    }

    updateConversations(conversations) {
        const container = document.getElementById('conversationsBody');
        if (!container) return;

        if (!conversations || conversations.length === 0) {
            container.innerHTML = '<div class="empty-state">暂无对话记录</div>';
            return;
        }

        container.innerHTML = conversations.map(conv => {
            const role = conv.role || 'unknown';
            const content = conv.content || '';
            const timestamp = conv.timestamp ? new Date(conv.timestamp.replace(' ', 'T') + 'Z').toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '';

            const isSystem = role === 'system';
            const isUser = role === 'user';
            const isAssistant = role === 'assistant';

            if (isSystem && !this.showSystemPrompt) {
                return '';
            }

            let roleClass = 'conversation-role-other';
            let roleText = role;
            if (isUser) {
                roleClass = 'conversation-role-user';
                roleText = '用户';
            } else if (isAssistant) {
                roleClass = 'conversation-role-assistant';
                roleText = 'AI';
            } else if (isSystem) {
                roleClass = 'conversation-role-system';
                roleText = '系统';
            }

            return `
                <div class="conversation-item">
                    <div class="conversation-header">
                        <span class="${roleClass}">${roleText}</span>
                        <span class="conversation-time">${timestamp}</span>
                    </div>
                    <div class="conversation-content">${content.replace(/\n/g, '<br>')}</div>
                </div>
            `;
        }).join('');
    }

    loadSettingsCache() {
        // 从缓存或API加载设置
        if (this.settingsCache) {
            this.showSystemPrompt = Boolean(this.settingsCache.show_system_prompt);
        }
    }

    // ============ Utility/Helper Methods ============

    formatPnl(value, isPnl = false) {
        if (value === null || value === undefined) return '$0.00';
        const num = parseFloat(value);
        if (isNaN(num)) return '$0.00';
        const sign = isPnl && num >= 0 ? '+' : '';
        return `${sign}$${num.toFixed(2)}`;
    }

    getPnlClass(value, isPnl = false) {
        if (!isPnl) return '';
        const num = parseFloat(value);
        if (isNaN(num)) return '';
        if (num > 0) return 'text-success';
        if (num < 0) return 'text-danger';
        return '';
    }

    formatCompactUsd(value) {
        if (!value) return '--';
        const num = parseFloat(value);
        if (isNaN(num)) return '--';
        if (num >= 1000000) return `$${(num / 1000000).toFixed(2)}M`;
        if (num >= 1000) return `$${(num / 1000).toFixed(2)}K`;
        return `$${num.toFixed(2)}`;
    }

    /**
     * 使用中文单位格式化成交量（亿、万）
     * @param {number} value - 成交量数值
     * @returns {string} 格式化后的字符串，例如："1.23亿"、"45.67万"、"1234.56"
     */
    formatVolumeChinese(value) {
        if (!value && value !== 0) return '--';
        const num = parseFloat(value);
        if (isNaN(num)) return '--';
        
        // 大于等于1亿（100000000）
        if (num >= 100000000) {
            const yi = num / 100000000;
            return `${yi.toFixed(2)}亿`;
        }
        
        // 大于等于1万（10000）
        if (num >= 10000) {
            const wan = num / 10000;
            return `${wan.toFixed(2)}万`;
        }
        
        // 小于1万，显示原数字，保留2位小数
        return num.toFixed(2);
    }

    getModelDisplayName(modelId) {
        const model = this.modelsCache.find(m => m.id === modelId);
        return model ? (model.name || `模型 #${modelId}`) : `模型 #${modelId}`;
    }
}

// ============ K线图组件 ============

/**
 * 自定义数据接入类
 * 实现 KLineChart Pro 版本的数据接入接口
 */
class CustomDatafeed {
    constructor() {
        this.socket = null;
        this.subscriptions = new Map(); // 存储订阅信息: key = `${symbol.ticker}:${period.text}`, value = { callback, symbol, period }
        this.marketPrices = []; // 缓存市场行情数据
    }

    /**
     * 模糊搜索标的
     * @param {string} search - 搜索关键词
     * @returns {Promise<SymbolInfo[]>}
     */
    async searchSymbols(search = '') {
        try {
            console.log('[CustomDatafeed] Searching symbols:', search);
            
            // 获取市场行情数据
            if (this.marketPrices.length === 0) {
                const response = await fetch('/api/market/prices');
                const result = await response.json();
                if (result.data) {
                    this.marketPrices = Object.keys(result.data).map(symbol => ({
                        symbol,
                        name: result.data[symbol].name || `${symbol}永续合约`,
                        contract_symbol: result.data[symbol].contract_symbol || symbol
                    }));
                }
            }

            // 过滤匹配的标的
            const searchUpper = search.toUpperCase();
            const matched = this.marketPrices
                .filter(item => {
                    const symbol = item.symbol.toUpperCase();
                    const name = (item.name || '').toUpperCase();
                    return symbol.includes(searchUpper) || name.includes(searchUpper);
                })
                .slice(0, 20); // 限制返回数量

            // 转换为 SymbolInfo 格式
            const symbols = matched.map(item => ({
                ticker: item.contract_symbol || item.symbol,
                shortName: item.symbol.replace('USDT', ''),
                name: item.name || `${item.symbol}永续合约`,
                exchange: 'BINANCE',
                market: 'futures',
                priceCurrency: 'usd',
                type: 'PERPETUAL'
            }));

            console.log('[CustomDatafeed] Found symbols:', symbols.length);
            return symbols;
        } catch (error) {
            console.error('[CustomDatafeed] Error searching symbols:', error);
            return [];
        }
    }

    /**
     * 获取历史K线数据
     * @param {SymbolInfo} symbol - 标的信息
     * @param {Period} period - 周期信息
     * @param {number} from - 开始时间戳（毫秒）
     * @param {number} to - 结束时间戳（毫秒）
     * @returns {Promise<KLineData[]>}
     */
    async getHistoryKLineData(symbol, period, from, to) {
        try {
            console.log('[CustomDatafeed] Getting history K-line data:', {
                ticker: symbol?.ticker || symbol,
                period: period?.text || period,
                from: new Date(from).toISOString(),
                to: new Date(to).toISOString()
            });

            // 将 period 转换为后端支持的 interval
            const interval = this.periodToInterval(period);
            if (!interval) {
                console.warn('[CustomDatafeed] Unsupported period:', period);
                return [];
            }

            // 获取 ticker（支持 symbol 对象或字符串）
            const ticker = symbol?.ticker || symbol;
            if (!ticker) {
                console.warn('[CustomDatafeed] Invalid symbol:', symbol);
                return [];
            }

            // 计算需要的数据量（根据时间范围估算，但后端限制最多500条）
            const limit = 500;

            // 将时间戳转换为 ISO 格式字符串（后端期望的格式）
            const startTimeISO = new Date(from).toISOString();
            const endTimeISO = new Date(to).toISOString();

            // 调用后端 API 获取 K 线数据
            const params = new URLSearchParams({
                symbol: ticker,
                interval: interval,
                limit: limit.toString()
            });
            if (startTimeISO) params.append('start_time', startTimeISO);
            if (endTimeISO) params.append('end_time', endTimeISO);

            const response = await fetch(`/api/market/klines?${params.toString()}`);
            const result = await response.json();

            if (!result || !result.data || !Array.isArray(result.data)) {
                console.warn('[CustomDatafeed] Invalid response format:', result);
                return [];
            }

            // 转换数据格式并过滤时间范围
            const klines = result.data
                .map(kline => {
                    // 处理时间戳：确保是数字类型（毫秒）
                    let timestamp = kline.timestamp;
                    
                    if (timestamp === null || timestamp === undefined) {
                        if (kline.kline_start_time) {
                            timestamp = typeof kline.kline_start_time === 'number' 
                                ? kline.kline_start_time 
                                : new Date(kline.kline_start_time).getTime();
                        } else if (kline.kline_end_time) {
                            timestamp = typeof kline.kline_end_time === 'number'
                                ? kline.kline_end_time
                                : new Date(kline.kline_end_time).getTime();
                        } else {
                            return null;
                        }
                    } else if (typeof timestamp === 'string') {
                        timestamp = new Date(timestamp).getTime();
                        if (isNaN(timestamp)) {
                            return null;
                        }
                    } else if (typeof timestamp !== 'number') {
                        return null;
                    }

                    // 确保时间戳是毫秒
                    if (timestamp < 1e12) {
                        timestamp = timestamp * 1000;
                    }

                    // 过滤时间范围
                    if (timestamp < from || timestamp > to) {
                        return null;
                    }

                    // 转换价格和成交量数据
                    const open = parseFloat(kline.open);
                    const high = parseFloat(kline.high);
                    const low = parseFloat(kline.low);
                    const close = parseFloat(kline.close);
                    const volume = parseFloat(kline.volume) || 0;

                    // 验证数据有效性
                    if (isNaN(open) || isNaN(high) || isNaN(low) || isNaN(close) || close <= 0) {
                        return null;
                    }

                    // 确保 high >= max(open, close) 和 low <= min(open, close)
                    const maxPrice = Math.max(open, close);
                    const minPrice = Math.min(open, close);
                    const validHigh = Math.max(high, maxPrice);
                    const validLow = Math.min(low, minPrice);

                    return {
                        timestamp: Math.floor(timestamp),
                        open: open,
                        high: validHigh,
                        low: validLow,
                        close: close,
                        volume: volume
                    };
                })
                .filter(kline => kline !== null && kline.timestamp > 0)
                .sort((a, b) => a.timestamp - b.timestamp); // 按时间升序排序

            console.log('[CustomDatafeed] Loaded K-line data:', {
                total: klines.length,
                firstTimestamp: klines.length > 0 ? new Date(klines[0].timestamp).toISOString() : null,
                lastTimestamp: klines.length > 0 ? new Date(klines[klines.length - 1].timestamp).toISOString() : null
            });

            return klines;
        } catch (error) {
            console.error('[CustomDatafeed] Error getting history K-line data:', error);
            return [];
        }
    }

    /**
     * 订阅标的在某个周期的实时数据
     * @param {SymbolInfo} symbol - 标的信息
     * @param {Period} period - 周期信息
     * @param {Function} callback - 数据回调函数
     */
    subscribe(symbol, period, callback) {
        try {
            const ticker = symbol?.ticker || symbol;
            const periodText = period?.text || period;
            
            console.log('[CustomDatafeed] Subscribing to real-time data:', {
                ticker,
                period: periodText
            });

            // 确保 WebSocket 连接已建立
            if (!this.socket && window.app && window.app.socket) {
                this.socket = window.app.socket;
                
                // 监听实时 K 线更新
                this.socket.on('klines:update', (data) => {
                    try {
                        const symbol = data.symbol || data.ticker;
                        const interval = data.interval || data.period;
                        const key = `${symbol}:${interval}`;
                        const subscription = this.subscriptions.get(key);
                        
                        if (subscription && subscription.callback) {
                            const kline = data.kline || data.data || data;
                            
                            // 处理时间戳
                            let timestamp = kline.timestamp;
                            if (typeof timestamp === 'string') {
                                timestamp = new Date(timestamp).getTime();
                            } else if (typeof timestamp !== 'number') {
                                if (kline.kline_start_time) {
                                    timestamp = typeof kline.kline_start_time === 'number'
                                        ? kline.kline_start_time
                                        : new Date(kline.kline_start_time).getTime();
                                } else if (kline.kline_end_time) {
                                    timestamp = typeof kline.kline_end_time === 'number'
                                        ? kline.kline_end_time
                                        : new Date(kline.kline_end_time).getTime();
                                } else {
                                    timestamp = Date.now();
                                }
                            }
                            
                            // 确保时间戳是毫秒
                            if (timestamp < 1e12) {
                                timestamp = timestamp * 1000;
                            }

                            // 转换数据格式
                            const klineData = {
                                timestamp: Math.floor(timestamp),
                                open: parseFloat(kline.open) || 0,
                                high: parseFloat(kline.high) || 0,
                                low: parseFloat(kline.low) || 0,
                                close: parseFloat(kline.close) || 0,
                                volume: parseFloat(kline.volume) || 0
                            };
                            
                            // 验证数据有效性
                            if (klineData.timestamp > 0 && klineData.close > 0) {
                                subscription.callback(klineData);
                            }
                        }
                    } catch (error) {
                        console.error('[CustomDatafeed] Error processing real-time K-line update:', error);
                    }
                });
            }

            // 将 period 转换为后端支持的 interval
            const interval = this.periodToInterval(period);
            if (!interval) {
                console.warn('[CustomDatafeed] Unsupported period for subscription:', period);
                return;
            }

            // 存储订阅信息
            const key = `${ticker}:${interval}`;
            this.subscriptions.set(key, {
                callback,
                symbol,
                period,
                interval
            });

            // 向后端发送订阅请求
            if (this.socket && this.socket.connected) {
                this.socket.emit('klines:subscribe', {
                    symbol: ticker,
                    interval: interval
                });
                console.log('[CustomDatafeed] Subscription sent to backend:', { symbol: ticker, interval });
            } else if (this.socket) {
                // 等待连接后发送订阅
                this.socket.once('connect', () => {
                    this.socket.emit('klines:subscribe', {
                        symbol: ticker,
                        interval: interval
                    });
                    console.log('[CustomDatafeed] Subscription sent after connection:', { symbol: ticker, interval });
                });
            }
        } catch (error) {
            console.error('[CustomDatafeed] Error subscribing:', error);
        }
    }

    /**
     * 取消订阅标的在某个周期的实时数据
     * @param {SymbolInfo} symbol - 标的信息
     * @param {Period} period - 周期信息
     */
    unsubscribe(symbol, period) {
        try {
            const ticker = symbol?.ticker || symbol;
            const periodText = period?.text || period;
            
            console.log('[CustomDatafeed] Unsubscribing from real-time data:', {
                ticker,
                period: periodText
            });

            // 将 period 转换为后端支持的 interval
            const interval = this.periodToInterval(period);
            if (!interval) {
                console.warn('[CustomDatafeed] Cannot unsubscribe: invalid interval for period:', period);
                return;
            }

            // 移除订阅信息
            const key = `${ticker}:${interval}`;
            const hadSubscription = this.subscriptions.has(key);
            this.subscriptions.delete(key);

            // 向后端发送取消订阅请求
            if (this.socket && this.socket.connected && hadSubscription) {
                this.socket.emit('klines:unsubscribe', {
                    symbol: ticker,
                    interval: interval
                });
                console.log('[CustomDatafeed] Unsubscription sent to backend:', { symbol: ticker, interval });
            }
        } catch (error) {
            console.error('[CustomDatafeed] Error unsubscribing:', error);
        }
    }

    /**
     * 将 Pro 版本的 Period 转换为后端支持的 interval
     * @param {Period} period - Pro 版本的周期对象
     * @returns {string|null} - 后端支持的 interval 字符串
     */
    periodToInterval(period) {
        if (!period) {
            return null;
        }

        // 如果 period 是字符串，直接返回
        if (typeof period === 'string') {
            return period;
        }

        // 如果 period 有 text 属性，使用 text
        if (period.text) {
            const periodMap = {
                '1m': '1m',
                '3m': '3m',
                '5m': '5m',
                '15m': '15m',
                '30m': '30m',
                '1h': '1h',
                '2h': '2h',
                '4h': '4h',
                '6h': '6h',
                '12h': '12h',
                '1d': '1d',
                '1w': '1w'
            };
            return periodMap[period.text] || null;
        }

        // 如果 period 有 multiplier 和 timespan，尝试构建
        if (period.multiplier && period.timespan) {
            const timespanMap = {
                'minute': 'm',
                'hour': 'h',
                'day': 'd',
                'week': 'w'
            };
            const suffix = timespanMap[period.timespan];
            if (suffix) {
                return `${period.multiplier}${suffix}`;
            }
        }

        return null;
    }

    /**
     * 清理资源
     */
    destroy() {
        // 取消所有订阅
        for (const [key, subscription] of this.subscriptions.entries()) {
            this.unsubscribe(subscription.symbol, subscription.period);
        }
        this.subscriptions.clear();
    }
}

/**
 * K线图管理器 - 使用 KLineChartPro
 */
class KLineChartManager {
    constructor() {
        this.chart = null;
        this.datafeed = null;
        this.currentSymbol = null;
        this.currentInterval = '5m';
    }

    /**
     * 初始化K线图
     * @param {string} containerId - 容器ID
     * @param {string} symbol - 交易对符号
     * @param {string} interval - 时间间隔
     */
    init(containerId, symbol, interval = '5m') {
        // 检查KLineChartPro是否加载
        if (typeof klinechartspro === 'undefined' && typeof window.klinechartspro === 'undefined') {
            console.error('[KLineChartPro] Library not loaded');
            return;
        }

        const KLineChartPro = klinechartspro?.KLineChartPro || window.klinechartspro?.KLineChartPro;
        if (!KLineChartPro) {
            console.error('[KLineChartPro] KLineChartPro class not found');
            return;
        }

        this.currentSymbol = symbol;
        this.currentInterval = interval;

        // 获取容器元素
        const container = document.getElementById(containerId);
        if (!container) {
            console.error(`[KLineChartPro] Container ${containerId} not found`);
            return;
        }

        // 清空容器
        container.innerHTML = '';

        // 创建自定义数据接入实例
        this.datafeed = new CustomDatafeed();

        // 将 symbol 字符串转换为 SymbolInfo 对象
        const symbolInfo = {
            ticker: symbol,
            shortName: symbol.replace('USDT', ''),
            name: `${symbol}永续合约`,
            exchange: 'BINANCE',
            market: 'futures',
            priceCurrency: 'usd',
            type: 'PERPETUAL'
        };

        // 将 interval 字符串转换为 Period 对象
        const period = this.intervalToPeriod(interval);

        console.log('[KLineChartPro] Initializing chart:', {
            symbol: symbolInfo,
            period: period,
            containerId: containerId
        });

        // 创建 KLineChartPro 实例
        try {
            this.chart = new KLineChartPro({
                container: container,
                symbol: symbolInfo,
                period: period,
                datafeed: this.datafeed
            });

            console.log('[KLineChartPro] Chart initialized successfully');
        } catch (error) {
            console.error('[KLineChartPro] Failed to create chart instance:', error);
            this.chart = null;
        }
    }

    /**
     * 将 interval 字符串转换为 Period 对象
     * @param {string} interval - 时间间隔字符串（如 '5m', '1h'）
     * @returns {Period} - Period 对象
     */
    intervalToPeriod(interval) {
        const periodMap = {
            '1m': { multiplier: 1, timespan: 'minute', text: '1m' },
            '3m': { multiplier: 3, timespan: 'minute', text: '3m' },
            '5m': { multiplier: 5, timespan: 'minute', text: '5m' },
            '15m': { multiplier: 15, timespan: 'minute', text: '15m' },
            '30m': { multiplier: 30, timespan: 'minute', text: '30m' },
            '1h': { multiplier: 1, timespan: 'hour', text: '1h' },
            '2h': { multiplier: 2, timespan: 'hour', text: '2h' },
            '4h': { multiplier: 4, timespan: 'hour', text: '4h' },
            '6h': { multiplier: 6, timespan: 'hour', text: '6h' },
            '12h': { multiplier: 12, timespan: 'hour', text: '12h' },
            '1d': { multiplier: 1, timespan: 'day', text: '1d' },
            '1w': { multiplier: 1, timespan: 'week', text: '1w' }
        };
        return periodMap[interval] || periodMap['5m'];
    }

    /**
     * 切换时间间隔
     * @param {string} interval - 新的时间间隔
     */
    async switchInterval(interval) {
        if (this.currentInterval === interval || !this.chart) return;

        this.currentInterval = interval;
        const period = this.intervalToPeriod(interval);

        try {
            // 使用 setPeriod 方法切换周期
            if (typeof this.chart.setPeriod === 'function') {
                this.chart.setPeriod(period);
                console.log('[KLineChartPro] Period changed successfully:', period);
            } else {
                console.warn('[KLineChartPro] setPeriod method not available, reinitializing chart');
                // 如果 setPeriod 不可用，重新初始化图表
                const containerId = this.chart.container?.id || 'klineChartContainer';
                this.destroy();
                this.init(containerId, this.currentSymbol, interval);
            }
        } catch (error) {
            console.error('[KLineChartPro] Error changing period:', error);
        }
    }

    /**
     * 销毁图表
     */
    destroy() {
        // 销毁数据接入
        if (this.datafeed) {
            this.datafeed.destroy();
            this.datafeed = null;
        }

        // 销毁图表
        if (this.chart) {
            try {
                if (typeof this.chart.destroy === 'function') {
                    this.chart.destroy();
                } else if (typeof this.chart.dispose === 'function') {
                    this.chart.dispose();
                }
            } catch (error) {
                console.error('[KLineChartPro] Error destroying chart:', error);
            }
            this.chart = null;
        }

        this.currentSymbol = null;
        this.currentInterval = '5m';
    }
}

// 在TradingApp类中添加K线图相关方法
TradingApp.prototype.openKlineChart = function(symbol, contractSymbol = null) {
    const displaySymbol = contractSymbol || symbol;
    const modal = document.getElementById('klineModal');
    const title = document.getElementById('klineModalTitle');
    
    if (!modal || !title) {
        console.error('[KLineChart] Modal elements not found');
        return;
    }
    
    title.textContent = `${displaySymbol} - K线图`;
    modal.style.display = 'block';

    // 初始化K线图
    if (!this.klineChartManager) {
        this.klineChartManager = new KLineChartManager();
    }

    // 使用合约符号（如果有）或基础符号
    const chartSymbol = contractSymbol || (symbol.includes('USDT') ? symbol : `${symbol}USDT`);
    
    // 等待模态框完全显示后再初始化图表
    setTimeout(() => {
        this.klineChartManager.init('klineChartContainer', chartSymbol, '5m');
    }, 100);

    // 绑定时间间隔切换事件（移除旧的事件监听器，避免重复绑定）
    const timeframeBtns = document.querySelectorAll('.timeframe-btn');
    timeframeBtns.forEach(btn => {
        // 移除旧的事件监听器
        const newBtn = btn.cloneNode(true);
        btn.parentNode.replaceChild(newBtn, btn);
        
        // 添加新的事件监听器
        newBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            timeframeBtns.forEach(b => b.classList.remove('active'));
            newBtn.classList.add('active');
            const interval = newBtn.dataset.interval;
            if (this.klineChartManager) {
                this.klineChartManager.switchInterval(interval);
            }
        });
    });

    // 绑定关闭事件
    const closeBtn = document.getElementById('klineModalClose');
    if (closeBtn) {
        closeBtn.onclick = () => {
            modal.style.display = 'none';
            if (this.klineChartManager) {
                this.klineChartManager.destroy();
            }
        };
    }

    // 点击外部关闭
    modal.onclick = (e) => {
        if (e.target === modal) {
            modal.style.display = 'none';
            if (this.klineChartManager) {
                this.klineChartManager.destroy();
            }
        }
    };
};

const app = new TradingApp();