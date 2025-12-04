/**
 * ==============================================================================
 * 前端开发/生产服务器
 * ==============================================================================
 * 功能：
 *   1. 提供静态文件服务（CSS、JS、图片等）
 *   2. 代理API请求到后端服务（/api/* -> BACKEND_URL/api/*）
 *   3. 代理WebSocket请求（/socket.io/* -> BACKEND_URL/socket.io/*）
 *   4. 提供KLineChart库文件服务（/lib/*）
 * ==============================================================================
 */

import express from 'express';
import { createProxyMiddleware } from 'http-proxy-middleware';
import path from 'path';
import { fileURLToPath } from 'url';
import fs from 'fs';

// ==============================================================================
// 初始化
// ==============================================================================
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.FRONTEND_PORT || 3000;
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:5002';

// ==============================================================================
// 中间件配置
// ==============================================================================

// ------------------------------------------------------------------------------
// 1. 静态文件服务
// ------------------------------------------------------------------------------
// 优先提供构建后的 dist/ 目录（生产环境）
// 如果不存在，则提供 public/ 目录（开发环境）
const distPath = path.join(__dirname, 'dist');
const publicPath = path.join(__dirname, 'public');

if (fs.existsSync(distPath)) {
    // 生产环境：提供构建后的文件
    app.use(express.static(distPath, {
        maxAge: '1d',
        etag: true,
        lastModified: true,
        setHeaders: (res, filePath) => {
            if (filePath.endsWith('.css')) {
                res.setHeader('Content-Type', 'text/css; charset=utf-8');
            }
            if (filePath.endsWith('.js')) {
                res.setHeader('Content-Type', 'application/javascript; charset=utf-8');
            }
            if (filePath.endsWith('.svg')) {
                res.setHeader('Content-Type', 'image/svg+xml');
            }
        }
    }));
    console.log(`[Frontend Server] Serving from: ${distPath} (production build)`);
} else {
    // 开发环境：提供 public/ 目录
    app.use(express.static(publicPath, {
        maxAge: '1d',
        etag: true,
        lastModified: true,
        setHeaders: (res, filePath) => {
            if (filePath.endsWith('.css')) {
                res.setHeader('Content-Type', 'text/css; charset=utf-8');
            }
            if (filePath.endsWith('.js')) {
                res.setHeader('Content-Type', 'application/javascript; charset=utf-8');
            }
            if (filePath.endsWith('.svg')) {
                res.setHeader('Content-Type', 'image/svg+xml');
            }
        }
    }));
    console.log(`[Frontend Server] Serving from: ${publicPath} (development)`);
}

// ------------------------------------------------------------------------------
// 2. KLineChart库文件服务（已移除）
// ------------------------------------------------------------------------------
// 注意：klinecharts 现在通过 npm 安装，在 Vue 组件中通过 ES6 import 使用
// Vite 构建时会自动打包 klinecharts，不再需要单独提供文件服务
console.log(`[Frontend Server] KLineChart is bundled by Vite (via npm install klinecharts)`);

// ------------------------------------------------------------------------------
// 3. API代理
// ------------------------------------------------------------------------------
// 将所有 /api/* 请求代理到后端服务
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

// ------------------------------------------------------------------------------
// 4. WebSocket代理
// ------------------------------------------------------------------------------
// 将 /socket.io/* 请求代理到后端服务
// 注意：Socket.IO使用长轮询和WebSocket，需要正确配置代理
// http-proxy-middleware在配置了ws:true后会自动处理WebSocket升级
const socketProxy = createProxyMiddleware({
    target: BACKEND_URL,
    changeOrigin: true,
    ws: true, // 启用WebSocket代理（包括HTTP长轮询和WebSocket升级）
    logLevel: 'warn',
    onProxyReq: (proxyReq, req, res) => {
        console.log(`[Socket.IO Proxy] ${req.method} ${req.url} -> ${BACKEND_URL}${req.url}`);
    },
    onProxyReqWs: (proxyReq, req, socket) => {
        console.log(`[Socket.IO Proxy] WS upgrade ${req.url} -> ${BACKEND_URL}${req.url}`);
    },
    onError: (err, req, res) => {
        console.error(`[Socket.IO Proxy Error] ${req.url}:`, err.message);
        if (!res.headersSent) {
            res.status(500).json({ error: 'Socket.IO proxy error' });
        }
    },
    onProxyError: (err, req, socket) => {
        console.error('[Socket.IO Proxy WS Error]', err.message);
        if (socket && !socket.destroyed) {
            socket.destroy();
        }
    }
});

app.use('/socket.io', socketProxy);

// ------------------------------------------------------------------------------
// 5. /lib/ 路径文件服务（KLineChart等库文件）
// ------------------------------------------------------------------------------
// 提供 /lib/ 路径的文件服务，映射到 public/lib/ 或 dist/lib/
app.get('/lib/*', (req, res, next) => {
    const libPath = req.path.replace('/lib/', '');
    const libDir = fs.existsSync(distPath) 
        ? path.join(distPath, 'lib')
        : path.join(publicPath, 'lib');
    const filePath = path.join(libDir, libPath);
    
    // 安全检查：确保文件路径在lib目录内
    if (!filePath.startsWith(libDir)) {
        return res.status(403).send('Forbidden');
    }
    
    if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
        res.sendFile(filePath);
    } else {
        res.status(404).send(`File not found: ${req.path}`);
    }
});

