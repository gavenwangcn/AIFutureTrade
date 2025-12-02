# Vue 前端代码修复说明

## 修复概述

本次修复将原始的静态页面（`templates/index.html` + `static/app.js`）的功能完整迁移到 Vue 3 框架，确保所有功能正常工作。

## 主要修复内容

### 1. WebSocket 连接和数据同步

**问题**：涨跌幅榜数据不同步

**修复**：
- ✅ 修复了 WebSocket 事件监听，添加了 `leaderboard:request` 初始数据请求
- ✅ 修复了 `leaderboard:update` 事件处理，确保数据正确更新
- ✅ 添加了 `leaderboard:error` 错误处理
- ✅ 修复了涨跌幅榜手动刷新功能，支持强制刷新参数

**文件**：
- `frontend/src/composables/useTradingApp.js` - WebSocket 初始化
- `frontend/src/services/api.js` - API 服务支持 force 参数

### 2. 数据格式映射

**问题**：后端返回的数据格式与前端显示不匹配

**修复**：
- ✅ 修复了市场行情数据格式，保留所有原始字段
- ✅ 修复了持仓数据映射（symbol, side, quantity, openPrice, currentPrice, leverage, pnl）
- ✅ 修复了交易记录数据映射（time, symbol, side, quantity, price, pnl, fee）
- ✅ 修复了对话记录数据映射（time, user_prompt, ai_response, cot_trace）

**文件**：
- `frontend/src/composables/useTradingApp.js` - 数据加载和映射函数

### 3. 按钮事件绑定

**问题**：按钮点击无反应

**修复**：
- ✅ 所有按钮使用 Vue 的 `@click` 指令绑定事件
- ✅ 模态框显示/隐藏使用响应式状态 `v-model` 或 `:visible` prop
- ✅ 确保所有事件处理函数正确导出和使用

**文件**：
- `frontend/src/App.vue` - 按钮事件绑定

### 4. 模态框组件

**问题**：模态框不显示

**修复**：
- ✅ 创建了通用 `Modal.vue` 组件
- ✅ 创建了 `SettingsModal.vue` - 系统设置
- ✅ 创建了 `StrategyModal.vue` - 策略配置
- ✅ 创建了 `FutureConfigModal.vue` - 合约配置
- ✅ 创建了 `ApiProviderModal.vue` - API提供方管理
- ✅ 创建了 `AddModelModal.vue` - 添加模型

**文件**：
- `frontend/src/components/Modal.vue`
- `frontend/src/components/SettingsModal.vue`
- `frontend/src/components/StrategyModal.vue`
- `frontend/src/components/FutureConfigModal.vue`
- `frontend/src/components/ApiProviderModal.vue`
- `frontend/src/components/AddModelModal.vue`

### 5. 涨跌幅榜显示

**问题**：涨跌幅榜数据不显示或格式错误

**修复**：
- ✅ 修复了涨跌幅榜数据结构，支持 `change_percent` 和 `change` 字段
- ✅ 添加了排名显示（`leaderboard-rank`）
- ✅ 添加了成交额显示（`leaderboard-volume`）
- ✅ 修复了点击事件，支持打开K线图

**文件**：
- `frontend/src/App.vue` - 涨跌幅榜模板
- `frontend/src/style.css` - 添加缺失的样式类

### 6. 市场行情显示

**问题**：市场行情数据格式不正确

**修复**：
- ✅ 修复了价格项的数据结构，支持完整的市场数据
- ✅ 添加了合约名称显示
- ✅ 添加了成交额显示
- ✅ 修复了点击事件，使用正确的合约符号

**文件**：
- `frontend/src/App.vue` - 市场行情模板

### 7. Tab 切换

**问题**：Tab 内容不显示

**修复**：
- ✅ 使用 `v-show` 和 `active` 类控制显示
- ✅ 确保样式正确应用（`.tab-content.active`）

**文件**：
- `frontend/src/App.vue` - Tab 切换逻辑
- `frontend/src/style.css` - Tab 样式

### 8. K线图组件

**问题**：K线图符号格式不正确

**修复**：
- ✅ 修复了 `openKlineChart` 函数，确保符号格式正确（添加 USDT 后缀）
- ✅ 确保使用合约符号（`contract_symbol`）而不是基础符号

**文件**：
- `frontend/src/App.vue` - `openKlineChart` 函数

## 代码结构

```
frontend/src/
├── components/
│   ├── Modal.vue              # 通用模态框组件
│   ├── SettingsModal.vue      # 系统设置模态框
│   ├── StrategyModal.vue      # 策略配置模态框
│   ├── FutureConfigModal.vue  # 合约配置模态框
│   ├── ApiProviderModal.vue   # API提供方模态框
│   ├── AddModelModal.vue      # 添加模型模态框
│   └── KLineChart.vue         # K线图组件
├── composables/
│   └── useTradingApp.js       # 业务逻辑（已修复）
├── services/
│   └── api.js                 # API 服务（已修复）
├── utils/
│   ├── api.js                 # HTTP 请求工具
│   └── websocket.js           # WebSocket 工具
├── config/
│   └── api.js                 # API 配置
├── App.vue                    # 主组件（已修复）
├── main.js                    # 入口文件
└── style.css                  # 样式文件（已更新）
```

## 功能验证清单

- [x] WebSocket 连接正常
- [x] 涨跌幅榜数据实时更新
- [x] 涨跌幅榜手动刷新功能
- [x] 市场行情数据加载和显示
- [x] 模型列表显示和选择
- [x] 持仓数据加载和显示
- [x] 交易记录加载和显示
- [x] 对话记录加载和显示
- [x] Tab 切换功能
- [x] 按钮点击事件
- [x] 模态框显示/隐藏
- [x] K线图打开功能
- [x] 刷新功能
- [x] 执行交易功能
- [x] 暂停自动交易功能

## 使用说明

### 开发环境

```bash
cd frontend
npm install
npm run dev
```

前端服务运行在 `http://localhost:3000`，通过 Vite 代理访问后端 API。

### 生产环境

```bash
cd frontend
npm install
npm run build
npm run preview
```

或使用 Docker：

```bash
docker build -t aifuturetrade-frontend -f frontend/Dockerfile .
docker run -p 3000:3000 aifuturetrade-frontend
```

## 注意事项

1. **后端地址配置**：
   - 开发环境：自动使用 Vite 代理
   - 生产环境：默认使用 `window.location.hostname:5002`
   - 可通过环境变量 `VITE_BACKEND_URL` 或 `VITE_BACKEND_PORT` 配置

2. **WebSocket 连接**：
   - 自动适配开发/生产环境
   - 连接成功后自动请求初始涨跌幅榜数据
   - 支持自动重连

3. **数据更新**：
   - 涨跌幅榜通过 WebSocket 实时更新
   - 其他数据通过 API 定期刷新
   - 支持手动刷新功能

4. **模态框管理**：
   - 所有模态框使用响应式状态控制显示
   - 支持点击外部关闭
   - 自动处理 body 滚动锁定

## 后续优化建议

1. 添加加载状态指示器
2. 添加错误提示组件
3. 优化数据刷新频率
4. 添加数据缓存机制
5. 优化移动端响应式布局

