/**
 * 前端开发/生产服务器
 * 提供静态文件服务，并代理API请求到后端
 */
import express from 'express';
import { createProxyMiddleware } from 'http-proxy-middleware';
import path from 'path';
import { fileURLToPath } from 'url';
import fs from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.FRONTEND_PORT || 3000;
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:5002';

// 静态文件服务
app.use(express.static(path.join(__dirname, 'public')));

// KLineChart库文件服务（优先从public/lib，如果不存在则从node_modules）
const libPath = path.join(__dirname, 'public', 'lib');
const nodeModulesLibPath = path.join(__dirname, 'node_modules', 'klinecharts', 'dist');

if (fs.existsSync(libPath) && fs.readdirSync(libPath).length > 0) {
    // 如果public/lib存在且有文件，使用它（npm run copy-assets已复制）
    app.use('/lib', express.static(libPath));
    console.log(`[Frontend Server] Serving KLineChart from: ${libPath}`);
} else {
    // 否则直接从node_modules提供
    app.use('/lib', express.static(nodeModulesLibPath));
    console.log(`[Frontend Server] Serving KLineChart from: ${nodeModulesLibPath}`);
}

// API代理：将所有 /api/* 请求代理到后端
app.use('/api', createProxyMiddleware({
    target: BACKEND_URL,
    changeOrigin: true,
    ws: true, // 支持WebSocket
    logLevel: 'warn',
    onProxyReq: (proxyReq, req, res) => {
        console.log(`[Proxy] ${req.method} ${req.url} -> ${BACKEND_URL}${req.url}`);
    },
    onError: (err, req, res) => {
        console.error(`[Proxy Error] ${req.url}:`, err.message);
        res.status(500).json({ error: 'Backend service unavailable' });
    }
}));

// WebSocket代理：将 /socket.io/* 请求代理到后端
app.use('/socket.io', createProxyMiddleware({
    target: BACKEND_URL,
    changeOrigin: true,
    ws: true,
    logLevel: 'warn'
}));

// 所有其他请求返回index.html（用于前端路由）
app.get('*', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

const server = app.listen(PORT, () => {
    console.log(`[Frontend Server] Server running on http://localhost:${PORT}`);
    console.log(`[Frontend Server] Backend API: ${BACKEND_URL}`);
    console.log(`[Frontend Server] Static files: ${path.join(__dirname, 'public')}`);
});

// 处理WebSocket升级
server.on('upgrade', (request, socket, head) => {
    // WebSocket请求由代理中间件处理
});
