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
      const errorData = await response.json().catch(() => ({ 
        error: `HTTP ${response.status}: ${response.statusText}` 
      }))
      throw new Error(errorData.error || `请求失败: ${response.status}`)
    }

    // 解析 JSON 响应
    const data = await response.json()
    return data
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
    const searchParams = new URLSearchParams(params)
    url = `${endpoint}?${searchParams.toString()}`
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

