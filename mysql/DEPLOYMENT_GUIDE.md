# MySQL 部署指南 - Linux 固定目录结构

## 概述

本文档说明如何将 MySQL 相关配置文件移动到 Linux 服务器的固定目录 `/mysql` 下，以便统一管理和维护。

## 目录结构

在 Linux 服务器上创建以下目录结构：

```bash
/mysql/
├── config/
│   └── my.cnf                    # MySQL高性能配置文件
└── scripts/
    ├── init-database.sh          # 数据库初始化脚本（必需）
    └── init-auth-plugin.sql      # 认证插件SQL脚本（可选，参考用）
```

## 部署步骤

### 1. 创建目录结构

```bash
# 创建主目录
sudo mkdir -p /mysql

# 创建配置目录
sudo mkdir -p /mysql/config

# 创建脚本目录
sudo mkdir -p /mysql/scripts
```

### 2. 复制配置文件

从项目目录复制以下文件到 Linux 服务器：

#### 必需文件（必须复制）

```bash
# 复制 MySQL 配置文件
sudo cp mysql/my.cnf /mysql/config/my.cnf

# 复制初始化脚本
sudo cp mysql/init-database.sh /mysql/scripts/init-database.sh

# 设置脚本执行权限
sudo chmod +x /mysql/scripts/init-database.sh
```

#### 可选文件（建议复制，用于参考）

```bash
# 复制认证插件SQL脚本（参考用，当前 docker-compose-mysql.yml 未挂载）
# 注意：init-database.sh 已包含认证插件配置，此文件仅作为参考
sudo cp mysql/init-auth-plugin.sql /mysql/scripts/init-auth-plugin.sql
```

**重要说明**：
- `init-auth-plugin.sql` 当前**未在 docker-compose-mysql.yml 中挂载**
- `init-database.sh` 脚本已包含所有认证插件配置逻辑（通过内嵌 SQL）
- 如需使用纯 SQL 方式，可以：
  1. 复制文件到 `/mysql/scripts/init-auth-plugin.sql`
  2. 在 `docker-compose-mysql.yml` 中添加挂载配置：
     ```yaml
     - /mysql/scripts/init-auth-plugin.sql:/docker-entrypoint-initdb.d/02-init-auth-plugin.sql:ro
     ```
  3. 注意：如果同时挂载两个脚本，MySQL 会按文件名顺序执行（01- 在 02- 之前）

### 3. 设置文件权限

```bash
# 设置目录权限（确保 Docker 可以读取）
sudo chmod -R 755 /mysql

# 确保配置文件可读
sudo chmod 644 /mysql/config/my.cnf

# 确保脚本可执行
sudo chmod 755 /mysql/scripts/init-database.sh
```

### 4. 验证文件结构

```bash
# 检查目录结构
tree /mysql
# 或
ls -laR /mysql

# 验证文件存在
test -f /mysql/config/my.cnf && echo "✓ my.cnf exists" || echo "✗ my.cnf missing"
test -f /mysql/scripts/init-database.sh && echo "✓ init-database.sh exists" || echo "✗ init-database.sh missing"
test -x /mysql/scripts/init-database.sh && echo "✓ init-database.sh executable" || echo "✗ init-database.sh not executable"
```

## 需要移动的文件清单

### 必需文件（必须移动到 `/mysql`）

| 源文件路径 | 目标路径 | 说明 |
|-----------|---------|------|
| `mysql/my.cnf` | `/mysql/config/my.cnf` | MySQL 高性能配置文件 |
| `mysql/init-database.sh` | `/mysql/scripts/init-database.sh` | 数据库初始化脚本 |

### 可选文件（建议移动，用于参考和故障排除）

| 源文件路径 | 目标路径 | 说明 |
|-----------|---------|------|
| `mysql/init-auth-plugin.sql` | `/mysql/scripts/init-auth-plugin.sql` | 认证插件SQL脚本（参考用） |
| `mysql/fix-auth-plugin.sh` | `/mysql/scripts/fix-auth-plugin.sh` | 修复认证插件脚本 |
| `mysql/fix-auth-plugin.bat` | `/mysql/scripts/fix-auth-plugin.bat` | Windows修复脚本（如需要） |

