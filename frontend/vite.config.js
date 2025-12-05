import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
      // 确保使用本地自构建的@klinecharts/pro，而不是npm registry版本
      '@klinecharts/pro': path.resolve(__dirname, '../klinecharts-pro')
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
      '/api': {
        target: 'http://localhost:5002',
        changeOrigin: true
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

