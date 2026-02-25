# Trade Monitor 服务使用说明

## 概述

Trade Monitor是一个监控告警服务，用于监控系统异常并自动处置。当async-service的ticker数据同步超过3分钟未输出日志时，会自动发送微信告警并重启async-service容器。

## 功能特性

1. **事件接收**: 接收其他服务的异常事件通知
2. **微信告警**: 通过企业微信机器人发送告警通知
3. **自动处置**: 根据告警类型自动执行处置动作（如重启容器）
4. **告警记录**: 记录所有告警历史，支持查询和统计

## 快速开始

### 1. 配置企业微信机器人

1. 在企业微信群中添加机器人，获取Webhook URL
2. 修改`.env`文件中的`WECHAT_WEBHOOK_URL`配置:

```bash
WECHAT_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY_HERE
```

### 2. 创建数据库表

#### 方法1: 使用Shell脚本（最简单）

```bash
# 直接运行初始化脚本
cd trade-monitor/scripts
./init_db.sh
```

脚本会自动：
- 加载.env文件中的环境变量
- 安装Python依赖
- 运行数据库初始化
- 验证表创建成功

#### 方法2: 使用Python初始化脚本

```bash
# 安装Python依赖
cd trade-monitor/scripts
pip install -r requirements.txt

# 运行初始化脚本
python init_db.py
```

脚本会自动：
- 连接到MySQL数据库
- 读取并执行SQL脚本
- 创建所需的表
- 验证表是否创建成功
- 插入默认配置数据

环境变量配置（可选，默认使用.env中的配置）:
```bash
export MYSQL_HOST=154.89.148.172
export MYSQL_PORT=32123
export MYSQL_USER=aifuturetrade
export MYSQL_PASSWORD=aifuturetrade123
export MYSQL_DATABASE=aifuturetrade

python init_db.py
```

#### 方法3: 手动执行SQL脚本

执行SQL脚本创建所需的数据库表:

```bash
mysql -h 154.89.148.172 -P 32123 -u aifuturetrade -p aifuturetrade < trade-monitor/sql/init.sql
```

或手动执行SQL:

```sql
-- 微信群配置表
CREATE TABLE IF NOT EXISTS `wechat_groups` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `group_name` VARCHAR(100) NOT NULL COMMENT '群组名称',
  `webhook_url` VARCHAR(500) NOT NULL COMMENT '企业微信Webhook URL',
  `alert_types` VARCHAR(500) DEFAULT NULL COMMENT '告警类型(逗号分隔)',
  `is_enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `description` VARCHAR(500) DEFAULT NULL COMMENT '描述',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 告警记录表
CREATE TABLE IF NOT EXISTS `alert_records` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `alert_type` VARCHAR(50) NOT NULL COMMENT '告警类型',
  `service_name` VARCHAR(100) NOT NULL COMMENT '服务名称',
  `severity` VARCHAR(20) NOT NULL COMMENT '严重程度',
  `title` VARCHAR(200) NOT NULL COMMENT '告警标题',
  `message` TEXT NOT NULL COMMENT '告警详细信息',
  `status` VARCHAR(20) NOT NULL DEFAULT 'OPEN' COMMENT '状态',
  `action_taken` VARCHAR(500) DEFAULT NULL COMMENT '已执行的处置动作',
  `wechat_sent` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已发送微信通知',
  `wechat_sent_at` DATETIME DEFAULT NULL COMMENT '微信通知发送时间',
  `resolved_at` DATETIME DEFAULT NULL COMMENT '解决时间',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 3. 配置微信群

插入微信群配置（替换实际的Webhook URL）:

```sql
INSERT INTO `wechat_groups` (`group_name`, `webhook_url`, `alert_types`, `is_enabled`, `description`)
VALUES ('默认告警群', 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY_HERE',
        'TICKER_SYNC_TIMEOUT,CONTAINER_DOWN', 1, '默认告警通知群组');
```

### 4. 启动服务

```bash
# 构建并启动所有服务
docker-compose up -d --build

# 或使用脚本
./scripts/docker-compose-up.sh --build
```

### 5. 验证服务

访问Swagger文档: http://localhost:5005/swagger-ui.html

## API接口

### 1. 接收事件通知

**POST** `/api/events/notify`

接收其他服务的异常事件通知。

