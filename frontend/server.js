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
// 提供 public/ 目录下的静态文件（CSS、JS、图片等）
// 必须在所有路由之前，确保静态资源正确加载
app.use(express.static(path.join(__dirname, 'public'), {
    maxAge: '1d', // 缓存1天
    etag: true,
    lastModified: true,
    setHeaders: (res, filePath) => {
        // 确保CSS文件有正确的Content-Type
        if (filePath.endsWith('.css')) {
            res.setHeader('Content-Type', 'text/css; charset=utf-8');
        }
        // 确保JS文件有正确的Content-Type
        if (filePath.endsWith('.js')) {
            res.setHeader('Content-Type', 'application/javascript; charset=utf-8');
        }
        // 确保SVG文件有正确的Content-Type
        if (filePath.endsWith('.svg')) {
            res.setHeader('Content-Type', 'image/svg+xml');
        }
    }
}));

// ------------------------------------------------------------------------------
// 2. KLineChart库文件服务
// ------------------------------------------------------------------------------
// 优先从 public/lib/ 提供，如果不存在则从 node_modules/ 提供
// 必须在静态文件服务之后，API代理之前
const libPath = path.join(__dirname, 'public', 'lib');
const nodeModulesLibPath = path.join(__dirname, 'node_modules', 'klinecharts', 'dist');

// 检查并配置KLineChart库路径
if (fs.existsSync(libPath) && fs.readdirSync(libPath).length > 0) {
    // 如果public/lib存在且有文件，使用它（npm run copy-assets已复制）
    app.use('/lib', express.static(libPath, {
        maxAge: '1d',
        etag: true,
        setHeaders: (res, filePath) => {
            if (filePath.endsWith('.js')) {
                res.setHeader('Content-Type', 'application/javascript; charset=utf-8');
            }
        }
    }));
    console.log(`[Frontend Server] Serving KLineChart from: ${libPath}`);
    
    // 验证文件是否存在
    const klineChartFile = path.join(libPath, 'klinecharts.min.js');
    if (fs.existsSync(klineChartFile)) {
        console.log(`[Frontend Server] ✓ KLineChart file found: ${klineChartFile}`);
    } else {
        console.warn(`[Frontend Server] ✗ KLineChart file not found: ${klineChartFile}`);
    }
} else {
    // 否则直接从node_modules提供
    if (fs.existsSync(nodeModulesLibPath)) {
        app.use('/lib', express.static(nodeModulesLibPath, {
            maxAge: '1d',
            etag: true,
            setHeaders: (res, filePath) => {
                if (filePath.endsWith('.js')) {
                    res.setHeader('Content-Type', 'application/javascript; charset=utf-8');
                }
            }
        }));
        console.log(`[Frontend Server] Serving KLineChart from: ${nodeModulesLibPath}`);
        
        // 验证文件是否存在
        const klineChartFile = path.join(nodeModulesLibPath, 'klinecharts.min.js');
        if (fs.existsSync(klineChartFile)) {
            console.log(`[Frontend Server] ✓ KLineChart file found: ${klineChartFile}`);
        } else {
            console.warn(`[Frontend Server] ✗ KLineChart file not found: ${klineChartFile}`);
        }
    } else {
        console.error(`[Frontend Server] ✗ KLineChart library not found in both ${libPath} and ${nodeModulesLibPath}`);
        console.error(`[Frontend Server] Please run: npm install && npm run copy-assets`);
    }
}

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
app.use('/socket.io', createProxyMiddleware({
    target: BACKEND_URL,
    changeOrigin: true,
    ws: true,
    logLevel: 'warn'
}));

// ------------------------------------------------------------------------------
// 5. 前端路由（SPA支持）
// ------------------------------------------------------------------------------
// 所有其他请求返回 index.html（用于前端路由）
// 注意：必须在静态文件服务之后，Express会先尝试静态文件，找不到才到这里
// 为了安全，排除静态资源文件扩展名和特定路径
app.get('*', (req, res, next) => {
    // 排除静态资源文件扩展名，避免拦截CSS、JS等文件
    const staticExtensions = ['.css', '.js', '.svg', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.woff', '.woff2', '.ttf', '.eot', '.json'];
    const ext = path.extname(req.path).toLowerCase();
    
    // 排除特定路径（如 /lib/, /api/, /socket.io/）
    if (req.path.startsWith('/lib/') || req.path.startsWith('/api/') || req.path.startsWith('/socket.io/')) {
        return res.status(404).send(`File not found: ${req.path}`);
    }
    
    if (staticExtensions.includes(ext)) {
        // 如果是静态资源但没找到，返回404
        console.warn(`[Frontend Server] Static file not found: ${req.path}`);
        return res.status(404).send(`File not found: ${req.path}`);
    }
    
    // 其他请求返回index.html（用于前端路由）
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
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
        console.error(`[Frontend Server]   Please run: npm install && npm run copy-assets`);
    }
    
    console.log('='.repeat(60));
});

// ==============================================================================
// WebSocket升级处理
// ==============================================================================
server.on('upgrade', (request, socket, head) => {
    // WebSocket请求由代理中间件处理
});
