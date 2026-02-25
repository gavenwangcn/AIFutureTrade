-- ==============================================================================
-- MySQL 认证插件初始化脚本（SQL版本）
-- ==============================================================================
-- 此脚本确保所有用户使用 mysql_native_password 认证插件
-- 解决 MySQL 8.0 默认使用 caching_sha2_password 导致的连接问题
-- 
-- 注意：此脚本会在数据库初始化时自动执行
-- 如果使用 shell 脚本版本（init-database.sh），此文件可以删除
-- ==============================================================================

-- 修改 root 用户的认证插件
ALTER USER IF EXISTS 'root'@'%' IDENTIFIED WITH mysql_native_password BY 'aifuturetrade_root123';
ALTER USER IF EXISTS 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'aifuturetrade_root123';

-- 修改应用用户的认证插件
-- 注意：如果用户是通过 MYSQL_USER 环境变量创建的，这里会确保使用正确的认证插件
ALTER USER IF EXISTS 'aifuturetrade'@'%' IDENTIFIED WITH mysql_native_password BY 'aifuturetrade123';
ALTER USER IF EXISTS 'aifuturetrade'@'localhost' IDENTIFIED WITH mysql_native_password BY 'aifuturetrade123';

-- 刷新权限
FLUSH PRIVILEGES;

