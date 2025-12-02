/**
 * 复制KLineChart库文件到public/lib目录
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const sourceDir = path.join(__dirname, '..', 'node_modules', 'klinecharts', 'dist');
const targetDir = path.join(__dirname, '..', 'public', 'lib');

try {
    // 创建目标目录
    if (!fs.existsSync(targetDir)) {
        fs.mkdirSync(targetDir, { recursive: true });
    }

    // 检查源目录是否存在
    if (!fs.existsSync(sourceDir)) {
        console.warn(`[KLineChart] Source directory not found: ${sourceDir}`);
        console.warn('[KLineChart] KLineChart files will be served from node_modules');
        process.exit(0); // 退出码0表示成功，不会中断构建
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

