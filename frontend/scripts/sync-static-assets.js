/**
 * ==============================================================================
 * 静态资源同步脚本
 * ==============================================================================
 * 功能：从项目根目录的 static/ 目录同步静态资源到 frontend/public/
 * 同步文件：style.css, favicon.svg
 * 用途：确保前端服务可以访问到最新的静态资源文件
 * ==============================================================================
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 在Docker构建时，static目录可能不在frontend目录的上级
// 尝试多个可能的路径
const possibleStaticDirs = [
    path.join(__dirname, '..', '..', 'static'),      // 项目根目录的static（本地开发）
    path.join(__dirname, '..', '..', '..', 'static'), // Docker构建时的路径
    '/tmp/static',                                     // Docker构建时复制的临时位置
];

const publicDir = path.join(__dirname, '..', 'public');
let staticDir = null;

// 查找存在的static目录
for (const dir of possibleStaticDirs) {
    if (fs.existsSync(dir)) {
        staticDir = dir;
        break;
    }
}

// 需要同步的文件列表
const filesToSync = ['style.css', 'favicon.svg'];

try {
    // 确保 public 目录存在
    if (!fs.existsSync(publicDir)) {
        fs.mkdirSync(publicDir, { recursive: true });
        console.log(`[Sync] Created directory: ${publicDir}`);
    }

    if (!staticDir) {
        console.warn('[Sync] Static directory not found, skipping sync');
        console.warn('[Sync] Make sure style.css and favicon.svg are in frontend/public/');
        process.exit(0);
    }

    let syncedCount = 0;
    filesToSync.forEach(file => {
        const sourceFile = path.join(staticDir, file);
        const targetFile = path.join(publicDir, file);

        if (fs.existsSync(sourceFile)) {
            fs.copyFileSync(sourceFile, targetFile);
            console.log(`[Sync] Copied ${file} to public/`);
            syncedCount++;
        } else {
            console.warn(`[Sync] Source file not found: ${sourceFile}`);
        }
    });

    console.log(`[Sync] Synced ${syncedCount} static asset files`);
} catch (error) {
    console.warn('[Sync] Error syncing static assets:', error.message);
    console.warn('[Sync] Make sure style.css and favicon.svg are in frontend/public/');
    process.exit(0); // 不中断构建
}
