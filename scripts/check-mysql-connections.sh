#!/bin/bash
# MySQL 连接数检查脚本

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

echo "连接信息:"
echo "  Host: $MYSQL_HOST:$MYSQL_PORT"
echo "  User: $MYSQL_USER"
echo "  Database: $MYSQL_DATABASE"
echo ""

# 检查连接数
echo "1. 当前连接数统计:"
mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" <<EOF
SELECT 
    VARIABLE_VALUE as current_connections,
    (SELECT VARIABLE_VALUE FROM information_schema.GLOBAL_VARIABLES WHERE VARIABLE_NAME = 'max_connections') as max_connections,
    ROUND(VARIABLE_VALUE / (SELECT VARIABLE_VALUE FROM information_schema.GLOBAL_VARIABLES WHERE VARIABLE_NAME = 'max_connections') * 100, 2) as usage_percent
FROM information_schema.GLOBAL_STATUS 
WHERE VARIABLE_NAME = 'Threads_connected';
EOF

echo ""
echo "2. 按用户分组的连接数:"
mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" <<EOF
SELECT 
    user, 
    COUNT(*) as connection_count 
FROM information_schema.PROCESSLIST 
WHERE user != 'system user'
GROUP BY user;
EOF

echo ""
echo "3. 长时间运行的连接（>60秒）:"
mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" <<EOF
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
mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" <<EOF
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

