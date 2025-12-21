# MySQL 连接数检查脚本 (PowerShell)

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "MySQL 连接数诊断工具" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# 从环境变量或配置文件读取数据库连接信息
$MYSQL_HOST = if ($env:MYSQL_HOST) { $env:MYSQL_HOST } else { "154.89.148.172" }
$MYSQL_PORT = if ($env:MYSQL_PORT) { $env:MYSQL_PORT } else { "32123" }
$MYSQL_USER = if ($env:MYSQL_USER) { $env:MYSQL_USER } else { "aifuturetrade" }
$MYSQL_PASSWORD = if ($env:MYSQL_PASSWORD) { $env:MYSQL_PASSWORD } else { "aifuturetrade123" }
$MYSQL_DATABASE = if ($env:MYSQL_DATABASE) { $env:MYSQL_DATABASE } else { "aifuturetrade" }

Write-Host "连接信息:" -ForegroundColor Yellow
Write-Host "  Host: $MYSQL_HOST`:$MYSQL_PORT"
Write-Host "  User: $MYSQL_USER"
Write-Host "  Database: $MYSQL_DATABASE"
Write-Host ""

# 检查是否安装了 MySQL 客户端
$mysqlCmd = Get-Command mysql -ErrorAction SilentlyContinue
if (-not $mysqlCmd) {
    Write-Host "错误: 未找到 mysql 命令，请先安装 MySQL 客户端" -ForegroundColor Red
    exit 1
}

Write-Host "1. 当前连接数统计:" -ForegroundColor Green
$query1 = @"
SELECT 
    VARIABLE_VALUE as current_connections,
    (SELECT VARIABLE_VALUE FROM information_schema.GLOBAL_VARIABLES WHERE VARIABLE_NAME = 'max_connections') as max_connections,
    ROUND(VARIABLE_VALUE / (SELECT VARIABLE_VALUE FROM information_schema.GLOBAL_VARIABLES WHERE VARIABLE_NAME = 'max_connections') * 100, 2) as usage_percent
FROM information_schema.GLOBAL_STATUS 
WHERE VARIABLE_NAME = 'Threads_connected';
"@

$query1 | mysql -h $MYSQL_HOST -P $MYSQL_PORT -u $MYSQL_USER -p"$MYSQL_PASSWORD" $MYSQL_DATABASE

Write-Host ""
Write-Host "2. 按用户分组的连接数:" -ForegroundColor Green
$query2 = @"
SELECT 
    user, 
    COUNT(*) as connection_count 
FROM information_schema.PROCESSLIST 
WHERE user != 'system user'
GROUP BY user;
"@

$query2 | mysql -h $MYSQL_HOST -P $MYSQL_PORT -u $MYSQL_USER -p"$MYSQL_PASSWORD" $MYSQL_DATABASE

Write-Host ""
Write-Host "3. 长时间运行的连接（>60秒）:" -ForegroundColor Green
$query3 = @"
SELECT 
    id, 
    user, 
    SUBSTRING_INDEX(host, ':', 1) as client_ip,
    db, 
    command, 
    time, 
    state, 
    LEFT(info, 100) as query
FROM information_schema.PROCESSLIST 
WHERE time > 60 AND user != 'system user'
ORDER BY time DESC
LIMIT 10;
"@

$query3 | mysql -h $MYSQL_HOST -P $MYSQL_PORT -u $MYSQL_USER -p"$MYSQL_PASSWORD" $MYSQL_DATABASE

Write-Host ""
Write-Host "4. 空闲连接（Sleep状态，>5分钟）:" -ForegroundColor Green
$query4 = @"
SELECT 
    id, 
    user, 
    SUBSTRING_INDEX(host, ':', 1) as client_ip,
    db, 
    command, 
    time, 
    state
FROM information_schema.PROCESSLIST 
WHERE command = 'Sleep' AND time > 300 AND user != 'system user'
ORDER BY time DESC
LIMIT 10;
"@

$query4 | mysql -h $MYSQL_HOST -P $MYSQL_PORT -u $MYSQL_USER -p"$MYSQL_PASSWORD" $MYSQL_DATABASE

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "诊断完成" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "建议：" -ForegroundColor Yellow
Write-Host "1. 如果 usage_percent > 80%，需要优化连接池配置或增加 max_connections"
Write-Host "2. 如果发现大量空闲连接，检查应用是否有连接泄漏"
Write-Host "3. 如果发现长时间运行的查询，优化慢查询"
Write-Host ""

