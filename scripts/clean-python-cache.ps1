# 清理 Python 编译文件脚本
# 从 Git 中移除已提交的 Python 编译文件

Write-Host "正在查找已提交的 Python 编译文件..." -ForegroundColor Yellow

# 查找所有已提交的 Python 编译文件
$pycFiles = git ls-files | Select-String -Pattern "\.pyc$|__pycache__"

if ($pycFiles.Count -eq 0) {
    Write-Host "✓ 没有找到已提交的 Python 编译文件" -ForegroundColor Green
    exit 0
}

Write-Host "找到 $($pycFiles.Count) 个已提交的 Python 编译文件：" -ForegroundColor Yellow
$pycFiles | ForEach-Object { Write-Host "  - $_" }

$confirm = Read-Host "`n是否要从 Git 中移除这些文件？(y/N)"
if ($confirm -ne 'y' -and $confirm -ne 'Y') {
    Write-Host "已取消操作" -ForegroundColor Yellow
    exit 0
}

# 从 Git 中移除这些文件（但保留本地文件）
Write-Host "`n正在从 Git 中移除这些文件..." -ForegroundColor Yellow
$pycFiles | ForEach-Object {
    git rm --cached $_ 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ 已移除: $_" -ForegroundColor Green
    } else {
        Write-Host "  ✗ 移除失败: $_" -ForegroundColor Red
    }
}

Write-Host "`n✓ 清理完成！" -ForegroundColor Green
Write-Host "请运行 'git commit' 提交这些更改" -ForegroundColor Yellow

