/**
 * API 服务模块
 * 封装所有后端 API 调用
 */

import { apiGet, apiPost, apiPut, apiDelete } from '../utils/api.js'

/**
 * 模型相关 API
 */
export const modelApi = {
  /**
   * 获取所有模型
   */
  getAll: () => apiGet('/api/models'),

  /**
   * 获取单个模型信息
   */
  getById: (modelId) => apiGet(`/api/models/${modelId}`),

  /**
   * 添加模型
   */
  create: (data) => apiPost('/api/models', data),

  /**
   * 删除模型
   */
  delete: (modelId) => apiDelete(`/api/models/${modelId}`),

  /**
   * 获取模型投资组合
   */
  getPortfolio: (modelId) => apiGet(`/api/models/${modelId}/portfolio`),

  /**
   * 获取模型交易记录
   * 注意：后端限制查询数量为10条（从配置读取），前端只显示前5条（从配置读取）
   */
  getTrades: (modelId, limit = 10) => apiGet(`/api/models/${modelId}/trades`, { limit }),

  /**
   * 获取模型对话记录
   */
  getConversations: (modelId, limit = 20) => apiGet(`/api/models/${modelId}/conversations`, { limit }),

  /**
   * 获取模型提示词配置
   */
  getPrompts: (modelId) => apiGet(`/api/models/${modelId}/prompts`),

  /**
   * 更新模型提示词配置
   */
  updatePrompts: (modelId, data) => apiPut(`/api/models/${modelId}/prompts`, data),

  /**
   * 执行交易（同时执行买入和卖出）
   */
  execute: (modelId) => apiPost(`/api/models/${modelId}/execute`),

  /**
   * 执行买入交易
   */
  executeBuy: (modelId) => apiPost(`/api/models/${modelId}/execute-buy`),

  /**
   * 执行卖出交易
   */
  executeSell: (modelId) => apiPost(`/api/models/${modelId}/execute-sell`),

  /**
   * 禁用自动买入
   */
  disableBuy: (modelId) => apiPost(`/api/models/${modelId}/disable-buy`),

  /**
   * 禁用自动卖出
   */
  disableSell: (modelId) => apiPost(`/api/models/${modelId}/disable-sell`),

  /**
   * 设置自动交易
   */
  setAutoTrading: (modelId, enabled) => apiPost(`/api/models/${modelId}/auto-trading`, { enabled }),

  /**
   * 设置杠杆
   */
  setLeverage: (modelId, leverage) => apiPost(`/api/models/${modelId}/leverage`, { leverage }),

  /**
   * 设置最大持仓数量
   */
  setMaxPositions: (modelId, maxPositions) => apiPost(`/api/models/${modelId}/max_positions`, { max_positions: maxPositions }),

  /**
   * 更新模型的API提供方和模型名称
   */
  updateProvider: (modelId, providerId, modelName) => apiPut(`/api/models/${modelId}/provider`, { provider_id: providerId, model_name: modelName }),

  /**
   * 设置模型批次配置
   */
  setBatchConfig: (modelId, buyBatchSize, buyBatchExecutionInterval, buyBatchExecutionGroupSize, sellBatchSize, sellBatchExecutionInterval, sellBatchExecutionGroupSize) => 
    apiPost(`/api/models/${modelId}/batch-config`, {
      buy_batch_size: buyBatchSize,
      buy_batch_execution_interval: buyBatchExecutionInterval,
      buy_batch_execution_group_size: buyBatchExecutionGroupSize,
      sell_batch_size: sellBatchSize,
      sell_batch_execution_interval: sellBatchExecutionInterval,
      sell_batch_execution_group_size: sellBatchExecutionGroupSize
    }),

  /**
   * 获取聚合投资组合数据
   */
  getAggregatedPortfolio: () => apiGet('/api/aggregated/portfolio'),

  /**
   * 获取模型持仓合约列表
   */
  getPortfolioSymbols: (modelId) => apiGet(`/api/models/${modelId}/portfolio/symbols`)
}

/**
 * 市场数据相关 API
 */
