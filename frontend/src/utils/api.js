/**
 * API 客户端工具
 * 统一封装 HTTP 请求，处理错误和响应
 */

import { API_BASE_URL } from '../config/api.js'

/**
 * 统一的 API 请求方法
 * @param {string} endpoint - API 端点路径（如：'/api/models'）
 * @param {RequestInit} options - fetch 选项
 * @returns {Promise<any>} 响应数据
 */
export async function apiRequest(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`
  
  // 默认配置
  const defaultOptions = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers
    },
    ...options
  }

  try {
    const response = await fetch(url, defaultOptions)
    
    // 检查响应状态
    if (!response.ok) {
      let errorData = {}
      try {
        errorData = await response.json()
      } catch (parseError) {
        // 如果响应不是JSON，则使用状态文本
        errorData = { error: `HTTP ${response.status}: ${response.statusText}` }
      }
      const errorMessage = errorData.error || errorData.message || `请求失败: ${response.status}`
      throw new Error(errorMessage)
    }

    // 对于 DELETE 请求，可能返回 204 No Content，没有响应体
    if (response.status === 204 || response.headers.get('content-length') === '0') {
      return { success: true, message: '操作成功' }
    }

    // 尝试解析 JSON 响应
    const contentType = response.headers.get('content-type')
    if (contentType && contentType.includes('application/json')) {
      try {
        const data = await response.json()
        return data
      } catch (parseError) {
        // 如果解析失败，返回空对象
        return { success: true }
      }
    }
    
    // 如果没有 JSON 内容，返回成功状态
    return { success: true }
  } catch (error) {
    // 网络错误或其他错误
    if (error instanceof TypeError && error.message.includes('fetch')) {
      throw new Error('网络连接失败，请检查后端服务是否运行')
    }
    throw error
  }
}

/**
 * GET 请求
 * @param {string} endpoint - API 端点路径
 * @param {URLSearchParams|Record<string, any>} params - 查询参数
 * @returns {Promise<any>}
 */
export async function apiGet(endpoint, params = {}) {
  let url = endpoint
  if (Object.keys(params).length > 0) {
    // 过滤掉 undefined、null 和空字符串的参数
    const filteredParams = {}
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== '') {
        filteredParams[key] = value
      }
    }
    if (Object.keys(filteredParams).length > 0) {
      const searchParams = new URLSearchParams(filteredParams)
      url = `${endpoint}?${searchParams.toString()}`
    }
  }
  return apiRequest(url, { method: 'GET' })
}

/**
 * POST 请求
 * @param {string} endpoint - API 端点路径
 * @param {any} data - 请求体数据
 * @returns {Promise<any>}
 */
export async function apiPost(endpoint, data = {}) {
  return apiRequest(endpoint, {
    method: 'POST',
    body: JSON.stringify(data)
  })
}

/**
 * PUT 请求
 * @param {string} endpoint - API 端点路径
 * @param {any} data - 请求体数据
 * @returns {Promise<any>}
 */
export async function apiPut(endpoint, data = {}) {
  return apiRequest(endpoint, {
    method: 'PUT',
    body: JSON.stringify(data)
  })
}

/**
 * DELETE 请求
 * @param {string} endpoint - API 端点路径
 * @returns {Promise<any>}
 */
export async function apiDelete(endpoint) {
  return apiRequest(endpoint, { method: 'DELETE' })
}

