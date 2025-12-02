# 前端代码优化说明

## 优化概述

本次优化重构了前端代码结构，使其更好地适配 Vue 3 Composition API 和与后端 app.py 的交互。

## 主要优化内容

### 1. 统一的 API 客户端封装

#### 创建的文件：
- `src/utils/api.js` - 统一的 HTTP 请求封装
- `src/services/api.js` - API 服务模块，封装所有后端接口

#### 优势：
- ✅ 统一的错误处理
- ✅ 统一的请求/响应格式
- ✅ 更好的代码复用性
- ✅ 易于维护和扩展

### 2. WebSocket 连接管理

#### 创建的文件：
- `src/utils/websocket.js` - WebSocket 连接工具

#### 优势：
- ✅ 统一的连接配置
- ✅ 自动适配开发/生产环境
- ✅ 更好的错误处理

### 3. 优化的 Composable

#### 更新的文件：
- `src/composables/useTradingApp.js` - 重构的业务逻辑

#### 改进：
- ✅ 使用统一的 API 服务
- ✅ 添加加载状态管理（loading）
- ✅ 添加错误状态管理（errors）
- ✅ 添加计算属性（computed）
- ✅ 更好的响应式数据管理
- ✅ 并行加载优化性能

### 4. API 配置优化

#### 更新的文件：
- `src/config/api.js` - API 基础 URL 配置

#### 改进：
- ✅ 自动适配开发/生产环境
- ✅ 支持环境变量配置
- ✅ 默认使用当前域名（前端后端同机）
- ✅ 端口可配置

## 代码结构

```
frontend/src/
├── config/
│   └── api.js              # API 基础配置
├── utils/
│   ├── api.js              # HTTP 请求工具
│   └── websocket.js        # WebSocket 工具
├── services/
│   └── api.js              # API 服务模块
├── composables/
│   └── useTradingApp.js    # 业务逻辑 Composable
└── components/
    └── KLineChart.vue      # K线图组件
```

## API 服务模块

### 模型 API (modelApi)
- `getAll()` - 获取所有模型
- `create(data)` - 创建模型
- `delete(modelId)` - 删除模型
- `getPortfolio(modelId)` - 获取投资组合
- `getTrades(modelId, limit)` - 获取交易记录
- `getConversations(modelId, limit)` - 获取对话记录
- `execute(modelId)` - 执行交易
- `setAutoTrading(modelId, enabled)` - 设置自动交易

### 市场数据 API (marketApi)
- `getPrices()` - 获取市场行情
- `getLeaderboard(limit)` - 获取涨跌幅榜
- `getKlines(symbol, interval, limit)` - 获取K线数据
- `getIndicators(symbol)` - 获取技术指标

### 其他 API
- `providerApi` - API 提供方管理
- `futuresApi` - 合约配置管理
- `settingsApi` - 系统设置

## 状态管理

### 响应式状态
- `loading` - 各模块的加载状态
- `errors` - 各模块的错误信息
- `isLoading` - 计算属性，是否有加载中的请求

### 使用示例
```javascript
const { loading, errors, isLoading } = useTradingApp()

// 检查特定模块是否加载中
if (loading.value.models) {
  // 显示加载提示
}

// 检查是否有错误
if (errors.value.models) {
  // 显示错误信息
}
```

## 环境配置

### 开发环境
- 自动使用 Vite 代理
- 无需配置环境变量

### 生产环境
- 默认：当前域名 + 端口 5002
- 可配置：`VITE_BACKEND_PORT=5002`
- 或完整URL：`VITE_BACKEND_URL=http://host:port`

## 错误处理

所有 API 调用都包含统一的错误处理：
- 网络错误
- HTTP 错误
- 业务错误

错误信息存储在 `errors` 对象中，便于 UI 显示。

## 性能优化

1. **并行加载**：使用 `Promise.all()` 并行加载数据
2. **按需加载**：只在需要时加载模型相关数据
3. **统一封装**：减少重复代码

## 向后兼容

- ✅ 保持原有的 API 接口不变
- ✅ 保持原有的数据结构
- ✅ 保持原有的功能特性

## 使用建议

1. **新增 API 调用**：在 `src/services/api.js` 中添加
2. **使用 API**：通过导入对应的 API 服务模块
3. **错误处理**：使用统一的错误处理机制
4. **加载状态**：使用 `loading` 对象管理加载状态