// ------------------------------------------------------------------------------
// 6. /klinecharts-pro/ 路径文件服务（自定义构建的 klinecharts-pro）
// ------------------------------------------------------------------------------
// 提供 /klinecharts-pro/ 路径的文件服务
// 优先使用挂载的构建产物，否则使用本地构建产物
const klinechartsProDistPath = path.join(__dirname, 'klinecharts-pro-dist');
const klinechartsProLocalPath = path.join(__dirname, '..', 'klinecharts-pro', 'dist');
const klinechartsProPath = fs.existsSync(klinechartsProDistPath) 
    ? klinechartsProDistPath 
    : klinechartsProLocalPath;

app.get('/klinecharts-pro/*', (req, res, next) => {
    const filePath = req.path.replace('/klinecharts-pro/', '');
    const fullPath = path.join(klinechartsProPath, filePath);
    
    // 安全检查：确保文件路径在dist目录内
    if (!fullPath.startsWith(klinechartsProPath)) {
        return res.status(403).send('Forbidden');
    }
    
    if (fs.existsSync(fullPath) && fs.statSync(fullPath).isFile()) {
        // 设置正确的Content-Type
        const ext = path.extname(fullPath).toLowerCase();
        if (ext === '.css') {
            res.setHeader('Content-Type', 'text/css; charset=utf-8');
        } else if (ext === '.js') {
            res.setHeader('Content-Type', 'application/javascript; charset=utf-8');
        }
        res.sendFile(fullPath);
    } else {
        res.status(404).send(`File not found: ${req.path}`);
    }
});

// ------------------------------------------------------------------------------
// 7. 前端路由（SPA支持）
// ------------------------------------------------------------------------------
// 所有其他请求返回 index.html（用于前端路由）
// 注意：必须在静态文件服务之后，Express会先尝试静态文件，找不到才到这里
// 为了安全，排除静态资源文件扩展名和特定路径
app.get('*', (req, res, next) => {
    // 排除静态资源文件扩展名，避免拦截CSS、JS等文件
    const staticExtensions = ['.css', '.js', '.svg', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.woff', '.woff2', '.ttf', '.eot', '.json'];
    const ext = path.extname(req.path).toLowerCase();
    
    // 排除特定路径（如 /api/, /socket.io/, /klinecharts-pro/）
    // 注意：/lib/ 和 /klinecharts-pro/ 路径已经在上面单独处理了
    if (req.path.startsWith('/api/') || req.path.startsWith('/socket.io/') || req.path.startsWith('/klinecharts-pro/')) {
        return res.status(404).send(`File not found: ${req.path}`);
    }
    
    if (staticExtensions.includes(ext)) {
        // 如果是静态资源但没找到，返回404
        console.warn(`[Frontend Server] Static file not found: ${req.path}`);
        return res.status(404).send(`File not found: ${req.path}`);
    }
    
    // 其他请求返回index.html（用于前端路由）
    // 优先使用构建后的文件，否则使用开发文件
    const indexPath = fs.existsSync(distPath) 
        ? path.join(distPath, 'index.html')
        : path.join(publicPath, 'index.html');
    res.sendFile(indexPath);
});

// ==============================================================================
// 启动服务器
// ==============================================================================
const server = app.listen(PORT, () => {
    console.log('='.repeat(60));
    console.log('[Frontend Server] Server started successfully');
    console.log('='.repeat(60));
    console.log(`[Frontend Server] URL: http://localhost:${PORT}`);
    console.log(`[Frontend Server] Backend API: ${BACKEND_URL}`);
    console.log(`[Frontend Server] Static files: ${path.join(__dirname, 'public')}`);
    console.log('');
    
    // 验证静态文件是否存在
    console.log('[Frontend Server] Checking static files...');
    const staticFiles = [
        { name: 'style.css', path: path.join(__dirname, 'public', 'style.css') },
        { name: 'favicon.svg', path: path.join(__dirname, 'public', 'favicon.svg') },
        { name: 'app.js', path: path.join(__dirname, 'public', 'app.js') },
        { name: 'index.html', path: path.join(__dirname, 'public', 'index.html') }
    ];
    
    staticFiles.forEach(file => {
        const exists = fs.existsSync(file.path);
        const status = exists ? '✓ Found' : '✗ Missing';
        console.log(`[Frontend Server]   ${file.name.padEnd(15)} ${status}`);
    });
    
    // 验证KLineChart库文件
    console.log('');
    console.log('[Frontend Server] Checking KLineChart library...');
    const libKlineChartPath = path.join(__dirname, 'public', 'lib', 'klinecharts.min.js');
    const nodeModulesKlineChartPath = path.join(__dirname, 'node_modules', 'klinecharts', 'dist', 'klinecharts.min.js');
    
    if (fs.existsSync(libKlineChartPath)) {
        console.log(`[Frontend Server]   /lib/klinecharts.min.js: ✓ Found in public/lib`);
    } else if (fs.existsSync(nodeModulesKlineChartPath)) {
        console.log(`[Frontend Server]   /lib/klinecharts.min.js: ✓ Found in node_modules (will be served)`);
    } else {
        console.error(`[Frontend Server]   /lib/klinecharts.min.js: ✗ Missing`);
        console.error(`[Frontend Server]   Note: This file is no longer needed. KLineChart is bundled by Vite via npm install.`);
    }
    
    console.log('='.repeat(60));
});

// ==============================================================================
// WebSocket升级处理
// ==============================================================================
// 注意：http-proxy-middleware在配置了ws:true后会自动处理WebSocket升级
// 这里我们只需要监听upgrade事件，确保Socket.IO请求被正确路由
// socketProxy中间件会自动处理WebSocket升级请求
server.on('upgrade', (request, socket, head) => {
    // Socket.IO的WebSocket升级由socketProxy中间件自动处理
    // 这里只是记录日志
    if (request.url && request.url.startsWith('/socket.io/')) {
        console.log(`[WebSocket Upgrade] ${request.url} -> ${BACKEND_URL}${request.url}`);
    }
});