export const marketApi = {
  /**
   * 获取市场行情价格
   */
  getPrices: () => apiGet('/api/market/prices'),

  /**
   * 获取涨幅榜
   */
  getGainers: (limit = 10) => {
    return apiGet('/api/market/leaderboard/gainers', { limit })
  },

  /**
   * 获取跌幅榜
   */
  getLosers: (limit = 10) => {
    return apiGet('/api/market/leaderboard/losers', { limit })
  },

  /**
   * 获取涨跌幅榜（已废弃，保留以兼容旧代码）
   */
  getLeaderboard: (limit = 10, force = false) => {
    const params = { limit }
    if (force) {
      params.force = 1
    }
    return apiGet('/api/market/leaderboard', params)
  },

  /**
   * 获取K线数据
   * @param {string} symbol - 交易对符号
   * @param {string} interval - 时间间隔
   * @param {number} limit - 返回的最大记录数，默认500
   * @param {string} startTime - 开始时间（可选，ISO格式字符串）
   * @param {string} endTime - 结束时间（可选，ISO格式字符串）
   */
  getKlines: (symbol, interval, limit = 500, startTime = null, endTime = null) => {
    const params = { symbol, interval, limit }
    if (startTime) {
      params.start_time = startTime
    }
    if (endTime) {
      params.end_time = endTime
    }
    return apiGet('/api/market/klines', params)
  },

  /**
   * 获取技术指标
   */
  getIndicators: (symbol) => apiGet(`/api/market/indicators/${symbol}`)
}

/**
 * API 提供方相关 API
 */
export const providerApi = {
  /**
   * 获取所有提供方
   */
  getAll: () => apiGet('/api/providers'),

  /**
   * 添加提供方
   */
  create: (data) => apiPost('/api/providers', data),

  /**
   * 删除提供方
   */
  delete: (providerId) => apiDelete(`/api/providers/${providerId}`),

  /**
   * 获取提供方的模型列表
   */
  fetchModels: (data) => apiPost('/api/providers/models', data)
}

/**
 * 合约配置相关 API
 */
export const futuresApi = {
  /**
   * 获取所有合约配置
   */
  getAll: () => apiGet('/api/futures'),

  /**
   * 添加合约配置
   */
  create: (data) => apiPost('/api/futures', data),

  /**
   * 删除合约配置
   */
  delete: (futureId) => apiDelete(`/api/futures/${futureId}`)
}

/**
 * 设置相关 API
 */
export const settingsApi = {
  /**
   * 获取设置
   */
  get: () => apiGet('/api/settings'),

  /**
   * 更新设置
   */
  update: (data) => apiPut('/api/settings', data)
}

/**
 * 账户管理相关 API
 */
export const accountApi = {
  /**
   * 获取所有账户
   */
  getAll: () => apiGet('/api/accounts'),

  /**
   * 添加账户
   */
  create: (data) => apiPost('/api/accounts', data),

  /**
   * 删除账户
   */
  delete: (accountAlias) => apiDelete(`/api/accounts/${accountAlias}`)
}

/**
 * 策略管理相关 API
 */
export const strategyApi = {
  /**
   * 获取所有策略
   */
  getAll: () => apiGet('/api/strategies'),

  /**
   * 根据ID获取策略
   */
  getById: (id) => apiGet(`/api/strategies/${id}`),

  /**
   * 根据条件查询策略
   */
  search: (params) => apiGet('/api/strategies/search', params),

  /**
   * 分页查询策略
   */
  getPage: (params) => apiGet('/api/strategies/page', params),

  /**
   * 添加策略
   */
  create: (data) => apiPost('/api/strategies', data),

  /**
   * 更新策略
   */
  update: (id, data) => apiPut(`/api/strategies/${id}`, data),

  /**
   * 删除策略
   */
  delete: (id) => apiDelete(`/api/strategies/${id}`)
}

/**
 * 模型关联策略相关 API
 */
export const modelStrategyApi = {
  /**
   * 获取所有模型策略关联
   */
  getAll: () => apiGet('/api/model-strategies'),

  /**
   * 根据ID获取模型策略关联
   */
  getById: (id) => apiGet(`/api/model-strategies/${id}`),

  /**
   * 根据模型ID获取模型策略关联
   */
  getByModelId: (modelId) => apiGet(`/api/model-strategies/model/${modelId}`),

  /**
   * 根据模型ID和类型获取模型策略关联
   */
  getByModelIdAndType: (modelId, type) => apiGet(`/api/model-strategies/model/${modelId}/type/${type}`),

  /**
   * 添加模型策略关联
   */
  create: (data) => apiPost('/api/model-strategies', data),

  /**
   * 更新模型策略关联优先级
   */
  updatePriority: (id, priority) => apiPut(`/api/model-strategies/${id}/priority`, { priority }),

  /**
   * 批量保存模型策略关联
   */
  batchSave: (modelId, type, data) => apiPost(`/api/model-strategies/model/${modelId}/type/${type}/batch`, data),

  /**
   * 删除模型策略关联
   */
  delete: (id) => apiDelete(`/api/model-strategies/${id}`)
}

/**
 * AI提供方服务相关 API
 */
export const aiProviderApi = {
  /**
   * 从提供方获取模型列表
   */
  fetchModels: (providerId) => apiPost('/api/ai/models', { providerId }),

  /**
   * 生成策略代码
   */
  generateStrategyCode: (data) => apiPost('/api/ai/generate-strategy-code', data)
}

