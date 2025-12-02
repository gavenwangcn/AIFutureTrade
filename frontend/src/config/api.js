/**
 * API 配置
 * 用于统一管理 API 基础 URL
 * 
 * 配置优先级：
 * 1. 环境变量 VITE_BACKEND_URL（完整URL，如：http://localhost:5002）
 * 2. 环境变量 VITE_BACKEND_PORT（仅端口，如：5002，使用当前域名+端口）
 * 3. 开发环境：使用相对路径（通过 Vite 代理）
 * 4. 生产环境：使用当前域名+默认端口5002
 */

export const getApiBaseUrl = () => {
  const isDev = import.meta.env.DEV
  
  // 如果设置了完整的后端URL，直接使用
  if (import.meta.env.VITE_BACKEND_URL) {
    return import.meta.env.VITE_BACKEND_URL
  }
  
  // 如果设置了后端端口，使用当前域名+指定端口
  const backendPort = import.meta.env.VITE_BACKEND_PORT || '5002'
  
  if (isDev) {
    // 开发环境：使用相对路径，通过 Vite 代理
    return ''
  } else {
    // 生产环境：使用当前域名+配置的端口
    // 如果前端和后端在同一台机器，使用当前域名即可
    const protocol = window.location.protocol
    const hostname = window.location.hostname
    return `${protocol}//${hostname}:${backendPort}`
  }
}

export const API_BASE_URL = getApiBaseUrl()

