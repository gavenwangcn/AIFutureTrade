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
// klinecharts 9.0.0+ 版本的文件可能在 dist/umd/ 目录中
const possibleSourceDirs = [
    path.join(__dirname, '..', 'node_modules', 'klinecharts', 'dist', 'umd'),
    path.join(__dirname, '..', 'node_modules', 'klinecharts', 'dist'),
    path.join(__dirname, '..', 'node_modules', 'klinecharts')
];
const targetDir = path.join(__dirname, '..', 'public', 'lib');

try {
    // 创建目标目录
    if (!fs.existsSync(targetDir)) {
        fs.mkdirSync(targetDir, { recursive: true });
        console.log(`[KLineChart] Created directory: ${targetDir}`);
    }

    // 查找源目录（按优先级检查多个可能的位置）
    let sourceDir = null;
    for (const dir of possibleSourceDirs) {
        if (fs.existsSync(dir)) {
            // 检查是否有 klinecharts.min.js 或类似的 .min.js 文件
            const files = fs.readdirSync(dir);
            const minJsFiles = files.filter(f => f.endsWith('.min.js'));
            
            if (minJsFiles.length > 0 || files.some(f => f.includes('klinecharts'))) {
                sourceDir = dir;
                console.log(`[KLineChart] Found source directory: ${dir}`);
                break;
            }
        }
    }

    if (!sourceDir) {
        console.error(`[KLineChart] ✗ Source directory not found in any of: ${possibleSourceDirs.join(', ')}`);
        console.error('[KLineChart] Please run: npm install klinecharts');
        console.warn('[KLineChart] KLineChart files will be served from node_modules (if available)');
        process.exit(0); // 退出码0表示成功，不会中断构建
    }
    
    // 检查源文件是否存在（优先查找 klinecharts.min.js）
    const preferredFile = path.join(sourceDir, 'klinecharts.min.js');
    const hasPreferredFile = fs.existsSync(preferredFile);
    
    if (!hasPreferredFile) {
        // 查找其他 .min.js 文件
        const files = fs.readdirSync(sourceDir);
        const minJsFiles = files.filter(f => f.endsWith('.min.js'));
        if (minJsFiles.length === 0) {
            console.warn(`[KLineChart] ⚠ No .min.js files found in ${sourceDir}`);
            console.warn('[KLineChart] Available files:', files.join(', '));
            console.warn('[KLineChart] Will copy all files from source directory');
        }
    }

    // 复制文件
    const files = fs.readdirSync(sourceDir);
    let copiedCount = 0;
    let minJsFile = null;

    files.forEach(file => {
        const sourceFile = path.join(sourceDir, file);
        const targetFile = path.join(targetDir, file);
        
        if (fs.statSync(sourceFile).isFile()) {
            fs.copyFileSync(sourceFile, targetFile);
            copiedCount++;
            console.log(`[KLineChart] Copied: ${file}`);
            
            // 记录 .min.js 文件
            if (file.endsWith('.min.js')) {
                minJsFile = file;
            }
        }
    });

    console.log(`[KLineChart] ✓ Copied ${copiedCount} files to ${targetDir}`);
    
    // 验证关键文件是否存在，如果文件名不同则创建符号链接或重命名
    const targetKlineChartFile = path.join(targetDir, 'klinecharts.min.js');
    if (fs.existsSync(targetKlineChartFile)) {
        console.log(`[KLineChart] ✓ klinecharts.min.js found in target directory`);
    } else if (minJsFile && minJsFile !== 'klinecharts.min.js') {
        // 如果找到其他 .min.js 文件，创建符号链接或复制为 klinecharts.min.js
        const sourceMinJsFile = path.join(targetDir, minJsFile);
        try {
            fs.copyFileSync(sourceMinJsFile, targetKlineChartFile);
            console.log(`[KLineChart] ✓ Created klinecharts.min.js from ${minJsFile}`);
        } catch (error) {
            console.warn(`[KLineChart] ⚠ Could not create klinecharts.min.js from ${minJsFile}:`, error.message);
            console.warn(`[KLineChart] Note: Update index.html to use /lib/${minJsFile} instead`);
        }
    } else {
        // 查找其他可能的文件名
        const targetFiles = fs.readdirSync(targetDir);
        const minJsFiles = targetFiles.filter(f => f.endsWith('.min.js'));
        if (minJsFiles.length > 0) {
            console.log(`[KLineChart] ⚠ klinecharts.min.js not found, but found: ${minJsFiles.join(', ')}`);
            console.log(`[KLineChart] Note: Update index.html to use /lib/${minJsFiles[0]} or rename the file`);
        }
    }
} catch (error) {
    console.warn('[KLineChart] Error copying files:', error.message);
    console.warn('[KLineChart] KLineChart files will be served from node_modules');
    process.exit(0); // 退出码0，不中断构建过程
}
