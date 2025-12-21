#!/bin/bash
# 清理 Python 编译文件脚本
# 从 Git 中移除已提交的 Python 编译文件

echo "正在查找已提交的 Python 编译文件..."

# 查找所有已提交的 Python 编译文件
pyc_files=$(git ls-files | grep -E "\.pyc$|__pycache__")

if [ -z "$pyc_files" ]; then
    echo "✓ 没有找到已提交的 Python 编译文件"
    exit 0
fi

echo "找到以下已提交的 Python 编译文件："
echo "$pyc_files" | while read -r file; do
    echo "  - $file"
done

read -p "是否要从 Git 中移除这些文件？(y/N) " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "已取消操作"
    exit 0
fi

# 从 Git 中移除这些文件（但保留本地文件）
echo ""
echo "正在从 Git 中移除这些文件..."
echo "$pyc_files" | while read -r file; do
    if git rm --cached "$file" 2>/dev/null; then
        echo "  ✓ 已移除: $file"
    else
        echo "  ✗ 移除失败: $file"
    fi
done

echo ""
echo "✓ 清理完成！"
echo "请运行 'git commit' 提交这些更改"

