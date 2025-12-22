#!/bin/bash
# MySQL 连接数检查脚本（支持 Docker 环境）

echo "=========================================="
echo "MySQL 连接数诊断工具"
echo "=========================================="
echo ""

# 从环境变量或配置文件读取数据库连接信息
MYSQL_HOST=${MYSQL_HOST:-154.89.148.172}
MYSQL_PORT=${MYSQL_PORT:-32123}
MYSQL_USER=${MYSQL_USER:-aifuturetrade}
MYSQL_PASSWORD=${MYSQL_PASSWORD:-aifuturetrade123}
MYSQL_DATABASE=${MYSQL_DATABASE:-aifuturetrade}
MYSQL_CONTAINER=${MYSQL_CONTAINER:-aifuturetrade-mysql}

# Docker 环境下使用 root 用户（有完整权限查看所有连接信息）
MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD:-aifuturetrade_root123}

# 检测是否使用 Docker
USE_DOCKER=false
if command -v docker &> /dev/null; then
    # 检查 MySQL 容器是否在运行
    if docker ps --format '{{.Names}}' | grep -q "^${MYSQL_CONTAINER}$"; then
        USE_DOCKER=true
        echo "检测到 Docker 环境，使用容器: $MYSQL_CONTAINER"
    fi
fi

# 构建 MySQL 命令
if [ "$USE_DOCKER" = true ]; then
    # 使用 Docker exec 在容器内执行 MySQL 命令
    # 在容器内使用 root 用户连接，确保有权限查看所有连接信息
    # 不指定 host，使用默认的 socket 连接（容器内推荐方式）
    # 注意：密码通过环境变量传递，避免在命令行中暴露
    MYSQL_CMD="docker exec -i -e MYSQL_PWD=\"$MYSQL_ROOT_PASSWORD\" $MYSQL_CONTAINER mysql"
    MYSQL_ARGS="-uroot $MYSQL_DATABASE"
    DOCKER_USER="root"
else
    # 使用本地 MySQL 客户端
    # 注意：密码通过环境变量传递，避免在命令行中暴露
    export MYSQL_PWD="$MYSQL_PASSWORD"
    MYSQL_CMD="mysql"
    MYSQL_ARGS="-h $MYSQL_HOST -P $MYSQL_PORT -u $MYSQL_USER $MYSQL_DATABASE"
    DOCKER_USER="$MYSQL_USER"
fi

echo "连接信息:"
if [ "$USE_DOCKER" = true ]; then
    echo "  方式: Docker 容器 ($MYSQL_CONTAINER)"
    echo "  用户: $DOCKER_USER (容器内使用 root 用户以确保完整权限)"
else
    echo "  Host: $MYSQL_HOST:$MYSQL_PORT"
    echo "  用户: $DOCKER_USER"
fi
echo "  Database: $MYSQL_DATABASE"
echo ""

# 检查连接数
echo "1. 当前连接数统计:"
$MYSQL_CMD $MYSQL_ARGS <<EOF
SELECT 
    VARIABLE_VALUE as current_connections,
    (SELECT VARIABLE_VALUE FROM information_schema.GLOBAL_VARIABLES WHERE VARIABLE_NAME = 'max_connections') as max_connections,
    ROUND(VARIABLE_VALUE / (SELECT VARIABLE_VALUE FROM information_schema.GLOBAL_VARIABLES WHERE VARIABLE_NAME = 'max_connections') * 100, 2) as usage_percent
FROM information_schema.GLOBAL_STATUS 
WHERE VARIABLE_NAME = 'Threads_connected';
EOF

echo ""
echo "2. 按用户分组的连接数:"
$MYSQL_CMD $MYSQL_ARGS <<EOF
SELECT 
    user, 
    COUNT(*) as connection_count 
FROM information_schema.PROCESSLIST 
WHERE user != 'system user'
GROUP BY user;
EOF

echo ""
echo "3. 长时间运行的连接（>60秒）:"
$MYSQL_CMD $MYSQL_ARGS <<EOF
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
EOF

echo ""
echo "4. 空闲连接（Sleep状态，>5分钟）:"
$MYSQL_CMD $MYSQL_ARGS <<EOF
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
EOF

echo ""
echo "=========================================="
echo "诊断完成"
echo "=========================================="
echo ""
echo "建议："
echo "1. 如果 usage_percent > 80%，需要优化连接池配置或增加 max_connections"
echo "2. 如果发现大量空闲连接，检查应用是否有连接泄漏"
echo "3. 如果发现长时间运行的查询，优化慢查询"
echo ""

