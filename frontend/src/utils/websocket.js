/**
 * WebSocket 工具
 * 统一管理 Socket.IO 连接
 */

import { io } from 'socket.io-client'
import { getApiBaseUrl } from '../config/api.js'

/**
 * 创建 Socket.IO 连接
 * @param {Object} options - Socket.IO 配置选项
 * @returns {import('socket.io-client').Socket}
 */
export function createSocketConnection(options = {}) {
  const isDev = import.meta.env.DEV
  
  // 获取后端 URL（与 API 配置保持一致）
  let backendUrl
  if (import.meta.env.VITE_BACKEND_URL) {
    backendUrl = import.meta.env.VITE_BACKEND_URL
  } else if (isDev) {
    // 开发环境：使用相对路径，通过 Vite 代理
    backendUrl = undefined
  } else {
    // 生产环境：使用当前域名+配置的端口
    const backendPort = import.meta.env.VITE_BACKEND_PORT || '5002'
    const protocol = window.location.protocol
    const hostname = window.location.hostname
    backendUrl = `${protocol}//${hostname}:${backendPort}`
  }

  const defaultOptions = {
    path: '/socket.io',
    transports: ['websocket', 'polling'],
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionAttempts: 5,
    withCredentials: false,
    autoConnect: true,
    ...options
  }

  const socket = io(backendUrl, defaultOptions)
  
  console.log('[WebSocket] 🔌 正在连接到:', backendUrl || 'current origin (via proxy)')
  console.log('[WebSocket] 连接配置:', {
    path: defaultOptions.path,
    transports: defaultOptions.transports,
    reconnection: defaultOptions.reconnection,
    autoConnect: defaultOptions.autoConnect
  })
  
  // 添加连接状态日志
  socket.on('connect', () => {
    console.log('[WebSocket] ✅ 连接成功，Socket ID:', socket.id)
  })
  
  socket.on('connect_error', (error) => {
    console.error('[WebSocket] ❌ 连接错误:', error.message || error)
  })
  
  return socket
}

