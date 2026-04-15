import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

/** 与 frontend/src/services/api.js 中 AI 生成策略代码等长请求一致（15 分钟），避免开发时代理先于 fetch 断开 */
const API_LONG_TIMEOUT_MS = 900000

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src')
    }
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false,
    copyPublicDir: true,
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, 'index.html')
      }
    }
  },
  publicDir: 'public',
  server: {
    port: 3000,
    proxy: {
      // trade-monitor（微信通知群等）需先于通用 /api，否则会打到 backend 5002
      '/api/wechat-groups': {
        target: 'http://localhost:5005',
        changeOrigin: true,
        timeout: API_LONG_TIMEOUT_MS,
        proxyTimeout: API_LONG_TIMEOUT_MS
      },
      '/api': {
        target: 'http://localhost:5002',
        changeOrigin: true,
        timeout: API_LONG_TIMEOUT_MS,
        proxyTimeout: API_LONG_TIMEOUT_MS
      },
      '/socket.io': {
        target: 'http://localhost:5002',
        changeOrigin: true,
        ws: true
      }
    }
  },
  preview: {
    port: 3000,
    host: '0.0.0.0'
    // 注意：vite preview 不支持代理配置
    // 生产环境建议使用 nginx 提供静态文件服务和反向代理
  }
})

