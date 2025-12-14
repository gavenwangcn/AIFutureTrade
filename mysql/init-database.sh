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
-- 修改 root 用户的认证插件
-- ==============================================================================
ALTER USER 'root'@'%' IDENTIFIED WITH mysql_native_password BY 'aifuturetrade_root123';
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'aifuturetrade_root123';

-- ==============================================================================
-- 修改应用用户的认证插件
-- ==============================================================================
-- 注意：如果用户是通过 MYSQL_USER 环境变量创建的，可能已经存在
-- 这里确保使用 mysql_native_password 认证插件
ALTER USER 'aifuturetrade'@'%' IDENTIFIED WITH mysql_native_password BY 'aifuturetrade123';
ALTER USER 'aifuturetrade'@'localhost' IDENTIFIED WITH mysql_native_password BY 'aifuturetrade123';

-- ==============================================================================
-- 刷新权限
-- ==============================================================================
FLUSH PRIVILEGES;

-- ==============================================================================
-- 验证配置
-- ==============================================================================
SELECT user, host, plugin FROM mysql.user WHERE user IN ('root', 'aifuturetrade');
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 认证插件配置完成！"
    echo ""
    echo "📝 验证连接..."
    if mysql -u aifuturetrade -paifuturetrade123 --allow-public-key-retrieval -e "SELECT 1" > /dev/null 2>&1; then
        echo "✅ 连接测试成功！"
    else
        echo "⚠️  连接测试失败"
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

