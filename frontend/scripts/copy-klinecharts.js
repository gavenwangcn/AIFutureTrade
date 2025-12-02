/**
 * ==============================================================================
 * KLineChart库文件复制脚本
 * ==============================================================================
 * 功能：从 node_modules/klinecharts/dist/ 复制KLineChart库文件到 public/lib/
 * 用途：确保KLineChart库文件可用于前端服务
 * ==============================================================================
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 路径配置
const sourceDir = path.join(__dirname, '..', 'node_modules', 'klinecharts', 'dist');
const targetDir = path.join(__dirname, '..', 'public', 'lib');

try {
    // 创建目标目录
    if (!fs.existsSync(targetDir)) {
        fs.mkdirSync(targetDir, { recursive: true });
        console.log(`[KLineChart] Created directory: ${targetDir}`);
    }

    // 检查源目录是否存在
    if (!fs.existsSync(sourceDir)) {
        console.error(`[KLineChart] ✗ Source directory not found: ${sourceDir}`);
        console.error('[KLineChart] Please run: npm install klinecharts');
        console.warn('[KLineChart] KLineChart files will be served from node_modules (if available)');
        process.exit(0); // 退出码0表示成功，不会中断构建
    }
    
    // 检查源文件是否存在
    const sourceFile = path.join(sourceDir, 'klinecharts.min.js');
    if (!fs.existsSync(sourceFile)) {
        console.error(`[KLineChart] ✗ Source file not found: ${sourceFile}`);
        console.error('[KLineChart] Please check if klinecharts package is correctly installed');
        console.warn('[KLineChart] KLineChart files will be served from node_modules (if available)');
        process.exit(0);
    }

    // 复制文件
    const files = fs.readdirSync(sourceDir);
    let copiedCount = 0;

    files.forEach(file => {
        const sourceFile = path.join(sourceDir, file);
        const targetFile = path.join(targetDir, file);
        
        if (fs.statSync(sourceFile).isFile()) {
            fs.copyFileSync(sourceFile, targetFile);
            copiedCount++;
        }
    });

    console.log(`[KLineChart] Copied ${copiedCount} files to ${targetDir}`);
} catch (error) {
    console.warn('[KLineChart] Error copying files:', error.message);
    console.warn('[KLineChart] KLineChart files will be served from node_modules');
    process.exit(0); // 退出码0，不中断构建过程
}
