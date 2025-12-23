# Docker Compose 自动重启服务 - Cron 配置说明

## 概述

本目录包含用于每天凌晨2点自动重启 Docker Compose 服务的脚本和配置。

## 文件说明

- `restart-services.sh` - 执行重启操作的主脚本
- `setup-cron.sh` - 自动设置cron任务的辅助脚本
- `README-cron.md` - 本说明文档

## 快速开始

### 方法一：使用自动设置脚本（推荐）

```bash
# 1. 确保脚本有执行权限
chmod +x scripts/restart-services.sh
chmod +x scripts/setup-cron.sh

# 2. 运行设置脚本（需要root权限）
sudo bash scripts/setup-cron.sh
```

### 方法二：手动设置cron任务

```bash
# 1. 确保脚本有执行权限
chmod +x scripts/restart-services.sh

# 2. 编辑cron任务
crontab -e

# 3. 添加以下行（每天凌晨2点执行）
0 2 * * * /root/AIFutureTrade/scripts/restart-services.sh
```

## 脚本功能

### restart-services.sh

执行以下操作：
1. 切换到项目目录 `/root/AIFutureTrade`
2. 执行 `docker compose down` 停止并删除所有容器
3. 等待5秒确保资源释放
4. 执行 `docker compose up -d` 重新启动所有服务
5. 等待10秒后检查服务状态
6. 记录日志到 `/root/AIFutureTrade/logs/restart-services.log`

### 日志文件

日志文件位置：`/root/AIFutureTrade/logs/restart-services.log`

日志包含：
- 执行时间戳
- 每个步骤的执行结果
- 错误信息（如果有）
- 服务状态检查结果

## Cron 时间格式说明

```
0 2 * * *
│ │ │ │ │
│ │ │ │ └─── 星期几 (0-7, 0和7都表示星期日)
│ │ │ └───── 月份 (1-12)
│ │ └─────── 日期 (1-31)
│ └───────── 小时 (0-23)
└─────────── 分钟 (0-59)
```

示例：
- `0 2 * * *` - 每天凌晨2:00
- `0 */6 * * *` - 每6小时执行一次
- `0 2 * * 1` - 每周一凌晨2:00

## 查看和管理 Cron 任务

### 查看当前cron任务
```bash
crontab -l
```

### 编辑cron任务
```bash
crontab -e
```

### 删除所有cron任务
```bash
crontab -r
```

### 删除特定任务
```bash
# 编辑cron任务，删除相关行
crontab -e

# 或使用命令删除
crontab -l | grep -v 'restart-services.sh' | crontab -
```

## 测试脚本

在设置cron任务之前，可以手动测试脚本：

```bash
# 手动执行脚本
bash /root/AIFutureTrade/scripts/restart-services.sh

# 查看日志
tail -f /root/AIFutureTrade/logs/restart-services.log
```

## 注意事项

1. **权限要求**：脚本需要root权限或docker组权限来执行docker命令
2. **日志目录**：脚本会自动创建日志目录 `/root/AIFutureTrade/logs/`
3. **服务依赖**：确保MySQL服务已启动（如果使用docker-compose-mysql.yml）
4. **环境变量**：确保 `.env` 文件存在且配置正确
5. **磁盘空间**：定期清理日志文件，避免磁盘空间不足

## 故障排查

### 问题：脚本执行失败

1. 检查脚本权限：
   ```bash
   ls -l scripts/restart-services.sh
   chmod +x scripts/restart-services.sh
   ```

2. 检查docker命令是否可用：
   ```bash
   which docker
   docker compose version
   ```

3. 查看日志文件：
   ```bash
   tail -n 50 /root/AIFutureTrade/logs/restart-services.log
   ```

### 问题：Cron任务未执行

1. 检查cron服务是否运行：
   ```bash
   systemctl status cron  # Debian/Ubuntu
   systemctl status crond  # CentOS/RHEL
   ```

2. 检查cron任务是否正确设置：
   ```bash
   crontab -l
   ```

3. 查看系统日志：
   ```bash
   grep CRON /var/log/syslog  # Debian/Ubuntu
   grep CRON /var/log/cron    # CentOS/RHEL
   ```

## 安全建议

1. 限制日志文件权限：
   ```bash
   chmod 600 /root/AIFutureTrade/logs/restart-services.log
   ```

2. 定期备份日志文件
3. 监控磁盘空间使用情况
4. 考虑添加邮件通知（cron任务执行结果）

## 相关文档

- [Docker Compose 文档](https://docs.docker.com/compose/)
- [Cron 使用指南](https://www.man7.org/linux/man-pages/man5/crontab.5.html)

