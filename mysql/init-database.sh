#!/bin/bash
# ==============================================================================
# MySQL 数据库初始化脚本
# ==============================================================================
# 此脚本在 MySQL 首次启动时自动执行
# 确保所有用户使用 mysql_native_password 认证插件
# ==============================================================================

set -e

echo "=============================================================================="
echo "MySQL 数据库初始化脚本"
echo "=============================================================================="
echo ""

# 等待 MySQL 完全启动
echo "⏳ 等待 MySQL 完全启动..."
until mysqladmin ping -h localhost -u root -paifuturetrade_root123 --silent 2>/dev/null; do
    echo "   等待中..."
    sleep 1
done
# 额外等待几秒，确保 MySQL 完全初始化（避免 Public Key Retrieval 错误）
echo "⏳ 等待 MySQL 完全初始化..."
sleep 3
echo "✅ MySQL 已就绪"
echo ""

# 执行 SQL 命令修改认证插件
echo "🔧 配置用户认证插件..."
mysql -u root -paifuturetrade_root123 --allow-public-key-retrieval <<EOF
-- ==============================================================================
-- 修改 root 用户的认证插件（支持 % 和 localhost 连接）
-- ==============================================================================
-- 确保 root 用户可以从任何主机（%）和 localhost 连接
ALTER USER 'root'@'%' IDENTIFIED WITH mysql_native_password BY 'aifuturetrade_root123';
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'aifuturetrade_root123';

-- 如果 root@127.0.0.1 存在，也更新它
ALTER USER IF EXISTS 'root'@'127.0.0.1' IDENTIFIED WITH mysql_native_password BY 'aifuturetrade_root123';

-- ==============================================================================
-- 修改应用用户的认证插件（支持 % 和 localhost 连接）
-- ==============================================================================
-- 注意：如果用户是通过 MYSQL_USER 环境变量创建的，可能已经存在
-- 这里确保使用 mysql_native_password 认证插件
-- 支持从任何主机（%）、localhost 和 127.0.0.1 连接
ALTER USER 'aifuturetrade'@'%' IDENTIFIED WITH mysql_native_password BY 'aifuturetrade123';
ALTER USER 'aifuturetrade'@'localhost' IDENTIFIED WITH mysql_native_password BY 'aifuturetrade123';
ALTER USER IF EXISTS 'aifuturetrade'@'127.0.0.1' IDENTIFIED WITH mysql_native_password BY 'aifuturetrade123';

-- 如果用户不存在，创建它们（确保可以从 localhost 连接）
CREATE USER IF NOT EXISTS 'aifuturetrade'@'localhost' IDENTIFIED WITH mysql_native_password BY 'aifuturetrade123';
CREATE USER IF NOT EXISTS 'aifuturetrade'@'127.0.0.1' IDENTIFIED WITH mysql_native_password BY 'aifuturetrade123';

-- 授予权限（确保所有用户都有完整权限）
GRANT ALL PRIVILEGES ON aifuturetrade.* TO 'aifuturetrade'@'%';
GRANT ALL PRIVILEGES ON aifuturetrade.* TO 'aifuturetrade'@'localhost';
GRANT ALL PRIVILEGES ON aifuturetrade.* TO 'aifuturetrade'@'127.0.0.1';

-- ==============================================================================
-- 刷新权限
-- ==============================================================================
FLUSH PRIVILEGES;

-- ==============================================================================
-- 验证配置
-- ==============================================================================
SELECT user, host, plugin FROM mysql.user WHERE user IN ('root', 'aifuturetrade') ORDER BY user, host;
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 认证插件配置完成！"
    echo ""
    echo "📝 验证连接..."
    # 测试从 localhost 连接
    if mysql -h localhost -u aifuturetrade -paifuturetrade123 --allow-public-key-retrieval -e "SELECT 1" > /dev/null 2>&1; then
        echo "✅ localhost 连接测试成功！"
    else
        echo "⚠️  localhost 连接测试失败"
    fi
    # 测试从 127.0.0.1 连接
    if mysql -h 127.0.0.1 -u aifuturetrade -paifuturetrade123 --allow-public-key-retrieval -e "SELECT 1" > /dev/null 2>&1; then
        echo "✅ 127.0.0.1 连接测试成功！"
    else
        echo "⚠️  127.0.0.1 连接测试失败"
    fi
else
    echo ""
    echo "❌ 配置失败"
    exit 1
fi

echo ""
echo "=============================================================================="
echo "MySQL 数据库初始化完成！"
echo "=============================================================================="