### 文档文件（可选，建议保留在项目目录）

以下文档文件可以保留在项目目录中，或复制到 `/mysql/docs/` 目录：

- `mysql/README.md` - MySQL 使用说明
- `mysql/README-INIT.md` - 初始化说明
- `mysql/TROUBLESHOOTING.md` - 故障排除指南
- `mysql/performance-tuning-guide.md` - 性能调优指南

## 一键部署脚本

创建以下脚本可以快速完成部署：

```bash
#!/bin/bash
# deploy-mysql-config.sh
# MySQL 配置文件部署脚本

set -e

echo "=============================================================================="
echo "MySQL 配置文件部署"
echo "=============================================================================="

# 创建目录结构
echo "📁 创建目录结构..."
sudo mkdir -p /mysql/config
sudo mkdir -p /mysql/scripts

# 复制配置文件
echo "📋 复制配置文件..."
sudo cp mysql/my.cnf /mysql/config/my.cnf
sudo cp mysql/init-database.sh /mysql/scripts/init-database.sh

# 设置权限
echo "🔐 设置文件权限..."
sudo chmod 644 /mysql/config/my.cnf
sudo chmod 755 /mysql/scripts/init-database.sh

# 验证
echo "✅ 验证文件..."
if [ -f /mysql/config/my.cnf ] && [ -f /mysql/scripts/init-database.sh ]; then
    echo "✓ 配置文件部署成功！"
    echo ""
    echo "目录结构："
    tree /mysql 2>/dev/null || ls -laR /mysql
else
    echo "✗ 配置文件部署失败！"
    exit 1
fi

echo ""
echo "=============================================================================="
echo "部署完成！现在可以使用 docker-compose -f docker-compose-mysql.yml up -d 启动 MySQL"
echo "=============================================================================="
```

使用方法：

```bash
chmod +x deploy-mysql-config.sh
./deploy-mysql-config.sh
```

## 验证部署

部署完成后，验证配置：

```bash
# 检查文件是否存在
ls -la /mysql/config/my.cnf
ls -la /mysql/scripts/init-database.sh

# 检查文件权限
stat /mysql/config/my.cnf
stat /mysql/scripts/init-database.sh

# 测试 Docker Compose 配置
docker-compose -f docker-compose-mysql.yml config
```

## 注意事项

1. **文件权限**：确保 `/mysql/scripts/init-database.sh` 具有执行权限（755）
2. **文件所有者**：如果使用非 root 用户运行 Docker，可能需要调整文件所有者
3. **路径一致性**：确保 `docker-compose-mysql.yml` 中的路径与实际部署路径一致
4. **首次启动**：首次启动 MySQL 容器时，初始化脚本会自动执行
5. **数据卷**：如果数据卷已存在，初始化脚本不会再次执行

## 故障排除

如果遇到权限问题：

```bash
# 检查文件权限
ls -la /mysql/config/
ls -la /mysql/scripts/

# 修复权限
sudo chmod 644 /mysql/config/my.cnf
sudo chmod 755 /mysql/scripts/init-database.sh
sudo chmod -R 755 /mysql
```

如果遇到文件不存在错误：

```bash
# 检查文件是否存在
test -f /mysql/config/my.cnf && echo "存在" || echo "不存在"
test -f /mysql/scripts/init-database.sh && echo "存在" || echo "不存在"

# 检查 Docker Compose 配置
docker-compose -f docker-compose-mysql.yml config | grep -A 5 volumes
```

## 更新配置

如果需要更新配置文件：

```bash
# 更新配置文件
sudo cp mysql/my.cnf /mysql/config/my.cnf

# 更新初始化脚本
sudo cp mysql/init-database.sh /mysql/scripts/init-database.sh
sudo chmod +x /mysql/scripts/init-database.sh

# 重启 MySQL 服务（注意：配置文件更改需要重启容器）
docker-compose -f docker-compose-mysql.yml restart mysql
```

## 相关文档

- `mysql/README.md` - MySQL 使用说明
- `mysql/README-INIT.md` - 初始化详细说明
- `mysql/TROUBLESHOOTING.md` - 故障排除指南
- `mysql/performance-tuning-guide.md` - 性能调优指南

