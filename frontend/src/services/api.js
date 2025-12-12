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
   */
  getTrades: (modelId, limit = 50) => apiGet(`/api/models/${modelId}/trades`, { limit }),

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
   * 执行交易
   */
  execute: (modelId) => apiPost(`/api/models/${modelId}/execute`),

  /**
   * 设置自动交易
   */
  setAutoTrading: (modelId, enabled) => apiPost(`/api/models/${modelId}/auto-trading`, { enabled }),

  /**
   * 设置杠杆
   */
  setLeverage: (modelId, leverage) => apiPost(`/api/models/${modelId}/leverage`, { leverage }),

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