请求体:
```json
{
  "eventType": "TICKER_SYNC_TIMEOUT",
  "serviceName": "aifuturetrade-async-service",
  "severity": "ERROR",
  "title": "Ticker同步超时告警",
  "message": "Ticker数据同步已超过3分钟未输出日志",
  "metadata": {
    "lastSyncTime": "2026-02-25T10:00:00",
    "minutesSinceLastSync": 5
  }
}
```

响应:
```json
{
  "success": true,
  "alertId": 1,
  "message": "事件通知已接收并处理"
}
```

### 2. 查询告警记录

**GET** `/api/alerts?page=1&pageSize=20&alertType=TICKER_SYNC_TIMEOUT&status=OPEN`

查询告警记录，支持分页和过滤。

响应:
```json
{
  "success": true,
  "data": [...],
  "total": 10,
  "page": 1,
  "pageSize": 20
}
```

### 3. 手动触发告警处置

**POST** `/api/alerts/{id}/handle`

手动触发指定告警的处置动作。

响应:
```json
{
  "success": true,
  "message": "告警处置已触发"
}
```

### 4. 查询微信群配置

**GET** `/api/alerts/wechat-groups`

查询所有微信群配置。

响应:
```json
{
  "success": true,
  "data": [...]
}
```

## 监控配置

### Async Service监控配置

在`.env`文件中配置:

```bash
# Ticker同步超时阈值（分钟）
ASYNC_MONITOR_TICKER_TIMEOUT=3

# 监控检查间隔（秒）
ASYNC_MONITOR_CHECK_INTERVAL=60

# Trade Monitor服务地址
TRADE_MONITOR_URL=http://trade-monitor:5005
```

### 监控工作流程

1. **Async Service**启动时，自动启动Ticker同步监控服务
2. 每次ticker数据同步成功后，记录同步时间
3. 监控服务每60秒检查一次，如果超过3分钟未同步，触发告警
4. 调用Trade Monitor的`/api/events/notify`接口发送告警
5. Trade Monitor接收告警后:
   - 创建告警记录
   - 发送微信通知
   - 自动重启async-service容器
   - 更新告警记录状态

## 告警类型

目前支持的告警类型:

- `TICKER_SYNC_TIMEOUT`: Ticker同步超时（自动重启容器）
- `CONTAINER_DOWN`: 容器停止运行
- 更多类型可以根据需要扩展

## 严重程度

- `INFO`: 信息
- `WARNING`: 警告
- `ERROR`: 错误
- `CRITICAL`: 严重

## 故障排查

### 1. 微信通知未收到

- 检查`.env`文件中的`WECHAT_WEBHOOK_URL`是否正确
- 检查`wechat_groups`表中的配置是否启用
- 检查`alert_records`表中的`wechat_sent`字段
- 查看trade-monitor日志: `docker-compose logs -f trade-monitor`

### 2. 容器重启失败

- 检查trade-monitor容器是否挂载了Docker socket
- 检查容器名称是否正确（默认: `aifuturetrade-async-service`）
- 查看trade-monitor日志中的错误信息

### 3. 监控未触发

- 检查async-service是否正常启动
- 检查async-service日志中是否有ticker同步日志
- 检查监控配置是否正确
- 查看async-service日志: `docker-compose logs -f async-service`

## 日志查看

```bash
# 查看trade-monitor日志
docker-compose logs -f trade-monitor

# 查看async-service日志
docker-compose logs -f async-service

# 查看告警日志
docker exec -it aifuturetrade-trade-monitor tail -f /app/logs/alert.log
```

## 测试

### 模拟ticker同步超时

1. 停止async-service的ticker同步（修改代码跳过日志输出）
2. 等待3分钟
3. 检查是否收到微信告警
4. 检查async-service容器是否自动重启
5. 查询`alert_records`表验证告警记录

### 手动触发告警

```bash
curl -X POST http://localhost:5005/api/events/notify \
  -H "Content-Type: application/json" \
  -d '{
    "eventType": "TICKER_SYNC_TIMEOUT",
    "serviceName": "aifuturetrade-async-service",
    "severity": "ERROR",
    "title": "测试告警",
    "message": "这是一条测试告警消息"
  }'
```

## 注意事项

1. **企业微信限制**: 企业微信机器人有频率限制，建议合理设置监控检查间隔
2. **容器命名**: 确保容器名称与配置一致，否则无法重启
3. **Docker Socket**: trade-monitor必须挂载Docker socket才能管理容器
4. **数据库表**: 首次使用前必须创建数据库表
5. **微信群配置**: 至少配置一个启用的微信群才能发送通知
